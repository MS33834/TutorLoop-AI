"""Unit tests for Settings configuration validation."""

import pytest
from pydantic import ValidationError

from app.config import Settings

# Environment variables that Settings reads; these must be cleared so the
# keyword arguments we pass to Settings() are actually used.
_ENV_KEYS = [
    "SECRET_KEY", "LLM_API_KEYS", "LLM_BASE_URLS", "LLM_MODELS",
    "APP_PORT", "FRAME_INTERVAL_SECONDS", "ACCESS_TOKEN_EXPIRE_MINUTES",
    "BKT_P_L0", "BKT_P_T", "BKT_P_G", "BKT_P_S", "RECOMMEND_STRATEGY",
]


@pytest.fixture
def clean_env(monkeypatch):
    """Remove all Settings-related env vars so tests control all inputs."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_config_secret_key_too_short_raises(clean_env):
    """SECRET_KEY shorter than 32 characters must be rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, SECRET_KEY="short")
    assert "32 characters" in str(exc_info.value)


def test_config_secret_key_default_value_raises(clean_env):
    """The default SECRET_KEY placeholder must be rejected.

    The default value 'change-me-in-production' is 25 chars, so it fails the
    length check first. We verify the default is rejected regardless.
    """
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY="change-me-in-production")


def test_config_app_port_out_of_range_raises(clean_env):
    """APP_PORT outside 1-65535 must be rejected."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY="x" * 32, APP_PORT=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY="x" * 32, APP_PORT=70000)


def test_config_app_port_valid(clean_env):
    """Valid APP_PORT values should be accepted."""
    s = Settings(_env_file=None, SECRET_KEY="x" * 32, APP_PORT=8080)
    assert s.app_port == 8080


def test_config_frame_interval_must_be_positive(clean_env):
    """FRAME_INTERVAL_SECONDS < 1 must be rejected."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY="x" * 32, FRAME_INTERVAL_SECONDS=0)


def test_config_token_expiry_must_be_positive(clean_env):
    """ACCESS_TOKEN_EXPIRE_MINUTES < 1 must be rejected."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY="x" * 32, ACCESS_TOKEN_EXPIRE_MINUTES=0)


def test_config_bkt_probability_out_of_range_raises(clean_env):
    """BKT probabilities outside [0, 1] must be rejected."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY="x" * 32, BKT_P_L0=1.5)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY="x" * 32, BKT_P_S=-0.1)


def test_config_recommend_strategy_invalid_raises(clean_env):
    """Invalid RECOMMEND_STRATEGY must be rejected."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY="x" * 32, RECOMMEND_STRATEGY="unknown_strategy")


def test_config_llm_key_lists_mismatched_length_raises(clean_env):
    """LLM_API_KEYS / LLM_BASE_URLS / LLM_MODELS must have equal length."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            SECRET_KEY="x" * 32,
            LLM_API_KEYS="key1,key2",
            LLM_BASE_URLS="http://a",
            LLM_MODELS="model1,model2",
        )
    assert "same length" in str(exc_info.value)


def test_config_llm_key_lists_matched_length_ok(clean_env):
    """Matched-length LLM lists should be accepted."""
    s = Settings(
        _env_file=None,
        SECRET_KEY="x" * 32,
        LLM_API_KEYS="key1,key2",
        LLM_BASE_URLS="http://a,http://b",
        LLM_MODELS="model1,model2",
    )
    assert len(s.llm_api_keys) == 2
    assert len(s.llm_key_configs) == 2
