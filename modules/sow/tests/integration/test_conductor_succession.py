"""Phase 11 (MANDATORY high-stakes) — conductor succession + persistence. Acceptance test:
kill the conductor mid-project, Resume→Select a different (mock) model, reconstruct from MCP
with ZERO project loss. Plus restart durability, the staleness checklist, and I-X3 succession.
"""
from __future__ import annotations

import base64
import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest
from node_runtime.supervisor.subscription_governor import SubscriptionLimitExceeded

from control_plane.recovery import ConductorState, SuccessionManager, should_snapshot
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _prov(a: str) -> dict:
    return {"author_node": a, "task_id": None, "ts": "2026-07-17T00:00:00+00:00",
            "directive_version": "v2.4", "confidence": "high"}


def _client(server, node, role):
    c = McpClient("127.0.0.1", server.port, server.credentials.issue(node, role, "proj")); c.connect()
    return c


def _project_state(server, conductor_node: str) -> ConductorState:
    """Build a realistic mid-project state, with memory_heads pointing at REAL accepted entries."""
    op = _client(server, "operator", "operator")
    heads = {}
    for i in (1, 2):
        pub = op.call("publish", kind="finding", tier="shared_project",
                      content_b64=_b64(f"accepted finding {i}".encode()), provenance=_prov("operator"),
                      status="ACCEPTED")
        heads[f"finding-{i}"] = pub["entry_id"] + "@1"
    op.close()
    return ConductorState(
        tasks=[{"task_id": "t-1", "state": "DONE"}, {"task_id": "t-2", "state": "IN_PROGRESS"}],
        nodes=[{"node_id": "worker-A", "state": "READY"}, {"node_id": "coder-B", "state": "BUSY"}],
        open_debates=["d-abc123"], pending_gates=["g-xyz"], memory_heads=heads,
        routing={"t-2": "worker-A"}, outstanding_issues=["U-example"], directive_version="v2.4",
        current_conductor={"node_id": conductor_node, "model": "claude-mock", "reason": "operator_selected",
                           "since": "2026-07-17T00:00:00+00:00"})


@pytest.fixture()
def server(tmp_path):
    srv = MCPServer(tmp_path / "store"); srv.start()
    yield srv
    srv.stop()


def test_kill_conductor_mid_project_zero_loss(server) -> None:
    # conductor A serializes its full operating state to MCP
    cond_a = _client(server, "conductor-A", "conductor")
    state = _project_state(server, "conductor-A")
    SuccessionManager(cond_a).serialize(state, trigger="major_event")
    cond_a.close()  # KILL conductor A (session gone)

    # operator Resume -> Select a different model; the new conductor reconstructs from MCP
    cond_b = _client(server, "conductor-B", "conductor")
    reconstructed, report = SuccessionManager(cond_b).reconstruct(
        expected_directive_version="v2.4",
        new_selection={"node_id": "conductor-B", "model": "fable-mock"})

    assert report.ok, report.reasons()
    # ZERO project loss: every piece of operating state survived
    assert reconstructed.tasks == state.tasks
    assert reconstructed.nodes == state.nodes
    assert reconstructed.open_debates == state.open_debates
    assert reconstructed.pending_gates == state.pending_gates
    assert reconstructed.memory_heads == state.memory_heads
    assert reconstructed.routing == state.routing
    assert reconstructed.outstanding_issues == state.outstanding_issues
    # only the conductor SELECTION changed (interface replaceable, memory not)
    assert reconstructed.current_conductor["model"] == "fable-mock"
    assert reconstructed.current_conductor["reason"] == "succession"
    cond_b.close()


def test_snapshot_survives_full_restart(tmp_path) -> None:
    store_dir = tmp_path / "store"
    srv1 = MCPServer(store_dir); srv1.start()
    cond = _client(srv1, "conductor-A", "conductor")
    state = _project_state(srv1, "conductor-A")
    SuccessionManager(cond).serialize(state)
    cond.close(); srv1.stop()

    # full workspace restart over the same store
    srv2 = MCPServer(store_dir); srv2.start()
    cond2 = _client(srv2, "conductor-A", "conductor")
    reconstructed, report = SuccessionManager(cond2).reconstruct(
        expected_directive_version="v2.4", new_selection={"node_id": "conductor-A", "model": "claude-mock"})
    assert report.ok and reconstructed.tasks == state.tasks and reconstructed.memory_heads == state.memory_heads
    cond2.close(); srv2.stop()


