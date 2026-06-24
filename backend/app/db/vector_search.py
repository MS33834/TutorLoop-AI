"""pgvector vector similarity search helpers."""

import json
import logging
import math
from typing import Any

from sqlalchemy import select, text

from app.db.postgres import AsyncSessionLocal
from app.models.db import KnowledgeNode, VideoFrame

logger = logging.getLogger(__name__)


def _normalize_embedding(embedding: list[float] | str | None) -> list[float] | None:
    """Ensure embedding is a list of floats."""
    if embedding is None:
        return None
    if isinstance(embedding, str):
        try:
            embedding = json.loads(embedding)
        except Exception:
            return None
    if not isinstance(embedding, list):
        return None
    try:
        return [float(x) for x in embedding]
    except Exception:
        return None


def _pgvector_literal(embedding: list[float]) -> str:
    """Return a PostgreSQL vector literal string."""
    return "[" + ",".join(str(x) for x in embedding) + "]"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two dense vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _to_float_vector(value: Any) -> list[float]:
    """Normalize an embedding stored as list/JSONB/Vector to a Python list."""
    if value is None:
        return []
    if isinstance(value, list):
        return [float(v) for v in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return [float(v) for v in parsed]
        except Exception:
            return []
    return []


async def _fallback_similar_frames(
    video_id: str, query_embedding: list[float], top_k: int
) -> list[dict[str, Any]]:
    """Brute-force cosine similarity fallback for video frames."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(VideoFrame).where(
                VideoFrame.video_id == video_id, VideoFrame.embedding.is_not(None)
            )
        )
        frames = list(result.scalars().all())

    scored = []
    for frame in frames:
        frame_embedding = _to_float_vector(frame.embedding)
        sim = _cosine_similarity(query_embedding, frame_embedding) if frame_embedding else 0.0
        scored.append((sim, frame))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "id": frame.id,
            "video_id": frame.video_id,
            "timestamp_seconds": frame.timestamp_seconds,
            "file_path": frame.file_path,
            "caption": frame.caption,
            "distance": 1.0 - sim,
        }
        for sim, frame in scored[:top_k]
    ]


async def search_similar_frames(
    video_id: str,
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Return the most similar video frames to a query embedding.

    Uses pgvector cosine distance (<=>) when available, otherwise falls back to
    an in-memory cosine similarity scan so RAG still works without pgvector.
    """
    embedding = _normalize_embedding(query_embedding)
    if not embedding:
        return []

    sql = text(
        """
        SELECT id, video_id, timestamp_seconds, file_path, caption,
               embedding <=> :query_embedding AS distance
        FROM video_frames
        WHERE video_id = :video_id
        ORDER BY embedding <=> :query_embedding
        LIMIT :top_k
        """
    )

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                sql,
                {
                    "query_embedding": _pgvector_literal(embedding),
                    "video_id": video_id,
                    "top_k": top_k,
                },
            )
            rows = result.mappings().all()
        except Exception as exc:
            logger.warning("pgvector frame search failed (%s); using Python fallback", exc)
            return await _fallback_similar_frames(video_id, embedding, top_k)

    return [dict(row) for row in rows]


async def _fallback_similar_nodes(
    course_id: str, query_embedding: list[float], top_k: int
) -> list[dict[str, Any]]:
    """Brute-force cosine similarity fallback for knowledge nodes."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(KnowledgeNode).where(
                KnowledgeNode.course_id == course_id,
                KnowledgeNode.embedding.is_not(None),
            )
        )
        nodes = list(result.scalars().all())

    scored = []
    for node in nodes:
        node_embedding = _to_float_vector(node.embedding)
        sim = _cosine_similarity(query_embedding, node_embedding) if node_embedding else 0.0
        scored.append((sim, node))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "id": node.id,
            "course_id": node.course_id,
            "name": node.name,
            "description": node.description,
            "threshold": node.threshold,
            "distance": 1.0 - sim,
        }
        for sim, node in scored[:top_k]
    ]


async def search_similar_nodes(
    course_id: str,
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Return the most similar knowledge nodes to a query embedding."""
    embedding = _normalize_embedding(query_embedding)
    if not embedding:
        return []

    sql = text(
        """
        SELECT id, course_id, name, description, threshold,
               embedding <=> :query_embedding AS distance
        FROM knowledge_nodes
        WHERE course_id = :course_id
        ORDER BY embedding <=> :query_embedding
        LIMIT :top_k
        """
    )

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                sql,
                {
                    "query_embedding": _pgvector_literal(embedding),
                    "course_id": course_id,
                    "top_k": top_k,
                },
            )
            rows = result.mappings().all()
        except Exception as exc:
            logger.warning("pgvector node search failed (%s); using Python fallback", exc)
            return await _fallback_similar_nodes(course_id, embedding, top_k)

    return [dict(row) for row in rows]


async def _fallback_similar_frames_in_course(
    course_id: str, query_embedding: list[float], top_k: int
) -> list[dict[str, Any]]:
    """Brute-force cosine similarity fallback for frames across a course."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(VideoFrame)
            .join(Video)
            .where(Video.course_id == course_id, VideoFrame.embedding.is_not(None))
        )
        frames = list(result.scalars().all())

    scored = []
    for frame in frames:
        frame_embedding = _to_float_vector(frame.embedding)
        sim = _cosine_similarity(query_embedding, frame_embedding) if frame_embedding else 0.0
        scored.append((sim, frame))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "id": frame.id,
            "video_id": frame.video_id,
            "timestamp_seconds": frame.timestamp_seconds,
            "file_path": frame.file_path,
            "caption": frame.caption,
            "distance": 1.0 - sim,
        }
        for sim, frame in scored[:top_k]
    ]


async def search_similar_frames_in_course(
    course_id: str,
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Return the most similar video frames across all videos in a course."""
    embedding = _normalize_embedding(query_embedding)
    if not embedding:
        return []

    sql = text(
        """
        SELECT vf.id, vf.video_id, vf.timestamp_seconds, vf.file_path, vf.caption,
               vf.embedding <=> :query_embedding AS distance
        FROM video_frames vf
        JOIN videos v ON vf.video_id = v.id
        WHERE v.course_id = :course_id
        ORDER BY vf.embedding <=> :query_embedding
        LIMIT :top_k
        """
    )

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                sql,
                {
                    "query_embedding": _pgvector_literal(embedding),
                    "course_id": course_id,
                    "top_k": top_k,
                },
            )
            rows = result.mappings().all()
        except Exception as exc:
            logger.warning("pgvector course frame search failed (%s); using Python fallback", exc)
            return await _fallback_similar_frames_in_course(course_id, embedding, top_k)

    return [dict(row) for row in rows]
