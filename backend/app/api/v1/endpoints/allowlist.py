"""Allow-list administration.

Entries carry an expiry and a mandatory reason. ``DELETE`` deactivates rather than
removing the row so the justification remains auditable. Values are parsed with
``ipaddress``/URL/domain/hash validators before they can influence the Phase 7
response engine.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.deps import Principal, SessionDep, client_ip, require_permission
from app.models.responses import AllowlistEntry
from app.repositories.responses import AllowlistRepository
from app.schemas.admin import (
    AllowlistCreateRequest,
    AllowlistResponse,
    AllowlistUpdateRequest,
)
from app.schemas.common import ErrorResponse, PageResponse
from app.services.admin import AllowlistAdminService

allowlist_router = APIRouter(prefix="/allowlist", tags=["admin"])

AllowlistAdmin = Annotated[Principal, Depends(require_permission("allowlist:write"))]

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}


def _to_response(entry: AllowlistEntry) -> AllowlistResponse:
    return AllowlistResponse(
        id=entry.id,
        entry_type=entry.entry_type,
        value=entry.value,
        reason=entry.reason,
        expires_at=entry.expires_at,
        is_active=entry.is_active,
        created_by=entry.created_by,
        created_at=entry.created_at,
    )


@allowlist_router.get(
    "",
    response_model=PageResponse[AllowlistResponse],
    operation_id="admin_list_allowlist",
    summary="List allow-list entries (keyset paginated)",
    description="Requires ``allowlist:write`` (ADMIN).",
    responses=ERROR_RESPONSES,
)
async def list_allowlist(
    _principal: AllowlistAdmin,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    entry_type: str | None = Query(default=None, pattern="^(IP|CIDR|DOMAIN|URL|HASH|USER)$"),
    is_active: bool | None = Query(default=None),
) -> PageResponse[AllowlistResponse]:
    page = await AllowlistRepository(session).list_page(
        limit=limit, cursor=cursor, entry_type=entry_type, is_active=is_active
    )
    return PageResponse[AllowlistResponse](
        items=[_to_response(entry) for entry in page.items], next_cursor=page.next_cursor
    )


@allowlist_router.post(
    "",
    response_model=AllowlistResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="admin_create_allowlist_entry",
    summary="Create an allow-list entry",
    description=(
        "Requires ``allowlist:write`` (ADMIN). IP/CIDR/DOMAIN/URL/HASH/USER values are "
        "strictly validated and normalised; a reason and an optional future expiry are "
        "mandatory context."
    ),
    responses=ERROR_RESPONSES,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": {
                        "entry_type": "CIDR",
                        "value": "203.0.113.0/24",
                        "reason": "Corporate vulnerability scanner",
                        "expires_at": "2026-12-31T00:00:00Z",
                    }
                }
            }
        }
    },
)
async def create_allowlist_entry(
    payload: AllowlistCreateRequest,
    request: Request,
    principal: AllowlistAdmin,
    session: SessionDep,
) -> AllowlistResponse:
    entry = await AllowlistAdminService(session).create(
        actor_id=principal.user_id or uuid.uuid4(),
        entry_type=payload.entry_type,
        value=payload.value,
        reason=payload.reason,
        expires_at=payload.expires_at,
        ip_address=client_ip(request),
    )
    return _to_response(entry)


@allowlist_router.patch(
    "/{entry_id}",
    response_model=AllowlistResponse,
    operation_id="admin_update_allowlist_entry",
    summary="Update the reason or expiry of an entry",
    responses=ERROR_RESPONSES,
)
async def update_allowlist_entry(
    entry_id: uuid.UUID,
    payload: AllowlistUpdateRequest,
    request: Request,
    principal: AllowlistAdmin,
    session: SessionDep,
) -> AllowlistResponse:
    entry = await AllowlistAdminService(session).update(
        actor_id=principal.user_id or uuid.uuid4(),
        entry_id=entry_id,
        reason=payload.reason,
        expires_at=payload.expires_at,
        ip_address=client_ip(request),
    )
    return _to_response(entry)


@allowlist_router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="admin_deactivate_allowlist_entry",
    summary="Deactivate an allow-list entry",
    description="Requires ``allowlist:write`` (ADMIN). Delete means deactivate; history is kept.",
    responses=ERROR_RESPONSES,
)
async def deactivate_allowlist_entry(
    entry_id: uuid.UUID,
    request: Request,
    principal: AllowlistAdmin,
    session: SessionDep,
) -> Response:
    await AllowlistAdminService(session).deactivate(
        actor_id=principal.user_id or uuid.uuid4(),
        entry_id=entry_id,
        ip_address=client_ip(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
