"""Async SQLAlchemy engine and session lifecycle.

The engine is created once per process with UTC, an application name and a
server-side statement timeout, so runaway queries cannot exhaust the pool.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings | None = None) -> AsyncEngine:
    """Create the process-wide async engine exactly once."""
    global _engine, _session_factory
    if _engine is None:
        resolved = settings or get_settings()
        database = resolved.database
        server_settings: dict[str, str] = {
            "application_name": database.application_name,
            "timezone": "UTC",
        }
        if database.statement_timeout_ms > 0:
            server_settings["statement_timeout"] = str(database.statement_timeout_ms)
        _engine = create_async_engine(
            database.url,
            pool_size=database.pool_size,
            max_overflow=database.max_overflow,
            pool_timeout=database.pool_timeout_seconds,
            pool_recycle=database.pool_recycle_seconds,
            pool_pre_ping=True,
            echo=database.echo,
            connect_args={
                "timeout": database.connect_timeout_seconds,
                "server_settings": server_settings,
            },
        )
        _session_factory = async_sessionmaker(
            bind=_engine,
            expire_on_commit=False,
            autoflush=False,
        )
    return _engine


def get_engine() -> AsyncEngine:
    return init_engine()


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        init_engine()
    if _session_factory is None:  # pragma: no cover - guarded by init_engine
        raise RuntimeError("Database session factory is not initialised")
    return _session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a transaction-scoped session."""
    async with get_session_factory()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
