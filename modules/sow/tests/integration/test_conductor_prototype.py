"""Phase 5 exit criteria: conductor + two workers end-to-end. Capability-based assignment
via the Scheduler; one artifact routed CANDIDATE->gate->ACCEPTED; zero manual transcript
routing (every hop is an MCP entry / graph event); plan gate + acceptance packet produced."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from adapters.conductor import publish_conductor_files
from control_plane.orchestration.conductor_prototype import ConductorPrototype
from control_plane.tasks.graph import TaskState
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer

ROOT = Path(__file__).resolve().parents[2]
CONDUCTOR_DIR = ROOT / "conductor"


@pytest.fixture()
def proto(tmp_path):
    srv = MCPServer(tmp_path / "store"); srv.start()
    op = McpClient("127.0.0.1", srv.port, srv.credentials.issue("op-boot", "operator", "proj")); op.connect()
    manifest = publish_conductor_files(op, "op-boot", CONDUCTOR_DIR)
    op.close()
    p = ConductorPrototype(srv, manifest)
    yield {"srv": srv, "proto": p}
    p.close(); srv.stop()


def test_end_to_end_two_workers_one_artifact_routed_to_accepted(proto) -> None:
    trace = proto["proto"].run("Design the offline conductor roster")

    # capability-based assignment: exactly 2 workers assigned, by descriptor rationale
    assert len(trace["assignments"]) == 2 and not trace["queued"]
    assert {a["node"] for a in trace["assignments"]} == {"worker-A", "worker-B"}
    assert all("by descriptor" in a["rationale"] for a in trace["assignments"])

    # both tasks reached DONE via GATED_PASS; artifacts routed to ACCEPTED
    graph = proto["proto"]._graph
    assert all(graph.get(t).state is TaskState.DONE for t in ("t-1", "t-2"))
    assert len(trace["accepted_entries"]) == 2

    # plan gate + acceptance packet exist
    assert trace["plan_gate"].startswith("m-")
    assert trace["acceptance_packet"].startswith("m-")


def test_every_accepted_artifact_carries_provenance_with_task_id(proto) -> None:
    trace = proto["proto"].run("Do the thing")
    srv = proto["srv"]
    reader = McpClient("127.0.0.1", srv.port, srv.credentials.issue("audit", "operator", "proj")); reader.connect()
    accepted = reader.call("read_status", status="ACCEPTED")
    findings = [e for e in accepted if e["kind"] == "finding" and e["entry_id"] in trace["accepted_entries"]]
    assert len(findings) == 2
    for f in findings:
        prov = f["provenance"]
        assert prov["task_id"] in ("t-1", "t-2")           # provenanced with the task it served
        assert prov["author_node"] in ("worker-A", "worker-B")
        assert "gate-1" in prov.get("reviewers", [])        # the gate that promoted it is recorded
        assert prov["gate_result"]                          # promotion carries a gate result
    reader.close()


def test_zero_manual_transcript_routing(proto) -> None:
    """Every worker got its context from an MCP entry ref, and every result left via an MCP
    publish — the trace's hops are all MCP entries / graph events, never a passed transcript."""
    objective = "Route via MCP only, uniquely-marked-objective-42"
    trace = proto["proto"].run(objective)
    kinds = {e["kind"] for e in trace["task_events"]}
    assert {"task_added", "task_assigned", "task_transition", "artifact_attached"} <= kinds
    # each worker recorded reading context from an MCP entry, not a transcript
    for w in proto["proto"]._workers.values():
        assigned = [e for e in w._session_log if e["kind"] == "assigned"]
        assert assigned and assigned[0]["context_entry"].startswith("m-")
    # and the published artifact bytes actually contain the MCP-sourced objective (proves the
    # worker read it from MCP, not that it merely logged a ref)
    srv = proto["srv"]
    reader = McpClient("127.0.0.1", srv.port, srv.credentials.issue("aud2", "operator", "proj")); reader.connect()
    for eid in trace["accepted_entries"]:
        body = base64.b64decode(reader.call("get_content", entry_id=eid)["content_b64"]).decode("utf-8")
        assert objective in body
    reader.close()


