"""Roles and users.

Email addresses are stored lowercase and the database enforces it so the plain
UNIQUE constraint is genuinely case-insensitive. Password hashes are the only
credential material stored; plaintext passwords never reach the database.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import RoleName, sql_values

if TYPE_CHECKING:
    from app.models.audit import AuditLog


class Role(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (CheckConstraint(f"name IN ({sql_values(RoleName)})", name="name_allowed"),)

    name: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)

    users: Mapped[list[User]] = relationship(back_populates="role")


class User(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("length(password_hash) >= 20", name="password_hash_present"),
        CheckConstraint("failed_login_count >= 0", name="failed_login_count_non_negative"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Durable lockout state. Redis carries the short-window throttle, but the
    # lockout counter must survive a cache flush, so it lives in PostgreSQL.
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    role: Mapped[Role] = relationship(back_populates="users")
    audit_entries: Mapped[list[AuditLog]] = relationship(back_populates="actor")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="user")


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    """Rotating opaque refresh token.

    Only the SHA-256 digest is stored, so a database disclosure does not yield
    usable session material. Tokens in the same ``family_id`` form one login
    session; replay of any consumed token revokes the whole family.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_hash_sha256"),
        CheckConstraint("expires_at > issued_at", name="expires_after_issue"),
        CheckConstraint(
            "used_at IS NULL OR revoked_at IS NULL OR used_at <= revoked_at",
            name="used_before_revoked",
        ),
        Index("ux_refresh_tokens_token_hash", "token_hash", unique=True),
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_family_id", "family_id"),
        Index("ix_refresh_tokens_user_family", "user_id", "family_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    family_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip_address: Mapped[str | None] = mapped_column(INET)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
