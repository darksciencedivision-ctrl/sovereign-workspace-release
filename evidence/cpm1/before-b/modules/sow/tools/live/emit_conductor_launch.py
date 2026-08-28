"""Governed CONDUCTOR **launch ticket** — Phase 17A `.lease` (directive §16 track 17A; OP-8 §13/OP-9).

The operator's first-use finding F3: conductor pane 1 sits at `awaiting_live_conductor` and typing
into it gets no answer. That state is honest — `emit_conductor_spawn` runs the full live-gate chain
but deliberately DEFERS the interactive `claude` drive and tears its I-X3 terminal down before
emitting, so the shell gets gates without a session. 17A ends the black pane, and the first thing it
needs is a shape the shell can actually *execute*:

  **a launch ticket** — an authorization decision made by the governed Python path (never by the
  shell), carrying the interactive argv, the NAMES of the credential-bearing env vars the shell must
  drop (§2.2 — names, never values), the CONDUCTOR chrome, and a **durable I-X3 lease that is still
  held when the ticket is emitted**, because the session it authorizes will outlive this emitter.

Why the lease had to become durable (`node_runtime/supervisor/terminal_lease`): every bounded emitter
in this build counts terminals in a fresh in-process `SubscriptionGovernor` and releases at teardown.
That was correct while nothing live outlived an emitter. A real interactive `claude` in the shell's
ConPTY does. Without a durable count the shell could hold two sessions while every emitter reported
0/2 — I-X3 would be decorative. So the ticket path:

  1. seeds an in-process governor from the DURABLE live leases (terminals held by the shell or by
     another tool become visible to this process's gate chain);
  2. runs `spawn_conductor_pane` — the identical gate chain 16C gated (live-operation authorization,
     provider-live, R8 §6 operator terms, `claude` presence, I-X3 acquire), with NO launcher;
  3. takes the DURABLE lease for the conductor node, owned by `--holder-pid` (the shell's pid);
  4. tears the in-process session down (the emitter's own D-LOOP-1 bookkeeping) — the durable lease
     is the ONLY thing that survives, it is named in the ticket, and `--release-lease` hands it back.

Fail-closed everywhere (invariant 3 / invariant 20 spirit): any gate refusal, a durable count already
at the allowance, or an unreadable ledger yields a REFUSAL ticket (`authorized:false`, `refused:true`,
`reason`, no argv, no lease) — never a fabricated authorization, never a leaked lease. A lease is
never taken without a real owner pid: `--holder-pid` is REQUIRED, because a lease owned by this
about-to-exit process would count a terminal nobody holds.

This emitter makes NO live model call and touches no credential: it builds argv and counts terminals.
The actual ConPTY launch is the shell's (`.pty`), and the type→answer round trip is `.roundtrip`.

Phase 17A `.pty` closed the three counting gaps `.lease` recorded as owed:

  * **U75** — the lease is keyed to the SESSION (`--session-id`), not to the constant conductor node
    id, so two real interactive sessions for pane 1 are two counted terminals;
  * **U76** — the durable count and the always-visible status bar now use the ONE
    `canonical_subscription_ref(provider)` spelling, so the bar cannot read 0/2 against a held lease;
  * **U77** — `--release-session` reclaims a lease by the key the SHELL chose before it asked, so a
    ticket whose delivery fails (shape refusal, timeout) does not strand a terminal.

Modes (a governed refusal is still a 0-exit JSON ticket; usage/argument errors exit 2 with no JSON):
  --emit-conductor-launch --holder-pid <pid> --session-id <id>   the launch ticket (or a refusal)
  --release-lease <lease_id>                   hand one durable terminal back
  --release-session <session_id>               hand back the terminal held by one session
  --emit-lease-status                          the observable durable n/allowance count
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Run as a script (`py -3.12 tools/live/emit_conductor_launch.py`) ⇒ Python puts the SCRIPT dir on
# sys.path, not the repo root. Bootstrap the root exactly as the sibling emitters do.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER  # noqa: E402
from adapters.conductor.provider_commands import (  # noqa: E402
    ConductorProviderUnavailable,
    commands_for,
    credential_scrub_names,
)
from control_plane.conductor.registry import (  # noqa: E402
    ConductorDescriptor,
    load_runtime_conductor_descriptor,
)
from adapters.frontier.claude_model_probe import (  # noqa: E402
    ModelProbeLedger,
    resolve_launch_model,
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
from node_runtime.supervisor.conductor_permission_profile import (  # noqa: E402
    PermissionProfileUnavailable,
    build_conductor_permission_profile,
)
from node_runtime.supervisor.frontier_spawn import (  # noqa: E402
    ClaudeCliUnavailable,
    LiveTermsNotConfirmed,
    _detect_cli,
)
from node_runtime.supervisor.subscription_governor import (  # noqa: E402
    SubscriptionGovernor,
    SubscriptionLimitExceeded,
    canonical_subscription_ref,
)
from node_runtime.supervisor.terminal_lease import (  # noqa: E402
    LeaseLedgerCorrupt,
    LeaseLedgerLocked,
    TerminalLeaseLedger,
)

#: Pinned so the shell source can validate the shape it parses (a drifted producer is refused).
LAUNCH_TICKET_SCHEMA = "conductor_launch_ticket@1.0"
LEASE_RELEASE_SCHEMA = "terminal_lease_release@1.0"
LEASE_STATUS_SCHEMA = "terminal_lease_status@1.0"

# The conductor-first pane's governed identity (§12.4) — shared with `emit_conductor_spawn` so the
# ticket and the 16C spawn feed describe the SAME node, not two conductors.
CONDUCTOR_NODE_ID = "conductor-pane-1"
CONDUCTOR_PERMISSION_PROFILE = "pp-conductor-pane"
#: U76: the ONE spelling every product path counts this subscription under (the status-bar feed
#: derives its ref from the same function), so a held terminal is visible in the always-on n/2 bar.
CONDUCTOR_SUBSCRIPTION_REF = canonical_subscription_ref(CLAUDE_CODE_ADAPTER)
CONDUCTOR_LEASE_PURPOSE = "conductor-pane-1 interactive session (OP-8 §13)"

#: The governed WORKSPACE the interactive conductor session is bound to (its ConPTY cwd). Part of
#: the containment U78(a) asked for: a session that inherits whatever directory the shell happened
#: to start in is not bound to anything. The repo root is this build's project workspace.
CONDUCTOR_WORKSPACE = str(ROOT)

# Governed refusals reported honestly instead of a fabricated authorization. Each is a gate working
# as designed: absent/narrow live config, unconfirmed R8 terms, absent CLI, naked identity, a full
# I-X3 count (in-process OR durable), or a ledger that cannot be trusted to say what is held.
_GOVERNANCE_REFUSALS = (
    ProfileViolation,
    LiveAuthorizationError,
    LiveTermsNotConfirmed,
    ClaudeCliUnavailable,
    ConductorPaneRefused,
    SubscriptionLimitExceeded,
    LeaseLedgerCorrupt,
    LeaseLedgerLocked,
    PermissionProfileUnavailable,
    ConductorProviderUnavailable,
)


def _default_ledger() -> TerminalLeaseLedger:
    """The host's durable ledger (patched in tests). Its file lives under `.sovereign_store/`
    (gitignored runtime state inside the repo root, §2.5), or wherever
    `SOW_TERMINAL_LEASE_LEDGER` points — the scratch-ledger override the in-runtime self-check uses
    so it never touches a lease the operator's own running conductor holds."""
    return TerminalLeaseLedger()


