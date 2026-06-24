"""Unit tests for AI gateway KeyPool logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.gateway import KeyPool, _is_retryable
from app.services.model_providers import (
    AuthenticationError,
    InsufficientBalanceError,
    ProviderError,
    RateLimitError,
)


def _make_key_info(key="sk-test", base_url="http://localhost:8000/v1", model="gpt-4"):
    """Create a KeyInfo with a mocked provider to avoid real HTTP."""
    with patch("app.gateway.create_provider") as mock_create:
        mock_provider = MagicMock()
        mock_provider.aclose = AsyncMock()
        mock_create.return_value = mock_provider
        from app.gateway import KeyInfo

        return KeyInfo(key=key, base_url=base_url, model=model)


def test_keypool_select_returns_healthy_key():
    pool = KeyPool(
        configs=[{"key": "sk-1", "base_url": "http://a", "model": "text-model"}]
    )
    key = pool.select_key("text")
    assert key is not None
    assert key.key == "sk-1"


def test_keypool_select_excludes_offline_keys():
    pool = KeyPool(
        configs=[
            {"key": "sk-1", "base_url": "http://a", "model": "text-model"},
            {"key": "sk-2", "base_url": "http://b", "model": "text-model"},
        ]
    )
    pool.keys[0].status = "offline"
    key = pool.select_key("text")
    assert key is not None
    assert key.key == "sk-2"


def test_keypool_select_returns_none_when_all_offline():
    pool = KeyPool(
        configs=[{"key": "sk-1", "base_url": "http://a", "model": "text-model"}]
    )
    pool.keys[0].status = "offline"
    assert pool.select_key("text") is None


def test_keypool_mark_degraded_increments_error_count():
    pool = KeyPool(
        configs=[{"key": "sk-1", "base_url": "http://a", "model": "text-model"}]
    )
    key = pool.keys[0]
    pool.mark_degraded(key, reason="timeout")
    assert key.status == "degraded"
    assert key.error_count == 1


def test_keypool_mark_degraded_offline_after_three_errors():
    pool = KeyPool(
        configs=[{"key": "sk-1", "base_url": "http://a", "model": "text-model"}]
    )
    key = pool.keys[0]
    pool.mark_degraded(key)
    pool.mark_degraded(key)
    pool.mark_degraded(key)
    assert key.status == "offline"
    assert key.error_count == 3


def test_keypool_mark_healthy_resets_errors():
    pool = KeyPool(
        configs=[{"key": "sk-1", "base_url": "http://a", "model": "text-model"}]
    )
    key = pool.keys[0]
    pool.mark_degraded(key)
    pool.mark_degraded(key)
    assert key.error_count == 2
    pool.mark_healthy(key, rtt_ms=50.0)
    assert key.status == "healthy"
    assert key.error_count == 0
    assert key.last_error_at is None
    # RTT should be updated via EWMA
    assert key.avg_rtt_ms != 100.0


def test_keypool_summary_returns_all_keys():
    pool = KeyPool(
        configs=[
            {"key": "sk-1", "base_url": "http://a", "model": "model-a"},
            {"key": "sk-2", "base_url": "http://b", "model": "model-b"},
        ]
    )
    summary = pool.summary()
    assert len(summary) == 2
    assert summary[0]["model"] == "model-a"
    assert "status" in summary[0]
    assert "avg_rtt_ms" in summary[0]


@pytest.mark.asyncio
async def test_keypool_close_all_closes_providers():
    """close_all should call aclose on every key's provider."""
    pool = KeyPool(
        configs=[
            {"key": "sk-1", "base_url": "http://a", "model": "text-model"},
            {"key": "sk-2", "base_url": "http://b", "model": "text-model"},
        ]
    )
    # Replace providers with mocks that have aclose
    for k in pool.keys:
        k.provider = MagicMock()
        k.provider.aclose = AsyncMock()

    await pool.close_all()

    for k in pool.keys:
        k.provider.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_keypool_close_all_swallows_errors():
    """close_all should not raise even if a provider's aclose fails."""
    pool = KeyPool(
        configs=[{"key": "sk-1", "base_url": "http://a", "model": "text-model"}]
    )
    pool.keys[0].provider = MagicMock()
    pool.keys[0].provider.aclose = AsyncMock(side_effect=RuntimeError("boom"))

    # Should not raise
    await pool.close_all()


def test_is_retryable_rate_limit():
    exc = RateLimitError()
    assert _is_retryable(exc) is True


def test_is_retryable_provider_error_503():
    exc = ProviderError("server error", status_code=503)
    assert _is_retryable(exc) is True


def test_is_retryable_provider_error_none_status():
    exc = ProviderError("connection failed", status_code=None)
    assert _is_retryable(exc) is True


def test_is_retryable_auth_error():
    exc = AuthenticationError()
    assert _is_retryable(exc) is False


def test_is_retryable_balance_error():
    exc = InsufficientBalanceError()
    assert _is_retryable(exc) is False


def test_is_retryable_none():
    assert _is_retryable(None) is False


def test_is_retryable_generic_exception():
    assert _is_retryable(ValueError("oops")) is False
