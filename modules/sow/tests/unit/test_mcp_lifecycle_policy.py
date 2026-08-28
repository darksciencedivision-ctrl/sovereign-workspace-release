"""Phase 3A: memory lifecycle legality + authorization policy (pure, no store/server)."""
from __future__ import annotations

import pytest

from control_plane.policy import Identity, SovereignPolicy
from mcp_server import lifecycle


# ---------- lifecycle ----------

@pytest.mark.parametrize(("cur", "req"), [
    ("CANDIDATE", "UNDER_REVIEW"), ("UNDER_REVIEW", "ACCEPTED"),
    ("UNDER_REVIEW", "DISPUTED"), ("DISPUTED", "REJECTED"), ("ACCEPTED", "ARCHIVED"),
])
def test_legal_status_edges(cur: str, req: str) -> None:
    lifecycle.validate_status_transition(cur, req, successor_ref="m-x@2" if req == "SUPERSEDED" else None)


@pytest.mark.parametrize(("cur", "req"), [
    ("ACCEPTED", "CANDIDATE"), ("REJECTED", "ACCEPTED"), ("ARCHIVED", "UNDER_REVIEW"),
    ("CANDIDATE", "SUPERSEDED"),
])
def test_illegal_status_edges(cur: str, req: str) -> None:
    with pytest.raises(lifecycle.IllegalStatusTransition):
        lifecycle.validate_status_transition(cur, req)


def test_supersede_requires_successor() -> None:
    with pytest.raises(lifecycle.IllegalStatusTransition, match="successor"):
        lifecycle.validate_status_transition("ACCEPTED", "SUPERSEDED")
    lifecycle.validate_status_transition("ACCEPTED", "SUPERSEDED", successor_ref="m-b@1")


def test_promotion_set() -> None:
    assert lifecycle.is_promotion("ACCEPTED")
    assert lifecycle.is_promotion("REJECTED")
    assert not lifecycle.is_promotion("UNDER_REVIEW")


# ---------- policy ----------

WORKER = Identity("n-w", "worker", "proj")
GATE = Identity("n-g", "gate", "proj")
OPERATOR = Identity("n-o", "operator", "proj")


def _entry(kind="finding", status="CANDIDATE", author="n-w", project="proj") -> dict:
    return {"kind": kind, "status": status, "project_id": project,
            "provenance": {"author_node": author}}


def test_worker_may_publish_candidate() -> None:
    assert SovereignPolicy().authorize_publish(WORKER, _entry()).allow


def test_worker_cannot_publish_accepted() -> None:
    v = SovereignPolicy().authorize_publish(WORKER, _entry(status="ACCEPTED"))
    assert not v.allow and "self-canonization" in v.reason


def test_worker_cannot_write_directive() -> None:
    v = SovereignPolicy().authorize_publish(WORKER, _entry(kind="directive"))
    assert not v.allow and "operator-only" in v.reason


def test_operator_may_write_directive() -> None:
    assert SovereignPolicy().authorize_publish(OPERATOR, _entry(kind="directive", author="n-o")).allow


def test_publish_author_must_match_node() -> None:
    v = SovereignPolicy().authorize_publish(WORKER, _entry(author="someone_else"))
    assert not v.allow and "author_node" in v.reason


def test_only_gate_or_operator_may_promote() -> None:
    cur = {"project_id": "proj", "status": "UNDER_REVIEW", "provenance": {"author_node": "n-w"}}
    assert not SovereignPolicy().authorize_transition(WORKER, cur, "ACCEPTED").allow
    assert SovereignPolicy().authorize_transition(GATE, cur, "ACCEPTED").allow
    assert SovereignPolicy().authorize_transition(OPERATOR, cur, "REJECTED").allow


def test_worker_transitions_only_own_entries() -> None:
    others = {"project_id": "proj", "status": "CANDIDATE", "provenance": {"author_node": "someone"}}
    v = SovereignPolicy().authorize_transition(WORKER, others, "UNDER_REVIEW")
    assert not v.allow and "own entries" in v.reason


def test_cross_project_read_denied() -> None:
    v = SovereignPolicy().authorize_read(WORKER, "memory", "other_proj", "ACCEPTED")
    assert not v.allow and "scope" in v.reason