def _resolve_cli() -> str | None:
    """The resolved `claude` binary path, from the SAME authority that gates its presence."""
    from adapters import detect

    return detect.claude_code_executable()


def _env_scrub_names() -> list[str]:
    """The NAMES of the credential/endpoint-bearing vars the shell must remove from the child env
    before spawning the interactive session.

    §2.2 in the strictest reading: the ticket carries names, never values — the shell already holds
    its own environment, so a name is all it needs to drop one, and a value would be exactly the
    thing this build never transmits. `scrub_credential_env()` performs the same removal Python-side
    for Python-side spawns; this is its cross-process equivalent."""
    return credential_scrub_names()


def _apply_permission_profile(provider: str, argv: list[str], permission_profile_id: str
                              ) -> tuple[list[str], dict[str, Any]]:
    """Represent the same conductor profile through the selected provider's supported flags."""
    if provider == CLAUDE_CODE_ADAPTER:
        profile = build_conductor_permission_profile(permission_profile_id)
        return [*argv, "--settings", profile.settings_json], dict(profile.boundary)
    # Codex command construction already pins read-only + attended/untrusted approval.  Do not
    # fabricate Claude hooks for a provider that does not implement that hook protocol.
    return list(argv), {
        "schema": "conductor_permission_boundary@1.0",
        "provider": provider,
        "permission_profile_id": permission_profile_id,
        "supervisor_owned": True,
        "sandbox": "read-only",
        "approval_policy": "never",
        "automatic_approval": False,
        "unrestricted_tools": False,
    }


