"""ARQ background jobs for video processing and knowledge graph extraction."""

import logging
import os

from app.db.postgres import AsyncSessionLocal
from app.models.db import Video
from app.services.kg_extractor import extract_knowledge_graph
from app.services.video_service import process_video

logger = logging.getLogger(__name__)


async def process_video_task(
    ctx: dict,
    video_id: str,
    course_id: str,
    title: str,
    temp_path: str,
) -> dict:
    """Extract frames and embeddings for a video, then mark it completed.

    The video record is created in a "processing" state before the task is
    enqueued so callers can poll its status.
    """
    try:
        await process_video(course_id, title, temp_path, video_id=video_id)
        await _update_video_status(video_id, "completed")
        logger.info("Video processing completed: %s", video_id)
        return {"video_id": video_id, "status": "completed"}
    except Exception as exc:
        logger.exception("Video processing failed for %s: %s", video_id, exc)
        await _update_video_status(video_id, "failed")
        raise
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as cleanup_exc:
                logger.warning("Could not remove temp video %s: %s", temp_path, cleanup_exc)


async def build_knowledge_graph_task(
    ctx: dict,
    course_id: str,
    video_id: str,
    transcript: str | None = None,
) -> dict:
    """Extract and persist a knowledge graph for a course video.

    Marks the video status to "kg_building" while running and "kg_ready" on
    success.  On failure the video is marked "kg_failed" and the exception is
    re-raised so ARQ can retry according to its retry policy.
    """
    await _update_video_status(video_id, "kg_building")
    try:
        graph = await extract_knowledge_graph(course_id, video_id, transcript)
        await _update_video_status(video_id, "kg_ready")
        logger.info(
            "Knowledge graph built for course=%s video=%s: %d nodes",
            course_id,
            video_id,
            len(graph.get("nodes", [])),
        )
        return graph
    except Exception as exc:
        logger.exception(
            "Knowledge graph build failed for course=%s video=%s: %s",
            course_id,
            video_id,
            exc,
        )
        await _update_video_status(video_id, "kg_failed")
        raise


async def _update_video_status(video_id: str, status: str) -> None:
    async with AsyncSessionLocal() as session:
        video = await session.get(Video, video_id)
        if video is not None:
            video.status = status
            await session.commit()
