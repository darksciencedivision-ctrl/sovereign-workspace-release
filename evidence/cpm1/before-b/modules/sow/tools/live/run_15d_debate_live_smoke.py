"""Phase 15D `.debate` LIVE re-run — operator-run live smoke (OP-9, directive §14).

This is NOT part of `pytest tests/`: it spawns the REAL host `claude` CLI for every debater,
which the deterministic suite must never do (`tests/integration/test_live_debate_flow.py` proves
the identical governed path MOCK-FIRST — no process). This is the live analogue of the Phase-1
spike's operator-run metric: ONE bounded debate through the SAME Phase-7-gated Debate Service and
the SAME live-spawn gates the mock-first suite exercises
(`control_plane.orchestration.live_debate.attempt_live_debate`), but with genuine
`ClaudeCliBackend` debaters, so each leg can be recorded `live` when — and only when — the CLI
reports back a verified executing checkpoint for a call spent inside THIS debate.

Directive §11 15D: "one bounded live debate (budgets enforced — real tokens now)". Everything the
governed path enforces still applies here and is un-bypassable by this driver:
  - ≤5 rounds hard cap, per-debate budget + per-caller quota + global concurrent cap (invariants
    14/17); a clean budget-exhaustion cutoff; dissent preserved VERBATIM (invariant 15);
  - two DISTINCT live backends (invariant 18 — no node solely judges its own work); the caller is
    a NON-conductor node (§2.8 — the service is not conductor-coupled);
  - every live gate in `spawn_claude_code_terminal` (profile+live auth, provider gate re-asserted,
    R8 §6 operator terms, CLI presence, I-X3 concurrency ≤ authorized allowance).

OP-9 discharged the R8 §6 [OPERATOR] live-terms gate for `claude_code`; this driver passes
`operator_terms_confirmed=True` on that RECORDED basis (invariant 1: the loop did not make that
determination, the operator did). Any OTHER unmet gate ⇒ skip-with-record, NO live call (§10.4).

Honesty (§6/§10.4): the outcome is reported EXACTLY as the governed path records it.
`build_debate_report` refuses to package any leg as `live` without a VERIFIED checkpoint for that
debater, so a mock/attempted/skipped leg can never be dressed up as a real-provider result.
D-LOOP-1: `attempt_live_debate` spawns → exercises → tears down within the call (synchronous
`subprocess.run` with a hard timeout per `generate`, and every I-X3 terminal released in a
`finally`), so no live process outlives this driver.

Usage:  py -3.12 tools/live/run_15d_debate_live_smoke.py [--model SLUG] [--max-rounds N]
                                                         [--timeout SECONDS]

By default each debater requests the CLI DEFAULT model (no `--model`), which is the most reliable
way to obtain a verified live checkpoint on an arbitrary host (the fable-5 slug acceptance was
confirmed end-to-end at `.flow`, U33). Pass `--model claude-fable-5` to drive the debaters on the
conductor selection's own checkpoint.
"""
from __future__ import annotations

import argparse
import base64
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.frontier.claude_code import ClaudeCliBackend  # noqa: E402
from control_plane.orchestration.live_debate import DebaterSpec, attempt_live_debate  # noqa: E402
from control_plane.profiles.live_authorization import load_live_authorization  # noqa: E402
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader  # noqa: E402
from mcp_server.protocol import McpClient  # noqa: E402
from mcp_server.server import MCPServer  # noqa: E402
from node_runtime.supervisor.subscription_governor import (  # noqa: E402
    SubscriptionGovernor,
    canonical_subscription_ref,
)

REPO_LIVE_CONFIG = ROOT / "config" / "live_operation.json"

# Smoke-scale, genuinely arguable topic with ONE seeded piece of evidence the debaters may cite.
EVIDENCE_TEXT = "The candidate roster note reads: 'Offline profile: exactly one conductor, no cloud adapters.'"
TOPIC = ("Does the candidate roster note satisfy the acceptance criterion of naming exactly one "
         "offline conductor with no cloud adapters?")


