"""Governed node spawn FROM a per-pane picker selection (Phase 15E `.spawn`; OP-7 §12.2/§12.3).

The per-pane picker (`control_plane/nodes/pane_picker.py`, sub-step `.picker`) only OFFERS
options. This module is the SPAWN dispatcher: it turns exactly ONE selected option
(provider × model × role) plus a mode (attended | autonomous) into a supervised, governed
spawn — or a fail-closed refusal — and produces the pane chrome the shell renders.

It is a THIN, deterministic coordinator (Buildout Directive §4 — permission/lifecycle logic,
never model output). It does NOT re-implement any gate; it composes the existing, already-gated
supervised spawn paths so there is exactly one place each kind of terminal is born:

  * frontier `claude_code`  → `frontier_spawn.spawn_claude_code_terminal` (I-X3 governed)
  * frontier `openai_codex_cli` → `codex_spawn.spawn_codex_terminal` (I-X3 governed, per-role)
  * local `ollama_local`    → `ResidencyPlanner.request_load` (invariant 22 — visible VRAM
    residency) then a supervised local node: `opencode_spawn.spawn_opencode_harness` for a
    coding role, else a supervised `LocalWorkerAdapter` (reasoning). Local terminals are NEVER
    subscription-governed (subscription_governor.py governs frontier subscriptions only).

Fail-closed selection validation (all BEFORE any spawn path or governor/planner mutation):
  * an `available=False` (greyed) option is refused — the picker already recorded WHY it is
    unavailable, and a node the operator cannot see offered must never be born;
  * a role not in the option's offered `roles` is refused (I-SC1 — capability is chosen from
    what the descriptor offered, never inferred from the model name);
  * an unknown mode is refused;
  * a missing node identity OR permission profile is refused (invariant 2/29 — no naked session;
    the downstream adapter/harness enforce the same guard as defense-in-depth);
  * a frontier selection with no subscription_ref is refused (an uncounted terminal defeats I-X3);
  * a local selection with no ResidencyPlanner, or a model with no registered footprint, is
    refused (we never schedule VRAM we cannot ADMIT — admission is against an unverified
    budget, never a proof of fit; U96).

Attended vs autonomous (OP-7 §12.3): BOTH modes spawn through the SAME supervised path with the
SAME permission profile — the mode is a chrome/routing label, NOT an authority grant (invariant
1: an operator-attended node gains no privilege the profile did not already grant). The full
interactive ConPTY attachment is a later sub-step (`.conductor-pane`); here the mode is carried
as a first-class governed fact.

D-LOOP-1: `GovernedSpawn.teardown()` releases a frontier terminal's I-X3 count so a spawn made in
a work unit is released within it; it is idempotent and a no-op for a local (ungoverned) node.

Mock-first: frontier paths take an injected mock backend and local coding takes an injected mock
harness/probe, so the whole dispatch is proven with zero live calls; a real live spawn supplies a
real backend/harness through the identical path and must be torn down within the unit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from adapters.base.contract import AdapterContext
from adapters.base.backend import Backend
from adapters.coding.opencode.harness import CodingHarness, HarnessProbe
from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER
from adapters.frontier.codex import CODEX_ADAPTER
from adapters.local.worker import LocalWorkerAdapter
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import ProfileLoader
from node_runtime.supervisor.codex_spawn import spawn_codex_terminal
from node_runtime.supervisor.frontier_spawn import spawn_claude_code_terminal
from node_runtime.supervisor.opencode_spawn import spawn_opencode_harness
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor
from scheduler.residency_planner.residency_planner import (
    LOADING,
    QUEUED,
    RESIDENT,
    ResidencyError,
    ResidencyPlanner,
)

_LOCAL_ADAPTER = "ollama_local"
ATTENDED = "attended"
AUTONOMOUS = "autonomous"
_MODES = frozenset({ATTENDED, AUTONOMOUS})

# Residency status → the node_state the pane chrome shows. A model that is not yet resident is
# honestly LOADING/QUEUED, never presented as ready.
_RESIDENCY_NODE_STATE = {
    RESIDENT: "ready",
    LOADING: "loading",
    QUEUED: "queued_for_vram",
}


class SpawnRefused(Exception):
    """A picker selection was refused fail-closed by the coordinator (bad/greyed/naked selection).

    Distinct from the governed spawn paths' own exceptions (SubscriptionLimitExceeded,
    ProfileViolation, LiveTermsNotConfirmed, ResidencyError, …), which propagate unchanged: those
    are the supervised paths enforcing their gates. This is the SELECTION-level refusal.

    `gate` names WHICH check said no, machine-readably. A receipt leg that asserts a refusal by
    matching words in the prose is evidence for whichever gate happened to fire and happened to use
    those words — the gate-validator caught exactly that on 2026-07-26, when an enumeration CRASH
    whose message contained "VRAM" satisfied the leg that was supposed to prove the invariant-22
    admission gate. An id cannot be borrowed that way."""

    def __init__(self, message: str, *, gate: str = "selection_guard") -> None:
        super().__init__(message)
        self.gate = gate


@dataclass(frozen=True)
class PaneSelection:
    """One picker choice the operator made in a pane. `option` is a single dict straight from
    `build_pane_picker(...)["options"]` — carried verbatim so the spawn can never disagree with
    what the operator saw offered."""

    option: dict[str, Any]
    role: str
    mode: str                              # attended | autonomous
    node_id: str
    permission_profile_id: str
    subscription_ref: str | None = None    # required for a frontier option; ignored for local


@dataclass
class NodeChrome:
    """The pane chrome the shell renders (OP-7 §11 15E / §12.3): model badge, subscription n/2,
    node state, role, mode. `governed=True` always — a naked session never reaches chrome."""

    provider: str
    adapter: str
    locality: str                          # frontier | local
    model_label: str
    model_slug: str | None
    model_verified: bool
    role: str
    mode: str                              # attended | autonomous
    node_state: str
    node_id: str
    governed: bool
    subscription: dict[str, Any] | None    # {ref, in_use, allowance} (frontier) | None (local)
    residency: str | None                  # residency state (local) | None (frontier)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider, "adapter": self.adapter, "locality": self.locality,
            "model_label": self.model_label, "model_slug": self.model_slug,
            "model_verified": self.model_verified, "role": self.role, "mode": self.mode,
            "node_state": self.node_state, "node_id": self.node_id, "governed": self.governed,
            "subscription": dict(self.subscription) if self.subscription is not None else None,
            "residency": self.residency,
        }


@dataclass
class GovernedSpawn:
    """The result of a governed spawn: the pane chrome, the live handle (a ModelWorkerAdapter for
    a frontier or local-reasoning node; a SupervisedOpenCode for a local-coding node), the
    residency decision for a local model (None for frontier), and a teardown that releases any
    governed I-X3 count (D-LOOP-1)."""

    chrome: NodeChrome
    handle: Any
    residency_decision: dict[str, Any] | None = None
    _release: Callable[[], None] | None = None

    def teardown(self) -> None:
        """Release the governed count for a frontier terminal (idempotent); no-op for local."""
        if self._release is not None:
            self._release()


def assert_selection_spawnable(selection: PaneSelection) -> None:
    """The fail-closed SELECTION guard, shared by every path that turns a picker choice into a node.

    Extracted at Phase 17B `.ticket` so the headless dispatcher below and the INTERACTIVE worker-pane
    authorization (`node_runtime/supervisor/worker_pane_spawn`) refuse identically: a divergence
    would mean a selection the operator can launch in a pane but the dispatcher would have refused
    (or the reverse), which is exactly the class of drift invariant 16 forbids. Raises `SpawnRefused`;
    performs NO mutation, so every refusal below happens with nothing acquired, reserved or spawned.
    """
    opt = selection.option
    if not isinstance(opt, dict):
        raise SpawnRefused("selection.option must be a picker option dict — fail closed")

    # (1) a greyed option is never spawnable — the picker recorded the reason.
    if not opt.get("available"):
        reason = opt.get("unavailable_reason") or "no reason recorded"
        raise SpawnRefused(
            f"option {opt.get('provider')}/{opt.get('label')} is unavailable ({reason}) — "
            f"cannot spawn a node the operator was shown as unavailable (fail closed)")
    # (2) mode must be known.
    if selection.mode not in _MODES:
        raise SpawnRefused(
            f"unknown pane mode {selection.mode!r} — expected attended|autonomous (fail closed)")
    # (3) role must be one the option OFFERED (I-SC1 — never inferred).
    offered = opt.get("roles") or []
    if selection.role not in offered:
        raise SpawnRefused(
            f"role {selection.role!r} not offered by {opt.get('provider')}/{opt.get('label')} "
            f"(offered: {list(offered)}) — the role must be one the option OFFERED, never inferred "
            f"from the model name (I-SC1). For frontier options `offered` is an adapter fact; for "
            f"local options it is today a coarse uniform menu (reasoning|coding) — a real per-model "
            f"capability descriptor is owed to the coding-integration follow-up (U63).")
    # The conductor node is NOT a worker spawn: it is the conductor-first, pinned, succession-capable
    # pane born by the dedicated conductor path (control_plane/conductor + conductor_spawn). Both
    # worker paths refuse it rather than build a WORKER handle under a chrome badge that reads
    # "conductor" (which would diverge). The picker still OFFERS the capability; routing it is the
    # conductor path's job.
    if selection.role == "conductor":
        raise SpawnRefused(
            "the conductor role is spawned by the dedicated conductor-first path (Phase 15E "
            "`.conductor-pane`), not this worker-spawn dispatcher — deferred, not unavailable")
    # (4) no naked session (invariant 2/29) — enforced here and again by the adapter/harness.
    if not selection.node_id:
        raise SpawnRefused("selection has no node identity — no naked session (invariant 2/29)")
    if not selection.permission_profile_id:
        raise SpawnRefused(
            "selection has no supervisor-issued permission profile — no naked session (inv 2/29)")


def spawn_node_from_selection(
    selection: PaneSelection,
    *,
    live: LiveAuthorization,
    governor: SubscriptionGovernor,
    profile_loader: ProfileLoader,
    mcp_client: Any,
    operator_terms_confirmed: bool = False,
    residency_planner: ResidencyPlanner | None = None,
    backend: Backend | None = None,
    opencode_harness: CodingHarness | None = None,
    opencode_probe: HarnessProbe | None = None,
    workspace_root: str | None = None,
    project_id: str = "proj",
) -> GovernedSpawn:
    """Spawn a governed node from ONE picker selection, or refuse fail-closed (`SpawnRefused`).

    `backend` — mock-first injected frontier backend (real one used only in a live smoke).
    `residency_planner` — required for a local selection (invariant 22 routing).
    `opencode_harness`/`opencode_probe` — injected for a local CODING selection (mock-first).
    """
    assert_selection_spawnable(selection)   # the ONE shared fail-closed selection guard
    opt = selection.option
    adapter_id = opt.get("adapter")
    if adapter_id in (CLAUDE_CODE_ADAPTER, CODEX_ADAPTER):
        return _spawn_frontier(
            selection, adapter_id=adapter_id, live=live, governor=governor,
            profile_loader=profile_loader, mcp_client=mcp_client,
            operator_terms_confirmed=operator_terms_confirmed, backend=backend,
            project_id=project_id)
    if adapter_id == _LOCAL_ADAPTER:
        return _spawn_local(
            selection, mcp_client=mcp_client, residency_planner=residency_planner,
            opencode_harness=opencode_harness, opencode_probe=opencode_probe,
            workspace_root=workspace_root, project_id=project_id)
    raise SpawnRefused(f"unknown adapter {adapter_id!r} in selection — fail closed")


# ---- frontier (subscription-governed, I-X3) -------------------------------------------------

def _spawn_frontier(
    selection: PaneSelection,
    *,
    adapter_id: str,
    live: LiveAuthorization,
    governor: SubscriptionGovernor,
    profile_loader: ProfileLoader,
    mcp_client: Any,
    operator_terms_confirmed: bool,
    backend: Backend | None,
    project_id: str,
) -> GovernedSpawn:
    if not selection.subscription_ref:
        raise SpawnRefused(
            f"frontier selection {adapter_id!r} has no subscription_ref — refuse to spawn an "
            f"uncounted terminal (I-X3, fail closed)")
    opt = selection.option
    model = opt.get("model_slug")  # None ⇒ CLI default (a recorded fallback the picker labelled)
    common = dict(
        mcp_client=mcp_client, governor=governor, subscription_ref=selection.subscription_ref,
        node_id=selection.node_id, permission_profile_id=selection.permission_profile_id,
        live_auth=live, profile_loader=profile_loader,
        operator_terms_confirmed=operator_terms_confirmed, model=model, project_id=project_id,
        backend=backend)
    if adapter_id == CLAUDE_CODE_ADAPTER:
        handle = spawn_claude_code_terminal(**common)
    else:
        # codex spawn selects per-role (reasoning|coding); the role is the offered capability.
        handle = spawn_codex_terminal(role=selection.role, **common)

    ref = selection.subscription_ref
    node_id = selection.node_id
    status = governor.status().get(ref, {})
    subscription = {"ref": ref, "in_use": governor.active_count(ref),
                    "allowance": status.get("allowance", live.terminals_for(adapter_id))}
    chrome = _chrome(selection, locality="frontier", node_state="ready",
                     subscription=subscription, residency=None)
    return GovernedSpawn(chrome=chrome, handle=handle, residency_decision=None,
                         _release=lambda: governor.release(ref, node_id))


# ---- local (VRAM-residency-governed, NOT subscription-governed) ------------------------------

def _spawn_local(
    selection: PaneSelection,
    *,
    mcp_client: Any,
    residency_planner: ResidencyPlanner | None,
    opencode_harness: CodingHarness | None,
    opencode_probe: HarnessProbe | None,
    workspace_root: str | None,
    project_id: str,
) -> GovernedSpawn:
    if residency_planner is None:
        raise SpawnRefused(
            "a local model must route through the ResidencyPlanner (OP-7 §12.2, invariant 22) — "
            "no planner supplied, fail closed")
    model = selection.option.get("model_slug")
    if not model:
        raise SpawnRefused("local selection has no model_slug — fail closed")

    # Build the (side-effect-free) supervised handle FIRST, then reserve VRAM. request_load is a
    # MUTATING call (it reserves VRAM and can flag idle models for eviction); the ResidencyPlanner
    # has no cancel primitive for a LOADING reservation, so reserving before a harness/identity gate
    # that can still refuse would leak a phantom, visible-but-wrong residency entry (contrary to
    # invariant 22's "residency is scheduled, visible"). Constructing the handle has no residency
    # side effect — it only gates presence/version/identity (coding) or re-checks the supervised
    # context (reasoning) — so a refusal here happens with ZERO VRAM reserved.
    if selection.role == "coding":
        handle: Any = spawn_opencode_harness(
            mcp_client=mcp_client, node_id=selection.node_id,
            permission_profile_id=selection.permission_profile_id,
            workspace_root=workspace_root or ".", harness=opencode_harness, probe=opencode_probe,
            project_id=project_id)
    else:
        # reasoning: a supervised local worker (no naked session — BaseAdapter re-checks the
        # supervisor identity + permission profile). The selected Ollama tag is the model name.
        context = AdapterContext(
            node_id=selection.node_id, role="worker", project_id=project_id,
            permission_profile_id=selection.permission_profile_id, mcp_credential_id="mcp-ref",
            subscription_ref=None,  # local: NOT subscription-backed, NOT governed by I-X3
            spawned_by_supervisor=True)
        handle = LocalWorkerAdapter(context, mcp_client, model_name=model)

    # invariant 22: NOW that the node is known spawnable, schedule VRAM residency VISIBLY. An
    # unsized/over-budget model is refused by the planner (fail closed) — surface it as a refusal.
    # NOTE (U63, owed): for a CODING node the harness auto-resolves its own coder model
    # (probe.coder_model); this reserves/badges the picker-SELECTED tag. They coincide in the
    # mock-first proof; forcing OpenCode to drive the selected tag (so the badge/reservation and the
    # model actually run cannot diverge) is owed to the coding-integration follow-up.
    try:
        decision = residency_planner.request_load(model)
    except ResidencyError as exc:
        raise SpawnRefused(
            f"residency/VRAM planner refused {model!r}: {exc} — cannot spawn a local model that "
            f"cannot be ADMITTED against this host's VRAM budget (fail closed; the budget is an "
            f"unverified stand-in unless SOW_VRAM_BUDGET_MB is set — U96)") from exc

    residency_state = decision.status
    node_state = _RESIDENCY_NODE_STATE.get(residency_state, residency_state)
    chrome = _chrome(selection, locality="local", node_state=node_state, subscription=None,
                     residency=residency_state)
    return GovernedSpawn(chrome=chrome, handle=handle, residency_decision=decision.as_dict(),
                         _release=None)


# ---- chrome -----------------------------------------------------------------------------------

def _chrome(selection: PaneSelection, *, locality: str, node_state: str,
            subscription: dict[str, Any] | None, residency: str | None) -> NodeChrome:
    """Build the pane chrome. The model badge (label/slug/verified) is carried VERBATIM from the
    picker option so the chrome never diverges from what the operator selected."""
    opt = selection.option
    return NodeChrome(
        provider=opt.get("provider", ""), adapter=opt.get("adapter", ""), locality=locality,
        model_label=opt.get("label", ""), model_slug=opt.get("model_slug"),
        model_verified=bool(opt.get("verified", False)), role=selection.role, mode=selection.mode,
        node_state=node_state, node_id=selection.node_id, governed=True,
        subscription=subscription, residency=residency)
