"""Append-only audit trail.

Immutability is enforced by database triggers (see the Phase 2 migration) and by
revoking UPDATE/DELETE/TRUNCATE from the application role. The Phase 1 source
material calls for immutable history but does not require cryptographic tamper
evidence, so no hash chain is stored. This keeps the writer cheap; a future
requirement for tamper evidence can add a chained digest without changing the
event contract.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.identity import User


class AuditLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("length(action) > 0", name="action_present"),
        CheckConstraint("length(entity_type) > 0", name="entity_type_present"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_actor_created_at", "actor_id", "created_at"),
        Index("ix_audit_logs_created_at_id", "created_at", "id"),
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)

    actor: Mapped[User | None] = relationship(back_populates="audit_entries")
