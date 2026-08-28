"""The governed, supervised session a HEADLESS one-shot OP-12 provider call runs inside —
Phase 18C `.probe-path`, discharging **U234**.

18A built the one harmless live probe (`GROK_PROVIDER_OK` / `GEMINI_PROVIDER_OK`) and then refused
to execute it: the child would have been a bare `subprocess.run` holding no node identity, no I-X3
subscription lease and no teardown accounting — a naked session (invariant 2 / I-C1). While the
providers sat outside every code-pinned live scope that refusal was academic. **18B `.scope` ended
that** by adding the OP-12 row, which is exactly what U237 needed and which left the
`_SUPERVISED_PROBE_PATH` constant as the only thing between `-Action probe` and an unsupervised
frontier CLI. The 18A round-4 validator's ruling was explicit: opening the operator's switch before
this path exists is *a gate failure at 18C*. This module is that path.

**It is the interactive pane's gate chain, in the same order, for a headless child.** Nothing here
is a second, looser rule — that is the whole point, because a probe that could be permitted by a
weaker rule than a session is a bypass with a diagnostic's name on it. The first cut of this module
*claimed* that parity and did not hold it, in the two places a caller supplies rather than the
module decides: it manufactured `ProfileLoader(DeploymentProfile("cloud"))` when none was injected,
so invariant 20's air-gap half could never refuse (an air-gapped host opened a leased session), and
it defaulted the operator's R8 §6 determination to *confirmed*. Both are now **required keywords**,
exactly as `worker_pane_spawn._authorize_frontier` has them, and
`test_the_gate_chain_matches_the_pane_path` pins the sequence so the claim cannot drift away from
the code again. The chain:

  1. `ProfileLoader.assert_startup([capability])` — roster eligibility + `LIVE_OPERATION_AUTHORIZED`
     (invariant 20, fail closed by absence); the loader is the CALLER's, built from the host's real
     `SOVEREIGN_DEPLOYMENT_PROFILE`, because a profile this module picks for itself is not a gate;
  2. `LiveAuthorization.assert_provider_live` re-asserted at the authorization site;
  3. the R8 §6 **operator** live-terms determination (OP-9 class; invariant 1 — never ours to make);
  4. CLI presence, with **that provider's own** exception type and a RESOLVED binary, never a bare
     name for the child to PATH-search (operator directive §14);
  5. **I-X3**: the durable `TerminalLeaseLedger` is projected into a `SubscriptionGovernor`, so a
     terminal the operator's shell holds is counted here, and this probe takes ONE lease on its own
     provider's resource (`grok_build_subscription` / `google_antigravity_subscription`, allowance 1
     each, never merged — operator directive §12). That is also the mechanism behind §17's "do not
     attempt simultaneous same-provider sessions": it is refused, not merely discouraged.
  6. the lease is released on **every** exit path, and the release is **measured** into
     `teardown_record` rather than asserted (D-LOOP-1).

`supervised_probe_runner` is the execution half: the child runs inside the repository's managed-
process boundary (`process_tree.run_managed_process` — a Windows **job object** on the operator's
host, a POSIX process group elsewhere; the deterministic suite runs on both), it must be the same
file the gate resolved (`argv[0] == session.executable`, refused otherwise — the gate below
resolves a binary precisely so the child cannot be a different one), it carries no interactive
stdin, and the credential-bearing environment is removed by NAME (§2.2/§13 — names, never values)
with its working directory bound to the authorized workspace. Descendants (grok's leader/agent
helpers) are reaped rather than left behind, and — because a containment failure is the one thing
this boundary exists to detect — `ProcessTreeCleanupError` is REPORTED into the verdict and into
`teardown_record["process_tree_clean"]` rather than escaping as a crash the operator would read as
a broken tool (invariant 27/29).

Honest note on "no interactive stdin": `supervised_probe_runner` passes `stdin=subprocess.DEVNULL`,
and `process_tree._run_posix` honours it directly. On Windows the job-member shim owns the handle
(it needs a pipe for its own GO admission) and hands `sys.stdin` to the real target, so the child
inherits a pipe that `communicate()` has already closed — EOF, the same *behaviour*, by a different
mechanism than the argument names. Recorded as U281 rather than described as a closed handle.

**The node record — the 18D `.close` wiring, and its exact limits.** Through 18C this module
registered no Sovereign node RECORD and could not: `NodeRegistry.register` refused both adapter ids
because node@1.0's `adapter` enum is frozen and has no member for either (U227). OP-12.1
(2026-08-01) ruled U227 by successor schema, `node@1.1` admits both, and 18D `.close` wires the
registration: a caller-supplied `registrar` (required keyword, `None` permitted and meaning exactly
"no record") writes a validated `node@1.1` document on the append-only node log once the terminal
is held, and the record is CLOSED on every exit path. `node_registered` is now a MEASUREMENT.
Registration is step 7 and not step 0 on purpose: it is not a gate, it authorizes nothing, and a
caller that registered a node without walking this chain would get none of the checks above —
which is why the record is written last, from a session that already passed all of them.

**What it still is NOT.** The job object does not make the CLI's own behaviour trustworthy:
`--permission-mode plan` / `--mode plan` are arguments the harness honours, and invariant 29 says
never trust the harness (U25 remains owed). What the boundary does guarantee is process-tree
teardown on every exit path. And an interactive PANE still mints only an identity — `worker_identity`
creates no record, and wiring that path is not this module's to do (U297).
"""
from __future__ import annotations

