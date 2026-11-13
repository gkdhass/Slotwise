"""Dataset provenance and training-run lineage."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DatasetStatus, Pipeline, TrainingRunStatus, sql_values


class Dataset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_values(DatasetStatus)})", name="status_allowed"),
        CheckConstraint("length(name) > 0", name="name_present"),
        CheckConstraint("length(source) > 0", name="source_present"),
        CheckConstraint("length(licence) > 0", name="licence_present"),
        CheckConstraint("checksum IS NULL OR checksum ~ '^[0-9a-f]{64}$'", name="checksum_sha256"),
        CheckConstraint(
            "status NOT IN ('VALIDATED', 'ACTIVE') OR "
            "(object_uri IS NOT NULL AND checksum IS NOT NULL)",
            name="validated_requires_object_and_checksum",
        ),
        CheckConstraint("jsonb_typeof(label_schema) = 'object'", name="label_schema_object"),
        # Provenance identity for idempotent seeding and catalogue lookups.
        Index("ux_datasets_name", "name", unique=True),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    modality: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    licence: Mapped[str] = mapped_column(Text, nullable=False)
    object_uri: Mapped[str | None] = mapped_column(Text)
    checksum: Mapped[str | None] = mapped_column(String(64))
    label_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DatasetStatus.REGISTERED.value
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class TrainingRun(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "training_runs"
    __table_args__ = (
        UniqueConstraint("mlflow_run_id", name="uq_training_runs_mlflow_run_id"),
        CheckConstraint(f"pipeline IN ({sql_values(Pipeline)})", name="pipeline_allowed"),
        CheckConstraint(f"status IN ({sql_values(TrainingRunStatus)})", name="status_allowed"),
        CheckConstraint("length(base_model) > 0", name="base_model_present"),
        CheckConstraint(
            "hyperparameters IS NOT NULL AND jsonb_typeof(hyperparameters) = 'object'",
            name="hyperparameters_object",
        ),
        CheckConstraint(
            "started_at IS NULL OR completed_at IS NULL OR completed_at >= started_at",
            name="completed_after_started",
        ),
        CheckConstraint(
            "status <> 'RUNNING' OR started_at IS NOT NULL", name="running_requires_start"
        ),
        CheckConstraint(
            "status NOT IN ('SUCCEEDED', 'FAILED', 'CANCELLED') OR completed_at IS NOT NULL",
            name="terminal_requires_completion",
        ),
        Index("ix_training_runs_dataset_status", "dataset_id", "status"),
        Index("ix_training_runs_pipeline_status", "pipeline", "status"),
    )

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False
    )
    pipeline: Mapped[str] = mapped_column(String(16), nullable=False)
    base_model: Mapped[str] = mapped_column(String(200), nullable=False)
    hyperparameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    mlflow_run_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TrainingRunStatus.PENDING.value
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
