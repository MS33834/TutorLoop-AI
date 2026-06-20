"""Async PostgreSQL database access."""

import logging

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create all SQLAlchemy tables."""
    from app.models.db import Base as AppBase  # noqa: PLC0415

    try:
        async with engine.begin() as conn:
            await conn.run_sync(AppBase.metadata.create_all)
        logger.info("PostgreSQL tables created/verified")
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not create tables automatically: %s", exc)


async def close_db() -> None:
    await engine.dispose()
