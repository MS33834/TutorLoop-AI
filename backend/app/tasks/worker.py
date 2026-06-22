"""ARQ worker configuration."""

import logging
import os

from arq import create_pool
from arq.connections import RedisSettings

from app.db.neo4j import close_driver
from app.db.postgres import close_db, init_db
from app.tasks.jobs import build_knowledge_graph_task, process_video_task

logger = logging.getLogger(__name__)


def _redis_settings() -> RedisSettings:
    """Build RedisSettings from REDIS_URL or defaults."""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    # arq expects host/port/password; parse a simple redis:// URL.
    if redis_url.startswith("redis://"):
        rest = redis_url[len("redis://") :]
        auth_host, _, port_db = rest.partition(":")
        if "@" in auth_host:
            password, _, host = auth_host.partition("@")
        else:
            password = None
            host = auth_host
        port_str, _, _ = port_db.partition("/")
        port = int(port_str) if port_str else 6379
        return RedisSettings(host=host, port=port, password=password)
    return RedisSettings()


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
    functions = [process_video_task, build_knowledge_graph_task]
    max_jobs = int(os.environ.get("ARQ_MAX_JOBS", "10"))
    job_timeout = int(os.environ.get("ARQ_JOB_TIMEOUT", "600"))
    keep_result = int(os.environ.get("ARQ_KEEP_RESULT", "3600"))