import os
import re
import subprocess
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from adapters.frontier.antigravity import ANTIGRAVITY_ADAPTER
from adapters.frontier.grok_build import GROK_ADAPTER
from adapters.frontier.process_tree import ProcessTreeCleanupError, run_managed_process
from control_plane.profiles.live_authorization import (
    LiveAuthorization,
    load_live_authorization,
)
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
from node_runtime.supervisor.frontier_provider_spawn import (
    AntigravityCliUnavailable,
    GrokCliUnavailable,
    capability_for_antigravity,
    capability_for_grok,
)
from node_runtime.supervisor.frontier_spawn import LiveTermsNotConfirmed
from node_runtime.supervisor.subscription_governor import (
    SubscriptionGovernor,
    canonical_subscription_ref,
)
from node_runtime.supervisor.terminal_lease import (
    LeaseLedgerCorrupt,
    LeaseLedgerLocked,
    TerminalLease,
    TerminalLeaseLedger,
    default_ledger_path,
)
from node_runtime.supervisor.worker_pane_spawn import (
    GATE_BINARY_UNRESOLVED,
    GATE_UNKNOWN_ADAPTER,
    worker_env_scrub_names,
)

if TYPE_CHECKING:      # the registrar is a caller-supplied collaborator, never constructed here
    from node_runtime.supervisor.provider_node_registration import ProviderNodeRegistrar

#: The ONLY providers this module governs. `claude_code` / `openai_codex_cli` have their own
#: supervised paths (`frontier_spawn` / `codex_spawn`) and must not acquire a second one here.
PROBE_PROVIDERS: tuple[str, ...] = (GROK_ADAPTER, ANTIGRAVITY_ADAPTER)

#: The role a probe is born under. Reasoning only — the OP-12 backends ship no coding role
#: (it would need an auto-approving permission mode operator directive §11 forbids, or an
#: undocumented sandbox profile; U260).
PROBE_ROLE = "reasoning"

#: Recorded on the durable lease so an operator reading the ledger can tell a one-shot probe (bounded
#: by `DEFAULT_PROBE_TIMEOUT_S`) from a pane they opened. Bounded work, its own purpose string.
PROBE_LEASE_PURPOSE = "one-shot harmless live provider probe (OP-12 §17, phase 18C)"

#: Identity gate id, distinct from the pane one: a receipt asserting "the probe refused on identity"
#: must not be satisfiable by a pane-path refusal.
GATE_PROBE_IDENTITY = "probe_identity"

#: Deliberately the same rule as `worker_pane_spawn._PANE_ID_RE` (private to that module), for the
#: same reason: this string becomes a node id and then a durable lease key, whose own delimiter is
#: `#`. `test_the_probe_id_charset_matches_the_pane_one` makes the duplication detectable.
_PROBE_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")

_CAPABILITY = {GROK_ADAPTER: capability_for_grok, ANTIGRAVITY_ADAPTER: capability_for_antigravity}
#: per provider, never shared — operator directive §14 forbids printing one provider's failure text
#: under another's name, and a TYPE cannot be got wrong by a copy-pasted message.
_UNAVAILABLE: dict[str, tuple[type[Exception], str]] = {
    GROK_ADAPTER: (GrokCliUnavailable, "grok"),
    ANTIGRAVITY_ADAPTER: (AntigravityCliUnavailable, "agy"),
}

