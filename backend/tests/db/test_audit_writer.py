"""Audit writer: same-transaction atomicity and secret redaction."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.models.assets import Asset
from app.models.audit import AuditLog
from app.repositories.audit import AuditRepository

pytestmark = pytest.mark.db


def _asset(name: str) -> Asset:
    return Asset(
        name=name,
        asset_type="SERVER",
        criticality="HIGH",
        owner_team="test",
        environment="DEV",
        is_active=True,
    )


async def test_audit_row_commits_with_parent_change(session_factory) -> None:
    name = f"audit-asset-{uuid.uuid4().hex}"
    async with session_factory() as session:
        asset = _asset(name)
        session.add(asset)
        await session.flush()
        asset_id = asset.id
        await AuditRepository(session).record(
            actor_id=None,
            action="asset.create",
            entity_type="asset",
            entity_id=asset_id,
            after={"name": name, "is_active": True},
        )
        await session.commit()

    async with session_factory() as session:
        stored_asset = await session.get(Asset, asset_id)
        entry = await session.scalar(select(AuditLog).where(AuditLog.entity_id == asset_id))
        assert stored_asset is not None
        assert entry is not None
        assert entry.action == "asset.create"
        assert entry.after == {"name": name, "is_active": True}


async def test_audit_row_rolls_back_with_parent_change(session_factory) -> None:
    name = f"audit-rollback-{uuid.uuid4().hex}"
    async with session_factory() as session:
        asset = _asset(name)
        session.add(asset)
        await session.flush()
        await AuditRepository(session).record(
            actor_id=None,
            action="asset.create",
            entity_type="asset",
            entity_id=asset.id,
            after={"name": name},
        )
        await session.rollback()

    async with session_factory() as session:
        assert await session.scalar(select(Asset).where(Asset.name == name)) is None
        remaining = await session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.entity_id.is_not(None))
        )
        assert remaining == 0


async def test_audit_writer_redacts_sensitive_fields(session_factory) -> None:
    async with session_factory() as session:
        entry = await AuditRepository(session).record(
            actor_id=None,
            action="user.update",
            entity_type="user",
            entity_id=uuid.uuid4(),
            before={"email": "analyst@example.com", "password_hash": "$argon2id$secret"},
            after={
                "email": "analyst@example.com",
                "password": "hunter2",
                "nested": {"api_key": "sk-live-123", "safe": "value"},
                "token": "abc.def.ghi",
            },
            ip_address="203.0.113.7",
        )
        await session.flush()
        entry_id = entry.id
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(AuditLog, entry_id)
        assert stored is not None
        assert stored.before is not None and stored.after is not None
        assert stored.before["password_hash"] == "[REDACTED]"
        assert stored.before["email"] == "analyst@example.com"
        assert stored.after["password"] == "[REDACTED]"
        assert stored.after["token"] == "[REDACTED]"
        assert stored.after["nested"]["api_key"] == "[REDACTED]"
        assert stored.after["nested"]["safe"] == "value"
        assert str(stored.ip_address) == "203.0.113.7"


async def test_audit_writer_serializes_non_json_values(session_factory) -> None:
    entity_id = uuid.uuid4()
    moment = datetime.now(UTC)
    async with session_factory() as session:
        entry = await AuditRepository(session).record(
            actor_id=None,
            action="event.transition",
            entity_type="event",
            entity_id=entity_id,
            before={"id": entity_id, "observed_at": moment, "status": "RECEIVED"},
        )
        await session.flush()
        entry_id = entry.id
        await session.commit()

    async with session_factory() as session:
        stored = await session.get(AuditLog, entry_id)
        assert stored is not None and stored.before is not None
        assert stored.before["id"] == str(entity_id)
        assert stored.before["observed_at"] == moment.isoformat()
        assert stored.before["status"] == "RECEIVED"


async def test_audit_writer_accepts_null_snapshots(session_factory) -> None:
    async with session_factory() as session:
        entry = await AuditRepository(session).record(
            actor_id=None,
            action="system.start",
            entity_type="system",
            entity_id=None,
        )
        await session.flush()
        assert entry.before is None
        assert entry.after is None
