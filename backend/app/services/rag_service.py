"""Multimodal RAG retrieval service backed by pgvector."""

import base64
import logging
from pathlib import Path

from sqlalchemy import select, text

from app.config import settings
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


async def _describe_screenshot(screenshot_path: str) -> str | None:
    """Use the VLM to describe a screenshot, returning None on failure.

    The description is used as a richer query for vector retrieval so that
    visual context (formulas, diagrams, UI state, error messages) is captured
    even when the text question alone is ambiguous. Any failure (missing file,
    VLM unavailable, parse error) returns None so callers can degrade to the
    timestamp-based frame fallback.
    """
    try:
        data = Path(screenshot_path).read_bytes()
    except Exception as exc:
        logger.warning("Could not read screenshot %s: %s", screenshot_path, exc)
        return None

    b64 = base64.b64encode(data).decode("utf-8")
    # Screenshots are PNGs from the browser; fall back to JPEG if the extension
    # is unusual — the data URL mime only affects provider-side sniffing at most.
    image_block = {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{b64}"},
    }
    prompt = (
        "请用 1-3 句话客观描述这张学习截图中的内容，包括可见的文字、公式、"
        "图表、代码或界面元素。只输出描述文本，不要输出 JSON 或格式标记。"
    )
    messages = [
        {"role": "user", "content": [{"type": "text", "text": prompt}, image_block]}
    ]

    try:
        # Reuse the shared VLM provider singleton from kg_extractor so we don't
        # spin up a second HTTP client pool. Falls back to the gateway when the
        # dedicated VLM endpoint isn't configured.
        if settings.vlm_base_url and settings.vlm_api_key:
            from app.services.kg_extractor import _get_vlm_provider

            provider = _get_vlm_provider()
            response = await provider.chat_completion(
                messages=messages,
                model=settings.vlm_model,
                temperature=0.2,
                max_tokens=256,
            )
        else:
            from app.gateway import chat_completion

            response = await chat_completion(messages=messages, model_type="vision")
        return response["choices"][0]["message"].get("content", "").strip() or None
    except Exception as exc:
        logger.warning("VLM screenshot description failed: %s", exc)
        return None


async def retrieve_context(
    video_id: str,
    question: str,
    screenshot_path: str | None = None,
    timestamp: float | None = None,
) -> dict:
    """Retrieve relevant video frames, knowledge nodes and materials for a question."""
    # When a screenshot is attached, describe it with the VLM and fold that
    # description into the retrieval query. Visual context (formulas, diagrams,
    # error output) often disambiguates an otherwise vague text question. If the
    # VLM call fails we transparently fall back to the text-only query, and the
    # timestamp-based frame retrieval below provides a final safety net.
    screenshot_description: str | None = None
    if screenshot_path:
        screenshot_description = await _describe_screenshot(screenshot_path)

    query_text = question
    if screenshot_description:
        query_text = f"{question}\n{screenshot_description}"
    question_embedding = encode_text(query_text)

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

    NOTE: this stays a keyword-overlap ranking (not vector similarity) because
    the CourseMaterial table has no embedding column yet. The screenshot
    description is intentionally not folded in here — material text is long-form
    document content, so n-gram overlap on the original question is a better
    signal than mixing in a short image caption.
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
