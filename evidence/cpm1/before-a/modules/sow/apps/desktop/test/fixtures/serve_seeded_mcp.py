"""TEST FIXTURE (not product code): a real, seeded MCP server bridged by a real IPC gateway.

Stands up the genuine governed read chain the desktop inspector reads over, as separate in-process
services on loopback, so the JS inspector source can be proven against REAL MCP state (not a mock):

    JS IpcClient  --ws-->  IpcGateway (McpControlSurface, read-only)  --ws-->  MCPServer (+store)

It seeds a handful of deterministic shared-memory entries that exercise every inspector dimension:
  * an attributed work artifact (kind=finding, task t-1, ACCEPTED)      -> "artifacts published"
  * a gate DECISION (kind=decision, task t-1, provenance.gate_result)   -> derived "gate chain"
  * an UNATTRIBUTED entry (task_id=None, CANDIDATE)                      -> unattributed bucket (inv 27)

then prints IPC_PORT / IPC_TOKEN / IPC_KEY (exactly like control_plane.ipc.run_gateway) and blocks.
The parent JS test discovers the creds from stdout, connects, reads, asserts, and kills the process.

Offline-honest: everything binds 127.0.0.1. Read-only surface: the gateway exposes only
{health, read_status}; nothing here can write over IPC (so no U25 dependency).
"""
from __future__ import annotations

import base64
import sys
import tempfile
import time
from pathlib import Path

# Run as a plain script (JS spawns `py -3.12 <this file>`): sys.path[0] is this dir, not the repo
# root, so make the repo importable. Repo root = five parents up (fixtures/test/desktop/apps/root).
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from control_plane.ipc.gateway import IpcCredentialStore, IpcGateway, McpControlSurface  # noqa: E402
from mcp_server.protocol import McpClient  # noqa: E402
from mcp_server.server import MCPServer  # noqa: E402

PROJECT = "proj"


def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _prov(author: str, task_id: str | None, **extra: object) -> dict[str, object]:
    return {
        "author_node": author, "task_id": task_id, "ts": "2026-07-18T00:00:00Z",
        "directive_version": "v2.4", "confidence": "high", **extra,
    }


def main() -> int:
    store_dir = tempfile.mkdtemp(prefix="inspector-fixture-")
    server = MCPServer(store_dir)
    mcp_port = server.start()

    # Seed via normal publisher clients (exercises the real publish path + policy). Policy pins
    # provenance.author_node to the publishing node and gates ACCEPTED to gate/operator roles, so
    # each seed entry is published by an authentic node of the right role — as in the real system.
    def publisher(node_id: str, role: str) -> McpClient:
        c = McpClient("127.0.0.1", mcp_port, server.credentials.issue(node_id, role, PROJECT))
        c.connect()
        return c

    worker_a = publisher("worker-A", "worker")
    worker_a.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64("worker-A finding for t-1"),
                  provenance=_prov("worker-A", "t-1", source_artifacts=["m-objective"]), status="CANDIDATE")
    worker_a.close()

    gate = publisher("gate-1", "gate")
    gate.call("publish", kind="decision", tier="shared_project",
              content_b64=_b64("plan gate: PASS"),
              provenance=_prov("gate-1", "t-1", gate_result="ACCEPTED by gate:gate-1", evidence=["m-ev1"]),
              status="ACCEPTED")
    gate.close()

    worker_b = publisher("worker-B", "worker")
    worker_b.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64("orphan candidate, no task"),
                  provenance=_prov("worker-B", None), status="CANDIDATE")
    worker_b.close()

    # the read surface authenticates onward to MCP with its own single credential (read-only)
    surf_tok = server.credentials.issue("inspector", "operator", PROJECT)
    surface = McpControlSurface(lambda: McpClient("127.0.0.1", mcp_port, surf_tok))

    creds = IpcCredentialStore()
    gateway = IpcGateway(creds, surface)
    ipc_port = gateway.start()
    tok, key = creds.issue("shell", "operator", PROJECT)

    print(f"IPC_PORT={ipc_port}", flush=True)
    print(f"IPC_TOKEN={tok}", flush=True)
    print(f"IPC_KEY={key.hex()}", flush=True)

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        gateway.stop()
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
