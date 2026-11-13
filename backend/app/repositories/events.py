"""Event persistence, idempotent ingestion upsert and keyset feed queries."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

from sqlalchemy import literal_column, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import InstrumentedAttribute

from app.core.errors import BadRequestError
from app.models.events import Event, EventLabel
from app.repositories.base import BaseRepository
from app.repositories.pagination import (
    Page,
    decode_cursor,
    encode_cursor,
    validate_limit,
)

# Only these columns may drive ordering. Anything else is rejected instead of
# being interpolated into SQL.
EVENT_SORT_COLUMNS: Mapping[str, InstrumentedAttribute[datetime]] = {
    "observed_at": Event.observed_at,
    "received_at": Event.received_at,
    "created_at": Event.created_at,
}


class EventRepository(BaseRepository[Event]):
    model = Event

    async def get_by_source_external(self, source_id: str, external_id: str) -> Event | None:
        statement = select(Event).where(
            Event.source_id == source_id, Event.external_id == external_id
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def upsert(self, values: Mapping[str, Any]) -> tuple[Event, bool]:
        """Insert or update one event keyed by (source_id, external_id).

        Rows without an external_id are not de-duplicated because the source has
        not supplied an identity; the partial unique index only covers rows that
        do. Returns ``(event, created)``.
        """
        payload = dict(values)
        external_id = payload.get("external_id")
        if external_id is None:
            insert_statement = pg_insert(Event).values(**payload).returning(Event)
            result = await self.session.execute(insert_statement)
            return result.scalar_one(), True

        update_values = {
            key: value
            for key, value in payload.items()
            if key not in {"id", "source_id", "external_id", "created_at"}
        }
        statement: Any = (
            pg_insert(Event)
            .values(**payload)
            .on_conflict_do_update(
                index_elements=[Event.source_id, Event.external_id],
                index_where=text("external_id IS NOT NULL"),
                set_=update_values,
            )
            .returning(Event, literal_column("(xmax = 0)").label("inserted"))
        )
        result = await self.session.execute(
            statement, execution_options={"populate_existing": True}
        )
        row = result.one()
        return cast(Event, row[0]), bool(row[1])

    async def list_keyset(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        sort: str = "observed_at",
        asset_id: uuid.UUID | None = None,
        processing_status: str | None = None,
        source_id: str | None = None,
        event_type: str | None = None,
        observed_from: datetime | None = None,
        observed_to: datetime | None = None,
    ) -> Page[Event]:
        limit = validate_limit(limit)
        sort_column = EVENT_SORT_COLUMNS.get(sort)
        if sort_column is None:
            raise BadRequestError(
                "Unsupported event sort column.",
                details={"allowed": sorted(EVENT_SORT_COLUMNS)},
            )

        statement = select(Event)
        if asset_id is not None:
            statement = statement.where(Event.asset_id == asset_id)
        if processing_status is not None:
            statement = statement.where(Event.processing_status == processing_status)
        if source_id is not None:
            statement = statement.where(Event.source_id == source_id)
        if event_type is not None:
            statement = statement.where(Event.event_type == event_type)
        if observed_from is not None:
            statement = statement.where(Event.observed_at >= observed_from)
        if observed_to is not None:
            statement = statement.where(Event.observed_at <= observed_to)

        decoded = decode_cursor(cursor)
        if decoded is not None:
            if decoded.get("s") != sort:
                raise BadRequestError("The pagination cursor does not match the requested sort.")
            try:
                sort_value = datetime.fromisoformat(str(decoded["v"]))
                last_id = uuid.UUID(str(decoded["id"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise BadRequestError("The pagination cursor is invalid.") from exc
            statement = statement.where(tuple_(sort_column, Event.id) < (sort_value, last_id))

        statement = statement.order_by(sort_column.desc(), Event.id.desc()).limit(limit)
        result = await self.session.execute(statement)
        items = list(result.scalars().all())

        next_cursor: str | None = None
        if len(items) == limit:
            last = items[-1]
            next_cursor = encode_cursor(
                {
                    "s": sort,
                    "v": getattr(last, sort).isoformat(),
                    "id": str(last.id),
                }
            )
        return Page(items=items, next_cursor=next_cursor)

    async def count_by_status(self) -> dict[str, int]:
        from sqlalchemy import func

        statement = select(Event.processing_status, func.count()).group_by(Event.processing_status)
        result = await self.session.execute(statement)
        return {str(row[0]): int(row[1]) for row in result}


class EventLabelRepository(BaseRepository[EventLabel]):
    model = EventLabel

    async def get_for_event(self, event_id: uuid.UUID, label: str) -> EventLabel | None:
        statement = select(EventLabel).where(
            EventLabel.event_id == event_id, EventLabel.label == label
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def create(self, values: Mapping[str, Any]) -> EventLabel:
        entity = EventLabel(**dict(values))
        self.session.add(entity)
        await self.session.flush()
        return entity
