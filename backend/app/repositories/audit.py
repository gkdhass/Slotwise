"""Audit writer.

The row is added to the caller's session, never committed here. A service that
commits its domain change without the audit row cannot accidentally produce a
half-audited transaction: both statements share the same ``asyncpg`` transaction
and the unit of work commits or rolls them back together.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import redact_mapping
from app.models.audit import AuditLog
from app.repositories.keyset import keyset_page
from app.repositories.pagination import Page


def _jsonable(value: Any) -> Any:
    """Make ORM snapshots JSONB-serialisable without losing field names."""
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID | Decimal | Enum):
        return str(value)
    return value


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        actor_id: uuid.UUID | None,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID | None,
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=cast(dict[str, Any] | None, redact_mapping(_jsonable(before))),
            after=cast(dict[str, Any] | None, redact_mapping(_jsonable(after))),
            ip_address=ip_address,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_page(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        actor_id: uuid.UUID | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> Page[AuditLog]:
        statement = select(AuditLog)
        if actor_id is not None:
            statement = statement.where(AuditLog.actor_id == actor_id)
        if action is not None:
            statement = statement.where(AuditLog.action == action)
        if entity_type is not None:
            statement = statement.where(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            statement = statement.where(AuditLog.entity_id == entity_id)
        if created_from is not None:
            statement = statement.where(AuditLog.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(AuditLog.created_at <= created_to)
        return await keyset_page(
            self.session,
            statement,
            scope="audit-logs",
            sort_column=AuditLog.created_at,
            id_column=AuditLog.id,
            limit=limit,
            cursor=cursor,
        )
