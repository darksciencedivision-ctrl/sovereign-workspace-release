"""Governed CONDUCTOR spawn feed — Phase 16C `.spawn` (directive §15 track 16C; OP-8 §13 / OP-9).

The shell's pane 1 is the conductor-first CONDUCTOR node (§12.4). Until `.selection` it drew its
badge from a hand-maintained literal (U65, closed); until THIS sub-step the pane was a pure JS
placeholder that never touched the governed spawn path — the on-launch pane 1 was not *born* through
`node_runtime/supervisor/conductor_pane_spawn.spawn_conductor_pane` and its `node_state` string was a
hardcoded constant. `.spawn` ends that: the shell sources the conductor pane's governed spawn from
THIS emitter, so pane 1 is GOVERNED-BORN through the full live-gate chain
(`ProfileLoader.assert_startup` + `LiveAuthorization.assert_provider_live` + R8 §6 operator terms +
`claude` CLI presence + the I-X3 `SubscriptionGovernor`), exactly as a live worker pane is.

SUBSTITUTION (directive §6, recorded): this is a bounded one-shot subprocess emitter — the SAME
`py -3.12` read-source pattern the 16B picker and the 16C `.selection` badge use — NOT the WS-IPC
channel. It runs the governed spawn with NO launcher, so the real interactive `claude` ConPTY drive
is DEFERRED to the operator-run shell (`spawn_conductor_pane`'s documented deferred branch): a live
model call is never made here (§2.2/§2.4), and `node_state` is the honest `awaiting_live_conductor`
— gates passed, argv + credential-scrubbed env built, I-X3 counted — but no session attached yet. The
mock-first "ready" branch (a launcher injected ⇒ `node_state: ready`) is proven by the unit tests and
`build_conductor_spawn_feed(..., launcher=...)`; the shell contract emits the deferred governed spawn.

D-LOOP-1 (CRITICAL, directive §14): the governed spawn ACQUIRES one I-X3 terminal; this emitter tears
it down (`ConductorPaneSession.teardown()`) in a `finally` BEFORE emitting, and records the release
(`torn_down` / `governor_released`) so a reader can verify no live terminal outlives the tool. With no
launcher nothing is actually launched, so teardown only releases the counted terminal — a live
`claude` process is never started here in the first place.

Honesty / fail-closed (invariant 3, invariant 20 spirit): if any gate REFUSES (no live-operation
config, provider not live, operator terms unconfirmed, `claude` absent, naked identity, I-X3 full)
this emits a governed-REFUSAL feed (`spawned:false`, `refused:true`, `reason`, `node_state:
spawn_refused`) — NEVER a fabricated spawn. `operator_terms_confirmed=True` rides the RECORDED OP-9
determination (the operator made it, not the loop — invariant 1); it is not a credential.

`--emit-conductor-spawn` prints ONLY the feed JSON (the stable shell contract, one line).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

# Run as a script (`py -3.12 tools/live/emit_conductor_spawn.py`), Python puts the SCRIPT dir on
# sys.path, not the repo root — bootstrap the root exactly as the sibling emitters do so the shell
# can invoke this directly.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER  # noqa: E402
from adapters.conductor.provider_commands import ConductorProviderUnavailable  # noqa: E402
from control_plane.conductor.registry import (  # noqa: E402
    ConductorDescriptor,
    ConductorRegistryError,
    load_runtime_conductor_descriptor,
)
from control_plane.conductor.selection import (  # noqa: E402
    OPERATOR_SELECTED_CONDUCTOR,
    ConductorSelection,
)
from control_plane.profiles.live_authorization import (  # noqa: E402
    LiveAuthorization,
    LiveAuthorizationError,
    load_live_authorization,
)
from control_plane.profiles.loader import (  # noqa: E402
    DeploymentProfile,
    ProfileLoader,
    ProfileViolation,
)
from node_runtime.supervisor.conductor_pane_spawn import (  # noqa: E402
    ConductorPaneRefused,
    spawn_conductor_pane,
)
from node_runtime.supervisor.frontier_spawn import (  # noqa: E402
    ClaudeCliUnavailable,
    LiveTermsNotConfirmed,
)
from node_runtime.supervisor.subscription_governor import (  # noqa: E402
    SubscriptionGovernor,
    SubscriptionLimitExceeded,
    canonical_subscription_ref,
)

#: Pinned so the shell source can validate the shape it parses (a drifted producer is refused).
CONDUCTOR_SPAWN_FEED_SCHEMA = "conductor_spawn_feed@1.0"

# The conductor-first pane's governed identity (§12.4). Non-empty ⇒ never a naked session (inv 2/29).
CONDUCTOR_NODE_ID = "conductor-pane-1"
CONDUCTOR_PERMISSION_PROFILE = "pp-conductor-pane"
#: U76 (Phase 17A `.pty`): the ONE canonical ref — the launch ticket, the durable lease and
#: the always-visible status bar all count this subscription under the same spelling.
CONDUCTOR_SUBSCRIPTION_REF = canonical_subscription_ref(CLAUDE_CODE_ADAPTER)

# The governed refusals the fail-closed feed reports honestly instead of fabricating a spawn. Each is
# a gate working as designed (fail closed), not a bug: absent config / provider-not-live (raised as
# ProfileViolation by assert_startup or LiveAuthorizationError at the spawn site), unconfirmed R8
# terms, absent CLI, naked identity, or a full I-X3 count.
_GOVERNANCE_REFUSALS = (
    ProfileViolation,
    LiveAuthorizationError,
    LiveTermsNotConfirmed,
    ClaudeCliUnavailable,
    ConductorPaneRefused,
    SubscriptionLimitExceeded,
    ConductorProviderUnavailable,
)


def _governed_feed(session: Any) -> dict[str, Any]:
    """The governed-spawn feed built from a successful `ConductorPaneSession`, captured BEFORE
    teardown so the chrome's subscription view reflects the acquired terminal (`in_use: 1`)."""
    return {
        "schema": CONDUCTOR_SPAWN_FEED_SCHEMA,
        "spawned": True,
        "refused": False,
        "reason": None,
        "node_state": session.chrome.node_state,   # "awaiting_live_conductor" (no launcher) | "ready"
        "launched": bool(session.launched),
        "chrome": session.chrome.as_dict(),
        "launch": dict(session.launch),
        "selection_record": dict(session.selection_record),
        # filled after teardown (below) — the D-LOOP-1 facts
        "torn_down": False,
        "governor_released": False,
    }


