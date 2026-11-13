"""Versioned response policies.

Versions are immutable: creating a policy always appends a new row whose
``supersedes_id`` points at the current version, and only ``enabled`` may be
toggled. A database trigger (Phase 3 migration) enforces the same rule for direct
SQL clients, and high-impact actions may never be stored without approval.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import Principal, SessionDep, SettingsDep, client_ip, require_permission
from app.core.errors import NotFoundError
from app.models.responses import ResponsePolicy
from app.repositories.responses import ResponsePolicyRepository
from app.schemas.admin import ResponsePolicyCreateRequest, ResponsePolicyResponse
from app.schemas.common import ErrorResponse, PageResponse
from app.services.admin import PolicyAdminService

policies_router = APIRouter(prefix="/response-policies", tags=["admin"])

PoliciesAdmin = Annotated[Principal, Depends(require_permission("policies:write"))]

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}


def _to_response(policy: ResponsePolicy) -> ResponsePolicyResponse:
    return ResponsePolicyResponse(
        id=policy.id,
        name=policy.name,
        version=policy.version,
        supersedes_id=policy.supersedes_id,
        action_type=policy.action_type,
        conditions=policy.conditions,
        requires_approval=policy.requires_approval,
        enabled=policy.enabled,
        created_by=policy.created_by,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


@policies_router.get(
    "",
    response_model=PageResponse[ResponsePolicyResponse],
    operation_id="admin_list_response_policies",
    summary="List response policy versions (keyset paginated)",
    description="Requires ``policies:write`` (ADMIN).",
    responses=ERROR_RESPONSES,
)
async def list_policies(
    _principal: PoliciesAdmin,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    name: str | None = Query(default=None, max_length=200),
    action_type: str | None = Query(default=None, max_length=32),
    enabled: bool | None = Query(default=None),
) -> PageResponse[ResponsePolicyResponse]:
    page = await ResponsePolicyRepository(session).list_page(
        limit=limit, cursor=cursor, name=name, action_type=action_type, enabled=enabled
    )
    return PageResponse[ResponsePolicyResponse](
        items=[_to_response(policy) for policy in page.items], next_cursor=page.next_cursor
    )


@policies_router.get(
    "/{name}/versions",
    response_model=list[ResponsePolicyResponse],
    operation_id="admin_list_response_policy_versions",
    summary="List every version of a named policy, newest first",
    responses=ERROR_RESPONSES,
)
async def list_policy_versions(
    name: str, _principal: PoliciesAdmin, session: SessionDep
) -> list[ResponsePolicyResponse]:
    versions = await ResponsePolicyRepository(session).list_versions(name)
    if not versions:
        raise NotFoundError("Response policy not found.")
    return [_to_response(policy) for policy in versions]


@policies_router.post(
    "",
    response_model=ResponsePolicyResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="admin_create_response_policy_version",
    summary="Create a new immutable policy version",
    description=(
        "Requires ``policies:write`` (ADMIN). High-impact actions (BLOCK_IP, "
        "ISOLATE_HOST, DISABLE_ACCOUNT, QUARANTINE_FILE) are refused when "
        "``requires_approval`` is false."
    ),
    responses=ERROR_RESPONSES,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": {
                        "name": "block-c2-callbacks",
                        "action_type": "BLOCK_IP",
                        "conditions": {"severity": "HIGH"},
                        "requires_approval": True,
                        "enabled": True,
                    }
                }
            }
        }
    },
)
async def create_policy_version(
    payload: ResponsePolicyCreateRequest,
    request: Request,
    principal: PoliciesAdmin,
    session: SessionDep,
    settings: SettingsDep,
) -> ResponsePolicyResponse:
    policy = await PolicyAdminService(session, settings).create_version(
        actor_id=principal.user_id or uuid.uuid4(),
        name=payload.name,
        action_type=payload.action_type,
        conditions=payload.conditions,
        requires_approval=payload.requires_approval,
        enabled=payload.enabled,
        supersedes_id=payload.supersedes_id,
        ip_address=client_ip(request),
    )
    return _to_response(policy)


async def _set_enabled(
    *,
    policy_id: uuid.UUID,
    enabled: bool,
    request: Request,
    principal: Principal,
    session: SessionDep,
    settings: SettingsDep,
) -> ResponsePolicyResponse:
    policy = await PolicyAdminService(session, settings).set_enabled(
        actor_id=principal.user_id or uuid.uuid4(),
        policy_id=policy_id,
        enabled=enabled,
        ip_address=client_ip(request),
    )
    return _to_response(policy)


@policies_router.post(
    "/{policy_id}/enable",
    response_model=ResponsePolicyResponse,
    operation_id="admin_enable_response_policy",
    summary="Enable a policy version",
    responses=ERROR_RESPONSES,
)
async def enable_policy(
    policy_id: uuid.UUID,
    request: Request,
    principal: PoliciesAdmin,
    session: SessionDep,
    settings: SettingsDep,
) -> ResponsePolicyResponse:
    return await _set_enabled(
        policy_id=policy_id,
        enabled=True,
        request=request,
        principal=principal,
        session=session,
        settings=settings,
    )


@policies_router.post(
    "/{policy_id}/disable",
    response_model=ResponsePolicyResponse,
    operation_id="admin_disable_response_policy",
    summary="Disable a policy version",
    responses=ERROR_RESPONSES,
)
async def disable_policy(
    policy_id: uuid.UUID,
    request: Request,
    principal: PoliciesAdmin,
    session: SessionDep,
    settings: SettingsDep,
) -> ResponsePolicyResponse:
    return await _set_enabled(
        policy_id=policy_id,
        enabled=False,
        request=request,
        principal=principal,
        session=session,
        settings=settings,
    )
