"""Pluggable LLM/VLM provider interface and registry."""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator


class ModelProvider(ABC):
    """Abstract base for model providers."""

    name: str = "abstract"

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Yield text chunks for a chat completion request."""
        yield ""

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """Return provider health metadata."""
        return {"status": "unknown"}


class OpenAICompatibleProvider(ModelProvider):
    """Provider for OpenAI-compatible HTTP endpoints."""

    name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            ) as response:
                response.raise_for_status()
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

    async def health_check(self) -> dict[str, Any]:
        return {"status": "healthy"}


class LocalMockProvider(ModelProvider):
    """Provider used in tests or for local fallback."""

    name = "local_mock"

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        yield "这是一个本地兜底回复。"

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