def _seed_evidence(srv: MCPServer, text: str) -> str:
    """Publish a REAL shared-memory entry a debater may cite, so a SUPPORTED citation means a ref
    that actually resolved in MCP — not a string that merely looked like one.

    Least privilege: a `worker`-role credential suffices to publish a CANDIDATE evidence entry
    (`evidence` is not an operator-only kind), and minting an authority-bearing `operator` role
    where a worker suffices is the wrong default — the same principle the debate path enforces via
    its role whitelist."""
    c = McpClient("127.0.0.1", srv.port, srv.credentials.issue("seed", "worker", "proj"))
    c.connect()
    try:
        return c.call(
            "publish", kind="evidence", tier="shared_project",
            content_b64=base64.b64encode(text.encode()).decode("ascii"),
            provenance={"author_node": "seed", "task_id": None,
                        "ts": "2026-07-20T00:00:00+00:00",
                        "directive_version": "v2.4", "confidence": "high"},
            status="CANDIDATE")["entry_id"]
    finally:
        c.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    # model=None sentinel: request the CLI DEFAULT (no --model). An explicit slug is carried
    # verbatim to argv and is only *confirmed* by the reply (it never reaches the extractor).
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-rounds", type=int, default=2)   # ≤5 hard cap; 2 allows one rebuttal
    ap.add_argument("--timeout", type=float, default=150.0)
    # U76 (Phase 17A `.pty`): ONE canonical ref per provider — the I-X3 cap is enforced per ref,
    # so a second spelling of the same real subscription is a second bucket at full allowance.
    ap.add_argument("--subscription", default=canonical_subscription_ref("claude_code"))
    args = ap.parse_args()

    cli_present = shutil.which("claude") is not None
    result: dict = {
        "topic": TOPIC,
        "cli_present": cli_present,
        "requested_model": args.model or "<cli-default>",
        "max_rounds": args.max_rounds,
        "repo_live_config_exists": REPO_LIVE_CONFIG.exists(),
    }

    with tempfile.TemporaryDirectory() as td:
        srv = MCPServer(Path(td) / "store")
        srv.start()
        try:
            ref = _seed_evidence(srv, EVIDENCE_TEXT)

            # The REAL repo authorization (OP-6 scope). Absent/denied ⇒ skip-with-record.
            live_auth = load_live_authorization(REPO_LIVE_CONFIG)

            # TWO GENUINE, DISTINCT vendor backends (invariant 18) that actually spawn `claude`.
            # Distinct instances — `attempt_live_debate` refuses two debaters sharing one backend.
            debaters = [
                DebaterSpec("debater-A", backend=ClaudeCliBackend(model=args.model,
                                                                  timeout_s=args.timeout)),
                DebaterSpec("debater-B", backend=ClaudeCliBackend(model=args.model,
                                                                  timeout_s=args.timeout)),
            ]

            outcome = attempt_live_debate(
                topic=TOPIC,
                server=srv,
                governor=SubscriptionGovernor(),
                subscription_ref=args.subscription,
                live_auth=live_auth,
                profile_loader=ProfileLoader(DeploymentProfile("cloud")),
                operator_terms_confirmed=True,   # OP-9: R8 §6 [OPERATOR] live-terms discharged
                debaters=debaters,
                caller_node_id="worker-caller",  # non-conductor caller (§2.8)
                caller_role="worker",
                evidence_refs=[ref],
                max_rounds=args.max_rounds,
                budget_units=300,                # 3 rounds worth at round_cost=100 (hard cap)
                round_cost=100,
                cli_present=cli_present,          # the DETECTED value, not a hardcoded True
            )

            report = outcome.report or {}
            result.update({
                "ran": outcome.ran,
                "published": outcome.published,
                "skipped_with_record": outcome.skipped_with_record,
                "reason": outcome.reason,
                "legs": outcome.legs,
                "debate_id": outcome.debate_id,
                "mcp_entry": outcome.mcp_entry,
                "report_entry": outcome.report_entry,
                "outcome": report.get("outcome"),
                "rounds_used": report.get("rounds_used"),
                "dissent_present": report.get("dissent") is not None,
                "cost_actual": report.get("cost_actual"),
                "budget": report.get("budget"),
                "debater_models": report.get("debater_models"),
                "evidence_map": report.get("evidence_map"),
                "positions": report.get("positions"),
            })
        finally:
            srv.stop()

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
