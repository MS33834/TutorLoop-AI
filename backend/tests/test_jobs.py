"""Unit tests for ARQ background jobs (screenshot cleanup, key heartbeat).

These tests don't require a running Redis or database — they exercise the
pure logic of the cleanup and probe tasks with mocked filesystem / gateway.
"""

import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.jobs import (
    SCREENSHOT_RETENTION_DAYS,
    cleanup_screenshots_task,
    probe_keys_health_task,
)

# ---------------------------------------------------------------------------
# cleanup_screenshots_task
# ---------------------------------------------------------------------------


def _make_old_file(tmp_path: Path, name: str, age_days: float) -> Path:
    """Create a file in tmp_path and backdate its mtime by age_days."""
    f = tmp_path / name
    f.write_bytes(b"fake-screenshot")
    old_mtime = time.time() - age_days * 86400
    os.utime(f, (old_mtime, old_mtime))
    return f


@pytest.mark.asyncio
async def test_cleanup_deletes_old_screenshots(tmp_path):
    """Files older than the retention window are deleted."""
    _make_old_file(tmp_path, "screenshot_old.png", age_days=SCREENSHOT_RETENTION_DAYS + 1)
    _make_old_file(tmp_path, "screenshot_old2.tmp_screenshot", age_days=SCREENSHOT_RETENTION_DAYS + 5)

    with patch("tempfile.gettempdir", return_value=str(tmp_path)):
        result = await cleanup_screenshots_task({})

    assert result["deleted"] == 2
    assert result["errors"] == 0
    assert not (tmp_path / "screenshot_old.png").exists()
    assert not (tmp_path / "screenshot_old2.tmp_screenshot").exists()


@pytest.mark.asyncio
async def test_cleanup_preserves_recent_screenshots(tmp_path):
    """Files within the retention window are NOT deleted."""
    _make_old_file(tmp_path, "screenshot_recent.png", age_days=1)
    _make_old_file(tmp_path, "screenshot_fresh.tmp_screenshot", age_days=0)

    with patch("tempfile.gettempdir", return_value=str(tmp_path)):
        result = await cleanup_screenshots_task({})

    assert result["deleted"] == 0
    assert (tmp_path / "screenshot_recent.png").exists()
    assert (tmp_path / "screenshot_fresh.tmp_screenshot").exists()


@pytest.mark.asyncio
async def test_cleanup_ignores_non_screenshot_files(tmp_path):
    """Files not matching the screenshot globs are left alone, even if old."""
    _make_old_file(tmp_path, "unrelated_old_file.txt", age_days=SCREENSHOT_RETENTION_DAYS + 10)
    _make_old_file(tmp_path, "screenshot_old.png", age_days=SCREENSHOT_RETENTION_DAYS + 1)

    with patch("tempfile.gettempdir", return_value=str(tmp_path)):
        result = await cleanup_screenshots_task({})

    assert result["deleted"] == 1
    assert (tmp_path / "unrelated_old_file.txt").exists()
    assert not (tmp_path / "screenshot_old.png").exists()


@pytest.mark.asyncio
async def test_cleanup_returns_zero_when_no_files(tmp_path):
    """An empty temp dir yields deleted=0."""
    with patch("tempfile.gettempdir", return_value=str(tmp_path)):
        result = await cleanup_screenshots_task({})

    assert result["deleted"] == 0
    assert result["errors"] == 0


@pytest.mark.asyncio
async def test_cleanup_skips_directories(tmp_path):
    """Directories matching the glob are skipped (only files are deleted)."""
    # Create a directory matching the screenshot glob pattern.
    d = tmp_path / "screenshot_dir"
    d.mkdir()
    old_mtime = time.time() - (SCREENSHOT_RETENTION_DAYS + 1) * 86400
    os.utime(d, (old_mtime, old_mtime))

    with patch("tempfile.gettempdir", return_value=str(tmp_path)):
        result = await cleanup_screenshots_task({})

    assert result["deleted"] == 0
    assert d.exists()  # directory preserved


# ---------------------------------------------------------------------------
# probe_keys_health_task
# ---------------------------------------------------------------------------


def _make_key_info(status="healthy", health_status="healthy", health_reason=""):
    """Build a mock KeyInfo with a stubbed provider.health_check."""
    key_info = MagicMock()
    key_info.status = status
    key_info.masked_key.return_value = "sk-t...st"

    key_info.provider = MagicMock()
    key_info.provider.health_check = AsyncMock(
        return_value={"status": health_status, "reason": health_reason}
    )
    return key_info


@pytest.mark.asyncio
async def test_probe_marks_healthy_key_as_healthy():
    """A key whose probe returns 'healthy' is marked healthy."""
    k = _make_key_info(status="degraded", health_status="healthy")
    mock_pool = MagicMock()
    mock_pool.keys = [k]

    with patch("app.gateway.pool", mock_pool):
        result = await probe_keys_health_task({})

    assert result["probed"] == 1
    assert result["healthy"] == 1
    mock_pool.mark_healthy.assert_called_once_with(k, rtt_ms=0.0)


@pytest.mark.asyncio
async def test_probe_marks_degraded_key_as_degraded():
    """A key whose probe returns 'degraded' is marked degraded."""
    k = _make_key_info(status="healthy", health_status="degraded", health_reason="rate limited")
    mock_pool = MagicMock()
    mock_pool.keys = [k]

    with patch("app.gateway.pool", mock_pool):
        result = await probe_keys_health_task({})

    assert result["degraded"] == 1
    mock_pool.mark_degraded.assert_called_once_with(k, reason="rate limited")


@pytest.mark.asyncio
async def test_probe_marks_offline_key_as_degraded():
    """A key whose probe returns 'offline' is escalated via mark_degraded."""
    k = _make_key_info(status="healthy", health_status="offline", health_reason="timeout")
    mock_pool = MagicMock()
    mock_pool.keys = [k]

    with patch("app.gateway.pool", mock_pool):
        result = await probe_keys_health_task({})

    assert result["offline"] == 1
    mock_pool.mark_degraded.assert_called_once_with(k, reason="timeout")


@pytest.mark.asyncio
async def test_probe_handles_provider_exception():
    """If health_check raises, the key is marked degraded and counted offline."""
    k = _make_key_info(status="healthy")
    k.provider.health_check = AsyncMock(side_effect=RuntimeError("boom"))
    mock_pool = MagicMock()
    mock_pool.keys = [k]

    with patch("app.gateway.pool", mock_pool):
        result = await probe_keys_health_task({})

    assert result["offline"] == 1
    mock_pool.mark_degraded.assert_called_once()
    args, kwargs = mock_pool.mark_degraded.call_args
    assert "boom" in kwargs.get("reason", "")


@pytest.mark.asyncio
async def test_probe_aggregates_multiple_keys():
    """Probe results are aggregated across multiple keys."""
    k1 = _make_key_info(health_status="healthy")
    k2 = _make_key_info(health_status="degraded", health_reason="slow")
    k3 = _make_key_info(health_status="offline", health_reason="down")
    mock_pool = MagicMock()
    mock_pool.keys = [k1, k2, k3]

    with patch("app.gateway.pool", mock_pool):
        result = await probe_keys_health_task({})

    assert result["probed"] == 3
    assert result["healthy"] == 1
    assert result["degraded"] == 1
    assert result["offline"] == 1
