"""Governed live-frontier spawn path — the ONE place a live `claude_code` terminal is born.
Phase 14B `.adapter` (directive §10.1; register OP-4/OP-5).

This is the real supervisor/startup path the directive requires to enforce, at the actual
spawn site and before any live call, every entry condition for live operation. It is
deterministic, fail-closed permission logic (Buildout Directive §4) — never model output.

Order of gates (all must pass; any failure => no live spawn):
  1. `ProfileLoader.assert_startup([cap], live_auth)` — whole-roster profile eligibility AND
     the LIVE_OPERATION_AUTHORIZED gate (discharges the .liveflag MINOR-2 latent-enforcement:
     a test drives THIS real entrypoint).
  2. `LiveAuthorization.assert_provider_live("claude_code")` — the primary gate re-asserted at
     the live-spawn site (belt-and-suspenders; distinct call site from the roster check).
  3. R8 §6 operator live-terms confirmation — the `[OPERATOR]`-flagged dated-terms items. In a
     non-interactive session these are unmet => skip-with-record (directive §10.4).
  4. `claude` CLI actually present on the host (real backend only; a mock proof injects its
     backend and skips this).
  5. SubscriptionGovernor.acquire — I-X3, concurrency governed by the enforced authorization
     (OP-6: at most 2 terminals/subscription, read from live_auth; a config may narrow to 1).
Only then is a supervisor-issued AdapterContext constructed (spawned_by_supervisor=True) and
handed to the live adapter. If construction fails the terminal is released (no wedged count).

The credential itself is never touched here or in the adapter (§2.2): the `claude` CLI holds
its own OAuth token in a host-native store.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from adapters.base.contract import AdapterCapability, AdapterContext
from adapters.frontier.claude_code import (
    CLAUDE_CODE_ADAPTER,
    CLAUDE_CODE_CAPABILITY_DESCRIPTORS,
    ClaudeCliBackend,
    ClaudeCodeAuthError,
    build_claude_code_adapter,
    claude_code_roster_descriptor,
    is_live_cli_backend,
    resolve_claude_model_ref,
)
from adapters.base.backend import Backend
from adapters.model_adapter import ModelWorkerAdapter
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import ProfileLoader
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor


class LiveTermsNotConfirmed(Exception):
    """The R8 §6 [OPERATOR] live-terms confirmation is not recorded — fail closed, no live call."""


class ClaudeCliUnavailable(Exception):
    """The `claude` CLI is not present on the host — cannot spawn a live terminal, fail closed."""


def capability_for_claude_code() -> AdapterCapability:
    """The live frontier capability the profile/live gate evaluates. `adapter="claude_code"`
    (not the `mock` sentinel) is what makes ProfileLoader treat this as a REAL live path."""
    return AdapterCapability(
        adapter=CLAUDE_CODE_ADAPTER, node_class="worker_reasoning", locality="frontier",
        offline_profile_eligible=False, requires_network=True, local_runtime=False,
        capabilities=tuple(c["capability"] for c in CLAUDE_CODE_CAPABILITY_DESCRIPTORS),
        subscription_backed=True)


def spawn_claude_code_terminal(
    *,
    mcp_client: Any,
    governor: SubscriptionGovernor,
    subscription_ref: str,
    node_id: str,
    permission_profile_id: str,
    live_auth: LiveAuthorization,
    profile_loader: ProfileLoader,
    operator_terms_confirmed: bool,
    model: str | None = None,
    project_id: str = "proj",
    cli_present: bool | None = None,
    backend: Backend | None = None,
) -> ModelWorkerAdapter:
    """Spawn the single live `claude_code` frontier terminal, or refuse (fail closed).

    `backend` is injected by the mock-first proof (a MockClaudeCliBackend) and by the live worker
    path (`live_claude_worker_handle`, which must widen the call timeout); when omitted the real
    ClaudeCliBackend is used. Every gate applies in ALL cases — the mock proof still needs an
    authorized live_auth + confirmed terms, and gate (4) tests the INJECTED backend too, so a real
    CLI backend cannot reach a live call by being handed in. `model` selects the per-node model
    (`--model`); None ⇒ CLI default (recorded roster fallback).
    """
    cap = capability_for_claude_code()

    # (1) whole-roster profile + live gate — the real startup path
    profile_loader.assert_startup([cap], live_auth=live_auth)
    # (2) primary live gate re-asserted at the spawn site
    live_auth.assert_provider_live(CLAUDE_CODE_ADAPTER)
    # (3) R8 §6 operator live-terms confirmation
    if not operator_terms_confirmed:
        raise LiveTermsNotConfirmed(
            "R8 §6 [OPERATOR] live-terms confirmation not recorded (dated Consumer Terms + Usage "
            "Policy + Claude Code headless docs; no clause prohibits first-party wrapped-CLI under "
            "the operator's own subscription) — fail closed, no live call (directive §10.4)")
    # (4) CLI presence. Gated whenever the backend that will run is a REAL vendor CLI — including
    #     an INJECTED one. Keying this on `backend is None` meant the product's own live worker
    #     path (`live_claude_worker_handle`, which must inject to widen the call timeout) computed
    #     `cli_present` and then had it silently ignored: a documented gate was provably not on the
    #     chain, and an I-X3 terminal was acquired before the missing CLI surfaced (spec-audit
    #     MAJOR-2, Phase 17B `.legs`). A mock proof supplies a mock backend and still skips it.
    if backend is None or is_live_cli_backend(backend):
        present = _detect_cli() if cli_present is None else cli_present
        if not present:
            raise ClaudeCliUnavailable(
                "`claude` CLI not detected on host PATH — cannot spawn a live terminal (fail closed)")
    # (5) I-X3: concurrency governed by the ENFORCED authorization, never hardcoded. The
    #     allowance comes from the operator-ordered, code-pinned LiveAuthorization scope
    #     (OP-6: at most 2 terminals/subscription; a config may narrow to 1). Gates (1)/(2)
    #     have already asserted the provider live, so the allowance is in [1, 2]; the governor
    #     additionally hard-caps (defense in depth — never raise on inference). `terminals_for`
    #     is the PER-PROVIDER allowance (OP-12 §12); for `claude_code` it is the OP-6 value.
    governor.register_subscription(
        subscription_ref, CLAUDE_CODE_ADAPTER,
        allowance=live_auth.terminals_for(CLAUDE_CODE_ADAPTER))
    governor.acquire(subscription_ref, node_id)
    try:
        context = AdapterContext(
            node_id=node_id, role="worker", project_id=project_id,
            permission_profile_id=permission_profile_id, mcp_credential_id="mcp-ref",
            subscription_ref=subscription_ref, spawned_by_supervisor=True)
        # Resolve the per-node model through the single honest resolver: a requested slug is
        # carried verbatim (unverified until the live smoke), `None` ⇒ CLI default with a recorded
        # fallback surfaced in the roster (directive §11 15B, never silent). The resolver is the one
        # source of the `--model` value; a mock proof supplies its own backend.
        resolved_model, _model_note = resolve_claude_model_ref(model)
        live_backend = backend or ClaudeCliBackend(model=resolved_model)
        adapter = build_claude_code_adapter(context, mcp_client, live_backend)
    except Exception:
        governor.release(subscription_ref, node_id)  # never wedge the I-X3 count
        raise
    return adapter


@dataclass(frozen=True)
class LiveSmokeOutcome:
    """Result of the single live smoke. `ran=False, skipped_with_record=True` is the honest
    non-interactive outcome (directive §10.4): the live path is built and gated but no live
    call was made because a gate was not satisfied."""

    ran: bool
    published: bool
    skipped_with_record: bool
    reason: str
    entry_id: str | None = None
    # The per-node model resolution SURFACED on every outcome (directive §11 15B — "recorded
    # fallback surfaced in the roster, never silent"): the claude_code roster/capability descriptor
    # carrying `model_ref` (requested / resolved_slug / verified / is_fallback / note). Present even
    # on a skip-with-record so which model (or CLI-default fallback) would have run is never silent.
    model_resolution: dict | None = None


def attempt_live_smoke(
    *,
    objective_entry_id: str,
    task_id: str,
    mcp_client: Any,
    governor: SubscriptionGovernor,
    subscription_ref: str,
    node_id: str,
    permission_profile_id: str,
    live_auth: LiveAuthorization,
    profile_loader: ProfileLoader,
    operator_terms_confirmed: bool,
    model: str | None = None,
    project_id: str = "proj",
    cli_present: bool | None = None,
    backend: Backend | None = None,
    max_tokens: int = 256,
) -> LiveSmokeOutcome:
    """Run EXACTLY ONE governed smoke: spawn -> assign -> execute (one generate) -> release.

    Any gate/availability failure (unauthorized live_auth, unconfirmed terms, absent CLI) or a
    fail-closed auth pause yields skip-with-record and makes NO live call. Success publishes one
    CANDIDATE through the full MCP + local-gate path. Directive §11 15B wants one smoke per available
    model — the caller loops model refs; each call is one governed smoke.
    """
    # Surface the model resolution on EVERY outcome — even a skip-with-record must record which
    # model (or the CLI-default fallback) would have run (directive §11 15B, never silent).
    model_resolution = claude_code_roster_descriptor(model)
    try:
        adapter = spawn_claude_code_terminal(
            mcp_client=mcp_client, governor=governor, subscription_ref=subscription_ref,
            node_id=node_id, permission_profile_id=permission_profile_id, live_auth=live_auth,
            profile_loader=profile_loader, operator_terms_confirmed=operator_terms_confirmed,
            model=model, project_id=project_id, cli_present=cli_present, backend=backend)
    except Exception as exc:  # noqa: BLE001 — every gate/availability failure is skip-with-record
        return LiveSmokeOutcome(ran=False, published=False, skipped_with_record=True,
                                reason=f"{type(exc).__name__}: {exc}", model_resolution=model_resolution)
    try:
        adapter.assign(task_id, objective_entry_id)
        result = adapter.execute(max_tokens=max_tokens)
    except ClaudeCodeAuthError as exc:  # subscription expired mid-call — fail-closed pause
        return LiveSmokeOutcome(ran=True, published=False, skipped_with_record=True,
                                reason=f"auth pause (Plan §18.4): {exc}", model_resolution=model_resolution)
    finally:
        governor.release(subscription_ref, node_id)
    if result.get("published"):
        reason = "live smoke ran; CANDIDATE published"
    else:
        # bounded, structured reason — never echo the raw result dict (may carry CLI stderr)
        detail = result.get("local_gate") or result.get("backend_error") or "no output"
        reason = f"ran, not published (gate/backend: {str(detail)[:120]})"
    return LiveSmokeOutcome(
        ran=True, published=bool(result.get("published")), skipped_with_record=False,
        reason=reason, entry_id=result.get("entry_id"), model_resolution=model_resolution)


def _detect_cli() -> bool:
    from adapters import detect
    return detect.claude_code_available()