def test_failed_stage_gate_blocks_dependent_end_to_end(tmp_path) -> None:
    """Invariant 16 through the real worker/gate/MCP flow: a stage-gate REJECT sends its task
    GATED_FAIL and a dependent task stays BLOCKED — no path to DONE. Exercises the whole
    failure path (worker publishes CANDIDATE -> gate rejects -> graph blocks dependent)."""
    from control_plane.tasks.graph import TaskState
    srv = MCPServer(tmp_path / "store"); srv.start()
    op = McpClient("127.0.0.1", srv.port, srv.credentials.issue("op-b", "operator", "proj")); op.connect()
    manifest = publish_conductor_files(op, "op-b", CONDUCTOR_DIR); op.close()
    p = ConductorPrototype(srv, manifest)
    try:
        objective = "dependency chain objective"
        obj_pub = p._op.call("publish", kind="finding", tier="shared_project",
                             content_b64=base64.b64encode(objective.encode()).decode("ascii"),
                             provenance={"author_node": "operator", "task_id": None,
                                         "ts": "2026-07-17T00:00:00+00:00", "directive_version": "v2.4",
                                         "confidence": "high"}, status="ACCEPTED")
        p._conductor.start(); p._conductor.run_cycle(objective)
        req = {"capability": "reasoning", "requirements": {"structured_output": True, "min_context": 8000}}
        p._graph.add_task("t-1", req)
        p._graph.add_task("t-2", req, deps=("t-1",))     # t-2 waits on t-1
        p._spawn_worker("worker-A")
        assignments, _ = p._scheduler.schedule_ready()
        assert [a.task_id for a in assignments] == ["t-1"]   # only t-1 is READY
        a = assignments[0]; worker = p._workers[a.node_id]
        p._graph.transition("t-1", TaskState.IN_PROGRESS, reason="start", by=a.node_id)
        worker.assign("t-1", obj_pub["entry_id"]); result = worker.execute()
        assert result["published"]                            # worker published a CANDIDATE
        p._graph.attach_artifact("t-1", result["entry_id"])
        p._graph.transition("t-1", TaskState.AWAITING_GATE, reason="pub", by=a.node_id)
        p._gate.call("transition", entry_id=result["entry_id"], requested_status="UNDER_REVIEW")
        p._gate.call("transition", entry_id=result["entry_id"], requested_status="REJECTED", reviewer_note="reject")
        p._graph.transition("t-1", TaskState.GATED_FAIL, reason="stage gate REJECT", by="gate-1")
        p._graph.transition("t-1", TaskState.BLOCKED, reason="gated fail", by="gate-1")
        assert p._graph.get("t-1").state is TaskState.BLOCKED
        assert p._graph.get("t-2").state is TaskState.BLOCKED   # dependent never advanced (inv 16)
    finally:
        p.close(); srv.stop()


def test_local_gate_fail_does_not_crash_and_blocks_task(proto) -> None:
    """F3 regression: an objective that trips the node-local gate (placeholder marker) must
    not KeyError the orchestrator; the task blocks and nothing is accepted."""
    trace = proto["proto"].run("Design the TODO roster")  # 'TODO' fails no_placeholders in the artifact
    assert trace["failed_tasks"]                            # at least one task blocked at the local gate
    graph = proto["proto"]._graph
    assert any(graph.get(t).state == TaskState.BLOCKED for t in ("t-1", "t-2"))


def test_worker_cannot_self_promote_only_gate_did(proto) -> None:
    trace = proto["proto"].run("Check promotion authority")
    srv = proto["srv"]
    # a worker token attempting to ACCEPT one of the findings must be refused
    from mcp_server.protocol import McpError
    w = McpClient("127.0.0.1", srv.port, srv.credentials.issue("rogue-worker", "worker", "proj")); w.connect()
    entry = trace["accepted_entries"][0]
    with pytest.raises(McpError):
        w.call("transition", entry_id=entry, requested_status="ACCEPTED")
    w.close()
