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

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/tutorloop",
        alias="DATABASE_URL",
    )
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="", alias="NEO4J_PASSWORD")

    cors_origins_raw: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    upload_dir: str = Field(default="uploads", alias="UPLOAD_DIR")
    frame_interval_seconds: int = Field(default=5, alias="FRAME_INTERVAL_SECONDS")

    recommend_strategy: str = Field(default="mastery_gap", alias="RECOMMEND_STRATEGY")

    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2", alias="EMBEDDING_MODEL"
    )

    bkt_p_l0: float = Field(default=0.3, alias="BKT_P_L0")
    bkt_p_t: float = Field(default=0.3, alias="BKT_P_T")
    bkt_p_g: float = Field(default=0.2, alias="BKT_P_G")
    bkt_p_s: float = Field(default=0.1, alias="BKT_P_S")

    vlm_model: str = Field(default="qwen2.5-vl", alias="VLM_MODEL")
    vlm_base_url: str = Field(default="", alias="VLM_BASE_URL")
    vlm_api_key: str = Field(default="", alias="VLM_API_KEY")

    @field_validator("llm_api_keys_raw", "llm_base_urls_raw", "llm_models_raw", "cors_origins_raw")
    @classmethod
    def _strip_whitespace(cls, value: str) -> str:
        return value.strip()

    @field_validator("bkt_p_l0", "bkt_p_t", "bkt_p_g", "bkt_p_s")
    @classmethod
    def _validate_probability(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("BKT probabilities must be between 0 and 1")
        return value

    @field_validator("recommend_strategy")
    @classmethod
    def _validate_recommend_strategy(cls, value: str) -> str:
        allowed = {"mastery_gap", "balanced"}
        if value not in allowed:
            raise ValueError(f"RECOMMEND_STRATEGY must be one of {allowed}")
        return value

    @property
    def cors_origins(self) -> list[str]:
        if not self.cors_origins_raw:
            return []
        return [item.strip() for item in self.cors_origins_raw.split(",") if item.strip()]

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
