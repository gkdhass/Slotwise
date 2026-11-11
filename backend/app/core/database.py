"""Async SQLAlchemy engine and session lifecycle.

Phase 1 intentionally defines no tables; Alembic and the declarative base are
wired now so Phase 2 can add models without changing application plumbing.
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
        _engine = create_async_engine(
            resolved.database.url,
            pool_size=resolved.database.pool_size,
            max_overflow=resolved.database.max_overflow,
            pool_timeout=resolved.database.pool_timeout_seconds,
            pool_recycle=resolved.database.pool_recycle_seconds,
            pool_pre_ping=True,
            echo=resolved.database.echo,
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
