"""Governed WORKER **launch ticket** — Phase 17B `.ticket` (directive §16 track 17B; closes the
authorization half of U70).

17A gave pane 1 an executable authorization (`emit_conductor_launch`) and the operator's conductor
went live. A picker selection on any OTHER pane still produced nothing: 16B recorded the choice,
badged it, and stopped at `selected_awaiting_governed_spawn` — the operator's first-use finding F3
("selecting a model records + badges but launches nothing").

This emitter is the worker's equivalent of the conductor ticket. ONE picker selection in (on stdin,
verbatim from what the operator was shown), and out comes either

  * an **authorized ticket**: the interactive argv, the RESOLVED binary, the governed workspace, the
    NAMES of the credential-bearing env vars the shell must drop (§2.2 — names, never values), the
    node identity minted PYTHON-side, the pane chrome, and — for a frontier selection — a **durable
    I-X3 lease that is still held**, because the session it authorizes will outlive this emitter; or
  * a **fail-closed refusal ticket** (`authorized:false`, `refused:true`, `reason`, no argv, no
    lease) for every gate that said no: a greyed option, the conductor role, an unauthorized live
    config, unconfirmed R8 §6 terms, an absent CLI, a full durable I-X3 count, an unreadable ledger,
    a local model whose VRAM cannot be proven, or a selection this emitter cannot even parse.

Two localities, two different governors — deliberately, per invariant 19:

  * **frontier** (every id in `FRONTIER_PANE_ADAPTERS`: `claude_code`, `openai_codex_cli`, and
    since OP-12 the pair `grok_build` + `google_antigravity`) is
    subscription-governed: the durable ledger is seeded into this process's `SubscriptionGovernor`
    so terminals held by the shell are visible here, the gate chain runs, and the lease is taken for
    the SESSION key the shell chose before it asked (U75/U77 — reclaimable even if this ticket never
    arrives). The `--model` slug is read OFFLINE from the 17A probe ledger, so a worker asks for the
    id the CLI actually accepts rather than the operator's label (the `.roundtrip` defect).
  * **local** (`ollama_local`) holds NO subscription terminal and needs NO credential. What governs
    it is VRAM residency (invariant 22): the selection routes through the same host planner the
    picker's residency chips came from, and a model whose footprint cannot be proven is refused.

This emitter makes NO live model call and touches no credential: it builds argv, counts terminals and
reserves VRAM. The ConPTY launch is the shell's, under this authorization (`.spawn`).

Modes (a governed refusal is still a 0-exit JSON ticket; usage errors exit 2 with no JSON):
  --emit-worker-launch --holder-pid <pid> --session-id <id> --pane-id <pane>   (selection on stdin)
  --release-session <session_id>        hand back the terminal held by one session, any subscription
  --release-lease <lease_id>            hand one durable terminal back by id

Disclosed side effects of --emit-worker-launch (W-76 - disclosure only, nothing here changed):
  * a FRONTIER selection TAKES A TERMINAL: a durable I-X3 lease that outlives this process
    (hand it back with --release-session or --release-lease);
  * the governed launch WRITES A DURABLE NODE RECORD under `.sovereign_store/`; node records
    are never deletable - they are closed by transition, never removed;
  * `operator_terms_confirmed=True` is ASSERTED AT THE CALL SITE citing recorded rulings
    OP-9/OP-12 - a code literal citing a ruling, never measured from the operator here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Run as a script ⇒ Python puts the SCRIPT dir on sys.path, not the repo root. Bootstrap the root
# exactly as the sibling emitters do.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER  # noqa: E402
from adapters.frontier.claude_model_probe import (  # noqa: E402
    ModelProbeLedger,
    resolve_launch_model,
)
from adapters.frontier.antigravity import ANTIGRAVITY_ADAPTER  # noqa: E402
from adapters.frontier.codex import CODEX_ADAPTER  # noqa: E402
from adapters.frontier.grok_build import GROK_ADAPTER  # noqa: E402
from control_plane.profiles.live_authorization import (  # noqa: E402
    LiveAuthorization,
    LiveAuthorizationError,
    load_live_authorization,
)
# `DeploymentProfile` is deliberately NOT imported here any more: this module has no business
# constructing one. Which profile is in force is the host's fact and arrives as a required
# `ProfileLoader` keyword (U283/U292(a)) — an unused import is how the manufactured `cloud` loader
# would come back without anyone noticing.
from control_plane.profiles.loader import (  # noqa: E402
    ProfileLoader,
    ProfileViolation,
)
from node_runtime.supervisor.codex_spawn import CodexCliUnavailable  # noqa: E402
from node_runtime.supervisor.frontier_spawn import (  # noqa: E402
    ClaudeCliUnavailable,
    LiveTermsNotConfirmed,
)
from control_plane.nodes.registry import RegistrationRefused  # noqa: E402
from control_plane.nodes.states import IllegalTransition  # noqa: E402
from node_runtime.supervisor.pane_node_spawn import PaneSelection, SpawnRefused  # noqa: E402
from node_runtime.supervisor.provider_node_registration import (  # noqa: E402
    REGISTRABLE_PROVIDERS,
    ProviderNodeRegistrationRefused,
    default_provider_node_registrar,
)
#: The ONE implementation of "which deployment profile is this host running under" (U283). Imported
#: rather than re-derived so the probe path and the pane path cannot answer it differently.
from node_runtime.supervisor.provider_probe_session import (  # noqa: E402
    profile_loader_from_host,
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
from node_runtime.supervisor.worker_pane_spawn import (  # noqa: E402
    FRONTIER_PANE_ADAPTERS,
    WorkerPaneRefused,
    authorize_worker_pane,
    worker_identity,
)
from scheduler.residency_planner.residency_planner import ResidencyPlanner  # noqa: E402

#: Pinned so the shell source can validate the shape it parses (a drifted producer is refused).
WORKER_TICKET_SCHEMA = "worker_launch_ticket@1.0"
LEASE_RELEASE_SCHEMA = "terminal_lease_release@1.0"
#: The shell's post-spawn attestation payload (18E `.live.electron.wiring`).
PANE_ATTESTATION_SCHEMA = "worker_pane_spawn_attestation@1.0"

#: The frontier adapters whose supervised PANES this build registers as Sovereign nodes. The two
#: OP-12 providers and no others: `node@1.1` is the vocabulary OP-12.1 authorized, and
#: `provider_node_registration` derives its record facts from those two adapters' own backends.
#: Registering `claude_code`/`openai_codex_cli` panes would mean changing behaviour OP-12 listed as
#: untouchable, so it is an OWED leg named in every ticket that does not get a record, never a
#: silent omission. DERIVED from the module that can actually build a record, never re-spelled here
#: — a second literal is how a provider lands in one list and not the other (the U254 shape).
_OP12_PANE_NODE_ADAPTERS = REGISTRABLE_PROVIDERS

#: The governed WORKSPACE a worker pane's session is bound to (its ConPTY cwd). Same binding the
#: conductor ticket makes: a session that inherits whatever directory the shell started in is bound
#: to nothing (U78(a)).
WORKER_WORKSPACE = str(ROOT)

#: Read from the pane authorization itself, never re-listed here: `worker_pane_spawn` decides which
#: frontier adapters can be authorized for a pane, and this emitter's job is to run THAT chain. A
#: second literal is how "the emitter counted a terminal for a provider the authorizer refuses"
#: (or the reverse) begins — and after OP-12 the set is four, so the copy would have been wrong the
#: day it was written.
_FRONTIER_ADAPTERS = FRONTIER_PANE_ADAPTERS
#: Sentinel node id for a refusal raised before an identity existed — it can never be a governor
#: holder, so the release measurement stays honest instead of defaulting to "released".
_NO_NODE = "(no node)"
_WORKER_LEASE_PURPOSE = "worker pane interactive session (OP-7 §12.2 picker spawn)"
#: gate id for the check that verifies the caller's option against the HOST's own enumeration.
#: Deliberately DISTINCT from the selection guard: an enumeration fault must never be readable as
#: evidence that a downstream gate fired (gate-validator BLOCKING-1c).
_GATE_HOST_ENUMERATION = "host_enumeration"
#: The shell's env-var-NAME payload (U105) is its own gate. A bare `SpawnRefused` made every
#: malformed-names refusal report the class default `selection_guard`, so a receipt leg asserting
#: that id to prove the SELECTION guard fired would go green on an env-payload fault too — the
#: cross-gate id borrowing the ids exist to stop (spec-audit MINOR-9, 2026-07-26).
_GATE_SHELL_ENV_NAMES = "shell_env_names"

# Governed refusals reported honestly instead of a fabricated authorization. Each is a gate working
# as designed — selection, identity/locality, roster/air-gap, live config, R8 terms, CLI presence,
# I-X3 (in-process OR durable), residency, or a ledger that cannot be trusted to say what is held.
_GOVERNANCE_REFUSALS = (
    SpawnRefused,
    # the argv builders' own fail-closed guards (an empty/flag-like model tag, a write sandbox with
    # no worktree) raise ValueError; without it here the emitter would crash with a traceback and
    # the shell would report "unavailable" having lost the actual reason (spec-audit MINOR-8).
    ValueError,
    WorkerPaneRefused,
    ProfileViolation,
    LiveAuthorizationError,
    LiveTermsNotConfirmed,
    ClaudeCliUnavailable,
    CodexCliUnavailable,
    SubscriptionLimitExceeded,
    LeaseLedgerCorrupt,
    LeaseLedgerLocked,
    # A pane whose node record cannot be written is a pane that must not open: invariant 2 says
    # every terminal is a Sovereign node, so a refusal here refuses the SESSION and the durable
    # terminal is handed back on the way out (18D `.close`'s rule, now on the pane path).
    ProviderNodeRegistrationRefused,
    RegistrationRefused,
)


def _default_ledger() -> TerminalLeaseLedger:
    """The host's durable lease ledger (or wherever `SOW_TERMINAL_LEASE_LEDGER` points — the
    scratch-ledger override the in-runtime self-check uses so it never touches a lease the
    operator's own running sessions hold)."""
    return TerminalLeaseLedger()


