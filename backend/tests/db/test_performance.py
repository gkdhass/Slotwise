"""Performance sanity: the key list queries use their indexes at 100k events.

The test inserts synthetic events, runs ``EXPLAIN (FORMAT JSON)`` and asserts the
expected index name appears in the plan. Plans are printed so the numbers can be
reported. All synthetic rows are removed afterwards.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import DateTime, bindparam, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models.events import Event

pytestmark = pytest.mark.db

EVENT_COUNT = 100_000
SOURCE_ID = "perf-seed"
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _rows(asset_id: uuid.UUID) -> list[dict[str, object]]:
    return [
        {
            "external_id": f"perf-{index:06d}",
            "source_type": "UPLOAD",
            "source_id": SOURCE_ID,
            "asset_id": asset_id if index % 20 == 0 else None,
            "observed_at": BASE + timedelta(seconds=index),
            "event_type": "NETWORK_FLOW",
            "raw_ref": f"s3://test/perf/{index}.json",
            "raw_checksum": hashlib.sha256(str(index).encode()).hexdigest(),
            "schema_version": "1.0",
            "processing_status": "RECEIVED" if index % 20 == 0 else "PROCESSED",
        }
        for index in range(EVENT_COUNT)
    ]


async def _explain(
    engine: AsyncEngine,
    label: str,
    body: str,
    params: dict[str, Any],
    binds: tuple[Any, ...],
) -> str:
    async with engine.connect() as connection:
        statement = text(f"EXPLAIN (FORMAT JSON) {body}").bindparams(*binds)
        result = await connection.execute(statement, params)
        plan = result.scalar()
    rendered = json.dumps(plan, default=str)
    print(f"\n[{label}]\n{rendered}")  # noqa: T201 - EXPLAIN plans are reported
    return rendered


async def test_key_queries_use_indexes_at_100k_events(migration_engine: AsyncEngine) -> None:
    asset_id = uuid.uuid4()
    asset_name = f"perf-asset-{asset_id.hex}"

    async with migration_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO assets (id, name, asset_type, criticality, owner_team,"
                " environment, is_active) VALUES"
                " (:id, :name, 'SERVER', 'HIGH', 'perf', 'DEV', true)"
            ),
            {"id": asset_id, "name": asset_name},
        )

    try:
        rows = _rows(asset_id)
        # Chunked executemany keeps memory bounded and mirrors batch ingestion.
        async with migration_engine.begin() as connection:
            for start in range(0, EVENT_COUNT, 10_000):
                await connection.execute(Event.__table__.insert(), rows[start : start + 10_000])
            await connection.execute(text("ANALYZE events"))

        keyset = await _explain(
            migration_engine,
            "keyset order",
            "SELECT * FROM events ORDER BY observed_at DESC, id DESC LIMIT 50",
            {},
            (),
        )
        assert "ix_events_observed_at_id" in keyset

        status_page = await _explain(
            migration_engine,
            "status filter",
            "SELECT * FROM events WHERE processing_status = :status "
            "ORDER BY observed_at DESC, id DESC LIMIT 50",
            {"status": "RECEIVED"},
            (),
        )
        assert "ix_events_processing_status_observed_at" in status_page

        asset_page = await _explain(
            migration_engine,
            "asset filter",
            "SELECT * FROM events WHERE asset_id = :asset_id AND observed_at >= :since "
            "ORDER BY observed_at DESC, id DESC LIMIT 50",
            {"asset_id": asset_id, "since": BASE},
            (),
        )
        assert "ix_events_asset_id_observed_at" in asset_page

        after_cursor = await _explain(
            migration_engine,
            "keyset cursor predicate",
            "SELECT * FROM events WHERE (observed_at, id) < (:observed_at, :last_id) "
            "ORDER BY observed_at DESC, id DESC LIMIT 50",
            {"observed_at": BASE + timedelta(seconds=50_000), "last_id": uuid.uuid4()},
            (
                bindparam("observed_at", type_=DateTime(timezone=True)),
                bindparam("last_id", type_=PGUUID(as_uuid=True)),
            ),
        )
        assert "ix_events_observed_at_id" in after_cursor
    finally:
        # Keep the shared test database clean for the rest of the suite.
        async with migration_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM events WHERE source_id = :source"), {"source": SOURCE_ID}
            )
            await connection.execute(text("DELETE FROM assets WHERE id = :id"), {"id": asset_id})
            await connection.execute(text("ANALYZE events"))
