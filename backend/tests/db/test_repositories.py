"""Repository behaviour against real PostgreSQL.

Covers idempotent upserts, keyset pagination stability, whitelisted sorts and
the unit-of-work wiring. Repositories contain no business/policy logic.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError
from app.models.alerts import Alert
from app.models.assets import Asset
from app.models.events import Event
from app.repositories.alerts import AlertRepository
from app.repositories.events import EventRepository
from app.repositories.unit_of_work import UnitOfWork
from tests.db.factories import (
    make_alert,
    make_event,
    make_inference,
    make_model,
)

pytestmark = pytest.mark.db

BASE = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _event_values(index: int, *, source_id: str = "sensor-repo") -> dict[str, object]:
    return {
        "external_id": f"evt-{index}",
        "source_type": "UPLOAD",
        "source_id": source_id,
        "observed_at": BASE + timedelta(minutes=index),
        "event_type": "NETWORK_FLOW",
        "raw_ref": f"s3://test/events/{index}.json",
        "raw_checksum": hashlib.sha256(str(index).encode()).hexdigest(),
        "schema_version": "1.0",
        "processing_status": "RECEIVED",
    }


async def test_event_upsert_is_idempotent(db_session: AsyncSession) -> None:
    repository = EventRepository(db_session)
    event, created = await repository.upsert(_event_values(1))
    assert created is True

    updated = _event_values(1)
    updated["processing_status"] = "PROCESSED"
    same_event, created_again = await repository.upsert(updated)
    assert created_again is False
    assert same_event.id == event.id
    assert same_event.processing_status == "PROCESSED"
    assert await repository.count() == 1


async def test_event_upsert_without_external_id_always_inserts(db_session: AsyncSession) -> None:
    repository = EventRepository(db_session)
    values = _event_values(1)
    values["external_id"] = None
    await repository.upsert(values)
    await repository.upsert(values)
    assert await repository.count() == 2


async def test_alert_upsert_is_idempotent(db_session: AsyncSession) -> None:
    event = await make_event(db_session)
    model = await make_model(db_session)
    inference = await make_inference(db_session, event=event, model=model)
    repository = AlertRepository(db_session)

    payload = {
        "event_id": event.id,
        "inference_result_id": inference.id,
        "category": "initial",
        "severity": "HIGH",
        "confidence": 0.9,
        "status": "NEW",
    }
    alert, created = await repository.upsert(payload)
    assert created is True

    payload["category"] = "updated"
    same_alert, created_again = await repository.upsert(payload)
    assert created_again is False
    assert same_alert.id == alert.id
    assert same_alert.category == "updated"
    assert await repository.count() == 1


async def test_event_keyset_pagination_is_stable_under_inserts(db_session: AsyncSession) -> None:
    repository = EventRepository(db_session)
    for index in range(10):
        await repository.upsert(_event_values(index))

    first = await repository.list_keyset(limit=4, sort="observed_at")
    assert [item.external_id for item in first.items] == ["evt-9", "evt-8", "evt-7", "evt-6"]
    assert first.next_cursor is not None

    # Newer events arrive between page requests and must not disturb page two.
    for index in range(10, 15):
        await repository.upsert(_event_values(index))

    second = await repository.list_keyset(limit=4, sort="observed_at", cursor=first.next_cursor)
    assert [item.external_id for item in second.items] == ["evt-5", "evt-4", "evt-3", "evt-2"]

    third = await repository.list_keyset(limit=4, sort="observed_at", cursor=second.next_cursor)
    assert [item.external_id for item in third.items] == ["evt-1", "evt-0"]
    assert third.next_cursor is None

    seen = {item.id for item in first.items + second.items + third.items}
    assert len(seen) == 10


async def test_event_keyset_cursor_binds_sort_and_id(db_session: AsyncSession) -> None:
    repository = EventRepository(db_session)
    for index in range(3):
        await repository.upsert(_event_values(index))
    page = await repository.list_keyset(limit=2, sort="observed_at")
    assert page.items[0].external_id == "evt-2"
    # A cursor produced for one sort cannot be replayed against another.
    with pytest.raises(BadRequestError):
        await repository.list_keyset(limit=2, sort="received_at", cursor=page.next_cursor)


async def test_event_sort_whitelist_rejects_unknown_columns(db_session: AsyncSession) -> None:
    repository = EventRepository(db_session)
    with pytest.raises(BadRequestError):
        await repository.list_keyset(sort="observed_at; DROP TABLE events")
    with pytest.raises(BadRequestError):
        await repository.list_keyset(sort="normalized_payload")


async def test_invalid_cursor_is_rejected(db_session: AsyncSession) -> None:
    repository = EventRepository(db_session)
    with pytest.raises(BadRequestError):
        await repository.list_keyset(cursor="!!!not-a-cursor!!!")


async def test_filter_values_are_parameterized(db_session: AsyncSession) -> None:
    repository = EventRepository(db_session)
    await repository.upsert(_event_values(1))
    page = await repository.list_keyset(source_id="x' OR 1=1 --")
    assert page.items == []
    # The table is still there, so the payload was treated as data.
    assert await repository.count() == 1


async def test_alert_keyset_pagination_is_stable(db_session: AsyncSession) -> None:
    event = await make_event(db_session)
    model = await make_model(db_session)
    alerts: list[Alert] = []
    for index in range(7):
        inference = await make_inference(
            db_session, event=event, model=model, predicted_class=f"class-{index}"
        )
        alert = await make_alert(db_session, event=event, inference=inference)
        alert.created_at = BASE + timedelta(minutes=index)
        alerts.append(alert)
    await db_session.flush()

    repository = AlertRepository(db_session)
    first = await repository.list_keyset(limit=3)
    assert [item.created_at for item in first.items] == [
        BASE + timedelta(minutes=6),
        BASE + timedelta(minutes=5),
        BASE + timedelta(minutes=4),
    ]
    second = await repository.list_keyset(limit=3, cursor=first.next_cursor)
    assert [item.created_at for item in second.items] == [
        BASE + timedelta(minutes=3),
        BASE + timedelta(minutes=2),
        BASE + timedelta(minutes=1),
    ]
    third = await repository.list_keyset(limit=3, cursor=second.next_cursor)
    assert [item.created_at for item in third.items] == [BASE]
    assert third.next_cursor is None


async def test_alert_sort_whitelist_rejects_unknown_columns(db_session: AsyncSession) -> None:
    repository = AlertRepository(db_session)
    with pytest.raises(BadRequestError):
        await repository.list_keyset(sort="confidence")


async def test_alert_keyset_filters_by_status_and_severity(db_session: AsyncSession) -> None:
    event = await make_event(db_session)
    model = await make_model(db_session)
    inference_a = await make_inference(db_session, event=event, model=model, predicted_class="a")
    inference_b = await make_inference(db_session, event=event, model=model, predicted_class="b")
    await make_alert(db_session, event=event, inference=inference_a, status="NEW", severity="HIGH")
    await make_alert(
        db_session, event=event, inference=inference_b, status="ACKNOWLEDGED", severity="LOW"
    )

    repository = AlertRepository(db_session)
    page = await repository.list_keyset(status="ACKNOWLEDGED", severity="LOW")
    assert len(page.items) == 1
    assert page.items[0].status == "ACKNOWLEDGED"


async def test_unit_of_work_commits_and_reuses_repositories(session_factory) -> None:
    name = f"uow-asset-{uuid.uuid4().hex}"
    async with UnitOfWork(session_factory) as uow:
        uow.assets.add(
            Asset(
                name=name,
                asset_type="SERVER",
                criticality="HIGH",
                owner_team="test",
                environment="DEV",
                is_active=True,
            )
        )
        await uow.commit()

    async with UnitOfWork(session_factory) as uow:
        found = await uow.assets.get_by_name(name)
        assert found is not None
        assert found.name == name


async def test_unit_of_work_rolls_back_unless_committed(session_factory) -> None:
    name = f"uow-rollback-{uuid.uuid4().hex}"
    async with UnitOfWork(session_factory) as uow:
        uow.assets.add(
            Asset(
                name=name,
                asset_type="SERVER",
                criticality="LOW",
                owner_team="test",
                environment="DEV",
                is_active=True,
            )
        )
        # No commit on purpose.

    async with UnitOfWork(session_factory) as uow:
        assert await uow.assets.get_by_name(name) is None


async def test_repository_get_returns_none_for_unknown_id(db_session: AsyncSession) -> None:
    repository = EventRepository(db_session)
    assert await repository.get(uuid.uuid4()) is None


async def test_offset_pagination_is_deterministic(db_session: AsyncSession) -> None:
    repository = EventRepository(db_session)
    for index in range(5):
        await repository.upsert(_event_values(index))
    first = await repository.list_offset(limit=2, offset=0)
    second = await repository.list_offset(limit=2, offset=2)
    assert {item.id for item in first}.isdisjoint({item.id for item in second})
    assert len(await repository.list_offset(limit=10, offset=0)) == 5
    assert await db_session.scalar(select(Event.id).limit(1)) is not None