def _host_planner() -> tuple[ResidencyPlanner | None, dict[str, Any]]:
    """The REAL host residency planner the picker's chips came from, WITH the provenance of the VRAM
    budget it enforces (`None` planner ⇒ daemon unreachable). The budget travels with it so the
    ticket can disclose an authorization made against a stand-in (gate-validator R2)."""
    from tools.live.enumerate_pane_picker import host_residency_planner

    return host_residency_planner()


#: exception class → the gate id to report when the exception carries none of its own. Every class in
#: `_GOVERNANCE_REFUSALS` appears, so a refusal is never `unclassified` in practice; the fallback exists
#: so a NEW refusal class can only ever under-claim.
_EXCEPTION_GATE = {
    "ProfileViolation": "profile_roster",       # roster eligibility / air-gap (invariant 20)
    "LiveAuthorizationError": "live_operation",  # LIVE_OPERATION_AUTHORIZED, fail-closed by absence
    "LiveTermsNotConfirmed": "operator_terms",  # R8 §6 [OPERATOR] (OP-9)
    "ClaudeCliUnavailable": "cli_present",
    "CodexCliUnavailable": "cli_present",
    "SubscriptionLimitExceeded": "ix3_allowance",
    "LeaseLedgerCorrupt": "lease_ledger",
    "LeaseLedgerLocked": "lease_ledger",
    "ValueError": "argv_builder",
    # The registry's own fence (an adapter no node schema version admits, a duplicate incarnation).
    # `ProviderNodeRegistrationRefused` carries its own `gate` and is read from the exception above.
    "RegistrationRefused": "node_registration",
}


def _gate_id(exc: BaseException) -> str:
    """WHICH gate refused, machine-readably. Taken from the exception's own `gate` where it sets one
    (`SpawnRefused`, `WorkerPaneRefused` — the two classes that cover several distinct checks each),
    else from the class.

    Why the ticket carries this at all: a receipt leg that proves "the invariant-22 admission gate
    refuses an over-budget pane" by regex-matching /VRAM/ over the reason accepts ANY refusal whose
    prose happens to contain the word — on 2026-07-26 an enumeration crash did exactly that and the
    leg went green while proving nothing about invariant 22. An id cannot be borrowed."""
    gate = getattr(exc, "gate", None)
    if isinstance(gate, str) and gate:
        return gate
    return _EXCEPTION_GATE.get(type(exc).__name__, "unclassified")


