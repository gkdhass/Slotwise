"""Model registry records and persisted inference outputs."""

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
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    ModelVersionStatus,
    Pipeline,
    Severity,
    sql_values,
)


class ModelVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint(
            "pipeline",
            "model_name",
            "version",
            name="uq_model_versions_pipeline_model_name_version",
        ),
        CheckConstraint(f"pipeline IN ({sql_values(Pipeline)})", name="pipeline_allowed"),
        CheckConstraint(f"status IN ({sql_values(ModelVersionStatus)})", name="status_allowed"),
        CheckConstraint("length(model_name) > 0", name="model_name_present"),
        CheckConstraint("length(version) > 0", name="version_present"),
        CheckConstraint("length(artifact_uri) > 0", name="artifact_uri_present"),
        CheckConstraint(
            "status <> 'ACTIVE' OR promoted_at IS NOT NULL",
            name="active_requires_promotion_timestamp",
        ),
        # At most one ACTIVE model per logical model. Enforced by the database
        # so concurrent promotions cannot create two production champions.
        Index(
            "ux_model_versions_active_per_model",
            "pipeline",
            "model_name",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("ix_model_versions_pipeline_status", "pipeline", "status"),
    )

    pipeline: Mapped[str] = mapped_column(String(16), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    framework: Mapped[str] = mapped_column(String(64), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=ModelVersionStatus.DRAFT.value
    )
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    training_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("training_runs.id", ondelete="SET NULL"),
        index=True,
    )


class InferenceResult(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "inference_results"
    __table_args__ = (
        CheckConstraint(f"severity IN ({sql_values(Severity)})", name="severity_allowed"),
        CheckConstraint("length(predicted_class) > 0", name="predicted_class_present"),
        CheckConstraint("anomaly_score >= 0 AND anomaly_score <= 1", name="anomaly_score_range"),
        CheckConstraint("inference_ms >= 0", name="inference_ms_non_negative"),
        CheckConstraint("jsonb_typeof(probabilities) = 'object'", name="probabilities_object"),
        Index("ix_inference_results_event_id_created_at", "event_id", "created_at"),
        Index("ix_inference_results_created_at_id", "created_at", "id"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    predicted_class: Mapped[str] = mapped_column(String(200), nullable=False)
    # Full class probability vector. Kept as JSONB because the class catalogue is
    # model-specific and changes with the pipeline rather than the schema.
    probabilities: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    explanation_ref: Mapped[str | None] = mapped_column(Text)
    inference_ms: Mapped[int] = mapped_column(Integer, nullable=False)
