"""W-56 — `resources/list` is not implemented: the conductor's actual first call must succeed.

R-09b, CONFIRMED live by the target-host review: the conductor's first substantive call into this
server was `resources/list`, answered `{"error":{"code":-32601,"message":"method not found:
resources/list"}}`. Any F2 unit that stopped at "make it start" left that failure in place.

The repair answers `resources/list` with an HONEST EMPTY INVENTORY. The canonical Phase 3A
resource registry (conductor-file / artifact / task / evidence resources, canonical Build Handoff
§9.5) is NOT implemented on this tree — `mcp_server/resources/` holds a scaffold `.gitkeep` — so
an empty list is the truthful state, and a subsystem build is not a surgical unit's work. The
capability declaration is deliberately unchanged (tools only): nothing advertises a resource
surface that does not exist, and `resources/read` / `resources/templates/list` remain method-not-
found — nothing is observed calling them, and there is nothing to read or template.

Like `tools/list`, the answer needs no app-control capability: it is answered even when the
gateway is unreachable, preserving W-55's property that the handshake does not depend on it.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


class _App:
    def identity_details(self) -> dict[str, str]:
        return {"node_id": "worker-1", "role": "worker", "project_id": "proj"}

    def call(self, operation: str, arguments: dict[str, Any] | None = None) -> Any:
        return {"ok": True}


def _runtime(tmp_path: Path):
    from control_plane.policy import SovereignPolicy
    from mcp_server.sovereign_tools import SovereignToolRuntime

    return SovereignToolRuntime(_App(), tmp_path, policy=SovereignPolicy())


# ---- negative: the defect -----------------------------------------------------------------------

def test_resources_list_is_answered_with_an_honest_empty_inventory(tmp_path: Path) -> None:
    """NEGATIVE. Pre-repair this answered -32601 "method not found" — the exact R-09b shape the
    live conductor hit. Repaired, the call succeeds and tells the truth: no resources exist."""
    from mcp_server.sovereign_tools import handle_request

    runtime = _runtime(tmp_path)
    try:
        response = handle_request(runtime, {"jsonrpc": "2.0", "id": 7, "method": "resources/list",
                                            "params": {}})
    finally:
        runtime.close()
    assert response is not None
    assert "error" not in response, (
        f"resources/list is still refused: {response['error']} — the conductor's actual first "
        f"call cannot succeed")
    assert response["result"] == {"resources": []}, (
        f"the inventory must be the honest empty list, not {response['result']!r}")


def test_resources_list_succeeds_over_stdio_without_a_gateway(tmp_path: Path) -> None:
    """NEGATIVE, process leg. The conductor scenario end to end: initialize, then resources/list,
    with NO gateway reachable. Pre-repair the second frame came back as -32601; repaired, both
    frames are answered and the process exits cleanly. The empty inventory needs no capability,
    so a dead gateway must not withhold it (W-55's property, preserved)."""
    import os
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    frames = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                               "clientInfo": {"name": "w56-test", "version": "1"}}}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {}}),
    ]) + "\n"
    env = {**os.environ, "SOVEREIGN_STORE_ROOT": str(tmp_path),
           "SOVEREIGN_CONTROL_PORT": str(port), "SOVEREIGN_CONTROL_TOKEN": "t",
           "PYTHONPATH": str(ROOT)}
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "mcp_server.sovereign_tools"],
        input=frames, capture_output=True, text=True, timeout=120, cwd=str(ROOT), env=env)
    replies = {r["id"]: r for r in (json.loads(line) for line in proc.stdout.splitlines())
               if r.get("id") is not None}
    assert 2 in replies, (
        f"resources/list was never answered (exit {proc.returncode}); stderr={proc.stderr[:300]}")
    assert "error" not in replies[2], (
        f"resources/list is still refused over stdio: {replies[2]['error']}")
    assert replies[2]["result"] == {"resources": []}
    assert proc.returncode == 0, proc.stderr[:300]


# ---- positive: what must NOT change ---------------------------------------------------------------

def test_the_declared_capabilities_still_advertise_tools_only(tmp_path: Path) -> None:
    """POSITIVE, declared bound. The repair answers a probe; it must not ADVERTISE a resource
    surface that does not exist. The capabilities block stays exactly the tools declaration, so a
    future registry has to declare itself honestly rather than inherit an advertisement."""
    from mcp_server.sovereign_tools import handle_request

    runtime = _runtime(tmp_path)
    try:
        response = handle_request(runtime, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                            "params": {}})
    finally:
        runtime.close()
    assert response is not None and "result" in response
    assert response["result"]["capabilities"] == {"tools": {"listChanged": False}}, (
        f"capabilities drifted: {response['result']['capabilities']!r}")


def test_unimplemented_resource_methods_still_say_so(tmp_path: Path) -> None:
    """POSITIVE, declared bound. `resources/read` and `resources/templates/list` have no honest
    answer but method-not-found: there is nothing to read and no template exists. Answering them
    with an invented success would be the same class of defect this unit removes."""
    from mcp_server.sovereign_tools import handle_request

    runtime = _runtime(tmp_path)
    try:
        for method in ("resources/read", "resources/templates/list"):
            response = handle_request(runtime, {"jsonrpc": "2.0", "id": 9, "method": method,
                                                "params": {}})
            assert response is not None
            assert response["error"]["code"] == -32601, (
                f"{method} must remain method-not-found until a registry exists: {response}")
    finally:
        runtime.close()


def test_tools_list_is_unaffected(tmp_path: Path) -> None:
    """POSITIVE control: the neighbour surface keeps its exact shape."""
    from mcp_server.sovereign_tools import TOOLS, handle_request

    runtime = _runtime(tmp_path)
    try:
        response = handle_request(runtime, {"jsonrpc": "2.0", "id": 3, "method": "tools/list",
                                            "params": {}})
    finally:
        runtime.close()
    assert response is not None
    assert response["result"]["tools"] == TOOLS