def _refusal(reason: str, *, gates: dict[str, Any], refused_by: str = "unclassified",
             node_registration: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fail-closed REFUSAL: no argv, no chrome, no lease — the shell renders the honest reason and
    the pane stays un-launched (invariant 2: no naked session, ever). `refused_by` names the gate."""
    return {
        "schema": WORKER_TICKET_SCHEMA,
        "authorized": False,
        "refused": True,
        "reason": reason,
        "refused_by": refused_by,
        "node_state": "launch_refused",
        "launch": None,
        "chrome": None,
        "identity": None,
        "containment": None,
        "lease": None,
        "residency": None,
        "model_probe": None,
        "subscription_governed": False,
        "release_with": None,
        "governor_released": True,     # nothing was acquired in-process, so nothing leaked
        # Present-and-negative rather than absent, for the same reason every other field on this
        # shape is: the two producers of `worker_launch_ticket@1.0` must publish one shape, or a
        # consumer reading `undefined` cannot tell a missing field from a measured negative.
        #
        # …and PASSED IN, not asserted. The first cut published "no session was authorized, so no
        # Sovereign node record exists for this attempt" unconditionally — a declaration on a
        # payload whose whole design principle is measurement, and a false one on the branch where
        # a governance refusal lands AFTER the record was written (validator MINOR-3 / spec-audit
        # MINOR-7). The caller now hands over what it MEASURED, including the outcome of closing a
        # record it had already created.
        "node_registration": node_registration if node_registration is not None
        else _no_pane_node_record(
            "no session was authorized, so no Sovereign node record exists for this attempt"),
        "gates": dict(gates),
    }


#: The option fields that must match the host enumeration for a selection to be honoured. Chosen as
#: the GOVERNANCE-bearing ones (which provider, which model, what locality, and whether the operator
#: was shown it as available) — not display text, which may legitimately be reworded.
_OPTION_IDENTITY_FIELDS = ("provider", "adapter", "locality", "model_slug", "available")


#: The providers whose enumeration costs an OUTBOUND metadata call. `grok models` reaches grok.com
#: to report the session (D-P18-7 / U271); `agy models` likewise leaves the host. Named here because
#: this module decides, per selection, whether that cost is owed at all.
_OP12_PROVIDERS = (GROK_ADAPTER, ANTIGRAVITY_ADAPTER)


def _host_offered_options(*, provider: str | None = None,
                          op12_probes: Any = None) -> list[dict[str, Any]]:
    """The options the host enumeration ACTUALLY offers right now (the same authority the picker
    drawer renders). Raises `SpawnRefused` if the host cannot be enumerated — an authorization that
    cannot check its input fails closed.

    **Scoped to the selected provider (validator MAJOR-3).** Until the 18B close this called
    `build_host_picker()` bare, which probes BOTH OP-12 CLIs unconditionally — so selecting a local
    `qwen3:8b` pane, with no subscription and no credential, emitted a metadata request to grok.com
    under the operator's SuperGrok session before the pane opened. D-P18-7 disclosed that cost for
    the PICKER site, where the operator has asked to see every provider; it was never disclosed for
    the launch path, and on a local selection it is not merely undisclosed, it is unowed
    (invariants 19/20 — locality is per node, and an offline-profile pane should not reach the
    network to be verified). A selection that is not for an OP-12 provider now verifies against an
    enumeration built with `no_op12_probes()`: the OP-12 groups render as not-probed, which cannot
    affect the match, because an option's identity carries its own provider.

    **And the seam is now threaded (validator MAJOR-2).** `op12_probes` is the same host-free seam
    `build_host_picker`/`enumerate_pane_picker.main` already published; it stopped at this caller,
    so a deterministic test that reached `main()` fired a real `grok --version` against the host —
    which `tests/live_call_guard` then refused at `grok models`, turning the one test covering the
    CLI contract into a test of its refusal branch. D-P18-5 claimed the suite never makes these
    calls; it does not now."""
    from tools.live.enumerate_pane_picker import (
        build_host_picker,
        no_op12_probes,
        only_op12_probe,
    )

    if op12_probes is None:
        # An OP-12 selection still pays for a REAL listing — but only for ITS OWN provider. Asking
        # for both meant authorizing a Gemini pane emitted `grok --version`/`grok models` to
        # grok.com under the operator's SuperGrok session (and vice versa): the cross-provider half
        # of the same egress U276 closed here for a LOCAL selection, left open between the two
        # frontier providers, and the reason the 18C receipt's cost disclosure was wrong
        # (spec-audit MAJOR-1, U290).
        op12_probes = (no_op12_probes() if provider not in _OP12_PROVIDERS
                       else only_op12_probe(provider))
    try:
        picker, _meta = build_host_picker(op12_probes=op12_probes)
    except Exception as exc:   # noqa: BLE001 - any enumeration fault is a refusal, never a bypass
        raise SpawnRefused(
            f"could not enumerate this host's offered models to verify the selection ({exc}) - "
            f"fail closed: an authorization is never granted against an unverifiable offer",
            gate=_GATE_HOST_ENUMERATION) from exc
    return list(picker.get("options") or [])


def _assert_option_offered(option: dict[str, Any], role: str,
                           offered: list[dict[str, Any]] | None,
                           op12_probes: Any = None) -> dict[str, Any]:
    """Verify the caller's option against the HOST's own enumeration (fail closed).

    The selection arrives on stdin from the shell, which got it from the renderer — so `available`
    and `roles`, the two fields the shared guard gates on, are caller-supplied. Verifying them
    against the live enumeration is what makes "carried verbatim from what the operator was shown" a
    CHECKED fact rather than a hope: a forged `available:true` on a greyed option, or a role no
    descriptor offered (I-SC1), is refused here before any gate runs.

    Returns the HOST's own version of the option, which is what every downstream gate and the chrome
    then use: matching on identity alone still let the caller supply the honesty-bearing fields
    (`verified`, `label`), so a forged `verified:true` reached the pane badge and contradicted
    invariant 3 (validator FINDING 3 / V-2). The caller chooses WHICH option; the host says what it
    IS.

    `offered=None` ⇒ enumerate the host (the product path), scoped to the selection's own provider
    so a non-OP-12 selection pays for no OP-12 metadata call. Tests inject a list, or inject
    `op12_probes` to keep the enumeration host-free while still exercising it."""
    options = (_host_offered_options(provider=option.get("provider"), op12_probes=op12_probes)
               if offered is None else list(offered))
    ident = {k: option.get(k) for k in _OPTION_IDENTITY_FIELDS}
    matches = [o for o in options if all(o.get(k) == v for k, v in ident.items())]
    if len(matches) > 1:
        # The identity fields are assumed to KEY an option; taking the first match silently binds one
        # of several to the badge. True on today's roster (every candidate slug is distinct, one
        # `None`-slug CLI-default per provider) but nothing asserted it, so a future provider whose
        # two labels resolve to one slug would attach the wrong `label`/`verified` to the pane
        # (spec-audit MINOR-6). Ambiguity is refused, not resolved by ordering.
        raise SpawnRefused(
            f"the selected option {option.get('provider')}/{option.get('model_slug')!r} matches "
            f"{len(matches)} distinct options this host offers ({[o.get('label') for o in matches]})"
            f" - refuse to bind an ambiguous selection to one of them (fail closed)",
            gate=_GATE_HOST_ENUMERATION)
    match = matches[0] if matches else None
    if match is None:
        raise SpawnRefused(
            f"the selected option {option.get('provider')}/{option.get('label')} "
            f"(slug {option.get('model_slug')!r}, available={option.get('available')}) is not one "
            f"this host currently offers on those terms - refuse to authorize a selection the host "
            f"enumeration does not presently back (fail closed; re-open the picker to refresh it). "
            f"NOTE: `available` is part of the identity, so a model the operator WAS shown, greyed, "
            f"lands here too - the picker's reason for greying it is the answer they need "
            f"(validator MINOR-5)",
            gate=_GATE_HOST_ENUMERATION)
    if role not in (match.get("roles") or []):
        raise SpawnRefused(
            f"role {role!r} is not offered by the HOST descriptor for "
            f"{match.get('provider')}/{match.get('label')} (offered: {list(match.get('roles') or [])})"
            f" - the role must be one the descriptor offered, never one the caller claimed (I-SC1)",
            gate=_GATE_HOST_ENUMERATION)
    return dict(match)


#: Bounds on the env var NAMES a shell may report holding (U105). Names are cheap to classify, but
#: an unbounded list from a caller is still an unbounded list: a real Windows environment is a few
#: hundred vars, and a name longer than this is not one the shell could have set.
_MAX_SHELL_ENV_NAMES = 4096
_MAX_ENV_NAME_LEN = 256


def _parse_shell_env_names(raw: Any) -> list[str]:
    """The env var NAMES the consuming shell holds — names ONLY, bounded, or a refusal (U105).

    Why the shell sends them at all: the scrub list was classified in THIS process's environment and
    then applied to the shell's, which is sound only while the two match — and a per-child `opts.env`
    (which 17B's own self-check uses) makes them diverge. Unioning the shell's names in before
    classification means a credential var only the shell holds, or one it spells with a different
    case than this process does, is still named in the list the shell deletes by.

    §2.2 tripwire: an entry containing `=` is a `name=value` pair, i.e. a VALUE being pushed at this
    emitter. Refused outright rather than split — this path takes names, and a caller that sends
    anything else is not one to accept a corrected reading from."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SpawnRefused(
            "selection.shell_env_names must be a JSON array of env var NAMES (§2.2: names, never "
            "values) — fail closed", gate=_GATE_SHELL_ENV_NAMES)
    if len(raw) > _MAX_SHELL_ENV_NAMES:
        raise SpawnRefused(
            f"selection.shell_env_names carries {len(raw)} entries (max {_MAX_SHELL_ENV_NAMES}) — "
            f"fail closed rather than classify an unbounded caller-supplied list",
            gate=_GATE_SHELL_ENV_NAMES)
    names: list[str] = []
    for entry in raw:
        if not isinstance(entry, str) or not entry:
            raise SpawnRefused(
                f"selection.shell_env_names carries a non-string entry ({type(entry).__name__}) — "
                f"fail closed", gate=_GATE_SHELL_ENV_NAMES)
        if "=" in entry:
            raise SpawnRefused(
                "selection.shell_env_names carries a `name=value` pair — this path takes env var "
                "NAMES only and never a value (§2.2, fail closed)", gate=_GATE_SHELL_ENV_NAMES)
        if len(entry) > _MAX_ENV_NAME_LEN:
            raise SpawnRefused(
                f"selection.shell_env_names carries a {len(entry)}-character entry (max "
                f"{_MAX_ENV_NAME_LEN}) — fail closed", gate=_GATE_SHELL_ENV_NAMES)
        names.append(entry)
    return names


def _parse_selection(selection: Any) -> tuple[dict[str, Any], str, str, list[str]]:
    """Validate the shell's selection payload into (option, role, mode, shell_env_names).

    Raises `SpawnRefused`. The option dict is carried VERBATIM from what the operator was shown (16B
    renders exactly the host enumeration), so the authorization can never disagree with the offer."""
    if not isinstance(selection, dict):
        raise SpawnRefused("selection must be a JSON object {option, role, mode} — fail closed")
    option = selection.get("option")
    if not isinstance(option, dict):
        raise SpawnRefused("selection carries no picker option dict — fail closed")
    role = selection.get("role")
    mode = selection.get("mode")
    if not isinstance(role, str) or not role:
        raise SpawnRefused("selection carries no role — a role is never inferred (I-SC1)")
    if not isinstance(mode, str) or not mode:
        raise SpawnRefused("selection carries no pane mode — expected attended|autonomous")
    return option, role, mode, _parse_shell_env_names(selection.get("shell_env_names"))


def _assert_profile_permits_verifying(option: dict[str, Any], loader: ProfileLoader) -> None:
    """Invariant 20 consulted BEFORE the host enumeration, not only after it (spec-audit F2, U303).

    The air-gap gate proper lives downstream in `worker_pane_spawn.assert_startup`, and it refuses
    every frontier adapter on an offline profile. But `_assert_option_offered` runs FIRST, and for
    an OP-12 selection it enumerates through `only_op12_probe(provider)` — `grok models` / `agy
    models`, which leave the host (D-P18-7/U271). So an air-gapped host emitted provider metadata
    traffic and THEN refused the pane. The verdict was right and the ordering was not, which for
    invariant 20 is the whole point: "excluded from the offline profile" has to mean the network was
    never touched, not that the answer came back no. Closing the parameter default made this
    reachable at all — before it, the manufactured `cloud` loader meant the gate never fired here.

    Refusing on the CALLER's claimed adapter is sound because it can only refuse MORE: the claim is
    already what scopes the probe (`_host_offered_options(provider=...)`), a lie about it cannot
    produce an authorization (the identity match downstream still has to succeed against the host's
    own enumeration), and the real gate still runs on the HOST's option for everything that gets
    past here. `ProfileViolation` is raised rather than a new refusal id because this IS that gate —
    `_EXCEPTION_GATE` maps it to `profile_roster` either way, so a reader cannot tell the two sites
    apart, and should not have to."""
    if not loader.profile.is_airgapped:
        return
    claimed = option.get("adapter")
    if claimed in _FRONTIER_ADAPTERS:
        raise ProfileViolation(
            f"adapter {claimed!r} is a subscription-backed frontier adapter and is excluded from "
            f"the offline/air-gapped profile (invariant 20) — refused BEFORE this host's model "
            f"enumeration ran, so no provider metadata call was made to verify a pane that could "
            f"never open")


def _no_pane_node_record(reason: str, *, log_path: str | None = None) -> dict[str, Any]:
    """The honest "no record, and here is why" shape.

    Every branch that does not write a node record publishes this rather than omitting the field:
    a consumer reading `undefined` cannot tell "no record was written" from "nobody looked", and
    the difference is the whole point of the measurement (18D's `node_registered` was a hardcoded
    `False` for exactly one release too long).

    `log_path` is the log the answer is ABOUT. `SOW_NODE_EVENT_LOG` can redirect the durable node
    log, so a payload saying `registered:true` without naming the file is a claim that could be
    about a scratch file in %TEMP% — which is exactly the 18D `real_switch` defect, one layer out
    (spec-audit MEDIUM-3). The registrar reports its path WITHOUT opening the file, so naming it
    costs nothing and every 18E payload now does."""
    return {"registered": False, "node_key": None, "incarnation": None, "schema_version": None,
            "node_id": None, "log_path": log_path, "reason": reason}


def _register_pane_node(registrar: Any, session: Any, *, session_id: str, lease_id: str,
                        adapter_id: str) -> dict[str, Any]:
    """Register one authorized frontier pane as a Sovereign node, or say precisely why not.

    Three outcomes, and they are three different facts:
      * a registrar and an OP-12 adapter ⇒ a record, MEASURED from what the registrar returned;
      * a registrar and a non-OP-12 adapter (`claude_code` / `openai_codex_cli`) ⇒ no record, with
        the scope named. Those two providers' panes predate this wiring and registering them would
        mean writing records for sessions whose behaviour OP-12 declared untouchable — recorded as
        owed rather than done quietly;
      * no registrar ⇒ no record, with that named too.

    A refusal PROPAGATES: it is a `ProviderNodeRegistrationRefused`, which is a governance refusal,
    so the ticket becomes a refusal ticket and the durable terminal is handed back."""
    if registrar is None:
        return _no_pane_node_record(
            "no registrar was supplied to build_worker_launch_ticket, so no node record was "
            "written or looked for (the caller's fact, stated rather than defaulted)")
    log_path = str(registrar.log_path)
    if adapter_id not in _OP12_PANE_NODE_ADAPTERS:
        return _no_pane_node_record(
            f"{adapter_id} panes are outside the OP-12 node-registration wiring: this build "
            f"registers {'/'.join(sorted(_OP12_PANE_NODE_ADAPTERS))} pane sessions (directive "
            f"§17.2(1)). The OP-6 providers' panes hold a durable I-X3 terminal and no node "
            f"record — an owed leg (U313), named here rather than papered over",
            log_path=log_path)
    out = registrar.register_pane_session(session, session_id=session_id, lease_id=lease_id)
    return {"registered": True, "node_key": out.node_key, "incarnation": out.incarnation,
            "schema_version": out.validated_against, "node_id": out.record.get("node_id"),
            "log_path": log_path,
            "adapter_admitted_by": out.adapter_schema_version, "reason": None}


def build_worker_pane_spawn_attestation(node_key: str, *, session_id: str, pid: int,
                                        registrar: Any) -> dict[str, Any]:
    """The shell saw its supervised ConPTY come up: move that pane's node record to READY.

    `session_id` is REQUIRED and is not decoration: a pane id is reused across sessions, so an
    attestation keyed on the pane alone could put a live pid onto a stale record left open by a
    crashed shell — see `ProviderNodeRegistrar._adopt_for_session`.

    NEVER raises — the shell calls this immediately after a successful spawn, and a bookkeeping
    fault must not tear down a live governed session that is already running correctly. The
    outcome is reported instead, so a receipt can tell an attested record from an unattested one
    rather than inferring it from silence."""
    out: dict[str, Any] = {"schema": PANE_ATTESTATION_SCHEMA, "node_key": node_key, "pid": pid,
                           "session_id": session_id, "attested": False, "incarnation": None,
                           "state": None,
                           "log_path": str(registrar.log_path) if registrar is not None else None,
                           "error": None}
    if registrar is None:
        out["error"] = "no registrar supplied — nothing to attest against"
        return out
    try:
        out.update(registrar.attest_spawned(node_key, session_id=session_id, pid=pid))
    except (ProviderNodeRegistrationRefused, RegistrationRefused, IllegalTransition, OSError,
            ValueError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            registrar.close()
        except Exception:      # noqa: BLE001 — a close that fails must not mask the result
            pass
    return out


def build_worker_launch_ticket(
    *,
    holder_pid: int,
    session_id: str,
    pane_id: str,
    selection: Any,
    # REQUIRED, both of them, and required for the same reason `governed_probe_session` requires
    # them (U283, closed there at 18C `.probe-path`; this is the same pair on the pane/worker
    # emitter, which U292(a) carried forward and directive §17.2(3) sends here). Their inputs come
    # from OUTSIDE this module: which deployment profile is in force is the HOST's fact, and
    # whether the subscription terms permit a supervised CLI call is the OPERATOR's (invariant 1).
    # A default made this module answer both — `ProfileLoader(DeploymentProfile("cloud"))` made
    # invariant 20's air-gap branch structurally unreachable on the product path, and
    # `operator_terms_confirmed=True` published a gate no caller had measured. `main()` supplies
    # both, each with its authorizing artifact named at the call site.
    profile_loader: ProfileLoader,
    operator_terms_confirmed: bool,
    # REQUIRED for the third time, and for the third version of the same reason (U283 / U292(a),
    # and now 18E): whether a governed session becomes a Sovereign NODE is the caller's fact, not
    # this module's. `None` is legitimate and means exactly "no record" — reported in the ticket
    # with its reason, never a silent skip. 18D made `registrar` a required keyword of
    # `governed_probe_session` on the probe path; this is the same keyword on the pane path.
    registrar: Any,
    workspace: str = WORKER_WORKSPACE,
    ledger: TerminalLeaseLedger | None = None,
    live_auth: LiveAuthorization | None = None,
    governor: SubscriptionGovernor | None = None,
    residency_planner: ResidencyPlanner | None = None,
    residency_budget: dict[str, Any] | None = None,
    probe_ledger: ModelProbeLedger | None = None,
    offered_options: list[dict[str, Any]] | None = None,
    #: the host-free enumeration seam `enumerate_pane_picker` publishes, threaded through so a
    #: caller that must not touch the OP-12 CLIs can still exercise the REAL verification path
    #: (validator MAJOR-2 — it stopped at this module and a deterministic test reached the host).
    op12_probes: Any = None,
    cli_present: bool | None = None,
    ollama_present: bool | None = None,
) -> dict[str, Any]:
    """Run the governed chain for ONE picker selection and return the ticket the shell executes.

    `holder_pid` OWNS any durable lease: the long-lived process that will hold the ConPTY session
    (the Electron main process), never this emitter. `session_id` is the identity of THAT session,
    chosen by the shell before it asks, so the terminal is counted per session and can be handed back
    even if this ticket never reaches it.

    `profile_loader` and `operator_terms_confirmed` are REQUIRED and have no defaults, because
    neither question is this module's to answer: which deployment profile is in force is the HOST's
    fact and which subscription terms the operator has confirmed is the OPERATOR's (invariant 1).
    The parameter-list comment says what the defaults used to do and why each was a defect (U283 /
    U292(a), directive §17.2(3)); `main()` is the sole production caller and supplies both."""
    led = ledger if ledger is not None else _default_ledger()
    loader = profile_loader
    gov = governor if governor is not None else SubscriptionGovernor()

    gates: dict[str, Any] = {
        "selection_offered": False,
        "live_operation_authorized": None,
        "operator_terms_confirmed": None,
        "cli_present": None,
        "local_runtime_present": None,
        "residency_scheduled": None,
        "ix3_counted": False,
    }

    session = None
    lease = None
    #: Outside the try, so the refusal branch reports what was MEASURED — including a record this
    #: call had already written before a later gate refused (validator MINOR-3 / spec-audit MINOR-7).
    node_registration: dict[str, Any] = _no_pane_node_record(
        "the authorization was refused before any node record could be written",
        log_path=str(registrar.log_path) if registrar is not None else None)
    model_probe: dict[str, Any] | None = None
    #: the identity actually MINTED, kept outside the try so the release measurement below can name
    #: the node even on the refusal branch (see `governor_released`).
    minted_node_id: str | None = None
    minted_sub_ref: str | None = None
    try:
        # W-15/R-10: INSIDE the guard. Every malformed-config path in the loader
        # raises by design, so with the load outside this `try` a LiveAuthorizationError
        # could never reach `except _GOVERNANCE_REFUSALS` and the gate id it is mapped
        # to (`live_operation`) was unreachable. Reproduced: a config naming grok_build
        # under register row OP-6 produced an uncaught traceback and `refused_by: null`
        # in the shell, even while launching a purely LOCAL pane that needs no live
        # authorization at all.
        auth = live_auth if live_auth is not None else load_live_authorization()
        option, role, mode, shell_env_names = _parse_selection(selection)
        # …and before THAT, the one gate whose whole meaning is "the network was not touched"
        # (spec-audit F2/U303). On a cloud profile this is a no-op; on an air-gapped one it refuses
        # a frontier pane without paying for the enumeration below.
        _assert_profile_permits_verifying(option, loader)
        # The option is CALLER-supplied; verify it against the host's own enumeration before any
        # gate reads it (spec-audit MAJOR-2). A forged `available`/`roles` dies here.
        # From here on the HOST's option is the option: identity fields matched, and the honesty
        # fields (`verified`, `label`, `roles`) come from the enumeration, never from the caller.
        option = _assert_option_offered(option, role, offered_options, op12_probes)
        gates["selection_offered"] = True
        adapter_id = option.get("adapter")
        frontier = adapter_id in _FRONTIER_ADAPTERS
        # The governed identity is minted HERE (invariant 2/29) — the shell asks for a pane's node,
        # it does not get to name it. An unknown role is refused before any gate mutation.
        identity = worker_identity(pane_id, role)
        sub_ref = canonical_subscription_ref(adapter_id) if frontier else None
        minted_node_id, minted_sub_ref = identity["node_id"], sub_ref
        pane_selection = PaneSelection(
            option=option, role=role, mode=mode, node_id=identity["node_id"],
            permission_profile_id=identity["permission_profile_id"], subscription_ref=sub_ref)

        model = None
        model_available = None
        if adapter_id == CLAUDE_CODE_ADAPTER:
            # OFFLINE read of the 17A probe verdict, keyed by the label the probe used (the option's
            # own slug). Accepted ⇒ ask for that id; conclusively unavailable ⇒ recorded CLI-default
            # fallback; unprobed/inconclusive ⇒ nothing changes and the option's slug is used.
            model_probe = resolve_launch_model(str(option.get("model_slug") or ""),
                                               ledger=probe_ledger)
            model, model_available = model_probe["model"], model_probe["model_available"]
        elif adapter_id == CODEX_ADAPTER:
            # There is no offline codex model probe (the CLI publishes no model list — 15C), so the
            # operator's label reaches `-m` UNVERIFIED. Say that in the ticket rather than emitting
            # `model_probe: null`, which reads like "nothing to report" (spec-audit MINOR-7 / U97).
            model_probe = {
                "label": option.get("model_slug"), "model": option.get("model_slug"),
                "model_available": None, "source": "unprobed-codex", "record": None,
                "note": ("the codex CLI publishes no model list and this build has no codex model "
                         "probe (U97): the id is carried verbatim and is UNVERIFIED until a live "
                         "reply — the 17A `.roundtrip` failure mode is not excluded for codex"),
            }
        elif adapter_id in (GROK_ADAPTER, ANTIGRAVITY_ADAPTER):
            # These two DO publish an offline model list, and the picker option was built from it —
            # so the id in the ticket is one the CLI itself named. That is a stronger provenance than
            # codex's unprobed label and a weaker one than a live reply, and the ticket says exactly
            # that rather than reusing either neighbour's wording. `model_available: True` is the
            # enumeration's verdict, not a session's.
            model, model_available = option.get("model_slug"), True
            model_probe = {
                "label": option.get("model_slug"), "model": model,
                "model_available": model_available, "source": "cli-enumeration", "record": None,
                "note": ("the id comes from this provider's own `models` listing, enumerated live on "
                         "the host: the CLI named it, so it is not an operator label — but no live "
                         "session has answered on it yet"),
            }

        if frontier:
            gates["live_operation_authorized"] = auth.is_provider_live(adapter_id)
            gates["operator_terms_confirmed"] = bool(operator_terms_confirmed)
            gates["cli_present"] = _detect_frontier_cli(adapter_id, cli_present)
            # the live gate FIRST — an unauthorized config has allowance 0, which is not a number the
            # governor can be seeded with; refusing here keeps the reason precise.
            auth.assert_provider_live(adapter_id)
            allowance = auth.terminals_for(adapter_id)        # per-provider (OP-12 §12)
            # the cross-process half of I-X3: project the DURABLE leases into this governor, so
            # terminals held by the shell (or another tool) are seen by the gate chain below.
            seeded = led.seed_governor(gov, subscription_ref=sub_ref, provider=adapter_id,
                                       allowance=allowance)
            session = authorize_worker_pane(
                pane_selection, live_auth=auth, governor=gov, profile_loader=loader,
                operator_terms_confirmed=operator_terms_confirmed, workspace=workspace,
                model=model, model_available=model_available, cli_present=gates["cli_present"],
                shell_env_names=shell_env_names)
            lease = led.acquire(subscription_ref=sub_ref, provider=adapter_id,
                                node_id=identity["node_id"], allowance=allowance,
                                holder_pid=int(holder_pid), purpose=_WORKER_LEASE_PURPOSE,
                                session_id=str(session_id or ""))
            gates["ix3_counted"] = True
            lease_view: dict[str, Any] | None = {
                **lease.as_dict(), "durable": True, "in_use": led.in_use(sub_ref),
                "allowance": allowance, "seeded_from_ledger": [ln.node_id for ln in seeded],
            }
            # …and invariant 2's other half: a counted terminal is a Sovereign NODE. Written HERE,
            # inside the try, so a registrar refusal refuses the SESSION — the `except` below hands
            # the durable terminal back. A leased supervised terminal with no record is the
            # naked-but-leased session the whole chain exists to prevent (18D `.close`, on the
            # probe path; this is the same rule on the pane path).
            node_registration = _register_pane_node(
                registrar, session, session_id=str(session_id or ""), lease_id=lease.lease_id,
                adapter_id=adapter_id)
        else:
            if residency_planner is not None:
                planner, budget = residency_planner, residency_budget
            else:
                planner, budget = _host_planner()
            gates["local_runtime_present"] = _detect_local_runtime(ollama_present)
            session = authorize_worker_pane(
                pane_selection, live_auth=auth, governor=gov, profile_loader=loader,
                operator_terms_confirmed=operator_terms_confirmed, workspace=workspace,
                residency_planner=planner, residency_budget=budget,
                ollama_present=gates["local_runtime_present"], shell_env_names=shell_env_names)
            gates["residency_scheduled"] = bool((session.residency_decision or {}).get("scheduled"))
            lease_view = None
            node_registration = _no_pane_node_record(
                "a LOCAL pane holds no subscription terminal and no frontier node record is "
                "written for it here: this wiring covers the two OP-12 frontier providers, whose "
                "supervised panes are the sessions directive §17.2(1) requires to be registered "
                "Sovereign nodes (invariant 19 — a local node is governed by VRAM residency)")

        ticket: dict[str, Any] = {
            "schema": WORKER_TICKET_SCHEMA,
            "authorized": True,
            "refused": False,
            "reason": None,
            "refused_by": None,
            "node_state": "launch_authorized",
            "launch": {**session.launch, "session_id": str(session_id or "")},
            "chrome": session.chrome.as_dict(),
            "identity": {
                "node_id": identity["node_id"],
                "permission_profile_id": identity["permission_profile_id"],
                "subscription_ref": sub_ref,
                "session_id": str(session_id or ""),
                "pane_id": str(pane_id),
                "workspace": str(workspace),
                "role": role,
                "mode": mode,
            },
            # What this ticket does and does NOT establish — stated, not implied (same disclosure the
            # conductor ticket makes). `chrome.governed:true` records AUTHORIZATION provenance, NOT
            # an enforced sandbox: the SHELL binds the process at spawn (supervised admission,
            # workspace cwd, credential scrub, lease release on exit).
            "containment": {
                "authorized": True,
                "supervisor_bound": False,
                "bound_by": ("shell supervised spawn — SessionManager.spawn refuses without an "
                             "admitted node (IpcSupervisor.admit over the verified control-plane "
                             "channel), reports the lifecycle, and kills every session on loss"),
                # The local branch lists NOTHING to release. It used to name
                # `residency_release_on_session_exit (U96)`, which asked the shell for a release that
                # by this build's own design cannot happen: the reservation lives in the emitter's
                # in-process planner and dies with the emitter, as U96 item 3 and the enumerator's
                # HONEST LIMITS both state. Two fields of one ticket disagreeing about whether there
                # is anything to release is exactly the kind of instruction a shell would either
                # ignore or implement against nothing (spec-audit NIT, 2026-07-26). The absence is
                # the honest statement; U96 tracks the durability gap itself.
                "requires": ["supervised_admission", "workspace_cwd_binding",
                             "credential_env_scrub"] + (
                                 ["lease_release_on_session_exit"] if lease_view else []),
                "residency_reservation_lifetime": (
                    None if lease_view else
                    "in-process to this emitter — nothing survives to be released (U96)"),
                "still_owed": ["permission_profile_binding (U78(a))", "os_job_object_or_acl (U25)",
                               "node_heartbeat (U78(a))"],
                "os_job_object": False,
                "owed_to": "U25 (pid→job-object handoff needs the IPC write op)",
                "note": ("authorization + (frontier) a counted terminal or (local) a scheduled VRAM "
                         "residency only; supervisor session registration, workspace binding and "
                         "credential scrubbing are enforced by the shell's supervised spawn"),
            },
            "lease": lease_view,
            "subscription_governed": bool(lease_view),
            # The decision AND the budget it was made against (gate-validator R2): `budget.estimate`
            # is ALWAYS true — an env-supplied budget is a stated figure, not a queried GPU capacity
            # — so this authorization is explicitly an ADMISSION against a stand-in, never "proven to
            # fit". `budget_source` names which stand-in (spec-audit MINOR-2, 2026-07-26).
            "residency": (dict(session.residency_decision, budget=session.residency_budget)
                          if session.residency_decision else None),
            "model_probe": dict(model_probe) if model_probe else None,
            # MEASURED from what the registrar returned, never declared: `registered:true` means a
            # `node@1.1` document validated against the real schema and landed on the hash-chained
            # append-only log, and `registered:false` always carries the reason it did not.
            "node_registration": dict(node_registration),
            "release_with": (["--release-session", str(session_id or "")] if lease_view else None),
            "governor_released": False,   # measured after teardown, never asserted
            "gates": dict(gates),
        }
    except _GOVERNANCE_REFUSALS as exc:
        # A refusal raised AFTER the durable lease was taken (a ledger fault while reading the count,
        # a shape error while building the ticket) must not leave a terminal counted for a session
        # that will never exist: the refusal ticket says `lease: null`, and that statement has to be
        # true (gate-validator R1). Best-effort — a ledger that is already unreadable cannot be
        # corrected from here, and dead-holder reaping remains the backstop.
        if lease is not None:
            try:
                led.release(lease.lease_id)
            except (LeaseLedgerCorrupt, LeaseLedgerLocked):
                pass
        # …and the same argument for the NODE record: a refusal raised after `_register_pane_node`
        # succeeded would otherwise leave a SPAWNING record on an append-only log for a session
        # that will never exist, while the refusal ticket said none existed. The record cannot be
        # un-written (invariant 12), so it is CLOSED as an unexpected exit and the outcome is
        # reported on the ticket rather than declared away.
        if node_registration.get("registered") and registrar is not None:
            try:
                node_registration = dict(node_registration, closed_on_refusal=(
                    registrar.close_session_record(
                        node_registration["node_key"], session_id=str(session_id or ""),
                        exit_code=None, expected=False)))
            except (ProviderNodeRegistrationRefused, RegistrationRefused, IllegalTransition,
                    OSError, ValueError) as close_exc:
                node_registration = dict(node_registration,
                                         closed_on_refusal={"closed": False,
                                                            "reason": str(close_exc)})
        ticket = _refusal(f"{type(exc).__name__}: {exc}", gates=gates, refused_by=_gate_id(exc),
                          node_registration=node_registration)
    except BaseException:
        # W-13/R-15: the release above is the ONLY one, and it sits inside the governance branch.
        # `_GOVERNANCE_REFUSALS` excludes OSError, KeyError and IllegalTransition -- and
        # `_register_pane_node`, which runs AFTER the acquire, reaches `os.fsync` and raises a bare
        # OSError on a full or failing disk. Such a failure escaped to the caller with the durable
        # terminal still counted, and its `holder_pid` is the long-lived shell, so dead-holder
        # reaping can never reclaim it: with grok's allowance of 1 the subscription wedges for the
        # life of the app.
        #
        # Donor: `tools/live/emit_conductor_dispatch.py:182-187` -- release, then re-raise, so the
        # terminal comes back and the failure is still reported. BaseException rather than
        # Exception on purpose: a KeyboardInterrupt between the acquire and the return strands the
        # same durable resource, and this is the fail-closed direction for one.
        if lease is not None:
            try:
                led.release(lease.lease_id)
            except (LeaseLedgerCorrupt, LeaseLedgerLocked):
                pass   # an unreadable ledger cannot be corrected from here; reaping is the backstop
        raise
    finally:
        if session is not None:
            session.teardown()   # in-process governor released; the durable lease is untouched
        # …and the node log's exclusive lock, on EVERY exit path (the same rule
        # `governed_probe_session` follows). This emitter is one-shot, but the lock is
        # cross-process and pid-stamped: a registrar left open here would refuse the very next
        # invocation — the shell's own spawn attestation — with `node_log_locked`.
        if registrar is not None:
            try:
                registrar.close()
            except Exception:      # noqa: BLE001 — a close that fails must not mask the ticket
                pass

    # Measured, not asserted, on BOTH branches (a refusal can be raised after `acquire`) — and
    # measured on THIS node, not on the governor as a whole, which was deliberately SEEDED with the
    # durable leases other processes hold. The question is whether OUR in-process acquire came back.
    #
    # Read from the MINTED identity, not from the ticket's: a refusal ticket carries `identity:null`,
    # so `node_id` fell back to the `_NO_NODE` sentinel — which can never be a governor holder, so
    # the comparison was vacuous and always yielded `true` on exactly the branch where a leak is
    # possible (the acquire happens after the identity is minted). The claim "measured, never
    # asserted" was false for the refusal branch (spec-audit MINOR-5, 2026-07-26). `_NO_NODE` now
    # survives only for a refusal raised BEFORE any identity existed, where nothing could leak.
    node_id = minted_node_id or _NO_NODE
    ref = minted_sub_ref or ""
    holders = (gov.status().get(ref) or {}).get("active") or []
    ticket["governor_released"] = node_id not in holders
    return ticket


def _detect_frontier_cli(adapter_id: str, injected: bool | None) -> bool:
    """Observed, never assumed (invariant 27): detected UP FRONT so a refusal raised by a LATER gate
    cannot report "CLI missing" when the CLI was found."""
    if injected is not None:
        return bool(injected)
    from adapters import detect

    resolvers = {
        CLAUDE_CODE_ADAPTER: detect.claude_code_available,
        CODEX_ADAPTER: detect.codex_available,
        GROK_ADAPTER: detect.grok_available,
        ANTIGRAVITY_ADAPTER: detect.antigravity_available,
    }
    # KeyError on an unlisted adapter is deliberate: a frontier provider wired into the authorizer
    # but not here would otherwise report a detection result belonging to another CLI.
    return bool(resolvers[adapter_id]())


def _detect_local_runtime(injected: bool | None) -> bool:
    if injected is not None:
        return bool(injected)
    from adapters import detect

    return detect.ollama_executable() is not None


def build_worker_lease_release_session(
    session_id: str, *, ledger: TerminalLeaseLedger | None = None, registrar: Any = None,
) -> dict[str, Any]:
    """Hand back the terminal held by ONE session, on WHICHEVER subscription holds it — and CLOSE
    that session's Sovereign node record on the same call.

    The shell knows the session key it chose; it should not have to know which provider's allowance
    the ticket ended up counting against (and on a refused/undelivered ticket it may not). Idempotent:
    nothing to reclaim reports `released:false` with no error.

    The node half is deliberately NOT conditional on the lease half. The lease may already be gone —
    reaped because a holder died, released by an earlier call — while the record is still open, and
    a release that only closed the record when it also reclaimed a terminal would leave exactly
    those nodes reading SPAWNING forever on the operator's log. The node key is read from the LEASE
    LEDGER before the release (that is where the session key and the node id are written together),
    so this needs no extra argument from the shell and cannot close a record for a different node.
    A session with no record at all — every local pane, and every OP-6 frontier pane — reports
    `closed:false` with the reason and is not an error."""
    led = ledger if ledger is not None else _default_ledger()
    out: dict[str, Any] = {"schema": LEASE_RELEASE_SCHEMA, "lease_id": None,
                           "session_id": session_id, "released": False, "released_count": 0,
                           "error": None, "subscriptions": {},
                           "node_record": {"closed": False, "node_key": None,
                                           "reason": "no registrar supplied"}}
    node_keys: list[str] = []
    try:
        refs = sorted(set(led.snapshot().keys())
                      | {canonical_subscription_ref(a) for a in _FRONTIER_ADAPTERS})
        # Read the node BEFORE the release removes the row that names it.
        node_keys = sorted({ln.node_id for ln in led.live() if ln.session_id == session_id})
        released = sum(led.release_session(ref, session_id) for ref in refs)
        out["released_count"] = released
        out["released"] = released > 0
        out["subscriptions"] = led.snapshot()
    except (LeaseLedgerCorrupt, LeaseLedgerLocked) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    if registrar is not None:
        # A ledger fault above must not stop the record from being closed — the two stores fail
        # independently, and a node left open because a LEASE file was locked is the D-LOOP-1 leak
        # arriving by the other store's failure.
        if not node_keys:
            node_keys = _pane_node_keys_for_session(session_id)
        try:
            out["node_record"] = _close_first_pane_record(registrar, node_keys, session_id)
        except (ProviderNodeRegistrationRefused, RegistrationRefused, IllegalTransition, OSError,
                ValueError) as exc:
            out["node_record"] = {"closed": False, "node_key": node_keys[0] if node_keys else None,
                                  "log_path": str(registrar.log_path),
                                  "reason": f"{type(exc).__name__}: {exc}"}
        finally:
            try:
                registrar.close()
            except Exception:      # noqa: BLE001 — a close that fails must not mask the result
                pass
    return out


def _pane_node_keys_for_session(session_id: str) -> list[str]:
    """The node key a worker pane session would have been minted with, derived from the session key.

    The ledger is the authority and is asked first; this is the fallback for the case that ledger
    cannot answer — the lease is already gone (reaped, or released by an earlier call) while the
    record is still open. The shell's session key is `<paneId>#<holderPid>.<seq>`
    (`picker/worker-spawn.js`) and `worker_identity` mints `worker-<paneId>`, so the pane id is the
    part before the `#`. Derivation, not invention: if it names no record, `close_session_record`
    reports exactly that and closes nothing."""
    head = str(session_id or "").split("#", 1)[0].strip()
    return [f"worker-{head}"] if head else []


def _close_first_pane_record(registrar: Any, node_keys: list[str], session_id: str,
                             ) -> dict[str, Any]:
    """Close the record for the first of `node_keys` this host's node log carries FOR THIS SESSION.

    The session binding is enforced inside `close_session_record`, not here: a record belonging to
    another session reports `closed:false` with its gate, so a stale record can never be closed by
    a late release for a different session (validator MAJOR-1 / spec-audit MAJOR-2)."""
    last: dict[str, Any] | None = None
    for key in node_keys:
        last = registrar.close_session_record(key, session_id=session_id, exit_code=None,
                                              expected=True)
        if last.get("closed"):
            return last
    return last or {"closed": False, "node_key": None, "log_path": str(registrar.log_path),
                    "reason": f"no node key could be resolved for session {session_id}"}


def build_worker_lease_release(lease_id: str, *, ledger: TerminalLeaseLedger | None = None,
                               ) -> dict[str, Any]:
    """Hand one durable terminal back by lease id. Idempotent; never raises."""
    led = ledger if ledger is not None else _default_ledger()
    out: dict[str, Any] = {"schema": LEASE_RELEASE_SCHEMA, "lease_id": lease_id,
                           "released": False, "error": None, "subscriptions": {}}
    try:
        out["released"] = led.release(lease_id)
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


def _value_after(argv: list[str], flag: str) -> str | None:
    """`_arg_after`, refusing a value that is itself a FLAG.

    `_arg_after` returns the next token whatever it is, so an omitted value silently swallows the
    following flag: `--record-pane-spawned --pid 10` yielded the node key `"--pid"` and went on to
    ask the operator's DURABLE node log about a node by that name, and `--release-session --pid 5`
    derived the node key `worker---pid` the same way. A value that looks like a flag is a missing
    value. Used by every mode that takes one, because fixing this in one mode and leaving it in its
    two siblings is how the defect comes back (validator MINOR-2)."""
    value = _arg_after(argv, flag)
    if value is None or value.startswith("-"):
        return None
    return value


def main(argv: list[str]) -> int:
    """CLI. Each mode prints exactly one JSON line and exits 0 (a governed refusal is still a 0-exit
    ticket the shell renders fail-closed); usage/argument errors exit 2 with NO JSON, which the shell
    source treats as "unavailable" — an un-launched pane, never a fabricated launch.

    There is a THIRD shape, added at 18E and stated here rather than left for someone to discover:
    a host whose `SOVEREIGN_DEPLOYMENT_PROFILE` names a profile that does not exist raises out of
    `profile_loader_from_host()` before any ticket is built (non-zero exit, traceback, no JSON).
    That is the fail-closed direction and the shell already handles it — `picker/launch-source.js`
    turns any non-ticket into `unavailableWorkerTicket` — but it is a real exit shape and the
    contract above did not describe it. It cannot be turned into a refusal ticket without this
    module deciding which profile to fall back to, which is the exact question §17.2(3) removed
    from it."""
    if "--emit-worker-launch" in argv:
        raw = _arg_after(argv, "--holder-pid")
        try:
            holder_pid = int(raw) if raw is not None else 0
        except ValueError:
            holder_pid = 0
        if holder_pid <= 0:
            sys.stderr.write(
                "--holder-pid <pid> is REQUIRED: a durable I-X3 lease must be owned by the "
                "long-lived process that will hold the session (the shell), never by this "
                "about-to-exit emitter — refuse to count a terminal nobody holds.\n")
            return 2
        session_id = _arg_after(argv, "--session-id")
        if not session_id:
            sys.stderr.write(
                "--session-id <id> is REQUIRED: a terminal is counted per SESSION, and the shell "
                "chooses the key before asking so it can hand the terminal back even if this "
                "ticket never reaches it (U75/U77).\n")
            return 2
        pane_id = _arg_after(argv, "--pane-id")
        if not pane_id:
            sys.stderr.write(
                "--pane-id <pane> is REQUIRED: the governed node identity is minted from the pane "
                "and the role, here — the shell never names its own node (invariant 2/29).\n")
            return 2
        raw_selection = sys.stdin.read()
        try:
            selection = json.loads(raw_selection) if raw_selection.strip() else None
        except json.JSONDecodeError as exc:
            # A selection we cannot parse is a REFUSAL, not a crash: the shell gets an honest,
            # well-formed ticket saying why the pane stayed un-launched.
            sys.stdout.write(json.dumps(_refusal(
                f"selection could not be parsed as JSON: {exc}",
                gates={"selection_offered": False}, refused_by="selection_guard"), default=str) + "\n")
            return 0
        sys.stdout.write(json.dumps(build_worker_launch_ticket(
            holder_pid=holder_pid, session_id=session_id, pane_id=pane_id, selection=selection,
            # The two gates whose inputs are not this module's to invent (U283/U292(a)).
            #
            # The profile comes from the HOST, through the one implementation of that question, so
            # an operator running the shell under SOVEREIGN_DEPLOYMENT_PROFILE=offline_airgapped
            # gets invariant 20's refusal on the product path and not only in a test.
            profile_loader=profile_loader_from_host(),
            # The OPERATOR's R8 §6 determination, recorded, never inferred (invariant 1): OP-9 for
            # claude_code/openai_codex_cli (AUTONOMOUS_BUILD_DIRECTIVE.md §14) and OP-12 for
            # grok_build/google_antigravity (§17, "the operator confirms both subscriptions permit
            # supervised first-party-CLI use"). It is a citation of a recorded ruling, not a
            # credential and not a measurement — and it is written HERE, at the call site, where a
            # reader can check the citation, rather than defaulted inside the gate chain.
            operator_terms_confirmed=True,
            # The DURABLE per-host node log under `.sovereign_store/` (18E `.live.electron.wiring`).
            # Supplied here, at the one production call site, for the same reason the two gate
            # inputs above are: whether a governed session becomes a Sovereign node is the caller's
            # fact. The registrar opens no file until a record is actually written, so a refused
            # ticket leaves nothing behind in the operator's store.
            registrar=default_provider_node_registrar(ROOT)),
            default=str) + "\n")
        return 0
    if "--record-pane-spawned" in argv:
        node_key = _value_after(argv, "--record-pane-spawned")
        raw_pid = _value_after(argv, "--pid")
        session_id = _value_after(argv, "--session-id")
        try:
            pid = int(raw_pid) if raw_pid is not None else 0
        except ValueError:
            pid = 0
        if not node_key or not session_id or pid <= 0:
            sys.stderr.write(
                "--record-pane-spawned <node_key> --session-id <id> --pid <pid> all required: the "
                "attestation's whole content is that a SUPERVISED process with that pid exists, "
                "and the SESSION is what binds it to the right record — a pane id is reused across "
                "sessions (fail closed).\n")
            return 2
        sys.stdout.write(json.dumps(build_worker_pane_spawn_attestation(
            node_key, session_id=session_id, pid=pid,
            registrar=default_provider_node_registrar(ROOT)),
            default=str) + "\n")
        return 0
    if "--release-session" in argv:
        session_id = _value_after(argv, "--release-session")
        if not session_id:
            sys.stderr.write("--release-session <session_id> requires the session key to hand back\n")
            return 2
        sys.stdout.write(json.dumps(build_worker_lease_release_session(
            session_id, registrar=default_provider_node_registrar(ROOT)), default=str) + "\n")
        return 0
    if "--release-lease" in argv:
        lease_id = _value_after(argv, "--release-lease")
        if not lease_id:
            sys.stderr.write("--release-lease <lease_id> requires the lease id to hand back\n")
            return 2
        sys.stdout.write(json.dumps(build_worker_lease_release(lease_id), default=str) + "\n")
        return 0
    sys.stderr.write(
        "usage: emit_worker_launch.py --emit-worker-launch --holder-pid <pid> --session-id <id> "
        "--pane-id <pane>   (the picker selection JSON on stdin)\n"
        "       emit_worker_launch.py --record-pane-spawned <node_key> --session-id <id> "
        "--pid <pid>\n"
        "       emit_worker_launch.py --release-session <session_id>\n"
        "       emit_worker_launch.py --release-lease <lease_id>\n"
        "  the governed WORKER launch ticket the shell executes in a pane's ConPTY (Phase 17B).\n"
        "  emit mode on a FRONTIER selection TAKES A TERMINAL (durable I-X3 lease) and WRITES A\n"
        "    DURABLE NODE RECORD under .sovereign_store/ - records are never deletable.\n"
        "  operator_terms_confirmed=True is asserted at the call site citing recorded rulings\n"
        "    OP-9/OP-12 - a literal citing a ruling, never measured from the operator here.\n")
    return 2


if __name__ == "__main__":  # pragma: no cover - exercised via tests calling main()
    raise SystemExit(main(sys.argv[1:]))
