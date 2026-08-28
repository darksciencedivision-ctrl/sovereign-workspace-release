"""Entrypoint so the IPC gateway runs as a genuinely separate OS process (D-IPC-01,
mirrors mcp_server/run_server.py). Prints the bound port first so a parent can discover it.
Offline-honest: binds 127.0.0.1 only.

    py -3.12 -m control_plane.ipc.run_gateway [port] [--mcp-host H --mcp-port P --mcp-token T]

Surface selection:
  - no --mcp-port  -> EchoControlSurface (diagnostic transport proof, no control plane);
  - --mcp-port set -> McpControlSurface bridging to a running MCP server.

Bootstrap: if SOVEREIGN_IPC_NODE / _ROLE / _PROJECT are set, one credential is issued at
startup and printed as IPC_TOKEN=<tok> and IPC_KEY=<hexkey> so a shell can connect. Ordinary
node credentials are issued by Sovereign at spawn, never self-served by nodes.
"""
from __future__ import annotations

import os
import sys
import time

from control_plane.ipc.gateway import EchoControlSurface, IpcCredentialStore, IpcGateway, McpControlSurface


def _parse(argv: list[str]) -> tuple[int, dict[str, str]]:
    port = 0
    opts: dict[str, str] = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            opts[a[2:]] = argv[i + 1]
            i += 2
        else:
            port = int(a)
            i += 1
    return port, opts


def main(argv: list[str]) -> int:
    port, opts = _parse(argv)
    credentials = IpcCredentialStore()
    if "mcp-port" in opts:
        from mcp_server.protocol import McpClient

        host = opts.get("mcp-host", "127.0.0.1")
        mcp_port = int(opts["mcp-port"])
        token = opts.get("mcp-token", "")
        surface = McpControlSurface(lambda: McpClient(host, mcp_port, token))
    else:
        surface = EchoControlSurface()

    gateway = IpcGateway(credentials, surface)
    bound = gateway.start(port=port)
    print(f"IPC_PORT={bound}", flush=True)

    node = os.environ.get("SOVEREIGN_IPC_NODE")
    if node:
        role = os.environ.get("SOVEREIGN_IPC_ROLE", "operator")
        project = os.environ.get("SOVEREIGN_IPC_PROJECT", "proj")
        # Recovery model (directive §9 track 14A): if a fixed credential is supplied AND the
        # recovery-model opt-in is explicitly set, install it instead of minting a fresh one, so a
        # RESTARTED gateway re-issues the SAME per-node credential a reconnecting shell already
        # holds — a persistent credential store would do the same. Loopback-only, still fully
        # authenticated + HMAC-verified per envelope. Fail-closed: the fixed-credential path can
        # NEVER activate silently in a real deployment — it requires IPC_ALLOW_FIXED_CRED=1, so
        # absent the explicit opt-in the gateway always mints a fresh random credential.
        fixed_tok = os.environ.get("IPC_FIXED_TOKEN")
        fixed_key = os.environ.get("IPC_FIXED_KEY")
        allow_fixed = os.environ.get("IPC_ALLOW_FIXED_CRED") == "1"
        if allow_fixed and fixed_tok and fixed_key:
            tok, key = fixed_tok, bytes.fromhex(fixed_key)
            credentials.install(tok, key, node, role, project)
        else:
            tok, key = credentials.issue(node, role, project)
        print(f"IPC_TOKEN={tok}", flush=True)
        print(f"IPC_KEY={key.hex()}", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        gateway.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
