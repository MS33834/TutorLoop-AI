"""FastAPI application entry point."""

import logging
import os
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from sqlalchemy import text

from app.config import settings
from app.db.neo4j import close_driver, get_driver
from app.db.postgres import close_db, engine, init_db
from app.gateway import start_health_probe, stop_health_probe
from app.limiter import limiter
from app.routers import auth, chat, courses, rooms, users
from app.tasks.worker import _redis_settings

logger = logging.getLogger(__name__)

if os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

    # init_db handles Alembic migrations when RUN_ALEMBIC_MIGRATIONS is set,
    # otherwise it falls back to metadata.create_all. No duplicate run here.
    await init_db()

    redis_pool = None
    if os.environ.get("REDIS_URL"):
        try:
            from arq import create_pool

            redis_pool = await create_pool(_redis_settings())
            app.state.redis = redis_pool
            logger.info("Connected to Redis task queue")
        except Exception as exc:
            logger.warning("Could not connect to Redis task queue: %s", exc)

    # Start periodic AI key health probing so the gateway can recover keys
    # without waiting for a user request.
    start_health_probe(interval_seconds=60.0)

    yield

    stop_health_probe()
    if redis_pool is not None:
        await redis_pool.close()
    # Close shared httpx clients in the AI gateway key pool and local fallback.
    try:
        from app.gateway import close_local_provider
        from app.gateway import pool as _gateway_pool

        await _gateway_pool.close_all()
        await close_local_provider()
    except Exception as exc:
        logger.warning("Could not close gateway HTTP clients: %s", exc)
    await close_db()
    await close_driver()


app = FastAPI(
    title="TutorLoop Gateway",
    version="0.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Attach a unique request ID to every request for tracing and logging.

    Honours an incoming X-Request-ID header (e.g. from an API gateway) when
    present, otherwise generates a UUID4. The ID is stored on request.state
    and echoed back in the response header for client-side correlation.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add baseline security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers[
        "Permissions-Policy"
    ] = "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
    response.headers[
        "Content-Security-Policy"
    ] = "default-src 'self'; frame-ancestors 'none'; connect-src 'self'; img-src 'self' data:; media-src 'self'; object-src 'none'; base-uri 'self';"
    return response


app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(courses.router)
app.include_router(rooms.router)
app.include_router(users.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("Unhandled exception [request_id=%s]: %s", request_id, exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务暂时开小差了，请稍后重试",
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )


async def _postgres_ready() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("PostgreSQL readiness check failed: %s", exc)
        return False


async def _neo4j_ready() -> bool:
    try:
        driver = await get_driver()
        await driver.verify_connectivity()
        return True
    except Exception as exc:
        logger.warning("Neo4j readiness check failed: %s", exc)
        return False


@app.get("/ready")
async def readiness_probe():
    """Return 200 only when critical dependencies are reachable."""
    pg_ok = await _postgres_ready()
    neo4j_ok = await _neo4j_ready()
    if not (pg_ok and neo4j_ok):
        raise HTTPException(
            status_code=503,
            detail={
                "ready": False,
                "postgres": pg_ok,
                "neo4j": neo4j_ok,
            },
        )
    return {"ready": True, "postgres": True, "neo4j": True}


@app.get("/live")
async def liveness_probe():
    return {"alive": True}


# Lightweight Prometheus-style metrics (no external dependency).
# Thread-safe counters guarded by a lock to remain correct under any
# thread-pool / multi-worker usage.
_metrics_lock = threading.Lock()
_request_count = 0
_error_count = 0


@app.middleware("http")
async def _metrics_middleware(request: Request, call_next):
    global _request_count, _error_count
    with _metrics_lock:
        _request_count += 1
    response = await call_next(request)
    if response.status_code >= 500:
        with _metrics_lock:
            _error_count += 1
    return response


@app.get("/metrics")
async def metrics_probe():
    """Return basic Prometheus-style metrics for Grafana scraping."""
    with _metrics_lock:
        req_total, err_total = _request_count, _error_count
    lines = [
        "# HELP tutorloop_requests_total Total requests served by this instance",
        "# TYPE tutorloop_requests_total counter",
        f"tutorloop_requests_total {req_total}",
        "# HELP tutorloop_errors_total Total 5xx responses served by this instance",
        "# TYPE tutorloop_errors_total counter",
        f"tutorloop_errors_total {err_total}",
    ]
    return PlainTextResponse("\n".join(lines) + "\n")


app.mount(
    "/uploads",
    StaticFiles(directory=settings.upload_dir, check_dir=False),
    name="uploads",
)
