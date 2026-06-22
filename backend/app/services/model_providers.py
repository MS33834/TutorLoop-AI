"""Pluggable LLM/VLM provider interface and registry."""

import base64
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Base exception for provider failures."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(ProviderError):
    """Raised when the provider returns a rate-limit response."""

    def __init__(self, message: str = "rate limit"):
        super().__init__(message, status_code=429)


class AuthenticationError(ProviderError):
    """Raised when the API key is rejected."""

    def __init__(self, message: str = "authentication failed"):
        super().__init__(message, status_code=401)


class InsufficientBalanceError(ProviderError):
    """Raised when the account has insufficient quota/balance."""

    def __init__(self, message: str = "insufficient balance"):
        super().__init__(message, status_code=402)


def _image_to_data_url(path: str) -> str | None:
    """Convert an image file path to a base64 data URL."""
    try:
        data = Path(path).read_bytes()
        b64 = base64.b64encode(data).decode("utf-8")
        # Assume JPEG for extracted frames; PNG screenshots are handled below.
        return f"data:image/jpeg;base64,{b64}"
    except Exception as exc:
        logger.warning("Could not read image %s: %s", path, exc)
        return None


def _content_block_to_message(content: str | list[dict[str, Any]] | dict[str, Any]) -> Any:
    """Normalize a message content value for the OpenAI-compatible API."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return [content]
    if isinstance(content, list):
        normalized: list[dict[str, Any]] = []
        for block in content:
            if isinstance(block, str):
                normalized.append({"type": "text", "text": block})
            elif isinstance(block, dict):
                if block.get("type") == "image_path":
                    data_url = _image_to_data_url(block["path"])
                    if data_url:
                        normalized.append({"type": "image_url", "image_url": {"url": data_url}})
                else:
                    normalized.append(block)
        return normalized
    return str(content)


def _classify_http_error(status_code: int, response_text: str = "") -> ProviderError:
    """Map HTTP status codes to typed provider errors."""
    lowered = response_text.lower()
    if status_code == 429 or "rate limit" in lowered or "too many requests" in lowered:
        return RateLimitError()
    if status_code == 401 or "unauthorized" in lowered or "invalid api key" in lowered:
        return AuthenticationError()
    if status_code == 402 or "insufficient" in lowered or "quota" in lowered or "balance" in lowered:
        return InsufficientBalanceError()
    return ProviderError(f"provider error {status_code}", status_code=status_code)


class ModelProvider(ABC):
    """Abstract base for model providers."""

    name: str = "abstract"

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Yield text chunks for a chat completion request."""
        yield ""

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return a non-streaming chat completion response."""
        return {}

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """Return provider health metadata."""
        return {"status": "unknown"}


class OpenAICompatibleProvider(ModelProvider):
    """Provider for OpenAI-compatible HTTP endpoints (text + vision)."""

    name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _normalize_messages(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return [
            {
                "role": msg.get("role", "user"),
                "content": _content_block_to_message(msg.get("content", "")),
            }
            for msg in messages
        ]

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _request_payload(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int | None,
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": self._normalize_messages(messages),
            "stream": stream,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        return payload

    async def stream_chat(  # type: ignore[override]
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        import httpx

        payload = self._request_payload(messages, model, temperature, max_tokens, stream=True)

        async with httpx.AsyncClient() as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=60,
                ) as response:
                    if response.status_code >= 400:
                        text = ""
                        try:
                            text = await response.aread()
                            text = text.decode("utf-8", errors="ignore")
                        except Exception:
                            pass
                        raise _classify_http_error(response.status_code, text)
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line.startswith("data: "):
                            continue
                        data = line.removeprefix("data: ").strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = __import__("json").loads(data)
                            delta = (
                                chunk.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content")
                            )
                            if delta:
                                yield delta
                        except Exception:
                            continue
            except httpx.HTTPStatusError as exc:
                raise _classify_http_error(exc.response.status_code, str(exc)) from exc
            except httpx.TimeoutException as exc:
                raise ProviderError(f"request timeout: {exc}", status_code=504) from exc
            except httpx.RequestError as exc:
                raise ProviderError(f"request failed: {exc}", status_code=None) from exc

    async def chat_completion(  # type: ignore[override]
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        import httpx

        payload = self._request_payload(messages, model, temperature, max_tokens, stream=False)

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=120,
                )
                if response.status_code >= 400:
                    raise _classify_http_error(response.status_code, response.text)
                return cast(dict[str, Any], response.json())
            except httpx.HTTPStatusError as exc:
                raise _classify_http_error(exc.response.status_code, str(exc)) from exc
            except httpx.TimeoutException as exc:
                raise ProviderError(f"request timeout: {exc}", status_code=504) from exc
            except httpx.RequestError as exc:
                raise ProviderError(f"request failed: {exc}", status_code=None) from exc

    async def health_check(self) -> dict[str, Any]:
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers=self._headers(),
                    timeout=10,
                )
                if response.status_code == 200:
                    return {"status": "healthy"}
                if response.status_code == 429:
                    return {"status": "degraded", "reason": "rate limited"}
                return {"status": "degraded", "reason": f"HTTP {response.status_code}"}
        except Exception as exc:
            return {"status": "offline", "reason": str(exc)}


class LocalMockProvider(ModelProvider):
    """Provider used in tests or for local fallback."""

    name = "local_mock"

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        yield "这是一个本地兜底回复。"

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "这是一个本地兜底回复。",
                    }
                }
            ]
        }

    async def health_check(self) -> dict[str, Any]:
        return {"status": "healthy"}


_PROVIDER_REGISTRY: dict[str, type[ModelProvider]] = {
    OpenAICompatibleProvider.name: OpenAICompatibleProvider,
    LocalMockProvider.name: LocalMockProvider,
}


def register_provider(name: str, cls: type[ModelProvider]) -> None:
    """Register a new model provider implementation."""
    _PROVIDER_REGISTRY[name] = cls


def create_provider(name: str, **kwargs: Any) -> ModelProvider:
    """Factory to instantiate a registered provider."""
    if name not in _PROVIDER_REGISTRY:
        raise ValueError(f"Unknown provider: {name}")
    return _PROVIDER_REGISTRY[name](**kwargs)
