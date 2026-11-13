"""Table-driven lifecycle transition tests.

The transition tables are the contract used by services; every documented edge
must pass and every other pair must be rejected with the typed 409 error.
"""

from __future__ import annotations

from itertools import product

import pytest

from app.core.errors import ErrorCode, InvalidStateTransitionError
from app.models.enums import (
    AlertStatus,
    EventStatus,
    ModelVersionStatus,
    ResponseActionStatus,
)
from app.policies.state_machines import (
    ALERT_TRANSITIONS,
    EVENT_TRANSITIONS,
    MACHINES,
    MODEL_VERSION_TRANSITIONS,
    RESPONSE_ACTION_TRANSITIONS,
    allowed_transitions,
    can_transition,
    require_transition,
)

CASES = (
    ("event", EventStatus, EVENT_TRANSITIONS),
    ("alert", AlertStatus, ALERT_TRANSITIONS),
    ("response_action", ResponseActionStatus, RESPONSE_ACTION_TRANSITIONS),
    ("model_version", ModelVersionStatus, MODEL_VERSION_TRANSITIONS),
)


@pytest.mark.parametrize(("name", "machine", "transitions"), CASES, ids=[c[0] for c in CASES])
def test_every_documented_transition_is_allowed(name, machine, transitions) -> None:
    assert MACHINES[machine] is transitions
    for source, targets in transitions.items():
        for target in targets:
            assert can_transition(machine, source, target), f"{name}: {source} -> {target}"
            assert require_transition(machine, source, target) is target
            assert target in allowed_transitions(machine, source)


@pytest.mark.parametrize(("name", "machine", "transitions"), CASES, ids=[c[0] for c in CASES])
def test_every_undocumented_transition_is_rejected(name, machine, transitions) -> None:
    states = list(machine)
    for source, target in product(states, states):
        if target in transitions.get(source, frozenset()):
            continue
        assert not can_transition(machine, source, target)
        with pytest.raises(InvalidStateTransitionError) as raised:
            require_transition(machine, source, target)
        error = raised.value
        assert error.code is ErrorCode.INVALID_STATE_TRANSITION
        assert error.status_code == 409
        assert error.details["entity"] == machine.__name__
        assert error.details["from"] == source.value
        assert error.details["to"] == target.value


@pytest.mark.parametrize(("name", "machine", "transitions"), CASES, ids=[c[0] for c in CASES])
def test_every_state_is_registered(name, machine, transitions) -> None:
    # Terminal states are present with an empty target set rather than omitted,
    # so an unknown status cannot silently bypass the transition check.
    assert set(transitions) == set(machine)


def test_event_transition_does_not_skip_validation() -> None:
    with pytest.raises(InvalidStateTransitionError):
        require_transition(EventStatus, "RECEIVED", "PROCESSED")


def test_response_action_cannot_execute_before_approval() -> None:
    with pytest.raises(InvalidStateTransitionError):
        require_transition(ResponseActionStatus, "REQUESTED", "EXECUTING")


def test_unknown_state_is_rejected() -> None:
    with pytest.raises(InvalidStateTransitionError) as raised:
        require_transition(EventStatus, "PROCESSED", "NOT_A_STATE")
    assert raised.value.code is ErrorCode.INVALID_STATE_TRANSITION