#: default timeout for one harmless probe: generous enough for a cold CLI start, bounded so a hung
#: child cannot hold the subscription's single terminal indefinitely.
DEFAULT_PROBE_TIMEOUT_S = 180.0


class ProbeSessionRefused(Exception):
    """This module refused fail-closed: an unusable probe identity, a provider it does not govern,
    or a presence gate that passed without resolving a binary. `gate` is the machine-readable id of
    the check that said no, so a receipt can assert the gate it claims to prove instead of grepping
    prose. The live gates' own exceptions (`LiveAuthorizationError`, `ProfileViolation`,
    `LiveTermsNotConfirmed`, `GrokCliUnavailable`, `AntigravityCliUnavailable`,
    `SubscriptionLimitExceeded`) propagate unchanged — each is a different gate saying no."""

    def __init__(self, message: str, *, gate: str = "probe_session") -> None:
        super().__init__(message)
        self.gate = gate


def probe_identity(probe_id: str) -> dict[str, str]:
    """The governed identity a probe child runs under — minted HERE, never supplied by a caller.

    Deterministic in the probe id alone, and bounded to a conservative charset before it can become
    a node id and enter the durable lease ledger (a key carrying whitespace, a path separator or the
    `#` lease-key delimiter is a key nobody can reliably reclaim by)."""
    pid = str(probe_id or "").strip()
    if not pid:
        raise ProbeSessionRefused(
            "a governed probe needs a probe id to mint a node identity — fail closed",
            gate=GATE_PROBE_IDENTITY)
    if not _PROBE_ID_RE.fullmatch(pid):
        raise ProbeSessionRefused(
            f"probe id {pid!r} is not a safe node-identity component — expected 1..64 chars of "
            f"[A-Za-z0-9._-] (fail closed: it becomes a key in the durable I-X3 ledger, whose own "
            f"delimiter is `#`)", gate=GATE_PROBE_IDENTITY)
    return {"node_id": f"probe-{pid}", "permission_profile_id": f"pp-probe-{PROBE_ROLE}"}


@dataclass
class GovernedProbeSession:
    """One authorized, leased, supervised headless probe session.

    Mutable by design: `spawned_pids` is filled by the runner and `teardown_record` by the context
    manager's exit — both are MEASUREMENTS taken after the fact, and a frozen document that asserted
    them up front would be claiming what it has not yet observed."""

    provider: str
    display: str
    node_id: str
    #: THIS probe run. Two probes of one provider share a node id (it is derived from the provider's
    #: own command name), so the session id is what makes them two terminals rather than one
    #: idempotent re-acquire — the U75 lesson, which is also why the governor counts the LEASE KEY.
    session_id: str
    permission_profile_id: str
    role: str
    subscription_ref: str
    allowance: int
    in_use: int
    lease_id: str
    executable: str
    workspace: str
    env_scrub_names: tuple[str, ...]
    seeded_from_ledger: tuple[str, ...] = ()
    spawned_pids: tuple[int, ...] = ()
    #: Set by the runner from `run_managed_process`'s own outcome: True when the boundary tore the
    #: whole descendant tree down, False when it raised `ProcessTreeCleanupError`, and None while
    #: no child has run. Tri-state on purpose — see `teardown_record`.
    process_tree_clean: bool | None = None
    #: The child's own exit code, set by the runner. `None` means no child ran (or it timed out /
    #: could not be spawned) — which is why the node exit records it as `None` rather than 0: a
    #: session that never ran a child did not exit 0, it did not exit at all.
    child_exit_code: int | None = None
    teardown_record: dict[str, Any] = field(default_factory=dict)
    _base_env: dict[str, str] | None = field(default=None, repr=False)

    #: Fixed facts about what this session IS — carried as fields so a consumer reads them from the
    #: document instead of assuming them from the module name.
    supervised: bool = True
    interactive: bool = False
    one_shot: bool = True
    #: MEASURED at 18D `.close`: True when this session's `registrar` wrote a `node@1.1` record on
    #: the append-only node log, False when the caller explicitly passed `registrar=None`. It was a
    #: hardcoded `False` through 18C — first because the vocabulary refused these adapter ids
    #: (U227), then, after OP-12.1 admitted them, because nothing was wired to write one. Both
    #: reasons are gone; the field now reports what happened.
    node_registered: bool = False
    #: The registration's own facts (`ProviderNodeRegistration.as_dict()`), or None when no record
    #: was created. Carried so a receipt reads the record's uuid, its schema version and the
    #: version that ADMITTED the adapter from the session document rather than re-deriving them.
    node_record: dict[str, Any] | None = None

    def child_env(self) -> dict[str, str]:
        """The environment the child gets: this process's (or the injected base), minus every name
        the shared classifier flags. A superset scrub — the union of the claude, codex and OP-12
        classifiers — because over-scrubbing costs a probe nothing and under-scrubbing hands one
        provider's key to another provider's child (§13)."""
        env = dict(os.environ if self._base_env is None else self._base_env)
        for name in self.env_scrub_names:
            env.pop(name, None)
        return env

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider, "display": self.display, "node_id": self.node_id,
            "session_id": self.session_id, "lease_key": f"{self.node_id}#{self.session_id}",
            "permission_profile_id": self.permission_profile_id, "role": self.role,
            "subscription_ref": self.subscription_ref, "allowance": self.allowance,
            "in_use": self.in_use, "lease_id": self.lease_id, "executable": self.executable,
            "workspace": self.workspace,
            # NAMES only — never a value (§2.2). `child_env` is deliberately not serialized.
            "env_scrub_names": list(self.env_scrub_names),
            "seeded_from_ledger": list(self.seeded_from_ledger),
            "spawned_pids": list(self.spawned_pids),
            "process_tree_clean": self.process_tree_clean,
            "supervised": self.supervised, "interactive": self.interactive,
            "one_shot": self.one_shot, "node_registered": self.node_registered,
            "node_record": dict(self.node_record) if self.node_record else None,
            "teardown": dict(self.teardown_record),
        }


