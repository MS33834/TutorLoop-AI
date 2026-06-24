"""Multimodal RAG retrieval service backed by pgvector."""

import logging

from sqlalchemy import select, text

from app.db.postgres import AsyncSessionLocal
from app.db.vector_search import search_similar_frames, search_similar_nodes
from app.models.db import CourseMaterial, Video
from app.services.embedding_service import encode_text

logger = logging.getLogger(__name__)

TOP_K_FRAMES = 4
TOP_K_NODES = 3
TOP_K_MATERIALS = 2
MAX_MATERIAL_TEXT_LENGTH = 4000


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


def _row_to_frame(row: dict) -> dict:
    """Normalise a vector_search row into the RAG frame format."""
    return {
        "id": row["id"],
        "timestamp_seconds": row["timestamp_seconds"],
        "file_path": row["file_path"],
        "caption": row.get("caption"),
        "similarity": round(1.0 - float(row.get("distance", 0.0)), 4),
    }


def _row_to_node(row: dict) -> dict:
    """Normalise a vector_search row into the RAG node format."""
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row.get("description"),
        "similarity": round(1.0 - float(row.get("distance", 0.0)), 4),
    }


async def retrieve_context(
    video_id: str,
    question: str,
    screenshot_path: str | None = None,
    timestamp: float | None = None,
) -> dict:
    """Retrieve relevant video frames, knowledge nodes and materials for a question."""
    question_embedding = encode_text(question)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Video.course_id).where(Video.id == video_id)
        )
        course_id = result.scalar_one_or_none()

    timestamp_frames = await _nearest_frames_by_timestamp(
        video_id, timestamp, TOP_K_FRAMES
    )

    # vector_search handles both the pgvector fast path and the Python
    # brute-force fallback, so RAG works whether pgvector is installed or not.
    similar_frame_rows = await search_similar_frames(
        video_id=video_id,
        query_embedding=question_embedding,
        top_k=TOP_K_FRAMES,
    )
    similar_frames = [_row_to_frame(row) for row in similar_frame_rows]

    seen = set()
    merged_frames = []
    for frame in timestamp_frames + similar_frames:
        if frame["id"] not in seen:
            seen.add(frame["id"])
            merged_frames.append(frame)

    similar_nodes = []
    if course_id:
        node_rows = await search_similar_nodes(
            course_id=course_id,
            query_embedding=question_embedding,
            top_k=TOP_K_NODES,
        )
        similar_nodes = [_row_to_node(row) for row in node_rows]

    # Retrieve relevant course materials ranked by keyword overlap with the
    # question. When CourseMaterial gains an embedding column in the future,
    # this can be switched to vector similarity without changing the API.
    materials = []
    if course_id:
        materials = await _retrieve_course_materials(course_id, question)

    return {
        "frames": merged_frames[: TOP_K_FRAMES * 2],
        "knowledge_nodes": similar_nodes,
        "screenshot_path": screenshot_path,
        "materials": materials,
    }


async def _retrieve_course_materials(course_id: str, question: str) -> list[dict]:
    """Return the most relevant extracted text snippets from course materials.

    Materials are ranked by token overlap with the question so the most
    pertinent supplementary documents are included in the context window.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CourseMaterial)
            .where(
                CourseMaterial.course_id == course_id,
                CourseMaterial.status.in_(["completed", "completed_with_warning"]),
                CourseMaterial.extracted_text.isnot(None),
            )
            .order_by(CourseMaterial.created_at.desc())
        )
        materials = list(result.scalars().all())

    scored = []
    for m in materials:
        text = (m.extracted_text or "").strip()
        if not text:
            continue
        score = _text_overlap_score(question, text)
        scored.append((score, m, text))

    scored.sort(key=lambda x: x[0], reverse=True)
    output = []
    for score, m, text in scored[:TOP_K_MATERIALS]:
        if len(text) > MAX_MATERIAL_TEXT_LENGTH:
            text = text[:MAX_MATERIAL_TEXT_LENGTH] + "…"
        output.append({
            "id": m.id,
            "title": m.title,
            "file_type": m.file_type,
            "text": text,
            "score": round(score, 4),
        })
    return output
