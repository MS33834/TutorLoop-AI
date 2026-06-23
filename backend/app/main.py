"""FastAPI application entry point."""

import logging
import os
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


def _run_alembic_migrations() -> None:
    """Run Alembic migrations synchronously before accepting traffic."""
    try:
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations completed")
    except Exception as exc:
        logger.warning("Could not run Alembic migrations: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

    if os.environ.get("RUN_ALEMBIC_MIGRATIONS", "").lower() in {"true", "1", "yes"}:
        _run_alembic_migrations()

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

    yield

    if redis_pool is not None:
        await redis_pool.close()
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
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept"],
)


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
    ] = "default-src 'self'; frame-ancestors 'none'; connect-src 'self' *;"
    return response


app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(courses.router)
app.include_router(rooms.router)
app.include_router(users.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务暂时开小差了，请稍后重试"},
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
_request_count = 0
_error_count = 0


@app.middleware("http")
async def _metrics_middleware(request: Request, call_next):
    global _request_count, _error_count
    _request_count += 1
    response = await call_next(request)
    if response.status_code >= 500:
        _error_count += 1
    return response


@app.get("/metrics")
async def metrics_probe():
    """Return basic Prometheus-style metrics for Grafana scraping."""
    lines = [
        "# HELP tutorloop_requests_total Total requests served by this instance",
        "# TYPE tutorloop_requests_total counter",
        f"tutorloop_requests_total {_request_count}",
        "# HELP tutorloop_errors_total Total 5xx responses served by this instance",
        "# TYPE tutorloop_errors_total counter",
        f"tutorloop_errors_total {_error_count}",
    ]
    return PlainTextResponse("\n".join(lines) + "\n")


app.mount(
    "/uploads",
    StaticFiles(directory=settings.upload_dir, check_dir=False),
    name="uploads",
)
