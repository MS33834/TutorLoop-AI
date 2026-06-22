"""Adaptive learning path recommendation service."""

import logging
import math
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.neo4j import get_graph
from app.db.postgres import AsyncSessionLocal
from app.models.db import Video, VideoFrame
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


async def _find_best_frame(course_id: str, node: dict) -> dict | None:
    """Find the video frame most similar to the node text."""
    frames = await _fetch_course_frames(course_id)
    if not frames:
        return None

    query_text = _node_text(node)
    query_embedding = encode_text(query_text)

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

    # Build candidate set using Neo4j graph if available.
    graph = {"nodes": [], "edges": []}
    neo4j_available = False
    try:
        graph = await get_graph(course_id)
        neo4j_available = True
    except Exception as exc:
        logger.warning("Neo4j unavailable for recommendation, using fallback: %s", exc)

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if not nodes and not neo4j_available:
        # Fallback: recommend from mastery records only.
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
                "该知识点掌握度最低，建议优先学习（Neo4j 不可用，采用简单兜底策略）。"
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
        "reason": "该知识点未掌握且前置条件已满足，建议优先学习。",
    }
