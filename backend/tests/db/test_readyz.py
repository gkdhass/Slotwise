"""``/readyz`` reports whether the deployed schema is at the Alembic head."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.config import Settings, reset_settings_cache
from app.services import health as health_module
from app.services.health import HealthService, expected_migration_heads

pytestmark = pytest.mark.db


async def _check(monkeypatch: pytest.MonkeyPatch | None = None):
    reset_settings_cache()
    settings = Settings()
    return await HealthService(settings).check_postgres()


async def test_readyz_reports_migrations_current(migrated_database) -> None:
    check = await _check()
    assert check.status == "ok"
    assert check.detail == "migrations_current"


async def test_expected_heads_come_from_checked_in_scripts(migrated_database) -> None:
    assert expected_migration_heads() == {"a13f5c9d2e01"}


async def test_readyz_reports_revision_mismatch(
    migrated_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        health_module, "expected_migration_heads", lambda: frozenset({"deadbeefdead"})
    )
    check = await _check()
    assert check.status == "error"
    assert check.detail == "migration_mismatch"


async def test_readyz_reports_missing_migration_state(migrated_database, migration_engine) -> None:
    async with migration_engine.begin() as connection:
        await connection.execute(
            text("ALTER TABLE alembic_version RENAME TO alembic_version_check")
        )
    try:
        check = await _check()
        assert check.status == "error"
        assert check.detail == "migration_state_missing"
    finally:
        async with migration_engine.begin() as connection:
            await connection.execute(
                text("ALTER TABLE alembic_version_check RENAME TO alembic_version")
            )
