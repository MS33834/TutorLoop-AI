"""Multi-key AI Gateway with weighted selection and local fallback.

This module now delegates actual HTTP streaming to the pluggable providers
in app.services.model_providers, while retaining multi-key health tracking
and weighted key selection.
"""

import asyncio
import logging
import random
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.services.model_providers import (
    ModelProvider,
    ProviderError,
    RateLimitError,
    create_provider,
)

logger = logging.getLogger(__name__)

DEFAULT_QUOTA = 1_000_000
MULTIMODAL_KEYWORDS = {"vl", "vision", "multimodal", "gpt-4o", "gemini"}
RTT_EWMA_ALPHA = 0.3


@dataclass
class KeyInfo:
    key: str
    base_url: str
    model: str
    status: str = "healthy"  # healthy / degraded / offline
    error_count: int = 0
    last_error_at: datetime | None = None
    avg_rtt_ms: float = 100.0
    remaining_quota: int = DEFAULT_QUOTA
    provider: ModelProvider = field(init=False)

    def __post_init__(self):
        self.provider = create_provider(
            "openai_compatible",
            base_url=self.base_url,
            api_key=self.key,
        )

    def masked_key(self) -> str:
        if len(self.key) <= 8:
            return "***"
        return f"{self.key[:4]}...{self.key[-4:]}"


