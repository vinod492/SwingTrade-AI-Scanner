"""Async engine / session factory. Works with SQLite (dev/tests) and Postgres (docker)."""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        kwargs = {}
        if settings.database_url.startswith("postgresql"):
            kwargs = {"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True}
        _engine = create_async_engine(settings.database_url, **kwargs)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    async with get_session_factory()() as session:
        yield session


def reset_engine() -> None:
    """Used by tests to swap DATABASE_URL."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