def test_staleness_directive_mismatch_flagged(server) -> None:
    cond = _client(server, "conductor-A", "conductor")
    SuccessionManager(cond).serialize(_project_state(server, "conductor-A"))
    _, report = SuccessionManager(cond).reconstruct(
        expected_directive_version="v9.9-WRONG", new_selection={"node_id": "conductor-A", "model": "m"})
    assert not report.ok and "directive_version_match" in report.reasons()
    cond.close()


def test_integrity_tamper_detected(server) -> None:
    """A snapshot whose embedded integrity does not match its state is flagged (not silently
    reconstructed)."""
    cond = _client(server, "conductor-A", "conductor")
    state = _project_state(server, "conductor-A")
    # publish a hand-built snapshot doc with a BOGUS integrity value
    doc = {"state": asdict(state),
           "checkpoint": {"checkpoint_id": "s-forged", "kind": "succession_snapshot",
                          "ts": datetime.now(timezone.utc).isoformat(), "trigger": "manual",
                          "memory_heads": state.memory_heads, "outstanding_issues": [],
                          "directive_version": "v2.4", "conductor": state.current_conductor,
                          "integrity": "sha256:" + "0" * 64, "schema": "checkpoint@1.0"}}
    cond.call("publish", kind="succession_state", tier="shared_project",
              content_b64=_b64(json.dumps(doc, sort_keys=True).encode()), provenance=_prov("conductor-A"),
              status="CANDIDATE")
    _, report = SuccessionManager(cond).reconstruct(
        expected_directive_version="v2.4", new_selection={"node_id": "conductor-A", "model": "m"})
    assert not report.ok and "integrity_ok" in report.reasons()
    cond.close()


def test_snapshot_age_reported_and_bounded(server) -> None:
    cond = _client(server, "conductor-A", "conductor")
    SuccessionManager(cond).serialize(_project_state(server, "conductor-A"))
    # a future 'now' makes the snapshot look old; age bound flags it
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    _, report = SuccessionManager(cond).reconstruct(
        expected_directive_version="v2.4", new_selection={"node_id": "conductor-A", "model": "m"},
        max_age_s=60, now=future)
    assert report.checks["snapshot_age_s"] > 3600 and not report.checks["age_within_limit"]
    cond.close()


def test_ix3_succession_handoff_owned_by_succession_code(server) -> None:
    """Succession preserves I-X3, and the succession code OWNS the release-before-acquire
    ordering (not just the governor). SuccessionManager.perform_handoff releases the
    predecessor's terminal before the successor acquires the one-per-subscription slot."""
    # W-79: claude_code, whose recorded cap is 2 - an UNRECORDED provider now caps at 0 and
    # refuses in acquire's provider-cap gate with ValueError long before the one-per-subscription
    # SLE can fire, which is exactly what narrowing this pin exposed.
    gov = SubscriptionGovernor(); gov.register_subscription("sub-claude_code", "claude_code", 2)
    gov.acquire("sub-claude_code", "conductor-A"); gov.acquire("sub-claude_code", "conductor-A2")
    # acquiring the successor WITHOUT the handoff (both slots held) must fail -> proves the
    # release-first ordering the handoff enforces actually matters
    with pytest.raises(SubscriptionLimitExceeded):
        gov.acquire("sub-claude_code", "conductor-B")
    order = SuccessionManager(_client(server, "c", "conductor")).perform_handoff(
        gov, "sub-claude_code", "conductor-A", "conductor-B")
    assert order == ["release", "acquire"]
    # cap-2 fixture: the handoff releases ONE of two held slots and the successor takes it -
    # the subscription returns to exactly full, now holding conductor-B
    assert gov.active_count("sub-claude_code") == 2


