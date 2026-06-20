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


async def process_video(
    course_id: str, title: str, source_path: str
) -> tuple[str, list[VideoFrame]]:
    """Save video metadata, extract frames, and persist frame records.

    Returns (video_id, list of VideoFrame ORM objects).
    """
    video_id = str(uuid.uuid4())
    target_dir = _frames_dir(video_id)
    _ensure_dir(target_dir)

    source_path_obj = Path(source_path)
    ext = source_path_obj.suffix or ".mp4"
    target_video = Path(settings.upload_dir) / "videos" / f"{video_id}{ext}"
    _ensure_dir(target_video.parent)
    os.replace(source_path, str(target_video))

    raw_frames, duration = extract_frames(str(target_video))

    db_frames = []
    for item in raw_frames:
        timestamp = item["timestamp_seconds"]
        filename = f"{int(timestamp * 1000)}.jpg"
        file_path = str(target_dir / filename)
        cv2.imwrite(file_path, item["frame"])

        caption = f"Frame at {timestamp}s"
        frame = VideoFrame(
            video_id=video_id,
            timestamp_seconds=timestamp,
            file_path=file_path,
            caption=caption,
            embedding=encode_text(caption),
        )
        db_frames.append(frame)

    video = Video(
        id=video_id,
        course_id=course_id,
        title=title,
        file_path=str(target_video),
        duration_seconds=duration,
    )

    async with AsyncSessionLocal() as session:
        session.add(video)
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
