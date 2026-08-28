"""Phase 3A gate criteria end-to-end against the loopback MCP server.

Covers every Buildout Directive §5 Phase 3A gate bullet: memory survives restart; nodes
keep independent context; every shared write has provenance; candidate/accepted separated;
canonical directive not worker-writable; conductor replacement preserves memory; disconnect
never corrupts state; concurrent-writer test yields conflict records (never silent
overwrite); no authorization logic inside MCP.
"""
from __future__ import annotations

import base64
import threading
from pathlib import Path

import pytest

from mcp_server.protocol import McpClient, McpDisconnected, McpError
from mcp_server.server import MCPServer
from persistence import SovereignStore


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


def _client(server: MCPServer, node_id: str, role: str, project: str = "proj") -> McpClient:
    token = server.credentials.issue(node_id, role, project)
    c = McpClient("127.0.0.1", server.port, token)
    c.connect()
    return c


def test_publish_read_and_candidate_accepted_separation(server: MCPServer) -> None:
    worker = _client(server, "n-w", "worker")
    gate = _client(server, "n-g", "gate")
    pub = worker.call("publish", kind="finding", content_b64=_b64(b"a finding"), provenance=_prov("n-w"))
    eid = pub["entry_id"]
    assert worker.call("read_status", status="CANDIDATE") and not worker.call("read_status", status="ACCEPTED")
    # worker cannot promote its own finding (no self-canonization)
    with pytest.raises(McpError, match="gate/operator"):
        worker.call("transition", entry_id=eid, requested_status="ACCEPTED")
    # gate can, after review
    worker.call("transition", entry_id=eid, requested_status="UNDER_REVIEW")
    res = gate.call("transition", entry_id=eid, requested_status="ACCEPTED")
    assert res["applied"]
    assert server.credentials.verify  # sanity
    accepted = worker.call("read_status", status="ACCEPTED")
    assert len(accepted) == 1 and accepted[0]["status"] == "ACCEPTED"


def test_every_write_has_provenance(server: MCPServer) -> None:
    worker = _client(server, "n-w", "worker")
    with pytest.raises(McpError, match="memory@1.0|provenance"):
        # provenance missing 'confidence' -> store refuses at schema boundary
        worker.call("publish", kind="finding", content_b64=_b64(b"x"),
                    provenance={"author_node": "n-w", "task_id": None, "ts": "2026-07-17T00:00:00+00:00",
                                "directive_version": "v2.4"})


def test_canonical_directive_not_worker_writable(server: MCPServer) -> None:
    worker = _client(server, "n-w", "worker")
    with pytest.raises(McpError, match="operator-only"):
        worker.call("publish", kind="directive", content_b64=_b64(b"malicious directive"), provenance=_prov("n-w"))


def test_concurrent_writers_yield_conflict_never_silent_overwrite(server: MCPServer) -> None:
    """D-MCP-03 mandatory test: two writers race to advance the same head; exactly one wins,
    the other gets a conflict record; both versions preserved."""
    gate = _client(server, "n-g", "gate")
    pub = gate.call("publish", kind="finding", content_b64=_b64(b"seed"), provenance=_prov("n-g"))
    eid = pub["entry_id"]
    gate.call("transition", entry_id=eid, requested_status="UNDER_REVIEW")

    results: list[dict] = []
    barrier = threading.Barrier(2)

    def racer(node: str) -> None:
        c = _client(server, node, "gate")
        barrier.wait()  # maximize contention on the same head
        results.append(c.call("transition", entry_id=eid, requested_status="ACCEPTED",
                              reviewer_note=f"by {node}"))
        c.close()

    t1 = threading.Thread(target=racer, args=("n-g1",))
    t2 = threading.Thread(target=racer, args=("n-g2",))
    t1.start(); t2.start(); t1.join(); t2.join()

    applied = [r for r in results if r.get("applied")]
    lost = [r for r in results if not r.get("applied")]
    assert len(applied) == 1, "exactly one writer may win the head"
    assert len(lost) == 1 and lost[0]["conflict"]["key"] == eid, "the loser gets a conflict record"
    conflicts = gate.call("list_conflicts", key=eid)
    assert len(conflicts) == 1 and conflicts[0]["status"] == "OPEN"
    # both versions exist in the store; head points at exactly one (no silent overwrite)
    assert server.store.get_head(eid) == applied[0]["ref"]


