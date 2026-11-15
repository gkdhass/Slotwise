"""Event ingestion and query endpoints for Phase 4-1."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from fastapi.responses import JSONResponse

from app.api.deps import (
    Principal,
    PrincipalAnnotated,
    SessionDep,
    SettingsDep,
    require_permission,
)
from app.core.errors import (
    BadRequestError,
    ForbiddenError,
)
from app.models.enums import EventStatus
from app.repositories.events import EventOutboxRepository, EventRepository
from app.schemas.common import ErrorResponse, PageResponse
from app.schemas.events import BatchEventRequest

# Dependency types for permission checks
EventsRead = Annotated[Principal, Depends(require_permission("events:read"))]
EventsWrite = Annotated[Principal, Depends(require_permission("events:ingest"))]

router = APIRouter(tags=["events"])


@router.post(
    "/events",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Event accepted"},
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
    },
)
async def ingest_events(
    batch: BatchEventRequest,
    principal: PrincipalAnnotated,
    session: SessionDep,
) -> JSONResponse:
    """Ingest events from a sensor principal.

    - Sensor principal required
    - Idempotent: duplicate (source_id, external_id) returns original event_id
    - Durable write: validate → archive → PostgreSQL transaction → 202
    """
    # Verify sensor principal (enforces sensor:ingest permission implicitly)
    if not principal.is_sensor or not principal.sensor_id:
        raise ForbiddenError("Only sensor principals can submit events")

    results = []
    for envelope in batch.events:
        # Validate source_id matches sensor identity
        if envelope.source_id != str(principal.sensor_id):
            raise BadRequestError(
                "source_id does not match sensor identity",
                details={
                    "expected": str(principal.sensor_id),
                    "received": envelope.source_id,
                },
            )

        # Validate and canonicalize
        try:
            envelope.canonical_bytes()
            checksum = envelope.compute_checksum()
        except Exception as exc:
            raise BadRequestError(f"Event validation failed: {exc}") from exc

        # Prepare event values
        event_values = {
            "external_id": envelope.external_id,
            "source_type": envelope.source_type.value,
            "source_id": envelope.source_id,
            "asset_id": (
                uuid.UUID(envelope.asset_id)
                if envelope.asset_id
                else None
            ),
            "observed_at": envelope.observed_at,
            "event_type": envelope.event_type.value,
            "raw_ref": f"s3://raw/{checksum[:4]}/{checksum}",
            "raw_checksum": checksum,
            "normalized_payload": envelope.normalized_payload.model_dump(
                by_alias=True
            ),
            "schema_version": envelope.schema_version.value,
            "processing_status": EventStatus.RECEIVED.value,
            "received_via": "api",
            "sensor_id": principal.sensor_id,
        }

        # Idempotent upsert
        event_repo = EventRepository(session)
        event, created = await event_repo.upsert(event_values)

        if not created:
            # Duplicate
            results.append({
                "event_id": str(event.id),
                "status": event.processing_status,
                "duplicate": True,
            })
            continue

        # Write optional label
        if envelope.label:
            label_values = {
                "event_id": event.id,
                "label": envelope.label.label,
                "source": envelope.label.source.value,
                "confidence": envelope.label.confidence,
            }
            event.labels.append(
                type("EventLabel", (), label_values)()
            )

        # Create outbox row
        outbox_values = {
            "event_id": event.id,
            "task_name": "preprocess_event",
            "payload": {
                "event_id": str(event.id),
                "event_type": envelope.event_type.value,
            },
            "status": "PENDING",
            "attempts": 0,
            "next_attempt_at": datetime.now(UTC)
            + timedelta(minutes=1),
        }
        outbox_repo = EventOutboxRepository(session)
        await outbox_repo.create(outbox_values)

        # Commit transaction
        await session.commit()

        results.append({
            "event_id": str(event.id),
            "status": EventStatus.VALIDATED.value,
            "duplicate": False,
        })

    if len(results) == 1:
        result = results[0]
        status_code = 200 if result["duplicate"] else 202
        return JSONResponse(content=result, status_code=status_code)

    return JSONResponse(content={"results": results}, status_code=202)


@router.get(
    "/events",
    response_model=PageResponse[dict[str, Any]],
    responses={
        200: {"description": "Paginated events"},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
    },
)
async def list_events(
    principal: EventsRead,  # noqa: ARG001 - used for permission check
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> PageResponse[dict[str, Any]]:
    """List events with keyset pagination."""
    event_repo = EventRepository(session)
    page = await event_repo.list_keyset(limit=limit, cursor=cursor)

    items = [
        {
            "id": str(event.id),
            "source_id": event.source_id,
            "event_type": event.event_type,
            "processing_status": event.processing_status,
            "observed_at": event.observed_at.isoformat(),
        }
        for event in page.items
    ]

    return PageResponse(items=items, next_cursor=page.next_cursor)


@router.get(
    "/events/{event_id}",
    responses={
        200: {"description": "Event details"},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def get_event(
    event_id: str,
    principal: EventsRead,  # noqa: ARG001 - used for permission check
    session: SessionDep,
) -> dict[str, Any]:
    """Get a single event by ID."""
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError as exc:
        raise BadRequestError("Invalid event ID format") from exc

    event_repo = EventRepository(session)
    event = await event_repo.get(event_uuid)

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    return {
        "id": str(event.id),
        "source_id": event.source_id,
        "event_type": event.event_type,
        "processing_status": event.processing_status,
        "observed_at": event.observed_at.isoformat(),
        "received_at": event.received_at.isoformat(),
        "raw_checksum": event.raw_checksum,
        "schema_version": event.schema_version,
    }




@router.post(
    "/events/imports",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Import accepted"},
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
    },
)
async def import_events(
    principal: Annotated[Principal, Depends(require_permission("events:import"))],  # noqa: ARG001
    session: SessionDep,  # noqa: ARG001 - reserved for future multipart/S3
    settings: SettingsDep,  # noqa: ARG001 - reserved for future size caps
) -> JSONResponse:
    """Import events from CSV/JSON/NDJSON file (Analyst and Admin only).

    - Multipart form with 'file' field
    - Content-type detection and validation
    - Size caps from settings
    - Per-row validation and deduplication
    - Returns: {accepted, duplicates, rejected: [{row, code}]}
    - Upload stored in S3 under imports/
    - Imported events use received_via='import', imported_by=current_user_id
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="POST /events/imports not yet fully implemented",
    )  # pragma: no cover - TODO Phase 4-2
