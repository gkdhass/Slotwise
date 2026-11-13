"""Sensor administration and the sensor machine principal.

A sensor key is a separate principal: it may only heartbeat (and, from Phase 4,
submit events). It is rejected everywhere a human JWT is required, and a human JWT
is rejected here. The raw key is shown exactly once; only the prefix and a hash are
stored.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import (
    Principal,
    SessionDep,
    client_ip,
    get_current_sensor,
    require_permission,
)
from app.core.errors import NotFoundError
from app.models.assets import Sensor
from app.repositories.assets import SensorRepository
from app.schemas.admin import (
    SensorCreatedResponse,
    SensorCreateRequest,
    SensorResponse,
    SensorRotateResponse,
)
from app.schemas.common import ErrorResponse, PageResponse
from app.services.admin import SensorAdminService

sensors_router = APIRouter(prefix="/sensors", tags=["admin"])

SensorsAdmin = Annotated[Principal, Depends(require_permission("sensors:manage"))]
SensorPrincipal = Annotated[Principal, Depends(get_current_sensor)]

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


def _to_response(sensor: Sensor) -> SensorResponse:
    return SensorResponse(
        id=sensor.id,
        name=sensor.name,
        sensor_type=sensor.sensor_type,
        asset_id=sensor.asset_id,
        credential_prefix=sensor.credential_prefix,
        status=sensor.status,
        last_seen_at=sensor.last_seen_at,
        credential_rotated_at=sensor.credential_rotated_at,
        revoked_at=sensor.revoked_at,
        created_at=sensor.created_at,
    )


@sensors_router.get(
    "",
    response_model=PageResponse[SensorResponse],
    operation_id="admin_list_sensors",
    summary="List sensors (keyset paginated)",
    description="Requires ``sensors:manage``. Credential hashes are never returned.",
    responses=ERROR_RESPONSES,
)
async def list_sensors(
    _principal: SensorsAdmin,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(ACTIVE|INACTIVE|REVOKED)$"),
    sensor_type: str | None = Query(default=None, max_length=64),
) -> PageResponse[SensorResponse]:
    page = await SensorRepository(session).list_page(
        limit=limit, cursor=cursor, status=status, sensor_type=sensor_type
    )
    return PageResponse[SensorResponse](
        items=[_to_response(sensor) for sensor in page.items], next_cursor=page.next_cursor
    )


@sensors_router.post(
    "",
    response_model=SensorCreatedResponse,
    status_code=201,
    operation_id="admin_create_sensor",
    summary="Create a sensor and reveal its API key once",
    description=(
        "Requires ``sensors:manage``. The key has the form ``<prefix>.<secret>``; the "
        "secret is returned exactly once and only its SHA-256 digest is persisted."
    ),
    responses=ERROR_RESPONSES,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": {
                        "name": "edge-sensor-01",
                        "sensor_type": "zeek",
                        "asset_id": None,
                    }
                }
            }
        }
    },
)
async def create_sensor(
    payload: SensorCreateRequest,
    request: Request,
    principal: SensorsAdmin,
    session: SessionDep,
) -> SensorCreatedResponse:
    sensor, api_key = await SensorAdminService(session).create(
        actor_id=principal.user_id or uuid.uuid4(),
        name=payload.name,
        sensor_type=payload.sensor_type,
        asset_id=payload.asset_id,
        ip_address=client_ip(request),
    )
    return SensorCreatedResponse(sensor=_to_response(sensor), api_key=api_key)


@sensors_router.post(
    "/{sensor_id}/rotate",
    response_model=SensorRotateResponse,
    operation_id="admin_rotate_sensor_key",
    summary="Rotate a sensor API key",
    description="Requires ``sensors:manage``. The previous key stops working immediately.",
    responses=ERROR_RESPONSES,
)
async def rotate_sensor_key(
    sensor_id: uuid.UUID,
    request: Request,
    principal: SensorsAdmin,
    session: SessionDep,
) -> SensorRotateResponse:
    sensor, api_key = await SensorAdminService(session).rotate(
        actor_id=principal.user_id or uuid.uuid4(),
        sensor_id=sensor_id,
        ip_address=client_ip(request),
    )
    return SensorRotateResponse(sensor=_to_response(sensor), api_key=api_key)


@sensors_router.post(
    "/{sensor_id}/revoke",
    response_model=SensorResponse,
    operation_id="admin_revoke_sensor",
    summary="Revoke a sensor",
    description="Requires ``sensors:manage``. Revocation is permanent for that key.",
    responses=ERROR_RESPONSES,
)
async def revoke_sensor(
    sensor_id: uuid.UUID,
    request: Request,
    principal: SensorsAdmin,
    session: SessionDep,
) -> SensorResponse:
    sensor = await SensorAdminService(session).revoke(
        actor_id=principal.user_id or uuid.uuid4(),
        sensor_id=sensor_id,
        ip_address=client_ip(request),
    )
    return _to_response(sensor)


@sensors_router.post(
    "/heartbeat",
    response_model=SensorResponse,
    operation_id="sensor_heartbeat",
    summary="Sensor heartbeat",
    description=(
        "Authenticated by ``X-Sensor-Key`` only. A user JWT is rejected. Updates "
        "``last_seen_at``; it is the only capability available to a sensor principal "
        "until event submission lands in Phase 4."
    ),
    responses=ERROR_RESPONSES,
)
async def sensor_heartbeat(
    principal: SensorPrincipal,
    session: SessionDep,
) -> SensorResponse:
    sensor = await SensorRepository(session).get(principal.sensor_id or uuid.uuid4())
    if sensor is None:  # pragma: no cover - the dependency already resolved the row
        raise NotFoundError("Sensor not found.")
    sensor.last_seen_at = datetime.now(UTC)
    await session.flush()
    await session.commit()
    return _to_response(sensor)
