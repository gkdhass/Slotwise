"""Alert triage, incident grouping and comment repositories."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

from sqlalchemy import literal_column, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.errors import BadRequestError
from app.models.alerts import Alert, Incident, IncidentAlert, IncidentComment
from app.repositories.base import BaseRepository
from app.repositories.pagination import (
    Page,
    decode_cursor,
    encode_cursor,
    validate_limit,
)

ALERT_SORT_COLUMNS: Mapping[str, InstrumentedAttribute[datetime]] = {
    "created_at": Alert.created_at,
    "updated_at": Alert.updated_at,
}


class AlertRepository(BaseRepository[Alert]):
    model = Alert

    async def get_by_inference_result(self, inference_result_id: uuid.UUID) -> Alert | None:
        statement = select(Alert).where(Alert.inference_result_id == inference_result_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def upsert(self, values: Mapping[str, Any]) -> tuple[Alert, bool]:
        payload = dict(values)
        update_values = {
            key: value
            for key, value in payload.items()
            if key not in {"id", "inference_result_id", "created_at"}
        }
        statement: Any = (
            pg_insert(Alert)
            .values(**payload)
            .on_conflict_do_update(
                index_elements=[Alert.inference_result_id],
                set_=update_values,
            )
            .returning(Alert, literal_column("(xmax = 0)").label("inserted"))
        )
        result = await self.session.execute(
            statement, execution_options={"populate_existing": True}
        )
        row = result.one()
        return cast(Alert, row[0]), bool(row[1])

    async def list_keyset(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        sort: str = "created_at",
        severity: str | None = None,
        status: str | None = None,
        assigned_to: uuid.UUID | None = None,
        asset_id: uuid.UUID | None = None,
        category: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> Page[Alert]:
        limit = validate_limit(limit)
        sort_column = ALERT_SORT_COLUMNS.get(sort)
        if sort_column is None:
            raise BadRequestError(
                "Unsupported alert sort column.",
                details={"allowed": sorted(ALERT_SORT_COLUMNS)},
            )

        statement = select(Alert)
        if severity is not None:
            statement = statement.where(Alert.severity == severity)
        if status is not None:
            statement = statement.where(Alert.status == status)
        if assigned_to is not None:
            statement = statement.where(Alert.assigned_to == assigned_to)
        if asset_id is not None:
            statement = statement.where(Alert.asset_id == asset_id)
        if category is not None:
            statement = statement.where(Alert.category == category)
        if created_from is not None:
            statement = statement.where(Alert.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(Alert.created_at <= created_to)

        decoded = decode_cursor(cursor)
        if decoded is not None:
            if decoded.get("s") != sort:
                raise BadRequestError("The pagination cursor does not match the requested sort.")
            try:
                sort_value = datetime.fromisoformat(str(decoded["v"]))
                last_id = uuid.UUID(str(decoded["id"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise BadRequestError("The pagination cursor is invalid.") from exc
            statement = statement.where(tuple_(sort_column, Alert.id) < (sort_value, last_id))

        statement = statement.order_by(sort_column.desc(), Alert.id.desc()).limit(limit)
        result = await self.session.execute(statement)
        items = list(result.scalars().all())

        next_cursor: str | None = None
        if len(items) == limit:
            last = items[-1]
            next_cursor = encode_cursor(
                {"s": sort, "v": getattr(last, sort).isoformat(), "id": str(last.id)}
            )
        return Page(items=items, next_cursor=next_cursor)


class IncidentRepository(BaseRepository[Incident]):
    model = Incident

    async def get_by_title(self, title: str) -> Incident | None:
        statement = (
            select(Incident).where(Incident.title == title).order_by(Incident.opened_at.asc())
        )
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def list_filtered(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
        severity: str | None = None,
        owner_id: uuid.UUID | None = None,
    ) -> list[Incident]:
        statement = select(Incident)
        if status is not None:
            statement = statement.where(Incident.status == status)
        if severity is not None:
            statement = statement.where(Incident.severity == severity)
        if owner_id is not None:
            statement = statement.where(Incident.owner_id == owner_id)
        statement = (
            statement.order_by(Incident.opened_at.desc(), Incident.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())


class IncidentAlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def link(self, incident_id: uuid.UUID, alert_id: uuid.UUID) -> bool:
        statement = (
            pg_insert(IncidentAlert)
            .values(incident_id=incident_id, alert_id=alert_id)
            .on_conflict_do_nothing(
                index_elements=[IncidentAlert.incident_id, IncidentAlert.alert_id]
            )
            .returning(IncidentAlert.alert_id)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def unlink(self, incident_id: uuid.UUID, alert_id: uuid.UUID) -> None:
        row = await self.session.get(IncidentAlert, (incident_id, alert_id))
        if row is not None:
            await self.session.delete(row)

    async def list_for_incident(self, incident_id: uuid.UUID) -> list[uuid.UUID]:
        statement = select(IncidentAlert.alert_id).where(IncidentAlert.incident_id == incident_id)
        result = await self.session.execute(statement)
        return [row[0] for row in result]


class IncidentCommentRepository(BaseRepository[IncidentComment]):
    model = IncidentComment

    async def find_by_body(self, incident_id: uuid.UUID, body: str) -> IncidentComment | None:
        statement = select(IncidentComment).where(
            IncidentComment.incident_id == incident_id, IncidentComment.body == body
        )
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def create(self, values: Mapping[str, Any]) -> IncidentComment:
        entity = IncidentComment(**dict(values))
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def list_for_incident(
        self, incident_id: uuid.UUID, *, limit: int = 100, offset: int = 0
    ) -> list[IncidentComment]:
        statement = (
            select(IncidentComment)
            .where(IncidentComment.incident_id == incident_id)
            .order_by(IncidentComment.created_at.asc(), IncidentComment.id.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
