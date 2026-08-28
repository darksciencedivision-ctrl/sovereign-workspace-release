"""W-55 — MCP startup diagnosability: the capability check may fail, but the server may not vanish.

Pre-repair, `mcp_server/sovereign_tools.py` resolved the app-control capability BEFORE reading a
single frame of stdin and exited 2 on any failure, to a stderr the launching CLI discards. The
operator-visible symptom was "MCP server 'sovereign' was not ready for this step" with no
diagnosis anywhere. The repair answers the first frame BEFORE the capability round-trip, records
every failed resolution under the store root, and degrades into a structured per-call error
instead of a dead process.

The EAGER round-trip itself is kept — moved after the first answered frame — because the worker
admission chain reads this process's first gateway arrival as evidence of life: the MCP_CONNECTING
loop in `apps/desktop/control/worker-readiness.js` stalls a worker whose session never establishes,
and `apps/desktop/control/assignment-gate.js` refuses to assign to one. The defect was the FATAL
failure mode, not the round-trip.

WHAT THIS DOES NOT CLAIM: F2 (the live Codex conductor never initialised sovereign) is NOT closed
here. The encoding candidate was eliminated by W-04 and re-measured by F-6; the surviving candidate
is N-02 (no `cwd` pinned in `.codex/config.toml`), which only a live Codex bring-up settles.
"""
from __future__ import annotations

import http.server
import json
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

_INITIALIZE = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "w55-test", "version": "1"}}})
_STATUS_CALL = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                           "params": {"name": "get_worker_status", "arguments": {}}})
_TOOLS_LIST = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}})


