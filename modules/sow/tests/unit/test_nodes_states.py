"""Phase 2: state machine legality (deterministic, no processes)."""
from __future__ import annotations

import pytest

from control_plane.nodes import LEGAL, IllegalTransition, NodeState, validate_transition


def test_every_state_has_an_explicit_rule() -> None:
    assert set(LEGAL) == set(NodeState)


@pytest.mark.parametrize(
    ("current", "requested"),
    [
        (NodeState.SPAWNING, NodeState.READY),
        (NodeState.READY, NodeState.ASSIGNED),
        (NodeState.ASSIGNED, NodeState.BUSY),
        (NodeState.BUSY, NodeState.READY),
        (NodeState.READY, NodeState.PAUSED),
        (NodeState.DISCONNECTED, NodeState.READY),
        (NodeState.BUSY, NodeState.TERMINATED),
    ],
)
def test_legal_transitions_pass(current: NodeState, requested: NodeState) -> None:
    validate_transition(current, requested)


@pytest.mark.parametrize(
    ("current", "requested"),
    [
        (NodeState.SPAWNING, NodeState.BUSY),       # cannot skip READY/ASSIGNED
        (NodeState.READY, NodeState.BUSY),          # work requires assignment first
        (NodeState.DISCONNECTED, NodeState.ASSIGNED),  # reconnect drops assignment context
        (NodeState.DISCONNECTED, NodeState.BUSY),
        (NodeState.TERMINATED, NodeState.READY),    # absorbing
        (NodeState.TERMINATED, NodeState.SPAWNING),
        (NodeState.READY, NodeState.SPAWNING),      # no going back
    ],
)
def test_illegal_transitions_raise(current: NodeState, requested: NodeState) -> None:
    with pytest.raises(IllegalTransition):
        validate_transition(current, requested)


def test_terminated_is_fully_absorbing() -> None:
    for requested in NodeState:
        if requested is NodeState.TERMINATED:
            continue
        with pytest.raises(IllegalTransition):
            validate_transition(NodeState.TERMINATED, requested)
