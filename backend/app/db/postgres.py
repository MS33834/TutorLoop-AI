"""Async PostgreSQL database access."""

import asyncio
import logging
import os

from alembic.config import Config
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create all SQLAlchemy tables or run Alembic migrations.

    When RUN_ALEMBIC_MIGRATIONS=true is set, the application runs
    `alembic upgrade head` on startup instead of SQLAlchemy metadata
    create_all. This is the recommended approach for production deployments.
    Migration failures are propagated so the container crashes rather than
    running with an out-of-date schema.
    """

    if os.environ.get("RUN_ALEMBIC_MIGRATIONS", "").lower() in {"1", "true", "yes"}:
        try:
            alembic_cfg = Config("alembic.ini")
            # Alembic's command.upgrade is synchronous and internally uses
            # asyncio.run; run it in the default thread pool to avoid blocking
            # the caller's event loop.
            await asyncio.get_event_loop().run_in_executor(
                None, command.upgrade, alembic_cfg, "head"
            )
            logger.info("Alembic migrations applied to head")
            return
        except Exception:
            logger.exception("Could not run Alembic migrations")
            raise

    from app.models.db import Base as AppBase  # noqa: PLC0415

    try:
        async with engine.begin() as conn:
            await conn.run_sync(AppBase.metadata.create_all)
        logger.info("PostgreSQL tables created/verified")
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not create tables automatically: %s", exc)


async def close_db() -> None:
    await engine.dispose()
