"""Phase 4-1: Event envelope, migration, ingestion API, durable write path.

Revision ID: b4e7f8c9d3a2
Revises: a13f5c9d2e01
Create Date: 2026-11-14 10:00:00.000000

Additive only: event_outbox table, event status columns, sensor FK, import metadata.
Schema changes only; privileges managed separately in grant_app_permissions.py.
Migration is reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4e7f8c9d3a2"
down_revision: str | None = "a13f5c9d2e01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create event_outbox table
    op.create_table(
        "event_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_name", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SENT', 'FAILED')",
            name="status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name="fk_event_outbox_event_id_events",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_event_outbox"),
    )
    op.create_index(
        "ix_event_outbox_status_next_attempt_at",
        "event_outbox",
        ["status", "next_attempt_at"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )

    # Add columns to events table
    op.add_column(
        "events",
        sa.Column("status_reason", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "events",
        sa.Column("received_via", sa.String(length=20), nullable=False, server_default="api"),
    )
    op.add_column(
        "events",
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "events",
        sa.Column("imported_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "events",
        sa.Column("preprocessed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "events",
        sa.Column("feature_ref", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "events",
        sa.Column("feature_schema_version", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "events",
        sa.Column("search_indexed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Add foreign key constraints
    op.create_foreign_key(
        "fk_events_sensor_id_sensors",
        "events",
        "sensors",
        ["sensor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_events_imported_by_users",
        "events",
        "users",
        ["imported_by"],
        ["id"],
        ondelete="SET NULL",
    )

    # Add CHECK constraint for received_via
    op.execute("""
        ALTER TABLE events
        ADD CONSTRAINT ck_events_received_via_allowed
        CHECK (received_via IN ('api', 'import'))
    """)


def downgrade() -> None:
    # Remove CHECK constraints using raw SQL
    op.execute("""
        ALTER TABLE events
        DROP CONSTRAINT IF EXISTS ck_events_received_via_allowed
    """)

    # Remove foreign key constraints
    op.drop_constraint("fk_events_sensor_id_sensors", "events", type_="foreignkey")
    op.drop_constraint("fk_events_imported_by_users", "events", type_="foreignkey")

    # Remove columns from events table
    op.drop_column("events", "search_indexed_at")
    op.drop_column("events", "feature_schema_version")
    op.drop_column("events", "feature_ref")
    op.drop_column("events", "preprocessed_at")
    op.drop_column("events", "imported_by")
    op.drop_column("events", "sensor_id")
    op.drop_column("events", "received_via")
    op.drop_column("events", "status_reason")

    # Drop event_outbox table
    op.drop_index("ix_event_outbox_status_next_attempt_at", table_name="event_outbox")
    op.drop_table("event_outbox")
