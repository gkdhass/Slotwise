"""Typed repository primitives.

Repositories only translate between the domain caller and SQLAlchemy: no policy,
state-machine or orchestration logic lives here. Transactions are owned by the
caller (or by :class:`UnitOfWork`) so an audit row can share the transaction of
the change it records.
"""

from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        return entity

    async def flush(self) -> None:
        await self.session.flush()

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)

    async def list_offset(self, *, limit: int = 100, offset: int = 0) -> list[ModelT]:
        """Offset pagination for bounded admin collections.

        Alert/event feeds use keyset pagination instead; offset is retained only
        for stable, small reference tables used by admin screens.
        """
        statement = select(self.model).limit(limit).offset(offset)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count(self) -> int:
        from sqlalchemy import func

        statement = select(func.count()).select_from(self.model)
        result = await self.session.execute(statement)
        return int(result.scalar_one())


def as_dict(entity: Base, *, exclude: set[str] | None = None) -> dict[str, Any]:
    """Convert an ORM row to a plain mapping for audit snapshots."""
    excluded = exclude or set()
    return {
        column.key: getattr(entity, column.key)
        for column in entity.__table__.columns
        if column.key not in excluded
    }
