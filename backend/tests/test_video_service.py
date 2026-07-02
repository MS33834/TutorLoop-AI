"""Unit tests for video frame extraction."""

import os

import cv2
import numpy as np
import pytest

from app.services.video_service import extract_and_save_frames


@pytest.fixture
def sample_video(tmp_path):
    """Create a short test video with known frame count using cv2."""
    video_path = str(tmp_path / "test_video.mp4")
    fps = 10
    width, height = 64, 48
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(video_path, fourcc, fps, (width, height))
    # Write 30 frames = 3 seconds at 10 fps
    for i in range(30):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = (i * 8, 0, 0)  # varying blue intensity
        writer.write(frame)
    writer.release()
    assert os.path.exists(video_path)
    return video_path


def test_extract_and_save_frames_writes_files(sample_video, tmp_path):
    """extract_and_save_frames should write JPG files to disk."""
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    saved, duration = extract_and_save_frames(
        sample_video, frames_dir, interval_seconds=1
    )
    assert len(saved) >= 2
    assert duration > 0
    # Each saved entry should have a file_path that exists on disk
    for item in saved:
        assert "timestamp_seconds" in item
        assert "file_path" in item
        assert os.path.exists(item["file_path"])
    # Files should be JPG
    for item in saved:
        assert item["file_path"].endswith(".jpg")


def test_extract_and_save_frames_invalid_path(tmp_path):
    """Non-existent video should return empty list and zero duration."""
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    saved, duration = extract_and_save_frames(
        str(tmp_path / "nonexistent.mp4"), frames_dir
    )
    assert saved == []
    assert duration == 0.0


def test_extract_and_save_frames_sorted_by_timestamp(sample_video, tmp_path):
    """Saved frames should be sorted by timestamp."""
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    saved, _ = extract_and_save_frames(
        sample_video, frames_dir, interval_seconds=1
    )
    timestamps = [item["timestamp_seconds"] for item in saved]
    assert timestamps == sorted(timestamps)
