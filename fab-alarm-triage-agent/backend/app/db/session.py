"""Async engine / session factory."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.db.models import Base

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().async_dsn, pool_pre_ping=True)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency."""
    async with get_sessionmaker()() as session:
        yield session


# Any constant works as long as every replica uses the same one.
_CREATE_ALL_LOCK_ID = 0x7FAB7121


async def create_all() -> None:
    """Create MES tables, one replica at a time.

    `create_all` reflects and then issues a bare CREATE TABLE, so two replicas starting
    together can both decide a table is missing and the loser crashes with "relation
    already exists" — failing its lifespan and crash-looping. A session-level advisory
    lock serialises them; it is released when the connection closes.

    LangGraph's checkpoint tables are created separately by `AsyncPostgresSaver.setup()`.
    """
    from sqlalchemy import text

    async with get_engine().begin() as conn:
        await conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _CREATE_ALL_LOCK_ID})
        await conn.run_sync(Base.metadata.create_all)
