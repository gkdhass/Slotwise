"""API dependencies: database session, Redis, principals and authorization.

Every protected route resolves its authorization from a permission dependency,
never from a role-name comparison in the handler. ``get_current_principal``
re-reads the user and role from PostgreSQL on every request, so deactivation,
lockout and role changes take effect immediately even for an unexpired JWT.

The module also exposes :func:`assert_all_routes_authorized`, called at app
startup and by the test-suite, which fails when a new route is neither public nor
decorated with an authorization dependency.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.errors import (
    AuthAccountLockedError,
    AuthInvalidCredentialsError,
    AuthRateLimitedError,
    AuthTokenExpiredError,
    AuthTokenInvalidError,
    DependencyUnavailableError,
    ForbiddenError,
    UnauthorizedError,
)
from app.core.rate_limit import check_sliding_window, sensor_key
from app.core.redis import RedisClient, get_redis_client
from app.core.security import (
    TokenValidationError,
    decode_access_token,
    parse_sensor_key,
    verify_sensor_key,
)
from app.models.assets import Sensor
from app.models.enums import RoleName
from app.policies.permissions import permissions_for
from app.services.health import HealthService

logger = logging.getLogger(__name__)

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
RedisDep = Annotated[RedisClient, Depends(get_redis_client)]
PrincipalDep = Annotated["Principal", Depends(lambda: None)]

SENSOR_PERMISSIONS = frozenset({"events:submit", "sensor:heartbeat"})


@dataclass(frozen=True)
class Principal:
    """Authenticated caller. ``is_sensor`` routes are audited separately."""

    user_id: uuid.UUID | None
    display_id: str
    role: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    email: str | None = None
    must_change_password: bool = False
    is_sensor: bool = False
    sensor_id: uuid.UUID | None = None
    sensor_name: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == RoleName.ADMIN.value


def client_ip(request: Request) -> str:
    """Client address used for throttling and audit context.

    The deployment terminates TLS at Nginx, which is configured to overwrite
    ``X-Forwarded-For``; the direct peer is used as a fallback so a spoofed
    header cannot invent an unlimited supply of rate-limit buckets when the
    header is absent.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        candidate = forwarded.split(",", 1)[0].strip()
        if candidate:
            return candidate
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthorizedError("A bearer access token is required.")
    return token.strip()


async def get_current_principal(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
) -> Principal:
    token = _bearer_token(request)
    try:
        claims = decode_access_token(token, settings=settings)
    except TokenValidationError as exc:
        if exc.expired:
            raise AuthTokenExpiredError() from exc
        raise AuthTokenInvalidError() from exc

    from app.repositories.identity import UserRepository

    user = await UserRepository(session).get_with_role(claims.subject)
    if user is None or not user.is_active:
        # Deactivation must win over a still-valid signature.
        raise AuthTokenInvalidError("The account is not available.")
    if user.locked_until is not None:
        from datetime import UTC, datetime

        if user.locked_until > datetime.now(UTC):
            raise AuthAccountLockedError()

    role = RoleName(user.role.name)
    return Principal(
        user_id=user.id,
        display_id=str(user.id),
        role=role.value,
        permissions=permissions_for(role),
        email=user.email,
        must_change_password=user.must_change_password,
    )


get_current_principal.__slotwise_auth__ = True  # type: ignore[attr-defined]


async def _audit_permission_denied(
    *,
    session: AsyncSession,
    principal: Principal,
    request: Request,
    required: tuple[str, ...],
) -> None:
    from app.repositories.audit import AuditRepository

    try:
        await AuditRepository(session).record(
            actor_id=principal.user_id,
            action="AUTH_PERMISSION_DENIED",
            entity_type="route",
            entity_id=None,
            after={
                "path": request.url.path,
                "method": request.method,
                "required_permissions": list(required),
                "role": principal.role,
            },
            ip_address=client_ip(request),
        )
        await session.commit()
    except Exception:  # pragma: no cover - the denial itself must still happen
        logger.warning("permission_denied_audit_failed", extra={"path": request.url.path})