#: The host's deployment-profile environment variable — the same name `frontier_provider_recon`
#: reads. One spelling, one meaning.
PROFILE_ENV = "SOVEREIGN_DEPLOYMENT_PROFILE"


def profile_loader_from_host(environ: dict[str, str] | None = None) -> ProfileLoader:
    """The deployment profile actually in force, as a `ProfileLoader` — the ONE implementation of
    "which profile is this host running under" on the probe path.

    Fail closed twice over: an unset variable means `cloud` (the documented default, and the only
    value that permits a frontier call at all), and an UNRECOGNISED id raises `ProfileViolation`
    out of `ProfileLoader.__init__` rather than being read as permission. It exists because the
    module used to manufacture a `cloud` loader for itself, which made invariant 20's air-gap half
    structurally unreachable on the product path (U91's shape, found by both reviewers at 18C)."""
    env = os.environ if environ is None else environ
    raw = (env.get(PROFILE_ENV) or "cloud").strip() or "cloud"
    return ProfileLoader(DeploymentProfile(raw))


def _resolve_executable(provider: str) -> str | None:
    """Host resolution through the module that owns detection — never a hardcoded install path."""
    from adapters import detect  # noqa: PLC0415 — local, matching the pane path's convention

    return {GROK_ADAPTER: detect.grok_executable,
            ANTIGRAVITY_ADAPTER: detect.antigravity_executable}[provider]()