def _governor_holders(governor: SubscriptionGovernor, subscription_ref: str) -> list[str]:
    """The node ids currently holding an IN-PROCESS terminal on this subscription."""
    entry = governor.status().get(subscription_ref) or {}
    return list(entry.get("active") or [])


def _refusal_ticket(exc: Exception, *, gates: dict[str, bool]) -> dict[str, Any]:
    """Fail-closed REFUSAL: no argv, no chrome, no lease — the shell renders the honest reason and
    keeps the un-launched conductor placeholder (invariant 2: no naked session ever)."""
    return {
        "schema": LAUNCH_TICKET_SCHEMA,
        "authorized": False,
        "refused": True,
        "reason": f"{type(exc).__name__}: {exc}",
        "node_state": "launch_refused",
        "launch": None,
        "chrome": None,
        "selection_record": None,
        "identity": None,
        "authority_boundary": None,
        "containment": None,
        "lease": None,
        "release_with": None,
        # measured by the caller after teardown, never asserted here
        "governor_released": False,
        "gates": dict(gates),
    }


def build_conductor_launch_ticket(
    *,
    holder_pid: int,
    session_id: str = "",
    workspace: str = CONDUCTOR_WORKSPACE,
    ledger: TerminalLeaseLedger | None = None,
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
    probe_ledger: ModelProbeLedger | None = None,   # None ⇒ the host-local probe ledger
    cli_present: bool | None = None,         # None ⇒ real host detection
    descriptor: ConductorDescriptor | None = None,
) -> dict[str, Any]:
    """Run the governed gate chain and return the launch ticket the shell executes, or a refusal.

    `holder_pid` OWNS the durable lease: it must be the long-lived process that will hold the ConPTY
    session (the Electron main process), never this emitter. `session_id` is the identity of THAT
    session, chosen by the shell before it asks (U75/U77): the terminal is counted per session, and
    the shell can hand it back by key even if this ticket never reaches it."""
    # W-15/R-10: guarded in place rather than moved. `auth` is read by the gate record
    # below, before the main `try` opens, so moving the load would reorder the chain; what
    # matters is that a malformed config becomes a REFUSAL TICKET naming the
    # `live_operation` gate instead of a traceback with `refused_by: null`.
    try:
        auth = live_auth if live_auth is not None else load_live_authorization()
    except _GOVERNANCE_REFUSALS as exc:
        return _refusal_ticket(exc, gates={"live_operation_authorized": False,
                                           "operator_terms_confirmed": bool(operator_terms_confirmed),
                                           "cli_present": None, "ix3_counted": False})
    led = ledger if ledger is not None else _default_ledger()
    loader = profile_loader if profile_loader is not None else ProfileLoader(DeploymentProfile("cloud"))
    gov = governor if governor is not None else SubscriptionGovernor()
    desc = descriptor
    provider = desc.adapter_id if desc is not None else CLAUDE_CODE_ADAPTER
    provider_commands = commands_for(provider)
    if desc is not None:
        selection = ConductorSelection(
            model=desc.model_id, reason="operator_selected",
            since="2026-08-02T00:00:00+00:00", adapter=desc.adapter_id,
            subscription_ref=desc.subscription_ref)
        workspace = desc.workspace
        permission_profile_id = desc.permission_profile_id
        subscription_ref = desc.subscription_ref
        # W-11/A-1: a descriptor supplies a LABEL, not a probed fact. Assigning `model` and
        # `model_available` here made the ledger consult below -- guarded on both being None --
        # UNREACHABLE on the only path `main()` actually takes, because `main()` always passes
        # `descriptor=load_runtime_conductor_descriptor()`, and on any clone without the operator's
        # host switch that descriptor resolves `claude_code`/`fable-5`: the exact slug the ledger
        # records the CLI rejecting, and the slug 17A `.roundtrip` watched the CLI refuse.
        #
        # The condition is the DONOR's, not a new one: `emit_conductor_selection.py:84-91` has
        # always resolved a claude label through the ledger and reserved a directly-carried slug for
        # a provider that HAS no ledger. This emitter is the one that diverged. A caller that
        # supplied either value still wins over both, exactly as before.
        if provider != CLAUDE_CODE_ADAPTER and model is None and model_available is None:
            model = desc.model_id
            model_available = True
    resolved_executable = provider_commands.resolve_executable()

    # The gate record is OBSERVED, never assumed (invariant 27). In particular `cli_present` is
    # detected up front rather than being back-filled after a successful spawn: a refusal raised by
    # a LATER gate (I-X3) would otherwise report "CLI missing" when the CLI was found — an honest-
    # looking record that misdiagnoses the refusal for the operator.
    gates = {"live_operation_authorized": auth.is_provider_live(provider),
             "operator_terms_confirmed": bool(operator_terms_confirmed),
             "cli_present": bool(resolved_executable) if cli_present is None else bool(cli_present),
             "ix3_counted": False}

    # The `--model` slug the host CLI actually ACCEPTS, read OFFLINE from the probe ledger
    # (`tools/live/probe_conductor_model.py` spends the live call; this emitter never does — the
    # shell requests this ticket on a bounded timeout). Three honest states, all pre-existing
    # arguments of the gated spawn: accepted slug ⇒ ask for it; conclusively unavailable ⇒
    # `model_available=False`, which makes the binding record the CLI-default FALLBACK; unprobed or
    # inconclusive ⇒ nothing changes and the selection's own label is carried verbatim.
    #
    # WHY THIS EXISTS (17A `.roundtrip`): `.pty` launched the live session with the operator's
    # selection LABEL as its slug, and the CLI answered every prompt with "There's an issue with the
    # selected model (fable-5)". A live session that cannot answer is the black pane with extra steps.
    if provider == CLAUDE_CODE_ADAPTER and model is None and model_available is None:
        model_probe = resolve_launch_model(selection.model, ledger=probe_ledger)
        model = model_probe["model"]
        model_available = model_probe["model_available"]
    else:
        model_probe = {"label": selection.model, "model": model, "model_available": model_available,
                       "source": ("registered-exact-slug"
                                  if desc is not None and provider != CLAUDE_CODE_ADAPTER
                                  else "caller-supplied"),
                       "record": None}

    session = None
    lease = None
    try:
        # (a) the live gate FIRST — an unauthorized config has allowance 0, which is not a number the
        # governor can be seeded with; refusing here keeps the reason precise instead of a ValueError.
        auth.assert_provider_live(provider)
        allowance = auth.terminals_for(provider)
        # (b) project the DURABLE live leases into this process's governor, so the gate chain below
        # sees terminals held by the shell / other tools. This is the cross-process half of I-X3.
        seeded = led.seed_governor(gov, subscription_ref=subscription_ref,
                                   provider=provider, allowance=allowance)
        # (c) the identical governed spawn 16C gated — every gate, no launcher (the ConPTY drive is
        # the shell's, and it is authorized by this ticket, not performed here).
        session = spawn_conductor_pane(
            mcp_client=object(),   # signature parity; MCP attaches natively at the shell's session
            governor=gov, subscription_ref=subscription_ref, node_id=node_id,
            permission_profile_id=permission_profile_id, live_auth=auth, profile_loader=loader,
            operator_terms_confirmed=operator_terms_confirmed, model=model,
            model_available=model_available, selection=selection, cli_present=cli_present,
            launcher=None, descriptor=desc)
        # Apply the supervisor-issued profile to the actual child argv. Marked voice prompts arm a
        # deny-all tool boundary for that turn; ordinary physical typing retains the attended path.
        launch_argv, authority_boundary = _apply_permission_profile(
            provider, session.launch["argv"], permission_profile_id)
        # (d) the DURABLE lease — the count that will outlive this process, owned by the shell.
        lease = led.acquire(subscription_ref=subscription_ref, provider=provider,
                            node_id=node_id, allowance=allowance, holder_pid=int(holder_pid),
                            purpose=CONDUCTOR_LEASE_PURPOSE, session_id=str(session_id or ""))
        gates["ix3_counted"] = True
        ticket = {
            "schema": LAUNCH_TICKET_SCHEMA,
            "authorized": True,
            "refused": False,
            "reason": None,
            "node_state": "launch_authorized",
            "launch": {
                "argv": launch_argv,
                "interactive": True,
                "one_shot": False,
                "env_credential_scrubbed": True,
                # names only, never values (§2.2) — the shell drops these from its own environment
                "env_scrub_names": _env_scrub_names(),
                # The RESOLVED binary the presence gate actually found. A ConPTY spawn takes a file,
                # not a PATH search (`claude` is `claude.EXE` on this host — a bare name is simply
                # "File not found"), and resolving it HERE means the shell executes exactly the
                # binary the gate verified instead of re-resolving a name under a different PATH.
                # Falls back to argv[0] only when detection was injected (tests) — never invented.
                "executable": resolved_executable or session.launch["argv"][0],
                # The governed WORKSPACE the session is bound to: the shell spawns the ConPTY with
                # this as its cwd rather than inheriting whatever directory it started in (U78(a),
                # workspace-binding half). A shell that cannot honor it must refuse, not improvise.
                "cwd": str(workspace),
                "note": (f"interactive `{provider_commands.executable_name}` for the operator's "
                         "live CONDUCTOR chat pane; provider flags come from the registered adapter "
                         "and the shell uses the shared supervised pane-1 lifecycle."),
            },
            "chrome": session.chrome.as_dict(),
            "selection_record": dict(session.selection_record),
            "conductor_descriptor": desc.as_dict() if desc is not None else {
                "role": "conductor", "provider_id": provider, "adapter_id": provider,
                "model_id": selection.model, "display_name": selection.model,
                "permission_profile_id": permission_profile_id, "workspace": str(workspace),
                "subscription_ref": subscription_ref, "locality": "frontier",
                "registered": True, "conductor_capable": True,
            },
            # WHERE the slug in that argv came from — a recorded live observation, a recorded
            # fallback, or nothing at all. Surfaced so the shell/receipt can state it (never silent).
            "model_probe": dict(model_probe),
            # The governed identity the session must be spawned UNDER (invariant 2/29). The shell
            # cannot invent these: they come from the gated spawn.
            "identity": {
                "node_id": node_id,
                "permission_profile_id": permission_profile_id,
                "subscription_ref": subscription_ref,
                "session_id": str(session_id or ""),
                "workspace": str(workspace),
                "role": "conductor",
                "mode": "attended",
            },
            "authority_boundary": authority_boundary,
            # What this ticket does and does NOT establish — stated, not implied. A ticket is an
            # AUTHORIZATION plus a counted terminal; it is not containment. `chrome.governed:true`
            # describes that authorization provenance, NOT an enforced sandbox. Binding the spawned
            # process to the supervisor (session registration, workspace/cwd binding, job-object /
            # ACL containment per invariant 29, heartbeat) is the shell-side work of `.pty` and is
            # owed there — a renderer must not read this ticket as "the session is contained".
            "containment": {
                "authorized": True,
                # A ticket is never containment — it is an authorization plus a counted terminal.
                # The SHELL binds the process at spawn; `.pty` states WHAT it must bind so a
                # renderer (or a future caller) cannot read `chrome.governed:true` as "sandboxed".
                "supervisor_bound": False,
                "bound_by": ("shell supervised spawn — SessionManager.spawn refuses without an "
                             "admitted node (IpcSupervisor.admit over the verified control-plane "
                             "channel), reports the lifecycle, and kills every session on loss"),
                "requires": ["supervised_admission", "workspace_cwd_binding",
                             "credential_env_scrub", "permission_profile_binding",
                             "lease_release_on_session_exit"],
                # The per-turn permission profile is launch-bound. Kernel containment and heartbeat
                # remain separate owed work and stay named here.
                "still_owed": ["os_job_object_or_acl (U25)",
                               "node_heartbeat (U78(a))"],
                # Honest remainder (unchanged for EVERY shell session, not new to the conductor):
                # the pid→Windows-Job-Object handoff is the Node Runtime's and needs the IPC write
                # op the per-node credential broker gates.
                "os_job_object": False,
                "owed_to": "U25 (pid→job-object handoff needs the IPC write op; U78(b)-(d) → 17D)",
                "note": ("authorization + counted terminal + an applied per-turn permission profile; "
                         "supervisor session registration, workspace binding and credential scrubbing "
                         "are enforced by the shell's supervised spawn. OS job-object containment "
                         "remains the Node Runtime's U25 boundary."),
            },
            "lease": {
                **lease.as_dict(),
                "durable": True,
                "in_use": led.in_use(subscription_ref),
                "allowance": allowance,
                "seeded_from_ledger": [ln.node_id for ln in seeded],
            },
            "release_with": ["--release-lease", lease.lease_id],
            # the emitter's OWN in-process count is released below (D-LOOP-1); the durable lease is
            # the deliberate survivor and is named right above.
            "governor_released": False,
            "gates": dict(gates),
        }
    except _GOVERNANCE_REFUSALS as exc:
        ticket = _refusal_ticket(exc, gates=gates)
    finally:
        if session is not None:
            session.teardown()   # in-process governor released; the durable lease is untouched

    # Measured, not asserted — and measured on THIS node, not on the governor as a whole: the
    # governor was deliberately SEEDED with the durable leases other processes hold, so an empty
    # governor is not the question. The question is whether OUR in-process acquire was handed back.
    ticket["governor_released"] = node_id not in _governor_holders(gov, subscription_ref)
    return ticket


