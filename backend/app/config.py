"""Application settings loaded from environment variables."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_api_keys_raw: str = Field(default="", alias="LLM_API_KEYS")
    llm_base_urls_raw: str = Field(default="", alias="LLM_BASE_URLS")
    llm_models_raw: str = Field(default="", alias="LLM_MODELS")

    local_base_url: str = Field(default="http://localhost:8001/v1", alias="LOCAL_BASE_URL")
    local_model: str = Field(default="qwen3.5-4b", alias="LOCAL_MODEL")

    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")

    @field_validator("llm_api_keys_raw", "llm_base_urls_raw", "llm_models_raw")
    @classmethod
    def _strip_whitespace(cls, value: str) -> str:
        return value.strip()

    @property
    def llm_api_keys(self) -> list[str]:
        if not self.llm_api_keys_raw:
            return []
        return [item.strip() for item in self.llm_api_keys_raw.split(",") if item.strip()]

    @property
    def llm_base_urls(self) -> list[str]:
        if not self.llm_base_urls_raw:
            return []
        return [item.strip() for item in self.llm_base_urls_raw.split(",") if item.strip()]

    @property
    def llm_models(self) -> list[str]:
        if not self.llm_models_raw:
            return []
        return [item.strip() for item in self.llm_models_raw.split(",") if item.strip()]

    @property
    def llm_key_configs(self):
        """Zip parallel lists into per-key configuration dicts."""
        keys = self.llm_api_keys
        bases = self.llm_base_urls
        models = self.llm_models
        if not (len(keys) == len(bases) == len(models)):
            raise ValueError(
                "LLM_API_KEYS, LLM_BASE_URLS, LLM_MODELS must have the same length"
            )
        return [
            {"key": key, "base_url": base, "model": model}
            for key, base, model in zip(keys, bases, models, strict=True)
        ]


settings = Settings()
