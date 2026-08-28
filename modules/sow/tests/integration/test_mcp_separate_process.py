"""Phase 3A: the MCP server runs as a genuinely separate OS process over loopback, and this
process writes AND reads through the socket — proving the 'separate loopback server'
criterion end-to-end, not just an in-process object."""
from __future__ import annotations

import base64
import os
import subprocess
import sys
import time
from pathlib import Path

from mcp_server.protocol import McpClient
from persistence import SovereignStore

ROOT = Path(__file__).resolve().parents[2]


def _b64(s: bytes) -> str:
    return base64.b64encode(s).decode("ascii")


def _read_prefixed(proc: subprocess.Popen, prefix: str, timeout_s: float = 15.0) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if line.startswith(prefix):
            return line.strip().split("=", 1)[1]
        if not line and proc.poll() is not None:
            break
    raise AssertionError(f"server process never emitted {prefix}")


def test_separate_process_authenticated_write_and_read(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    env = {**os.environ, "SOVEREIGN_BOOTSTRAP_ROLE": "operator",
           "SOVEREIGN_BOOTSTRAP_NODE": "boot", "SOVEREIGN_BOOTSTRAP_PROJECT": "proj"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "mcp_server.run_server", str(store_dir), "0"],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
    )
    try:
        port = int(_read_prefixed(proc, "MCP_PORT="))
        token = _read_prefixed(proc, "BOOTSTRAP_TOKEN=")

        client = McpClient("127.0.0.1", port, token)
        client.connect()
        prov = {"author_node": "boot", "task_id": None, "ts": "2026-07-17T00:00:00+00:00",
                "directive_version": "v2.4", "confidence": "high"}
        pub = client.call("publish", kind="finding", content_b64=_b64(b"cross-process fact"), provenance=prov)
        client.call("transition", entry_id=pub["entry_id"], requested_status="UNDER_REVIEW")
        client.call("transition", entry_id=pub["entry_id"], requested_status="ACCEPTED")
        accepted = client.call("read_status", status="ACCEPTED")
        assert len(accepted) == 1 and accepted[0]["entry_id"] == pub["entry_id"]
        health = client.call("health")
        assert health["ok"]
        client.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    # the store the separate process wrote survives it and is consistent
    reopened = SovereignStore(store_dir / "sovereign.db")
    assert reopened.verify()["ok"]
    assert len(reopened.list_by_status("proj", "ACCEPTED")) == 1
    reopened.close()
