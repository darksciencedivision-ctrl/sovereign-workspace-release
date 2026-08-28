"""Phase 3A spec-audit remediations — regression tests pinning each fixed defect so a
reintroduction fails the suite (F2 stale/loser reads, F3 CAS traversal, F4 cross-project
isolation, private-tier isolation, F8 health scope, F9 supersede successor)."""
from __future__ import annotations

import base64
from pathlib import Path

import pytest

from mcp_server.protocol import McpClient, McpError
from mcp_server.server import MCPServer


def _b64(s: bytes) -> str:
    return base64.b64encode(s).decode("ascii")


def _prov(author: str) -> dict:
    return {"author_node": author, "task_id": None, "ts": "2026-07-17T00:00:00+00:00",
            "directive_version": "v2.4", "confidence": "high"}


@pytest.fixture()
def server(tmp_path: Path):
    srv = MCPServer(tmp_path / "store")
    srv.start()
    yield srv
    srv.stop()


def _client(server: MCPServer, node: str, role: str, project: str = "proj") -> McpClient:
    c = McpClient("127.0.0.1", server.port, server.credentials.issue(node, role, project))
    c.connect()
    return c


def test_stale_versions_do_not_surface_as_current(server: MCPServer) -> None:
    """F2: after promotion, the old CANDIDATE version is not returned by read_status.
    Uses operator (final authority, exempt from the inv-18 approver!=author rule)."""
    gate = _client(server, "n-g", "operator")
    pub = gate.call("publish", kind="finding", content_b64=_b64(b"x"), provenance=_prov("n-g"))
    gate.call("transition", entry_id=pub["entry_id"], requested_status="UNDER_REVIEW")
    gate.call("transition", entry_id=pub["entry_id"], requested_status="ACCEPTED")
    assert gate.call("read_status", status="CANDIDATE") == []       # stale @1 excluded
    assert gate.call("read_status", status="UNDER_REVIEW") == []    # stale @2 excluded
    assert len(gate.call("read_status", status="ACCEPTED")) == 1    # only the head


def test_race_loser_fork_not_returned_as_accepted(server: MCPServer) -> None:
    """F2: the CAS loser's fork carries status ACCEPTED but is not the head -> excluded."""
    import threading
    g = _client(server, "n-g", "gate")
    pub = g.call("publish", kind="finding", content_b64=_b64(b"seed"), provenance=_prov("n-g"))
    eid = pub["entry_id"]
    g.call("transition", entry_id=eid, requested_status="UNDER_REVIEW")
    barrier = threading.Barrier(2)
    out: list = []

    def race(n: str) -> None:
        c = _client(server, n, "gate")
        barrier.wait()
        out.append(c.call("transition", entry_id=eid, requested_status="ACCEPTED"))
        c.close()

    ts = [threading.Thread(target=race, args=(f"n{i}",)) for i in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]
    accepted = g.call("read_status", status="ACCEPTED")
    assert len(accepted) == 1, "only the winning head is ACCEPTED, not the loser fork"


def test_cas_path_traversal_refused(server: MCPServer) -> None:
    """F3: a crafted 64-char ref with traversal must not read outside the store."""
    op = _client(server, "n-o", "operator")
    evil = "sha256:" + "../../../../etc/passwd".ljust(64, "a")[:64]
    with pytest.raises(McpError):  # rejected as an invalid ref / not in project, never a file read
        op.call("get_artifact", artifact_id=evil)


def test_cross_project_artifact_isolation(tmp_path: Path) -> None:
    """F4: knowing a content hash does not grant another project's artifact."""
    srv = MCPServer(tmp_path / "store")
    srv.start()
    try:
        a = _client(srv, "a", "worker", project="projA")
        b = _client(srv, "b", "worker", project="projB")
        art = a.call("put_artifact", content_b64=_b64(b"projA secret"), media_type="text/plain")
        aid = art["artifact_id"]
        assert a.call("get_artifact", artifact_id=aid)["meta"]["created_by_node"] == "a"
        with pytest.raises(McpError, match="no such artifact"):
            b.call("get_artifact", artifact_id=aid)  # same hash, different project -> denied
    finally:
        srv.stop()


def test_private_tier_not_leaked_via_shared_read(server: MCPServer) -> None:
    """Invariant 9: a private_node entry is never returned by another node's shared read."""
    a = _client(server, "a", "worker")
    a.call("publish", kind="finding", tier="private_node", content_b64=_b64(b"a private note"),
           provenance=_prov("a"))
    b = _client(server, "b", "worker")
    assert b.call("read_status", status="CANDIDATE") == []  # shared read returns no private entries


def test_private_tier_not_readable_by_other_node_via_get_content(server: MCPServer) -> None:
    """F1: get_content must enforce tier ownership — a private_node entry is readable only
    by its author, never by another same-project node."""
    a = _client(server, "node-a", "worker")
    pub = a.call("publish", kind="finding", tier="private_node", content_b64=_b64(b"a's private bytes"),
                 provenance=_prov("node-a"))
    eid = pub["entry_id"]
    assert base64.b64decode(a.call("get_content", entry_id=eid)["content_b64"]) == b"a's private bytes"
    b = _client(server, "node-b", "worker")
    with pytest.raises(McpError, match="readable only by its author"):
        b.call("get_content", entry_id=eid)
    with pytest.raises(McpError, match="readable only by its author"):
        b.call("get_head", entry_id=eid)


def test_health_is_operator_conductor_only(server: MCPServer) -> None:
    """F8: store health is not exposed to worker/gate nodes."""
    worker = _client(server, "n-w", "worker")
    with pytest.raises(McpError, match="operator/conductor-only"):
        worker.call("health")
    op = _client(server, "n-o", "operator")
    assert op.call("health")["ok"] is True


def test_supersede_requires_real_successor(server: MCPServer) -> None:
    """F9: SUPERSEDED must reference a real version, not any truthy string."""
    gate = _client(server, "n-g", "operator")  # operator: exempt from inv-18 approver!=author
    pub = gate.call("publish", kind="finding", content_b64=_b64(b"y"), provenance=_prov("n-g"))
    gate.call("transition", entry_id=pub["entry_id"], requested_status="UNDER_REVIEW")
    gate.call("transition", entry_id=pub["entry_id"], requested_status="ACCEPTED")
    with pytest.raises(McpError, match="does not reference a real version"):
        gate.call("transition", entry_id=pub["entry_id"], requested_status="SUPERSEDED",
                  successor_ref="m-bogus@1")
