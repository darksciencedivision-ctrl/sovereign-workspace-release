"""Governed live-conductor spawn path — the ONE place a LIVE `claude_code`-backed conductor is
born. Phase 15B `.conductor` (directive §11 15B: "make the backend conductor-capable").

The conductor is an INTERFACE + runtime selection (invariant 3, current selection Fable 5). This
module binds the LIVE claude_code backend (via `ClaudeCodeConductorBackend`) into the Phase-4
`ConductorAdapter` behind the SAME governed contract used for the live worker terminal — no naked
session (I-C1/invariant 2), no credential handling (§2.2), no self-authorization of any protected
action. It reuses the live-frontier gate set from `frontier_spawn` verbatim (a live conductor is a
subscription-backed live path exactly like a live worker), differing only in the adapter it builds.

Order of gates (all must pass; any failure ⇒ no live conductor):
  1. `ProfileLoader.assert_startup([claude_code cap], live_auth)` — roster eligibility AND the
     LIVE_OPERATION_AUTHORIZED gate, evaluated on the *provider* capability (`adapter="claude_code"`)
     because live authorization is keyed on the provider, never on the conductor selection label.
  2. `LiveAuthorization.assert_provider_live("claude_code")` — the primary live gate re-asserted.
  3. R8 §6 operator live-terms confirmation — `[OPERATOR]`-flagged; unmet ⇒ skip-with-record.
  4. `claude` CLI present on the host (real backend only; a mock proof injects its own backend).
  5. `SubscriptionGovernor.register_subscription(..., allowance=live_auth.terminals_for(provider))`
     — the ConductorAdapter itself acquires/releases the terminal at start()/close() (Phase-4
     design), so this path only sets the authorized allowance and never double-counts.

Mock-first: `attempt_live_conductor_smoke` drives the whole path with an injected mock backend and
publishes a real CANDIDATE decision through MCP; the single LIVE `claude` conductor smoke stays
skip-with-record until the operator terms are discharged (directive §10.4). No live call here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from adapters.base.backend import Backend, BackendAuthPause
from adapters.base.contract import AdapterContext
from adapters.conductor.adapter import ConductorAdapter
from adapters.frontier.claude_code import (
    CLAUDE_CODE_ADAPTER,
    ClaudeCliBackend,
    ClaudeCodeConductorBackend,
    bind_calls_snapshot,
    claude_code_conductor_descriptor,
    resolve_claude_model_ref,
    verify_reported_checkpoint,
)
from control_plane.conductor.selection import (
    OPERATOR_SELECTED_CONDUCTOR,
    ConductorSelection,
    ExecutingEvidence,
    bind_conductor_selection,
)
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import ProfileLoader
from node_runtime.supervisor.frontier_spawn import (
    ClaudeCliUnavailable,
    LiveTermsNotConfirmed,
    _detect_cli,
    capability_for_claude_code,
)
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor


def spawn_claude_code_conductor(
    *,
    mcp_client: Any,
    governor: SubscriptionGovernor,
    subscription_ref: str,
    node_id: str,
    permission_profile_id: str,
    live_auth: LiveAuthorization,
    profile_loader: ProfileLoader,
    operator_terms_confirmed: bool,
    conductor_file_refs: dict[str, str],
    model: str | None = None,
    selection: ConductorSelection = OPERATOR_SELECTED_CONDUCTOR,
    project_id: str = "proj",
    cli_present: bool | None = None,
    backend: Backend | None = None,
) -> ConductorAdapter:
    """Build the single LIVE `claude_code`-backed conductor, or refuse (fail closed).

    `backend` is injected only by the mock-first proof (a `MockClaudeCliBackend`); when omitted the
    real `ClaudeCliBackend` is used and the host CLI must be present. Every gate applies in BOTH
    cases. The returned adapter is NOT started — the caller (or the smoke) calls `.start()`, which
    acquires the subscription terminal and loads the conductor files from MCP.

    `selection` is the operator's conductor SELECTION (default: fable-5, OP-6 — invariant 3). When
    `model` is omitted the conductor requests the SELECTION's own model rather than silently taking
    the CLI default (directive §11 15D: "model_ref = fable-5 if available else recorded fallback").
    An explicit `model` still wins, and either way the accepted slug stays unverified until a live
    smoke reports the executing checkpoint back.
    """
    cap = capability_for_claude_code()

    # (1) whole-roster profile + LIVE_OPERATION_AUTHORIZED gate — the real startup path
    profile_loader.assert_startup([cap], live_auth=live_auth)
    # (2) primary live gate re-asserted at the spawn site
    live_auth.assert_provider_live(CLAUDE_CODE_ADAPTER)
    # (3) R8 §6 operator live-terms confirmation
    if not operator_terms_confirmed:
        raise LiveTermsNotConfirmed(
            "R8 §6 [OPERATOR] live-terms confirmation not recorded — fail closed, no live "
            "conductor (directive §10.4)")
    # (4) CLI presence (real backend only; a mock proof supplies its own backend)
    if backend is None:
        present = _detect_cli() if cli_present is None else cli_present
        if not present:
            raise ClaudeCliUnavailable(
                "`claude` CLI not detected on host PATH — cannot spawn a live conductor (fail closed)")
    # (5) I-X3: set the authorized allowance; the ConductorAdapter acquires/releases at
    #     start()/close(), so this path registers but never acquires (no double-count).
    governor.register_subscription(
        subscription_ref, CLAUDE_CODE_ADAPTER,
        allowance=live_auth.terminals_for(CLAUDE_CODE_ADAPTER))

    # Resolve the per-node model through the single honest resolver (verbatim slug, unverified
    # until a live smoke; None ⇒ CLI-default fallback surfaced in the roster).
    requested_model = model if model is not None else selection.model
    resolved_model, _model_note = resolve_claude_model_ref(requested_model)
    worker_backend = backend or ClaudeCliBackend(model=resolved_model)
    conductor_backend = ClaudeCodeConductorBackend(
        worker_backend, model_name=f"claude_code:conductor:{resolved_model or 'default'}")

    context = AdapterContext(
        node_id=node_id, role="conductor", project_id=project_id,
        permission_profile_id=permission_profile_id, mcp_credential_id="mcp-ref",
        subscription_ref=subscription_ref, spawned_by_supervisor=True)
    # ConductorAdapter refuses a naked launch (I-C1) and holds no credential (base default).
    return ConductorAdapter(context, mcp_client, conductor_backend, governor, conductor_file_refs)


@dataclass(frozen=True)
class ConductorSmokeOutcome:
    """Result of the single live conductor smoke. `ran=False, skipped_with_record=True` is the
    honest non-interactive outcome (directive §10.4): the live conductor path is built and gated
    but no live call was made because a gate was unmet."""

    ran: bool
    published: bool
    skipped_with_record: bool
    reason: str
    decision_entry: str | None = None
    # per-node model resolution surfaced on EVERY outcome (directive §11 15B, never silent)
    model_resolution: dict | None = None
    # the conductor SELECTION + the EXECUTING checkpoint, recorded separately on EVERY outcome
    # (directive §11 15D — "selection preserved even when the executing checkpoint differs")
    conductor_selection: dict | None = None


def attempt_live_conductor_smoke(
    *,
    objective: str,
    mcp_client: Any,
    governor: SubscriptionGovernor,
    subscription_ref: str,
    node_id: str,
    permission_profile_id: str,
    live_auth: LiveAuthorization,
    profile_loader: ProfileLoader,
    operator_terms_confirmed: bool,
    conductor_file_refs: dict[str, str],
    model: str | None = None,
    selection: ConductorSelection = OPERATOR_SELECTED_CONDUCTOR,
    project_id: str = "proj",
    cli_present: bool | None = None,
    backend: Backend | None = None,
) -> ConductorSmokeOutcome:
    """Run EXACTLY ONE governed conductor smoke: spawn → start (acquire + load files) → one cycle
    (publish a CANDIDATE decision) → close (release).

    Any gate/availability failure (unauthorized live_auth, unconfirmed terms, absent CLI) yields
    skip-with-record and makes NO live call. A `BackendAuthPause` mid-cycle is a fail-closed pause
    (Plan §18.4) — reported, terminal released. Success publishes one CANDIDATE decision through the
    full MCP + governor path.
    """
    # the model the spawn will actually request: an explicit `model` wins, else the SELECTION's own
    # (kept identical to the spawn's resolution so the surfaced record can never describe a
    # different slug than the one that reaches argv)
    requested_model = model if model is not None else selection.model
    model_resolution = claude_code_conductor_descriptor(requested_model)
    # selection recorded up front so EVERY exit below carries it — including the ones that refuse
    # before a backend exists (nothing executed ⇒ nothing reported ⇒ unverified)
    selection_record = bind_conductor_selection(
        selection, requested_model=requested_model, resolver=resolve_claude_model_ref).as_record()
    try:
        adapter = spawn_claude_code_conductor(
            mcp_client=mcp_client, governor=governor, subscription_ref=subscription_ref,
            node_id=node_id, permission_profile_id=permission_profile_id, live_auth=live_auth,
            profile_loader=profile_loader, operator_terms_confirmed=operator_terms_confirmed,
            conductor_file_refs=conductor_file_refs, model=model, selection=selection,
            project_id=project_id, cli_present=cli_present, backend=backend)
    except Exception as exc:  # noqa: BLE001 — every gate/availability failure is skip-with-record
        return ConductorSmokeOutcome(
            ran=False, published=False, skipped_with_record=True,
            reason=f"{type(exc).__name__}: {exc}", model_resolution=model_resolution,
            conductor_selection=selection_record)
    # Snapshotted BEFORE the cycle so a reported checkpoint can be dated to a call made by THIS
    # smoke (U45). `None` when no vendor backend is behind the adapter — which can never verify.
    calls_before = bind_calls_snapshot(adapter.backend)
    try:
        adapter.start()  # acquires the subscription terminal + loads conductor files from MCP
        result = adapter.run_cycle(objective)
    except BackendAuthPause as exc:  # subscription expired mid-call — fail-closed pause
        adapter.close()
        return ConductorSmokeOutcome(
            ran=True, published=False, skipped_with_record=True,
            reason=f"auth pause (Plan §18.4): {exc}", model_resolution=model_resolution,
            conductor_selection=selection_record)
    except Exception as exc:  # noqa: BLE001 — anything else: skip-with-record, never a false PASS
        adapter.close()
        return ConductorSmokeOutcome(
            ran=False, published=False, skipped_with_record=True,
            reason=f"{type(exc).__name__}: {exc}", model_resolution=model_resolution,
            conductor_selection=selection_record)
    # a cycle ran: reconcile the EXECUTING checkpoint under the ONE verification rule (U45) — exact
    # vendor class, a call spent here, a checkpoint the CLI itself reported, stamped AFTER the
    # snapshot above. Anything less (mock path, a CLI that reported nothing, a checkpoint left over
    # from an earlier run) stays UNVERIFIED and is recorded as an unbacked claim, not a checkpoint.
    # A verified id differing from the selection LABEL is surfaced as a label mismatch, never masked.
    evidence = verify_reported_checkpoint(adapter.backend, calls_before=calls_before)
    selection_record = bind_conductor_selection(
        selection, requested_model=requested_model,
        executing_evidence=ExecutingEvidence(evidence["model"]) if evidence else None,
        reported_model=None if evidence else adapter.reported_model,
        resolver=resolve_claude_model_ref).as_record()
    adapter.close()  # release the terminal (no wedge)
    return ConductorSmokeOutcome(
        ran=True, published=True, skipped_with_record=False,
        reason="live conductor smoke ran; CANDIDATE decision published",
        decision_entry=result["decision_entry"], model_resolution=model_resolution,
        conductor_selection=selection_record)
