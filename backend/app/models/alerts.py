"""Alerts, incidents, their association rows and analyst comments."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AlertStatus, IncidentStatus, Severity, sql_values


class Alert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(f"severity IN ({sql_values(Severity)})", name="severity_allowed"),
        CheckConstraint(f"status IN ({sql_values(AlertStatus)})", name="status_allowed"),
        CheckConstraint("length(category) > 0", name="category_present"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint(
            "status <> 'ASSIGNED' OR assigned_to IS NOT NULL",
            name="assigned_requires_owner",
        ),
        CheckConstraint(
            "status <> 'SUPPRESSED' OR suppression_reason IS NOT NULL",
            name="suppressed_requires_reason",
        ),
        # One alert per inference result: retries can then be idempotent.
        Index("ux_alerts_inference_result_id", "inference_result_id", unique=True),
        Index("ix_alerts_severity", "severity"),
        Index("ix_alerts_status", "status"),
        Index("ix_alerts_created_at_id", "created_at", "id"),
        Index("ix_alerts_assigned_to", "assigned_to"),
        Index("ix_alerts_asset_id", "asset_id"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("events.id", ondelete="RESTRICT"), nullable=False
    )
    inference_result_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inference_results.id", ondelete="RESTRICT"),
        nullable=False,
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL")
    )
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=AlertStatus.NEW.value)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    # Additive Phase 1 approvals: record which severity policy scored the alert
    # and whether an analyst must review it before closure.
    severity_policy_version: Mapped[str | None] = mapped_column(String(64))
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    suppression_reason: Mapped[str | None] = mapped_column(Text)
    suppressed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Incident(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(f"severity IN ({sql_values(Severity)})", name="severity_allowed"),
        CheckConstraint(f"status IN ({sql_values(IncidentStatus)})", name="status_allowed"),
        CheckConstraint("length(title) > 0", name="title_present"),
        CheckConstraint(
            "status NOT IN ('RESOLVED', 'CLOSED') OR resolved_at IS NOT NULL",
            name="closed_requires_resolved_at",
        ),
        CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= opened_at", name="resolved_after_opened"
        ),
        Index("ix_incidents_status_opened_at", "status", "opened_at"),
        Index("ix_incidents_severity", "severity"),
        Index("ix_incidents_owner_id", "owner_id"),
        Index("ix_incidents_title", "title"),
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=IncidentStatus.OPEN.value
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)


class IncidentAlert(Base):
    __tablename__ = "incident_alerts"
    __table_args__ = (Index("ix_incident_alerts_alert_id", "alert_id"),)

    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IncidentComment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "incident_comments"
    __table_args__ = (
        CheckConstraint("length(body) BETWEEN 1 AND 10000", name="body_length"),
        Index("ix_incident_comments_incident_created_at", "incident_id", "created_at"),
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