def _refusal_feed(exc: Exception, *, live_authorized: bool, cli_present: bool) -> dict[str, Any]:
    """The fail-closed governed-REFUSAL feed. No chrome/launch — nothing was born; the shell renders
    the conductor pane as an honest un-governed-live placeholder with the reason, never a fabricated
    spawn (invariant 3 / invariant 20 spirit)."""
    return {
        "schema": CONDUCTOR_SPAWN_FEED_SCHEMA,
        "spawned": False,
        "refused": True,
        "reason": f"{type(exc).__name__}: {exc}",
        "node_state": "spawn_refused",
        "launched": False,
        "chrome": None,
        "launch": None,
        "selection_record": None,
        "torn_down": False,      # nothing acquired to tear down
        "governor_released": True,  # the count never left 0 (release-on-failure inside the spawn)
        "live_authorized": live_authorized,
        "cli_present": cli_present,
    }


def build_conductor_spawn_feed(
    *,
    live_auth: LiveAuthorization | None = None,
    governor: SubscriptionGovernor | None = None,
    profile_loader: ProfileLoader | None = None,
    selection: ConductorSelection = OPERATOR_SELECTED_CONDUCTOR,
    subscription_ref: str = CONDUCTOR_SUBSCRIPTION_REF,
    node_id: str = CONDUCTOR_NODE_ID,
    permission_profile_id: str = CONDUCTOR_PERMISSION_PROFILE,
    operator_terms_confirmed: bool = True,   # OP-9 recorded basis (invariant 1) — not a credential
    model: str | None = None,
    model_available: bool | None = None,
    cli_present: bool | None = None,         # None ⇒ real host detection (shutil.which("claude"))
    launcher: Callable[..., Any] | None = None,  # injected only by the mock-first "ready" proof
    descriptor: ConductorDescriptor | None = None,
) -> dict[str, Any]:
    """Run the governed conductor-pane spawn and return the shell feed, tearing the terminal down
    (D-LOOP-1) in a `finally` before returning.

    Defaults resolve the REAL repo authorization (`load_live_authorization()`), a fresh
    `SubscriptionGovernor`, and the cloud `ProfileLoader`. With no `launcher` the interactive `claude`
    ConPTY drive is deferred (operator-run §6) ⇒ `node_state: awaiting_live_conductor`; no live call is
    made. Any governed refusal ⇒ the fail-closed refusal feed (never a fabricated spawn)."""
    auth = live_auth if live_auth is not None else load_live_authorization()
    gov = governor if governor is not None else SubscriptionGovernor()
    loader = profile_loader if profile_loader is not None else ProfileLoader(DeploymentProfile("cloud"))
    provider = descriptor.adapter_id if descriptor is not None else CLAUDE_CODE_ADAPTER
    effective_ref = descriptor.subscription_ref if descriptor is not None else subscription_ref
    if descriptor is not None:
        selection = ConductorSelection(
            model=descriptor.model_id, reason="operator_selected",
            since="2026-08-02T00:00:00+00:00", adapter=descriptor.adapter_id,
            subscription_ref=descriptor.subscription_ref)
        permission_profile_id = descriptor.permission_profile_id
        model = descriptor.model_id
        model_available = True
    live_authorized = auth.is_provider_live(provider)

    session = None
    try:
        session = spawn_conductor_pane(
            mcp_client=object(),   # signature parity; not read (MCP attaches natively at .dispatch)
            governor=gov, subscription_ref=effective_ref, node_id=node_id,
            permission_profile_id=permission_profile_id, live_auth=auth, profile_loader=loader,
            operator_terms_confirmed=operator_terms_confirmed, model=model,
            model_available=model_available, selection=selection, cli_present=cli_present,
            launcher=launcher, descriptor=descriptor)
        feed = _governed_feed(session)
        feed["live_authorized"] = live_authorized
        # cli_present detected by the spawn when None: a governed spawn only reaches here if the CLI
        # gate passed (real path) or a launcher supplied its own session — report the effective fact.
        feed["cli_present"] = True if cli_present is None else bool(cli_present)
    except _GOVERNANCE_REFUSALS as exc:
        feed = _refusal_feed(exc, live_authorized=live_authorized,
                             cli_present=bool(cli_present) if cli_present is not None else False)
    finally:
        if session is not None:
            session.teardown()   # D-LOOP-1: close any handle + release the I-X3 terminal

    if feed["spawned"]:
        # teardown has run — record the D-LOOP-1 facts truthfully (the count is back to 0).
        feed["torn_down"] = True
        feed["governor_released"] = gov.active_count(effective_ref) == 0
    return feed


