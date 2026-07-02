"""Application settings loaded from environment variables."""

from pydantic import Field, field_validator, model_validator
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
    local_model: str = Field(default="qwen2.5-3b", alias="LOCAL_MODEL")

    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")

    secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    # When True, the refresh-token cookie is always sent with Secure. Useful
    # for production deployments that terminate TLS outside the app (so the
    # request scheme seen by the app is still HTTP). Defaults to False so local
    # dev over HTTP keeps working; override with COOKIE_SECURE=true in prod.
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")

    @field_validator("secret_key")
    @classmethod
    def _validate_secret_key(cls, value: str) -> str:
        if not value or len(value) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        if value == "change-me-in-production":
            raise ValueError("SECRET_KEY is using the default insecure value; set a strong random key")
        # Reject well-known placeholder values shipped in env.example so a
        # forgotten edit does not silently expose the JWT signing key.
        insecure_placeholders = {
            "please_change_this_secret_key_before_deployment",
            "replace-with-a-strong-random-key-of-at-least-32-chars",
            "change-me",
            "changeme",
            "secret",
        }
        if value.lower() in insecure_placeholders:
            raise ValueError(
                "SECRET_KEY is using a known placeholder value; set a strong random key"
            )
        return value

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/tutorloop",
        alias="DATABASE_URL",
    )
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="", alias="NEO4J_PASSWORD")

    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")

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

    @field_validator("app_port")
    @classmethod
    def _validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("APP_PORT must be between 1 and 65535")
        return value

    @field_validator("frame_interval_seconds")
    @classmethod
    def _validate_frame_interval(cls, value: int) -> int:
        if value < 1:
            raise ValueError("FRAME_INTERVAL_SECONDS must be at least 1")
        return value

    @field_validator("access_token_expire_minutes")
    @classmethod
    def _validate_token_expiry(cls, value: int) -> int:
        if value < 1:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be at least 1")
        # Access tokens should be short-lived; a leaked long-lived access token
        # cannot be revoked. Cap at 24h to prevent misconfiguration (e.g. the
        # 7-day value previously shipped in env.example). Use refresh tokens
        # for long sessions instead.
        if value > 1440:
            raise ValueError(
                "ACCESS_TOKEN_EXPIRE_MINUTES must not exceed 1440 (24h); "
                "use refresh tokens for longer sessions"
            )
        return value

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

    @model_validator(mode="after")
    def _validate_llm_key_lists(self):
        keys = [x for x in self.llm_api_keys_raw.split(",") if x.strip()] if self.llm_api_keys_raw else []
        bases = [x for x in self.llm_base_urls_raw.split(",") if x.strip()] if self.llm_base_urls_raw else []
        models = [x for x in self.llm_models_raw.split(",") if x.strip()] if self.llm_models_raw else []
        if not (len(keys) == len(bases) == len(models)):
            raise ValueError("LLM_API_KEYS, LLM_BASE_URLS, LLM_MODELS must have the same length")
        return self

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
