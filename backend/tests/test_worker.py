"""Unit tests for ARQ worker Redis URL parsing."""

import pytest

from app.tasks.worker import _redis_settings


@pytest.fixture
def redis_env(monkeypatch):
    """Fixture to set REDIS_URL and restore it after the test."""
    def _set(url):
        monkeypatch.setenv("REDIS_URL", url)
    return _set


def test_redis_settings_default(monkeypatch):
    """Without REDIS_URL, defaults to localhost:6379."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    rs = _redis_settings()
    assert rs.host == "localhost"
    assert rs.port == 6379


def test_redis_settings_simple(redis_env):
    redis_env("redis://localhost:6379")
    rs = _redis_settings()
    assert rs.host == "localhost"
    assert rs.port == 6379


def test_redis_settings_custom_port(redis_env):
    redis_env("redis://redis-host:6380")
    rs = _redis_settings()
    assert rs.host == "redis-host"
    assert rs.port == 6380


def test_redis_settings_with_password(redis_env):
    redis_env("redis://:secretpass@localhost:6379")
    rs = _redis_settings()
    assert rs.host == "localhost"
    assert rs.port == 6379
    assert rs.password == "secretpass"


def test_redis_settings_with_user_and_password(redis_env):
    redis_env("redis://default:complex:pass@redis-host:6380")
    rs = _redis_settings()
    assert rs.host == "redis-host"
    assert rs.port == 6380
    # urlparse percent-decodes the password; colon in password is preserved.
    assert rs.password is not None


def test_redis_settings_with_database_index(redis_env):
    redis_env("redis://localhost:6379/3")
    rs = _redis_settings()
    assert rs.host == "localhost"
    assert rs.port == 6379
    assert getattr(rs, "database", None) == 3


def test_redis_settings_full_url(redis_env):
    redis_env("redis://user:p%40ss@myredis.example.com:6390/5")
    rs = _redis_settings()
    assert rs.host == "myredis.example.com"
    assert rs.port == 6390
    # %40 decodes to @
    assert rs.password == "p@ss"
    assert getattr(rs, "database", None) == 5


def test_redis_settings_invalid_scheme_returns_defaults(monkeypatch):
    """Non-redis schemes fall back to default RedisSettings."""
    monkeypatch.setenv("REDIS_URL", "http://example.com")
    rs = _redis_settings()
    # Default RedisSettings has host='localhost' etc. (arq defaults)
    assert rs.host == "localhost"