def build_lease_release(lease_id: str, *, ledger: TerminalLeaseLedger | None = None) -> dict[str, Any]:
    """Hand one durable terminal back. Idempotent: releasing an already-released lease reports
    `released:false` with NO error — the shell may call this from more than one teardown path."""
    led = ledger if ledger is not None else _default_ledger()
    out: dict[str, Any] = {"schema": LEASE_RELEASE_SCHEMA, "lease_id": lease_id,
                           "released": False, "error": None, "subscriptions": {}}
    try:
        out["released"] = led.release(lease_id)
        out["subscriptions"] = led.snapshot()
    except (LeaseLedgerCorrupt, LeaseLedgerLocked) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def build_lease_release_session(session_id: str, *, subscription_ref: str = CONDUCTOR_SUBSCRIPTION_REF,
                                ledger: TerminalLeaseLedger | None = None) -> dict[str, Any]:
    """Hand back the terminal held by ONE session (U77).

    The shell picks the session key before it requests a ticket, so this is the only reclaim path
    that works when the ticket itself never arrives (JS shape refusal, emitter timeout) and the
    lease id was therefore never learned. Idempotent: nothing to reclaim reports `released:0`."""
    led = ledger if ledger is not None else _default_ledger()
    out: dict[str, Any] = {"schema": LEASE_RELEASE_SCHEMA, "lease_id": None,
                           "session_id": session_id, "released": False, "released_count": 0,
                           "error": None, "subscriptions": {}}
    try:
        n = led.release_session(subscription_ref, session_id)
        out["released_count"] = n
        out["released"] = n > 0
        out["subscriptions"] = led.snapshot()
    except (LeaseLedgerCorrupt, LeaseLedgerLocked) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def build_lease_status(*, ledger: TerminalLeaseLedger | None = None,
                       live_auth: LiveAuthorization | None = None,
                       provider: str = CLAUDE_CODE_ADAPTER) -> dict[str, Any]:
    """The observable durable count (invariant 27): who holds what, and the authorized allowance.

    `allowance` is the CURRENTLY authorized one, which on a de-authorized host is 0 while leases may
    still be held by live processes — that combination is not a contradiction to hide but exactly
    what the operator needs to see (`authorized:false` + a non-zero `in_use` ⇒ terminals held under
    an authorization that has since been withdrawn). Never presented as a fresh grant."""
    led = ledger if ledger is not None else _default_ledger()
    # W-15/R-10: the lease STATUS surface reports faults in its own `error` field rather
    # than raising; a malformed live config is such a fault, not a crash.
    try:
        auth = live_auth if live_auth is not None else load_live_authorization()
    except LiveAuthorizationError as exc:
        return {"schema": LEASE_STATUS_SCHEMA, "allowance": 0, "authorized": False,
                "subscriptions": {}, "error": f"{type(exc).__name__}: {exc}"}
    out: dict[str, Any] = {"schema": LEASE_STATUS_SCHEMA,
                           # the conductor's own subscription allowance, per provider (OP-12 §12):
                           # the global number would overstate a 1-terminal subscription's ceiling
                           "allowance": auth.terminals_for(provider),
                           "authorized": auth.authorized,
                           "subscriptions": {}, "error": None}
    try:
        out["subscriptions"] = led.snapshot()
    except (LeaseLedgerCorrupt, LeaseLedgerLocked) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def _arg_after(argv: list[str], flag: str) -> str | None:
    try:
        i = argv.index(flag)
    except ValueError:
        return None
    return argv[i + 1] if i + 1 < len(argv) else None


