"""Normalized events and analyst/ML labels."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
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

    labels: Mapped[list[EventLabel]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class EventLabel(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "event_labels"
    __table_args__ = (
        CheckConstraint("length(label) BETWEEN 1 AND 200", name="label_length"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
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
