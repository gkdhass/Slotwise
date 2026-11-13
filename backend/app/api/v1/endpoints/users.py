"""User administration.

Every route requires ``users:manage`` (ADMIN). Deactivation is the only removal
path: audit foreign keys are ``ON DELETE SET NULL`` and the Phase 2 trigger blocks
the resulting update, so hard deletion is never offered.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import (
    Principal,
    SessionDep,
    SettingsDep,
    client_ip,
    require_permission,
)
from app.models.identity import User
from app.schemas.admin import (
    ResetPasswordResponse,
    UserCreateRequest,
    UserCreateResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.schemas.common import ErrorResponse, PageResponse
from app.services.admin import UserAdminService

users_router = APIRouter(prefix="/users", tags=["admin"])

UsersAdmin = Annotated[Principal, Depends(require_permission("users:manage"))]

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}


def _to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role.name,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        failed_login_count=user.failed_login_count,
        locked_until=user.locked_until,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


def _service(session: SessionDep, settings: SettingsDep) -> UserAdminService:
    return UserAdminService(session, settings)


@users_router.get(
    "",
    response_model=PageResponse[UserResponse],
    operation_id="admin_list_users",
    summary="List users (keyset paginated)",
    description="Requires ``users:manage``. Filters are whitelisted: role and active state.",
    responses=ERROR_RESPONSES,
)
async def list_users(
    _principal: UsersAdmin,
    session: SessionDep,
    settings: SettingsDep,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, description="Opaque cursor from the previous page."),
    role: str | None = Query(default=None, pattern="^(ADMIN|ANALYST|VIEWER)$"),
    is_active: bool | None = Query(default=None),
) -> PageResponse[UserResponse]:
    page = await _service(session, settings).users.list_page(
        limit=limit, cursor=cursor, role=role, is_active=is_active
    )
    return PageResponse[UserResponse](
        items=[_to_response(user) for user in page.items], next_cursor=page.next_cursor
    )


@users_router.get(
    "/{user_id}",
    response_model=UserResponse,
    operation_id="admin_get_user",
    summary="Get one user",
    responses=ERROR_RESPONSES,
)
async def get_user(
    user_id: uuid.UUID,
    _principal: UsersAdmin,
    session: SessionDep,
    settings: SettingsDep,
) -> UserResponse:
    return _to_response(await _service(session, settings)._target(user_id))


@users_router.post(
    "",
    response_model=UserCreateResponse,
    status_code=201,
    operation_id="admin_create_user",
    summary="Create a user",
    description=(
        "Requires ``users:manage``. When no password is supplied a policy-compliant "
        "temporary password is generated, returned exactly once, and "
        "``must_change_password`` is set."
    ),
    responses=ERROR_RESPONSES,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": {
                        "email": "analyst@example.com",
                        "role": "ANALYST",
                    }
                }
            }
        }
    },
)
async def create_user(
    payload: UserCreateRequest,
    request: Request,
    principal: UsersAdmin,
    session: SessionDep,
    settings: SettingsDep,
) -> UserCreateResponse:
    user, temporary = await _service(session, settings).create_user(
        actor_id=principal.user_id or uuid.uuid4(),
        email=payload.email,
        role_name=payload.role,
        password=payload.password,
        ip_address=client_ip(request),
    )
    return UserCreateResponse(
        user=_to_response(user),
        temporary_password=temporary,
        password_generated=temporary is not None,
    )


@users_router.patch(
    "/{user_id}",
    response_model=UserResponse,
    operation_id="admin_update_user",
    summary="Update email, role or active state",
    description=(
        "Requires ``users:manage``. Cannot remove your own administrator role and "
        "cannot demote or deactivate the last active administrator."
    ),
    responses=ERROR_RESPONSES,
)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    request: Request,
    principal: UsersAdmin,
    session: SessionDep,
    settings: SettingsDep,
) -> UserResponse:
    user = await _service(session, settings).update_user(
        actor_id=principal.user_id or uuid.uuid4(),
        user_id=user_id,
        email=payload.email,
        role_name=payload.role,
        is_active=payload.is_active,
        ip_address=client_ip(request),
    )
    return _to_response(user)


@users_router.post(
    "/{user_id}/deactivate",
    response_model=UserResponse,
    operation_id="admin_deactivate_user",
    summary="Deactivate a user (no hard delete)",
    responses=ERROR_RESPONSES,
)
async def deactivate_user(
    user_id: uuid.UUID,
    request: Request,
    principal: UsersAdmin,
    session: SessionDep,
    settings: SettingsDep,
) -> UserResponse:
    user = await _service(session, settings).set_active(
        actor_id=principal.user_id or uuid.uuid4(),
        user_id=user_id,
        active=False,
        ip_address=client_ip(request),
    )
    return _to_response(user)


@users_router.post(
    "/{user_id}/reactivate",
    response_model=UserResponse,
    operation_id="admin_reactivate_user",
    summary="Reactivate a user",
    responses=ERROR_RESPONSES,
)
async def reactivate_user(
    user_id: uuid.UUID,
    request: Request,
    principal: UsersAdmin,
    session: SessionDep,
    settings: SettingsDep,
) -> UserResponse:
    user = await _service(session, settings).set_active(
        actor_id=principal.user_id or uuid.uuid4(),
        user_id=user_id,
        active=True,
        ip_address=client_ip(request),
    )
    return _to_response(user)


@users_router.post(
    "/{user_id}/unlock",
    response_model=UserResponse,
    operation_id="admin_unlock_user",
    summary="Clear a durable account lockout",
    description="Requires ``users:manage``. Audited as ``AUTH_ACCOUNT_UNLOCKED``.",
    responses=ERROR_RESPONSES,
)
async def unlock_user(
    user_id: uuid.UUID,
    request: Request,
    principal: UsersAdmin,
    session: SessionDep,
    settings: SettingsDep,
) -> UserResponse:
    user = await _service(session, settings).unlock(
        actor_id=principal.user_id or uuid.uuid4(),
        user_id=user_id,
        ip_address=client_ip(request),
    )
    return _to_response(user)


@users_router.post(
    "/{user_id}/reset-password",
    response_model=ResetPasswordResponse,
    operation_id="admin_reset_password",
    summary="Reset a password and return a one-time temporary password",
    description=(
        "Requires ``users:manage``. Revokes every refresh token for the user, sets "
        "``must_change_password`` and never stores the temporary password."
    ),
    responses=ERROR_RESPONSES,
)
async def reset_password(
    user_id: uuid.UUID,
    request: Request,
    principal: UsersAdmin,
    session: SessionDep,
    settings: SettingsDep,
) -> ResetPasswordResponse:
    user, temporary = await _service(session, settings).reset_password(
        actor_id=principal.user_id or uuid.uuid4(),
        user_id=user_id,
        ip_address=client_ip(request),
    )
    return ResetPasswordResponse(
        user_id=user.id, temporary_password=temporary, must_change_password=True
    )