def main(argv: list[str]) -> int:
    """CLI. Each mode prints exactly one JSON line and exits 0 (a governed refusal is still a
    0-exit ticket the shell renders fail-closed); usage/argument errors exit 2, which the shell
    source treats as "unavailable" — an honest un-launched conductor, never a fabricated launch."""
    if "--emit-conductor-launch" in argv:
        raw = _arg_after(argv, "--holder-pid")
        try:
            holder_pid = int(raw) if raw is not None else 0
        except ValueError:
            holder_pid = 0
        if holder_pid <= 0:
            sys.stderr.write(
                "--holder-pid <pid> is REQUIRED: the durable I-X3 lease must be owned by the "
                "long-lived process that will hold the session (the shell), never by this "
                "about-to-exit emitter — refuse to count a terminal nobody holds.\n")
            return 2
        session_id = _arg_after(argv, "--session-id")
        if not session_id:
            sys.stderr.write(
                "--session-id <id> is REQUIRED: a terminal is counted per SESSION, not per node "
                "(the conductor node id never changes, so node-keyed counting would report two "
                "real sessions as one — I-X3 defeated). The shell chooses the key before asking, "
                "so it can also hand the terminal back if this ticket never reaches it.\n")
            return 2
        sys.stdout.write(json.dumps(
            build_conductor_launch_ticket(holder_pid=holder_pid, session_id=session_id,
                                          descriptor=load_runtime_conductor_descriptor()),
            default=str) + "\n")
        return 0
    if "--release-session" in argv:
        session_id = _arg_after(argv, "--release-session")
        if not session_id:
            sys.stderr.write("--release-session <session_id> requires the session key to hand back\n")
            return 2
        desc = load_runtime_conductor_descriptor()
        released = build_lease_release_session(
            session_id, subscription_ref=desc.subscription_ref)
        # Compatibility/recovery: a selection may have changed after the shell chose the session
        # key but before an undelivered ticket was reclaimed. Try the other registered conductor
        # subscription rather than stranding its lease; release_session is idempotent.
        if not released["released"] and desc.subscription_ref != CONDUCTOR_SUBSCRIPTION_REF:
            released = build_lease_release_session(
                session_id, subscription_ref=CONDUCTOR_SUBSCRIPTION_REF)
        sys.stdout.write(json.dumps(released, default=str) + "\n")
        return 0
    if "--release-lease" in argv:
        lease_id = _arg_after(argv, "--release-lease")
        if not lease_id:
            sys.stderr.write("--release-lease <lease_id> requires the lease id to hand back\n")
            return 2
        sys.stdout.write(json.dumps(build_lease_release(lease_id), default=str) + "\n")
        return 0
    if "--emit-lease-status" in argv:
        sys.stdout.write(json.dumps(build_lease_status(
            provider=load_runtime_conductor_descriptor().adapter_id), default=str) + "\n")
        return 0
    sys.stderr.write(
        "usage: emit_conductor_launch.py --emit-conductor-launch --holder-pid <pid> "
        "--session-id <id>\n"
        "       emit_conductor_launch.py --release-lease <lease_id>\n"
        "       emit_conductor_launch.py --release-session <session_id>\n"
        "       emit_conductor_launch.py --emit-lease-status\n"
        "  the governed CONDUCTOR launch ticket the shell executes in pane 1's ConPTY, its durable\n"
        "  I-X3 lease, and the release/status modes (Phase 17A .lease).\n")
    return 2


if __name__ == "__main__":  # pragma: no cover - exercised via tests calling main()
    raise SystemExit(main(sys.argv[1:]))
