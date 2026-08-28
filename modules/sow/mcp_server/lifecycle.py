"""Memory-state lifecycle legality (Plan section 9.4; Canonical Handoff 2.10.3).

Pure state machine over memory@1.0 statuses — schema legality, NOT authorization (who may
request a transition is the control plane's decision, policy.py). Split out so both the
server and the policy reason over the same edges.

    CANDIDATE -> UNDER_REVIEW -> DISPUTED
    UNDER_REVIEW/DISPUTED/CANDIDATE -> ACCEPTED | ACCEPTED_WITH_RESERVATIONS | REJECTED
    ACCEPTED* -> SUPERSEDED (requires a successor)  |  any -> ARCHIVED
Nothing is deleted; ARCHIVED and terminal-REJECTED are end states.
"""
from __future__ import annotations

CANDIDATE = "CANDIDATE"
UNDER_REVIEW = "UNDER_REVIEW"
DISPUTED = "DISPUTED"
ACCEPTED = "ACCEPTED"
ACCEPTED_WITH_RESERVATIONS = "ACCEPTED_WITH_RESERVATIONS"
REJECTED = "REJECTED"
SUPERSEDED = "SUPERSEDED"
ARCHIVED = "ARCHIVED"

PROMOTED = frozenset({ACCEPTED, ACCEPTED_WITH_RESERVATIONS, REJECTED})

_LEGAL: dict[str, frozenset[str]] = {
    CANDIDATE: frozenset({UNDER_REVIEW, REJECTED, ARCHIVED, ACCEPTED, ACCEPTED_WITH_RESERVATIONS}),
    UNDER_REVIEW: frozenset({DISPUTED, ACCEPTED, ACCEPTED_WITH_RESERVATIONS, REJECTED, ARCHIVED}),
    DISPUTED: frozenset({UNDER_REVIEW, ACCEPTED, ACCEPTED_WITH_RESERVATIONS, REJECTED, ARCHIVED}),
    ACCEPTED: frozenset({SUPERSEDED, ARCHIVED}),
    ACCEPTED_WITH_RESERVATIONS: frozenset({SUPERSEDED, ARCHIVED, ACCEPTED}),
    REJECTED: frozenset({ARCHIVED}),
    SUPERSEDED: frozenset({ARCHIVED}),
    ARCHIVED: frozenset(),
}


class IllegalStatusTransition(Exception):
    pass


def is_legal(current: str, requested: str) -> bool:
    return requested in _LEGAL.get(current, frozenset())


def validate_status_transition(current: str, requested: str, *, successor_ref: str | None = None) -> None:
    if not is_legal(current, requested):
        raise IllegalStatusTransition(f"illegal memory status transition {current} -> {requested}")
    if requested == SUPERSEDED and not successor_ref:
        raise IllegalStatusTransition("SUPERSEDED requires a successor reference")


def is_promotion(requested: str) -> bool:
    """A promotion into accepted/rejected state — reserved for gate/operator authority."""
    return requested in PROMOTED