def test_task_graph_version_mismatch_flagged(server) -> None:
    """§19.1 task-graph version match: a snapshot at an older task-graph version is flagged."""
    cond = _client(server, "conductor-A", "conductor")
    state = _project_state(server, "conductor-A"); state.task_graph_version = 5
    SuccessionManager(cond).serialize(state)
    _, report = SuccessionManager(cond).reconstruct(
        expected_directive_version="v2.4", expected_task_graph_version=6,  # graph moved on
        new_selection={"node_id": "conductor-A", "model": "m"})
    assert not report.ok and "task_graph_version_match" in report.reasons()
    cond.close()


def test_post_snapshot_accepted_work_flagged(server) -> None:
    """§19.1 age-vs-event-log-tail: ACCEPTED work that happened AFTER the snapshot (the real
    project-loss window) is detected and flagged, not silently lost."""
    cond = _client(server, "conductor-A", "conductor")
    SuccessionManager(cond).serialize(_project_state(server, "conductor-A"))
    # new accepted work lands AFTER the snapshot
    op = _client(server, "operator", "operator")
    op.call("publish", kind="finding", tier="shared_project", content_b64=_b64(b"post-snapshot work"),
            provenance=_prov("operator"), status="ACCEPTED")
    op.close()
    _, report = SuccessionManager(cond).reconstruct(
        expected_directive_version="v2.4", new_selection={"node_id": "conductor-A", "model": "m"})
    assert not report.ok and "event_tail_current" in report.reasons()
    assert report.checks["newer_accepted_entries"]  # the post-snapshot entry is named
    cond.close()


def test_version_advance_on_tracked_head_flagged(server) -> None:
    """R2: a version advance on an already-tracked memory head (same entry_id, new version)
    is post-snapshot work the entry-id diff alone would miss — memory_heads_current catches it."""
    # publish a finding and track it as a memory head at @1
    worker = _client(server, "w", "worker")
    pub = worker.call("publish", kind="finding", tier="shared_project",
                      content_b64=_b64(b"tracked"), provenance=_prov("w"), status="CANDIDATE")
    eid = pub["entry_id"]
    state = _project_state(server, "conductor-A")
    state.memory_heads["tracked"] = eid + "@1"
    cond = _client(server, "conductor-A", "conductor")
    SuccessionManager(cond).serialize(state)
    # advance that head in place (transition -> new version) AFTER the snapshot
    gate = _client(server, "g", "gate")
    gate.call("transition", entry_id=eid, requested_status="UNDER_REVIEW")  # -> @2
    _, report = SuccessionManager(cond).reconstruct(
        expected_directive_version="v2.4", new_selection={"node_id": "conductor-A", "model": "m"})
    assert not report.ok and "memory_heads_current" in report.reasons()
    worker.close(); gate.close(); cond.close()


def test_empty_node_registry_flagged(server) -> None:
    """node-registry presence is a BLOCKING §19.1 check (not advisory)."""
    cond = _client(server, "conductor-A", "conductor")
    state = _project_state(server, "conductor-A"); state.nodes = []
    SuccessionManager(cond).serialize(state)
    _, report = SuccessionManager(cond).reconstruct(
        expected_directive_version="v2.4", new_selection={"node_id": "conductor-A", "model": "m"})
    assert not report.ok and "node_registry_present" in report.reasons()
    cond.close()


def _seed_entry_under_review(server) -> tuple[object, object, str]:
    """A published finding moved to UNDER_REVIEW: the state both actors will contend over."""
    gate = _client(server, "g-seed", "gate")
    seed_worker = _client(server, "seed-w", "worker")
    pub = seed_worker.call("publish", kind="finding", tier="shared_project",
                           content_b64=_b64(b"seed"), provenance=_prov("seed-w"), status="CANDIDATE")
    eid = pub["entry_id"]
    gate.call("transition", entry_id=eid, requested_status="UNDER_REVIEW")
    return gate, seed_worker, eid


