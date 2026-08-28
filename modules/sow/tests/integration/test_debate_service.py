"""Phase 7 §2.8 acceptance: a NON-CONDUCTOR node requests a debate; bounded rounds, dissent
preservation, cost cap, and invariant 18 (no node solely judges its own work) all hold; the
debate record is written immutably to MCP."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from control_plane.policy import Identity, SovereignPolicy
from debate_service.cost_governor.governor import CostGovernor
from debate_service.evidence_manager.manager import EvidenceManager, mcp_resolver
from debate_service.service import DebateAuthorizationError, DebateService
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer
from tests.fixtures.mock_debater import MockDebater


def _prov(a): return {"author_node": a, "task_id": None, "ts": "2026-07-17T00:00:00+00:00",
                      "directive_version": "v2.4", "confidence": "high"}


@pytest.fixture()
def wired(tmp_path):
    srv = MCPServer(tmp_path / "store"); srv.start()
    # a real evidence entry to cite
    caller = McpClient("127.0.0.1", srv.port, srv.credentials.issue("worker-1", "worker", "proj")); caller.connect()
    ev = caller.call("publish", kind="finding", tier="shared_project",
                     content_b64=base64.b64encode(b"evidence body").decode("ascii"),
                     provenance=_prov("worker-1"), status="CANDIDATE")
    svc = DebateService(SovereignPolicy(), CostGovernor(per_caller_quota=100_000, global_concurrent_cap=4),
                        EvidenceManager(mcp_resolver(caller)), caller, round_cost=100)
    yield {"srv": srv, "caller": caller, "svc": svc, "evidence_ref": ev["entry_id"]}
    caller.close(); srv.stop()


def _req(caller="worker-1", topic="Is approach A better than B?", rounds=5, budget=10_000):
    return {"caller_node": caller, "topic": topic,
            "participants": [{"capability": "reasoning", "requirements": {"structured_output": True}}],
            "max_rounds": rounds, "budget": {"tokens": budget}}


def test_non_conductor_can_request_debate(wired) -> None:
    """I-DS1: a worker (not the conductor) requests a debate and it runs."""
    caller = Identity("worker-1", "worker", "proj")
    debaters = [MockDebater("worker-1", "A", evidence_refs=[wired["evidence_ref"]]),
                MockDebater("reviewer-2", "A", converge_to="A", converge_after=1,
                            evidence_refs=[wired["evidence_ref"]])]
    rec = wired["svc"].request_debate(caller, _req(), debaters)
    assert rec["debate_id"].startswith("d-")
    assert rec["result"]["outcome"] in ("CONVERGED", "DISSENT_PRESERVED")
    # written immutably to MCP as an evidence record a gate can reference
    assert rec["mcp_entry"].startswith("m-")
    stored = wired["caller"].call("get_content", entry_id=rec["mcp_entry"])
    assert json.loads(base64.b64decode(stored["content_b64"]))["debate_id"] == rec["debate_id"]


def test_caller_cannot_be_sole_judge(wired) -> None:
    """Invariant 18: a debate whose only participant is the caller is refused."""
    caller = Identity("worker-1", "worker", "proj")
    debaters = [MockDebater("worker-1", "A", evidence_refs=[wired["evidence_ref"]])]
    with pytest.raises(DebateAuthorizationError, match="invariant 18|solely judges"):
        wired["svc"].request_debate(caller, _req(), debaters)


def test_dissent_preserved_flows_to_record(wired) -> None:
    caller = Identity("worker-1", "worker", "proj")
    debaters = [MockDebater("worker-1", "keep", evidence_refs=[wired["evidence_ref"]]),
                MockDebater("reviewer-2", "drop", evidence_refs=[wired["evidence_ref"]])]
    rec = wired["svc"].request_debate(caller, _req(rounds=3), debaters)
    assert rec["result"]["outcome"] == "DISSENT_PRESERVED"
    assert rec["result"]["dissent"] and "keep" in rec["result"]["dissent"] and "drop" in rec["result"]["dissent"]


def test_budget_exhaustion_is_clean(wired) -> None:
    caller = Identity("worker-1", "worker", "proj")
    debaters = [MockDebater("worker-1", "x", evidence_refs=[wired["evidence_ref"]]),
                MockDebater("reviewer-2", "y", evidence_refs=[wired["evidence_ref"]])]
    rec = wired["svc"].request_debate(caller, _req(rounds=5, budget=250), debaters)  # 2 rounds affordable
    assert rec["result"]["outcome"] == "BUDGET_EXHAUSTED"
    assert rec["result"]["rounds_used"] == 2 and rec["result"]["cost_actual"]["tokens"] == 200


def test_voice_role_cannot_request_debate(wired) -> None:
    caller = Identity("voice-1", "voice", "proj")
    debaters = [MockDebater("voice-1", "a"), MockDebater("n2", "b")]
    with pytest.raises(DebateAuthorizationError, match="may not request debate"):
        wired["svc"].request_debate(caller, _req(caller="voice-1"), debaters)


@pytest.mark.parametrize("bad", [
    {"topic": "", "max_rounds": 3, "budget": {"tokens": 100}, "participants": [{"capability": "reasoning"}]},
    {"topic": "t", "max_rounds": 9, "budget": {"tokens": 100}, "participants": [{"capability": "reasoning"}]},
    {"topic": "t", "max_rounds": 3, "budget": {"tokens": 0}, "participants": [{"capability": "reasoning"}]},
    {"topic": "t", "max_rounds": 3, "participants": [{"capability": "reasoning"}]},  # no budget
])
def test_malformed_request_fails_clean_not_crash(wired, bad) -> None:
    """MINOR: a malformed request is a clean DebateAuthorizationError, not a KeyError/TypeError."""
    caller = Identity("worker-1", "worker", "proj")
    debaters = [MockDebater("worker-1", "a", evidence_refs=[wired["evidence_ref"]]),
                MockDebater("n2", "b", evidence_refs=[wired["evidence_ref"]])]
    bad = {"caller_node": "worker-1", **bad}
    with pytest.raises(DebateAuthorizationError):
        wired["svc"].request_debate(caller, bad, debaters)


def test_global_cap_refuses_extra_debate(tmp_path) -> None:
    srv = MCPServer(tmp_path / "store"); srv.start()
    try:
        c = McpClient("127.0.0.1", srv.port, srv.credentials.issue("w", "worker", "proj")); c.connect()
        gov = CostGovernor(global_concurrent_cap=1)
        gov.open_debate("d-existing", "someone", 100)  # occupy the only slot
        svc = DebateService(SovereignPolicy(), gov, EvidenceManager(lambda r: True), c)
        caller = Identity("w", "worker", "proj")
        debaters = [MockDebater("w", "a"), MockDebater("n2", "b")]
        with pytest.raises(DebateAuthorizationError, match="global concurrent"):
            svc.request_debate(caller, _req(caller="w"), debaters)
        c.close()
    finally:
        srv.stop()
