"""pgvector vector similarity search helpers."""

import json
import logging
from typing import Any

from sqlalchemy import text

from app.db.postgres import AsyncSessionLocal

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


async def search_similar_frames(
    video_id: str,
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Return the most similar video frames to a query embedding.

    Uses pgvector cosine distance (<=>). Returns an empty list if the vector
    column is not available (e.g. JSONB fallback) or pgvector is unreachable.
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
            logger.warning("pgvector frame search failed (%s); returning empty", exc)
            return []

    return [dict(row) for row in rows]


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
            logger.warning("pgvector node search failed (%s); returning empty", exc)
            return []

    return [dict(row) for row in rows]


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
            logger.warning("pgvector course frame search failed (%s); returning empty", exc)
            return []

    return [dict(row) for row in rows]