class KeyPool:
    def __init__(self, configs: list[dict[str, Any]] | None = None):
        configs = configs or settings.llm_key_configs
        self.keys: list[KeyInfo] = [
            KeyInfo(key=c["key"], base_url=c["base_url"], model=c["model"])
            for c in configs
        ]

    def _is_text_model(self, model: str) -> bool:
        lowered = model.lower()
        return not any(kw in lowered for kw in MULTIMODAL_KEYWORDS)

    def _healthy_keys(self, model_type: str = "text") -> list[KeyInfo]:
        candidates = [k for k in self.keys if k.status != "offline"]
        if model_type == "text":
            text_keys = [k for k in candidates if self._is_text_model(k.model)]
            if text_keys:
                return text_keys
        else:
            multi_keys = [k for k in candidates if not self._is_text_model(k.model)]
            if multi_keys:
                return multi_keys
        return candidates

    def _success_rate(self, key_info: KeyInfo) -> float:
        """Return a smoothed success rate based on recent error count."""
        return 1.0 / (1.0 + key_info.error_count)

    def select_key(self, model_type: str = "text", exclude: set[int] | None = None) -> KeyInfo | None:
        """Select a key using weighted random selection.

        Weight = (remaining_quota / avg_rtt_ms) * success_rate^2.
        Quota favours keys with more budget, RTT favours fast keys, and the
        squared success rate aggressively penalises recently failing keys.
        """
        exclude = exclude or set()
        healthy = [k for k in self._healthy_keys(model_type) if id(k) not in exclude]
        if not healthy:
            return None
        weights = []
        for k in healthy:
            quota_factor = max(1.0, k.remaining_quota)
            rtt_factor = max(1.0, k.avg_rtt_ms)
            success_factor = self._success_rate(k) ** 2
            weights.append(quota_factor / rtt_factor * success_factor)

        total = sum(weights)
        if total <= 0:
            return random.choice(healthy)
        pick = random.uniform(0, total)
        current = 0.0
        for key_info, weight in zip(healthy, weights, strict=False):
            current += weight
            if pick <= current:
                return key_info
        return healthy[-1]

    def mark_degraded(self, key_info: KeyInfo, reason: str = ""):
        key_info.error_count += 1
        key_info.last_error_at = datetime.now(UTC)
        if key_info.error_count >= 3:
            key_info.status = "offline"
            logger.warning(
                "Key %s marked offline (%s)", key_info.masked_key(), reason or "errors"
            )
        else:
            key_info.status = "degraded"
            logger.warning(
                "Key %s marked degraded (%s)", key_info.masked_key(), reason or "errors"
            )

    def mark_healthy(self, key_info: KeyInfo, rtt_ms: float | None = None):
        key_info.status = "healthy"
        key_info.error_count = 0
        key_info.last_error_at = None
        if rtt_ms is not None and rtt_ms > 0:
            key_info.avg_rtt_ms = (
                RTT_EWMA_ALPHA * rtt_ms + (1 - RTT_EWMA_ALPHA) * key_info.avg_rtt_ms
            )

    async def probe_keys(self) -> None:
        """Run lightweight health checks on all keys and update their status."""
        for key_info in self.keys:
            start = time.perf_counter()
            try:
                health = await key_info.provider.health_check()
                rtt_ms = (time.perf_counter() - start) * 1000
                if health.get("status") == "healthy":
                    self.mark_healthy(key_info, rtt_ms=rtt_ms)
                else:
                    self.mark_degraded(
                        key_info, reason=health.get("reason", "unhealthy probe")
                    )
            except Exception as exc:
                self.mark_degraded(key_info, reason=str(exc))

    def summary(self) -> list[dict[str, Any]]:
        return [
            {
                "model": k.model,
                "status": k.status,
                "error_count": k.error_count,
                "avg_rtt_ms": round(k.avg_rtt_ms, 2),
            }
            for k in self.keys
        ]

    async def close_all(self) -> None:
        """Close shared HTTP clients on all keys to release connections."""
        for k in self.keys:
            aclose = getattr(k.provider, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception as exc:
                    logger.warning("Error closing provider client: %s", exc)


pool = KeyPool()


# Reusable local fallback provider so we don't create a new httpx client on
# every fallback attempt. Lazily initialised on first use.
_local_provider: ModelProvider | None = None


def _get_local_provider() -> ModelProvider:
    """Return a shared local fallback provider, creating it on first use."""
    global _local_provider
    if _local_provider is None:
        _local_provider = create_provider(
            "openai_compatible",
            base_url=settings.local_base_url,
            api_key="local",
        )
    return _local_provider


async def close_local_provider() -> None:
    """Close the shared local fallback provider's HTTP client."""
    global _local_provider
    if _local_provider is not None:
        aclose = getattr(_local_provider, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception as exc:
                logger.warning("Error closing local provider client: %s", exc)
        _local_provider = None


class GatewayError(Exception):
    pass


def _is_retryable(exc: BaseException | None) -> bool:
    """Return True if the exception warrants trying another cloud key."""
    if exc is None:
        return False
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, ProviderError):
        status = getattr(exc, "status_code", None)
        if status in {429, 502, 503, 504, None}:
            return True
    return False


async def _stream_with_first_token_timeout(
    provider: ModelProvider,
    model: str,
    messages: list[dict[str, Any]],
    first_token_timeout: float = 3.0,
) -> AsyncIterator[dict[str, Any]]:
    gen = provider.stream_chat(messages=messages, model=model)
    try:
        first = await asyncio.wait_for(gen.__anext__(), timeout=first_token_timeout)
    except StopAsyncIteration:
        return
    except TimeoutError as exc:
        raise GatewayError("first token timeout") from exc
    except ProviderError as exc:
        raise GatewayError(str(exc)) from exc
    except Exception as exc:
        raise GatewayError(str(exc)) from exc

    yield {"type": "token", "content": first}
    async for chunk in gen:
        yield {"type": "token", "content": chunk}


async def _try_cloud(
    key_info: KeyInfo,
    messages: list[dict[str, Any]],
    model_type: str,
) -> AsyncIterator[dict[str, Any]]:
    try:
        async for chunk in _stream_with_first_token_timeout(
            key_info.provider,
            key_info.model,
            messages,
        ):
            yield chunk
        pool.mark_healthy(key_info)
    except GatewayError as exc:
        pool.mark_degraded(key_info, reason=str(exc))
        raise


async def _try_local(
    messages: list[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    provider = _get_local_provider()
    try:
        async for chunk in _stream_with_first_token_timeout(
            provider,
            settings.local_model,
            messages,
            first_token_timeout=5.0,
        ):
            yield chunk
    except GatewayError as exc:
        logger.warning("Local fallback failed: %s", exc)
        yield {"type": "error", "message": f"Local fallback failed: {exc}"}


async def stream_chat(
    messages: list[dict[str, Any]],
    model_type: str = "text",
) -> AsyncIterator[dict[str, Any]]:
    """Yield SSE chunks; prefer cloud keys and fall back to local model."""
    excluded: set[int] = set()
    for _ in range(max(1, len(pool.keys))):
        key_info = pool.select_key(model_type, exclude=excluded)
        if not key_info:
            break
        excluded.add(id(key_info))
        try:
            async for chunk in _try_cloud(key_info, messages, model_type):
                yield chunk
            return
        except GatewayError as exc:
            if _is_retryable(exc.__cause__):
                logger.warning("Retrying stream_chat after key failure: %s", exc)
                continue
            logger.warning("Non-retryable stream_chat failure: %s", exc)
            break

    async for chunk in _try_local(messages):
        yield chunk


async def chat_completion(
    messages: list[dict[str, Any]],
    model_type: str = "text",
) -> dict[str, Any]:
    """Non-streaming chat completion; used by VLM/KG services.

    Tries each healthy cloud key in turn, then falls back to the local model.
    RTT is tracked on both success and error paths so degraded keys get
    accurate latency signals.
    """
    last_error: Exception | None = None
    excluded: set[int] = set()

    for _ in range(max(1, len(pool.keys))):
        key_info = pool.select_key(model_type, exclude=excluded)
        if not key_info:
            break
        excluded.add(id(key_info))

        start = time.perf_counter()
        try:
            response = await key_info.provider.chat_completion(
                messages=messages,
                model=key_info.model,
            )
            pool.mark_healthy(key_info, rtt_ms=(time.perf_counter() - start) * 1000)
            return response
        except Exception as exc:
            # Track RTT even on failure so the weighted selector has accurate
            # latency data for degraded keys.
            elapsed_ms = (time.perf_counter() - start) * 1000
            pool.mark_degraded(key_info, reason=str(exc))
            # mark_degraded resets error_count tracking but doesn't update RTT;
            # update avg_rtt_ms directly for degraded keys.
            if elapsed_ms > 0:
                key_info.avg_rtt_ms = (
                    RTT_EWMA_ALPHA * elapsed_ms
                    + (1 - RTT_EWMA_ALPHA) * key_info.avg_rtt_ms
                )
            last_error = exc
            logger.warning(
                "Cloud chat completion failed for key %s (rtt=%.0fms): %s",
                key_info.masked_key(),
                elapsed_ms,
                exc,
            )
            if _is_retryable(exc):
                continue
            break

    # Local fallback using the shared provider (connection reuse).
    logger.warning("All cloud keys failed; falling back to local model. Last error: %s", last_error)
    provider = _get_local_provider()
    return await provider.chat_completion(
        messages=messages,
        model=settings.local_model,
    )


# Background health-probe task. Started in app.main on application startup and
# cancelled on shutdown so the gateway can recover degraded/offline keys
# without waiting for a user request.
_health_probe_task: asyncio.Task | None = None


async def _health_probe_loop(interval_seconds: float = 60.0) -> None:
    """Periodically probe all keys and refresh their health status."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await pool.probe_keys()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Health probe loop error: %s", exc)


def start_health_probe(interval_seconds: float = 60.0) -> None:
    """Start the periodic key health probe (idempotent)."""
    global _health_probe_task
    if _health_probe_task is not None and not _health_probe_task.done():
        return
    _health_probe_task = asyncio.create_task(_health_probe_loop(interval_seconds))


def stop_health_probe() -> None:
    """Cancel the periodic key health probe."""
    global _health_probe_task
    if _health_probe_task is not None and not _health_probe_task.done():
        _health_probe_task.cancel()
