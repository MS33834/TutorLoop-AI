"""Video frame extraction and persistence service."""

import logging
import os
import uuid
from pathlib import Path

import cv2
from sqlalchemy import func, select

from app.config import settings
from app.db.postgres import AsyncSessionLocal
from app.models.db import Video, VideoFrame
from app.services.embedding_service import encode_text

logger = logging.getLogger(__name__)


def _frames_dir(video_id: str) -> Path:
    return Path(settings.upload_dir) / "frames" / video_id


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def extract_frames(
    video_path: str, interval_seconds: int | None = None
) -> tuple[list[dict], float]:
    """Extract JPG frames from a video at fixed intervals.

    Returns (list of dicts with timestamp_seconds and frame image, video duration).

    .. note::
        For memory efficiency prefer :func:`extract_and_save_frames` which writes
        each frame to disk immediately instead of accumulating them in memory.
    """
    interval = interval_seconds or settings.frame_interval_seconds
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error("Cannot open video: %s", video_path)
        return [], 0.0

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0.0

    frames = []
    frame_interval = int(fps * interval)
    frame_index = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_index % frame_interval == 0:
            timestamp_seconds = round(frame_index / fps, 2)
            frames.append({"timestamp_seconds": timestamp_seconds, "frame": frame})

        frame_index += 1

    cap.release()

    # Sort by timestamp so directory listing is deterministic
    frames.sort(key=lambda x: x["timestamp_seconds"])
    return frames, duration


def extract_and_save_frames(
    video_path: str,
    target_dir: Path,
    interval_seconds: int | None = None,
) -> tuple[list[dict], float]:
    """Extract frames and write each to disk immediately.

    Unlike :func:`extract_frames`, this holds at most one decoded frame in
    memory at a time, avoiding OOM on long videos. Returns a list of dicts
    with ``timestamp_seconds`` and ``file_path`` keys, plus the video duration.
    """
    interval = interval_seconds or settings.frame_interval_seconds
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error("Cannot open video: %s", video_path)
        return [], 0.0

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0.0

    frame_interval = max(1, int(fps * interval))
    saved: list[dict] = []
    frame_index = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_index % frame_interval == 0:
                timestamp_seconds = round(frame_index / fps, 2)
                filename = f"{int(timestamp_seconds * 1000)}.jpg"
                file_path = str(target_dir / filename)
                if cv2.imwrite(file_path, frame):
                    saved.append(
                        {"timestamp_seconds": timestamp_seconds, "file_path": file_path}
                    )
                else:
                    logger.warning("Failed to write frame to %s; skipping", file_path)

            frame_index += 1
    finally:
        cap.release()

    saved.sort(key=lambda x: x["timestamp_seconds"])
    return saved, duration


async def process_video(
    course_id: str, title: str, source_path: str, video_id: str | None = None
) -> tuple[str, list[VideoFrame]]:
    """Save video metadata, extract frames, and persist frame records.

    Args:
        course_id: The course this video belongs to.
        title: Display title for the video.
        source_path: Temporary path to the uploaded video file.
        video_id: Optional pre-generated video ID (used by background tasks).

    Returns:
        Tuple of (video_id, list of VideoFrame ORM objects).
    """
    video_id = video_id or str(uuid.uuid4())
    target_dir = _frames_dir(video_id)
    _ensure_dir(target_dir)

    source_path_obj = Path(source_path)
    ext = source_path_obj.suffix or ".mp4"
    target_video = Path(settings.upload_dir) / "videos" / f"{video_id}{ext}"
    _ensure_dir(target_video.parent)
    os.replace(source_path, str(target_video))

    raw_frames, duration = extract_and_save_frames(str(target_video), target_dir)

    db_frames = []
    for item in raw_frames:
        timestamp = item["timestamp_seconds"]
        file_path = item["file_path"]

        # Use a meaningful placeholder caption that includes the video title
        # and timestamp. This is overwritten by VLM-generated captions during
        # knowledge graph extraction, but until then it provides enough
        # textual signal for embedding-based retrieval to work reasonably.
        caption = f"{title} - {timestamp}s"
        frame = VideoFrame(
            video_id=video_id,
            timestamp_seconds=timestamp,
            file_path=file_path,
            caption=caption,
            embedding=encode_text(caption),
        )
        db_frames.append(frame)

    async with AsyncSessionLocal() as session:
        video = await session.get(Video, video_id)
        if video is None:
            video = Video(
                id=video_id,
                course_id=course_id,
                title=title,
                file_path=str(target_video),
                duration_seconds=duration,
                status="completed",
            )
            session.add(video)
        else:
            video.title = title
            video.file_path = str(target_video)
            video.duration_seconds = duration
            video.status = "completed"

        for frame in db_frames:
            session.add(frame)
        await session.commit()

    logger.info(
        "Processed video %s: %d frames, %.2f seconds", video_id, len(db_frames), duration
    )
    return video_id, db_frames


async def get_frame_path(video_id: str, timestamp_seconds: float) -> str | None:
    """Return the frame file path nearest to the requested timestamp."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(VideoFrame)
            .where(VideoFrame.video_id == video_id)
            .order_by(func.abs(VideoFrame.timestamp_seconds - timestamp_seconds))
            .limit(1)
        )
        frame = result.scalar_one_or_none()
        return frame.file_path if frame else None
