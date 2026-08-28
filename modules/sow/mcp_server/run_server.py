"""Entrypoint so the MCP server runs as a genuinely separate OS process (Plan Phase 3A:
"separate loopback server"). Prints the bound port as the first stdout line so a parent can
discover it. Offline-honest: binds 127.0.0.1 only (network=none compatible).

    py -3.12 -m mcp_server.run_server <store_dir> [port]

Bootstrap: if SOVEREIGN_BOOTSTRAP_ROLE / _NODE / _PROJECT are set, a single credential is
issued at startup and printed as BOOTSTRAP_TOKEN=<tok>. This is the operator/Sovereign
bootstrap path (the first identity has to come from somewhere); ordinary node credentials
are issued by Sovereign at spawn, never self-served by nodes.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from mcp_server.server import MCPServer


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: run_server <store_dir> [port]", file=sys.stderr)
        return 2
    store_dir = Path(argv[0])
    port = int(argv[1]) if len(argv) > 1 else 0
    server = MCPServer(store_dir)
    bound = server.start(port=port)
    print(f"MCP_PORT={bound}", flush=True)
    role = os.environ.get("SOVEREIGN_BOOTSTRAP_ROLE")
    if role:
        token = server.credentials.issue(
            os.environ.get("SOVEREIGN_BOOTSTRAP_NODE", "bootstrap"),
            role, os.environ.get("SOVEREIGN_BOOTSTRAP_PROJECT", "proj"),
        )
        print(f"BOOTSTRAP_TOKEN={token}", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