@contextmanager
def governed_probe_session(
    provider: str,
    *,
    probe_id: str,
    workspace: str | Path,
    # REQUIRED, both of them, and required for the same reason: they are the two gates whose input
    # comes from outside this module. A default here is this module deciding a question that is the
    # host's (which deployment profile is in force) or the OPERATOR's (whether the subscription
    # terms permit a supervised CLI call). `_authorize_frontier` requires both; so does this.
    profile_loader: ProfileLoader,
    operator_terms_confirmed: bool,
    # REQUIRED for a third reason of the same kind: whether the session this module opens becomes a
    # Sovereign node RECORD (invariant 2) is the caller's fact, not this module's default. Passing
    # `None` is legitimate and means exactly one thing — no record, and the session says so in
    # `node_registered` — but the caller has to write it.
    registrar: "ProviderNodeRegistrar | None",
    live_auth: LiveAuthorization | None = None,
    governor: SubscriptionGovernor | None = None,
    ledger: TerminalLeaseLedger | None = None,
    cli_present: bool | None = None,
    executable: str | None = None,
    holder_pid: int | None = None,
    session_id: str = "",
    base_env: dict[str, str] | None = None,
) -> Iterator[GovernedProbeSession]:
    """Authorize, lease and (on exit) release ONE governed headless probe session.

    Raises before yielding if any gate refuses — the body never runs and nothing is spent. The
    durable lease is released on every exit path, including an exception raised by the body, and the
    release is measured into `session.teardown_record`.

    `operator_terms_confirmed` carries the OP-9-class R8 §6 determination the OPERATOR made — for
    these two providers it is recorded at `AUTONOMOUS_BUILD_DIRECTIVE.md` §17 ("the operator confirms
    both subscriptions permit supervised first-party-CLI use, same R8 class as OP-9"). It is a
    recorded fact, not a credential and not this build's judgement (invariant 1), which is why the
    caller must pass it and name its basis at the call site instead of inheriting a default from
    here. `profile_loader` is required for the mirror-image reason: the active deployment profile is
    a property of the HOST, and a loader this module manufactures cannot refuse anything (U91)."""
    if provider not in PROBE_PROVIDERS:
        raise ProbeSessionRefused(
            f"{provider!r} is not governed by the OP-12 probe path — this module authorizes "
            f"{'/'.join(PROBE_PROVIDERS)} only; `claude_code` and `openai_codex_cli` have their own "
            f"supervised paths and must not acquire a second one here (fail closed)",
            gate=GATE_UNKNOWN_ADAPTER)

    identity = probe_identity(probe_id)
    node_id = identity["node_id"]
    auth = live_auth if live_auth is not None else load_live_authorization()
    loader = profile_loader
    gov = governor if governor is not None else SubscriptionGovernor()
    led = ledger if ledger is not None else TerminalLeaseLedger(default_ledger_path())

    # (1) whole-roster profile + LIVE_OPERATION_AUTHORIZED / air-gap gate (invariant 20).
    loader.assert_startup([_CAPABILITY[provider]()], live_auth=auth)
    # (2) the primary live gate, re-asserted at the authorization site.
    auth.assert_provider_live(provider)
    # (3) the operator's own R8 §6 live-terms determination.
    if not operator_terms_confirmed:
        raise LiveTermsNotConfirmed(
            f"R8 §6 [OPERATOR] live-terms confirmation not recorded — fail closed, no live "
            f"{provider} probe (directive §10.4)")
    # (4) CLI presence, and the RESOLVED binary: the child must be the file that was gated.
    exc_type, command = _UNAVAILABLE[provider]
    resolved = executable if executable is not None else _resolve_executable(provider)
    present = (resolved is not None) if cli_present is None else bool(cli_present)
    if not present:
        raise exc_type(f"`{command}` CLI not detected on host PATH — cannot open a governed live "
                       f"probe session (fail closed)")
    if not (isinstance(resolved, str) and resolved.strip()):
        raise ProbeSessionRefused(
            f"the {provider} presence gate passed but no executable path was resolved — refuse to "
            f"spawn a bare binary NAME the OS resolves at spawn time: the child must be the file "
            f"that was gated (fail closed)", gate=GATE_BINARY_UNRESOLVED)
    exe = resolved.strip()

    # (5) I-X3. The durable ledger is the authority; seeding projects the terminals OTHER holders
    # (the operator's own shell) already hold into this process's governor, so the gate chain below
    # refuses for their terminals exactly as it does for ours.
    ref = canonical_subscription_ref(provider)
    allowance = auth.terminals_for(provider)          # per-provider cap (OP-12 §12) — 1, never 2
    # One probe run = one session. A node id alone would make a SECOND concurrent probe of the same
    # provider an idempotent re-acquire of the first probe's terminal — it would run uncounted and
    # then release a lease the first probe still needed (U75, from the other end). The governor is
    # therefore counted by LEASE KEY, which is the same convention `seed_governor` projects with.
    sid = str(session_id or "") or uuid.uuid4().hex[:12]
    lease_key = f"{node_id}#{sid}"
    seeded = led.seed_governor(gov, subscription_ref=ref, provider=provider, allowance=allowance)
    gov.acquire(ref, lease_key)

    lease: TerminalLease | None = None
    session: GovernedProbeSession | None = None
    registration = None
    body_error: BaseException | None = None
    try:
        lease = led.acquire(subscription_ref=ref, provider=provider, node_id=node_id,
                            allowance=allowance,
                            holder_pid=int(holder_pid if holder_pid is not None else os.getpid()),
                            purpose=PROBE_LEASE_PURPOSE, session_id=sid)
        session = GovernedProbeSession(
            provider=provider, display=_display(provider), node_id=node_id, session_id=sid,
            permission_profile_id=identity["permission_profile_id"], role=PROBE_ROLE,
            subscription_ref=ref, allowance=allowance, in_use=led.in_use(ref),
            lease_id=lease.lease_id, executable=exe, workspace=str(workspace),
            env_scrub_names=tuple(worker_env_scrub_names(base_env)),
            seeded_from_ledger=tuple(ln.node_id for ln in seeded), _base_env=base_env)
        # (7) the node RECORD — 18D `.close`, the wiring OP-12.1 authorized. It comes LAST because
        # it is not a gate: a record describes a session every gate above has already permitted,
        # and it is written only once the terminal is actually held. A refusal here propagates —
        # the `finally` below hands the lease back — because a session that could not be written
        # down is a session invariant 2 does not admit, and proceeding anyway would produce exactly
        # the naked-but-leased terminal this whole chain exists to prevent.
        if registrar is not None:
            registration = registrar.register_session(session)
            session.node_registered = True
            session.node_record = registration.as_dict()
        yield session
    except BaseException as exc:
        # Captured, not handled: the exit written on the append-only node log must say whether the
        # session ended the way it meant to. It was unconditionally `expected=True, exit_code=None`
        # — so a crashed or contained-failure session read as a clean exit to anyone reading the
        # operator's node history (spec-audit MEDIUM-4). Re-raised immediately; the `finally` below
        # is the only reader.
        body_error = exc
        raise
    finally:
        # The node record is CLOSED first, on every exit path: a one-shot session whose record
        # reads SPAWNING forever is a D-LOOP-1 leak in the one place an auditor looks for it. A
        # failure to close is recorded, never raised — it must not mask the body's own exception,
        # and it must not stop the lease coming back below.
        node_exit_recorded = False
        node_exit_error: str | None = None
        # MEASURED, not assumed: the child's own exit code when one ran, and `expected` false when
        # the body raised or the process-tree boundary reported a containment failure. The lease
        # half of teardown was measured while the node half was asserted — the inverse of the
        # standard this module applies everywhere else.
        node_expected = body_error is None and (session is None or session.process_tree_clean is not False)
        if registrar is not None and registration is not None:
            try:
                registrar.record_exit(registration,
                                      exit_code=None if session is None else session.child_exit_code,
                                      expected=node_expected)
                node_exit_recorded = True
            except Exception as exc:      # noqa: BLE001 — measured, never raised over the body's
                node_exit_error = f"{type(exc).__name__}: {exc}"
        if registrar is not None:
            # The log and its cross-process lock are handed back on every exit path, so a
            # long-lived process neither leaks a handle per probe nor holds the node log against
            # the next one (D-LOOP-1, spec-audit MEDIUM-5).
            try:
                registrar.close()
            except Exception as exc:      # noqa: BLE001 — same rule: measured, never raised
                node_exit_error = node_exit_error or f"close: {type(exc).__name__}: {exc}"
        # Every exit path, in the order that leaves the least behind: durable first (it is what
        # another process can see), then the in-process count, then MEASURE both.
        lease_released = False
        try:
            if lease is not None:
                try:
                    lease_released = led.release(lease.lease_id)
                except (LeaseLedgerCorrupt, LeaseLedgerLocked):
                    lease_released = False   # an unreadable ledger cannot be corrected from here
        finally:
            # UNCONDITIONAL: a durable release that fails in some way this module did not
            # anticipate (the ledger writes files, so `OSError` is reachable) must not carry the
            # in-process slot away with it. A leaked governor slot is a terminal nobody can reclaim
            # without restarting the process.
            gov.release(ref, lease_key)
        if session is not None:
            holders = (gov.status().get(ref) or {}).get("active") or []
            try:
                in_use_after: int | None = led.in_use(ref)
            except (LeaseLedgerCorrupt, LeaseLedgerLocked):
                in_use_after = None
            session.teardown_record = {
                "lease_released": lease_released,
                "governor_released": lease_key not in holders,
                "in_use_after": in_use_after,
                # The PROCESS half of teardown, from the runner's own observation. `None` means no
                # child ran (a refusal, or a body that never spawned) — deliberately not `True`,
                # because "nothing was left behind" and "nothing was checked" are different facts.
                "process_tree_clean": session.process_tree_clean,
                # The node half of teardown, alongside the lease half. False with no error means
                # the caller asked for no record; False WITH an error means one was written and
                # could not be closed, which is the state an auditor must be able to see.
                "node_exit_recorded": node_exit_recorded,
                "node_exit_error": node_exit_error,
                "node_exit_expected": node_expected if registration is not None else None,
                "measured": True,
            }


