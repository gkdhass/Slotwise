"""Normalized events and analyst/ML labels."""

from __future__ import annotations

import uuid
from datetime import datetime

# Forward references for relationships
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import EventStatus, EventType, SourceType, sql_values

if TYPE_CHECKING:
    from app.models.assets import Sensor
    from app.models.identity import User


class Event(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(f"source_type IN ({sql_values(SourceType)})", name="source_type_allowed"),
        CheckConstraint(f"event_type IN ({sql_values(EventType)})", name="event_type_allowed"),
        CheckConstraint(
            f"processing_status IN ({sql_values(EventStatus)})", name="processing_status_allowed"
        ),
        CheckConstraint("length(source_id) > 0", name="source_id_present"),
        CheckConstraint("length(raw_ref) > 0", name="raw_ref_present"),
        CheckConstraint(
            "raw_checksum ~ '^[0-9a-f]{64}$'",
            name="raw_checksum_sha256",
        ),
        CheckConstraint("length(schema_version) > 0", name="schema_version_present"),
        CheckConstraint("received_via IN ('api', 'import')", name="received_via_allowed"),
        # Ingestion may legitimately omit external_id (e.g. uploads). Only rows
        # that claim a source identity are subject to duplicate protection.
        Index(
            "ux_events_source_external",
            "source_id",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        # Keyset pagination order: newest first, id as the tie-breaker.
        Index("ix_events_observed_at_id", "observed_at", "id"),
        Index("ix_events_asset_id_observed_at", "asset_id", "observed_at"),
        Index("ix_events_processing_status_observed_at", "processing_status", "observed_at"),
    )

    external_id: Mapped[str | None] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Pointer to the immutable raw object in OpenSearch/S3. The checksum makes
    # tampering detectable without loading the object.
    raw_ref: Mapped[str] = mapped_column(Text, nullable=False)
    raw_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")
    processing_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=EventStatus.RECEIVED.value
    )
    status_reason: Mapped[str | None] = mapped_column(String(500))
    received_via: Mapped[str] = mapped_column(String(20), nullable=False, default="api")
    sensor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sensors.id", ondelete="SET NULL"),
    )
    imported_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    preprocessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feature_ref: Mapped[str | None] = mapped_column(String(500))
    feature_schema_version: Mapped[str | None] = mapped_column(String(16))
    search_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    labels: Mapped[list[EventLabel]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    sensor: Mapped[Sensor | None] = relationship("Sensor")
    imported_by_user: Mapped[User | None] = relationship("User")


class EventOutbox(CreatedAtMixin, Base):
    __tablename__ = "event_outbox"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint("status IN ('PENDING', 'SENT', 'FAILED')", name="status_allowed"),
        Index(
            "ix_event_outbox_status_next_attempt_at",
            "status",
            "next_attempt_at",
            postgresql_where=text("status = 'PENDING'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_name: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    event: Mapped[Event] = relationship("Event")


class EventLabel(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "event_labels"
    __table_args__ = (
        CheckConstraint("length(label) BETWEEN 1 AND 200", name="label_length"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        CheckConstraint("source IN ('ANALYST', 'ML', 'SENSOR_SUPPLIED')", name="source_allowed"),
        # One label value per event; the source records who supplied it.
        Index("ux_event_labels_event_label", "event_id", "label", unique=True),
        Index("ix_event_labels_label", "label"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="ANALYST")
    confidence: Mapped[float | None] = mapped_column(Float)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    event: Mapped[Event] = relationship(back_populates="labels")
