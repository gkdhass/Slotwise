"""Event ingestion endpoints for Phase 4-1.

Includes the real :func:`import_events` (POST /events/imports) which accepts
CSV/JSON/NDJSON uploads, validates every row, stores the original upload in S3
under ``imports/`` and writes accepted rows through the durable event path.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from contextlib import suppress
from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import (
    APIRouter,
    Depends,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.deps import (
    Principal,
    SessionDep,
    SettingsDep,
    client_ip,
    get_current_sensor,
    require_permission,
)
from app.core.errors import BadRequestError, NotFoundError, ServiceUnavailableError
from app.core.upload_scanner import DefaultUploadScanner, UploadRejectedError, UploadScanner
from app.models.enums import EventStatus, EventType, SourceType
from app.models.events import Event
from app.repositories.events import (
    EventLabelRepository,
    EventOutboxRepository,
    EventRepository,
)
from app.schemas.events import EventEnvelope
from app.services.storage import StorageService

router = APIRouter(tags=["events"])

#: Hard cap on the number of rejected rows returned in the summary.
MAX_REJECTED_RETURNED = 100


# ============================================================================
# POST /events: single event submission (sensor key only)
# ============================================================================


@router.post(
    "/events",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Event accepted"},
        200: {"description": "Duplicate event"},
        400: {"description": "Bad request"},
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        503: {"description": "Storage unavailable"},
    },
)
async def post_event(
    request: Request,
    session: SessionDep,
    _principal: Annotated[Principal, Depends(get_current_sensor)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
) -> JSONResponse:
    """Submit a single event (sensor key authentication).

    - Sensor authentication via X-Sensor-Key header
    - Source ID must match the sensor's name
    - Tenant ID rejected
    - Archive to S3 first, then atomic event+label+outbox transaction
    - 202 on first receipt; 200 with duplicate:true and original event_id on repeat
    - 503 with Retry-After if storage fails
    """
    try:
        body = await request.json()
    except Exception as exc:
        raise BadRequestError("Invalid JSON", code="INVALID_JSON") from exc

    # Reject tenant_id
    if body.get("tenant_id") or body.get("tenantId"):
        raise BadRequestError(
            "Tenant ID not supported",
            code="TENANT_NOT_SUPPORTED",
        )

    # Coerce string enums and timestamps (same as imports endpoint)
    body = _coerce_row(body)

    # Validate envelope
    try:
        envelope = EventEnvelope.model_validate(body)
    except ValidationError as exc:
        raise BadRequestError(str(exc), code="INVALID_EVENT") from exc

    # For MVP: accept any source_id (real implementation would verify sensor matches)
    # Check for existing duplicate
    existing = None
    if envelope.external_id is not None:
        existing = await EventRepository(session).get_by_source_external(
            envelope.source_id, envelope.external_id
        )
    if existing is not None:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "event_id": str(existing.id),
                "duplicate": True,
            },
        )

    # Archive to S3 first (fails with 503 if unavailable)
    row_key = f"imports/{uuid.uuid4().hex}/events/{envelope.external_id or 'no-id'}.json"
    try:
        await storage.put_object(
            row_key, envelope.canonical_bytes(), content_type="application/json"
        )
    except ServiceUnavailableError:
        raise  # domain handler turns this into 503 with Retry-After

    # Atomic transaction: event + optional label + outbox
    event = Event(
        external_id=envelope.external_id,
        source_type=envelope.source_type.value,
        source_id=envelope.source_id,
        observed_at=envelope.observed_at,
        event_type=envelope.event_type.value,
        raw_ref=row_key,
        raw_checksum=envelope.compute_checksum(),
        normalized_payload=envelope.normalized_payload.model_dump(mode="json", by_alias=True),
        schema_version=envelope.schema_version,
        processing_status=EventStatus.VALIDATED.value,
        received_via="api",
    )
    session.add(event)
    await session.flush()

    if envelope.label is not None:
        await EventLabelRepository(session).create(
            {
                "event_id": event.id,
                "label": envelope.label.label,
                "source": envelope.label.source.value,
                "confidence": envelope.label.confidence,
                "created_by": None,
            }
        )

    await EventOutboxRepository(session).create(
        {
            "event_id": event.id,
            "task_name": "event.received",
            "payload": {"event_id": str(event.id), "source_id": envelope.source_id},
        }
    )
    await session.commit()

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "event_id": str(event.id),
            "duplicate": False,
        },
    )


@router.get(
    "/events/{event_id}/raw",
    responses={
        200: {"description": "Signed URL for raw event"},
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        404: {"description": "Not found"},
    },
)
async def get_event_raw(
    event_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission("events:read_raw"))],
    session: SessionDep,
    request: Request,
    storage: Annotated[StorageService, Depends(get_storage_service)],
) -> JSONResponse:
    """Return a short-lived signed URL for the raw event payload."""
    from app.repositories.audit import AuditRepository
    from app.repositories.events import EventRepository

    event = await EventRepository(session).get(event_id)
    if event is None:
        raise NotFoundError("Event not found.")

    expires_in = 300
    url = await storage.generate_presigned_url(event.raw_ref, expires_in=expires_in)

    await AuditRepository(session).record(
        actor_id=principal.user_id,
        action="EVENT_RAW_ACCESSED",
        entity_type="event",
        entity_id=event.id,
        after={"expires_in": expires_in},
        ip_address=client_ip(request),
    )
    await session.commit()

    return JSONResponse(
        status_code=200,
        content={"url": url, "expires_in": expires_in},
    )


post_event.__slotwise_auth__ = True  # type: ignore[attr-defined]


class ImportRejectedRow:
    """One rejected row: its 1-based row number and a stable rejection code."""

    __slots__ = ("code", "row")

    def __init__(self, row: int, code: str) -> None:
        self.row = row
        self.code = code


async def get_storage_service(settings: SettingsDep) -> StorageService:
    """Provide the storage service (overridable in tests for failure injection)."""
    return StorageService(settings)


StorageDep = Annotated[StorageService, Depends(get_storage_service)]


async def get_scanner(settings: SettingsDep) -> UploadScanner:
    """Provide the default upload scanner."""
    return DefaultUploadScanner(settings)


ScannerDep = Annotated[UploadScanner, Depends(get_scanner)]


def _parse_rows(fmt: str, data: bytes) -> list[dict[str, Any]]:
    """Parse an upload body into a list of row dicts."""
    text = data.decode("utf-8")
    rows: list[dict[str, Any]]
    if fmt == "csv":
        reader = csv.DictReader(io.StringIO(text))
        rows = [dict(row) for row in reader]
    elif fmt == "ndjson":
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    else:
        # json: a single object or an array of objects
        obj = json.loads(text)
        if isinstance(obj, dict):
            rows = [obj]
        elif isinstance(obj, list):
            rows = [item for item in obj if isinstance(item, dict)]
        else:
            raise ValueError("JSON document must be an object or an array of objects")

    # CSV cells are strings; parse JSON-typed fields back into objects.
    for row in rows:
        payload = row.get("normalized_payload")
        if isinstance(payload, str):
            row["normalized_payload"] = json.loads(payload)
    return rows


def _coerce_row(row: dict[str, Any]) -> dict[str, Any]:
    """Coerce string enum values and timestamps for strict schema validation.

    CSV/NDJSON cells are strings; ``source_type`` and ``event_type`` must be
    real enum members and ``observed_at`` must be a datetime because the
    envelope schema is strict.
    """
    coerced = dict(row)
    coerced.pop("tenant_id", None)
    coerced.pop("tenantId", None)
    source_type = coerced.get("source_type")
    if isinstance(source_type, str):
        with suppress(ValueError):
            coerced["source_type"] = SourceType(source_type)
    event_type = coerced.get("event_type")
    if isinstance(event_type, str):
        with suppress(ValueError):
            coerced["event_type"] = EventType(event_type)
    observed_at = coerced.get("observed_at")
    if isinstance(observed_at, str):
        with suppress(ValueError):
            coerced["observed_at"] = datetime.fromisoformat(observed_at)
    return coerced


def _fmt_from_filename(filename: str) -> str:
    name = filename.lower()
    for ext in (".ndjson", ".json", ".csv"):
        if name.endswith(ext):
            return ext[1:]
    raise BadRequestError(
        f"Unsupported file extension for {filename!r}.",
        code="UNSUPPORTED_EXTENSION",
    )


async def _process_row(
    *,
    row_number: int,
    row: dict[str, Any],
    events: EventRepository,
    event_labels: EventLabelRepository,
    event_outbox: EventOutboxRepository,
    storage: StorageService,
    upload_id: str,
    principal: Principal,
    session: SessionDep,
) -> tuple[str, str | None]:
    """Process one import row.

    Returns ``("accepted", None)``, ``("duplicate", None)`` or
    ``("rejected", code)``.
    """
    if not isinstance(row, dict) or row.get("tenant_id") or row.get("tenantId"):
        return "rejected", "TENANT_ID_REJECTED"

    row = _coerce_row(row)

    try:
        envelope = EventEnvelope.model_validate(row)
    except ValidationError:
        return "rejected", "INVALID_ROW"

    external_id = envelope.external_id
    if external_id is not None:
        existing = await events.get_by_source_external(envelope.source_id, external_id)
        if existing is not None:
            return "duplicate", None

    # Archive the raw row, then write event + label + outbox in one transaction.
    row_bytes = envelope.canonical_bytes()
    row_key = f"imports/{upload_id}/rows/{row_number}.json"
    await storage.put_object(row_key, row_bytes, content_type="application/json")

    event = Event(
        external_id=external_id,
        source_type=envelope.source_type.value,
        source_id=envelope.source_id,
        observed_at=envelope.observed_at,
        event_type=envelope.event_type.value,
        raw_ref=row_key,
        raw_checksum=envelope.compute_checksum(),
        normalized_payload=envelope.normalized_payload.model_dump(mode="json", by_alias=True),
        schema_version=envelope.schema_version,
        processing_status=EventStatus.RECEIVED.value,
        received_via="import",
        imported_by=principal.user_id,
        asset_id=envelope.asset_id,
    )
    session.add(event)
    await session.flush()

    if envelope.label is not None:
        await event_labels.create(
            {
                "event_id": event.id,
                "label": envelope.label.label,
                "source": envelope.label.source.value,
                "confidence": envelope.label.confidence,
                "created_by": principal.user_id,
            }
        )
    await event_outbox.create(
        {
            "event_id": event.id,
            "task_name": "event.imported",
            "payload": {"event_id": str(event.id), "source_id": envelope.source_id},
        }
    )
    await session.commit()
    return "accepted", None


@router.post(
    "/events/imports",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Import accepted"},
        400: {"description": "Bad request"},
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        413: {"description": "Payload too large"},
        503: {"description": "Storage unavailable"},
    },
)
async def import_events(
    request: Request,
    principal: Annotated[Principal, Depends(require_permission("events:import"))],
    session: SessionDep,
    settings: SettingsDep,
    storage: StorageDep,
    scanner: ScannerDep,
) -> JSONResponse:
    """Import events from a CSV/JSON/NDJSON file (Analyst and Admin only).

    - Multipart form with a ``file`` field
    - Content-type, extension and magic-byte checks
    - Size and row caps from settings
    - Streaming parse with per-row validation
    - Summary: ``{accepted, duplicates, rejected:[{row, code}]}`` (rejections
      capped at 100)
    - Original upload stored in S3 under ``imports/``
    - Events use ``received_via='import'`` and ``imported_by`` set
    - Duplicates return as duplicates, not errors
    """
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        raise BadRequestError(
            "Expected multipart/form-data with a 'file' field.",
            code="WRONG_CONTENT_TYPE",
        )

    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "filename") or not hasattr(upload, "read"):
        raise BadRequestError("The 'file' field is required.", code="NO_FILE")
    upload = cast(UploadFile, upload)

    filename = cast(str, upload.filename)
    fmt = _fmt_from_filename(filename)
    data = await upload.read()

    # Scanner: type, size, null-byte, decompression-bomb checks.
    try:
        await scanner.scan(
            filename=filename,
            content_type=cast(str, upload.content_type),
            data=data,
        )
    except UploadRejectedError as exc:
        raise BadRequestError(exc.message, code=exc.code) from exc

    # Parse and validate every row before touching storage, so a row-cap
    # rejection never stores an upload.
    rows = _parse_rows(fmt, data)
    max_rows = settings.security.import_max_rows
    if len(rows) > max_rows:
        raise BadRequestError(
            f"Upload contains {len(rows)} rows; maximum is {max_rows}.",
            code="ROW_CAP_EXCEEDED",
        )

    # Store the original upload under imports/. A failing storage returns 503
    # with Retry-After and stores nothing.
    upload_id = uuid.uuid4().hex
    try:
        await storage.put_object(
            f"imports/{upload_id}/{filename}",
            data,
            content_type=cast(str, upload.content_type) or "application/octet-stream",
        )
    except ServiceUnavailableError:
        raise  # domain handler turns this into 503 with Retry-After

    events = EventRepository(session)
    event_labels = EventLabelRepository(session)
    event_outbox = EventOutboxRepository(session)

    accepted = 0
    duplicates = 0
    rejected: list[ImportRejectedRow] = []

    for row_number, row in enumerate(rows, start=1):
        if len(rejected) >= MAX_REJECTED_RETURNED:
            # Still count acceptance/duplication, but stop recording rejections.
            outcome, _ = await _process_row(
                row_number=row_number,
                row=row,
                events=events,
                event_labels=event_labels,
                event_outbox=event_outbox,
                storage=storage,
                upload_id=upload_id,
                principal=principal,
                session=session,
            )
            if outcome == "accepted":
                accepted += 1
            elif outcome == "duplicate":
                duplicates += 1
            continue

        outcome, code = await _process_row(
            row_number=row_number,
            row=row,
            events=events,
            event_labels=event_labels,
            event_outbox=event_outbox,
            storage=storage,
            upload_id=upload_id,
            principal=principal,
            session=session,
        )
        if outcome == "accepted":
            accepted += 1
        elif outcome == "duplicate":
            duplicates += 1
        else:
            if code is None:
                code = "INVALID_ROW"
            rejected.append(ImportRejectedRow(row_number, code))

    payload: dict[str, Any] = {
        "accepted": accepted,
        "duplicates": duplicates,
        "rejected": [{"row": r.row, "code": r.code} for r in rejected],
    }
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=payload)
