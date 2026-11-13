"""Response policy, allow-list and action repositories."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, or_, select

from app.models.responses import AllowlistEntry, ResponseAction, ResponsePolicy
from app.repositories.base import BaseRepository
from app.repositories.keyset import keyset_page
from app.repositories.pagination import Page


class ResponsePolicyRepository(BaseRepository[ResponsePolicy]):
    model = ResponsePolicy

    async def get_by_name(self, name: str) -> ResponsePolicy | None:
        """Return the newest version of a named policy."""
        result = await self.session.execute(
            select(ResponsePolicy)
            .where(ResponsePolicy.name == name)
            .order_by(ResponsePolicy.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def next_version(self, name: str) -> int:
        result = await self.session.execute(
            select(func.max(ResponsePolicy.version)).where(ResponsePolicy.name == name)
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1

    async def list_versions(self, name: str) -> list[ResponsePolicy]:
        result = await self.session.execute(
            select(ResponsePolicy)
            .where(ResponsePolicy.name == name)
            .order_by(ResponsePolicy.version.desc())
        )
        return list(result.scalars().all())

    async def list_page(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        name: str | None = None,
        action_type: str | None = None,
        enabled: bool | None = None,
    ) -> Page[ResponsePolicy]:
        statement = select(ResponsePolicy)
        if name is not None:
            statement = statement.where(ResponsePolicy.name == name)
        if action_type is not None:
            statement = statement.where(ResponsePolicy.action_type == action_type)
        if enabled is not None:
            statement = statement.where(ResponsePolicy.enabled.is_(enabled))
        return await keyset_page(
            self.session,
            statement,
            scope="response-policies",
            sort_column=ResponsePolicy.created_at,
            id_column=ResponsePolicy.id,
            limit=limit,
            cursor=cursor,
        )

    async def set_enabled(self, policy: ResponsePolicy, enabled: bool) -> None:
        policy.enabled = enabled
        await self.session.flush()

    async def list_enabled(self) -> list[ResponsePolicy]:
        statement = (
            select(ResponsePolicy)
            .where(ResponsePolicy.enabled.is_(True))
            .order_by(ResponsePolicy.name)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())


class AllowlistRepository(BaseRepository[AllowlistEntry]):
    model = AllowlistEntry

    async def find_active(
        self, entry_type: str, value: str, *, now: Any | None = None
    ) -> AllowlistEntry | None:
        moment = now if now is not None else func.now()
        statement = select(AllowlistEntry).where(
            AllowlistEntry.entry_type == entry_type,
            AllowlistEntry.value == value,
            AllowlistEntry.is_active.is_(True),
            or_(AllowlistEntry.expires_at.is_(None), AllowlistEntry.expires_at > moment),
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_active(self) -> list[AllowlistEntry]:
        statement = (
            select(AllowlistEntry)
            .where(AllowlistEntry.is_active.is_(True))
            .order_by(AllowlistEntry.entry_type, AllowlistEntry.value)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_page(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        entry_type: str | None = None,
        is_active: bool | None = None,
    ) -> Page[AllowlistEntry]:
        statement = select(AllowlistEntry)
        if entry_type is not None:
            statement = statement.where(AllowlistEntry.entry_type == entry_type)
        if is_active is not None:
            statement = statement.where(AllowlistEntry.is_active.is_(is_active))
        return await keyset_page(
            self.session,
            statement,
            scope="allowlist",
            sort_column=AllowlistEntry.created_at,
            id_column=AllowlistEntry.id,
            limit=limit,
            cursor=cursor,
        )


class ResponseActionRepository(BaseRepository[ResponseAction]):
    model = ResponseAction

    async def get_by_idempotency_key(self, key: str) -> ResponseAction | None:
        statement = select(ResponseAction).where(ResponseAction.idempotency_key == key)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_for_alert(self, alert_id: uuid.UUID) -> list[ResponseAction]:
        statement = (
            select(ResponseAction)
            .where(ResponseAction.alert_id == alert_id)
            .order_by(ResponseAction.requested_at.desc(), ResponseAction.id.desc())
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_pending(self, *, limit: int = 100, offset: int = 0) -> list[ResponseAction]:
        statement = (
            select(ResponseAction)
            .where(ResponseAction.status == "PENDING_APPROVAL")
            .order_by(ResponseAction.requested_at.asc(), ResponseAction.id.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def create(self, values: Mapping[str, Any]) -> ResponseAction:
        entity = ResponseAction(**dict(values))
        self.session.add(entity)
        await self.session.flush()
        return entity
