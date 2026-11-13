"""Asset administration.

Deletion is soft: events reference assets, so ``DELETE`` sets ``is_active=false``
and keeps the row. That preserves historical joins and matches the platform-wide
rule that evidence is never destructively removed.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import Principal, SessionDep, client_ip, require_permission
from app.core.errors import ConflictError, NotFoundError
from app.models.assets import Asset
from app.repositories.assets import AssetRepository
from app.repositories.audit import AuditRepository
from app.schemas.admin import AssetCreateRequest, AssetResponse, AssetUpdateRequest
from app.schemas.common import ErrorResponse, PageResponse

assets_router = APIRouter(prefix="/assets", tags=["admin"])

AssetsRead = Annotated[Principal, Depends(require_permission("assets:read"))]
AssetsWrite = Annotated[Principal, Depends(require_permission("assets:write"))]

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}


def _to_response(asset: Asset) -> AssetResponse:
    return AssetResponse(
        id=asset.id,
        name=asset.name,
        asset_type=asset.asset_type,
        criticality=asset.criticality,
        owner_team=asset.owner_team,
        environment=asset.environment,
        is_active=asset.is_active,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def _snapshot(asset: Asset) -> dict[str, object]:
    return {
        "name": asset.name,
        "asset_type": asset.asset_type,
        "criticality": asset.criticality,
        "owner_team": asset.owner_team,
        "environment": asset.environment,
        "is_active": asset.is_active,
    }


async def _target(session: SessionDep, asset_id: uuid.UUID) -> Asset:
    asset = await AssetRepository(session).get(asset_id)
    if asset is None:
        raise NotFoundError("Asset not found.")
    return asset


@assets_router.get(
    "",
    response_model=PageResponse[AssetResponse],
    operation_id="admin_list_assets",
    summary="List assets (keyset paginated)",
    description="Requires ``assets:read``, which every role holds.",
    responses=ERROR_RESPONSES,
)
async def list_assets(
    _principal: AssetsRead,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    criticality: str | None = Query(default=None, pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$"),
    environment: str | None = Query(default=None, pattern="^(DEV|STAGING|PROD)$"),
    is_active: bool | None = Query(default=None),
) -> PageResponse[AssetResponse]:
    page = await AssetRepository(session).list_page(
        limit=limit,
        cursor=cursor,
        criticality=criticality,
        environment=environment,
        is_active=is_active,
    )
    return PageResponse[AssetResponse](
        items=[_to_response(asset) for asset in page.items], next_cursor=page.next_cursor
    )


@assets_router.get(
    "/{asset_id}",
    response_model=AssetResponse,
    operation_id="admin_get_asset",
    summary="Get one asset",
    responses=ERROR_RESPONSES,
)
async def get_asset(
    asset_id: uuid.UUID, _principal: AssetsRead, session: SessionDep
) -> AssetResponse:
    return _to_response(await _target(session, asset_id))


@assets_router.post(
    "",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="admin_create_asset",
    summary="Create an asset",
    description="Requires ``assets:write`` (ADMIN).",
    responses=ERROR_RESPONSES,
)
async def create_asset(
    payload: AssetCreateRequest,
    request: Request,
    principal: AssetsWrite,
    session: SessionDep,
) -> AssetResponse:
    asset = Asset(
        name=payload.name,
        asset_type=payload.asset_type,
        criticality=payload.criticality,
        owner_team=payload.owner_team,
        environment=payload.environment,
        is_active=payload.is_active,
    )
    session.add(asset)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("An asset with that name already exists.") from exc
    await AuditRepository(session).record(
        actor_id=principal.user_id,
        action="ASSET_CREATED",
        entity_type="asset",
        entity_id=asset.id,
        after=_snapshot(asset),
        ip_address=client_ip(request),
    )
    await session.commit()
    return _to_response(asset)


@assets_router.patch(
    "/{asset_id}",
    response_model=AssetResponse,
    operation_id="admin_update_asset",
    summary="Update an asset",
    description="Requires ``assets:write`` (ADMIN).",
    responses=ERROR_RESPONSES,
)
async def update_asset(
    asset_id: uuid.UUID,
    payload: AssetUpdateRequest,
    request: Request,
    principal: AssetsWrite,
    session: SessionDep,
) -> AssetResponse:
    asset = await _target(session, asset_id)
    before = _snapshot(asset)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(asset, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("An asset with that name already exists.") from exc
    await AuditRepository(session).record(
        actor_id=principal.user_id,
        action="ASSET_UPDATED",
        entity_type="asset",
        entity_id=asset.id,
        before=before,
        after=_snapshot(asset),
        ip_address=client_ip(request),
    )
    await session.commit()
    return _to_response(asset)


@assets_router.delete(
    "/{asset_id}",
    response_model=AssetResponse,
    operation_id="admin_deactivate_asset",
    summary="Deactivate an asset (soft delete)",
    description=(
        "Requires ``assets:write`` (ADMIN). Events reference assets, so the row is "
        "retained with ``is_active=false`` instead of being deleted."
    ),
    responses=ERROR_RESPONSES,
)
async def deactivate_asset(
    asset_id: uuid.UUID,
    request: Request,
    principal: AssetsWrite,
    session: SessionDep,
) -> AssetResponse:
    asset = await _target(session, asset_id)
    before = _snapshot(asset)
    asset.is_active = False
    await session.flush()
    await AuditRepository(session).record(
        actor_id=principal.user_id,
        action="ASSET_DEACTIVATED",
        entity_type="asset",
        entity_id=asset.id,
        before=before,
        after=_snapshot(asset),
        ip_address=client_ip(request),
    )
    await session.commit()
    return _to_response(asset)
