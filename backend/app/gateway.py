"""Multi-key AI Gateway with weighted selection and local fallback."""

import asyncio
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import httpx

from app.config import settings


DEFAULT_QUOTA = 1_000_000
MULTIMODAL_KEYWORDS = {"vl", "vision", "multimodal", "gpt-4o", "gemini"}


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

    def select_key(self, model_type: str = "text") -> KeyInfo | None:
        healthy = self._healthy_keys(model_type)
        if not healthy:
            return None
        weights = [
            max(1.0, k.remaining_quota) / max(1.0, k.avg_rtt_ms) for k in healthy
        ]
        total = sum(weights)
        if total <= 0:
            return random.choice(healthy)
        pick = random.uniform(0, total)
        current = 0.0
        for key_info, weight in zip(healthy, weights):
            current += weight
            if pick <= current:
                return key_info
        return healthy[-1]

    def mark_degraded(self, key_info: KeyInfo):
        key_info.error_count += 1
        key_info.last_error_at = datetime.now(timezone.utc)
        if key_info.error_count >= 3:
            key_info.status = "offline"
        else:
            key_info.status = "degraded"

    def mark_healthy(self, key_info: KeyInfo):
        key_info.status = "healthy"
        key_info.error_count = 0
        key_info.last_error_at = None

    def summary(self) -> list[dict[str, Any]]:
        return [
            {
                "model": k.model,
                "status": k.status,
                "error_count": k.error_count,
                "avg_rtt_ms": k.avg_rtt_ms,
            }
            for k in self.keys
        ]


pool = KeyPool()


class GatewayError(Exception):
    pass


async def _openai_stream(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
) -> AsyncIterator[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }

    async with client.stream(
        "POST",
        url,
        headers=headers,
        json=payload,
        timeout=httpx.Timeout(120.0, connect=10.0),
    ) as response:
        if response.status_code != 200:
            text = await response.aread()
            raise GatewayError(
                f"HTTP {response.status_code}: {text.decode('utf-8', errors='replace')}"
            )

        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            content = delta.get("content")
            if content:
                yield {"type": "token", "content": content}


async def _stream_with_first_token_timeout(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    first_token_timeout: float = 3.0,
) -> AsyncIterator[dict[str, Any]]:
    gen = _openai_stream(client, base_url, api_key, model, messages)
    try:
        first = await asyncio.wait_for(gen.__anext__(), timeout=first_token_timeout)
    except StopAsyncIteration:
        return
    except asyncio.TimeoutError:
        raise GatewayError("first token timeout")
    except Exception as exc:
        raise GatewayError(str(exc))

    yield first
    async for item in gen:
        yield item


async def _try_cloud(
    client: httpx.AsyncClient,
    key_info: KeyInfo,
    messages: list[dict[str, str]],
    model_type: str,
) -> AsyncIterator[dict[str, Any]]:
    try:
        async for chunk in _stream_with_first_token_timeout(
            client,
            key_info.base_url,
            key_info.key,
            key_info.model,
            messages,
        ):
            yield chunk
        pool.mark_healthy(key_info)
    except GatewayError:
        pool.mark_degraded(key_info)
        raise


async def _try_local(
    client: httpx.AsyncClient,
    messages: list[dict[str, str]],
) -> AsyncIterator[dict[str, Any]]:
    try:
        async for chunk in _stream_with_first_token_timeout(
            client,
            settings.local_base_url,
            "local",
            settings.local_model,
            messages,
            first_token_timeout=5.0,
        ):
            yield chunk
    except GatewayError as exc:
        yield {"type": "error", "message": f"Local fallback failed: {exc}"}


async def stream_chat(
    messages: list[dict[str, str]],
    model_type: str = "text",
) -> AsyncIterator[dict[str, Any]]:
    """Yield SSE chunks; prefer cloud keys and fall back to local model."""
    async with httpx.AsyncClient() as client:
        key_info = pool.select_key(model_type)
        if key_info:
            try:
                async for chunk in _try_cloud(client, key_info, messages, model_type):
                    yield chunk
                return
            except GatewayError:
                pass

        async for chunk in _try_local(client, messages):
            yield chunk
