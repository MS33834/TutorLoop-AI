"""ARQ worker configuration."""

import logging
import os
from urllib.parse import unquote, urlparse

from arq import create_pool
from arq.connections import RedisSettings
from arq.cron import cron

from app.db.neo4j import close_driver
from app.db.postgres import close_db, init_db
from app.tasks.jobs import (
    build_knowledge_graph_task,
    cleanup_expired_anonymous_data_task,
    cleanup_screenshots_task,
    probe_keys_health_task,
    process_video_task,
)

logger = logging.getLogger(__name__)


def _redis_settings() -> RedisSettings:
    """Build RedisSettings from REDIS_URL or defaults.

    Supports the full ``redis://[username[:password]@]host[:port][/db]``
    syntax via urllib.parse, including percent-encoded credentials and a
    database index.
    """
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    parsed = urlparse(redis_url)

    if parsed.scheme not in {"redis", "rediss", "unix"}:
        return RedisSettings()

    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    # urlparse returns the password percent-encoded; decode it so special
    # characters (e.g. @, :, /) in the password are restored.
    password = unquote(parsed.password) if parsed.password else None

    settings_kwargs: dict = {"host": host, "port": port, "password": password}

    # Honour the database index when present (e.g. redis://host:6379/2).
    if parsed.path and len(parsed.path) > 1:
        db_str = parsed.path.lstrip("/")
        try:
            settings_kwargs["database"] = int(db_str)
        except ValueError:
            logger.warning("Ignoring invalid Redis DB index %r in %s", db_str, redis_url)

    return RedisSettings(**settings_kwargs)


async def on_startup(ctx: dict) -> None:
    """Initialize DB connections for the worker process."""
    logging.basicConfig(level=logging.INFO)
    await init_db()
    ctx["redis"] = await create_pool(_redis_settings())


async def on_shutdown(ctx: dict) -> None:
    """Clean up DB connections."""
    await close_db()
    await close_driver()
    redis = ctx.get("redis")
    if redis is not None:
        await redis.close()


class WorkerSettings:
    """ARQ worker settings used by `arq app.tasks.worker.WorkerSettings`."""

    redis_settings = _redis_settings()
    on_startup = on_startup
    on_shutdown = on_shutdown
    functions = [
        process_video_task,
        build_knowledge_graph_task,
        cleanup_screenshots_task,
        cleanup_expired_anonymous_data_task,
        probe_keys_health_task,
    ]
    max_jobs = int(os.environ.get("ARQ_MAX_JOBS", "10"))
    job_timeout = int(os.environ.get("ARQ_JOB_TIMEOUT", "600"))
    keep_result = int(os.environ.get("ARQ_KEEP_RESULT", "3600"))

    # Scheduled jobs (cron). Times are in UTC.
    cron_jobs = [
        # Delete expired screenshot temp files daily at 03:00 UTC.
        cron(cleanup_screenshots_task, hour=3, minute=0),
        # Purge stale anonymous data daily at 04:00 UTC.
        cron(cleanup_expired_anonymous_data_task, hour=4, minute=0),
        # Probe AI key health every 30 seconds (TechSpec §3.1 heartbeat).
        cron(probe_keys_health_task, second={0, 30}),
    ]
