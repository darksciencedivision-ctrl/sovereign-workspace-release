"""Phase 15E `.objective` — the operator command surface end to end over a REAL MCP server.

Proves the governed pause OP-7 §12.5 item 5 requires: the operator submits an objective, the
conductor decomposes and the plan gate runs, the plan SURFACES in the approval drawer, and ONLY on
operator approval does the LiveGovernedFlow assign → workers publish CANDIDATE → gates → the
conductor synthesizes an acceptance packet. The two load-bearing governance properties:

  * invariant 1 — no worker is assigned until the operator approves (the plan pauses);
  * invariant 16 — a gate-failed plan is surfaced but cannot be approved into execution.

MOCK-FIRST (§10.4): the conductor/worker legs are mock (`LiveGovernedFlow` default); no `claude`
process is spawned. This proves the SURFACE and the governance around the flow, not a live model.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from adapters.conductor import publish_conductor_files
from control_plane.orchestration.live_flow import LiveGovernedFlow
from control_plane.orchestration.operator_surface import (
    ApprovalError,
    ApprovalKind,
    ApprovalQueue,
    ObjectiveIntake,
    ObjectiveIntakeError,
)
from control_plane.policy import Identity
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer

ROOT = Path(__file__).resolve().parents[2]
CONDUCTOR_DIR = ROOT / "conductor"
OBJECTIVE = "Design the offline conductor roster"
OPERATOR = Identity(node_id="op", role="operator", project_id="proj")
WORKER = Identity(node_id="w", role="worker", project_id="proj")


@pytest.fixture()
def harness(tmp_path):
    srv = MCPServer(tmp_path / "store")
    srv.start()
    op = McpClient("127.0.0.1", srv.port, srv.credentials.issue("op-boot", "operator", "proj"))
    op.connect()
    manifest = publish_conductor_files(op, "op-boot", CONDUCTOR_DIR)
    op.close()
    flow = LiveGovernedFlow(srv, manifest)
    queue = ApprovalQueue()
    intake = ObjectiveIntake(flow, queue)
    yield {"srv": srv, "flow": flow, "queue": queue, "intake": intake}
    flow.close()
    srv.stop()


def _reader(srv):
    c = McpClient("127.0.0.1", srv.port, srv.credentials.issue("audit", "operator", "proj"))
    c.connect()
    return c


def test_submit_surfaces_a_plan_and_assigns_nothing_until_approved(harness) -> None:
    intake, queue, flow = harness["intake"], harness["queue"], harness["flow"]

    submitted = intake.submit(OBJECTIVE)
    # the plan surfaced for approval ...
    assert submitted["approvable"] is True and queue.badge_count == 1
    item = queue.get(submitted["item_id"])
    assert item.kind is ApprovalKind.PLAN and not item.resolved
    assert submitted["proposal"]["task_count"] >= 2
    # ... and NOT ONE task has been assigned (invariant 1 — the plan paused for the operator).
    # begin() built the graph (a no-dep task is READY, a dependent one PENDING) but no wave has run,
    # so nothing has advanced past READY into ASSIGNED/IN_PROGRESS/DONE.
    assert flow.graph.all_tasks(), "the plan gate passed, so the graph was built"
    assert all(t.state.value in ("PENDING", "READY") for t in flow.graph.all_tasks())
    # nothing accepted in MCP beyond the seeded conductor files + the objective (no worker artifact)
    reader = _reader(harness["srv"])
    accepted_kinds = {e.get("kind") for e in reader.call("read_status", status="ACCEPTED")}
    assert "artifact" not in accepted_kinds


def test_operator_approval_runs_the_flow_to_an_acceptance_packet(harness) -> None:
    intake, queue = harness["intake"], harness["queue"]
    submitted = intake.submit(OBJECTIVE)

    # a non-operator cannot approve (invariant 1)
    with pytest.raises(ApprovalError):
        intake.approve(WORKER)
    assert queue.badge_count == 1

    result = intake.approve(OPERATOR)
    # the queue item is resolved-approved; the flow ran to a real acceptance packet
    assert queue.badge_count == 0
    assert result["item"]["decision"] == "approve"
    packet = result["packet"]
    assert packet["schema"] == "acceptance_packet@1.0" and packet["objective"] == OBJECTIVE
    assert packet["accepted_count"] > 0
    assert result["acceptance_packet"].startswith("m-")
    # the packet is a mock-leg run — never packaged as live
    assert packet["legs"]["conductor"] == "mock" and packet["operator_disposition"] == "pending"
    # the accepted artifacts really landed ACCEPTED in MCP
    reader = _reader(harness["srv"])
    accepted_ids = {e["entry_id"] for e in reader.call("read_status", status="ACCEPTED")}
    assert set(packet_entry_ids(packet)) <= accepted_ids


def packet_entry_ids(packet) -> list[str]:
    return [row["entry_id"] for row in packet["accepted"]]


def test_operator_rejection_declines_the_objective_and_assigns_nothing(harness) -> None:
    intake, queue, flow = harness["intake"], harness["queue"], harness["flow"]
    intake.submit(OBJECTIVE)

    result = intake.reject(OPERATOR, reason="not this sprint")
    assert result["declined"] is True and result["assigned"] is False
    assert queue.badge_count == 0
    # the flow was abandoned: no wave ran, so nothing advanced past READY and nothing reached MCP
    assert all(t.state.value in ("PENDING", "READY") for t in flow.graph.all_tasks())
    reader = _reader(harness["srv"])
    assert "artifact" not in {e.get("kind") for e in reader.call("read_status", status="ACCEPTED")}


def test_second_submit_is_refused_one_objective_per_intake(harness) -> None:
    intake = harness["intake"]
    intake.submit(OBJECTIVE)
    with pytest.raises(ObjectiveIntakeError):
        intake.submit("a different objective")


def test_approve_before_submit_is_refused(harness) -> None:
    intake = harness["intake"]
    with pytest.raises(ObjectiveIntakeError):
        intake.approve(OPERATOR)
