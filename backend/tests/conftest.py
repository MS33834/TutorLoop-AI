import asyncio
import logging
import os
from unittest.mock import patch

import asyncpg
import pytest

# The app validates these settings at import time; provide safe defaults for tests.
os.environ.setdefault("SECRET_KEY", "a" * 32)
os.environ.setdefault("LLM_API_KEYS", "sk-test-key")
os.environ.setdefault("LLM_BASE_URLS", "http://localhost:8000/v1")
os.environ.setdefault("LLM_MODELS", "test-model")

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PostgreSQL availability probe (session-scoped, sync).
#
# Uses asyncio.run internally so the fixture stays synchronous and avoids
# event-loop-scope conflicts with pytest-asyncio's function-scoped loop. The
# probe is a one-shot connect/close against the configured DATABASE_URL; if PG
# is unreachable (local sandbox without Docker) the E2E suite is skipped.
# ---------------------------------------------------------------------------
def _resolve_pg_dsn() -> str:
    """Return a plain postgresql:// DSN usable by asyncpg."""
    raw = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/tutorloop",
    )
    return raw.replace("postgresql+asyncpg://", "postgresql://")


async def _probe_pg() -> tuple[bool, str]:
    dsn = _resolve_pg_dsn()
    try:
        conn = await asyncpg.connect(dsn, timeout=3)
        await conn.close()
        return True, ""
    except Exception as exc:  # pragma: no cover - depends on env
        return False, f"{type(exc).__name__}: {exc}"


@pytest.fixture(scope="session")
def pg_available() -> bool:
    """Return True if a PostgreSQL backend is reachable for E2E tests."""
    ok, reason = asyncio.run(_probe_pg())
    if not ok:
        logger.info("PostgreSQL unavailable, E2E tests will be skipped: %s", reason)
    return ok


@pytest.fixture
def skip_without_pg(pg_available: bool) -> None:
    """Skip a test when PostgreSQL is not available."""
    if not pg_available:
        pytest.skip("需要 PostgreSQL")


# ---------------------------------------------------------------------------
# Schema bootstrap (session-scoped, autouse, sync).
#
# Creates all tables via Base.metadata.create_all (no Alembic) when PG is
# available, and drops them at session end. Uses asyncio.run + engine.dispose
# so connections are never shared across event loops (the setup loop is
# separate from each test's function-scoped loop).
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def setup_db(pg_available: bool):
    if not pg_available:
        yield
        return

    # Import here so the env-var defaults above are applied first.
    from app.db.postgres import engine
    from app.models.db import Base

    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # Dispose so no pooled connection is tied to this transient event loop;
        # tests will create fresh connections in their own loop.
        await engine.dispose()

    asyncio.run(_create())
    yield

    async def _drop():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(_drop())


# ---------------------------------------------------------------------------
# Gateway mocking (session-scoped, autouse).
#
# The chat router binds ``stream_chat`` at import time
# (``from app.gateway import stream_chat``), so we must patch
# ``app.routers.chat.stream_chat`` — not ``app.gateway.stream_chat`` — for the
# route handler to see the fake. ``chat_completion`` is also patched defensively
# on both modules so any Socratic-assessment / RAG path that imports it
# directly (socratic_agent, rag_service) also short-circuits.
# ---------------------------------------------------------------------------
async def _fake_stream_chat(messages, model_type: str = "text"):
    # Yield a couple of token chunks mirroring the real gateway's SSE shape.
    for token in ("你", "好", "，", "世", "界"):
        yield {"type": "token", "content": token}


async def _fake_chat_completion(messages, model_type: str = "text") -> dict:
    return {"choices": [{"message": {"content": "mocked chat completion"}}]}


@pytest.fixture(scope="session", autouse=True)
def mock_gateway():
    with (
        patch("app.routers.chat.stream_chat", _fake_stream_chat),
        patch("app.gateway.chat_completion", _fake_chat_completion),
        patch("app.services.socratic_agent.chat_completion", _fake_chat_completion),
    ):
        yield


# ---------------------------------------------------------------------------
# Rate-limiter disabling (session-scoped, autouse).
#
# SlowAPI's default_limits would 429 bursty E2E requests against the same
# 127.0.0.1 client. Flip the global limiter off for the whole session.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def disable_limiter():
    from app.limiter import limiter

    previous = getattr(limiter, "enabled", True)
    limiter.enabled = False
    try:
        yield
    finally:
        limiter.enabled = previous


# ---------------------------------------------------------------------------
# HTTP client (function-scoped, async).
#
# Uses httpx.ASGITransport against the real FastAPI app without triggering its
# lifespan (which would try Neo4j/Redis). app.state.redis is set to None so
# getattr(...) calls in routes behave as if no Redis is configured (sync
# fallback path for video/graph processing).
# ---------------------------------------------------------------------------
@pytest.fixture
async def async_client():
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    # Without lifespan, app.state.redis is never set; ensure the attribute
    # exists so getattr(..., None) returns None rather than raising.
    if not hasattr(app.state, "redis"):
        app.state.redis = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Auth fixtures (function-scoped, async).
#
# The /api/auth/register endpoint always creates role="student" (the schema
# has no role field), but the course owner check is created_by == user.id, so
# a student who creates a course is its owner and passes all owner-gated
# endpoints. The fixture registers once; if the user already exists (from a
# previous test run / leftover row) it falls back to login.
# ---------------------------------------------------------------------------
E2E_USERNAME = "e2e_teacher"
E2E_PASSWORD = "Test1234!"


@pytest.fixture
async def auth_token(async_client) -> str:
    resp = await async_client.post(
        "/api/auth/register",
        json={"username": E2E_USERNAME, "password": E2E_PASSWORD},
    )
    if resp.status_code == 409:
        # User already exists from a previous run / leftover row.
        resp = await async_client.post(
            "/api/auth/login",
            json={"username": E2E_USERNAME, "password": E2E_PASSWORD},
        )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["access_token"]


@pytest.fixture
async def auth_headers(auth_token: str) -> dict:
    return {"Authorization": f"Bearer {auth_token}"}
