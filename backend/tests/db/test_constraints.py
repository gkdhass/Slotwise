"""One test per database integrity rule.

Each test provokes exactly one violation so a failure identifies the specific
constraint that regressed. PostgreSQL error type is asserted as
``IntegrityError``; the rule itself is named in the test id.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alerts import Alert, Incident, IncidentAlert, IncidentComment
from app.models.assets import Asset, Sensor
from app.models.datasets import Dataset, TrainingRun
from app.models.events import Event, EventLabel
from app.models.identity import Role, User
from app.models.inference import InferenceResult, ModelVersion
from app.models.responses import AllowlistEntry, ResponseAction, ResponsePolicy
from tests.db.factories import (
    make_alert,
    make_asset,
    make_event,
    make_inference,
    make_model,
    make_user,
)

pytestmark = pytest.mark.db


async def _expect_failure(db_session: AsyncSession, *entities: object) -> IntegrityError:
    for entity in entities:
        db_session.add(entity)
    with pytest.raises(IntegrityError) as raised:
        await db_session.flush()
    await db_session.rollback()
    return raised.value


def _event(**overrides: object) -> Event:
    values: dict[str, object] = {
        "external_id": f"evt-{uuid.uuid4().hex}",
        "source_type": "UPLOAD",
        "source_id": "sensor-test",
        "observed_at": datetime.now(UTC),
        "event_type": "NETWORK_FLOW",
        "raw_ref": "s3://test/raw.json",
        "raw_checksum": "a" * 64,
        "schema_version": "1.0",
        "processing_status": "RECEIVED",
    }
    values.update(overrides)
    return Event(**values)


def _response_action(alert: Alert, user: User, **overrides: object) -> ResponseAction:
    values: dict[str, object] = {
        "alert_id": alert.id,
        "action_type": "BLOCK_IP",
        "target": "198.51.100.9",
        "requested_by": user.id,
        "status": "REQUESTED",
        "idempotency_key": uuid.uuid4().hex,
    }
    values.update(overrides)
    return ResponseAction(**values)


async def test_role_name_must_be_known(db_session: AsyncSession) -> None:
    await _expect_failure(db_session, Role(name="SUPERUSER"))


async def test_role_name_is_unique(db_session: AsyncSession) -> None:
    db_session.add(Role(name="ANALYST"))
    await db_session.flush()
    await _expect_failure(db_session, Role(name="ANALYST"))


async def test_user_email_is_unique(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    await _expect_failure(
        db_session,
        User(email=user.email, password_hash="y" * 40, role_id=user.role_id),
    )


async def test_user_email_must_be_lowercase(db_session: AsyncSession) -> None:
    role = Role(name="VIEWER")
    db_session.add(role)
    await db_session.flush()
    await _expect_failure(
        db_session,
        User(email="Mixed@Example.com", password_hash="y" * 40, role_id=role.id),
    )


async def test_user_role_must_exist(db_session: AsyncSession) -> None:
    await _expect_failure(
        db_session,
        User(email="ghost@example.com", password_hash="y" * 40, role_id=uuid.uuid4()),
    )


async def test_asset_name_is_unique(db_session: AsyncSession) -> None:
    asset = await make_asset(db_session)
    await _expect_failure(
        db_session,
        Asset(
            name=asset.name,
            asset_type="SERVER",
            criticality="HIGH",
            owner_team="test",
            environment="DEV",
        ),
    )


async def test_asset_criticality_must_be_known(db_session: AsyncSession) -> None:
    await _expect_failure(
        db_session,
        Asset(
            name=f"asset-{uuid.uuid4().hex}",
            asset_type="SERVER",
            criticality="APOCALYPTIC",
            owner_team="test",
            environment="DEV",
        ),
    )


async def test_sensor_credential_hash_must_not_be_plaintext_short(db_session: AsyncSession) -> None:
    await _expect_failure(
        db_session,
        Sensor(
            name=f"sensor-{uuid.uuid4().hex}",
            sensor_type="zeek",
            credential_hash="short",
            status="ACTIVE",
        ),
    )


async def test_sensor_status_must_be_known(db_session: AsyncSession) -> None:
    await _expect_failure(
        db_session,
        Sensor(
            name=f"sensor-{uuid.uuid4().hex}",
            sensor_type="zeek",
            credential_hash="c" * 64,
            status="BROKEN",
        ),
    )


async def test_event_source_external_id_is_unique(db_session: AsyncSession) -> None:
    first = await make_event(db_session, source_id="sensor-1", external_id="same")
    db_session.add(_event(source_id=first.source_id, external_id=first.external_id))
    with pytest.raises(IntegrityError) as raised:
        await db_session.flush()
    await db_session.rollback()
    assert "ux_events_source_external" in str(raised.value)


async def test_events_without_external_id_are_not_deduplicated(db_session: AsyncSession) -> None:
    first = await make_event(db_session, source_id="sensor-2")
    second = await make_event(db_session, source_id="sensor-2")
    first.external_id = None
    second.external_id = None
    # Both rows now have a NULL identity and must coexist.
    await db_session.flush()


async def test_event_checksum_must_be_sha256_hex(db_session: AsyncSession) -> None:
    await _expect_failure(db_session, _event(raw_checksum="not-a-checksum"))


async def test_event_processing_status_must_be_known(db_session: AsyncSession) -> None:
    await _expect_failure(db_session, _event(processing_status="DONE"))


async def test_event_asset_must_exist(db_session: AsyncSession) -> None:
    await _expect_failure(db_session, _event(asset_id=uuid.uuid4()))


async def test_event_label_is_unique_per_event(db_session: AsyncSession) -> None:
    event = await make_event(db_session)
    db_session.add(EventLabel(event_id=event.id, label="malware", source="ANALYST"))
    await db_session.flush()
    await _expect_failure(db_session, EventLabel(event_id=event.id, label="malware", source="ML"))


async def test_event_label_confidence_is_bounded(db_session: AsyncSession) -> None:
    event = await make_event(db_session)
    await _expect_failure(
        db_session, EventLabel(event_id=event.id, label="x", source="ML", confidence=1.2)
    )


async def test_inference_anomaly_score_is_bounded(db_session: AsyncSession) -> None:
    event = await make_event(db_session)
    model = await make_model(db_session)
    await _expect_failure(
        db_session,
        InferenceResult(
            event_id=event.id,
            model_version_id=model.id,
            predicted_class="scan",
            probabilities={"benign": 0.1},
            anomaly_score=-0.01,
            severity="LOW",
            inference_ms=5,
        ),
    )


async def test_inference_latency_is_non_negative(db_session: AsyncSession) -> None:
    event = await make_event(db_session)
    model = await make_model(db_session)
    await _expect_failure(
        db_session,
        InferenceResult(
            event_id=event.id,
            model_version_id=model.id,
            predicted_class="scan",
            probabilities={"benign": 0.1},
            anomaly_score=0.5,
            severity="LOW",
            inference_ms=-1,
        ),
    )


async def test_inference_probabilities_must_be_an_object(db_session: AsyncSession) -> None:
    event = await make_event(db_session)
    model = await make_model(db_session)
    await _expect_failure(
        db_session,
        InferenceResult(
            event_id=event.id,
            model_version_id=model.id,
            predicted_class="scan",
            probabilities=["benign", 1.0],  # type: ignore[arg-type]
            anomaly_score=0.5,
            severity="LOW",
            inference_ms=5,
        ),
    )


async def test_model_version_identity_is_unique(db_session: AsyncSession) -> None:
    model = await make_model(db_session, pipeline="MODULE_A", model_name="detector", version="1.0")
    await _expect_failure(
        db_session,
        ModelVersion(
            pipeline=model.pipeline,
            model_name=model.model_name,
            version=model.version,
            artifact_uri="s3://test/other.onnx",
            framework="onnx",
            metrics={},
            status="DRAFT",
        ),
    )


async def test_model_active_requires_promoted_at(db_session: AsyncSession) -> None:
    await _expect_failure(db_session, _active_model(promoted_at=None))


def _active_model(*, promoted_at: datetime | None) -> ModelVersion:
    return ModelVersion(
        pipeline="MODULE_A",
        model_name=f"model-{uuid.uuid4().hex}",
        version="1.0",
        artifact_uri="s3://test/model.onnx",
        framework="onnx",
        metrics={},
        status="ACTIVE",
        promoted_at=promoted_at,
    )


async def test_alert_one_per_inference_result(db_session: AsyncSession) -> None:
    event = await make_event(db_session)
    model = await make_model(db_session)
    inference = await make_inference(db_session, event=event, model=model)
    await make_alert(db_session, event=event, inference=inference)
    await _expect_failure(
        db_session,
        Alert(
            event_id=event.id,
            inference_result_id=inference.id,
            category="duplicate",
            severity="LOW",
            confidence=0.5,
            status="NEW",
        ),
    )


async def test_alert_confidence_is_bounded(db_session: AsyncSession) -> None:
    event = await make_event(db_session)
    model = await make_model(db_session)
    inference = await make_inference(db_session, event=event, model=model)
    await _expect_failure(
        db_session,
        Alert(
            event_id=event.id,
            inference_result_id=inference.id,
            category="bad-confidence",
            severity="LOW",
            confidence=1.01,
            status="NEW",
        ),
    )


async def test_alert_assigned_requires_owner(db_session: AsyncSession) -> None:
    event = await make_event(db_session)
    model = await make_model(db_session)
    inference = await make_inference(db_session, event=event, model=model)
    await _expect_failure(
        db_session,
        Alert(
            event_id=event.id,
            inference_result_id=inference.id,
            category="unassigned",
            severity="LOW",
            confidence=0.5,
            status="ASSIGNED",
        ),
    )


async def test_alert_suppressed_requires_reason(db_session: AsyncSession) -> None:
    event = await make_event(db_session)
    model = await make_model(db_session)
    inference = await make_inference(db_session, event=event, model=model)
    await _expect_failure(
        db_session,
        Alert(
            event_id=event.id,
            inference_result_id=inference.id,
            category="suppressed",
            severity="LOW",
            confidence=0.5,
            status="SUPPRESSED",
        ),
    )


async def test_incident_closed_requires_resolved_at(db_session: AsyncSession) -> None:
    await _expect_failure(
        db_session,
        Incident(title="closed without resolution", severity="LOW", status="CLOSED"),
    )


async def test_incident_resolution_cannot_precede_opening(db_session: AsyncSession) -> None:
    opened = datetime.now(UTC)
    await _expect_failure(
        db_session,
        Incident(
            title="time travel",
            severity="LOW",
            status="RESOLVED",
            opened_at=opened,
            resolved_at=opened - timedelta(hours=1),
        ),
    )


async def test_incident_alert_pair_is_unique(db_session: AsyncSession) -> None:
    event = await make_event(db_session)
    model = await make_model(db_session)
    inference = await make_inference(db_session, event=event, model=model)
    alert = await make_alert(db_session, event=event, inference=inference)
    incident = Incident(title="pair", severity="LOW", status="OPEN")
    db_session.add(incident)
    await db_session.flush()
    db_session.add(IncidentAlert(incident_id=incident.id, alert_id=alert.id))
    await db_session.flush()
    await _expect_failure(db_session, IncidentAlert(incident_id=incident.id, alert_id=alert.id))


async def test_incident_comment_body_length_is_bounded(db_session: AsyncSession) -> None:
    incident = Incident(title="comment", severity="LOW", status="OPEN")
    db_session.add(incident)
    await db_session.flush()
    await _expect_failure(db_session, IncidentComment(incident_id=incident.id, body="x" * 10_001))


async def test_response_action_idempotency_key_is_unique(db_session: AsyncSession) -> None:
    event = await make_event(db_session)
    model = await make_model(db_session)
    inference = await make_inference(db_session, event=event, model=model)
    alert = await make_alert(db_session, event=event, inference=inference)
    user = await make_user(db_session)
    action = _response_action(alert, user)
    db_session.add(action)
    await db_session.flush()
    await _expect_failure(
        db_session,
        _response_action(alert, user, idempotency_key=action.idempotency_key),
    )


async def test_response_action_status_must_be_known(db_session: AsyncSession) -> None:
    event = await make_event(db_session)
    model = await make_model(db_session)
    inference = await make_inference(db_session, event=event, model=model)
    alert = await make_alert(db_session, event=event, inference=inference)
    user = await make_user(db_session)
    await _expect_failure(db_session, _response_action(alert, user, status="LAUNCHED"))


async def test_response_policy_action_type_must_be_known(db_session: AsyncSession) -> None:
    await _expect_failure(
        db_session,
        ResponsePolicy(
            name=f"policy-{uuid.uuid4().hex}",
            action_type="LAUNCH_MISSILES",
            conditions={},
            requires_approval=True,
            enabled=True,
        ),
    )


async def test_allowlist_active_value_is_unique(db_session: AsyncSession) -> None:
    entry = AllowlistEntry(entry_type="IP", value="198.51.100.10", reason="trusted", is_active=True)
    db_session.add(entry)
    await db_session.flush()
    await _expect_failure(
        db_session,
        AllowlistEntry(entry_type="IP", value="198.51.100.10", reason="duplicate", is_active=True),
    )


async def test_allowlist_inactive_value_may_repeat(db_session: AsyncSession) -> None:
    db_session.add(
        AllowlistEntry(entry_type="DOMAIN", value="old.example.com", reason="old", is_active=False)
    )
    db_session.add(
        AllowlistEntry(entry_type="DOMAIN", value="old.example.com", reason="new", is_active=True)
    )
    await db_session.flush()
    active = (
        await db_session.execute(
            select(AllowlistEntry).where(
                AllowlistEntry.value == "old.example.com", AllowlistEntry.is_active.is_(True)
            )
        )
    ).scalar_one()
    assert active.reason == "new"


async def test_dataset_validated_requires_object_and_checksum(db_session: AsyncSession) -> None:
    await _expect_failure(
        db_session,
        Dataset(
            name=f"dataset-{uuid.uuid4().hex}",
            modality="network_flow",
            source="test",
            licence="test",
            status="VALIDATED",
        ),
    )


async def test_dataset_checksum_must_be_sha256_hex(db_session: AsyncSession) -> None:
    await _expect_failure(
        db_session,
        Dataset(
            name=f"dataset-{uuid.uuid4().hex}",
            modality="network_flow",
            source="test",
            licence="test",
            status="REGISTERED",
            checksum="xyz",
        ),
    )


async def test_dataset_name_is_unique(db_session: AsyncSession) -> None:
    dataset = Dataset(
        name="repeated-dataset",
        modality="network_flow",
        source="test",
        licence="test",
        status="REGISTERED",
    )
    db_session.add(dataset)
    await db_session.flush()
    await _expect_failure(
        db_session,
        Dataset(
            name=dataset.name,
            modality="network_flow",
            source="test",
            licence="test",
            status="REGISTERED",
        ),
    )


async def test_training_run_mlflow_id_is_unique(db_session: AsyncSession) -> None:
    dataset = Dataset(
        name=f"dataset-{uuid.uuid4().hex}",
        modality="network_flow",
        source="test",
        licence="test",
        status="REGISTERED",
    )
    db_session.add(dataset)
    await db_session.flush()
    run = TrainingRun(
        dataset_id=dataset.id,
        pipeline="MODULE_A",
        base_model="resnet50",
        hyperparameters={},
        mlflow_run_id="run-1",
        status="PENDING",
    )
    db_session.add(run)
    await db_session.flush()
    await _expect_failure(
        db_session,
        TrainingRun(
            dataset_id=dataset.id,
            pipeline="MODULE_A",
            base_model="resnet50",
            hyperparameters={},
            mlflow_run_id="run-1",
            status="PENDING",
        ),
    )


async def test_training_run_terminal_status_requires_completion(db_session: AsyncSession) -> None:
    dataset = Dataset(
        name=f"dataset-{uuid.uuid4().hex}",
        modality="network_flow",
        source="test",
        licence="test",
        status="REGISTERED",
    )
    db_session.add(dataset)
    await db_session.flush()
    await _expect_failure(
        db_session,
        TrainingRun(
            dataset_id=dataset.id,
            pipeline="MODULE_A",
            base_model="resnet50",
            hyperparameters={},
            status="SUCCEEDED",
        ),
    )


async def test_training_run_hyperparameters_must_be_an_object(db_session: AsyncSession) -> None:
    dataset = Dataset(
        name=f"dataset-{uuid.uuid4().hex}",
        modality="network_flow",
        source="test",
        licence="test",
        status="REGISTERED",
    )
    db_session.add(dataset)
    await db_session.flush()
    await _expect_failure(
        db_session,
        TrainingRun(
            dataset_id=dataset.id,
            pipeline="MODULE_A",
            base_model="resnet50",
            hyperparameters=[1, 2, 3],  # type: ignore[arg-type]
            status="PENDING",
        ),
    )
