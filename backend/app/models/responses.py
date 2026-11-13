"""Response policies, allow-list entries and simulated response actions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    AllowlistEntryType,
    ResponseActionStatus,
    ResponseActionType,
    sql_high_impact_values,
    sql_values,
)


class ResponsePolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable, versioned response policy.

    A policy is identified by ``(name, version)``. Changing the conditions or
    action creates a new row whose ``supersedes_id`` points at the previous
    version; the older rows are read-only (enforced by a database trigger in the
    Phase 3 migration, not only by the API). Only ``enabled`` may still be
    flipped, and only on the current version, so an incident responder can
    disable a rule without rewriting its history.
    """

    __tablename__ = "response_policies"
    __table_args__ = (
        CheckConstraint(
            f"action_type IN ({sql_values(ResponseActionType)})", name="action_allowed"
        ),
        CheckConstraint("length(name) > 0", name="name_present"),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("jsonb_typeof(conditions) = 'object'", name="conditions_object"),
        UniqueConstraint("name", "version", name="uq_response_policies_name_version"),
        Index("ix_response_policies_action_enabled", "action_type", "enabled"),
        Index("ix_response_policies_name_version", "name", "version"),
    )

    # Natural key (name, version) so versions can be seeded idempotently.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("response_policies.id", ondelete="RESTRICT")
    )
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    conditions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class AllowlistEntry(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "allowlist_entries"
    __table_args__ = (
        CheckConstraint(
            f"entry_type IN ({sql_values(AllowlistEntryType)})", name="entry_type_allowed"
        ),
        CheckConstraint("length(value) > 0", name="value_present"),
        # "Active" is an explicit flag instead of a predicate on expires_at:
        # PostgreSQL partial indexes cannot reference now(), and a stale
        # non-expiring row must not block a newly re-added protected value.
        Index(
            "ux_allowlist_entries_active_value",
            "entry_type",
            "value",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        Index("ix_allowlist_entries_lookup", "entry_type", "value"),
    )

    entry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ResponseAction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "response_actions"
    __table_args__ = (
        CheckConstraint(
            f"action_type IN ({sql_values(ResponseActionType)})", name="action_allowed"
        ),
        CheckConstraint(f"status IN ({sql_values(ResponseActionStatus)})", name="status_allowed"),
        CheckConstraint("length(target) > 0", name="target_present"),
        CheckConstraint("length(idempotency_key) > 0", name="idempotency_key_present"),
        # Approval and execution are distinct states. Nothing may enter the
        # execution half of the lifecycle without a recorded approver.
        CheckConstraint(
            "status NOT IN ('APPROVED', 'EXECUTING', 'SUCCEEDED', 'FAILED', 'ROLLED_BACK') "
            "OR approved_by IS NOT NULL",
            name="approved_states_require_approver",
        ),
        # Separation of duties for destructive actions, enforced independently
        # of the application feature flag.
        CheckConstraint(
            "approved_by IS NULL OR approved_by <> requested_by "
            f"OR action_type NOT IN ({sql_high_impact_values()})",
            name="high_impact_requires_independent_approver",
        ),
        CheckConstraint(
            "executed_at IS NULL OR executed_at >= requested_at", name="executed_after_requested"
        ),
        CheckConstraint(
            "status NOT IN ('SUCCEEDED', 'FAILED', 'ROLLED_BACK') OR executed_at IS NOT NULL",
            name="terminal_execution_requires_timestamp",
        ),
        Index("ix_response_actions_status_requested_at", "status", "requested_at"),
        Index("ix_response_actions_alert_id", "alert_id"),
        Index("ix_response_actions_incident_id", "incident_id"),
        Index("ix_response_actions_approved_by", "approved_by"),
    )

    alert_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("alerts.id", ondelete="RESTRICT"), nullable=False
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL")
    )
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("response_policies.id", ondelete="SET NULL")
    )
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=ResponseActionStatus.REQUESTED.value
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    rollback_ref: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
