"""Pure lifecycle state machines shared by services and tests.

The database stores status values but deliberately does not encode the full
transition graph: keeping it in Python makes the rules unit-testable and lets
services return the standard conflict envelope. The database still enforces the
two invariants that must never depend on application code (approver required
before execution and one ACTIVE model per logical model).

Branches where the source document is terse are annotated inline with the
interpretation used here.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import TypeVar

from app.core.errors import InvalidStateTransitionError
from app.models.enums import (
    AlertStatus,
    EventStatus,
    ModelVersionStatus,
    ResponseActionStatus,
)

E = TypeVar("E", bound=StrEnum)

_Transitions = Mapping[StrEnum, frozenset[StrEnum]]

# Event: RECEIVED -> VALIDATED -> QUEUED -> PROCESSED / FAILED / QUARANTINED.
# Terminal outcomes are reachable only after queueing, as drawn in the Phase 1
# document. Validation failures are represented by not advancing and recording
# the error separately, not by inventing an undocumented edge.
EVENT_TRANSITIONS: _Transitions = {
    EventStatus.RECEIVED: frozenset({EventStatus.VALIDATED}),
    EventStatus.VALIDATED: frozenset({EventStatus.QUEUED}),
    EventStatus.QUEUED: frozenset(
        {EventStatus.PROCESSED, EventStatus.FAILED, EventStatus.QUARANTINED}
    ),
    EventStatus.PROCESSED: frozenset(),
    EventStatus.FAILED: frozenset(),
    EventStatus.QUARANTINED: frozenset(),
}

# Alert: NEW -> ACKNOWLEDGED -> ASSIGNED -> RESOLVED / FALSE_POSITIVE / SUPPRESSED.
# The document shows a single triage funnel, so closing before assignment is
# rejected rather than silently allowed.
ALERT_TRANSITIONS: _Transitions = {
    AlertStatus.NEW: frozenset({AlertStatus.ACKNOWLEDGED}),
    AlertStatus.ACKNOWLEDGED: frozenset({AlertStatus.ASSIGNED}),
    AlertStatus.ASSIGNED: frozenset(
        {AlertStatus.RESOLVED, AlertStatus.FALSE_POSITIVE, AlertStatus.SUPPRESSED}
    ),
    AlertStatus.RESOLVED: frozenset(),
    AlertStatus.FALSE_POSITIVE: frozenset(),
    AlertStatus.SUPPRESSED: frozenset(),
}

# ResponseAction: REQUESTED -> PENDING_APPROVAL -> APPROVED / REJECTED
# -> EXECUTING -> SUCCEEDED / FAILED / ROLLED_BACK. The last three are drawn as
# parallel execution outcomes, so ROLLED_BACK is reachable directly from
# EXECUTING (for example when a simulation detects a conflicting live change).
RESPONSE_ACTION_TRANSITIONS: _Transitions = {
    ResponseActionStatus.REQUESTED: frozenset({ResponseActionStatus.PENDING_APPROVAL}),
    ResponseActionStatus.PENDING_APPROVAL: frozenset(
        {ResponseActionStatus.APPROVED, ResponseActionStatus.REJECTED}
    ),
    ResponseActionStatus.APPROVED: frozenset({ResponseActionStatus.EXECUTING}),
    ResponseActionStatus.EXECUTING: frozenset(
        {
            ResponseActionStatus.SUCCEEDED,
            ResponseActionStatus.FAILED,
            ResponseActionStatus.ROLLED_BACK,
        }
    ),
    ResponseActionStatus.REJECTED: frozenset(),
    ResponseActionStatus.SUCCEEDED: frozenset(),
    ResponseActionStatus.FAILED: frozenset(),
    ResponseActionStatus.ROLLED_BACK: frozenset(),
}

# ModelVersion: DRAFT -> TRAINED -> EVALUATED -> APPROVED -> ACTIVE -> RETIRED.
MODEL_VERSION_TRANSITIONS: _Transitions = {
    ModelVersionStatus.DRAFT: frozenset({ModelVersionStatus.TRAINED}),
    ModelVersionStatus.TRAINED: frozenset({ModelVersionStatus.EVALUATED}),
    ModelVersionStatus.EVALUATED: frozenset({ModelVersionStatus.APPROVED}),
    ModelVersionStatus.APPROVED: frozenset({ModelVersionStatus.ACTIVE}),
    ModelVersionStatus.ACTIVE: frozenset({ModelVersionStatus.RETIRED}),
    ModelVersionStatus.RETIRED: frozenset(),
}

MACHINES: Mapping[type[StrEnum], _Transitions] = {
    EventStatus: EVENT_TRANSITIONS,
    AlertStatus: ALERT_TRANSITIONS,
    ResponseActionStatus: RESPONSE_ACTION_TRANSITIONS,
    ModelVersionStatus: MODEL_VERSION_TRANSITIONS,
}


def _coerce(machine: type[E], value: E | str, *, entity: str, field: str) -> E:
    if isinstance(value, machine):
        return value
    try:
        return machine(value)
    except ValueError as exc:
        raise InvalidStateTransitionError(
            "Unknown lifecycle state.",
            details={"entity": entity, "field": field, "value": str(value)},
        ) from exc


def allowed_transitions(machine: type[E], current: E | str) -> frozenset[E]:
    state = _coerce(machine, current, entity=machine.__name__, field="current")
    targets = MACHINES[machine].get(state, frozenset())
    return frozenset(
        _coerce(machine, target, entity=machine.__name__, field="target") for target in targets
    )


def can_transition(machine: type[E], current: E | str, target: E | str) -> bool:
    current_state = _coerce(machine, current, entity=machine.__name__, field="current")
    target_state = _coerce(machine, target, entity=machine.__name__, field="target")
    return target_state in MACHINES[machine].get(current_state, frozenset())


def require_transition(machine: type[E], current: E | str, target: E | str) -> E:
    """Return the target state or raise a typed conflict error."""
    current_state = _coerce(machine, current, entity=machine.__name__, field="current")
    target_state = _coerce(machine, target, entity=machine.__name__, field="target")
    if target_state not in MACHINES[machine].get(current_state, frozenset()):
        allowed = sorted(item.value for item in allowed_transitions(machine, current_state))
        raise InvalidStateTransitionError(
            details={
                "entity": machine.__name__,
                "from": current_state.value,
                "to": target_state.value,
                "allowed": allowed,
            }
        )
    return target_state
