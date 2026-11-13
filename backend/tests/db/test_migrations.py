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
from sqlalchemy import inspect

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
