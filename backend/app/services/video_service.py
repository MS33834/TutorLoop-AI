"""Video frame extraction and persistence service."""

import logging
import shutil
import uuid
from pathlib import Path

import cv2
from sqlalchemy import select

from app.config import settings
from app.db.postgres import AsyncSessionLocal
from app.models.db import Video, VideoFrame
from app.services.embedding_service import encode_text

logger = logging.getLogger(__name__)


def _frames_dir(video_id: str) -> Path:
    return Path(settings.upload_dir) / "frames" / video_id


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def extract_and_save_frames(
    video_path: str,
    target_dir: Path,
    interval_seconds: int | None = None,
) -> tuple[list[dict], float]:
    """Extract frames and write each to disk immediately.

    Holds at most one decoded frame in memory at a time, avoiding OOM on long
    videos. Returns a list of dicts with ``timestamp_seconds`` and
    ``file_path`` keys, plus the video duration.
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
    # shutil.move works across filesystems (falling back to copy+delete),
    # unlike os.replace which fails with EXDEV when the temp upload and the
    # upload dir live on different mounts.
    shutil.move(source_path, str(target_video))

    raw_frames, duration = extract_and_save_frames(str(target_video), target_dir)

    db_frames = []
    for item in raw_frames:
        timestamp = item["timestamp_seconds"]
        file_path = item["file_path"]

        # Placeholder caption used until VLM captions are generated during KG
        # extraction. Includes the video title, timestamp and a short
        # descriptor so embedding-based retrieval has meaningful text to work
        # with. The "[placeholder]" prefix lets RAG/recommendation detect and
        # downgrade these captions when real VLM captions are available.
        caption = f"[placeholder] {title} 视频关键帧（{timestamp}秒）"
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
