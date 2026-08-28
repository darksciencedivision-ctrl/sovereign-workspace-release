"""Governed CONDUCTOR dispatch feed emitter — Phase 16C `.dispatch` (directive §15 track 16C; OP-8 §13.4).

The shell's govern-born conductor pane (`.spawn`) dispatches work to worker nodes over MCP and
synthesizes the results (OP-8 §13.4). This emitter runs ONE governed dispatch through the REAL
`control_plane.orchestration.live_flow` loop (decompose → assign BY DESCRIPTOR → CANDIDATE over MCP →
real gate engine → conductor synthesis into an acceptance packet) and prints the folded
`conductor_dispatch_feed@1.0` JSON the shell renders — the SAME bounded `py -3.12` read-source pattern
the 16B picker and the 16C `.selection`/`.spawn` feeds use.

MOCK-FIRST BY DEFAULT, no live call (directive §6 / §10.4): with no flag the dispatch runs on the
mock conductor + local workers (`legs.conductor=mock`, `legs.workers=mock`) and spawns NO
`claude`/`codex` process (§2.2/§2.4). That is the ONLY thing the shell's launch path asks for — an
app launch may never spend the operator's subscription — and the live-spawn imports live inside the
`--live-workers` factory so this module cannot reach a vendor CLI without the flag.

`--live-workers` (Phase 17B `.legs`) DOES spawn one governed live `claude_code` worker: every live
gate applies first (roster profile + LIVE_OPERATION_AUTHORIZED, provider-live, R8 §6 operator terms,
CLI presence, I-X3 acquire), the flow routes it exactly one subtask, and its leg is derived from the
checkpoint the CLI reports back — so `legs.workers=live` is reachable and U58's worker half is
discharged by evidence rather than asserted. D-LOOP-1: the loopback MCP server + flow are created in
a caller-owned tempdir and torn down before the feed is emitted (`torn_down:true`), and the durable
I-X3 lease is released on every path; nothing outlives the tool.

Fail-closed (invariant 3 / invariant 20 spirit): any fault ⇒ the un-dispatched feed
(`dispatched:false`, `reason`), a 0-exit JSON line the shell renders as "dispatch unavailable", never a
fabricated dispatch.

`--emit-conductor-dispatch` prints ONLY the feed JSON (the stable shell contract, one line).
"""
from __future__ import annotations

import datetime as _dt
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Run as a script (`py -3.12 tools/live/emit_conductor_dispatch.py`) — put the repo root on sys.path
# exactly as the sibling emitters do so the shell can invoke this directly.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.orchestration.conductor_dispatch import (  # noqa: E402
    DEFAULT_OBJECTIVE,
    build_conductor_dispatch_feed,
    undispatched_feed,
)
from control_plane.orchestration.live_flow import STAGE_CRITERIA  # noqa: E402

CONDUCTOR_DIR = ROOT / "conductor"
REPO_LIVE_CONFIG = ROOT / "config" / "live_operation.json"

#: The LIVE worker's brief: the same smoke objective, plus the criteria the STAGE gate will apply to
#: whatever it publishes — a definition of done in the sense of Plan §9 (role + task + need-to-know).
#:
#: WHY (17E `.close`, measured): a live `claude` worker was given the bare objective, answered it
#: perfectly well, and the real stage gate refused the artifact because the prose contained one
#: informal incompleteness marker — `no_placeholders` is CRITICAL and scans the published bytes. The
#: node was judged by a rule nobody had given it, so whether the assembled leg came back green
#: depended on the model's word choice.
#:
#: WHAT THIS IS NOT (spec-audit M3/M4 at this gate, recorded rather than argued away):
#:  * It is NOT scoped context routed over MCP. `ModelWorkerAdapter.execute` embeds the objective
#:    verbatim into the published bytes, so this text becomes part of the artifact the gate scans.
#:    That is why the "cannot self-defeat" test below has to exist at all.
#:  * The evidence that this gate refuses live work — the 2026-07-31T15:13Z refusal run — was produced
#:    under the BARE objective, i.e. the configuration BEFORE this constant. It is evidence about the
#:    gate FUNCTION (unchanged, and pinned by the mock-path tests), not about this changed path. Under
#:    the briefed configuration there is exactly one live run and it is green.
#:  * `no_placeholders` is the only criterion here the node's wording can trip. `claims_cite_evidence`
#:    evaluates the ADAPTER's generated claim records, not the model's prose, so the brief does not
#:    tell the node it is judged on that (it used to; the sentence is gone).
#:
#: The marker words are DELIBERATELY not spelled out — quoting them here would trip `no_placeholders`
#: on every run, for the text of the instruction. `test_the_live_objective_states_the_stage_criteria_
#: and_cannot_self_defeat` pins that with the real criterion function.
LIVE_WORKER_OBJECTIVE = (
    f"{DEFAULT_OBJECTIVE}. Answer in at most three sentences of complete, finished prose. "
    f"What you publish is judged by a deterministic gate whose criteria are: "
    f"{', '.join(STAGE_CRITERIA)}. One of those binds your wording: the gate scans your text "
    f"literally for informal markers of incomplete or provisional work (the blocklist in "
    f"control_plane/gates/criteria.py) and refuses the artifact if it finds one, even in a "
    f"quotation or an aside. Write only settled statements about the roster design itself."
)


