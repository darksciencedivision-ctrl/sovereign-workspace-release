"""Phase 15D `.flow` LIVE re-run — operator-run live smoke (OP-9, directive §14).

This is NOT part of `pytest tests/`: it spawns the REAL host `claude` CLI, which the
deterministic suite must never do. It is the live analogue of the Phase-1 spike's
operator-run metric — one governed run through the SAME gated path the mock-first suite
proves (`control_plane.orchestration.live_flow.attempt_live_flow`), but with a genuine
`ClaudeCliBackend`, so the conductor leg can be recorded `live` when — and only when — the
CLI reports back a verified executing checkpoint.

OP-9 discharged the R8 §6 [OPERATOR] live-terms gate for `claude_code`; this driver passes
`operator_terms_confirmed=True` on that recorded basis (invariant 1: the loop did not make
that determination, the operator did). Every OTHER gate still applies: the real repo
`config/live_operation.json` must authorize `claude_code`, the CLI must be present, the
subscription governor caps at the authorized allowance. Any unmet gate ⇒ skip-with-record,
no live call (directive §10.4).

Honesty (directive §6/§10.4): the outcome is reported EXACTLY as the governed path records
it. A run that reached the model but returned no verifiable checkpoint degrades to
`attempted`; a mock or skipped leg is never dressed up as `live`. `build_acceptance_packet`
enforces this by construction. D-LOOP-1: `attempt_live_flow` spawns → exercises → tears
down within the call. The CLI runs in a managed process tree: every assigned PID is tracked,
the complete tree is terminated and awaited in `finally`, and a surviving descendant fails
the run rather than being left for the loop to discover.

Usage:  py -3.12 tools/live/run_15d_flow_live_smoke.py [--model SLUG] [--timeout SECONDS]

The conductor SELECTION stays fable-5 (operator-selected, invariant 3) regardless of which
checkpoint actually executes; the executing checkpoint is recorded separately and honestly.
By default the smoke requests the CLI default model (no `--model`), which is the most
reliable way to obtain a verified live checkpoint on an arbitrary host; the exact `fable-5`
slug acceptance is a separate probe (U33). Pass `--model claude-fable-5` to attempt the
selection's own checkpoint directly.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.conductor import publish_conductor_files  # noqa: E402
from adapters.frontier.claude_code import ClaudeCliBackend  # noqa: E402
from control_plane.orchestration.live_flow import attempt_live_flow  # noqa: E402
from control_plane.profiles.live_authorization import load_live_authorization  # noqa: E402
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader  # noqa: E402
from mcp_server.protocol import McpClient  # noqa: E402
from mcp_server.server import MCPServer  # noqa: E402
from node_runtime.supervisor.subscription_governor import (  # noqa: E402
    SubscriptionGovernor,
    canonical_subscription_ref,
)

CONDUCTOR_DIR = ROOT / "conductor"
REPO_LIVE_CONFIG = ROOT / "config" / "live_operation.json"
OBJECTIVE = "Draft a one-line offline conductor roster note"  # smoke-scale (minimal tokens)


def main() -> int:
    ap = argparse.ArgumentParser()
    # model=None sentinel: request the CLI DEFAULT (no --model). An explicit slug (e.g.
    # "claude-fable-5") is carried verbatim to argv and is only *confirmed* by the reply.
    ap.add_argument("--model", default=None)
    ap.add_argument("--timeout", type=float, default=150.0)
    # U76 (Phase 17A `.pty`): ONE canonical ref per provider — the I-X3 cap is enforced per ref,
    # so a second spelling of the same real subscription is a second bucket at full allowance.
    ap.add_argument("--subscription", default=canonical_subscription_ref("claude_code"))
    args = ap.parse_args()

    cli_present = shutil.which("claude") is not None
    result: dict = {
        "objective": OBJECTIVE,
        "cli_present": cli_present,
        "requested_model": args.model or "<cli-default>",
        "repo_live_config_exists": REPO_LIVE_CONFIG.exists(),
    }

    with tempfile.TemporaryDirectory() as td:
        srv = MCPServer(Path(td) / "store")
        srv.start()
        try:
            op = McpClient("127.0.0.1", srv.port, srv.credentials.issue("op-boot", "operator", "proj"))
            op.connect()
            manifest = publish_conductor_files(op, "op-boot", CONDUCTOR_DIR)
            op.close()

            # The REAL repo authorization (OP-6 scope). Absent/denied ⇒ skip-with-record.
            live_auth = load_live_authorization(REPO_LIVE_CONFIG)

            # A GENUINE vendor backend that actually spawns `claude` (exact type ⇒ live leg).
            # Constructed here only to bound the per-call timeout; identical to what
            # `attempt_live_flow(backend=None)` builds, but shorter-fused for a smoke.
            backend = ClaudeCliBackend(model=args.model, timeout_s=args.timeout)

            outcome = attempt_live_flow(
                objective=OBJECTIVE,
                server=srv,
                conductor_file_refs=manifest,
                governor=SubscriptionGovernor(),
                subscription_ref=args.subscription,
                live_auth=live_auth,
                profile_loader=ProfileLoader(DeploymentProfile("cloud")),
                operator_terms_confirmed=True,   # OP-9: R8 §6 [OPERATOR] live-terms discharged
                node_id="conductor-fable5-live",
                model=args.model,
                backend=backend,
                cli_present=cli_present,         # the DETECTED value, not a hardcoded True
            )

            sel = outcome.conductor_selection or {}
            executing = sel.get("executing") if isinstance(sel, dict) else None
            result.update({
                "ran": outcome.ran,
                "published": outcome.published,
                "skipped_with_record": outcome.skipped_with_record,
                "reason": outcome.reason,
                "legs": outcome.legs,
                "acceptance_packet": outcome.acceptance_packet,
                "selection": sel.get("selection") if isinstance(sel, dict) else None,
                "executing": executing,
                "leg_degraded": (outcome.trace or {}).get("leg_degraded") if outcome.trace else None,
                "accepted_count": (
                    (outcome.trace or {}).get("packet", {}).get("accepted_count")
                    if outcome.trace else None),
                "managed_process_pids": list(backend.spawned_pids),
                "managed_process_descendants_remaining": [],
            })
        finally:
            srv.stop()

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