def main(argv: list[str]) -> int:
    """CLI: `--emit-conductor-spawn` prints the governed spawn feed as one JSON line and exits 0
    (a governed refusal is still a 0-exit feed the shell renders fail-closed). Any other invocation
    prints usage to stderr and exits 2 — the shell source treats a non-zero exit as "unavailable" and
    renders the honest un-governed-live conductor placeholder, never a fabricated spawn."""
    if "--emit-conductor-spawn" in argv:
        try:
            descriptor = load_runtime_conductor_descriptor()
        except ConductorRegistryError as exc:
            # LOCAL-ONLY fail-closed (invariant 20): no enumerated local conductor is a governed
            # REFUSAL feed the shell renders honestly (exit 0), never a traceback.
            sys.stdout.write(json.dumps(_refusal_feed(
                exc, live_authorized=False, cli_present=False), default=str) + "\n")
            return 0
        sys.stdout.write(json.dumps(build_conductor_spawn_feed(
            descriptor=descriptor), default=str) + "\n")
        return 0
    sys.stderr.write(
        "usage: emit_conductor_spawn.py --emit-conductor-spawn\n"
        "  prints the governed conductor_spawn_feed@1.0 JSON the shell renders (Phase 16C .spawn).\n"
    )
    return 2


if __name__ == "__main__":  # pragma: no cover - exercised via tests calling main()
    raise SystemExit(main(sys.argv[1:]))
