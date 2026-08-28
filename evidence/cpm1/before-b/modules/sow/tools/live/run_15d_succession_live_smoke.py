"""Phase 15D `.succession` LIVE re-run — operator-run live smoke (OP-9, directive §14).

This is NOT part of `pytest tests/`: it spawns the REAL host `claude` CLI for the predecessor
conductor's decomposition, which the deterministic suite must never do
(`tests/integration/test_live_succession.py` proves the identical governed handover MOCK-FIRST —
no process, pinned by a `subprocess.Popen` ban). It is the live analogue of the Phase-1 spike's
operator-run metric: ONE governed conductor succession through the SAME gated path the mock-first
suite exercises (`control_plane.orchestration.live_succession.LiveConductorSuccession`), but with a
genuine live claude_code conductor as the PREDECESSOR — so the conductor that gets killed is a real,
subscription-spending Fable-5 conductor with a VERIFIED executing checkpoint, not a mock.

Directive §11 15D / OP-9 §2: "kill the live Fable-5 conductor mid-run, resume on a different
live/local backend, zero project loss, restore selection." Everything the governed path enforces
still applies here and is un-bypassable by this driver:
  - the KILL is real: the predecessor's adapter is closed (releasing its subscription terminal) and
    its MCP session ends; if it survives `close()` the succession is REFUSED, never reported;
  - the successor is a SEPARATELY-CONSTRUCTED adapter on its OWN MCP session + node id that reloads
    all 12 conductor files FROM shared memory (invariant 5), gated by the §19.1 staleness checklist;
  - ZERO LOSS is compared by CONTENT HASH read back from MCP, never by entry id, never by trusting
    a node's own `content_hash` (I-M1);
  - the succession report is published CANDIDATE by the successor and promoted by a SEPARATE gate
    node (invariant 18), `operator_disposition: pending` (invariant 1);
  - I-X3 release-before-acquire is OBSERVED on the real `SubscriptionGovernor`.

WHY THE PREDECESSOR IS THE LIVE LEG, AND THE SUCCESSOR IS NOT. `LiveGovernedFlow._synthesize`
assembles the acceptance packet DETERMINISTICALLY from MCP reads + gate records — it never calls
the successor's backend (U46/U58). So a successor conducts (loads its 12 files, reads the ACCEPTED
set, publishes, is gated) WITHOUT spending a model call, and the leg vocabulary — which reports
model SPEND, not activity — records its leg `skipped` regardless of which backend it is. The
meaningful LIVE element of a succession is therefore the KILLED conductor: its live decomposition
call is a genuine Fable-5 subscription spend. This driver makes the predecessor a real
`ClaudeCliBackend` and keeps the successor a distinct mock backend (`mock-successor`), exactly as
the mock-first suite records the successor leg — fully honest, and no extra live call spent.

OP-9 discharged the R8 §6 [OPERATOR] live-terms gate for `claude_code`; the predecessor factory
passes `operator_terms_confirmed=True` on that RECORDED basis (invariant 1: the loop did not make
that determination, the operator did). An unauthorized/absent `live_auth` still raises through
`spawn_claude_code_conductor`'s ordered gates (assert_startup + assert_provider_live) and becomes a
skip-with-record with NO live call (§10.4). NOTE: because this driver INJECTS a real backend, the
spawn's own CLI-presence gate is bypassed (`conductor_spawn` skips it whenever a backend is supplied),
so the detected `cli_present` value passed here is inert; an absent `claude` binary instead fails
closed one layer down — `ClaudeCliBackend.generate` raises `FileNotFoundError` → `ClaudeCodeAuthError`,
caught by `LiveConductorSuccession.run()` and reported as a skip-with-record, still with no spend and
no naked session.

Honesty (§6/§10.4): the outcome is reported EXACTLY as the governed path records it. The
predecessor leg is `live` only when the CLI reported back a VERIFIED executing checkpoint for a call
spent inside THIS run; `zero_loss.ok` is preservation (nothing lost) and `work_advanced` is the
anti-vacuity strengthener (the successor completed work the predecessor never saw). With a
dependency-free live decomposition the whole graph finishes in one wave, so `work_advanced` can be
False even though the kill + governed handover + zero-loss preservation all held — that is recorded,
never dressed up. D-LOOP-1: the only live child is the predecessor's synchronous `subprocess.run`
decomposition (hard timeout), and `LiveConductorSuccession.run()` tears every adapter/client down in
a `finally`, so no live process outlives this driver.

Usage:  py -3.12 tools/live/run_15d_succession_live_smoke.py [--model SLUG] [--timeout SECONDS]
                                                             [--kill-after-waves N]

By default the predecessor requests the CLI DEFAULT model (no `--model`), the most reliable way to
obtain a verified live checkpoint on an arbitrary host (the fable-5 slug acceptance was confirmed
end-to-end at `.flow`, U33). The conductor SELECTION stays fable-5 (operator-selected, invariant 3)
regardless of which checkpoint actually executes; the executing checkpoint is recorded separately
and honestly. Pass `--model claude-fable-5` to drive the predecessor on the selection's own slug.
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
from control_plane.conductor.selection import OPERATOR_SELECTED_CONDUCTOR  # noqa: E402
from control_plane.orchestration.live_flow import live_conductor_handle  # noqa: E402
from control_plane.orchestration.live_succession import (  # noqa: E402
    LiveConductorSuccession,
    mock_successor_handle,
)
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
OBJECTIVE = "Draft a short offline conductor roster note"  # smoke-scale (minimal tokens)


def main() -> int:
    ap = argparse.ArgumentParser()
    # model=None sentinel: request the CLI DEFAULT (no --model). An explicit slug (e.g.
    # "claude-fable-5") is carried verbatim to argv and is only *confirmed* by the reply.
    ap.add_argument("--model", default=None)
    ap.add_argument("--timeout", type=float, default=150.0)
    # U76 (Phase 17A `.pty`): ONE canonical ref per provider — the I-X3 cap is enforced per ref,
    # so a second spelling of the same real subscription is a second bucket at full allowance.
    ap.add_argument("--subscription", default=canonical_subscription_ref("claude_code"))
    ap.add_argument("--kill-after-waves", type=int, default=1)
    args = ap.parse_args()

    cli_present = shutil.which("claude") is not None
    result: dict = {
        "objective": OBJECTIVE,
        "cli_present": cli_present,
        "requested_model": args.model or "<cli-default>",
        "kill_after_waves": args.kill_after_waves,
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

            # The REAL repo authorization (OP-6 scope). Absent/denied ⇒ the predecessor factory
            # raises through the spawn gates ⇒ skip-with-record, NO live call.
            live_auth = load_live_authorization(REPO_LIVE_CONFIG)
            # ONE governor shared by the runner AND both conductors, so the I-X3 release-before-
            # acquire handoff is OBSERVED on the same object, not asserted.
            governor = SubscriptionGovernor()

            def predecessor_factory(client):
                """The LIVE Fable-5 conductor that gets killed. A genuine `ClaudeCliBackend` (model
                None ⇒ CLI default, the reliably-verifiable checkpoint) is injected, so its
                decomposition spends a real subscription call and its leg is `live` on a verified
                checkpoint. Built through the SAME governed spawn gates the mock-first suite uses via
                `mock_predecessor_handle`; the only difference is a real vendor backend."""
                # node_id MUST match the client the runner issues for the predecessor
                # (`LiveConductorSuccession._client("conductor-fable5", ...)`): MCP enforces
                # provenance.author_node == the publishing node (invariant 11), so a conductor
                # publishing under a different id than its credential is refused. The mock helper
                # (`mock_predecessor_handle`) defaults to exactly this id for the same reason.
                return live_conductor_handle(
                    mcp_client=client, governor=governor, subscription_ref=args.subscription,
                    node_id="conductor-fable5", permission_profile_id="pp-conductor",
                    live_auth=live_auth, profile_loader=ProfileLoader(DeploymentProfile("cloud")),
                    operator_terms_confirmed=True,   # OP-9: R8 §6 [OPERATOR] live-terms discharged
                    conductor_file_refs=manifest, model=args.model,
                    selection=OPERATOR_SELECTED_CONDUCTOR, project_id="proj",
                    cli_present=cli_present,          # the DETECTED value, not a hardcoded True
                    backend=ClaudeCliBackend(model=args.model, timeout_s=args.timeout))

            def successor_factory(client):
                """A DIFFERENT backend that resumes the SAME governed run. Mock, deliberately: the
                successor's synthesis spends no model call (U46/U58), so its leg is `skipped`
                whatever backend it is — a live/local successor would add no observable live leg. A
                distinct `model_name` ('mock-successor') is what makes 'a DIFFERENT backend' checkable
                in the report's label-difference refusal (U50)."""
                return mock_successor_handle(client, manifest, governor=governor,
                                             subscription_ref=args.subscription)

            runner = LiveConductorSuccession(
                srv, manifest, predecessor_factory=predecessor_factory,
                successor_factory=successor_factory, governor=governor,
                subscription_ref=args.subscription)
            outcome = runner.run(OBJECTIVE, kill_after_waves=args.kill_after_waves)

            report = outcome.report or {}
            zl = outcome.zero_loss
            result.update({
                "ran": outcome.ran,
                "published": outcome.published,
                "skipped_with_record": outcome.skipped_with_record,
                "governance_refusal": outcome.governance_refusal,
                "reason": outcome.reason,
                "legs": outcome.legs,
                "report_verdict": outcome.report_verdict,
                "report_entry": outcome.report_entry,
                "acceptance_packet": outcome.acceptance_packet,
                "predecessor": report.get("predecessor"),
                "successor": report.get("successor"),
                "run_spend_leg": report.get("run_spend_leg"),
                "restored_selection": report.get("restored_selection"),
                "restored_selection_note": report.get("restored_selection_note"),
                "handoff_order": report.get("handoff_order"),
                "handoff_note": report.get("handoff_note"),
                "staleness_ok": (report.get("staleness") or {}).get("ok"),
                "zero_loss": ({"ok": zl.ok, "checks": zl.checks} if zl is not None else None),
            })
        finally:
            srv.stop()

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
