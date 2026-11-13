"""Assets and sensors."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    AssetType,
    Criticality,
    Environment,
    SensorStatus,
    sql_values,
)


class Asset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(f"asset_type IN ({sql_values(AssetType)})", name="asset_type_allowed"),
        CheckConstraint(f"criticality IN ({sql_values(Criticality)})", name="criticality_allowed"),
        CheckConstraint(f"environment IN ({sql_values(Environment)})", name="environment_allowed"),
    )

    # Unique because seed and ingestion adapters use the name as a natural key.
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    criticality: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_team: Mapped[str] = mapped_column(String(120), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    sensors: Mapped[list[Sensor]] = relationship(back_populates="asset")


class Sensor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sensors"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_values(SensorStatus)})", name="status_allowed"),
        CheckConstraint("length(credential_hash) >= 32", name="credential_hash_present"),
        CheckConstraint(
            "credential_prefix IS NULL OR credential_prefix ~ '^[a-z0-9]{8,32}$'",
            name="credential_prefix_format",
        ),
        # Revocation is a dated event, not just a status value: the timestamp is
        # what downstream queries and the audit trail rely on.
        CheckConstraint(
            "status <> 'REVOKED' OR revoked_at IS NOT NULL", name="revoked_requires_timestamp"
        ),
        Index(
            "ux_sensors_credential_prefix",
            "credential_prefix",
            unique=True,
            postgresql_where=text("credential_prefix IS NOT NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    sensor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        index=True,
    )
    # Only a derived credential hash is stored; the raw sensor credential is
    # issued once and never persisted. Rotation replaces this value.
    credential_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Non-secret public lookup id sent ahead of the secret. It lets the server
    # find the row without a table scan and without logging the secret half.
    credential_prefix: Mapped[str | None] = mapped_column(String(32))
    credential_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SensorStatus.ACTIVE.value
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    asset: Mapped[Asset | None] = relationship(back_populates="sensors")