def require_permission(permission: str) -> Any:
    async def dependency(
        request: Request,
        session: SessionDep,
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if principal.must_change_password:
            raise ForbiddenError(
                "The password must be changed before using this endpoint.",
                details={"reason": "password_change_required"},
            )
        if permission not in principal.permissions:
            await _audit_permission_denied(
                session=session,
                principal=principal,
                request=request,
                required=(permission,),
            )
            raise ForbiddenError(
                "You do not have the required permission.",
                details={"required": permission},
            )
        return principal

    dependency.__slotwise_auth__ = True  # type: ignore[attr-defined]
    dependency.__required_permissions__ = (permission,)  # type: ignore[attr-defined]
    return dependency


def require_any_permission(*permissions: str) -> Any:
    async def dependency(
        request: Request,
        session: SessionDep,
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if principal.must_change_password:
            raise ForbiddenError(
                "The password must be changed before using this endpoint.",
                details={"reason": "password_change_required"},
            )
        if not principal.permissions.intersection(permissions):
            await _audit_permission_denied(
                session=session,
                principal=principal,
                request=request,
                required=permissions,
            )
            raise ForbiddenError(
                "You do not have any of the required permissions.",
                details={"required_any": list(permissions)},
            )
        return principal

    dependency.__slotwise_auth__ = True  # type: ignore[attr-defined]
    dependency.__required_permissions__ = tuple(permissions)  # type: ignore[attr-defined]
    return dependency


async def get_current_sensor(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    redis: RedisDep,
) -> Principal:
    raw = request.headers.get("x-sensor-key", "").strip()
    parsed = parse_sensor_key(raw) if raw else None
    if parsed is None:
        raise AuthInvalidCredentialsError("A valid sensor key is required.")
    prefix, secret = parsed

    from app.repositories.assets import SensorRepository

    try:
        decision = await check_sliding_window(
            redis,
            key=sensor_key(prefix, client_ip(request)),
            limit=settings.security.rate_limit_sensor_per_minute,
            window_seconds=60,
        )
    except Exception as exc:  # RedisError and transport failures alike
        # Fail closed for machine credentials too: uncounted attempts are not
        # allowed to hammer the key lookup.
        raise DependencyUnavailableError(
            "Authentication throttling is temporarily unavailable."
        ) from exc
    if not decision.allowed:
        raise AuthRateLimitedError(retry_after=decision.retry_after)

    sensor: Sensor | None = await SensorRepository(session).get_by_prefix(prefix)
    if (
        sensor is None
        or sensor.status != "ACTIVE"
        or sensor.revoked_at is not None
        or not verify_sensor_key(secret, sensor.credential_hash)
    ):
        raise AuthInvalidCredentialsError("A valid sensor key is required.")

    return Principal(
        user_id=None,
        display_id=str(sensor.id),
        role="SENSOR",
        permissions=SENSOR_PERMISSIONS,
        is_sensor=True,
        sensor_id=sensor.id,
        sensor_name=sensor.name,
    )


get_current_sensor.__slotwise_auth__ = True  # type: ignore[attr-defined]


#: Routes that intentionally require no user or sensor authentication. Kept
#: deliberately small; every entry is reviewed with the route that needs it.
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/healthz"),
        ("GET", "/readyz"),
        ("GET", "/metrics"),
        ("GET", "/api/v1/healthz"),
        ("GET", "/api/v1/readyz"),
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/refresh"),
        ("POST", "/api/v1/auth/logout"),
    }
)


def _dependency_calls(dependant: Any) -> list[Any]:
    calls: list[Any] = []
    if getattr(dependant, "call", None) is not None:
        calls.append(dependant.call)
    for child in getattr(dependant, "dependencies", ()) or ():
        calls.extend(_dependency_calls(child))
    return calls


def iter_api_routes(routes: Any) -> list[Any]:
    """Flatten the route table across FastAPI router representations.

    FastAPI versions in this project's range keep included routers as wrapper
    objects (``_IncludedRouter``) and expose their concrete entries through
    ``effective_candidates()``; older versions flatten to ``APIRoute`` directly.
    Both shapes are handled so the startup guard and the test-suite see every
    real endpoint.
    """
    flattened: list[Any] = []
    for route in routes:
        if isinstance(route, APIRoute):
            flattened.append(route)
            continue
        candidates = getattr(route, "effective_candidates", None)
        if callable(candidates):
            flattened.extend(iter_api_routes(candidates()))
            continue
        # ``_EffectiveRouteContext`` is a concrete route context rather than an
        # APIRoute subclass; it carries the same authorization metadata.
        if hasattr(route, "dependant") and hasattr(route, "methods"):
            flattened.append(route)
    return flattened


def unprotected_routes(app: Any) -> list[tuple[str, str]]:
    unprotected: list[tuple[str, str]] = []
    for route in iter_api_routes(app.routes):
        methods = sorted(route.methods or ())
        for method in methods:
            if (method, route.path) in PUBLIC_ROUTES:
                continue
            calls = _dependency_calls(route.dependant)
            if not any(getattr(call, "__slotwise_auth__", False) for call in calls):
                unprotected.append((method, route.path))
    return unprotected


def assert_all_routes_authorized(app: Any) -> None:
    missing = unprotected_routes(app)
    if missing:
        rendered = ", ".join(f"{method} {path}" for method, path in missing)
        raise RuntimeError("Routes without an explicit authorization dependency: " + rendered)


PrincipalAnnotated = Annotated[Principal, Depends(get_current_principal)]


def get_health_service(settings: SettingsDep) -> HealthService:
    """Construct the readiness service per request from validated settings."""
    return HealthService(settings)


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]