def _utc_now() -> str:
    """Wall clock for a LIVE run — the mock path stays on the fixed replayable stamp."""
    return _dt.datetime.now(_dt.timezone.utc).isoformat()

#: Smoke-scale by CONSTRUCTION, not by this number: the governed loop routes exactly one `reasoning`
#: subtask to the single live node, so exactly one exchange happens (directive §16 "live exchanges
#: MINIMAL"). `max_tokens` is threaded through the adapter contract but `claude -p` accepts no such
#: flag, so `ClaudeCliBackend.generate` cannot enforce it — the only bound that actually binds a live
#: exchange is the wall clock below. Stated plainly because the earlier comment here claimed this
#: ceiling "keeps that exchange minimal", which it does not (spec-audit MINOR-4).
LIVE_WORKER_MAX_TOKENS = 200
#: The one bound that actually binds. `claude -p` is an agentic session, not a completion endpoint:
#: it may use tools before answering. Two `.legs` dispatches spent a real call and died at 150 s with
#: the node reporting `TimeoutExpired` (visible in the feed's `node_refusals` since this sub-step);
#: the runs that then succeeded took 254 s and 318 s. Those measurements are why 150 s was wrong —
#: 420 s is a chosen margin above them, a fail-closed ceiling on ONE exchange and not a target. Each
#: live run records the elapsed time it actually needed in the feed's `live_run` block.
LIVE_WORKER_TIMEOUT_S = 420.0
LIVE_WORKER_NODE_ID = "worker-claude-live"


def _live_worker_factory(model: str | None):
    """Build the `worker_handles` factory that spawns ONE live `claude_code` worker.

    Imported lazily inside the factory so this module carries no live-spawn import unless
    `--live-workers` is actually passed: the shell's launch path invokes this emitter with no flag
    and must never be able to reach a vendor CLI (§2.4 discipline, unchanged for the default path).

    The factory RELEASES anything it acquired before it raises — `run_governed_dispatch` documents
    that ownership boundary, and a wedged I-X3 count is the failure mode it exists to prevent.
    """
    def _factory(server, project_id):
        import os
        import shutil

        from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER, ClaudeCliBackend
        from control_plane.orchestration.live_flow import WorkerHandle, live_claude_worker_handle
        from control_plane.profiles.live_authorization import load_live_authorization
        from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
        from mcp_server.protocol import McpClient
        from node_runtime.supervisor.subscription_governor import (
            SubscriptionGovernor,
            canonical_subscription_ref,
        )
        from node_runtime.supervisor.terminal_lease import TerminalLeaseLedger

        live_auth = load_live_authorization(REPO_LIVE_CONFIG)
        ref = canonical_subscription_ref("claude_code")
        allowance = live_auth.terminals_for("claude_code")   # per-provider (OP-12 §12)

        # The DURABLE I-X3 count, not just this process's. A short-lived emitter with its own fresh
        # governor cannot see the terminals the operator's running shell holds, so without this the
        # live worker below could be the 3rd terminal on a 2-terminal subscription. `seed_governor`
        # projects the durable leases in first, then `acquire` writes ours where every other process
        # can see it — so the shell's n/2 bar counts this worker while it runs (U111's gap, closed
        # for this path rather than merely disclosed).
        ledger = TerminalLeaseLedger()
        governor = SubscriptionGovernor()
        ledger.seed_governor(governor, subscription_ref=ref, provider=CLAUDE_CODE_ADAPTER,
                             allowance=allowance)
        lease = ledger.acquire(subscription_ref=ref, provider=CLAUDE_CODE_ADAPTER,
                               node_id=LIVE_WORKER_NODE_ID, allowance=allowance,
                               holder_pid=os.getpid(),
                               purpose="phase-17b.legs governed live worker dispatch",
                               session_id=f"legs-{os.getpid()}")

        # Inside the try: `credentials.issue`/`connect()` can raise, and the durable lease is already
        # held by then. Acquiring outside it stranded an I-X3 terminal on exactly the window this
        # factory's docstring promises is closed (validator R4) — self-healing only because a dead
        # `holder_pid` is later reaped, which is not a guarantee an in-process caller gets.
        client: McpClient | None = None
        try:
            client = McpClient("127.0.0.1", server.port,
                               server.credentials.issue(LIVE_WORKER_NODE_ID, "worker", project_id))
            client.connect()
            handle = live_claude_worker_handle(
                mcp_client=client,
                governor=governor,
                subscription_ref=ref,
                node_id=LIVE_WORKER_NODE_ID,
                permission_profile_id="pp-worker",
                # the REAL repo authorization (OP-6 scope) — absent/denied ⇒ the spawn refuses
                live_auth=live_auth,
                profile_loader=ProfileLoader(DeploymentProfile("cloud")),
                # OP-9 (directive §14) discharged the R8 §6 [OPERATOR] live-terms determination;
                # the loop did not and could not make it (invariant 1)
                operator_terms_confirmed=True,
                model=model,
                project_id=project_id,
                cli_present=shutil.which("claude") is not None,   # DETECTED, never hardcoded
                backend=ClaudeCliBackend(model=model, timeout_s=LIVE_WORKER_TIMEOUT_S),
                max_tokens=LIVE_WORKER_MAX_TOKENS)
        except Exception:
            # a refused spawn leaves neither a socket nor a durable lease behind (D-LOOP-1)
            if client is not None:
                client.close()
            ledger.release(lease.lease_id)
            raise

        inner_release = handle.release

        def _release() -> None:
            try:
                if inner_release is not None:
                    inner_release()
            finally:
                # the durable lease is released even if the in-process governor release throws —
                # a stranded lease outlives this process and would eat an operator terminal
                ledger.release(lease.lease_id)
                if client is not None:
                    client.close()

        return (WorkerHandle(**{**handle.__dict__, "release": _release}),)
    return _factory


