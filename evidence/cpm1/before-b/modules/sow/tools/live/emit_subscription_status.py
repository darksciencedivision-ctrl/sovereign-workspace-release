"""Governed SUBSCRIPTION-STATUS feed — Phase 16D `.statusbar` (directive §15 track 16D; OP-10).

The operator launched the shipped shell and saw the status bar report
"⚠ concurrency count unavailable (fail-closed)" (OP-10 first-use finding). Root cause: the
always-visible status bar reads the subscription-concurrency n/2 count over the `subscription_status`
IPC op, but the gateway the running shell actually spawns is the `EchoControlSurface` (diagnostic
transport), which does NOT expose that op — so the read fails and the bar degrades, honestly but
uselessly, to the em-dash unknown. The tested IPC read path (`apps/desktop/statusbar/source.js` +
`apps/desktop/test/statusbar-source.test.js`, proven against a real seeded `SubscriptionGovernor`)
is correct; it simply has no governor-backed surface to talk to in the shipped shell.

`.statusbar` closes that gap the SAME way 16B (picker) and 16C (`.selection`/`.spawn`/`.dispatch`)
closed theirs: a bounded one-shot `py -3.12` read-source emitter — NOT the WS-IPC channel — that
builds the REAL `SubscriptionGovernor`, seeds it from the enforced `LiveAuthorization` scope (the
same `config/live_operation.json` gate every live path reads), and prints its `status()` as one JSON
line the shell folds through the pure `terminal/statusbar/statusbar-model` view. The shell renders a
readable **n/allowance** count instead of "unavailable".

SUBSTITUTION (directive §6, recorded): a bounded subprocess emitter, not the authenticated WebSocket
IPC surface (`SubscriptionStatusControlSurface`). The IPC surface stays the design endpoint for a
long-lived governor-backed gateway; wiring it into the shell's gateway process would REPLACE the
`EchoControlSurface` the supervisor's `health`/`session_event` liveness path already rides — a
first-launch regression risk exactly of the class D-P16-0 warns against — so `.statusbar` uses the
proven, isolated read-source instead. Recorded here and in the evidence report.

HONESTY (invariant 3; §6; §10.4). The emitted count is REAL, not fabricated:
  * `allowance` is the operator-authorized OP-6 ceiling read from the enforced `LiveAuthorization`
    (governor-capped at 2; a config may narrow, never widen);
  * `in_use` is the count of `active` terminals held by the governor this emit builds. The governor
    is built FRESH per emit and is NOT wired to any live-session tracker, so in the non-interactive
    build `in_use` is structurally **0** — a truthful, honest zero (the governor WAS read and holds
    no active terminal; the shell drives no live frontier session — mock-first §2.4, live drive is
    operator-run / gate 16F), distinct from the em-dash "we could not read". It only ever UNDERstates
    concurrency (the fail-safe direction — it can never mint capacity or authority).
DYNAMIC per-session tracking — `in_use` rising/falling as the shell itself spawns and reaps live
workers against a SHARED, long-lived governor — is OWED to gate 16F (recorded
`live_session_tracking.owed`), where the shell actually drives live spawns. `.statusbar` makes the
authorized ceiling + the current (0) held-count READABLE; it does not yet watch live sessions.

FAIL-CLOSED (invariant 3 / invariant 20 spirit). `load_live_authorization()` fails closed: absence
of `config/live_operation.json` (a fresh clone) ⇒ DENIED, and this emits `authorized:false,
status:null` — which the JS fold renders as the em-dash unknown with the reason attached, never a
fabricated "0/2". A malformed/out-of-scope config RAISES `LiveAuthorizationError`; the emitter reports
it as `authorized:false, status:null` with the reason, so the bar stays honest rather than crashing.
No model call, no credential, no network (§2.2/§2.4): the emitter only reads the authorization gate
and builds an in-memory governor.

`--emit-subscription-status` prints ONLY the feed JSON (the stable shell contract, one line).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

# Run as a script (`py -3.12 tools/live/emit_subscription_status.py`): Python puts the SCRIPT dir on
# sys.path, not the repo root — bootstrap the root exactly as the sibling emitters do so the shell can
# invoke this directly.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.profiles.live_authorization import (  # noqa: E402
    LiveAuthorization,
    LiveAuthorizationError,
    load_live_authorization,
)
from node_runtime.supervisor.subscription_governor import (  # noqa: E402
    SubscriptionGovernor,
    canonical_subscription_ref,
)
from node_runtime.supervisor.terminal_lease import (  # noqa: E402
    LeaseLedgerCorrupt,
    LeaseLedgerLocked,
    TerminalLeaseLedger,
)

#: Pinned so the shell source can validate the shape it parses (a drifted producer is refused).
SUBSCRIPTION_STATUS_FEED_SCHEMA = "subscription_status_feed@1.0"

#: The ONE canonical ref per provider (U76). This used to be a private spelling here while the
#: conductor launch path counted under another — two buckets for one real subscription, and a bar
#: that read 0/2 against a genuinely held terminal. Both now derive from the same function.
_subscription_ref = canonical_subscription_ref


def _load_auth() -> tuple[LiveAuthorization | None, str | None]:
    """Resolve the enforced authorization, fail-closed. Returns (auth, error). A DENIED auth is a
    valid `LiveAuthorization` (authorized:false) with a reason; a malformed config raises, which we
    turn into (None, reason) so the emitter reports an honest unreadable status rather than crashing."""
    try:
        return load_live_authorization(), None
    except LiveAuthorizationError as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _denied_feed(*, reason: str, register_row: str | None, source: str) -> dict[str, Any]:
    """Fail-closed feed: no readable governor ⇒ `status:null`, which the JS fold renders as the
    em-dash unknown (never a fabricated 0/2). This is the fresh-clone (no config) / malformed path."""
    return {
        "schema": SUBSCRIPTION_STATUS_FEED_SCHEMA,
        "authorized": False,
        "providers": [],
        "allowance": 0,
        "register_row": register_row,
        "source": source,
        "reason": reason,
        "status": None,   # unreadable ⇒ fail-closed unknown in the bar
        "live_session_tracking": {
            "owed": True,
            "issue": "16F",
            "note": "not authorized — no live-operation config; the bar shows the fail-closed unknown",
        },
    }


def build_subscription_status_feed(
    *,
    live_auth: LiveAuthorization | None = None,
    governor: SubscriptionGovernor | None = None,
    held: Mapping[str, Sequence[str]] | None = None,
    ledger: TerminalLeaseLedger | None = None,
) -> dict[str, Any]:
    """Build the status-bar feed from the REAL governor, seeded from the enforced authorization.

    Defaults resolve the REAL repo authorization (`load_live_authorization()`) and a fresh
    `SubscriptionGovernor`. For each authorized provider one subscription is registered at the
    authorized allowance (the OP-6 ceiling). `held` optionally injects acquired terminals per
    provider (`{provider: [node_id, …]}`) so the "active"/"at-capacity" render path is exercisable
    in tests exactly as a live spawn would `acquire()`; the shell contract passes no `held`, so
    `in_use` is a truthful 0 (no live frontier terminal is held by the non-interactive shell —
    live drive is operator-run / 16F). No model call, no credential (§2.2/§2.4)."""
    if live_auth is not None:
        auth: LiveAuthorization | None = live_auth
        auth_err: str | None = None
    else:
        auth, auth_err = _load_auth()

    if auth is None:  # malformed/out-of-scope config raised — fail closed, honest unreadable
        return _denied_feed(reason=auth_err or "live authorization unreadable", register_row=None,
                            source="(none)")
    if not auth.authorized:  # DENIED by absence / explicit disable — fail closed, honest unreadable
        return _denied_feed(reason=auth.reason, register_row=auth.register_row, source=auth.source)

    gov = governor if governor is not None else SubscriptionGovernor()
    led = ledger if ledger is not None else TerminalLeaseLedger()
    providers = sorted(auth.providers)
    ledger_error: str | None = None
    seeded: dict[str, list[str]] = {}
    for provider in providers:
        ref = _subscription_ref(provider)
        # register at the authorized allowance (the ceiling), then acquire any injected held terminals
        # — the exact register-then-acquire the supervised frontier-spawn path performs.
        # PER-PROVIDER allowance (OP-12 §12), not the global config number. Passing the global one
        # here was a real regression the moment the operator wrote the OP-12 switch the repo's own
        # `.example` publishes: the governor refuses an allowance above a provider's cap, the
        # ValueError propagated out of `main`, the feed exited nonzero, and the shell degraded the
        # WHOLE bar to the em-dash unknown — including claude_code and openai_codex_cli, i.e. the
        # "concurrency count unavailable (fail-closed)" defect OP-10/16D exists to have fixed.
        gov.register_subscription(ref, provider=provider, allowance=auth.terminals_for(provider))
        # Phase 17A `.pty` (U76): seed from the DURABLE lease ledger, so `in_use` is the count of
        # terminals actually held RIGHT NOW — including the live interactive conductor session the
        # shell holds in pane 1, which no in-process governor of this short-lived emitter could see.
        # A lease whose holder process is gone is not live and is never counted. Fail-closed and
        # non-fatal: an unreadable ledger leaves the ceiling readable and is reported, never guessed.
        try:
            seeded[ref] = [ln.lease_key for ln in led.seed_governor(
                gov, subscription_ref=ref, provider=provider,
                allowance=auth.terminals_for(provider))]
        except (LeaseLedgerCorrupt, LeaseLedgerLocked) as exc:
            ledger_error = f"{type(exc).__name__}: {exc}"
        for node_id in (held or {}).get(provider, ()):  # test/injection hook only
            gov.acquire(ref, node_id)

    return {
        "schema": SUBSCRIPTION_STATUS_FEED_SCHEMA,
        "authorized": True,
        "providers": providers,
        "allowance": auth.terminals_per_subscription,      # the GLOBAL ceiling (kept for shape)
        # …and the per-provider truth beside it: after OP-12 one number cannot describe four
        # subscriptions (grok/antigravity are 1 each under a config that says 2). A consumer that
        # renders `allowance` alone overstates two of them; the bar reads THIS map for its display
        # ceiling (wired at `.picker`, clamped to the code-pinned cap at the 18B close so the feed
        # can narrow but never raise).
        "allowance_by_provider": {p: auth.terminals_for(p) for p in providers},
        "register_row": auth.register_row,
        "source": auth.source,
        "reason": auth.reason,
        # {ref: {provider, allowance, active:[…], in_use}} — the REAL count. A ledger the emitter
        # could not read yields `status: null`, i.e. the em-dash UNKNOWN in the bar: with the count
        # now sourced from the durable ledger, a readable-looking `in_use: 0` beside a read fault
        # would be exactly the fabricated zero U76 was opened for (the bar never shows 0 as a claim).
        "status": None if ledger_error else gov.status(),
        "durable_leases": {
            # Observability (invariant 27): which durable lease keys were projected into the count,
            # and whether the ledger could be read at all.
            "seeded": seeded,
            "error": ledger_error,
        },
        "live_session_tracking": {
            # Phase 17A `.pty` (U76): `in_use` is sourced from the DURABLE cross-process lease
            # ledger, so the live interactive CONDUCTOR session the shell holds shows up here — the
            # bar can no longer read 0/2 against a genuinely held terminal. 17B closed the worker
            # half: `emit_worker_launch` takes a durable lease for every frontier pane, OP-12
            # included, so a live worker IS counted here (the prose above said otherwise until the
            # 18B close — spec-audit MINOR-6). Local/Ollama nodes are not subscription-bound by
            # design and are counted by VRAM residency, not by a subscription (invariant 19).
            "owed": False,
            "issue": None,
            "conductor_counted": True,
            "worker_counted": True,
            "ledger_error": ledger_error,
            "note": "in_use = durable I-X3 leases held right now (the conductor session AND every "
                    "frontier worker pane since 17B), reaped when a holder process dies; allowance "
                    "= the authorized per-provider ceiling (2 for the OP-6 pair, 1 each for the "
                    "OP-12 pair). A ledger read fault yields status:null.",
        },
    }


def main(argv: list[str]) -> int:
    """CLI: `--emit-subscription-status` prints the status feed as one JSON line and exits 0 (a
    fail-closed unreadable status is still a 0-exit feed the shell renders as the honest unknown).
    Any other invocation prints usage to stderr and exits 2 — the shell source treats a non-zero exit
    as "unavailable" and renders the em-dash unknown, never a fabricated count."""
    if "--emit-subscription-status" in argv:
        sys.stdout.write(json.dumps(build_subscription_status_feed(), default=str) + "\n")
        return 0
    sys.stderr.write(
        "usage: emit_subscription_status.py --emit-subscription-status\n"
        "  prints the governed subscription_status_feed@1.0 JSON the shell status bar renders "
        "(Phase 16D .statusbar).\n"
    )
    return 2


if __name__ == "__main__":  # pragma: no cover - exercised via tests calling main()
    raise SystemExit(main(sys.argv[1:]))
