"""Append-only audit log, enforced by the database rather than by callers."""

from __future__ import annotations

import pytest
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models.audit import AuditLog

pytestmark = pytest.mark.db


async def _insert_as(engine: AsyncEngine, action: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            insert(AuditLog.__table__).values(action=action, entity_type="event", entity_id=None)
        )


async def test_application_role_can_insert_audit_rows(db_session: AsyncSession) -> None:
    entry = AuditLog(action="test.insert", entity_type="event", entity_id=None)
    db_session.add(entry)
    await db_session.flush()
    assert entry.id is not None
    count = await db_session.scalar(select(func.count()).select_from(AuditLog))
    assert count == 1


async def test_application_role_privileges_are_revoked(db_session: AsyncSession) -> None:
    rows = await db_session.execute(
        text(
            "SELECT has_table_privilege(current_user, 'audit_logs', 'INSERT'),"
            " has_table_privilege(current_user, 'audit_logs', 'UPDATE'),"
            " has_table_privilege(current_user, 'audit_logs', 'DELETE'),"
            " has_table_privilege(current_user, 'audit_logs', 'TRUNCATE')"
        )
    )
    can_insert, can_update, can_delete, can_truncate = rows.one()
    assert can_insert is True
    assert can_update is False
    assert can_delete is False
    assert can_truncate is False


async def test_application_role_cannot_update_audit_rows(db_session: AsyncSession) -> None:
    entry = AuditLog(action="test.update", entity_type="event", entity_id=None)
    db_session.add(entry)
    await db_session.flush()
    entry_id = entry.id
    await db_session.commit()

    with pytest.raises(DBAPIError) as raised:
        await db_session.execute(
            update(AuditLog).where(AuditLog.id == entry_id).values(action="tampered")
        )
    await db_session.rollback()
    assert _sqlstate(raised.value) in {"42501", "P0001"}
    stored = await db_session.scalar(select(AuditLog.action).where(AuditLog.id == entry_id))
    assert stored == "test.update"


async def test_application_role_cannot_delete_audit_rows(db_session: AsyncSession) -> None:
    entry = AuditLog(action="test.delete", entity_type="event", entity_id=None)
    db_session.add(entry)
    await db_session.flush()
    await db_session.commit()

    with pytest.raises(DBAPIError) as raised:
        await db_session.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": entry.id})
    await db_session.rollback()
    assert _sqlstate(raised.value) in {"42501", "P0001"}


async def test_application_role_cannot_truncate_audit_rows(db_session: AsyncSession) -> None:
    with pytest.raises(DBAPIError) as raised:
        await db_session.execute(text("TRUNCATE audit_logs"))
    await db_session.rollback()
    assert _sqlstate(raised.value) in {"42501", "P0001"}


@pytest.mark.parametrize(
    ("statement", "expected_fragment"),
    [
        ("UPDATE audit_logs SET action = 'tampered' WHERE id = :id", "append-only"),
        ("DELETE FROM audit_logs WHERE id = :id", "append-only"),
    ],
)
async def test_owner_is_blocked_by_the_trigger(
    migration_engine: AsyncEngine, statement: str, expected_fragment: str
) -> None:
    """The table owner (migration role) still cannot rewrite history."""
    async with migration_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            result = await connection.execute(
                insert(AuditLog.__table__)
                .values(action="owner.test", entity_type="event")
                .returning(AuditLog.id)
            )
            audit_id = result.scalar_one()
            with pytest.raises(DBAPIError) as raised:
                await connection.execute(text(statement), {"id": audit_id})
            assert expected_fragment in str(raised.value)
            await transaction.rollback()
        finally:
            if transaction.is_active:
                await transaction.rollback()


async def test_owner_cannot_truncate_even_an_empty_table(migration_engine: AsyncEngine) -> None:
    async with migration_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            with pytest.raises(DBAPIError) as raised:
                await connection.execute(text("TRUNCATE audit_logs"))
            assert "append-only" in str(raised.value)
            await transaction.rollback()
        finally:
            if transaction.is_active:
                await transaction.rollback()


def _sqlstate(error: DBAPIError) -> str:
    return str(getattr(error.orig, "sqlstate", "") or "")
