"""Adaptive learning path recommendation service."""

import logging
import math
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.neo4j import get_graph
from app.db.postgres import AsyncSessionLocal
from app.db.vector_search import search_similar_frames_in_course
from app.models.db import KnowledgeEdge, KnowledgeNode, Video, VideoFrame
from app.services import bkt_engine
from app.services.embedding_service import encode_text
from app.services.recommendation_strategies import get_strategy

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _text_overlap_score(query: str, text: str | None) -> float:
    """Simple token overlap fallback when embeddings are unavailable."""
    if not text:
        return 0.0
    query_tokens = set(query.lower().split())
    text_tokens = set(text.lower().split())
    if not query_tokens:
        return 0.0
    overlap = len(query_tokens & text_tokens)
    return overlap / len(query_tokens)


def _node_text(node: dict) -> str:
    return f"{node.get('name', '')} {node.get('description', '')}".strip()


async def _fetch_course_frames(course_id: str) -> list[VideoFrame]:
    """Return all video frames for a course, ordered by timestamp."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(VideoFrame)
            .join(Video)
            .where(Video.course_id == course_id)
            .options(selectinload(VideoFrame.video))
            .order_by(VideoFrame.timestamp_seconds)
        )
        return list(result.scalars().all())


async def _load_graph_from_postgres(course_id: str) -> dict:
    """Load knowledge graph nodes and edges from Postgres as Neo4j fallback."""
    async with AsyncSessionLocal() as session:
        node_result = await session.execute(
            select(KnowledgeNode)
            .where(KnowledgeNode.course_id == course_id)
            .order_by(KnowledgeNode.created_at)
        )
        nodes = list(node_result.scalars().all())

        edge_result = await session.execute(
            select(KnowledgeEdge).where(KnowledgeEdge.course_id == course_id)
        )
        edges = list(edge_result.scalars().all())

    return {
        "nodes": [
            {
                "id": n.id,
                "name": n.name,
                "description": n.description or "",
                "threshold": n.threshold,
            }
            for n in nodes
        ],
        "edges": [
            {
                "from": e.source_id,
                "to": e.target_id,
                "relation": e.relation,
            }
            for e in edges
        ],
    }


async def _find_best_frame(course_id: str, node: dict) -> dict | None:
    """Find the video frame most similar to the node text.

    Uses pgvector HNSW approximate nearest neighbor search when available,
    falling back to brute-force cosine similarity if the vector search fails.
    """
    query_text = _node_text(node)
    query_embedding = encode_text(query_text)

    # Try pgvector ANN search first (O(log n) with HNSW index).
    try:
        similar = await search_similar_frames_in_course(
            course_id=course_id,
            query_embedding=query_embedding,
            top_k=1,
        )
        if similar:
            row = similar[0]
            return {
                "video_id": row["video_id"],
                "timestamp_seconds": row["timestamp_seconds"],
                "file_path": row["file_path"],
                "caption": row["caption"],
                "similarity": round(1.0 - float(row["distance"]), 4),
            }
    except Exception as exc:
        logger.warning("Vector frame search failed, using fallback: %s", exc)

    # Fallback: brute-force scan over all course frames.
    frames = await _fetch_course_frames(course_id)
    if not frames:
        return None

    best_frame = frames[0]
    best_score = -1.0
    for frame in frames:
        caption = frame.caption or Path(frame.file_path).name
        frame_embedding = frame.embedding
        if isinstance(frame_embedding, str):
            import json

            try:
                frame_embedding = json.loads(frame_embedding)
            except Exception:
                frame_embedding = None

        if frame_embedding and query_embedding:
            score = _cosine_similarity(query_embedding, frame_embedding)
        else:
            score = _text_overlap_score(query_text, caption)

        if score > best_score:
            best_score = score
            best_frame = frame

    return {
        "video_id": best_frame.video_id,
        "timestamp_seconds": best_frame.timestamp_seconds,
        "file_path": best_frame.file_path,
        "caption": best_frame.caption,
        "similarity": round(best_score, 4),
    }


def _build_prereq_map(edges: list[dict]) -> dict[str, set[str]]:
    """Map node_id -> set of prerequisite node_ids, ignoring cycles."""
    prereq_map: dict[str, set[str]] = {}
    for edge in edges:
        if edge.get("relation", "prerequisite") != "prerequisite":
            continue
        from_id = edge.get("from")
        to_id = edge.get("to")
        if not from_id or not to_id or from_id == to_id:
            continue
        prereq_map.setdefault(to_id, set()).add(from_id)
    return prereq_map


def _compute_depth(prereq_map: dict[str, set[str]]) -> dict[str, int]:
    """Compute longest prerequisite chain depth for each node (DAG)."""
    depth_cache: dict[str, int] = {}

    def depth(node_id: str, visiting: set[str] | None = None) -> int:
        if node_id in depth_cache:
            return depth_cache[node_id]
        if visiting is None:
            visiting = set()
        if node_id in visiting:
            return 0  # cycle guard
        visiting.add(node_id)
        prereqs = prereq_map.get(node_id, set())
        max_depth = 1 + max((depth(p, visiting) for p in prereqs), default=0)
        visiting.discard(node_id)
        depth_cache[node_id] = max_depth
        return max_depth

    all_nodes = set(prereq_map.keys()) | {p for deps in prereq_map.values() for p in deps}
    for node_id in all_nodes:
        depth(node_id)
    return depth_cache


async def recommend_next(user_id: str, course_id: str) -> dict | None:
    """Recommend the next knowledge node for a user in a course."""
    mastery_records = await bkt_engine.get_mastery(user_id, course_id)
    mastery_by_node = {record["node_id"]: record for record in mastery_records}

    # Build candidate set from Postgres first (source of truth after editing),
    # falling back to Neo4j if Postgres has no graph data.
    graph = {"nodes": [], "edges": []}
    try:
        graph = await _load_graph_from_postgres(course_id)
    except Exception as exc:
        logger.warning("Postgres graph load failed: %s", exc)

    if not graph.get("nodes"):
        try:
            graph = await get_graph(course_id)
        except Exception as neo_exc:
            logger.warning("Neo4j fallback for recommendation failed: %s", neo_exc)

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if not nodes:
        # Final fallback: recommend from mastery records only.
        not_mastered = [r for r in mastery_records if r["p_known"] < r["threshold"]]
        if not not_mastered:
            return None
        candidate = min(not_mastered, key=lambda r: r["p_known"])
        frame = await _find_best_frame(course_id, candidate)
        return {
            "node": {
                "id": candidate["node_id"],
                "name": candidate["name"],
                "description": candidate["description"],
                "threshold": candidate["threshold"],
                "p_known": candidate["p_known"],
            },
            "video_id": frame["video_id"] if frame else None,
            "timestamp_seconds": frame["timestamp_seconds"] if frame else None,
            "reason": (
                f"「{candidate['name']}」当前掌握度 {candidate['p_known']:.0%}，"
                f"阈值 {candidate['threshold']:.0%}，"
                f"差距 {candidate['threshold'] - candidate['p_known']:.2f}，"
                f"建议优先攻克。"
            ),
        }

    # Use graph-aware candidate selection.
    prereq_map = _build_prereq_map(edges)
    mastered_ids = {
        node_id
        for node_id, record in mastery_by_node.items()
        if record["p_known"] >= record["threshold"]
    }

    candidates = []
    for node in nodes:
        node_id = node.get("id")
        record = mastery_by_node.get(node_id)
        if record is None:
            continue
        if record["p_known"] >= record["threshold"]:
            continue
        prereqs = prereq_map.get(node_id, set())
        if not prereqs.issubset(mastered_ids):
            continue
        candidates.append((node, record))

    if not candidates:
        return None

    strategy = get_strategy(settings.recommend_strategy)
    depth_map = _compute_depth(prereq_map)

    candidate_nodes = [node for node, _ in candidates]
    ranked = strategy.rank(
        candidate_nodes,
        mastery_by_node,
        {"depth_map": depth_map},
    )

    best_node = ranked[0]
    best_record = mastery_by_node.get(best_node.get("id"), {})
    frame = await _find_best_frame(course_id, best_node)

    return {
        "node": {
            "id": best_node.get("id"),
            "name": best_node.get("name"),
            "description": best_node.get("description"),
            "threshold": best_record.get("threshold", 0.8),
            "p_known": best_record.get("p_known", 0.0),
        },
        "video_id": frame["video_id"] if frame else None,
        "timestamp_seconds": frame["timestamp_seconds"] if frame else None,
        "reason": (
            f"「{best_node.get('name')}」当前掌握度 {best_record.get('p_known', 0.0):.0%}，"
            f"阈值 {best_record.get('threshold', 0.8):.0%}，"
            f"先修内容已学完，正是攻克它的好时机。"
        ),
    }
