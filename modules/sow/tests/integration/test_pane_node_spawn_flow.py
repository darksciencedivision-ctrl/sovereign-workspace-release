"""Phase 15E `.spawn` (integration): a governed node spawned FROM a picker selection runs the
whole governance path through the REAL MCP server — scoped context read from MCP, node-local
gate, CANDIDATE published — for both a frontier (mock-first) and a local-reasoning node, then
tears down (D-LOOP-1). No live call: the frontier backend is a MockClaudeCliBackend.
"""
from __future__ import annotations

import base64

import pytest

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER, MockClaudeCliBackend
from control_plane.nodes.pane_picker import build_pane_picker
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer
from node_runtime.supervisor.pane_node_spawn import PaneSelection, spawn_node_from_selection
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor
from scheduler.residency_planner.residency_planner import ResidencyPlanner


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _prov(author: str) -> dict:
    return {"author_node": author, "task_id": None, "ts": "2026-07-24T00:00:00+00:00",
            "directive_version": "v2.4", "confidence": "high"}


@pytest.fixture()
def server(tmp_path):
    srv = MCPServer(tmp_path / "store"); srv.start()
    yield srv
    srv.stop()


def _client(server: MCPServer, node_id: str, role: str) -> McpClient:
    c = McpClient("127.0.0.1", server.port, server.credentials.issue(node_id, role, "proj"))
    c.connect()
    return c


def _authorized() -> LiveAuthorization:
    return LiveAuthorization(
        authorized=True, providers=frozenset({CLAUDE_CODE_ADAPTER}),
        terminals_per_subscription=2, register_row="OP-6", source="(test)", reason="test auth")


def _option(picker: dict, provider: str, label: str) -> dict:
    return next(o for o in picker["options"] if o["provider"] == provider and o["label"] == label)


def test_frontier_selection_end_to_end_publishes_candidate_then_teardown(server, tmp_path) -> None:
    op = _client(server, "op", "operator")
    obj = op.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64(b"Explain compare-and-swap in one sentence."),
                  provenance=_prov("op"), status="ACCEPTED")
    mcp = _client(server, "claude-node", "worker")

    live = _authorized()
    picker = build_pane_picker(live, claude_available=True)
    sel = PaneSelection(option=_option(picker, CLAUDE_CODE_ADAPTER, "Opus 4.8"), role="reasoning",
                        mode="autonomous", node_id="claude-node", permission_profile_id="pp-frontier",
                        subscription_ref="claude-sub")
    gov = SubscriptionGovernor()
    spawn = spawn_node_from_selection(
        sel, live=live, governor=gov, profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        mcp_client=mcp, operator_terms_confirmed=True, backend=MockClaudeCliBackend())

    assert spawn.chrome.subscription == {"ref": "claude-sub", "in_use": 1, "allowance": 2}
    spawn.handle.assign("t-live", obj["entry_id"])
    result = spawn.handle.execute()
    assert result["published"] and result["local_gate"] == "PASS"
    body = base64.b64decode(mcp.call("get_content", entry_id=result["entry_id"])["content_b64"]).decode("utf-8")
    assert "claude_code" in body

    spawn.teardown()
    assert gov.active_count("claude-sub") == 0  # D-LOOP-1: released within the unit
    mcp.close(); op.close()


def test_local_reasoning_selection_end_to_end_publishes_candidate(server, tmp_path) -> None:
    op = _client(server, "op", "operator")
    obj = op.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64(b"Summarize the CAS invariant."),
                  provenance=_prov("op"), status="ACCEPTED")
    mcp = _client(server, "local-node", "worker")

    planner = ResidencyPlanner(total_vram_mb=12000)
    planner.register_model("llama3:8b", 6000)
    picker = build_pane_picker(LiveAuthorization.denied("offline"),
                               ollama_models=["llama3:8b"], residency=planner.residency_map())
    sel = PaneSelection(option=_option(picker, "ollama_local", "llama3:8b"), role="reasoning",
                        mode="autonomous", node_id="local-node", permission_profile_id="pp-local")
    gov = SubscriptionGovernor()
    spawn = spawn_node_from_selection(
        sel, live=LiveAuthorization.denied("offline"), governor=gov,
        profile_loader=ProfileLoader(DeploymentProfile("offline_airgapped")), mcp_client=mcp,
        residency_planner=planner)

    assert spawn.chrome.locality == "local" and spawn.chrome.subscription is None
    assert spawn.chrome.residency == "loading"
    assert gov.status() == {}  # a local node never touches the subscription governor
    spawn.handle.assign("t-local", obj["entry_id"])
    result = spawn.handle.execute()
    assert result["published"] and result["local_gate"] == "PASS"
    body = base64.b64decode(mcp.call("get_content", entry_id=result["entry_id"])["content_b64"]).decode("utf-8")
    assert "local-node" in body
    spawn.teardown()  # no-op for local
    mcp.close(); op.close()