def _display(provider: str) -> str:
    from adapters.frontier.antigravity import ANTIGRAVITY_DISPLAY  # noqa: PLC0415
    from adapters.frontier.grok_build import GROK_DISPLAY  # noqa: PLC0415

    return {GROK_ADAPTER: GROK_DISPLAY, ANTIGRAVITY_ADAPTER: ANTIGRAVITY_DISPLAY}[provider]


def supervised_probe_runner(session: GovernedProbeSession,
                            timeout_s: float = DEFAULT_PROBE_TIMEOUT_S):
    """A `frontier_provider_recon.Runner` that executes the child under supervision.

    Same boundary the live `claude_code` backend uses: a managed-process boundary that owns the
    whole descendant tree (a Windows job object on the operator's host; a POSIX process group
    elsewhere), so a CLI which spawns helpers (grok's leader/agent processes) cannot leave any
    behind when this returns OR times out — operator directive §12's process-tree termination on
    every exit path. No interactive stdin reaches the child (see the module docstring's note on the
    Windows mechanism, U281), because an inherited non-TTY stdin lets a TUI-capable CLI block
    forever and turns a probe into a timeout.

    **The child is the file the gate resolved.** `argv[0]` must equal `session.executable`, or this
    refuses. Without that line the gate's "refuse to spawn a bare binary NAME" rule protected a
    value nobody spawned: the runner executed whatever argv it was handed, and the two agreed only
    because one call site happened to pass the same string.

    Returns the runner protocol's `(exit_code|None, stdout, stderr, timed_out, spawn_error)` — a
    timeout, a missing binary and a CONTAINMENT failure are REPORTED, not raised, so the probe's
    acceptance logic classifies them (exit-code-first: an exit-0 transcript is never reclassified by
    its text). `ProcessTreeCleanupError` in particular: it is the one signal this boundary exists to
    produce, and letting it escape turned an invariant-29 containment failure into a traceback that
    the PowerShell runner reports to the operator as "a tool failure, not a governed refusal"."""

    def run(argv: Sequence[str]):
        cmd = list(argv)
        if not cmd or cmd[0] != session.executable:
            raise ProbeSessionRefused(
                f"the probe child's argv[0] ({cmd[0] if cmd else None!r}) is not the executable "
                f"this session gated ({session.executable!r}) — refuse to spawn a binary the gate "
                f"never resolved (fail closed)", gate=GATE_BINARY_UNRESOLVED)
        try:
            proc = run_managed_process(cmd, timeout=timeout_s, env=session.child_env(),
                                       stdin=subprocess.DEVNULL, cwd=session.workspace)
        except subprocess.TimeoutExpired:
            session.process_tree_clean = True   # the boundary tore the tree down, then re-raised
            return None, "", "", True, None
        except ProcessTreeCleanupError as exc:
            # Descendants survived the boundary. Recorded as unclean AND surfaced as a spawn_error
            # so the verdict cannot be `accepted` on a run that leaked processes.
            session.process_tree_clean = False
            return None, "", "", False, f"{type(exc).__name__}: {exc}"
        except (FileNotFoundError, OSError) as exc:
            return None, "", "", False, f"{type(exc).__name__}: {exc}"
        session.process_tree_clean = True
        session.spawned_pids = tuple(sorted(set(session.spawned_pids) | set(proc.spawned_pids)))
        # The child's real exit code, so the node record's `exit` row carries it rather than a
        # `None` that reads the same for "ran and returned 0" and "never ran" (spec-audit MEDIUM-4).
        session.child_exit_code = proc.returncode
        return proc.returncode, proc.stdout or "", proc.stderr or "", False, None

    return run
