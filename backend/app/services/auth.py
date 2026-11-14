"""Authentication flows: login, refresh rotation, logout and password changes.

All state changes share one database transaction with their audit row. Refresh
tokens are opaque, stored only as SHA-256 digests, and rotated on every use.
Presenting a consumed or revoked token revokes the whole token family and emits
``AUTH_REFRESH_REUSE_DETECTED``.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    AuthAccountLockedError,
    AuthInvalidCredentialsError,
    AuthRefreshRejectedRevokedFamilyError,
    AuthRefreshReuseDetectedError,
    AuthTokenExpiredError,
    AuthTokenInvalidError,
    PasswordPolicyViolationError,
    UnauthorizedError,
)
from app.core.security import (
    PasswordPolicyCheckError,
    create_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    password_needs_rehash,
    validate_new_password,
    verify_dummy_password,
    verify_password,
)
from app.models.identity import RefreshToken, User
from app.repositories.audit import AuditRepository
from app.repositories.identity import RefreshTokenRepository, UserRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoginResult:
    user: User
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass(frozen=True)
class RefreshResult:
    user: User
    access_token: str
    refresh_token: str
    expires_in: int


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.users = UserRepository(session)
        self.tokens = RefreshTokenRepository(session)
        self.audit = AuditRepository(session)

    # ------------------------------------------------------------------ login

    async def login(
        self,
        *,
        email: str,
        password: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> LoginResult:
        normalized = email.strip().lower()
        user = await self.users.get_by_email(normalized)

        if user is None:
            # Equalise timing with a real Argon2 verification.
            verify_dummy_password(password, settings=self.settings)
            await self.audit.record(
                actor_id=None,
                action="AUTH_LOGIN_FAILURE",
                entity_type="auth",
                entity_id=None,
                after={"reason": "invalid_credentials"},
                ip_address=ip_address,
            )
            await self.session.commit()
            raise AuthInvalidCredentialsError()

        if not verify_password(password, user.password_hash, settings=self.settings):
            await self._register_failure(user, ip_address=ip_address)
            raise AuthInvalidCredentialsError()

        now = datetime.now(UTC)
        if user.locked_until is not None and user.locked_until > now:
            await self.audit.record(
                actor_id=user.id,
                action="AUTH_LOGIN_FAILURE",
                entity_type="user",
                entity_id=user.id,
                after={"reason": "account_locked"},
                ip_address=ip_address,
            )
            await self.session.commit()
            raise AuthAccountLockedError()

        if not user.is_active:
            await self.audit.record(
                actor_id=user.id,
                action="AUTH_LOGIN_FAILURE",
                entity_type="user",
                entity_id=user.id,
                after={"reason": "account_inactive"},
                ip_address=ip_address,
            )
            await self.session.commit()
            raise AuthInvalidCredentialsError()

        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = now
        if password_needs_rehash(user.password_hash, settings=self.settings):
            user.password_hash = hash_password(password, settings=self.settings)
            user.password_changed_at = now

        raw, digest = new_refresh_token()
        refresh = RefreshToken(
            user_id=user.id,
            family_id=uuid.uuid4(),
            token_hash=digest,
            expires_at=now + timedelta(hours=self.settings.security.refresh_token_expire_hours),
            user_agent=(user_agent or "")[:512] or None,
            ip_address=ip_address,
        )
        self.session.add(refresh)
        await self.audit.record(
            actor_id=user.id,
            action="AUTH_LOGIN_SUCCESS",
            entity_type="user",
            entity_id=user.id,
            after={"role": user.role.name},
            ip_address=ip_address,
        )
        await self.session.commit()

        return LoginResult(
            user=user,
            access_token=create_access_token(user.id, user.role.name, settings=self.settings),
            refresh_token=raw,
            expires_in=self.settings.security.access_token_expire_minutes * 60,
        )

    async def _register_failure(self, user: User, *, ip_address: str | None) -> None:
        user.failed_login_count += 1
        threshold = self.settings.security.lockout_threshold
        locked_now = False
        if user.failed_login_count >= threshold:
            user.locked_until = datetime.now(UTC) + timedelta(
                minutes=self.settings.security.lockout_minutes
            )
            locked_now = True
            user.failed_login_count = 0
        await self.audit.record(
            actor_id=user.id,
            action="AUTH_LOGIN_FAILURE",
            entity_type="user",
            entity_id=user.id,
            after={
                "reason": "invalid_password",
                "failed_attempts": user.failed_login_count,
                "locked": locked_now,
            },
            ip_address=ip_address,
        )
        if locked_now:
            await self.audit.record(
                actor_id=user.id,
                action="AUTH_ACCOUNT_LOCKED",
                entity_type="user",
                entity_id=user.id,
                after={
                    "locked_until": user.locked_until.isoformat() if user.locked_until else None,
                    "threshold": threshold,
                },
                ip_address=ip_address,
            )
        await self.session.commit()

    # ---------------------------------------------------------------- refresh

    async def refresh(
        self,
        *,
        raw_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> RefreshResult:
        if not raw_token:
            raise AuthTokenInvalidError("A refresh token is required.")
        row = await self.tokens.get_by_hash(hash_token(raw_token))
        if row is None:
            raise AuthTokenInvalidError("The refresh token is invalid.")

        now = datetime.now(UTC)

        # Distinguish between replay (used_at set, revoked_at may be None or later)
        # vs already-revoked-family (revoked_at set before or without use)
        if row.used_at is not None:
            # Token was already used → replay detection → revoke family and log reuse
            await self._handle_reuse(row, ip_address=ip_address)
            raise AuthRefreshReuseDetectedError()
        elif row.revoked_at is not None:
            # Token is part of an already-revoked family → log different action
            await self._handle_revoked_family(row, ip_address=ip_address)
            raise AuthRefreshRejectedRevokedFamilyError()

        if row.expires_at <= now:
            await self.tokens.revoke_family(row.family_id, now=now)
            await self.session.commit()
            raise AuthTokenExpiredError()

        user = await self.users.get_with_role(row.user_id)
        if user is None or not user.is_active:
            await self.tokens.revoke_family(row.family_id, now=now)
            await self.session.commit()
            raise AuthTokenInvalidError("The account is not available.")
        if user.locked_until is not None and user.locked_until > now:
            await self.tokens.revoke_family(row.family_id, now=now)
            await self.session.commit()
            raise AuthAccountLockedError()

        raw, digest = new_refresh_token()
        replacement = RefreshToken(
            user_id=user.id,
            family_id=row.family_id,
            token_hash=digest,
            expires_at=now + timedelta(hours=self.settings.security.refresh_token_expire_hours),
            user_agent=(user_agent or "")[:512] or None,
            ip_address=ip_address,
        )
        self.session.add(replacement)
        await self.session.flush()
        row.used_at = now
        row.replaced_by = replacement.id
        await self.session.commit()

        return RefreshResult(
            user=user,
            access_token=create_access_token(user.id, user.role.name, settings=self.settings),
            refresh_token=raw,
            expires_in=self.settings.security.access_token_expire_minutes * 60,
        )

    async def _handle_reuse(self, row: RefreshToken, *, ip_address: str | None) -> None:
        """Handle replay of an already-used token (actual reuse detection)."""
        await self.tokens.revoke_family(row.family_id)
        await self.audit.record(
            actor_id=row.user_id,
            action="AUTH_REFRESH_REUSE_DETECTED",
            entity_type="refresh_token_family",
            entity_id=row.family_id,
            after={"token_id": str(row.id), "reason": "consumed_token_replayed"},
            ip_address=ip_address,
        )
        await self.session.commit()
        logger.warning(
            "refresh_token_reuse_detected",
            extra={"family_id": str(row.family_id), "user_id": str(row.user_id)},
        )

    async def _handle_revoked_family(self, row: RefreshToken, *, ip_address: str | None) -> None:
        """Handle use of a token from an already-revoked family (not a replay, just revoked)."""
        await self.audit.record(
            actor_id=row.user_id,
            action="AUTH_REFRESH_REJECTED_REVOKED_FAMILY",
            entity_type="refresh_token_family",
            entity_id=row.family_id,
            after={"token_id": str(row.id), "reason": "token_from_revoked_family"},
            ip_address=ip_address,
        )
        await self.session.commit()
        logger.warning(
            "refresh_token_revoked_family_rejected",
            extra={"family_id": str(row.family_id), "user_id": str(row.user_id)},
        )

    # ----------------------------------------------------------------- logout

    async def logout(self, *, raw_token: str | None, ip_address: str | None) -> None:
        if raw_token:
            row = await self.tokens.get_by_hash(hash_token(raw_token))
            if row is not None:
                await self.tokens.revoke_family(row.family_id)
                await self.audit.record(
                    actor_id=row.user_id,
                    action="AUTH_LOGOUT",
                    entity_type="user",
                    entity_id=row.user_id,
                    after={"family_id": str(row.family_id)},
                    ip_address=ip_address,
                )
                await self.session.commit()
                return
        await self.session.commit()

    async def logout_all(self, *, user_id: uuid.UUID, ip_address: str | None) -> None:
        revoked = await self.tokens.revoke_all_for_user(user_id)
        await self.audit.record(
            actor_id=user_id,
            action="AUTH_LOGOUT_ALL",
            entity_type="user",
            entity_id=user_id,
            after={"revoked": revoked},
            ip_address=ip_address,
        )
        await self.session.commit()

    # -------------------------------------------------------------- password

    async def change_password(
        self,
        *,
        user_id: uuid.UUID,
        current_password: str,
        new_password: str,
        ip_address: str | None,
    ) -> None:
        user = await self.users.get_with_role(user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("The account is not available.")
        if not verify_password(current_password, user.password_hash, settings=self.settings):
            await self.audit.record(
                actor_id=user.id,
                action="AUTH_PASSWORD_CHANGE_FAILED",
                entity_type="user",
                entity_id=user.id,
                after={"reason": "invalid_current_password"},
                ip_address=ip_address,
            )
            await self.session.commit()
            raise AuthInvalidCredentialsError("The current password is incorrect.")
        self._validate_password(new_password, user)
        now = datetime.now(UTC)
        user.password_hash = hash_password(new_password, settings=self.settings)
        user.password_changed_at = now
        user.must_change_password = False
        user.failed_login_count = 0
        user.locked_until = None
        await self.tokens.revoke_all_for_user(user.id, now=now)
        await self.audit.record(
            actor_id=user.id,
            action="AUTH_PASSWORD_CHANGED",
            entity_type="user",
            entity_id=user.id,
            after={"sessions_revoked": True},
            ip_address=ip_address,
        )
        await self.session.commit()

    def _validate_password(self, password: str, user: User) -> None:
        try:
            validate_new_password(
                password,
                email=user.email,
                current_hash=user.password_hash,
                settings=self.settings,
            )
        except PasswordPolicyCheckError as exc:
            raise PasswordPolicyViolationError(details={"reasons": exc.reasons}) from exc
