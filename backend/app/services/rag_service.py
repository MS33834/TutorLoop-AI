"""Multimodal RAG retrieval service backed by pgvector."""

import json
import logging
import math

from sqlalchemy import select, text

from app.db.postgres import AsyncSessionLocal
from app.models.db import KnowledgeNode, Video, VideoFrame
from app.services.embedding_service import encode_text

logger = logging.getLogger(__name__)

TOP_K_FRAMES = 4
TOP_K_NODES = 3


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _to_float_vector(value) -> list[float]:
    """Normalize an embedding stored as list/JSONB/Vector to a Python list of floats."""
    if value is None:
        return []
    if isinstance(value, list):
        return [float(v) for v in value]
    if isinstance(value, str):
        parsed = json.loads(value)
        return [float(v) for v in parsed]
    return []


def _format_vector(query_embedding: list[float]) -> str:
    return f"[{','.join(str(float(v)) for v in query_embedding)}]"


async def _nearest_frames_by_timestamp(
    video_id: str, timestamp: float | None, top_k: int
) -> list[dict]:
    if timestamp is None:
        return []
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT id, timestamp_seconds, file_path, caption
                FROM video_frames
                WHERE video_id = :video_id
                ORDER BY ABS(timestamp_seconds - :timestamp)
                LIMIT :limit
                """
            ),
            {"video_id": video_id, "timestamp": timestamp, "limit": top_k},
        )
        return [dict(row) for row in result.mappings().all()]


async def _similar_frames_by_vector(
    video_id: str, query_embedding: list[float], top_k: int
) -> list[dict]:
    vec = _format_vector(query_embedding)
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    """
                    SELECT id, timestamp_seconds, file_path, caption,
                           1 - (embedding <=> :vec::vector) AS similarity
                    FROM video_frames
                    WHERE video_id = :video_id AND embedding IS NOT NULL
                    ORDER BY embedding <=> :vec::vector
                    LIMIT :limit
                    """
                ),
                {"video_id": video_id, "vec": vec, "limit": top_k},
            )
            return [dict(row) for row in result.mappings().all()]
    except Exception as exc:
        logger.warning("Vector frame search failed: %s", exc)
        return []


async def _similar_frames_by_python(
    video_id: str, query_embedding: list[float], top_k: int
) -> list[dict]:
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
            "timestamp_seconds": frame.timestamp_seconds,
            "file_path": frame.file_path,
            "caption": frame.caption,
            "similarity": round(sim, 4),
        }
        for sim, frame in scored[:top_k]
    ]


async def _similar_nodes_by_vector(
    course_id: str, query_embedding: list[float], top_k: int
) -> list[dict]:
    vec = _format_vector(query_embedding)
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    """
                    SELECT id, name, description,
                           1 - (embedding <=> :vec::vector) AS similarity
                    FROM knowledge_nodes
                    WHERE course_id = :course_id AND embedding IS NOT NULL
                    ORDER BY embedding <=> :vec::vector
                    LIMIT :limit
                    """
                ),
                {"course_id": course_id, "vec": vec, "limit": top_k},
            )
            return [dict(row) for row in result.mappings().all()]
    except Exception as exc:
        logger.warning("Vector node search failed: %s", exc)
        return []


async def _similar_nodes_by_python(
    course_id: str, query_embedding: list[float], top_k: int
) -> list[dict]:
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
            "name": node.name,
            "description": node.description,
            "similarity": round(sim, 4),
        }
        for sim, node in scored[:top_k]
    ]


async def retrieve_context(
    video_id: str,
    question: str,
    screenshot_path: str | None = None,
    timestamp: float | None = None,
) -> dict:
    """Retrieve relevant video frames and knowledge nodes for a question."""
    question_embedding = encode_text(question)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Video.course_id).where(Video.id == video_id)
        )
        course_id = result.scalar_one_or_none()

    timestamp_frames = await _nearest_frames_by_timestamp(
        video_id, timestamp, TOP_K_FRAMES
    )

    similar_frames = await _similar_frames_by_vector(
        video_id, question_embedding, TOP_K_FRAMES
    )
    if not similar_frames:
        similar_frames = await _similar_frames_by_python(
            video_id, question_embedding, TOP_K_FRAMES
        )

    seen = set()
    merged_frames = []
    for frame in timestamp_frames + similar_frames:
        if frame["id"] not in seen:
            seen.add(frame["id"])
            merged_frames.append(frame)

    similar_nodes = []
    if course_id:
        similar_nodes = await _similar_nodes_by_vector(
            course_id, question_embedding, TOP_K_NODES
        )
        if not similar_nodes:
            similar_nodes = await _similar_nodes_by_python(
                course_id, question_embedding, TOP_K_NODES
            )

    return {
        "frames": merged_frames[: TOP_K_FRAMES * 2],
        "knowledge_nodes": similar_nodes,
        "screenshot_path": screenshot_path,
    }