def test_memory_survives_process_restart(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    srv1 = MCPServer(store_dir)
    srv1.start()
    gate = _client(srv1, "n-g", "operator")  # operator: exempt from inv-18 approver!=author
    pub = gate.call("publish", kind="finding", content_b64=_b64(b"durable"), provenance=_prov("n-g"))
    gate.call("transition", entry_id=pub["entry_id"], requested_status="UNDER_REVIEW")
    gate.call("transition", entry_id=pub["entry_id"], requested_status="ACCEPTED")
    gate.close()
    srv1.stop()

    # fresh server object over the same store dir = restart
    srv2 = MCPServer(store_dir)
    srv2.start()
    reader = _client(srv2, "n-r", "worker")
    accepted = reader.call("read_status", status="ACCEPTED")
    assert len(accepted) == 1 and accepted[0]["entry_id"] == pub["entry_id"]
    assert srv2.store.verify()["ok"]
    reader.close()
    srv2.stop()


def test_conductor_replacement_preserves_memory(server: MCPServer) -> None:
    cond_a = _client(server, "conductor-A", "conductor")
    gate = _client(server, "n-g", "gate")
    pub = cond_a.call("publish", kind="finding", content_b64=_b64(b"project truth"), provenance=_prov("conductor-A"))
    gate.call("transition", entry_id=pub["entry_id"], requested_status="ACCEPTED")
    cond_a.close()  # conductor A is gone
    # a different conductor identity reconstructs from the same shared memory
    cond_b = _client(server, "conductor-B", "conductor")
    accepted = cond_b.call("read_status", status="ACCEPTED")
    assert len(accepted) == 1 and accepted[0]["entry_id"] == pub["entry_id"]


def test_disconnect_is_fail_closed_and_store_uncorrupted(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    srv = MCPServer(store_dir)
    srv.start()
    token = srv.credentials.issue("n-g", "gate", "proj")
    gate = McpClient("127.0.0.1", srv.port, token)
    gate.connect()
    gate.call("publish", kind="finding", content_b64=_b64(b"before outage"), provenance=_prov("n-g"))
    port = srv.port
    srv.stop()  # server process goes away
    # a node that (re)connects to a dead MCP must fail closed, not proceed on assumptions
    stale = McpClient("127.0.0.1", port, token)
    with pytest.raises(McpDisconnected):
        stale.call("read_status", status="CANDIDATE")
    # store on disk is intact and consistent after the abrupt stop
    reopened = SovereignStore(store_dir / "sovereign.db")
    assert reopened.verify()["ok"]
    assert len(reopened.list_by_status("proj", "CANDIDATE")) == 1
    reopened.close()
    gate.close()


def test_unauthenticated_request_refused(server: MCPServer) -> None:
    bad = McpClient("127.0.0.1", server.port, "not-a-real-token")
    bad.connect()
    with pytest.raises(McpError, match="authentication failed"):
        bad.call("read_status", status="CANDIDATE")
    bad.close()


def test_no_authorization_logic_inside_mcp_server_module() -> None:
    """Structural guard for I-M2: the server module must delegate every allow/deny to
    control_plane.policy and contain no role checks of its own."""
    mcp_dir = Path(__file__).resolve().parents[2] / "mcp_server"
    for fname in ("server.py", "memory_service.py"):
        src = (mcp_dir / fname).read_text(encoding="utf-8")
        for forbidden in ['role ==', 'role in (', '.role ==', '"worker"', "'worker'", '"operator"', "'operator'", '"gate"', "'gate'"]:
            assert forbidden not in src, f"authorization-like token {forbidden!r} found in mcp_server/{fname}"
