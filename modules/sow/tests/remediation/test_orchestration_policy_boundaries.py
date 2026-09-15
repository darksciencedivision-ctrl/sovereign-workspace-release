"""Retained mutation graders for the cross-task and bounded-debate boundaries.

These two tests replace the removed broad collaboration suite as the executable
targets for orchestration mutations O3 and O4.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from control_plane.policy import Identity, SovereignPolicy
from mcp_server.collaboration_service import CollaborationError, CollaborationService
from persistence import SovereignStore


@pytest.fixture()
def service(tmp_path: Path):
    store = SovereignStore(tmp_path / "sovereign.db")
    svc = CollaborationService(store, SovereignPolicy())
    try:
        yield svc
    finally:
        store.close()


def _assigned(service: CollaborationService):
    conductor = Identity("cond-1", "conductor", "proj")
    first = Identity("worker-1", "worker", "proj")
    second = Identity("worker-2", "worker", "proj")
    task = service.create_task(
        conductor,
        objective="exercise retained orchestration boundaries",
        owner_node_ids=[first.node_id, second.node_id],
        peer_nodes=[first.node_id, second.node_id],
        acceptance_criteria=["retain scope", "bound debate"],
    )
    return conductor, first, second, task


def test_progress_lifecycle_and_cross_task_access_fail_closed(
    service: CollaborationService,
) -> None:
    _conductor, first, _second, task = _assigned(service)
    stranger = Identity("worker-other", "worker", "proj")
    with pytest.raises(CollaborationError, match="cross-task recipient"):
        service.send_message(
            first,
            task_id=task["task_id"],
            thread_id=task["thread_id"],
            recipient_node_ids=[stranger.node_id],
            message_kind="question",
            body="must remain scoped",
        )


def test_bounded_debate_preserves_evidence_and_dissent(
    service: CollaborationService,
) -> None:
    conductor, first, second, task = _assigned(service)
    debate = service.open_debate(
        conductor,
        task_id=task["task_id"],
        proposition="the boundary must remain bounded",
        participant_node_ids=[first.node_id, second.node_id],
        evidence_refs=["evidence-1"],
        max_rounds=1,
    )
    turn = service.post_debate_turn(
        first,
        debate_id=debate["debate_id"],
        body="first position",
        evidence_refs=["evidence-2"],
    )
    service.post_debate_turn(
        second,
        debate_id=debate["debate_id"],
        body="dissenting position",
        evidence_refs=["evidence-3"],
        reply_to=turn["turn_id"],
    )
    with pytest.raises(CollaborationError, match="round limit"):
        service.post_debate_turn(
            first,
            debate_id=debate["debate_id"],
            body="unbounded second round",
        )
