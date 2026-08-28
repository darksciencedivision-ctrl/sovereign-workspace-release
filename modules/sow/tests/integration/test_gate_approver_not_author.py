"""Phase 8: the memory-layer half of invariant 18 — a gate may not promote an entry it
authored (a node cannot solely judge its own work), enforced at the authority."""
from __future__ import annotations

import base64
from pathlib import Path

import pytest

from mcp_server.protocol import McpClient, McpError
from mcp_server.server import MCPServer


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _prov(a: str) -> dict:
    return {"author_node": a, "task_id": None, "ts": "2026-07-17T00:00:00+00:00",
            "directive_version": "v2.4", "confidence": "high"}


@pytest.fixture()
def server(tmp_path):
    srv = MCPServer(tmp_path / "store"); srv.start()
    yield srv
    srv.stop()


def _client(server, node, role):
    c = McpClient("127.0.0.1", server.port, server.credentials.issue(node, role, "proj")); c.connect()
    return c


def test_gate_cannot_promote_its_own_authored_entry(server) -> None:
    gate = _client(server, "gate-1", "gate")
    # the gate node itself authors an entry
    pub = gate.call("publish", kind="finding", tier="shared_project",
                    content_b64=_b64(b"gate's own finding"), provenance=_prov("gate-1"), status="CANDIDATE")
    gate.call("transition", entry_id=pub["entry_id"], requested_status="UNDER_REVIEW")
    with pytest.raises(McpError, match="may not promote an entry it authored|invariant 18"):
        gate.call("transition", entry_id=pub["entry_id"], requested_status="ACCEPTED")
    gate.close()


def test_a_different_gate_may_promote_it(server) -> None:
    author_gate = _client(server, "gate-1", "gate")
    other_gate = _client(server, "gate-2", "gate")
    pub = author_gate.call("publish", kind="finding", tier="shared_project",
                           content_b64=_b64(b"finding"), provenance=_prov("gate-1"), status="CANDIDATE")
    author_gate.call("transition", entry_id=pub["entry_id"], requested_status="UNDER_REVIEW")
    res = other_gate.call("transition", entry_id=pub["entry_id"], requested_status="ACCEPTED")
    assert res["applied"]  # an independent gate may promote it
    author_gate.close(); other_gate.close()


def test_gate_cannot_publish_directly_into_accepted(server) -> None:
    """F2: the publish path is also invariant-18 guarded — a gate cannot publish its own
    entry straight into ACCEPTED (bypassing the transition path)."""
    gate = _client(server, "gate-1", "gate")
    with pytest.raises(McpError, match="invariant 18|promoted state"):
        gate.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64(b"self-canonized"), provenance=_prov("gate-1"), status="ACCEPTED")
    gate.close()


def test_worker_authored_entry_promoted_by_gate_normally(server) -> None:
    worker = _client(server, "worker-1", "worker")
    gate = _client(server, "gate-1", "gate")
    pub = worker.call("publish", kind="finding", tier="shared_project",
                      content_b64=_b64(b"worker finding"), provenance=_prov("worker-1"), status="CANDIDATE")
    worker.call("transition", entry_id=pub["entry_id"], requested_status="UNDER_REVIEW")
    res = gate.call("transition", entry_id=pub["entry_id"], requested_status="ACCEPTED")
    assert res["applied"]
    worker.close(); gate.close()
