"""Migration lifecycle and model-drift checks.

These run against the real database and exercise the checked-in Alembic scripts
rather than ``Base.metadata.create_all``, so the upgrade/downgrade path is what
production actually executes.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import inspect, text

from app.models import Base

pytestmark = pytest.mark.db

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


EXPECTED_TABLES = frozenset(
    {
        "alembic_version",
        "alerts",
        "allowlist_entries",
        "assets",
        "audit_logs",
        "datasets",
        "event_labels",
        "events",
        "incident_alerts",
        "incident_comments",
        "incidents",
        "inference_results",
        "model_versions",
        "refresh_tokens",
        "response_actions",
        "response_policies",
        "roles",
        "sensors",
        "training_runs",
        "users",
    }
)


def _run_alembic(action: str, revision: str) -> None:
    config = alembic_config()
    getattr(command, action)(config, revision)


async def _table_names(engine) -> set[str]:
    async with engine.connect() as connection:
        return set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))


async def test_upgrade_downgrade_upgrade_cycle(migrated_database, migration_engine) -> None:
    assert await _table_names(migration_engine) == EXPECTED_TABLES

    await asyncio.to_thread(_run_alembic, "downgrade", "base")
    remaining = await _table_names(migration_engine)
    # Only Alembic's bookkeeping table survives a downgrade to base.
    assert remaining == {"alembic_version"}

    await asyncio.to_thread(_run_alembic, "upgrade", "head")
    assert await _table_names(migration_engine) == EXPECTED_TABLES


async def test_downgrade_folds_versioned_policies(migrated_database, migration_engine) -> None:
    """A committed policy history must not make the Phase 2 downgrade fail.

    Phase 3 keeps one row per ``(name, version)`` and forbids DELETE, so a
    downgrade has to fold the history itself before restoring the Phase 2
    ``uq_response_policies_name`` constraint.
    """
    import uuid as uuid_module

    name = f"migrator-version-{uuid_module.uuid4().hex[:8]}"
    async with migration_engine.begin() as connection:
        first_id = (
            await connection.execute(
                text(
                    "INSERT INTO response_policies "
                    "(name, version, action_type, requires_approval, conditions, enabled) "
                    "VALUES (:name, 1, 'BLOCK_IP', true, '{}', true) RETURNING id"
                ),
                {"name": name},
            )
        ).scalar_one()
        await connection.execute(
            text(
                "INSERT INTO response_policies "
                "(name, version, action_type, requires_approval, conditions, enabled, "
                "supersedes_id) "
                "VALUES (:name, 2, 'ISOLATE_HOST', true, '{}', true, :first_id)"
            ),
            {"name": name, "first_id": first_id},
        )

    # Stop at the Phase 2 revision: downgrading to base would drop the table and
    # hide whether the fold worked.
    await asyncio.to_thread(_run_alembic, "downgrade", "7c0f74402c2b")
    async with migration_engine.connect() as connection:
        names = (
            (
                await connection.execute(
                    text("SELECT name FROM response_policies WHERE name = :name"),
                    {"name": name},
                )
            )
            .scalars()
            .all()
        )
    assert names == [name]

    await asyncio.to_thread(_run_alembic, "upgrade", "head")
    async with migration_engine.connect() as connection:
        versions = (
            (
                await connection.execute(
                    text("SELECT version FROM response_policies WHERE name = :name"),
                    {"name": name},
                )
            )
            .scalars()
            .all()
        )
    assert versions == [1]


async def test_migration_head_matches_model_metadata(migrated_database, migration_engine) -> None:
    """The migration must produce exactly the schema the models declare."""
    async with migration_engine.connect() as connection:
        actual = set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))
    assert actual - {"alembic_version"} == set(Base.metadata.tables)


async def test_alembic_autogenerate_detects_no_drift(migrated_database) -> None:
    """``alembic check`` fails if the models and the migration disagree."""
    env = dict(os.environ)
    result = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", "check"],
        cwd=str(BACKEND_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 0, output
    assert "No new upgrade operations detected" in output


# Constraint and index names follow ``<kind>_<table>_<detail>``. SQLAlchemy's
# naming convention already prefixes them, so a migration that spells the
# prefix into the explicit name (``ck_users_ck_users_email``) produces a
# doubled name that still "works" but is impossible to read or target.
NAME_PREFIXES = ("ck_", "uq_", "fk_", "ix_")

_CONSTRAINT_NAME_SQL = """
SELECT c.relname AS table_name, con.conname AS name
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
UNION ALL
SELECT tablename AS table_name, indexname AS name
FROM pg_indexes
WHERE schemaname = 'public'
"""


def _has_doubled_prefix(table: str, name: str) -> bool:
    """Return True when a name repeats its kind prefix or its table name."""
    if name.count(f"{table}_") > 1:
        return True
    prefix = next((candidate for candidate in NAME_PREFIXES if name.startswith(candidate)), "")
    remainder = name[len(prefix) :]
    table_head = f"{table}_"
    if not remainder.startswith(table_head):
        return False
    detail = remainder[len(table_head) :]
    return any(detail.startswith(candidate) for candidate in NAME_PREFIXES)


def test_doubled_name_detector_recognises_regressions() -> None:
    """The detector must catch the bug it guards against, without false positives."""
    assert _has_doubled_prefix("users", "ck_users_ck_users_email")
    assert _has_doubled_prefix("users", "ix_users_ix_users_email")
    assert _has_doubled_prefix("users", "ck_users_ck_email")
    assert not _has_doubled_prefix("users", "ck_users_email")
    assert not _has_doubled_prefix("sensors", "ck_sensors_credential_prefix_format")
    assert not _has_doubled_prefix("incident_alerts", "fk_incident_alerts_alert_id_alerts")


async def test_constraint_and_index_names_are_not_doubled(
    migrated_database, migration_engine
) -> None:
    """No pg_constraint/pg_indexes name may repeat its prefix or table name."""
    async with migration_engine.connect() as connection:
        rows = (await connection.execute(text(_CONSTRAINT_NAME_SQL))).all()
    offenders = sorted({(table, name) for table, name in rows if _has_doubled_prefix(table, name)})
    assert offenders == [], f"doubled constraint/index names: {offenders}"
