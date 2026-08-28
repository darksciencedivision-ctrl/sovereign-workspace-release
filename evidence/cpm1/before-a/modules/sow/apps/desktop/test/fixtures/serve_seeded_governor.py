"""TEST FIXTURE (not product code): a real IPC gateway over a real, seeded subscription governor.

Stands up the genuine governed read chain the desktop status bar reads over, as separate services
on loopback, so the JS status-bar source can be proven against a REAL SubscriptionGovernor (not a
mock):

    JS IpcClient  --ws-->  IpcGateway (SubscriptionStatusControlSurface, read-only)  --> governor.status()

It seeds the real node_runtime governor exactly as the supervised spawn path would:
  * an Anthropic (claude_code) subscription, allowance 2, with ONE terminal acquired  -> 1/2 active
  * an OpenAI (openai_codex_cli) subscription, allowance 2, with NO terminal acquired  -> 0/2 idle

then prints IPC_PORT / IPC_TOKEN / IPC_KEY (exactly like control_plane.ipc.run_gateway) and blocks.
The parent JS test discovers the creds from stdout, connects, reads subscription_status, asserts the
folded n/2 rows, and kills the process.

Offline-honest: everything binds 127.0.0.1. Read-only surface: the gateway exposes only
{health, subscription_status}; nothing here can register/acquire/release or raise an allowance.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Run as a plain script (JS spawns `py -3.12 <this file>`): make the repo importable. Repo root =
# five parents up (fixtures/test/desktop/apps/root), matching serve_seeded_mcp.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from control_plane.ipc.gateway import (  # noqa: E402
    IpcCredentialStore,
    IpcGateway,
    SubscriptionStatusControlSurface,
)
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor  # noqa: E402

PROJECT = "proj"


def main() -> int:
    # The REAL governor, seeded via its real API (register at the OP-6 allowance, then acquire) —
    # the exact operations the supervised frontier-spawn path performs.
    governor = SubscriptionGovernor()
    governor.register_subscription("sub-anthropic", provider="claude_code", allowance=2)
    governor.acquire("sub-anthropic", node_id="frontier-A")  # one live terminal -> 1/2
    governor.register_subscription("sub-openai", provider="openai_codex_cli", allowance=2)
    # no acquire on the OpenAI subscription -> 0/2 idle

    surface = SubscriptionStatusControlSurface(governor.status)

    creds = IpcCredentialStore()
    gateway = IpcGateway(creds, surface)
    ipc_port = gateway.start()
    # role "shell", NOT "operator": the shell must not self-mint the highest role (invariant 1),
    # matching apps/desktop/main.js. The read-only surface is role-agnostic, so this is purely for
    # fidelity with the product credential the real shell holds.
    tok, key = creds.issue("shell", "shell", PROJECT)

    print(f"IPC_PORT={ipc_port}", flush=True)
    print(f"IPC_TOKEN={tok}", flush=True)
    print(f"IPC_KEY={key.hex()}", flush=True)

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        gateway.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
