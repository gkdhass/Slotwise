"""Authentication endpoints.

Login returns the access token in the body and the refresh token only as an
HttpOnly cookie. Refresh and logout additionally require a custom header and an
allow-listed ``Origin`` when one is present: SameSite=Strict already blocks
cross-site cookie sending, and these checks defend against a misconfigured
browser or proxy that weakens it.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status
from redis.exceptions import RedisError

from app.api.deps import (
    PrincipalAnnotated,
    SessionDep,
    SettingsDep,
    client_ip,
)
from app.core.errors import (
    AuthRateLimitedError,
    DependencyUnavailableError,
    ForbiddenError,
    UnauthorizedError,
)
from app.core.rate_limit import (
    check_sliding_window,
    login_account_key,
    login_ip_key,
    refresh_key,
    ticket_key,
)
from app.core.redis import RedisClient, get_redis_client
from app.core.security import clear_refresh_cookie, set_refresh_cookie
from app.core.tickets import issue_ws_ticket
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RefreshResponse,
    UserSummary,
    WsTicketResponse,
)
from app.schemas.common import ErrorResponse
from app.services.auth import AuthService

auth_router = APIRouter(prefix="/auth", tags=["auth"])

RedisClientDep = Annotated[RedisClient, Depends(get_redis_client)]

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


def _summary(
    user_id: uuid.UUID, email: str, role: str, is_active: bool, must_change: bool
) -> UserSummary:
    return UserSummary(
        id=user_id,
        email=email,
        role=role,
        is_active=is_active,
        must_change_password=must_change,
    )


async def _enforce(
    redis: RedisClient,
    *,
    key: str,
    limit: int,
    window_seconds: int = 60,
) -> None:
    try:
        decision = await check_sliding_window(
            redis, key=key, limit=limit, window_seconds=window_seconds
        )
    except RedisError as exc:
        # Documented decision: authentication fails closed when the throttling
        # store is unavailable. Durable lockout still protects accounts.
        raise DependencyUnavailableError(
            "Authentication throttling is temporarily unavailable."
        ) from exc
    if not decision.allowed:
        raise AuthRateLimitedError(
            retry_after=decision.retry_after,
            details={"window_seconds": window_seconds},
        )


def enforce_csrf(request: Request, settings: SettingsDep) -> None:
    security = settings.security
    header = request.headers.get(security.csrf_header_name, "")
    if header != security.csrf_header_value:
        raise ForbiddenError(
            "The anti-CSRF header is missing or incorrect.",
            details={"reason": "csrf_header_invalid"},
        )
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.app.cors_origins:
        raise ForbiddenError(
            "The request origin is not allowed.",
            details={"reason": "origin_not_allowed"},
        )


@auth_router.post(
    "/login",
    response_model=LoginResponse,
    operation_id="auth_login",
    summary="Sign in and receive an access token",
    description=(
        "Verifies the password with Argon2id, applies durable lockout after repeated "
        "failures and returns a 15-minute access token plus an HttpOnly refresh cookie. "
        "Unknown emails and wrong passwords return an identical 401 response."
    ),
    responses=ERROR_RESPONSES,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": {
                        "email": "analyst@example.com",
                        "password": "Correct-Horse-Battery-2026!",
                    }
                }
            }
        }
    },
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    redis: RedisClientDep,
) -> LoginResponse:
    ip = client_ip(request)
    await _enforce(
        redis,
        key=login_ip_key(ip),
        limit=settings.security.rate_limit_login_per_minute,
    )
    await _enforce(
        redis,
        key=login_account_key(payload.email),
        limit=settings.security.rate_limit_login_account_per_minute,
    )
    result = await AuthService(session, settings).login(
        email=payload.email,
        password=payload.password,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
    )
    set_refresh_cookie(response, result.refresh_token, settings)
    return LoginResponse(
        access_token=result.access_token,
        expires_in=result.expires_in,
        user=_summary(
            result.user.id,
            result.user.email,
            result.user.role.name,
            result.user.is_active,
            result.user.must_change_password,
        ),
    )


@auth_router.post(
    "/refresh",
    response_model=RefreshResponse,
    operation_id="auth_refresh",
    summary="Rotate the refresh token and issue a new access token",
    description=(
        "Consumes the refresh cookie, revokes it, and issues a replacement in the same "
        "family. Replaying a consumed token revokes the entire family and returns "
        "AUTH_REFRESH_REUSE_DETECTED."
    ),
    responses=ERROR_RESPONSES,
)
async def refresh(
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    redis: RedisClientDep,
) -> RefreshResponse:
    enforce_csrf(request, settings)
    await _enforce(
        redis,
        key=refresh_key(client_ip(request)),
        limit=settings.security.rate_limit_refresh_per_minute,
    )
    raw = request.cookies.get(settings.security.refresh_cookie_name)
    result = await AuthService(session, settings).refresh(
        raw_token=raw,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    set_refresh_cookie(response, result.refresh_token, settings)
    return RefreshResponse(
        access_token=result.access_token,
        expires_in=result.expires_in,
        user=_summary(
            result.user.id,
            result.user.email,
            result.user.role.name,
            result.user.is_active,
            result.user.must_change_password,
        ),
    )


@auth_router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="auth_logout",
    summary="Revoke the current refresh-token family",
    description="Requires the anti-CSRF header. Always clears the cookie, even if it was absent.",
    responses=ERROR_RESPONSES,
)
async def logout(
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    enforce_csrf(request, settings)
    raw = request.cookies.get(settings.security.refresh_cookie_name)
    await AuthService(session, settings).logout(raw_token=raw, ip_address=client_ip(request))
    clear_refresh_cookie(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@auth_router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="auth_logout_all",
    summary="Revoke every refresh token for the signed-in user",
    responses=ERROR_RESPONSES,
)
async def logout_all(
    request: Request,
    response: Response,
    principal: PrincipalAnnotated,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    if principal.user_id is None:
        raise UnauthorizedError()
    await AuthService(session, settings).logout_all(
        user_id=principal.user_id, ip_address=client_ip(request)
    )
    clear_refresh_cookie(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@auth_router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="auth_change_password",
    summary="Change the signed-in user's password",
    description=(
        "Enforces the password policy (minimum length, common-password denylist, no reuse), "
        "revokes every refresh token and audits the change."
    ),
    responses=ERROR_RESPONSES,
)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    principal: PrincipalAnnotated,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    if principal.user_id is None:
        raise UnauthorizedError()
    await AuthService(session, settings).change_password(
        user_id=principal.user_id,
        current_password=payload.current_password,
        new_password=payload.new_password,
        ip_address=client_ip(request),
    )
    clear_refresh_cookie(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@auth_router.post(
    "/ws-ticket",
    response_model=WsTicketResponse,
    operation_id="auth_ws_ticket",
    summary="Issue a single-use WebSocket ticket",
    description=(
        "Stores a hashed ticket in Redis for 30 seconds, bound to the user and client IP. "
        "The WebSocket handshake consumes it with GETDEL so it cannot be replayed."
    ),
    responses=ERROR_RESPONSES,
)
async def ws_ticket(
    request: Request,
    principal: PrincipalAnnotated,
    settings: SettingsDep,
    redis: RedisClientDep,
) -> WsTicketResponse:
    if principal.user_id is None:
        raise UnauthorizedError()
    if principal.must_change_password:
        raise ForbiddenError(
            "The password must be changed before opening a WebSocket.",
            details={"reason": "password_change_required"},
        )
    await _enforce(
        redis,
        key=ticket_key(str(principal.user_id)),
        limit=settings.security.rate_limit_ticket_per_minute,
    )
    raw = await issue_ws_ticket(
        redis,
        user_id=principal.user_id,
        ip_address=client_ip(request),
        ttl_seconds=settings.security.ws_ticket_ttl_seconds,
    )
    return WsTicketResponse(ticket=raw, expires_in=settings.security.ws_ticket_ttl_seconds)


@auth_router.get(
    "/me",
    response_model=MeResponse,
    operation_id="auth_me",
    summary="Return the current principal and effective permissions",
    description=(
        "The user, role and lockout state are read from PostgreSQL on every request. "
        "Permissions are resolved server-side from the role and are never put in the JWT."
    ),
    responses=ERROR_RESPONSES,
)
async def me(principal: PrincipalAnnotated, session: SessionDep) -> MeResponse:
    if principal.user_id is None:
        raise UnauthorizedError()
    from app.repositories.identity import UserRepository

    user = await UserRepository(session).get_with_role(principal.user_id)
    if user is None:
        raise UnauthorizedError("The account is not available.")
    return MeResponse(
        id=user.id,
        email=user.email,
        role=user.role.name,
        permissions=sorted(principal.permissions),
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
        password_changed_at=user.password_changed_at,
    )
