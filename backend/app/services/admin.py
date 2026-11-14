"""Administrative services: users, sensors, response policies and allow-list.

The protections that matter (last active administrator, self-demotion, immutable
policy versions, approval-first high-impact actions) are enforced here and, where
possible, repeated in the database. Every mutation writes exactly one audit row
in the same transaction.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import secrets
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import TypeVar
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.errors import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    LastAdminProtectedError,
    NotFoundError,
    PasswordPolicyViolationError,
)
from app.core.security import (
    PasswordPolicyCheckError,
    hash_password,
    new_sensor_key,
    validate_new_password,
)
from app.models.assets import Sensor
from app.models.enums import (
    HIGH_IMPACT_ACTION_TYPES,
    ResponseActionType,
    SensorStatus,
)
from app.models.identity import Role, User
from app.models.responses import AllowlistEntry, ResponsePolicy
from app.repositories.assets import AssetRepository, SensorRepository
from app.repositories.audit import AuditRepository
from app.repositories.identity import RoleRepository, UserRepository
from app.repositories.responses import AllowlistRepository, ResponsePolicyRepository

logger = logging.getLogger(__name__)

#: PostgreSQL SQLSTATEs raised when two transactions conflict under load.
RETRYABLE_SQLSTATES = frozenset({"40P01", "40001"})
MAX_CONCURRENCY_ATTEMPTS = 3

_T = TypeVar("_T")


def is_retryable_conflict(exc: BaseException) -> bool:
    """True for a deadlock (40P01) or serialization failure (40001)."""
    candidate: BaseException | None = exc
    while candidate is not None:
        state = getattr(candidate, "sqlstate", None) or getattr(candidate, "pgcode", None)
        if state in RETRYABLE_SQLSTATES:
            return True
        candidate = getattr(candidate, "orig", None)
    return False


def user_snapshot(user: User, role_name: str) -> dict[str, object]:
    """Audit-safe view: identity and role only, never credential material."""
    return {
        "email": user.email,
        "role": role_name,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
    }


def generate_temporary_password(settings: Settings, email: str) -> str:
    for _ in range(10):
        candidate = f"Sw-{secrets.token_urlsafe(15)}-9!"
        try:
            validate_new_password(candidate, email=email, settings=settings)
        except PasswordPolicyCheckError:
            continue
        return candidate
    raise RuntimeError("Unable to generate a policy-compliant temporary password")


class AuditWriter:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditRepository(session)

    async def record(
        self,
        *,
        actor_id: uuid.UUID | None,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID | None,
        before: Mapping[str, object] | None = None,
        after: Mapping[str, object] | None = None,
        ip_address: str | None = None,
    ) -> None:
        await self.audit.record(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before,
            after=after,
            ip_address=ip_address,
        )


class UserAdminService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.users = UserRepository(session)
        self.roles = RoleRepository(session)
        self.audit = AuditWriter(session)

    async def _role(self, name: str) -> Role:
        role = await self.roles.get_by_name(name)
        if role is None:
            raise BadRequestError("Unknown role.", details={"role": name})
        return role

    async def _target(self, user_id: uuid.UUID) -> User:
        user = await self.users.get_with_role(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        return user

    async def _lock_active_admins(self) -> list[uuid.UUID]:
        """Lock every active administrator row and return their ids.

        This is the single serialization point for every operation that can
        reduce the active-administrator count. The plain row select (no
        aggregate) plus ``FOR UPDATE`` ordered by id means concurrent callers
        queue behind each other instead of both reading the same stale count.
        ``populate_existing`` discards identity-map values cached earlier in the
        request (for example by the authentication dependency), so the caller
        always sees the row as it exists after the lock wait.
        """
        statement = (
            select(User.id)
            .join(Role, User.role_id == Role.id)
            .where(Role.name == "ADMIN", User.is_active.is_(True))
            .order_by(User.id)
            .with_for_update(of=User)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def _lock_target(self, user_id: uuid.UUID) -> User:
        """Re-read the target row while holding the admin lock, bypassing the cache."""
        statement = (
            select(User)
            .options(selectinload(User.role))
            .where(User.id == user_id)
            .execution_options(populate_existing=True)
        )
        user = (await self.session.execute(statement)).scalar_one_or_none()
        if user is None:
            raise NotFoundError("User not found.")
        return user

    async def _run_with_retry(self, operation: Callable[[], Awaitable[_T]]) -> _T:
        """Run a whole unit of work in its own transaction, retrying conflicts.

        A deadlock (40P01) or serialization failure (40001) aborts the current
        transaction; the session is rolled back and the *entire* operation runs
        again in a fresh transaction so no stale ORM state or aborted
        transaction survives into the retry.
        """
        for attempt in range(1, MAX_CONCURRENCY_ATTEMPTS + 1):
            try:
                return await operation()
            except DBAPIError as exc:
                if not is_retryable_conflict(exc):
                    raise
                await self.session.rollback()
                if attempt >= MAX_CONCURRENCY_ATTEMPTS:
                    raise ConflictError(
                        "Operation failed due to concurrent modifications. Please try again.",
                        details={"reason": "deadlock_retry_exhausted"},
                    ) from exc
        raise RuntimeError("Unexpected control flow in _run_with_retry")

    async def create_user(
        self,
        *,
        actor_id: uuid.UUID,
        email: str,
        role_name: str,
        password: str | None,
        ip_address: str | None,
    ) -> tuple[User, str | None]:
        role = await self._role(role_name)
        normalised = email.strip().lower()
        if await self.users.get_by_email(normalised) is not None:
            raise ConflictError("A user with that email already exists.")
        generated = password is None
        plaintext = password or generate_temporary_password(self.settings, normalised)
        if password is not None:
            try:
                validate_new_password(plaintext, email=normalised, settings=self.settings)
            except PasswordPolicyCheckError as exc:
                raise PasswordPolicyViolationError(details={"reasons": exc.reasons}) from exc
        user = User(
            email=normalised,
            password_hash=hash_password(plaintext, settings=self.settings),
            role_id=role.id,
            is_active=True,
            must_change_password=generated,
            password_changed_at=datetime.now(UTC) if not generated else None,
        )
        user.role = role
        self.session.add(user)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("A user with that email already exists.") from exc
        await self.audit.record(
            actor_id=actor_id,
            action="USER_CREATED",
            entity_type="user",
            entity_id=user.id,
            after={**user_snapshot(user, role.name), "temporary_password": generated},
            ip_address=ip_address,
        )
        await self.session.commit()
        return user, (plaintext if generated else None)

    async def update_user(
        self,
        *,
        actor_id: uuid.UUID,
        user_id: uuid.UUID,
        email: str | None,
        role_name: str | None,
        is_active: bool | None,
        ip_address: str | None,
    ) -> User:
        """Update a user; the whole unit of work is retried on a DB conflict."""
        return await self._run_with_retry(
            lambda: self._mutate_user(
                actor_id=actor_id,
                user_id=user_id,
                email=email,
                role_name=role_name,
                is_active=is_active,
                ip_address=ip_address,
            )
        )

    async def set_active(
        self,
        *,
        actor_id: uuid.UUID,
        user_id: uuid.UUID,
        active: bool,
        ip_address: str | None,
    ) -> User:
        """Activate or deactivate a user through the shared admin lock."""
        return await self._run_with_retry(
            lambda: self._mutate_user(
                actor_id=actor_id,
                user_id=user_id,
                email=None,
                role_name=None,
                is_active=active,
                ip_address=ip_address,
                action="USER_REACTIVATED" if active else "USER_DEACTIVATED",
            )
        )

    async def _mutate_user(
        self,
        *,
        actor_id: uuid.UUID,
        user_id: uuid.UUID,
        email: str | None,
        role_name: str | None,
        is_active: bool | None,
        ip_address: str | None,
        action: str | None = None,
    ) -> User:
        """Apply one user change inside the locked admin transaction.

        Deactivation, demotion and disable all funnel through here: the active
        administrator rows are locked first, the target is re-read under that
        lock (so the identity map cannot serve a pre-lock ``is_active``/role),
        the invariant is checked against the locked rows and only then is the
        change applied and committed.
        """
        locked_admin_ids = await self._lock_active_admins()
        user = await self._lock_target(user_id)
        current_role = user.role.name
        before = user_snapshot(user, current_role)

        new_role: Role | None = None
        if role_name is not None and role_name != current_role:
            new_role = await self._role(role_name)

        removing_active_admin = (
            current_role == "ADMIN"
            and user.is_active
            and (
                (new_role is not None and new_role.name != "ADMIN")
                or (is_active is not None and not is_active)
            )
        )
        if removing_active_admin and len(locked_admin_ids) <= 1:
            raise LastAdminProtectedError()

        if new_role is not None:
            if user.id == actor_id and current_role == "ADMIN" and new_role.name != "ADMIN":
                raise ForbiddenError(
                    "You cannot remove your own administrator role.",
                    details={"reason": "self_demotion_forbidden"},
                )
            user.role_id = new_role.id
            # Keep the loaded relationship consistent so the response and the
            # audit snapshot report the new role without a second query.
            user.role = new_role

        if is_active is not None and is_active != user.is_active:
            if not is_active and user.id == actor_id:
                raise ForbiddenError(
                    "You cannot deactivate your own account.",
                    details={"reason": "self_deactivation_forbidden"},
                )
            user.is_active = is_active

        if email is not None:
            user.email = email.strip().lower()

        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("A user with that email already exists.") from exc

        resolved_action = action or (
            "USER_ROLE_CHANGED" if new_role is not None else "USER_UPDATED"
        )
        await self.audit.record(
            actor_id=actor_id,
            action=resolved_action,
            entity_type="user",
            entity_id=user.id,
            before=before,
            after=user_snapshot(user, user.role.name),
            ip_address=ip_address,
        )
        await self.session.commit()
        return user

    async def unlock(
        self, *, actor_id: uuid.UUID, user_id: uuid.UUID, ip_address: str | None
    ) -> User:
        user = await self._target(user_id)
        before = {
            "failed_login_count": user.failed_login_count,
            "locked_until": user.locked_until.isoformat() if user.locked_until else None,
        }
        user.failed_login_count = 0
        user.locked_until = None
        await self.session.flush()
        await self.audit.record(
            actor_id=actor_id,
            action="AUTH_ACCOUNT_UNLOCKED",
            entity_type="user",
            entity_id=user.id,
            before=before,
            after={"failed_login_count": 0, "locked_until": None},
            ip_address=ip_address,
        )
        await self.session.commit()
        return user

    async def reset_password(
        self, *, actor_id: uuid.UUID, user_id: uuid.UUID, ip_address: str | None
    ) -> tuple[User, str]:
        user = await self._target(user_id)
        temporary = generate_temporary_password(self.settings, user.email)
        user.password_hash = hash_password(temporary, settings=self.settings)
        user.must_change_password = True
        user.password_changed_at = None
        user.failed_login_count = 0
        user.locked_until = None
        from app.repositories.identity import RefreshTokenRepository

        revoked = await RefreshTokenRepository(self.session).revoke_all_for_user(user.id)
        await self.session.flush()
        await self.audit.record(
            actor_id=actor_id,
            action="USER_PASSWORD_RESET",
            entity_type="user",
            entity_id=user.id,
            after={"must_change_password": True, "sessions_revoked": revoked},
            ip_address=ip_address,
        )
        await self.session.commit()
        return user, temporary


class SensorAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.sensors = SensorRepository(session)
        self.assets = AssetRepository(session)
        self.audit = AuditWriter(session)

    async def _target(self, sensor_id: uuid.UUID) -> Sensor:
        sensor = await self.sensors.get(sensor_id)
        if sensor is None:
            raise NotFoundError("Sensor not found.")
        return sensor

    async def create(
        self,
        *,
        actor_id: uuid.UUID,
        name: str,
        sensor_type: str,
        asset_id: uuid.UUID | None,
        ip_address: str | None,
    ) -> tuple[Sensor, str]:
        if await self.sensors.get_by_name(name) is not None:
            raise ConflictError("A sensor with that name already exists.")
        if asset_id is not None and await self.assets.get(asset_id) is None:
            raise BadRequestError("Unknown asset.", details={"asset_id": str(asset_id)})
        issued = new_sensor_key()
        sensor = Sensor(
            name=name,
            sensor_type=sensor_type,
            asset_id=asset_id,
            credential_prefix=issued.prefix,
            credential_hash=issued.hash,
            credential_rotated_at=datetime.now(UTC),
            status=SensorStatus.ACTIVE.value,
        )
        self.session.add(sensor)
        await self.session.flush()
        await self.audit.record(
            actor_id=actor_id,
            action="SENSOR_CREATED",
            entity_type="sensor",
            entity_id=sensor.id,
            after={"name": name, "prefix": issued.prefix, "status": sensor.status},
            ip_address=ip_address,
        )
        await self.session.commit()
        return sensor, issued.raw

    async def rotate(
        self, *, actor_id: uuid.UUID, sensor_id: uuid.UUID, ip_address: str | None
    ) -> tuple[Sensor, str]:
        sensor = await self._target(sensor_id)
        if sensor.status == SensorStatus.REVOKED.value:
            raise ConflictError("A revoked sensor cannot be rotated; create a new sensor.")
        issued = new_sensor_key()
        sensor.credential_prefix = issued.prefix
        sensor.credential_hash = issued.hash
        sensor.credential_rotated_at = datetime.now(UTC)
        await self.session.flush()
        await self.audit.record(
            actor_id=actor_id,
            action="SENSOR_KEY_ROTATED",
            entity_type="sensor",
            entity_id=sensor.id,
            after={"prefix": issued.prefix},
            ip_address=ip_address,
        )
        await self.session.commit()
        return sensor, issued.raw

    async def revoke(
        self, *, actor_id: uuid.UUID, sensor_id: uuid.UUID, ip_address: str | None
    ) -> Sensor:
        sensor = await self._target(sensor_id)
        if sensor.status == SensorStatus.REVOKED.value:
            return sensor
        now = datetime.now(UTC)
        sensor.status = SensorStatus.REVOKED.value
        sensor.revoked_at = now
        await self.session.flush()
        await self.audit.record(
            actor_id=actor_id,
            action="SENSOR_REVOKED",
            entity_type="sensor",
            entity_id=sensor.id,
            after={"status": sensor.status, "revoked_at": now.isoformat()},
            ip_address=ip_address,
        )
        await self.session.commit()
        return sensor


class PolicyAdminService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.policies = ResponsePolicyRepository(session)
        self.audit = AuditWriter(session)

    async def create_version(
        self,
        *,
        actor_id: uuid.UUID,
        name: str,
        action_type: str,
        conditions: dict[str, object],
        requires_approval: bool,
        enabled: bool,
        supersedes_id: uuid.UUID | None,
        ip_address: str | None,
    ) -> ResponsePolicy:
        if action_type not in {item.value for item in ResponseActionType}:
            raise BadRequestError("Unknown response action type.")
        high_impact = action_type in {item.value for item in HIGH_IMPACT_ACTION_TYPES}
        if high_impact and not requires_approval:
            raise BadRequestError(
                "High-impact response policies must require approval.",
                details={"action_type": action_type},
            )
        latest = await self.policies.get_by_name(name)
        if supersedes_id is not None and (latest is None or latest.id != supersedes_id):
            raise ConflictError("Only the current policy version can be superseded.")
        version = await self.policies.next_version(name)
        policy = ResponsePolicy(
            name=name,
            version=version,
            supersedes_id=supersedes_id or (latest.id if latest is not None else None),
            action_type=action_type,
            conditions=dict(conditions),
            requires_approval=requires_approval,
            enabled=enabled,
            created_by=actor_id,
        )
        self.session.add(policy)
        await self.session.flush()
        await self.audit.record(
            actor_id=actor_id,
            action="RESPONSE_POLICY_VERSION_CREATED",
            entity_type="response_policy",
            entity_id=policy.id,
            after={
                "name": name,
                "version": version,
                "action_type": action_type,
                "requires_approval": requires_approval,
                "enabled": enabled,
            },
            ip_address=ip_address,
        )
        await self.session.commit()
        return policy

    async def set_enabled(
        self,
        *,
        actor_id: uuid.UUID,
        policy_id: uuid.UUID,
        enabled: bool,
        ip_address: str | None,
    ) -> ResponsePolicy:
        policy = await self.policies.get(policy_id)
        if policy is None:
            raise NotFoundError("Response policy not found.")
        if (
            enabled
            and not policy.requires_approval
            and policy.action_type in {item.value for item in HIGH_IMPACT_ACTION_TYPES}
        ):
            raise BadRequestError("High-impact response policies must require approval.")
        policy.enabled = enabled
        await self.session.flush()
        await self.audit.record(
            actor_id=actor_id,
            action="RESPONSE_POLICY_ENABLED" if enabled else "RESPONSE_POLICY_DISABLED",
            entity_type="response_policy",
            entity_id=policy.id,
            before={"enabled": not enabled},
            after={"enabled": enabled},
            ip_address=ip_address,
        )
        await self.session.commit()
        return policy


_DOMAIN_LABEL = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
_HEX_HASH = re.compile(r"^[A-Fa-f0-9]{32,128}$")


def validate_allowlist_value(entry_type: str, value: str) -> str:
    """Strict parser for allow-list values; returns the normalised form."""
    candidate = value.strip()
    if not candidate:
        raise BadRequestError("Allow-list value must not be empty.")
    try:
        if entry_type == "IP":
            return str(ipaddress.ip_address(candidate))
        if entry_type == "CIDR":
            if "/" not in candidate:
                raise ValueError("CIDR requires a prefix length")
            return str(ipaddress.ip_network(candidate, strict=False))
    except ValueError as exc:
        raise BadRequestError("Invalid IP address or network.") from exc
    if entry_type == "DOMAIN":
        if len(candidate) > 253 or "/" in candidate or "://" in candidate:
            raise BadRequestError("Invalid domain name.")
        labels = candidate.rstrip(".").split(".")
        if len(labels) < 2 or not all(_DOMAIN_LABEL.match(label) for label in labels):
            raise BadRequestError("Invalid domain name.")
        return candidate.rstrip(".").lower()
    if entry_type == "URL":
        parts = urlsplit(candidate)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise BadRequestError("Only absolute http(s) URLs are allowed.")
        return candidate
    if entry_type == "HASH":
        if not _HEX_HASH.fullmatch(candidate):
            raise BadRequestError("Hash values must be 32-128 hexadecimal characters.")
        return candidate.lower()
    if entry_type == "USER":
        if any(character.isspace() for character in candidate) or len(candidate) > 320:
            raise BadRequestError("Invalid user identifier.")
        return candidate.lower()
    raise BadRequestError("Unknown allow-list entry type.")


class AllowlistAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.allowlist = AllowlistRepository(session)
        self.audit = AuditWriter(session)

    async def create(
        self,
        *,
        actor_id: uuid.UUID,
        entry_type: str,
        value: str,
        reason: str,
        expires_at: datetime | None,
        ip_address: str | None,
    ) -> AllowlistEntry:
        normalised = validate_allowlist_value(entry_type, value)
        if expires_at is not None and expires_at <= datetime.now(UTC):
            raise BadRequestError("The expiry must be in the future.")
        if await self.allowlist.find_active(entry_type, normalised) is not None:
            raise ConflictError("An active allow-list entry already covers that value.")
        entry = AllowlistEntry(
            entry_type=entry_type,
            value=normalised,
            reason=reason,
            expires_at=expires_at,
            created_by=actor_id,
            is_active=True,
        )
        self.session.add(entry)
        await self.session.flush()
        await self.audit.record(
            actor_id=actor_id,
            action="ALLOWLIST_CREATED",
            entity_type="allowlist_entry",
            entity_id=entry.id,
            after={
                "entry_type": entry_type,
                "value": normalised,
                "reason": reason,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
            ip_address=ip_address,
        )
        await self.session.commit()
        return entry

    async def update(
        self,
        *,
        actor_id: uuid.UUID,
        entry_id: uuid.UUID,
        reason: str | None,
        expires_at: datetime | None,
        ip_address: str | None,
    ) -> AllowlistEntry:
        entry = await self.allowlist.get(entry_id)
        if entry is None:
            raise NotFoundError("Allow-list entry not found.")
        before = {"reason": entry.reason, "expires_at": entry.expires_at}
        if reason is not None:
            entry.reason = reason
        if expires_at is not None:
            if expires_at <= datetime.now(UTC):
                raise BadRequestError("The expiry must be in the future.")
            entry.expires_at = expires_at
        await self.session.flush()
        await self.audit.record(
            actor_id=actor_id,
            action="ALLOWLIST_UPDATED",
            entity_type="allowlist_entry",
            entity_id=entry.id,
            before={
                "reason": before["reason"],
                "expires_at": before["expires_at"].isoformat()
                if isinstance(before["expires_at"], datetime)
                else None,
            },
            after={
                "reason": entry.reason,
                "expires_at": entry.expires_at.isoformat() if entry.expires_at else None,
            },
            ip_address=ip_address,
        )
        await self.session.commit()
        return entry

    async def deactivate(
        self, *, actor_id: uuid.UUID, entry_id: uuid.UUID, ip_address: str | None
    ) -> None:
        entry = await self.allowlist.get(entry_id)
        if entry is None:
            raise NotFoundError("Allow-list entry not found.")
        if not entry.is_active:
            return
        entry.is_active = False
        await self.session.flush()
        await self.audit.record(
            actor_id=actor_id,
            action="ALLOWLIST_DEACTIVATED",
            entity_type="allowlist_entry",
            entity_id=entry.id,
            before={"is_active": True},
            after={"is_active": False},
            ip_address=ip_address,
        )
        await self.session.commit()