def test_unresolved_conflict_flagged(server) -> None:
    """unresolved-conflict scan is BLOCKING: an open conflict in the store blocks a clean
    succession until reconciled.

    DETERMINISTIC SINCE U451. The original forced the conflict with two threads on a
    `threading.Barrier` and then ASSERTED that a conflict had been created. A barrier releases
    both threads at roughly the same moment; it cannot make them collide. The scheduler was free
    to serialise the two transitions, in which case exactly one ACCEPT landed, no conflict
    existed, and the assertion failed — measured at roughly one run in eighty, on identical
    bytes, with no host or load dependency. That was a defect in the TEST's synchronisation, not
    in the product: the assertion required a condition the setup could not guarantee.

    The condition is now ESTABLISHED rather than hoped for, through the store's own CAS seam,
    which is the same window `MemoryService.transition` opens between reading the head and
    committing against it. No sleeps, no retries, no extra threads.
    """
    gate, seed_worker, eid = _seed_entry_under_review(server)

    # BOTH actors observe the SAME pre-transition head — the value `transition()` reads first
    # and CASes against last.
    observed_head = server.store.get_head(eid)
    losing_version = {**server.store.get_entry(observed_head), "status": "ACCEPTED"}

    # Actor A attempts and WINS, through the ordinary service path: the head advances.
    won = gate.call("transition", entry_id=eid, requested_status="ACCEPTED")
    assert won["applied"] is True
    assert server.store.get_head(eid) != observed_head

    # Actor B attempts the SAME transition from the head it observed BEFORE A won. Its CAS is
    # deterministically stale, which is exactly what the losing thread used to be relied upon to
    # become by luck.
    lost = server.store.commit_version(losing_version, eid, observed_head, conflict_id="c-u451")
    assert lost.ok is False, "the stale CAS must lose"
    assert lost.conflict, "a losing writer leaves a conflict record, never a silent overwrite"

    assert gate.call("list_conflicts", key=eid)  # a conflict exists

    cond = _client(server, "conductor-A", "conductor")
    SuccessionManager(cond).serialize(_project_state(server, "conductor-A"))
    _, report = SuccessionManager(cond).reconstruct(
        expected_directive_version="v2.4", new_selection={"node_id": "conductor-A", "model": "m"})
    assert not report.ok and "no_unresolved_conflicts" in report.reasons()
    gate.close(); seed_worker.close(); cond.close()


def test_succession_does_not_flag_conflicts_when_none_are_open(server) -> None:
    """Calibration for the test above, in the other direction.

    Identical setup and an identical winning transition, with the LOSING write removed. If the
    succession check still reported `no_unresolved_conflicts`, the assertion above would be
    passing for some reason other than the conflict it claims to be about — which is how a test
    keeps reporting a property it stopped measuring.
    """
    gate, seed_worker, eid = _seed_entry_under_review(server)
    won = gate.call("transition", entry_id=eid, requested_status="ACCEPTED")
    assert won["applied"] is True
    assert not gate.call("list_conflicts", key=eid), "no losing writer, so no conflict"

    cond = _client(server, "conductor-A", "conductor")
    SuccessionManager(cond).serialize(_project_state(server, "conductor-A"))
    _, report = SuccessionManager(cond).reconstruct(
        expected_directive_version="v2.4", new_selection={"node_id": "conductor-A", "model": "m"})
    assert "no_unresolved_conflicts" not in report.reasons()
    gate.close(); seed_worker.close(); cond.close()


def test_cadence_policy_major_event_and_interval() -> None:
    assert should_snapshot(last_snapshot_ts=100.0, now_ts=101.0, had_major_event=True)     # event -> yes
    assert should_snapshot(last_snapshot_ts=None, now_ts=101.0, had_major_event=False)     # first -> yes
    assert should_snapshot(last_snapshot_ts=100.0, now_ts=500.0, had_major_event=False, interval_s=300)  # elapsed
    assert not should_snapshot(last_snapshot_ts=100.0, now_ts=200.0, had_major_event=False, interval_s=300)  # within
