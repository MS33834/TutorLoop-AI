"""ARQ background jobs for video processing and knowledge graph extraction."""

import logging
import os
import time
from pathlib import Path

from app.db.postgres import AsyncSessionLocal
from app.models.db import Video
from app.services.kg_extractor import extract_knowledge_graph
from app.services.video_service import process_video

logger = logging.getLogger(__name__)

# Screenshots older than this are deleted by the cleanup job.
SCREENSHOT_RETENTION_DAYS = 7
# Screenshots are written to the system temp dir with a known prefix.
SCREENSHOT_GLOBS = ("screenshot_*", "*.tmp_screenshot*")


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


async def cleanup_screenshots_task(ctx: dict) -> dict:
    """Delete screenshot temp files older than SCREENSHOT_RETENTION_DAYS.

    Screenshots are written to the OS temp directory during chat requests and
    are normally deleted immediately after use. This job is a safety net for
    cases where deletion failed (e.g. process crash), preventing unbounded
    disk growth. Runs daily via ARQ cron.
    """
    import tempfile

    tmp_dir = Path(tempfile.gettempdir())
    cutoff = time.time() - SCREENSHOT_RETENTION_DAYS * 86400
    deleted = 0
    errors = 0

    for pattern in SCREENSHOT_GLOBS:
        for path in tmp_dir.glob(pattern):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                    deleted += 1
            except Exception as exc:
                errors += 1
                logger.warning("Could not delete screenshot %s: %s", path, exc)

    logger.info("Screenshot cleanup: deleted=%d errors=%d", deleted, errors)
    return {"deleted": deleted, "errors": errors}


async def probe_keys_health_task(ctx: dict) -> dict:
    """Actively probe all AI gateway keys and update their health status.

    TechSpec §3.1 specifies a 30s heartbeat probe. This job runs that probe so
    that offline keys are detected and recovered without waiting for a real
    user request to hit them. Keys that come back online are marked healthy.
    """
    from app.gateway import pool

    results = {"probed": 0, "healthy": 0, "degraded": 0, "offline": 0}
    for key_info in pool.keys:
        results["probed"] += 1
        try:
            health = await key_info.provider.health_check()
            status = health.get("status")
            if status == "healthy":
                pool.mark_healthy(key_info, rtt_ms=0.0)
                results["healthy"] += 1
            elif status == "degraded":
                pool.mark_degraded(key_info, reason=health.get("reason", "probe degraded"))
                results["degraded"] += 1
            else:
                # offline — keep current state, mark_degraded will escalate
                pool.mark_degraded(key_info, reason=health.get("reason", "probe offline"))
                results["offline"] += 1
        except Exception as exc:
            pool.mark_degraded(key_info, reason=str(exc))
            results["offline"] += 1
            logger.warning("Key probe failed for %s: %s", key_info.masked_key(), exc)

    logger.info("Key health probe: %s", results)
    return results