def _closed_port() -> int:
    """A port nothing is listening on: bind one, read the number, release it."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _spawn(tmp_path: Path, port: int, frames: str) -> subprocess.CompletedProcess:
    import os

    env = {**os.environ, "SOVEREIGN_STORE_ROOT": str(tmp_path),
           "SOVEREIGN_CONTROL_PORT": str(port), "SOVEREIGN_CONTROL_TOKEN": "t",
           "PYTHONPATH": str(ROOT)}
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "mcp_server.sovereign_tools"],
        input=frames, capture_output=True, text=True, timeout=120, cwd=str(ROOT), env=env)


def _replies(proc: subprocess.CompletedProcess) -> dict[Any, dict[str, Any]]:
    return {r["id"]: r for r in (json.loads(line) for line in proc.stdout.splitlines())
            if r.get("id") is not None}


class _RecordingGateway:
    """The smallest app-control gateway: answers every operation and records arrivals."""

    def __init__(self, port: int = 0) -> None:
        self.requests: list[dict[str, Any]] = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:                       # noqa: N802 - stdlib naming
                length = int(self.headers.get("Content-Length") or 0)
                outer.requests.append(json.loads(self.rfile.read(length).decode("utf-8")))
                payload = json.dumps({"ok": True, "result": {
                    "node_id": "worker-1", "role": "worker", "project_id": "proj"}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args: Any) -> None:      # keep pytest output clean
                return

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


# ---- negative: the defect, driven through the REAL process --------------------------------

def test_initialize_is_answered_when_the_capability_is_unreachable(tmp_path: Path) -> None:
    """NEGATIVE. The gateway is unreachable, so the capability cannot resolve. Pre-repair the
    process exited 2 BEFORE reading stdin, so the client saw a dead process and the handshake
    never started. Repaired, `initialize` is answered first and the failure degrades."""
    proc = _spawn(tmp_path, _closed_port(), _INITIALIZE + "\n")
    replies = _replies(proc)
    assert 1 in replies, (
        f"the server answered nothing and exited {proc.returncode}: a capability failure must "
        f"not silence the handshake; stderr={proc.stderr[:300]}")
    assert proc.returncode == 0, (
        f"the server died (exit {proc.returncode}) instead of degrading; stderr={proc.stderr[:300]}")
    assert replies[1]["result"]["serverInfo"]["name"] == "sovereign"


def test_a_capability_failure_is_structured_for_the_client_and_logged_durably(tmp_path: Path) -> None:
    """NEGATIVE. The first tool call must come back as a structured, readable error — and the
    fault must be recorded somewhere that survives a CLI that discards stderr. Pre-repair the
    process was already dead before either frame was read."""
    proc = _spawn(tmp_path, _closed_port(), _INITIALIZE + "\n" + _STATUS_CALL + "\n")
    replies = _replies(proc)
    assert 2 in replies, (
        f"the tool call was never answered (exit {proc.returncode}); stderr={proc.stderr[:300]}")
    payload = replies[2]["result"]
    assert payload["isError"] is True, payload
    text = payload["content"][0]["text"]
    assert "capability" in text and "unavailable" in text, text
    assert "mcp_startup_faults.log" in text, (
        "the diagnosis must point at the durable record, not only describe itself")
    log_path = tmp_path / "mcp_startup_faults.log"
    assert log_path.exists(), "the fault was not recorded anywhere durable"
    entry = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert entry.get("fault"), entry
    assert proc.returncode == 0, f"the server must stay alive for later calls; stderr={proc.stderr[:300]}"


# ---- positive: the repaired behaviour, and what must NOT change ---------------------------

def test_a_healthy_gateway_still_round_trips_the_first_tool_call(tmp_path: Path) -> None:
    """POSITIVE control. A healthy gateway must behave exactly as before: the tool call succeeds
    and no fault is logged."""
    gateway = _RecordingGateway()
    try:
        proc = _spawn(tmp_path, gateway.port, _INITIALIZE + "\n" + _STATUS_CALL + "\n")
    finally:
        gateway.stop()
    assert proc.returncode == 0, proc.stderr[:300]
    replies = _replies(proc)
    payload = replies[2]["result"]
    assert payload["isError"] is False, payload
    assert payload["structuredContent"]["nodes"], payload
    assert not (tmp_path / "mcp_startup_faults.log").exists(), (
        "a healthy startup must not write a fault log")
    assert gateway.requests, "the capability round-trip never reached the gateway"


def test_the_session_is_established_before_any_tool_call(tmp_path: Path) -> None:
    """POSITIVE, and the reason the eager round-trip survives: the admission chain reads a gateway
    session as evidence of life. A handshake with NO tool call must still have produced a gateway
    arrival — `worker-readiness.js` stalls a worker whose session never establishes, and
    `assignment-gate.js` refuses to assign to one."""
    gateway = _RecordingGateway()
    try:
        proc = _spawn(tmp_path, gateway.port, _INITIALIZE + "\n" + _TOOLS_LIST + "\n")
    finally:
        gateway.stop()
    assert proc.returncode == 0, proc.stderr[:300]
    assert gateway.requests, (
        "no gateway arrival without a tool call: the session the admission chain reads is no "
        "longer established at startup")


def test_a_later_tool_call_recovers_when_the_gateway_appears(tmp_path: Path) -> None:
    """POSITIVE. A gateway that comes up AFTER the server started is recovered by the next call,
    not by a restart: the resolution is retried, never memoized as a permanent failure."""
    import pytest

    from mcp_server.sovereign_tools import ToolError, _DeferredRuntime

    port = _closed_port()
    holder = _DeferredRuntime(str(port), "t", tmp_path)
    with pytest.raises(ToolError):
        holder.call("get_worker_status", {})
    assert (tmp_path / "mcp_startup_faults.log").exists(), "the failed attempt was not logged"
    gateway = _RecordingGateway(port)
    try:
        result = holder.call("get_worker_status", {})
    finally:
        gateway.stop()
        holder.close()
    assert result["tasks"] == []
    assert result["nodes"], result
    assert gateway.requests, "the recovery attempt never reached the gateway"


def test_the_fault_log_never_grows_past_its_cap(tmp_path: Path) -> None:
    """POSITIVE. A gateway that stays down while calls keep coming must not grow the log forever
    (the W-35/W-63 class). At the cap, nothing is appended."""
    import pytest

    from mcp_server.sovereign_tools import (
        STARTUP_FAULT_LOG_CAP_BYTES,
        STARTUP_FAULT_LOG_NAME,
        ToolError,
        _DeferredRuntime,
    )

    log_path = tmp_path / STARTUP_FAULT_LOG_NAME
    log_path.write_bytes(b"x" * STARTUP_FAULT_LOG_CAP_BYTES)
    holder = _DeferredRuntime(str(_closed_port()), "t", tmp_path)
    with pytest.raises(ToolError):
        holder.call("get_worker_status", {})
    holder.close()
    assert log_path.stat().st_size == STARTUP_FAULT_LOG_CAP_BYTES, (
        "the fault log grew past its cap")
