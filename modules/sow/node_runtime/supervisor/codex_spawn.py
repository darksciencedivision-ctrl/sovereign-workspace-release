"""Governed live-Codex spawn path — the ONE place a live `openai_codex_cli` terminal is born.
Phase 15C `.adapter` (directive §11 track 15C; register OP-6).

The second live frontier provider the operator authorized (OP-6). This is the real supervisor/
startup path the directive requires to enforce, at the actual spawn site and before any live call,
every entry condition for live operation. It is deterministic, fail-closed permission logic
(Buildout Directive §4) — never model output — and mirrors frontier_spawn.py (`claude_code`)
exactly so the two live providers share one governed shape.

Order of gates (all must pass; any failure => no live spawn):
  1. `ProfileLoader.assert_startup([cap], live_auth)` — whole-roster profile eligibility AND the
     LIVE_OPERATION_AUTHORIZED gate, driving the REAL entrypoint.
  2. `LiveAuthorization.assert_provider_live("openai_codex_cli")` — the primary gate re-asserted at
     the live-spawn site (belt-and-suspenders; distinct call site from the roster check).
  3. R8 §6 operator live-terms confirmation — the `[OPERATOR]`-flagged item from
     R8_TOS_VERIFICATION_OPENAI_CODEX.md §6 (the wrapped-orchestrator ToS interpretation). In a
     non-interactive session it is unmet => skip-with-record (directive §10.4).
  4. `codex` CLI actually present on the host (real backend only; a mock proof injects its backend
     and skips this).
  5. SubscriptionGovernor.acquire — I-X3, concurrency governed by the enforced authorization
     (OP-6: at most 2 terminals/subscription, read from live_auth; a config may narrow to 1).
Only then is a supervisor-issued AdapterContext constructed (spawned_by_supervisor=True) and handed
to the live adapter. If construction fails the terminal is released (no wedged count).

The credential itself is never touched here or in the adapter (§2.2): the `codex` CLI holds its own
ChatGPT-subscription OAuth token in a host-native store (`~/.codex/auth.json`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from adapters.base.backend import Backend
from adapters.base.contract import AdapterCapability, AdapterContext
from adapters.frontier.codex import (
    CODEX_ADAPTER,
    _ROLE_DESCRIPTORS,
    _ROLE_NODE_CLASS,
    CodexAuthError,
    CodexCliBackend,
    build_codex_adapter,
    codex_roster_descriptor,
    resolve_codex_model_ref,
)
from adapters.model_adapter import ModelWorkerAdapter
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import ProfileLoader
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor


class LiveTermsNotConfirmed(Exception):
    """The R8 §6 [OPERATOR] live-terms confirmation is not recorded — fail closed, no live call."""


class CodexCliUnavailable(Exception):
    """The `codex` CLI is not present on the host — cannot spawn a live terminal, fail closed."""


def capability_for_codex(role: str = "reasoning") -> AdapterCapability:
    """The live frontier capability the profile/live gate evaluates. `adapter="openai_codex_cli"`
    (not the `mock` sentinel) is what makes ProfileLoader treat this as a REAL live path."""
    if role not in _ROLE_NODE_CLASS:
        raise ValueError(f"unknown codex worker role {role!r} — expected reasoning|coding")
    return AdapterCapability(
        adapter=CODEX_ADAPTER, node_class=_ROLE_NODE_CLASS[role], locality="frontier",
        offline_profile_eligible=False, requires_network=True, local_runtime=False,
        capabilities=tuple(c["capability"] for c in _ROLE_DESCRIPTORS[role]),
        subscription_backed=True)


def spawn_codex_terminal(
    *,
    mcp_client: Any,
    governor: SubscriptionGovernor,
    subscription_ref: str,
    node_id: str,
    permission_profile_id: str,
    live_auth: LiveAuthorization,
    profile_loader: ProfileLoader,
    operator_terms_confirmed: bool,
    role: str = "reasoning",
    model: str | None = None,
    workdir: str | None = None,
    project_id: str = "proj",
    cli_present: bool | None = None,
    backend: Backend | None = None,
) -> ModelWorkerAdapter:
    """Spawn a single live `openai_codex_cli` frontier terminal, or refuse (fail closed).

    `backend` is injected only by the mock-first proof (a MockCodexCliBackend); when omitted the
    real CodexCliBackend is used and the host CLI must be present. Every gate applies in BOTH cases
    — the mock proof still needs an authorized live_auth + confirmed terms. `role`/`model`/`workdir`
    configure per-node model selection and coding-role worktree isolation.
    """
    cap = capability_for_codex(role)

    # (1) whole-roster profile + live gate — the real startup path
    profile_loader.assert_startup([cap], live_auth=live_auth)
    # (2) primary live gate re-asserted at the spawn site
    live_auth.assert_provider_live(CODEX_ADAPTER)
    # (3) R8 §6 operator live-terms confirmation
    if not operator_terms_confirmed:
        raise LiveTermsNotConfirmed(
            "R8 §6 [OPERATOR] live-terms confirmation not recorded for openai_codex_cli (dated "
            "OpenAI Consumer/Business terms + Codex CLI headless docs; no clause prohibits "
            "first-party wrapped-CLI under the operator's own subscription) — fail closed, no live "
            "call (directive §10.4)")
    # (4) CLI presence (real backend only; a mock proof supplies its own backend)
    if backend is None:
        present = _detect_cli() if cli_present is None else cli_present
        if not present:
            raise CodexCliUnavailable(
                "`codex` CLI not detected on host PATH — cannot spawn a live terminal (fail closed)")
    # (5) I-X3: concurrency governed by the ENFORCED authorization, never hardcoded. The allowance
    #     comes from the operator-ordered, code-pinned LiveAuthorization scope (OP-6: at most 2
    #     terminals/subscription; a config may narrow to 1). Gates (1)/(2) have already asserted the
    #     provider live, so the allowance is in [1, 2]; the governor additionally hard-caps
    #     (defense in depth — never raise on inference). `terminals_for` is the PER-PROVIDER
    #     allowance (OP-12 §12 caps its two providers at 1 under a config that says 2); for
    #     `openai_codex_cli` it is the OP-6 value unchanged.
    governor.register_subscription(
        subscription_ref, CODEX_ADAPTER, allowance=live_auth.terminals_for(CODEX_ADAPTER))
    governor.acquire(subscription_ref, node_id)
    try:
        context = AdapterContext(
            node_id=node_id, role="worker", project_id=project_id,
            permission_profile_id=permission_profile_id, mcp_credential_id="mcp-ref",
            subscription_ref=subscription_ref, spawned_by_supervisor=True)
        # Resolve the per-node model through the single honest resolver: a requested slug is
        # carried verbatim (unverified until the live smoke), `None` ⇒ CLI default with a
        # recorded fallback surfaced in the roster (directive §11 15C, never silent). The
        # resolver is the one source of the `-m` value; a mock proof supplies its own backend.
        resolved_model, _model_note = resolve_codex_model_ref(model)
        live_backend = backend or CodexCliBackend(model=resolved_model, role=role, workdir=workdir)
        adapter = build_codex_adapter(context, mcp_client, live_backend, role=role)
    except Exception:
        governor.release(subscription_ref, node_id)  # never wedge the I-X3 count
        raise
    return adapter


@dataclass(frozen=True)
class LiveSmokeOutcome:
    """Result of the single live smoke. `ran=False, skipped_with_record=True` is the honest
    non-interactive outcome (directive §10.4): the live path is built and gated but no live call was
    made because a gate was not satisfied."""

    ran: bool
    published: bool
    skipped_with_record: bool
    reason: str
    entry_id: str | None = None
    # The per-node model resolution SURFACED on every outcome (directive §11 15C — "recorded
    # fallback surfaced in the roster, never silent"): the codex roster/capability descriptor
    # carrying `model_ref` (requested / resolved_slug / verified / is_fallback / note). Present
    # even on a skip-with-record so which model (or CLI-default fallback) would have run is
    # never silent. None only if the descriptor could not be built (unknown role).
    model_resolution: dict | None = None


def attempt_codex_live_smoke(
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
    role: str = "reasoning",
    model: str | None = None,
    workdir: str | None = None,
    project_id: str = "proj",
    cli_present: bool | None = None,
    backend: Backend | None = None,
    max_tokens: int = 256,
) -> LiveSmokeOutcome:
    """Run EXACTLY ONE governed smoke: spawn -> assign -> execute (one generate) -> release.

    Any gate/availability failure (unauthorized live_auth, unconfirmed terms, absent CLI) or a
    fail-closed auth pause yields skip-with-record and makes NO live call. Success publishes one
    CANDIDATE through the full MCP + local-gate path. Directive §11 15C wants one smoke per available
    model — the caller loops model refs; each call is one governed smoke.
    """
    # Surface the model resolution on EVERY outcome — even a skip-with-record must record which
    # model (or the CLI-default fallback) would have run (directive §11 15C, never silent).
    try:
        model_resolution: dict | None = codex_roster_descriptor(role, model)
    except ValueError:
        model_resolution = None  # unknown role — the spawn below fails closed and records it
    try:
        adapter = spawn_codex_terminal(
            mcp_client=mcp_client, governor=governor, subscription_ref=subscription_ref,
            node_id=node_id, permission_profile_id=permission_profile_id, live_auth=live_auth,
            profile_loader=profile_loader, operator_terms_confirmed=operator_terms_confirmed,
            role=role, model=model, workdir=workdir, project_id=project_id,
            cli_present=cli_present, backend=backend)
    except Exception as exc:  # noqa: BLE001 — every gate/availability failure is skip-with-record
        return LiveSmokeOutcome(ran=False, published=False, skipped_with_record=True,
                                reason=f"{type(exc).__name__}: {exc}", model_resolution=model_resolution)
    try:
        adapter.assign(task_id, objective_entry_id)
        result = adapter.execute(max_tokens=max_tokens)
    except CodexAuthError as exc:  # subscription expired mid-call — fail-closed pause
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
    return detect.codex_available()
