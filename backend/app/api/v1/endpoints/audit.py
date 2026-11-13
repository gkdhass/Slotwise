"""Read-only audit trail access.

There is deliberately no write path here: audit rows are produced by the audit
writer inside each domain transaction, and the database revokes UPDATE/DELETE on
``audit_logs`` from the runtime role. This endpoint only exposes already-redacted
rows to holders of ``audit:read`` (ADMIN).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import Principal, SessionDep, require_permission
from app.models.audit import AuditLog
from app.repositories.audit import AuditRepository
from app.schemas.admin import AuditLogResponse
from app.schemas.common import ErrorResponse, PageResponse

audit_router = APIRouter(prefix="/audit-logs", tags=["admin"])

AuditReader = Annotated[Principal, Depends(require_permission("audit:read"))]

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
}


def _to_response(entry: AuditLog) -> AuditLogResponse:
    return AuditLogResponse(
        id=entry.id,
        actor_id=entry.actor_id,
        action=entry.action,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        before=entry.before,
        after=entry.after,
        ip_address=str(entry.ip_address) if entry.ip_address is not None else None,
        created_at=entry.created_at,
    )


@audit_router.get(
    "",
    response_model=PageResponse[AuditLogResponse],
    operation_id="admin_list_audit_logs",
    summary="List audit records (read-only, keyset paginated)",
    description=(
        "Requires ``audit:read`` (ADMIN). Filters are whitelisted: actor, action, "
        "entity type/id and a created-at range. No endpoint can modify audit rows."
    ),
    responses=ERROR_RESPONSES,
)
async def list_audit_logs(
    _principal: AuditReader,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None, max_length=100),
    entity_type: str | None = Query(default=None, max_length=100),
    entity_id: uuid.UUID | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
) -> PageResponse[AuditLogResponse]:
    page = await AuditRepository(session).list_page(
        limit=limit,
        cursor=cursor,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        created_from=created_from,
        created_to=created_to,
    )
    return PageResponse[AuditLogResponse](
        items=[_to_response(entry) for entry in page.items], next_cursor=page.next_cursor
    )
