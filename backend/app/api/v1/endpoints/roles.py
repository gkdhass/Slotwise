"""Read-only role catalogue with the effective permission bundle per role.

Permissions live in code (``app/policies/permissions.py``), so this endpoint is a
projection, not a second source of truth. It is exposed so the admin UI can render
capability badges without hard-coding the matrix.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import Principal, SessionDep, require_permission
from app.policies.permissions import permissions_for
from app.repositories.identity import RoleRepository
from app.schemas.admin import RoleResponse
from app.schemas.common import ErrorResponse

roles_router = APIRouter(prefix="/roles", tags=["admin"])

RolesAdmin = Annotated[Principal, Depends(require_permission("roles:manage"))]

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
}


@roles_router.get(
    "",
    response_model=list[RoleResponse],
    operation_id="admin_list_roles",
    summary="List roles and their permission bundles",
    description=(
        "Requires ``roles:manage``. The ML-operator bundle (datasets:write, "
        "training:run, models:promote, models:retire) appears only on ADMIN."
    ),
    responses=ERROR_RESPONSES,
)
async def list_roles(_principal: RolesAdmin, session: SessionDep) -> list[RoleResponse]:
    roles = await RoleRepository(session).list_all()
    return [
        RoleResponse(
            name=role.name,
            description=role.description,
            permissions=sorted(permissions_for(role.name)),
        )
        for role in roles
    ]
