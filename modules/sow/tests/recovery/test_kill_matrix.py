"""Phase 13 kill-matrix recovery: inject faults at each layer and confirm the system recovers
without loss/corruption — the recovery leg of the evaluation (Plan §7-P13, §12.4)."""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

from control_plane.nodes import (
    AppendOnlyEventLog,
    HeartbeatPolicy,
    NodeProcessManager,
    NodeRegistry,
    NodeState,
    RestartPolicy,
    verify_file,
)
from control_plane.recovery import ConductorState, SuccessionManager
from mcp_server.protocol import McpClient, McpDisconnected
from mcp_server.server import MCPServer

SIM = str(Path(__file__).resolve().parents[1] / "fixtures" / "sim_node.py")


def _b64(b): return base64.b64encode(b).decode("ascii")


def _prov(a): return {"author_node": a, "task_id": None, "ts": "2026-07-17T00:00:00+00:00",
                      "directive_version": "v2.4", "confidence": "high"}


def test_kill_node_recovers_via_restart(tmp_path) -> None:
    """Node layer: a crashed node is detected and restarted; the event log stays intact."""
    import time
    log = AppendOnlyEventLog(tmp_path / "events.jsonl")
    mgr = NodeProcessManager(NodeRegistry(log), log,
                             HeartbeatPolicy(interval_s=0.25, miss_factor=4.0),
                             RestartPolicy(max_restarts=2, backoff_s=0.1))
    try:
        mgr.spawn("n1", [sys.executable, SIM, "--hb-ms", "100", "--crash-after-s", "1"])
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            mgr.poll()
            if mgr.registry.get("n1").incarnation == 2:
                break
            time.sleep(0.1)
        assert mgr.registry.get("n1").incarnation == 2   # restarted as a new incarnation
        assert verify_file(tmp_path / "events.jsonl").ok  # log intact through the crash
    finally:
        assert mgr.terminate_all() == []


def test_mcp_disconnect_is_fail_closed_and_store_recovers(tmp_path) -> None:
    """MCP layer: an abrupt server loss fails closed and the on-disk store reopens intact."""
    from persistence import SovereignStore
    store_dir = tmp_path / "store"
    srv = MCPServer(store_dir); srv.start()
    op = McpClient("127.0.0.1", srv.port, srv.credentials.issue("op", "operator", "proj")); op.connect()
    op.call("publish", kind="finding", tier="shared_project", content_b64=_b64(b"before crash"),
            provenance=_prov("op"), status="ACCEPTED")
    port = srv.port
    srv.stop()
    stale = McpClient("127.0.0.1", port, "tok")
    with pytest.raises(McpDisconnected):
        stale.call("read_status", status="ACCEPTED")
    reopened = SovereignStore(store_dir / "sovereign.db")
    assert reopened.verify()["ok"] and len(reopened.list_by_status("proj", "ACCEPTED")) == 1
    reopened.close()


def test_conductor_loss_recovers_with_zero_project_loss(tmp_path) -> None:
    """Conductor layer: kill the conductor, a successor reconstructs from MCP with no loss."""
    srv = MCPServer(tmp_path / "store"); srv.start()
    try:
        a = McpClient("127.0.0.1", srv.port, srv.credentials.issue("cond-A", "conductor", "proj")); a.connect()
        state = ConductorState(tasks=[{"task_id": "t-1", "state": "DONE"}],
                               nodes=[{"node_id": "w", "state": "READY"}],
                               directive_version="v2.4",
                               current_conductor={"node_id": "cond-A", "model": "m", "reason": "operator_selected",
                                                  "since": "2026-07-17T00:00:00+00:00"})
        SuccessionManager(a).serialize(state)
        a.close()  # conductor killed
        b = McpClient("127.0.0.1", srv.port, srv.credentials.issue("cond-B", "conductor", "proj")); b.connect()
        recon, report = SuccessionManager(b).reconstruct(
            expected_directive_version="v2.4", new_selection={"node_id": "cond-B", "model": "m2"})
        assert report.ok and recon.tasks == state.tasks
        b.close()
    finally:
        srv.stop()
