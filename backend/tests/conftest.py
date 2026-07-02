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
# available, and drops them at session end.
#
# CRITICAL — event-loop isolation (Sprint 1.4 fix):
# The previous implementation reused the module-level singleton
# ``app.db.postgres.engine`` to create tables inside ``asyncio.run()``. That
# engine's connection pool (asyncpg Protocol objects + Future objects) became
# bound to the transient setup loop; even after ``engine.dispose()`` the
# ``AsyncAdaptedQueuePool`` retained adapters that, when reused by tests
# running in their own function-scoped loop, raised
# ``RuntimeError: Task got Future attached to a different loop`` (and a
# cascading ``ValueError: password cannot be longer than 72 bytes`` from
# passlib's threadpool).
#
# Fix: setup_db builds a **dedicated, throwaway engine** that is fully
# disposed within the setup loop. The global ``app.db.postgres.engine`` is
# never touched here, so its pool is empty when tests begin — each test
# creates fresh connections bound to its own loop. A new throwaway engine is
# built again at teardown for the drop.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def setup_db(pg_available: bool):
    if not pg_available:
        yield
        return

    # Import here so the env-var defaults above are applied first.
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.config import settings
    from app.models.db import Base

    async def _create() -> None:
        # Dedicated throwaway engine: completely isolated from the global
        # ``app.db.postgres.engine`` singleton used by tests. Its connections
        # are bound to this setup loop and destroyed with it.
        tmp_engine = create_async_engine(settings.database_url, future=True)
        try:
            async with tmp_engine.begin() as conn:
                # pgvector extension must exist before any table with VECTOR
                # columns can be created. The migrations job creates it via
                # alembic, but this fixture uses Base.metadata.create_all.
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await tmp_engine.dispose()

    asyncio.run(_create())
    yield

    async def _drop() -> None:
        # A fresh throwaway engine for teardown (the create-time one is gone).
        tmp_engine = create_async_engine(settings.database_url, future=True)
        try:
            async with tmp_engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
        finally:
            await tmp_engine.dispose()

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
