"""Multimodal RAG retrieval service."""

import logging
import math
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

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
        import json

        parsed = json.loads(value)
        return [float(v) for v in parsed]
    return []


async def _fetch_frames(video_id: str) -> list[VideoFrame]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(VideoFrame)
            .where(VideoFrame.video_id == video_id)
            .options(selectinload(VideoFrame.video))
            .order_by(VideoFrame.timestamp_seconds)
        )
        return list(result.scalars().all())


async def _fetch_nodes(course_id: str) -> list[KnowledgeNode]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(KnowledgeNode).where(KnowledgeNode.course_id == course_id)
        )
        return list(result.scalars().all())


def _retrieve_nearest_frames(
    frames: list[VideoFrame], timestamp: float | None, top_k: int
) -> list[dict]:
    if timestamp is None:
        return []

    scored = [
        (abs(frame.timestamp_seconds - timestamp), frame) for frame in frames
    ]
    scored.sort(key=lambda x: x[0])
    return [
        {
            "id": frame.id,
            "timestamp_seconds": frame.timestamp_seconds,
            "file_path": frame.file_path,
            "caption": frame.caption,
        }
        for _, frame in scored[:top_k]
    ]


def _retrieve_similar_frames(
    frames: list[VideoFrame], question_embedding: list[float], top_k: int
) -> list[dict]:
    scored = []
    for frame in frames:
        text = frame.caption or Path(frame.file_path).name
        frame_embedding = _to_float_vector(frame.embedding)
        if frame_embedding:
            sim = _cosine_similarity(question_embedding, frame_embedding)
        else:
            # No embedding yet: use a simple text overlap fallback
            overlap = sum(1 for word in text.split() if word in str(question_embedding))
            sim = overlap * 0.01
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


def _retrieve_similar_nodes(
    nodes: list[KnowledgeNode], question_embedding: list[float], top_k: int
) -> list[dict]:
    scored = []
    for node in nodes:
        text = f"{node.name} {node.description or ''}".strip()
        node_embedding = _to_float_vector(node.embedding)
        if node_embedding:
            sim = _cosine_similarity(question_embedding, node_embedding)
        else:
            sim = 0.0
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
    """Retrieve relevant video frames and knowledge nodes for a question.

    Args:
        video_id: Target video ID.
        question: User question text.
        screenshot_path: Optional screenshot image path (reserved for future use).
        timestamp: Optional video timestamp to find nearby frames.

    Returns:
        Dict with "frames" and "knowledge_nodes".
    """
    frames = await _fetch_frames(video_id)
    question_embedding = encode_text(question)

    # Need course_id for knowledge nodes; infer from the first frame's video
    course_id = None
    if frames:
        course_id = frames[0].video.course_id
    else:
        async with AsyncSessionLocal() as session:
            from app.models.db import Video

            result = await session.execute(
                select(Video.course_id).where(Video.id == video_id)
            )
            course_id = result.scalar_one_or_none()

    nodes = await _fetch_nodes(course_id) if course_id else []

    timestamp_frames = _retrieve_nearest_frames(frames, timestamp, TOP_K_FRAMES)
    similar_frames = _retrieve_similar_frames(frames, question_embedding, TOP_K_FRAMES)

    # Merge and deduplicate by frame id, keeping best rank
    seen = set()
    merged_frames = []
    for frame in timestamp_frames + similar_frames:
        if frame["id"] not in seen:
            seen.add(frame["id"])
            merged_frames.append(frame)

    similar_nodes = _retrieve_similar_nodes(nodes, question_embedding, TOP_K_NODES)

    return {
        "frames": merged_frames[: TOP_K_FRAMES * 2],
        "knowledge_nodes": similar_nodes,
        "screenshot_path": screenshot_path,
    }