def emit(*, live_workers: bool = False, model: str | None = None) -> dict:
    """Run the governed dispatch in a self-cleaning tempdir and return the folded feed. The tempdir
    is created UNDER the OS temp root (never in the repo, §2.5) and removed on exit.

    `live_workers=False` (the default, and the ONLY thing the shell's launch path asks for) makes no
    live call at all. `live_workers=True` (Phase 17B `.legs`) replaces the deterministic pool with a
    single governed LIVE `claude_code` worker: the flow routes it exactly one subtask, so exactly one
    live exchange happens, and its leg is derived from the checkpoint the CLI reports back.
    """
    started = time.time()
    try:
        with tempfile.TemporaryDirectory(prefix="sov-dispatch-") as td:
            feed = build_conductor_dispatch_feed(
                conductor_dir=CONDUCTOR_DIR, store_root=Path(td),
                # The LIVE path alone carries the criteria brief; the shell's launch dispatch keeps
                # the replayable objective every mock receipt was folded from.
                objective=LIVE_WORKER_OBJECTIVE if live_workers else DEFAULT_OBJECTIVE,
                # the live worker is the ONLY node in the pool, so the one `reasoning` subtask it can
                # serve routes to it by descriptor and the rest are honestly QUEUED — one live call
                worker_ids=() if live_workers else ("worker-A", "worker-B"),
                # A LIVE run takes the REAL clock: a run that spent a real call is dated when it
                # happened, never with the mock path's replayable `DISPATCH_TS` (inv 11). The mock
                # path keeps the fixed stamp so its receipts stay byte-reproducible.
                clock=_utc_now if live_workers else None,
                worker_handles=_live_worker_factory(model) if live_workers else None)
    except Exception as exc:  # noqa: BLE001 — even a tempdir/setup fault is reported, never faked
        feed = undispatched_feed(f"{type(exc).__name__}: {exc}",
                                 ts=_utc_now() if live_workers else None)
    if live_workers:
        # The receipt must stand on its own. Without these a `live` feed is shape-identical to one a
        # stub could print, and the gate-validator had to reconstruct the run from filesystem mtimes
        # to corroborate it (validator R1). None of this PROVES liveness — `verify_reported_checkpoint`
        # carries the STATED LIMIT (U43) that instrumentation on a caller-supplied object constrains
        # its class, not its behaviour — but it dates the run and records the host facts it depended on.
        feed["live_run"] = {
            "run_ts": _utc_now(),
            "elapsed_s": round(time.time() - started, 1),
            "cli_present": shutil.which("claude") is not None,
            "repo_live_config_exists": REPO_LIVE_CONFIG.exists(),
            "requested_model": model,
            "max_tokens": LIVE_WORKER_MAX_TOKENS,
            "timeout_s": LIVE_WORKER_TIMEOUT_S,
        }
    return feed


def main(argv: list[str]) -> int:
    if "--emit-conductor-dispatch" in argv:
        live = "--live-workers" in argv
        model = None
        if "--model" in argv:
            idx = argv.index("--model")
            if idx + 1 < len(argv):
                model = argv[idx + 1]
        sys.stdout.write(json.dumps(emit(live_workers=live, model=model), default=str) + "\n")
        return 0
    sys.stderr.write(
        "usage: emit_conductor_dispatch.py --emit-conductor-dispatch [--live-workers] [--model SLUG]\n"
        "  prints the governed conductor_dispatch_feed@1.0 JSON the shell renders (Phase 16C .dispatch).\n"
        "  --live-workers spawns ONE governed live claude_code worker (Phase 17B .legs) — every live\n"
        "  gate applies and an unmet gate yields the honest un-dispatched feed, never a fake dispatch.\n"
    )
    return 2


if __name__ == "__main__":  # pragma: no cover - exercised via tests calling main()
    raise SystemExit(main(sys.argv[1:]))
