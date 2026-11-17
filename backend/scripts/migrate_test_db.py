#!/usr/bin/env python
"""Migrate test database using alembic programmatically."""

from alembic import command
from alembic.config import Config


def migrate():
    """Run alembic upgrade head."""
    alembic_cfg = Config("alembic.ini")
    # Override URL to use localhost
    alembic_cfg.set_main_option(
        "sqlalchemy.url",
        "postgresql+asyncpg://slotwise_migrator:slotwise_migrator@localhost:5432/slotwise_test?ssl=false"
    )
    command.upgrade(alembic_cfg, "head")
    print("✓ Migration complete")

if __name__ == "__main__":
    migrate()
