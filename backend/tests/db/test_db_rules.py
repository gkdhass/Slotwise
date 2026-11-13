"""Database-enforced rules that must not depend on application code.

Covers the approver-before-execution rule, separation of duties and the single
ACTIVE model champion per ``(pipeline, model_name)``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alerts import Alert
from app.models.identity import User
from app.models.inference import ModelVersion
from app.models.responses import ResponseAction
from tests.db.factories import (
    make_alert,
    make_event,
    make_inference,
    make_model,
    make_user,
)

pytestmark = pytest.mark.db


async def _chain(db_session: AsyncSession) -> tuple[Alert, User]:
    event = await make_event(db_session)
    model = await make_model(db_session)
    inference = await make_inference(db_session, event=event, model=model)
    alert = await make_alert(db_session, event=event, inference=inference)
    user = await make_user(db_session)
    return alert, user


def _action(alert: Alert, user: User, **overrides: object) -> ResponseAction:
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


async def _flush_fails(db_session: AsyncSession) -> str:
    with pytest.raises(IntegrityError) as raised:
        await db_session.flush()
    await db_session.rollback()
    return str(raised.value)


async def test_inserting_executing_without_approver_is_rejected(db_session: AsyncSession) -> None:
    alert, user = await _chain(db_session)
    db_session.add(_action(alert, user, status="EXECUTING"))
    message = await _flush_fails(db_session)
    assert "approved_states_require_approver" in message


async def test_updating_to_executing_without_approver_is_rejected(db_session: AsyncSession) -> None:
    alert, user = await _chain(db_session)
    action = _action(alert, user, status="PENDING_APPROVAL")
    db_session.add(action)
    await db_session.flush()

    with pytest.raises(IntegrityError) as raised:
        await db_session.execute(
            update(ResponseAction).where(ResponseAction.id == action.id).values(status="EXECUTING")
        )
    await db_session.rollback()
    assert "approved_states_require_approver" in str(raised.value)


async def test_high_impact_action_rejects_self_approval(db_session: AsyncSession) -> None:
    alert, user = await _chain(db_session)
    db_session.add(
        _action(
            alert,
            user,
            action_type="ISOLATE_HOST",
            status="APPROVED",
            approved_by=user.id,
        )
    )
    message = await _flush_fails(db_session)
    assert "high_impact_requires_independent_approver" in message


async def test_independent_approval_is_accepted(db_session: AsyncSession) -> None:
    alert, requester = await _chain(db_session)
    approver = await make_user(db_session)
    action = _action(
        alert,
        requester,
        action_type="ISOLATE_HOST",
        status="APPROVED",
        approved_by=approver.id,
    )
    db_session.add(action)
    await db_session.flush()
    assert action.id is not None


async def test_low_impact_action_may_be_self_approved(db_session: AsyncSession) -> None:
    alert, user = await _chain(db_session)
    # BLOCK_DOMAIN is not in HIGH_IMPACT_ACTION_TYPES, so self-approval is allowed
    # even though the UI still recommends a second reviewer.
    action = _action(
        alert,
        user,
        action_type="BLOCK_DOMAIN",
        status="APPROVED",
        approved_by=user.id,
    )
    db_session.add(action)
    await db_session.flush()
    assert action.approved_by == user.id


async def test_terminal_action_requires_execution_timestamp(db_session: AsyncSession) -> None:
    alert, requester = await _chain(db_session)
    approver = await make_user(db_session)
    db_session.add(
        _action(
            alert,
            requester,
            status="SUCCEEDED",
            approved_by=approver.id,
        )
    )
    message = await _flush_fails(db_session)
    assert "terminal_execution_requires_timestamp" in message


async def test_execution_cannot_precede_request(db_session: AsyncSession) -> None:
    alert, requester = await _chain(db_session)
    approver = await make_user(db_session)
    db_session.add(
        _action(
            alert,
            requester,
            status="SUCCEEDED",
            approved_by=approver.id,
            executed_at=datetime(2000, 1, 1, tzinfo=UTC),
        )
    )
    message = await _flush_fails(db_session)
    assert "executed_after_requested" in message


async def test_two_active_models_for_same_model_are_rejected(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    first = await make_model(
        db_session,
        pipeline="MODULE_A",
        model_name="detector",
        version="1.0",
        status="ACTIVE",
        promoted_at=now,
    )
    db_session.add(
        ModelVersion(
            pipeline=first.pipeline,
            model_name=first.model_name,
            version="2.0",
            artifact_uri="s3://test/model-v2.onnx",
            framework="onnx",
            metrics={},
            status="ACTIVE",
            promoted_at=now,
        )
    )
    message = await _flush_fails(db_session)
    assert "ux_model_versions_active_per_model" in message


async def test_new_active_model_allowed_after_retiring_previous(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    first = await make_model(
        db_session,
        pipeline="MODULE_A",
        model_name="detector",
        version="1.0",
        status="ACTIVE",
        promoted_at=now,
    )
    first.status = "RETIRED"
    await db_session.flush()
    await make_model(
        db_session,
        pipeline="MODULE_A",
        model_name="detector",
        version="2.0",
        status="ACTIVE",
        promoted_at=now,
    )
    assert first.status == "RETIRED"


async def test_active_models_allowed_for_different_pipeline(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    await make_model(
        db_session,
        pipeline="MODULE_A",
        model_name="detector",
        version="1.0",
        status="ACTIVE",
        promoted_at=now,
    )
    await make_model(
        db_session,
        pipeline="MODULE_B",
        model_name="detector",
        version="1.0",
        status="ACTIVE",
        promoted_at=now,
    )
