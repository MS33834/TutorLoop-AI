"""Unit tests for courses router helper functions.

Covers the pure validation/URL-building helpers in the courses router without
requiring a running database or task queue. Note: ``_build_video_url`` reads
``settings.upload_dir`` from the module globals, but ``courses`` does not import
``settings`` itself; the tests inject it via monkeypatch so the function can be
exercised in isolation.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.config import settings
from app.routers.courses import (
    _build_video_url,
    _validate_video_magic,
    _validate_video_upload,
)

# --- _validate_video_upload ---------------------------------------------


def _fake_upload_file(filename: str, content_type: str) -> SimpleNamespace:
    return SimpleNamespace(filename=filename, content_type=content_type)


def test_validate_video_upload_valid_extension_returns_ext():
    file = _fake_upload_file("lecture.mp4", "video/mp4")
    assert _validate_video_upload(file) == ".mp4"


def test_validate_video_upload_extension_is_case_insensitive():
    file = _fake_upload_file("lecture.MP4", "video/mp4")
    assert _validate_video_upload(file) == ".mp4"


def test_validate_video_upload_invalid_extension_raises_415():
    file = _fake_upload_file("notes.txt", "text/plain")
    with pytest.raises(HTTPException) as exc_info:
        _validate_video_upload(file)
    assert exc_info.value.status_code == 415


def test_validate_video_upload_valid_ext_but_bad_mime_raises_415():
    file = _fake_upload_file("lecture.mp4", "text/plain")
    with pytest.raises(HTTPException) as exc_info:
        _validate_video_upload(file)
    assert exc_info.value.status_code == 415


def test_validate_video_upload_missing_filename_raises_415():
    file = _fake_upload_file(None, "video/mp4")
    with pytest.raises(HTTPException) as exc_info:
        _validate_video_upload(file)
    assert exc_info.value.status_code == 415


# --- _validate_video_magic ----------------------------------------------


def _mp4_magic() -> bytes:
    # 16 bytes with "ftyp" at offset 4-8 (ISO base media file).
    return b"\x00\x00\x00\x20" + b"ftyp" + b"isom0000"


def test_validate_video_magic_valid_mp4_header_passes():
    # Should not raise.
    _validate_video_magic(_mp4_magic(), ".mp4")


def test_validate_video_magic_invalid_header_raises_415():
    bad = b"\x00" * 16  # no recognized magic bytes
    with pytest.raises(HTTPException) as exc_info:
        _validate_video_magic(bad, ".mp4")
    assert exc_info.value.status_code == 415


def test_validate_video_magic_too_small_raises_415():
    with pytest.raises(HTTPException) as exc_info:
        _validate_video_magic(b"\x00" * 5, ".mp4")
    assert exc_info.value.status_code == 415


def test_validate_video_magic_valid_avi_header_passes():
    header = b"RIFF" + b"\x00" * 4 + b"AVI " + b"\x00" * 4
    _validate_video_magic(header, ".avi")  # should not raise


def test_validate_video_magic_valid_webm_header_passes():
    header = b"\x1a\x45\xdf\xa3" + b"\x00" * 8
    _validate_video_magic(header, ".webm")  # should not raise


# --- _build_video_url ---------------------------------------------------


def test_build_video_url_empty_path_returns_empty():
    assert _build_video_url("") == ""


@pytest.fixture
def inject_settings(monkeypatch):
    """Make ``settings`` available in the courses module globals."""
    monkeypatch.setattr("app.routers.courses.settings", settings, raising=False)
    return settings


def test_build_video_url_temp_path_returns_empty(inject_settings, monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    # A path outside the upload directory (e.g. a temp processing file) yields "".
    assert _build_video_url(str(tmp_path / "processing.mp4")) == ""


def test_build_video_url_under_upload_dir_returns_uploads_prefix(
    inject_settings, monkeypatch, tmp_path
):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    video_file = upload_dir / "course-1" / "lecture.mp4"
    video_file.parent.mkdir(parents=True)
    video_file.write_text("dummy")

    url = _build_video_url(str(video_file))
    assert url == "/uploads/course-1/lecture.mp4"


def test_build_video_url_strips_trailing_slash_from_upload_dir(
    inject_settings, monkeypatch, tmp_path
):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir) + "/")
    video_file = upload_dir / "lecture.mp4"
    video_file.write_text("dummy")

    url = _build_video_url(str(video_file))
    assert url == "/uploads/lecture.mp4"
