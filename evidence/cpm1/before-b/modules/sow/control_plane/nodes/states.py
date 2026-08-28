"""Node state machine (Plan section 9.1; node@1.0 schema `state` enum).

Deterministic, fail-closed: any transition not explicitly legal raises. TERMINATED is
absorbing — restart never resurrects an incarnation, it registers the next one.
PAUSED resumes only to the exact state it interrupted (recorded by the registry).
DISCONNECTED re-enters via READY only: assignment context is deliberately dropped on
reconnect (fail closed; task reassignment is a later-phase concern, Plan section 11.2).
"""
from __future__ import annotations

from enum import Enum


class NodeState(str, Enum):
    SPAWNING = "SPAWNING"
    READY = "READY"
    ASSIGNED = "ASSIGNED"
    BUSY = "BUSY"
    PAUSED = "PAUSED"
    DISCONNECTED = "DISCONNECTED"
    TERMINATED = "TERMINATED"


LEGAL: dict[NodeState, frozenset[NodeState]] = {
    NodeState.SPAWNING: frozenset({NodeState.READY, NodeState.DISCONNECTED, NodeState.TERMINATED}),
    NodeState.READY: frozenset({NodeState.ASSIGNED, NodeState.PAUSED, NodeState.DISCONNECTED, NodeState.TERMINATED}),
    NodeState.ASSIGNED: frozenset({NodeState.BUSY, NodeState.READY, NodeState.PAUSED, NodeState.DISCONNECTED, NodeState.TERMINATED}),
    NodeState.BUSY: frozenset({NodeState.READY, NodeState.PAUSED, NodeState.DISCONNECTED, NodeState.TERMINATED}),
    NodeState.PAUSED: frozenset({NodeState.READY, NodeState.ASSIGNED, NodeState.BUSY, NodeState.DISCONNECTED, NodeState.TERMINATED}),
    NodeState.DISCONNECTED: frozenset({NodeState.READY, NodeState.TERMINATED}),
    NodeState.TERMINATED: frozenset(),
}

RESUMABLE: frozenset[NodeState] = frozenset({NodeState.READY, NodeState.ASSIGNED, NodeState.BUSY})


class IllegalTransition(Exception):
    def __init__(self, current: NodeState, requested: NodeState) -> None:
        super().__init__(f"illegal transition {current.value} -> {requested.value}")
        self.current = current
        self.requested = requested


def validate_transition(current: NodeState, requested: NodeState) -> None:
    """Raise IllegalTransition unless current -> requested is explicitly legal."""
    if requested not in LEGAL[current]:
        raise IllegalTransition(current, requested)
