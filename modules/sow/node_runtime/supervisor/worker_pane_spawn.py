"""Governed LIVE WORKER pane — the ONE place an interactive worker session is authorized from a
picker selection. Phase 17B `.ticket` (directive §16 track 17B; OP-7 §12.2/§12.3; closes the
authorization half of **U70**).

The operator's first-use finding F3: choosing a model on a pane "records + badges but launches
nothing". 16B was honest about that (`governed:false`, `selected_awaiting_governed_spawn`) — the
selection went through the guard and stopped. This module is the worker analogue of
`conductor_pane_spawn`: it turns ONE picker option (provider × model × role × mode) into an
executable, governed, INTERACTIVE launch spec — or a fail-closed refusal.

Why a separate module from `pane_node_spawn.spawn_node_from_selection`: that dispatcher builds a
HEADLESS handle (a `ModelWorkerAdapter` / OpenCode harness the scheduler drives). A pane the operator
watches and types into needs the other shape — argv for an interactive CLI the shell spawns in a
ConPTY. Both apply the SAME selection guard (`assert_selection_spawnable`, extracted so the two can
never drift on greyed/mode/role/naked refusals); this path is then STRICTER, refusing the coding
roles it has no isolated worktree to give (below) — stricter, never laxer.

Gate chain, by locality:

  * **frontier** (every id in `FRONTIER_PANE_ADAPTERS`: `claude_code`, `openai_codex_cli`, and
    since 18B `.picker` the OP-12 pair `grok_build` + `google_antigravity`) — the identical live chain the conductor pane
    runs: `ProfileLoader.assert_startup([capability], live_auth)` (roster eligibility AND the
    LIVE_OPERATION_AUTHORIZED / air-gap gate, invariant 20) → `assert_provider_live` → R8 §6 operator
    terms → CLI presence → I-X3 `acquire` on the subscription. A refusal at any step releases nothing
    it did not take, and `teardown()` hands the terminal back (D-LOOP-1).
  * **local** (`ollama_local`) — NOT subscription-governed (invariant 19: locality is per-node; the
    subscription governor governs frontier subscriptions only) and credential-free. What governs it
    is invariant 22: the model MUST route through the `ResidencyPlanner`, which refuses an unsized or
    over-budget model, and this path additionally refuses one that would only fit by DISPLACING a
    model the Ollama daemon is already serving — the planner is a bookkeeping mirror, it does not own
    the host's VRAM, and "never mid-generation eviction" cannot be enforced against a `generating`
    flag that the host seeding never sets. The residency state is carried into the chrome so
    "loading" is never displayed as "ready", and the BUDGET's provenance travels with it. The budget
    is ALWAYS `estimate:true` — an operator-supplied `SOW_VRAM_BUDGET_MB` is a figure some process
    stated, not a queried GPU capacity, so it is a stand-in with a better source, not a measurement.
    `budget_source` says which. No authorization here ever claims the fit was proven (spec-audit
    MINOR-2, 2026-07-26: the previous wording implied `estimate:false` was reachable; it is not).

Honesty rules this module will not bend:
  * the chrome badge's LABEL and `model_verified` are carried verbatim from the picker option
    (invariant 3) — `model_verified` is never upgraded here, only a live reply can do that. The
    `model_slug` is deliberately NOT verbatim: it is the id the CLI was probed to accept, which can
    differ from the label's spelling (`fable-5` → `claude-fable-5`), and both are shown;
  * a requested slug that is not available resolves to the CLI default and is RECORDED as a fallback
    (`is_fallback`, directive §11 15B) — never silently substituted;
  * this module makes NO live model call and reads NO credential: it builds argv, counts terminals
    and reserves VRAM. The ConPTY spawn is the shell's, under the authorization this produces.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from adapters.frontier.antigravity import (
    ANTIGRAVITY_ADAPTER,
    build_interactive_antigravity_command,
)
from adapters.frontier.claude_code import (
    CLAUDE_CODE_ADAPTER,
    build_interactive_command,
)
from adapters.frontier.claude_code import is_credential_env_key as _claude_credential_key
from adapters.frontier.codex import (
    CODEX_ADAPTER,
    SANDBOX_READ_ONLY,
    build_interactive_codex_command,
    resolve_codex_model_ref,
)
from adapters.frontier.codex import is_credential_env_key as _codex_credential_key
from adapters.frontier.grok_build import GROK_ADAPTER, build_interactive_grok_command
from adapters.frontier.provider_cli_common import (
    is_provider_credential_env_key as _op12_credential_key,
)
from adapters.local.ollama_session import (
    OLLAMA_LOCAL_ADAPTER,
    build_interactive_ollama_command,
)
from adapters.local.llamacpp import (
    LLAMACPP_LOCAL_ADAPTER,
    build_interactive_llamacpp_command,
)
from control_plane.local_only import frontier_disabled, LOCAL_ONLY_REASON
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import ProfileLoader
from node_runtime.supervisor.codex_spawn import CodexCliUnavailable, capability_for_codex
from node_runtime.supervisor.frontier_provider_spawn import (
    AntigravityCliUnavailable,
    GrokCliUnavailable,
    capability_for_antigravity,
    capability_for_grok,
)
from node_runtime.supervisor.frontier_spawn import (
    ClaudeCliUnavailable,
    LiveTermsNotConfirmed,
    capability_for_claude_code,
)
from node_runtime.supervisor.pane_node_spawn import (
    PaneSelection,
    SpawnRefused,
    assert_selection_spawnable,
)
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor
from adapters.coding.opencode.harness import OpenCodeCliHarness
from adapters.coding.opencode.session import (
    OPENCODE_LOCAL_ADAPTER,
    build_interactive_opencode_command,
)
from scheduler.residency_planner.residency_planner import (
    LOADING,
    RESIDENT,
    UNKNOWN,
    ResidencyDecision,
    ResidencyError,
    ResidencyPlanner,
)

#: The worker roles a PANE can be born under. `conductor` is refused by the shared selection guard.
WORKER_ROLES = ("reasoning", "coding")

#: Every frontier adapter this module can authorize an INTERACTIVE pane for. One tuple, so the
#: dispatch, the unknown-adapter refusal message and the per-provider tables below cannot disagree
#: about which providers are wired — the drift that would show up as a provider the dispatcher
#: accepts and a message that says it does not.
FRONTIER_PANE_ADAPTERS: tuple[str, ...] = (
    CLAUDE_CODE_ADAPTER, CODEX_ADAPTER, GROK_ADAPTER, ANTIGRAVITY_ADAPTER,
)

#: adapter → (capability factory, presence-exception type, human command name). The exception type
#: is per provider because operator directive §14 forbids printing one provider's failure text under
#: another's name; making it a TYPE rather than a formatted string means the wrong one cannot be
#: raised by a copy-paste that keeps the old message.
_FRONTIER_PROVIDER_GATES: dict[str, tuple[Any, type[Exception], str]] = {
    CLAUDE_CODE_ADAPTER: (capability_for_claude_code, ClaudeCliUnavailable, "claude"),
    GROK_ADAPTER: (capability_for_grok, GrokCliUnavailable, "grok"),
    ANTIGRAVITY_ADAPTER: (capability_for_antigravity, AntigravityCliUnavailable, "agy"),
    # codex is absent DELIBERATELY: its capability is per-ROLE (`capability_for_codex(role)`), so it
    # takes the role-aware branch below rather than a zero-argument factory. Listing it here with a
    # lambda would hide that difference behind a uniform-looking table.
}

#: What a shell-supplied pane id may contain before it becomes a node id / durable lease key. `#` is
#: deliberately EXCLUDED: it is the `lease_key` delimiter (`node_id#session_id`), so a pane id
#: carrying one lets two different (pane, session) pairs produce the same key (spec-audit / validator
#: FINDING 7).
_PANE_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")

#: What a pane's chrome reports before the shell has spawned anything. NOT "ready": this function
#: returns an AUTHORIZATION, `containment.supervisor_bound` is false in the same ticket, and no
#: process exists yet — "ready" is a live-node state asserted about a node that has not been born
#: (invariant 3/27, spec-audit MINOR-1).
#:
#: It applies to BOTH branches. The local branch used to derive its state from the residency
#: decision, and three artifacts (this comment's predecessor, a test docstring, the .ticket evidence
#: report §E) called that "already honest". It was not: deriving is not the same as being true, and
#: what it derived from is a fact about a MODEL, not about a node. The scheduled-load case read
#: "loading", which was harmless enough to hide the reachable case — an already-resident model, which
#: is what every `/api/ps` entry is seeded to on this host, reported "ready" for a node that does not
#: exist (spec-audit MAJOR-1, 2026-07-26). The residency fact keeps `chrome.residency`, where it is
#: true; `node_state` says what this call actually established.
_AUTHORIZED_NOT_STARTED = "launch_authorized"


#: Machine-readable gate ids. A refusal names WHICH gate said no, so an in-runtime receipt leg can
#: assert the gate it claims to prove instead of grepping the prose for a word another gate's message
#: might also contain (gate-validator BLOCKING-1c, 2026-07-26).
GATE_WORKER_ROLE = "worker_role"          # pane identity / role minting
GATE_ROLE_DEFERRED = "role_deferred"      # a role this build has no isolated worktree to give
GATE_WORKTREE_UNAVAILABLE = "worktree_unavailable"
GATE_OPENCODE_ABSENT = "opencode_absent"
GATE_SUBSCRIPTION_REF = "subscription_ref"  # a frontier selection that would be uncounted (I-X3)
GATE_RUNTIME_ABSENT = "runtime_absent"    # the local runtime is not launchable on this host
#: invariant 22, the FIT decision: this model does not fit the budget as the snapshot reports it
#: (unknown footprint, larger than the whole budget, or only fits by displacing a resident model).
GATE_VRAM_ADMISSION = "vram_admission"
#: invariant 22, the PROVENANCE failure: there is no trustworthy budget to decide a fit AGAINST.
#: Deliberately DISTINCT from the fit gate. One id for both let a receipt leg named "a pane that
#: does not fit VRAM is refused" go green on a budget the host had falsified — nothing was measured
#: and nothing about fit was proven. That is the same borrowed-evidence defect the gate ids were
#: introduced to stop, one level down: cross-FAMILY borrowing was closed, intra-family was not
#: (spec-audit MAJOR-1, 2026-07-26).
GATE_VRAM_BUDGET = "vram_budget_unestablished"
#: invariant 22, the model's own provenance: the snapshot carries no usable footprint / free-VRAM
#: figure, so the fit cannot be DECIDED at all. Also not the fit gate — "we could not tell" is not
#: "it does not fit", and it sat inside `vram_admission` after the first split (validator MINOR-1).
GATE_VRAM_FOOTPRINT = "vram_footprint_unknown"
#: the ticket would DISCLOSE a budget the planner does not enforce. The budget here WAS established;
#: what failed is the wiring between the two, so stamping it `vram_budget_unestablished` asserts
#: something false about the refusal — the same intra-family borrowing the split above ended
#: (spec-audit MAJOR-2, 2026-07-26).
GATE_VRAM_BUDGET_MISMATCH = "vram_budget_mismatch"
GATE_UNKNOWN_ADAPTER = "unknown_adapter"  # outside the OP-6 + local scope
#: the resolved binary disagreed with the gate that was told the CLI is present (fail-closed)
GATE_BINARY_UNRESOLVED = "binary_unresolved"
GATE_LOCAL_ONLY = "local_only_policy"


class WorkerPaneRefused(Exception):
    """A governed worker-pane authorization refused fail-closed by this coordinator: a naked or
    unknown identity/role, a frontier selection with no subscription_ref (an uncounted terminal
    defeats I-X3), an absent local runtime, a model whose VRAM cannot be proven, or a path this
    build has deliberately deferred (local coding).

    `gate` is the machine-readable id of the check that refused (the `GATE_*` constants above).

    Distinct from the live gates' own exceptions (`LiveAuthorizationError`, `ProfileViolation`,
    `LiveTermsNotConfirmed`, `ClaudeCliUnavailable`, `CodexCliUnavailable`,
    `SubscriptionLimitExceeded`) and from `SpawnRefused` (the shared SELECTION guard) — both of
    which propagate unchanged, because each is a different gate saying no."""

    def __init__(self, message: str, *, gate: str = "worker_pane") -> None:
        super().__init__(message)
        self.gate = gate


def worker_identity(pane_id: str, role: str) -> dict[str, str]:
    """The governed identity a worker pane's session runs under — minted HERE, never by the shell.

    Deterministic and derived only from (pane, role): the shell asks for a pane's node, it does not
    get to choose what that node is called or what permission profile it carries (invariant 2/29 —
    a session with a self-chosen identity is a naked session with extra steps). The PANE id is the
    one shell-supplied ingredient, so it is bounded to a conservative charset before it can become a
    node id and enter the durable lease ledger: a lease key carrying whitespace, a path separator or
    an unbounded string is a key nobody can reliably reclaim by (spec-audit MINOR-10)."""
    pid = str(pane_id or "").strip()
    if not pid:
        raise WorkerPaneRefused("a worker pane needs a pane id to mint a node identity — fail closed",
                               gate=GATE_WORKER_ROLE)
    if not _PANE_ID_RE.fullmatch(pid):
        raise WorkerPaneRefused(
            f"pane id {pid!r} is not a safe node-identity component — expected 1..64 chars of "
            f"[A-Za-z0-9._-] (fail closed: a node id lands in the durable I-X3 ledger as a key, and "
            f"`#` is that key's own delimiter)", gate=GATE_WORKER_ROLE)
    if role not in WORKER_ROLES:
        raise WorkerPaneRefused(
            f"unknown worker role {role!r} — expected {'|'.join(WORKER_ROLES)} (the conductor role "
            f"is born by the dedicated conductor-first path, fail closed)", gate=GATE_WORKER_ROLE)
    return {"node_id": f"worker-{pid}", "permission_profile_id": f"pp-worker-{role}"}


def worker_env_scrub_names(base_env: dict[str, str] | None = None, *,
                           shell_env_names: list[str] | None = None) -> list[str]:
    """The NAMES of the credential/endpoint-bearing vars the shell must drop from the child env.

    §2.2 in the strictest reading: names, never values — the shell already holds its own environment,
    so a name is all it needs to drop one. The UNION of ALL THREE frontier classifiers (claude,
    codex, and the shared OP-12 one covering `XAI_*` / `GEMINI_*` / `GOOGLE_*` / `ANTIGRAVITY_*` —
    operator directive §13) is used for EVERY worker locality, including local: a superset can only
    over-scrub (a local model needs no cloud credential at all), while a per-provider list would
    leave the other provider's key in the child env of a session that has no business seeing it.
    The OP-12 classifier was added with the providers themselves rather than after: a `grok` pane
    launched before the union included `XAI_API_KEY` would have inherited exactly the variable §13
    names first.

    `shell_env_names` are the var NAMES the CONSUMER holds, unioned in before classification (U105).
    Measuring the list in the EMITTER's environment and applying it to the SHELL's was sound only
    while the two environments matched — and 17B itself made divergence reachable, because a per-child
    `opts.env` is how the `.ticket` self-check scrubs PATH. Two concrete ways the emitter's list can
    miss a key the shell holds: (1) the shell was launched with a credential var the emitter's child
    env does not carry; (2) Windows preserves the CASE a var was created with while this classifier
    upper-cases, so `Anthropic_Api_Key` in the shell and `ANTHROPIC_API_KEY` here classify the same
    but are two different literal keys, and the shell deletes by exact spelling. Names only — a
    caller-supplied entry is never read for a value, and the emitter refuses any `name=value` pair."""
    env = os.environ if base_env is None else base_env
    names = set(env)
    if shell_env_names:
        names |= {n for n in shell_env_names if isinstance(n, str) and n}
    return sorted(k for k in names
                  if _claude_credential_key(k) or _codex_credential_key(k)
                  or _op12_credential_key(k))


@dataclass
class WorkerPaneChrome:
    """The worker pane chrome the shell renders: model badge, role, mode, node state, and EITHER a
    subscription view (frontier, n/allowance) OR a residency state (local, invariant 22). `governed`
    is always True — a naked session never reaches chrome; `interactive` is always True — this is a
    pane the operator watches, not a headless one-shot."""

    provider: str
    adapter: str
    locality: str                          # frontier | local
    model_label: str                       # the picker option's label, verbatim
    model_slug: str | None                 # the argv slug; None ⇒ CLI default (recorded fallback)
    model_verified: bool                   # carried from the option — never upgraded here
    is_fallback: bool
    role: str
    mode: str                              # attended | autonomous (a label, NOT an authority grant)
    node_id: str
    node_state: str
    subscription: dict[str, Any] | None    # {ref, in_use, allowance} (frontier) | None (local)
    residency: str | None                  # residency state (local) | None (frontier)
    governed: bool = True
    interactive: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider, "adapter": self.adapter, "locality": self.locality,
            "model_label": self.model_label, "model_slug": self.model_slug,
            "model_verified": self.model_verified, "is_fallback": self.is_fallback,
            "role": self.role, "mode": self.mode, "node_id": self.node_id,
            "node_state": self.node_state, "governed": self.governed,
            "interactive": self.interactive,
            "subscription": dict(self.subscription) if self.subscription is not None else None,
            "residency": self.residency,
        }


@dataclass
class WorkerPaneSession:
    """A governed worker-pane AUTHORIZATION: the chrome, the interactive launch spec the shell
    executes, the residency decision for a local model (None for frontier), and a teardown that
    releases the governed I-X3 count (D-LOOP-1; a no-op for a local node, which holds none)."""

    chrome: WorkerPaneChrome
    launch: dict[str, Any]
    #: The permission profile the identity was minted with (`worker_identity`). Carried on the
    #: SESSION rather than only on the selection because the node RECORD written for this pane
    #: names it (schema `node@1.1` requires it), and a registrar reading it off a selection object
    #: the caller still holds would be reading the caller's copy, not the authorization's.
    permission_profile_id: str | None = None
    residency_decision: dict[str, Any] | None = None
    #: provenance of the VRAM budget the local decision was made against ({vram_budget_mb,
    #: budget_source, estimate, …}); None for a frontier pane. Carried so the ticket can DISCLOSE an
    #: authorization made against an estimated budget instead of implying the fit was proven.
    residency_budget: dict[str, Any] | None = None
    subscription_governed: bool = False
    _release: Callable[[], None] | None = field(default=None, repr=False)

    def teardown(self) -> None:
        if self._release is not None:
            self._release()


def _resolved_binary(resolved: str | None, adapter_id: str) -> str:
    """The RESOLVED binary path, or a refusal — never a bare name.

    `exe = resolved or "claude"` was a fail-OPEN: when `cli_present` was injected True while
    detection returned nothing, the ticket carried a bare `claude`/`codex`/`ollama` and the shell
    PATH-searched it, contradicting this module's own claim that "the shell spawns exactly what was
    gated" and the renderer's allowlist, which compares the basename of a path that was supposed to
    have been resolved. Unreachable on today's product path only because presence is DEFINED as
    "executable is not None" — an undefended coupling (spec-audit MINOR-4, 2026-07-26)."""
    if isinstance(resolved, str) and resolved.strip():
        return resolved
    raise WorkerPaneRefused(
        f"the {adapter_id} presence gate passed but no executable path was resolved — refuse to "
        f"emit a bare binary NAME for the shell to PATH-search: the launch must be the file that "
        f"was gated, not whatever answers to that name at spawn time (fail closed)",
        gate=GATE_BINARY_UNRESOLVED)


#: Flags a launch note does NOT describe, and the only ones. An EXCLUSION list, not an inclusion
#: list, because round 2 of this unit's own review found the inclusion version failing OPEN: a flag
#: nobody had thought to enumerate — `--allow`, `--no-plan`, `--plugin-dir`, or whatever the next
#: provider brings — was silently omitted from the operator's ticket, which is exactly how the
#: widening this unit reverted would have travelled undisclosed. The two groups here are what a
#: note must not repeat: the model slug (the chrome carries it WITH its fallback disclosure, and a
#: second copy is a second place to be wrong) and the prompt/output plumbing, which says nothing
#: about authority. Everything else in the argv is disclosed by DEFAULT.
_NOTE_SILENT_FLAGS: frozenset[str] = frozenset({
    "-m", "--model",                                      # the chrome's job, with its fallback note
    "-p", "--single", "--print", "--prompt", "--prompt-file", "--prompt-json",
    "--output-format",
})


def describe_pinned_flags(argv: list[str], *, workspace: str | None = None) -> str:
    """The pins this launch ACTUALLY carries, READ OFF the argv the note is attached to.

    Phase 19 unit 1, from the gate-validator's MAJOR-1 and the spec-auditor's MAJOR-1 on the OP-13
    revert. These notes used to be hand-written prose, and the untagged post-18E range edited them
    to match the widened argv it shipped: `--mode accept-edits` for Antigravity and "plan disabled"
    for Grok. Reverting the argv alone would have left the launch TICKET — which is what the
    receipts and the shell surface show the operator — advertising a mode the operator had just
    forbidden, with nothing in 2262 tests able to see the contradiction, because a sentence cannot
    disagree with a list it was never derived from.

    So it is derived now, in BOTH directions — and the second direction is the one round 2 of this
    unit's review had to fix. The first version rendered an ENUMERATED set of noteworthy flags: it
    could not over-claim, but it could silently under-claim, and the flags it would have omitted
    include `--allow` and `--no-plan`, i.e. precisely the half of the widening this unit reverted.
    Disclosure that fails open is not disclosure (gate-validator MEDIUM-1, spec-audit MEDIUM-1 /
    NIT-9). What is rendered is now every flag in the argv EXCEPT `_NOTE_SILENT_FLAGS`, and
    `tests/unit/test_worker_ticket_honesty.py` walks it both ways.

    Invariant 27 (the orchestra is visible) and build directive §4: routing rationale is
    observable, which means TRUE and COMPLETE, not merely present."""
    ws = workspace.strip() if isinstance(workspace, str) else None
    parts: list[str] = []
    i = 1                                        # argv[0] is the executable, never a pin
    while i < len(argv):
        tok = argv[i]
        i += 1
        if not tok.startswith("-") or tok in _NOTE_SILENT_FLAGS:
            continue
        nxt = argv[i] if i < len(argv) else None
        if nxt is not None and not nxt.startswith("-"):
            i += 1
            if ws and nxt.strip() == ws:
                parts.append(f"{tok} scoped to the authorized workspace")
            else:
                parts.append(f"{tok} {nxt}")
            continue
        parts.append(tok)
    return ", ".join(parts) if parts else "no pinned flags"


def _launch(argv: list[str], *, executable: str, cwd: str, note: str,
            shell_env_names: list[str] | None = None) -> dict[str, Any]:
    return {
        "argv": list(argv),
        "executable": executable,
        "cwd": str(cwd),
        "interactive": True,
        "one_shot": False,
        "env_credential_scrubbed": True,
        # names only, never values (§2.2) — the shell drops these from its own environment. Classified
        # over the union of THIS process's env and the names the shell reported holding (U105).
        "env_scrub_names": worker_env_scrub_names(shell_env_names=shell_env_names),
        "note": note,
    }


def authorize_worker_pane(
    selection: PaneSelection,
    *,
    live_auth: LiveAuthorization,
    governor: SubscriptionGovernor,
    profile_loader: ProfileLoader,
    operator_terms_confirmed: bool,
    workspace: str,
    residency_planner: ResidencyPlanner | None = None,
    residency_budget: dict[str, Any] | None = None,
    worktree_manager: Any = None,
    model: str | None = None,
    model_available: bool | None = None,
    cli_present: bool | None = None,
    ollama_present: bool | None = None,
    llamacpp_present: bool | None = None,
    executable: str | None = None,
    shell_env_names: list[str] | None = None,
) -> WorkerPaneSession:
    """Authorize ONE picker selection as a live, governed, interactive WORKER pane session.

    `model` overrides the argv slug (the probed, actually-accepted id — 17A's model probe); omitted ⇒
    the option's own `model_slug`. `model_available=False` records the CLI-default FALLBACK branch.
    `cli_present`/`ollama_present` inject host detection for the deterministic suite; None ⇒ the real
    host probe. `executable` is the RESOLVED binary the presence gate found (a ConPTY spawn takes a
    file, not a PATH search); omitted ⇒ resolved here. `shell_env_names` are the env var NAMES the
    consuming shell holds, unioned into the classifier (U105 — see `worker_env_scrub_names`).

    Raises `SpawnRefused` (selection), `WorkerPaneRefused` (identity/locality/residency), or the
    gates' own exceptions. Makes NO live model call."""
    assert_selection_spawnable(selection)      # the ONE shared guard (greyed / mode / role / naked)
    opt = selection.option
    adapter_id = opt.get("adapter")
    if adapter_id in FRONTIER_PANE_ADAPTERS:
        if frontier_disabled(adapter_id):
            raise WorkerPaneRefused(f"{LOCAL_ONLY_REASON}: {adapter_id!r} cannot be spawned",
                                    gate=GATE_LOCAL_ONLY)
        return _authorize_frontier(
            selection, adapter_id=adapter_id, live_auth=live_auth, governor=governor,
            profile_loader=profile_loader, operator_terms_confirmed=operator_terms_confirmed,
            workspace=workspace, model=model, model_available=model_available,
            cli_present=cli_present, executable=executable, shell_env_names=shell_env_names)
    if adapter_id == OPENCODE_LOCAL_ADAPTER:
        # EPC-04. A distinct ADAPTER, not a role variant of `ollama_local`: both run a local model,
        # but one is a REPL and the other is a harness with write hands inside a worktree. Routed
        # straight to the coding authorizer so the pane cannot be reached with the reasoning
        # path's assumptions — in particular, without a worktree.
        return _authorize_local_coding(
            selection, residency_planner=residency_planner, residency_budget=residency_budget,
            worktree_manager=worktree_manager, shell_env_names=shell_env_names)
    if adapter_id == OLLAMA_LOCAL_ADAPTER:
        return _authorize_local(
            selection, workspace=workspace, residency_planner=residency_planner,
            residency_budget=residency_budget, ollama_present=ollama_present, executable=executable,
            shell_env_names=shell_env_names, worktree_manager=worktree_manager)
    if adapter_id == LLAMACPP_LOCAL_ADAPTER:
        return _authorize_llamacpp_local(
            selection, workspace=workspace, residency_planner=residency_planner,
            residency_budget=residency_budget, llamacpp_present=llamacpp_present,
            executable=executable, shell_env_names=shell_env_names)
    raise WorkerPaneRefused(
        f"unknown adapter {adapter_id!r} in selection — this build authorizes live panes for "
        f"{'/'.join(sorted(FRONTIER_PANE_ADAPTERS))} (OP-6 + OP-12 scope) and "
        f"{OLLAMA_LOCAL_ADAPTER}/{LLAMACPP_LOCAL_ADAPTER}/{OPENCODE_LOCAL_ADAPTER} only (fail closed; a new provider "
        f"needs a new operator "
        f"authorization)", gate=GATE_UNKNOWN_ADAPTER)


# ---- frontier: subscription-governed, I-X3-counted ---------------------------------------------

def _resolve_frontier_executable(adapter_id: str) -> str | None:
    """The RESOLVED binary for one frontier adapter, from `adapters.detect` — the module that owns
    host detection. One mapping, so a provider added to `FRONTIER_PANE_ADAPTERS` without a resolver
    raises a KeyError here (loudly, before any gate mutation) instead of silently falling through to
    another provider's binary. The import is function-local, matching this module's existing
    convention for `detect`."""
    from adapters import detect  # noqa: PLC0415

    resolvers = {
        CLAUDE_CODE_ADAPTER: detect.claude_code_executable,
        CODEX_ADAPTER: detect.codex_executable,
        GROK_ADAPTER: detect.grok_executable,
        ANTIGRAVITY_ADAPTER: detect.antigravity_executable,
    }
    return resolvers[adapter_id]()


def _authorize_frontier(
    selection: PaneSelection,
    *,
    adapter_id: str,
    live_auth: LiveAuthorization,
    governor: SubscriptionGovernor,
    profile_loader: ProfileLoader,
    operator_terms_confirmed: bool,
    workspace: str,
    model: str | None,
    model_available: bool | None,
    cli_present: bool | None,
    executable: str | None,
    shell_env_names: list[str] | None = None,
) -> WorkerPaneSession:
    opt = selection.option
    if not selection.subscription_ref:
        raise WorkerPaneRefused(
            f"frontier selection {adapter_id!r} has no subscription_ref — refuse to authorize an "
            f"uncounted terminal (I-X3, fail closed)", gate=GATE_SUBSCRIPTION_REF)
    role = selection.role
    # A frontier CODING pane would write with the model's own hands; Phase 10 gives it an isolated
    # worktree and this authorization has no worktree to give (the pane's cwd is the project
    # workspace). Refused as DEFERRED, not unavailable — the reason names what would unblock it.
    if role == "coding":
        raise WorkerPaneRefused(
            f"a live {adapter_id} CODING pane needs its own isolated git worktree to write in "
            f"(Phase 10 / T2) — this authorization binds the session to the project workspace, so "
            f"the coding role is DEFERRED here, not unavailable: route it through the worktree-"
            f"isolated coding path (U95)", gate=GATE_ROLE_DEFERRED)

    # (1) whole-roster profile + LIVE_OPERATION_AUTHORIZED / air-gap gate (invariant 20).
    cap = (capability_for_codex(role) if adapter_id == CODEX_ADAPTER
           else _FRONTIER_PROVIDER_GATES[adapter_id][0]())
    profile_loader.assert_startup([cap], live_auth=live_auth)
    # (2) primary live gate re-asserted at the authorization site.
    live_auth.assert_provider_live(adapter_id)
    # (3) R8 §6 operator live-terms confirmation (OP-9; the operator's determination, not ours).
    if not operator_terms_confirmed:
        raise LiveTermsNotConfirmed(
            f"R8 §6 [OPERATOR] live-terms confirmation not recorded — fail closed, no live "
            f"{adapter_id} worker pane (directive §10.4)")
    # (4) CLI presence — and RESOLVE the binary, so the shell spawns exactly what was gated. The
    # resolver and the exception are BOTH per provider (operator directive §14): a missing `agy`
    # must not surface as a `claude` problem, and the resolver must be the one whose candidate list
    # covers that CLI's own Windows shim spellings.
    resolved = executable or _resolve_frontier_executable(adapter_id)
    present = (resolved is not None) if cli_present is None else bool(cli_present)
    if not present:
        exc_type, command = (CodexCliUnavailable, "codex") if adapter_id == CODEX_ADAPTER \
            else (_FRONTIER_PROVIDER_GATES[adapter_id][1], _FRONTIER_PROVIDER_GATES[adapter_id][2])
        raise exc_type(
            f"`{command}` CLI not detected on host PATH — cannot open a live worker pane "
            f"(fail closed)")
    exe = _resolved_binary(resolved, adapter_id)

    # (5) I-X3: register the authorized allowance, then acquire this pane's ONE terminal.
    ref = selection.subscription_ref
    node_id = selection.node_id
    governor.register_subscription(ref, adapter_id,
                                   allowance=live_auth.terminals_for(adapter_id))
    governor.acquire(ref, node_id)
    try:
        requested = model if model is not None else opt.get("model_slug")
        # A slug PROBED unavailable resolves to the CLI default and is RECORDED as a fallback — the
        # 17A `.roundtrip` lesson: launching the operator's selection LABEL as a slug produces a live
        # session that cannot answer anything.
        if model_available is False:
            requested = None
        if adapter_id == CLAUDE_CODE_ADAPTER:
            slug = requested.strip() if isinstance(requested, str) and requested.strip() else None
            argv = build_interactive_command(exe, model=slug)
            note = ("interactive `claude` worker session (no -p) in a governed pane; the shell "
                    "spawns it in the pane's ConPTY under this authorization")
        elif adapter_id == GROK_ADAPTER:
            # The slug is carried verbatim from an option built out of `grok models` — the CLI's own
            # listing — so there is no label-to-slug resolution step to get wrong here (17A's
            # `.roundtrip` failure needed one; this provider publishes its ids). None ⇒ CLI default,
            # recorded as a fallback by the chrome below exactly as the other providers do.
            slug = requested.strip() if isinstance(requested, str) and requested.strip() else None
            argv = build_interactive_grok_command(exe, model=slug, workdir=str(workspace))
            note = (f"interactive `grok` TUI worker session (no -p, "
                    f"{describe_pinned_flags(argv, workspace=str(workspace))}); the shell spawns "
                    f"it in the pane's ConPTY under this authorization")
        elif adapter_id == ANTIGRAVITY_ADAPTER:
            slug = requested.strip() if isinstance(requested, str) and requested.strip() else None
            argv = build_interactive_antigravity_command(exe, model=slug, workdir=str(workspace))
            note = (f"interactive `agy` TUI worker session (no -p, "
                    f"{describe_pinned_flags(argv, workspace=str(workspace))}; the workspace is "
                    f"also the ConPTY's working directory — this CLI has no working-directory "
                    f"flag); the shell spawns it in the pane's ConPTY")
        else:
            slug, _resolve_note = resolve_codex_model_ref(
                requested if isinstance(requested, str) else None)
            argv = build_interactive_codex_command(
                exe, model=slug, sandbox=SANDBOX_READ_ONLY, workdir=str(workspace))
            note = ("interactive `codex` worker session (no `exec`, read-only sandbox, --cd scoped "
                    "to the authorized workspace); the shell spawns it in the pane's ConPTY")
        status = governor.status().get(ref, {})
        chrome = WorkerPaneChrome(
            provider=opt.get("provider", adapter_id), adapter=adapter_id, locality="frontier",
            model_label=opt.get("label", ""), model_slug=slug,
            model_verified=bool(opt.get("verified", False)),
            is_fallback=slug is None, role=role, mode=selection.mode, node_id=node_id,
            node_state=_AUTHORIZED_NOT_STARTED,
            subscription={"ref": ref, "in_use": governor.active_count(ref),
                          "allowance": status.get("allowance",
                                                  live_auth.terminals_for(adapter_id))},
            residency=None)
        launch = _launch(argv, executable=exe, cwd=str(workspace), note=note,
                         shell_env_names=shell_env_names)
    except Exception:
        governor.release(ref, node_id)         # never wedge the I-X3 count
        raise
    return WorkerPaneSession(chrome=chrome, launch=launch, residency_decision=None,
                             permission_profile_id=selection.permission_profile_id,
                             subscription_governed=True,
                             _release=lambda: governor.release(ref, node_id))


# ---- local: VRAM-residency-governed, never subscription-governed --------------------------------

def _assert_fits_without_displacing(planner: ResidencyPlanner, model: str) -> None:
    """Refuse, WITHOUT mutating the planner, a local pane that could only fit by displacing another
    model (invariant 22).

    Why this is a refusal and not a scheduled swap: this planner is a bookkeeping MIRROR of the
    Ollama daemon's residency, not its allocator. The host seeding marks models resident but never
    sets `generating`, so the planner's own "evict only idle models" rule is evaluated against a flag
    nothing populates — a model it considers idle may be answering a prompt right now, and invariant
    22 states "never mid-generation eviction" in absolute terms. So a local pane is authorized only
    when it fits in FREE VRAM. Deliberate consequence: on a busy host the operator gets an honest
    "no room" instead of a pane whose birth silently reclaimed VRAM from a model in use.

    Decided from the planner's own read-only snapshot, so a refusal leaves no phantom LOADING entry
    or evicted model in the residency view the operator sees (validator FINDING 3)."""
    snap = planner.snapshot()
    entry = next((m for m in snap.get("models", []) if m.get("model") == model), None)
    if entry is None:
        return   # unknown footprint — `request_load` raises ResidencyError, handled by the caller
    if entry.get("status") in (RESIDENT, LOADING):
        return   # already in VRAM: re-requesting it displaces nothing
    footprint = entry.get("footprint_mb")
    free = snap.get("free_vram_mb")
    total = snap.get("total_vram_mb")
    used = snap.get("used_vram_mb")
    if not isinstance(footprint, int) or not isinstance(free, int) or footprint > free:
        # State the cause the snapshot actually shows. The one message used to assert "would only fit
        # by displacing another resident model" for every over-budget case — including one where
        # NOTHING is resident and the budget is simply smaller than the model, which is a different
        # fact and a different fix for the operator (validator MINOR-1).
        if not isinstance(footprint, int) or not isinstance(free, int):
            raise WorkerPaneRefused(
                f"a local pane for {model!r} has no usable footprint/free-VRAM figure in the "
                f"residency snapshot ({footprint!r}/{free!r}), so the fit cannot be DECIDED at all "
                f"— refused fail-closed. This is a gap in what the host reported, not a finding "
                f"about the model's size (invariant 22)",
                gate=GATE_VRAM_FOOTPRINT)
        if isinstance(total, int) and footprint > total:
            cause = (f"is larger than the whole {total}MB VRAM budget, so it can never be resident "
                     f"under it — nothing needs to be displaced for this to fail")
        else:
            cause = (f"would only fit by displacing another resident model (free VRAM {free}MB of "
                     f"{total}MB, {used}MB in use)")
        raise WorkerPaneRefused(
            f"a local pane for {model!r} ({footprint}MB) {cause} — this planner mirrors the Ollama "
            f"daemon's residency, it does not own the host's VRAM, and it cannot tell whether a "
            f"resident model is mid-generation (invariant 22). Refused: free VRAM on the host, or "
            f"set SOW_VRAM_BUDGET_MB if the budget is understated (U96)",
            gate=GATE_VRAM_ADMISSION)


def _reserve_local_vram(residency_planner: ResidencyPlanner | None,
                        residency_budget: dict[str, Any] | None,
                        model: str,
                        build_argv: Any) -> tuple[list[str], Any, dict[str, Any]]:
    """The invariant-22 reservation every LOCAL pane takes, in ONE place.

    EPC-04 extracted this when the OpenCode coding pane became a second caller. It is
    deliberately shared rather than copied: `module_source_registry` states the house rule
    that "a second literal elsewhere is how a provider ends up in one list and not the
    other", and two copies of a VRAM gate is that shape with worse consequences — two
    paths that disagree about whether a model fits the card.

    `build_argv` is a CALLABLE rather than a finished list on purpose. The ordering below
    is load-bearing (validator FINDING 3): argv must be built side-effect-free BEFORE
    `request_load` mutates, because the planner has no cancel primitive and a refusal
    after it leaves a phantom residency entry in the view the operator reads. Passing a
    callable keeps that ordering INSIDE the helper instead of trusting each caller to
    remember it.

    Returns `(argv, decision, budget)`. Every refusal, and its gate id, is unchanged.
    """
    budget = residency_budget or {}
    if residency_planner is None or budget.get("established") is not True:
        # Repeat the enumeration's own reason: a bare "no planner supplied" reads as an internal
        # wiring fault and hides the one-line fix, and it must never be mistaken for "the model does
        # not fit" — nothing was measured.
        why = str(budget.get("budget_source")
                  or ("no planner supplied" if residency_planner is None
                      else "no VRAM budget provenance supplied with the planner"))
        raise WorkerPaneRefused(
            f"a local model must route through the ResidencyPlanner (OP-7 §12.2, invariant 22) and "
            f"this host's VRAM budget could not be established: {why}. Fail closed — an authorization "
            f"is never granted against a budget nothing could verify (U96)",
            # NOT the fit gate: nothing was measured, so this refusal is evidence about PROVENANCE
            # and must not be readable as evidence that a model does not fit (spec-audit MAJOR-1).
            gate=GATE_VRAM_BUDGET)
    # The disclosed budget must be the budget that is ENFORCED. The ticket carries `residency_budget`
    # verbatim as the authorization's stated basis, while the arithmetic runs against the planner's
    # own total — and nothing paired them: a planner built for 6000MB alongside a budget claiming
    # 99999MB produced a ticket disclosing a number the gate never used (validator MINOR-4; the
    # DISCLOSURE family U102 names, though U102's own row is about `running_vram_mb`).
    # The two agreeing is exactly what makes the disclosure meaningful, so it is asserted here.
    declared = budget.get("vram_budget_mb")
    enforced = residency_planner.total_vram_mb()
    if declared != enforced:
        raise WorkerPaneRefused(
            f"the VRAM budget this authorization would DISCLOSE ({declared}MB) is not the one the "
            f"planner ENFORCES ({enforced}MB) — refuse to emit a ticket whose stated basis is not "
            f"the basis it was decided on (fail closed, invariant 27)",
            gate=GATE_VRAM_BUDGET_MISMATCH)

    # Build the (side-effect-free) argv FIRST, then reserve VRAM — `request_load` is MUTATING and the
    # planner has no cancel primitive, so any refusal that can be decided WITHOUT it must be decided
    # first or it leaves a phantom residency entry behind (validator FINDING 3).
    argv = build_argv()
    _assert_fits_without_displacing(residency_planner, model)
    try:
        decision = residency_planner.request_load(model)
    except ResidencyError as exc:
        raise WorkerPaneRefused(
            f"residency/VRAM planner refused {model!r}: {exc} — cannot open a local model pane that "
            f"does not fit the host VRAM budget (fail closed, invariant 22)",
            gate=GATE_VRAM_ADMISSION) from exc

    # Invariant 22 says a VRAM swap is "scheduled, visible, never mid-generation eviction". This
    # planner is a bookkeeping MIRROR of the daemon's state, not its allocator: the host seeding
    # marks models resident but never sets `generating`, so the planner's own "evict only idle
    # models" rule is being evaluated against a flag nothing populates — a model it considers idle
    # may be answering a prompt right now. So a local pane is authorized only when it fits WITHOUT
    # displacing anything; a decision that evicts or flags another model is REFUSED here rather than
    # acted on (fail closed, gate-validator B1 / spec-audit MAJOR-3). Deliberate consequence: on a
    # busy host the operator gets an honest "no room" instead of a pane whose birth silently
    # reclaimed VRAM from a model the daemon was serving.
    # Defence in depth: the pre-check above decides this case without mutating, but if a future
    # planner change made a displacement reachable anyway, refuse rather than act on it.
    displaced = list(decision.evicted) + list(decision.awaiting_eviction)
    if displaced:
        raise WorkerPaneRefused(
            f"a local pane for {model!r} would only fit by displacing {displaced} — refused "
            f"(invariant 22; see the pre-check above)", gate=GATE_VRAM_ADMISSION)

    return argv, decision, dict(budget)


def _authorize_local(
    selection: PaneSelection,
    *,
    workspace: str,
    residency_planner: ResidencyPlanner | None,
    residency_budget: dict[str, Any] | None,
    ollama_present: bool | None,
    executable: str | None,
    shell_env_names: list[str] | None = None,
    worktree_manager: Any = None,
) -> WorkerPaneSession:
    from adapters import detect

    opt = selection.option
    if selection.role == "coding":
        # U95 LIFTED (EPC-04). The refusal called this role "the supervised OpenCode-harness path
        # (worktree-isolated, Phase 10 / 14C) ... deferred, not unavailable" — it named a route
        # rather than denying one, and this branch walks it.
        #
        # Its REASON is unchanged and is now enforced rather than deferred to: "a coding role
        # without a worktree would be a model with write hands and no containment." The worktree is
        # a precondition below, and its absence refuses the pane in those words.
        return _authorize_local_coding(
            selection, residency_planner=residency_planner, residency_budget=residency_budget,
            worktree_manager=worktree_manager, shell_env_names=shell_env_names)
    model = opt.get("model_slug")
    if not model:
        # NOT the VRAM gate: a selection with no model tag is malformed, and stamping it
        # `vram_admission` is the same id-borrowing the gate ids exist to stop (validator R1).
        raise SpawnRefused("local selection has no model_slug — fail closed")
    resolved = executable or detect.ollama_executable()
    present = (resolved is not None) if ollama_present is None else bool(ollama_present)
    if not present:
        raise WorkerPaneRefused(
            "the local `ollama` runtime is not on this host's PATH — cannot open a local worker "
            "pane (fail closed; the picker's enumeration comes from the daemon, which can be "
            "reachable without the CLI being launchable)", gate=GATE_RUNTIME_ABSENT)
    exe = _resolved_binary(resolved, OLLAMA_LOCAL_ADAPTER)
    # Two independent conditions, both fail-closed, because they are two different ways the same
    # thing goes wrong and relying on either alone is a fail-OPEN waiting for the other to drift:
    #   * no planner — nothing can be measured at all;
    #   * a budget that is not ESTABLISHED — the enumeration built a planner but the host's own
    #     residency contradicted the budget it was built on, so its arithmetic means nothing.
    # The enumeration currently returns those together, but that is a cross-module convention this
    # module cannot see; asserting it here is what makes it a rule (spec-audit MAJOR-1). An absent
    # budget is treated as unestablished — a caller that supplies a planner and no provenance has
    # told us nothing about what the planner's total means.
    argv, decision, budget = _reserve_local_vram(
        residency_planner, residency_budget, model,
        lambda: build_interactive_ollama_command(exe, model=model))

    chrome = WorkerPaneChrome(
        provider=opt.get("provider", OLLAMA_LOCAL_ADAPTER), adapter=OLLAMA_LOCAL_ADAPTER,
        locality="local", model_label=opt.get("label", model), model_slug=model,
        model_verified=bool(opt.get("verified", False)), is_fallback=False,
        role=selection.role, mode=selection.mode, node_id=selection.node_id,
        node_state=_AUTHORIZED_NOT_STARTED,    # not the residency status — see _AUTHORIZED_NOT_STARTED
        subscription=None,                     # invariant 19: local is NOT subscription-governed
        residency=decision.status)
    launch = _launch(argv, executable=exe, cwd=str(workspace), shell_env_names=shell_env_names,
                     note=("interactive `ollama run` local worker session in a governed pane; no "
                           "subscription and no credential is involved — VRAM residency (invariant "
                           "22) is what governs it"))
    return WorkerPaneSession(
        chrome=chrome, launch=launch, permission_profile_id=selection.permission_profile_id,
        residency_decision=decision.as_dict(),
        # Always present and always ESTABLISHED: the gate above refuses anything else, and the
        # disclosed figure has been checked against the planner's own total. The old "no provenance"
        # fallback shape here was dead code that read as if an unestablished budget could reach an
        # authorized ticket — it cannot, and code that implies otherwise is a false disclosure.
        residency_budget=dict(budget),
        subscription_governed=False, _release=None)


def _authorize_llamacpp_local(
    selection: PaneSelection,
    *,
    workspace: str,
    residency_planner: ResidencyPlanner | None,
    residency_budget: dict[str, Any] | None,
    llamacpp_present: bool | None,
    executable: str | None,
    shell_env_names: list[str] | None = None,
) -> WorkerPaneSession:
    """Authorize a reasoning pane backed by the supervised llama.cpp router."""
    if selection.role != "reasoning":
        raise WorkerPaneRefused("llama.cpp interactive panes currently support reasoning only",
                                gate=GATE_WORKER_ROLE)
    model = selection.option.get("model_slug")
    if not model:
        raise SpawnRefused("llama.cpp selection has no model_slug — fail closed")
    from adapters import detect
    resolved = executable or detect.llamacpp_executable()
    server_ready = detect.llamacpp_available()
    present = (bool(resolved) and server_ready if llamacpp_present is None
               else bool(resolved) and bool(llamacpp_present))
    if not present:
        raise WorkerPaneRefused(
            "the supervised local llama.cpp endpoint is unavailable or the workspace endpoint "
            "client cannot be resolved (fail closed; no Ollama/cloud fallback)",
            gate=GATE_RUNTIME_ABSENT)
    exe = _resolved_binary(resolved, LLAMACPP_LOCAL_ADAPTER)
    argv = build_interactive_llamacpp_command(exe, model=model)
    # This adapter attaches to the single-instance router. The router supervisor owns model
    # loading and its one-model residency limit; the Ollama-specific planner has no truthful view
    # of those child processes. Record that authority explicitly instead of fabricating an Ollama
    # footprint or refusing a healthy llama.cpp endpoint because Ollama is absent.
    decision = ResidencyDecision(
        model=model, scheduled=True, status=UNKNOWN,
        reason="residency is managed by the supervised llama.cpp router (models-max=1)")
    budget = {
        "established": True,
        "budget_source": "supervised llama.cpp router admission",
        "runtime_managed": True,
    }
    chrome = WorkerPaneChrome(
        provider=LLAMACPP_LOCAL_ADAPTER, adapter=LLAMACPP_LOCAL_ADAPTER, locality="local",
        model_label=selection.option.get("label", model), model_slug=model,
        model_verified=bool(selection.option.get("verified", False)), is_fallback=False,
        role=selection.role, mode=selection.mode, node_id=selection.node_id,
        node_state=_AUTHORIZED_NOT_STARTED, subscription=None, residency=decision.status)
    launch = _launch(argv, executable=exe, cwd=str(workspace), shell_env_names=shell_env_names,
                     note=("interactive workspace client attached to the supervised loopback "
                           "llama.cpp router; no subscription or cloud fallback is involved"))
    return WorkerPaneSession(
        chrome=chrome, launch=launch, permission_profile_id=selection.permission_profile_id,
        residency_decision=decision.as_dict(), residency_budget=dict(budget),
        subscription_governed=False, _release=None)


def _authorize_local_coding(
    selection: PaneSelection,
    *,
    residency_planner: ResidencyPlanner | None,
    residency_budget: dict[str, Any] | None,
    worktree_manager: Any,
    shell_env_names: list[str] | None = None,
) -> WorkerPaneSession:
    """A local CODING pane: OpenCode, interactive, confined to its own git worktree (EPC-04, U95).

    THE CONTAINMENT IS THE PRECONDITION, not a feature of the pane. The refusal this replaces
    existed because "a coding role without a worktree would be a model with write hands and no
    containment", and that sentence is still true — so the worktree is obtained BEFORE the pane is
    authorized, and its absence refuses rather than downgrading to an uncontained session.

    Everything a local pane already obeys is obeyed here unchanged: no subscription (invariant 19),
    no credential, and the loopback llama.cpp model pin that is why an OpenCode pane can spend
    nothing. What is NOT inherited from `_authorize_local` is the Ollama residency planner — this
    pane has no Ollama in its path, and `residency_planner`/`residency_budget` are accepted and left
    alone on purpose so the caller's one signature keeps working for every local adapter.

    `cwd` is the WORKTREE, not the workspace — that is the containment: the process starts inside
    the only tree it may modify, and `--pure` keeps unmeasured plugins out of it.
    """
    opt = selection.option
    model = opt.get("model_slug")
    if not model:
        raise SpawnRefused("local coding selection has no model_slug — fail closed")

    # NO `ollama` CLI GATE HERE, and none is needed for the router either: OpenCode reaches its
    # model over the workspace's loopback llama.cpp endpoint, so the Ollama CLI and the Ollama
    # daemon are both absent from this path's list of dependencies. What IS load-bearing is the
    # router answering, because a coding pane whose endpoint is down is a model with write hands
    # and nothing behind it. That is measured, not assumed, in step (2).
    #
    # THE RESIDENCY AUTHORITY IS THE ROUTER, NOT THE OLLAMA PLANNER — the same call
    # `_authorize_llamacpp_local` already made for the reasoning pane. The planner is a bookkeeping
    # mirror of a daemon this workspace does not use; routing a coding pane through it meant every
    # OpenCode option was refused with "this host's VRAM admission budget could not be established
    # — ollama daemon unreachable — no planner" on a host whose llama.cpp router was answering 69
    # models. The router admits one model at a time (`models-max 1`) and owns the swap; a planner
    # that claimed to pre-commit that swap would be recording an authority it does not hold.

    # (1) THE OPENCODE BINARY, RESOLVED HERE — deliberately not the caller's `executable`.
    #
    # `authorize_worker_pane` receives ONE executable, resolved for the option's own adapter, which
    # is the shell's Python. Launching that with OpenCode's argv would run the wrong program with a
    # worktree path as its first argument. The parameter is not threaded in for exactly that reason.
    #
    # `.executable` is `shutil.which("opencode")` — a real path, or None when it is not installed.
    # None is a PRESENCE fact, and gets its own gate: "install opencode" is a different operator
    # action from `binary_unresolved` ("the presence gate and the resolver disagreed").
    resolved = OpenCodeCliHarness().executable
    if not (resolved or "").strip():
        raise WorkerPaneRefused(
            "the `opencode` CLI is not on this host's PATH — cannot open a local coding pane "
            "(fail closed; the operator installs it, this workspace never does — §7)",
            gate=GATE_OPENCODE_ABSENT)
    exe = _resolved_binary(resolved, OPENCODE_LOCAL_ADAPTER)

    # (2) THE ENDPOINT. Absent, refused — with no fallback to fall through to.
    from adapters import detect  # noqa: PLC0415 — this module's convention for host detection

    if not detect.llamacpp_available():
        raise WorkerPaneRefused(
            "the supervised local llama.cpp endpoint is not answering — cannot open an OpenCode "
            "coding pane against it (fail closed; there is no Ollama and no cloud fallback)",
            gate=GATE_RUNTIME_ABSENT)

    # (3) the worktree. No manager, no worktree, no pane.
    if worktree_manager is None:
        raise WorkerPaneRefused(
            "a local CODING pane requires a worktree manager and none was supplied — refused "
            "rather than run uncontained. A coding role without a worktree is a model with write "
            "hands and no containment (the U95 reason, enforced rather than deferred)",
            gate=GATE_WORKTREE_UNAVAILABLE)
    # `ensure`, not `create`: the manager's map is in-memory, so a pane the operator REOPENS in a
    # fresh process would otherwise hit `git worktree add -b` on a branch that already exists and
    # be refused. `ensure` reconciles against git and adopts the pane's own tree — and refuses to
    # adopt one registered anywhere else, which is where the containment is actually kept.
    try:
        worktree = worktree_manager.ensure(selection.node_id)
    except Exception as exc:  # noqa: BLE001 — every provisioning failure is an attributable refusal
        raise WorkerPaneRefused(
            f"could not provision an isolated worktree for {selection.node_id!r}: {exc} — "
            f"refused rather than run uncontained", gate=GATE_WORKTREE_UNAVAILABLE) from exc

    # Side-effect-free, and ordered before anything mutates: `build_interactive_opencode_command`
    # is where the §2.3 pin is re-asserted at the build site, so a non-local model is refused here
    # rather than after a worktree has been adopted.
    argv = build_interactive_opencode_command(exe, worktree=worktree.path, model=model)
    decision = ResidencyDecision(
        model=model, scheduled=True, status=UNKNOWN,
        reason="residency is managed by the supervised llama.cpp router (models-max=1)")
    budget = {
        "established": True,
        "budget_source": "supervised llama.cpp router admission",
        "runtime_managed": True,
    }

    chrome = WorkerPaneChrome(
        provider=opt.get("provider", OPENCODE_LOCAL_ADAPTER), adapter=OPENCODE_LOCAL_ADAPTER,
        locality="local", model_label=opt.get("label", model), model_slug=model,
        model_verified=bool(opt.get("verified", False)), is_fallback=False,
        role=selection.role, mode=selection.mode, node_id=selection.node_id,
        node_state=_AUTHORIZED_NOT_STARTED,
        subscription=None,                     # invariant 19: local is NOT subscription-governed
        residency=decision.status)
    launch = _launch(
        argv, executable=exe, cwd=str(worktree.path), shell_env_names=shell_env_names,
        note=("interactive OpenCode coding pane confined to its own git worktree; the model is "
              "pinned to the supervised loopback llama.cpp endpoint and the child environment is "
              "credential-scrubbed, so no subscription and no cloud credential is involved — the "
              "router's own residency and the worktree are what govern it"))
    return WorkerPaneSession(
        chrome=chrome, launch=launch, permission_profile_id=selection.permission_profile_id,
        residency_decision=decision.as_dict(), residency_budget=dict(budget),
        subscription_governed=False, _release=None)
