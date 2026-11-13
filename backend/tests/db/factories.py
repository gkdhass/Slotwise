"""ORM factories for database tests.

Values are deliberately synthetic and unique per call; no production data is
read or invented as a real measurement.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alerts import Alert, Incident
from app.models.assets import Asset
from app.models.enums import (
    AlertStatus,
    AssetType,
    Criticality,
    Environment,
    EventType,
    Severity,
    SourceType,
)
from app.models.events import Event
from app.models.identity import Role, User
from app.models.inference import InferenceResult, ModelVersion


async def make_role(session: AsyncSession, name: str = "ANALYST") -> Role:
    result = await session.execute(select(Role).where(Role.name == name))
    role = result.scalar_one_or_none()
    if role is None:
        role = Role(name=name, description=f"test {name}")
        session.add(role)
        await session.flush()
    return role


async def make_user(
    session: AsyncSession,
    *,
    role_name: str = "ADMIN",
    email: str | None = None,
    password_hash: str = "x" * 40,
    is_active: bool = True,
) -> User:
    role = await make_role(session, role_name)
    user = User(
        email=email or f"user-{uuid.uuid4().hex}@example.com",
        password_hash=password_hash,
        role_id=role.id,
        is_active=is_active,
    )
    session.add(user)
    await session.flush()
    return user


async def make_asset(session: AsyncSession, *, name: str | None = None) -> Asset:
    asset = Asset(
        name=name or f"asset-{uuid.uuid4().hex}",
        asset_type=AssetType.SERVER.value,
        criticality=Criticality.HIGH.value,
        owner_team="test",
        environment=Environment.DEV.value,
        is_active=True,
    )
    session.add(asset)
    await session.flush()
    return asset


async def make_model(
    session: AsyncSession,
    *,
    pipeline: str = "MODULE_A",
    model_name: str | None = None,
    version: str | None = None,
    status: str = "DRAFT",
    promoted_at: datetime | None = None,
    training_run_id: uuid.UUID | None = None,
) -> ModelVersion:
    model = ModelVersion(
        pipeline=pipeline,
        model_name=model_name or f"model-{uuid.uuid4().hex}",
        version=version or "1.0",
        artifact_uri="s3://test/models/test.onnx",
        framework="onnx",
        metrics={},
        status=status,
        promoted_at=promoted_at,
        training_run_id=training_run_id,
    )
    session.add(model)
    await session.flush()
    return model


async def make_event(
    session: AsyncSession,
    *,
    source_id: str = "sensor-test",
    external_id: str | None = None,
    asset_id: uuid.UUID | None = None,
    observed_at: datetime | None = None,
    processing_status: str = "RECEIVED",
) -> Event:
    event = Event(
        external_id=external_id or f"evt-{uuid.uuid4().hex}",
        source_type=SourceType.UPLOAD.value,
        source_id=source_id,
        asset_id=asset_id,
        observed_at=observed_at or datetime.now(UTC),
        event_type=EventType.NETWORK_FLOW.value,
        raw_ref="s3://test/events/raw.json",
        raw_checksum=hashlib.sha256(b"raw").hexdigest(),
        normalized_payload={"test": True},
        schema_version="1.0",
        processing_status=processing_status,
    )
    session.add(event)
    await session.flush()
    return event


async def make_inference(
    session: AsyncSession,
    *,
    event: Event,
    model: ModelVersion,
    predicted_class: str = "scan",
    anomaly_score: float = 0.5,
    severity: str = "MEDIUM",
    inference_ms: int = 5,
    probabilities: dict[str, Any] | None = None,
) -> InferenceResult:
    inference = InferenceResult(
        event_id=event.id,
        model_version_id=model.id,
        predicted_class=predicted_class,
        probabilities=probabilities or {"benign": 0.5, "scan": 0.5},
        anomaly_score=anomaly_score,
        severity=severity,
        inference_ms=inference_ms,
    )
    session.add(inference)
    await session.flush()
    return inference


async def make_alert(
    session: AsyncSession,
    *,
    event: Event,
    inference: InferenceResult,
    status: str = AlertStatus.NEW.value,
    severity: str = Severity.HIGH.value,
    confidence: float = 0.9,
    assigned_to: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    suppression_reason: str | None = None,
) -> Alert:
    alert = Alert(
        event_id=event.id,
        inference_result_id=inference.id,
        asset_id=asset_id,
        category="test-category",
        severity=severity,
        confidence=confidence,
        status=status,
        assigned_to=assigned_to,
        severity_policy_version="test-v1",
        review_required=True,
        suppression_reason=suppression_reason,
    )
    session.add(alert)
    await session.flush()
    return alert


async def make_incident(session: AsyncSession, *, status: str = "OPEN") -> Incident:
    incident = Incident(
        title=f"incident-{uuid.uuid4().hex}",
        severity=Severity.MEDIUM.value,
        status=status,
        summary="test incident",
    )
    session.add(incident)
    await session.flush()
    return incident
