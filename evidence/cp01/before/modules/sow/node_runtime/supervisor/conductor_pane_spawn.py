"""Governed conductor-first pane — the ONE place the LIVE interactive CONDUCTOR chat pane is born.
Phase 15E `.conductor-pane` (directive §13 / OP-8; §12.4 conductor-first startup).

`pane_node_spawn.spawn_node_from_selection` REFUSES the conductor role and points here: the conductor
is not a worker handle under a "conductor" badge — it is the conductor-first, pinned, succession-capable
pane 1 the operator lands in on launch and *talks to* (OP-8 §13). This module produces that GOVERNED
pane, reusing the frontier live-gate set verbatim (a live conductor pane is a subscription-backed live
path exactly like a live worker) and differing only in what it builds:

  * an INTERACTIVE `claude` launch (`build_interactive_command` — NO `-p`; the operator drives it),
    not the one-shot `claude -p --output-format json` worker command;
  * the CONDUCTOR chrome: pinned pane 1, model badge = the current SELECTION (fable-5 / recorded
    fallback), `attended` mode (the operator types into it);
  * the Resume→Select succession affordance reachable from that chrome (invariant 28 / OP-8 §13.7).

Order of gates (all must pass; any failure ⇒ no conductor pane):
  1. `ProfileLoader.assert_startup([claude_code cap], live_auth)` — roster eligibility AND the
     LIVE_OPERATION_AUTHORIZED gate (keyed on the PROVIDER capability, never on the selection label).
  2. `LiveAuthorization.assert_provider_live("claude_code")` — the primary live gate re-asserted.
  3. R8 §6 operator live-terms confirmation — `[OPERATOR]`-flagged; unmet ⇒ fail-closed refusal.
  4. `claude` CLI present on the host (real launch only; a mock launcher injects its own session).
  5. I-X3: register the authorized allowance, then acquire this pane's ONE subscription terminal;
     release on any construction failure so the count never wedges.

Honesty (invariant 3, §6/§10.4): the badge shows the operator SELECTION label ("fable-5"); the
EXECUTING checkpoint stays unverified until a live reply reports one (`bind_conductor_selection`). This
module builds and gates the interactive session but makes NO live call itself — the actual interactive
ConPTY drive is an operator-run surface like every GUI in this build (directive §6 substitution). A
mock-first `launcher` proves the whole governed path with zero live calls; a real interactive launch
supplies a real launcher through the identical path and is torn down within its unit (D-LOOP-1).

Out of scope for THIS sub-step (kept honest, not faked): native-MCP orchestration — the conductor
dispatching to worker CLIs while conversing (OP-8 §13.4) is `.objective`; voice-IN (§13.5) is `.voice`;
restart recovery of the conductor-first layout is `.recovery`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER
from adapters.conductor.provider_commands import (
    ConductorProviderUnavailable,
    commands_for,
    scrubbed_environment,
)
from control_plane.conductor.registry import ConductorDescriptor, resolve_conductor_descriptor
from control_plane.conductor.selection import (
    OPERATOR_SELECTED_CONDUCTOR,
    ConductorSelection,
    bind_conductor_selection,
)
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import ProfileLoader
from node_runtime.supervisor.frontier_spawn import ClaudeCliUnavailable, LiveTermsNotConfirmed
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor

CONDUCTOR_LABEL = "CONDUCTOR"
ATTENDED = "attended"


class ConductorPaneRefused(Exception):
    """A conductor-first pane spawn refused fail-closed by this coordinator — a naked identity or a
    frontier selection with no subscription_ref (an uncounted terminal defeats I-X3).

    Distinct from the live gates' own exceptions (`LiveAuthorizationError`, `LiveTermsNotConfirmed`,
    `ClaudeCliUnavailable`, `SubscriptionLimitExceeded`), which propagate unchanged: those are the
    supervised path enforcing its live gates. This is the identity/counting-level refusal."""


def conductor_succession_affordance(
    selection: ConductorSelection = OPERATOR_SELECTED_CONDUCTOR,
) -> dict[str, Any]:
    """The Resume→Select control the conductor chrome surfaces (OP-7 §12.4; directive §13.7).

    Data only — this does NOT perform a succession. The actual serialize/reconstruct/restore is
    `control_plane.recovery.succession.SuccessionManager` + `restore_operator_selection` (built and
    gated at Phase 15D). This states that the control is reachable from the pane chrome and what it
    will do, in a stable fail-closed shape the renderer draws a button from."""
    return {
        "available": True,
        "control": "resume_select",
        "actions": ["resume", "select", "restore"],
        "current_selection": selection.as_current_conductor(),
        # what "restore selection" returns to after a succession (invariant 28 / 15D)
        "restore_target": selection.model,
        "note": ("kill the conductor mid-run → Resume → Select a backend → reconstruct zero-loss "
                 "(SuccessionManager) → restore the operator selection (restore_operator_selection)."),
    }


@dataclass
class ConductorPaneChrome:
    """The CONDUCTOR pane chrome the shell renders (OP-8 §13 / OP-7 §12.4). `governed=True` always —
    a naked session never reaches chrome; `interactive=True` — a live agentic chat, not a one-shot
    worker. The model badge shows the SELECTION label, never a fabricated executing checkpoint id."""

    provider: str
    adapter: str
    model_label: str                     # the SELECTION label ("fable-5"), never a checkpoint id
    model_slug: str | None               # the resolved `--model` slug; None ⇒ CLI-default fallback
    model_verified: bool                 # False until a live reply reports the executing checkpoint
    is_fallback: bool                    # True ⇒ recorded CLI-default fallback (directive §11 15B)
    node_id: str
    node_state: str                      # "ready" (a session launched) | "awaiting_live_conductor"
    subscription: dict[str, Any] | None  # {ref, in_use, allowance} (I-X3 n/2 visible in chrome)
    succession: dict[str, Any]           # the Resume→Select affordance reachable from chrome
    label: str = CONDUCTOR_LABEL
    pane_ordinal: int = 1                # conductor-first: pane 1 on launch (§12.4)
    pinned: bool = True                  # pinned by default (§12.4)
    role: str = "conductor"
    mode: str = ATTENDED                 # the operator talks to it (OP-8 §13.2)
    locality: str = "frontier"
    governed: bool = True
    interactive: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label, "pane_ordinal": self.pane_ordinal, "pinned": self.pinned,
            "role": self.role, "mode": self.mode, "provider": self.provider,
            "adapter": self.adapter, "locality": self.locality, "model_label": self.model_label,
            "model_slug": self.model_slug, "model_verified": self.model_verified,
            "is_fallback": self.is_fallback, "node_id": self.node_id, "node_state": self.node_state,
            "governed": self.governed, "interactive": self.interactive,
            "subscription": dict(self.subscription) if self.subscription is not None else None,
            "succession": dict(self.succession),
        }


@dataclass
class ConductorPaneSession:
    """The result of a governed conductor-pane spawn: the pinned CONDUCTOR chrome, the interactive
    launch spec (argv + the fact the env is credential-scrubbed), the honest CHOSEN/REQUESTED/
    EXECUTING selection record, the live session handle (a mock in the mock-first proof; None when
    the real interactive launch is deferred to the operator-run shell), and a teardown that closes
    any launched session and releases the governed I-X3 count (D-LOOP-1)."""

    chrome: ConductorPaneChrome
    launch: dict[str, Any]
    selection_record: dict[str, Any]
    handle: Any = None
    launched: bool = False
    _release: Callable[[], None] | None = field(default=None, repr=False)

    def teardown(self) -> None:
        """Close a launched interactive session (if any), then release the I-X3 count (D-LOOP-1).
        Idempotent: the governor release uses `discard`, and a second call is harmless. The release
        runs in a `finally` so the count is freed even if the session's `close` raises."""
        try:
            if self.handle is not None and hasattr(self.handle, "close"):
                self.handle.close()
        finally:
            if self._release is not None:
                self._release()


def _subscription_view(governor: SubscriptionGovernor, ref: str,
                       live_auth: LiveAuthorization, provider: str) -> dict[str, Any]:
    status = governor.status().get(ref, {})
    return {"ref": ref, "in_use": governor.active_count(ref),
            # the conductor pane is always the Anthropic backend, so the per-provider allowance is
            # the honest fallback when the governor has no row yet (never the global number)
            "allowance": status.get("allowance", live_auth.terminals_for(provider))}


def spawn_conductor_pane(
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
    selection: ConductorSelection = OPERATOR_SELECTED_CONDUCTOR,
    model_available: bool | None = None,
    project_id: str = "proj",
    cli_present: bool | None = None,
    launcher: Callable[..., Any] | None = None,
    executable: str = "claude",
    descriptor: ConductorDescriptor | None = None,
) -> ConductorPaneSession:
    """Spawn the governed, conductor-first, interactive CONDUCTOR pane, or refuse (fail closed).

    `selection` is the operator's conductor SELECTION (default: fable-5, OP-6 — invariant 3). `model`
    overrides the requested `--model` slug; omitted ⇒ the selection's own model. `model_available=False`
    records the CLI-default fallback branch (directive §11 15B — never silent). `launcher` is injected
    only by the mock-first proof (`launcher(argv=..., env=..., node_id=...)` returning a session handle
    with a `close()`); when omitted, the real interactive launch is deferred to the operator-run shell
    and no live call is made here. Every gate applies in BOTH cases. `mcp_client` is accepted for
    signature parity with the other supervised spawn paths (the interactive session attaches to MCP
    natively at `.objective`; it is not read here)."""
    # (0) fail-closed identity/counting checks FIRST — before any gate/governor mutation.
    desc = descriptor or resolve_conductor_descriptor(
        selection.adapter or CLAUDE_CODE_ADAPTER, selection.model)
    if desc.role != "conductor" or not desc.registered or not desc.conductor_capable:
        raise ConductorPaneRefused("selection is not a registered conductor-capable descriptor")
    if descriptor is not None and desc.subscription_ref != subscription_ref:
        raise ConductorPaneRefused(
            f"selection subscription {desc.subscription_ref!r} does not match launch subscription "
            f"{subscription_ref!r} (fail closed)")
    if descriptor is not None and desc.permission_profile_id != permission_profile_id:
        raise ConductorPaneRefused("selection permission profile does not match launch identity")
    provider = desc.adapter_id
    provider_commands = commands_for(provider)

    if not node_id:
        raise ConductorPaneRefused(
            "conductor pane has no node identity — no naked session (invariant 2/29)")
    if not permission_profile_id:
        raise ConductorPaneRefused(
            "conductor pane has no supervisor-issued permission profile — no naked session (inv 2/29)")
    if not subscription_ref:
        raise ConductorPaneRefused(
            "conductor pane has no subscription_ref — refuse an uncounted terminal (I-X3, fail closed)")

    # The gate keys on the PROVIDER capability (claude_code, node_class worker_reasoning), NOT the
    # conductor role/label: a conductor pane is a subscription-backed live path gated exactly like a
    # live worker — the conductor-ness is chrome + the interactive launch, not a distinct capability.
    cap = provider_commands.capability()
    # (1) whole-roster profile + LIVE_OPERATION_AUTHORIZED gate — the real startup path.
    profile_loader.assert_startup([cap], live_auth=live_auth)
    # (2) primary live gate re-asserted at the spawn site.
    live_auth.assert_provider_live(provider)
    # (3) R8 §6 operator live-terms confirmation.
    if not operator_terms_confirmed:
        raise LiveTermsNotConfirmed(
            "R8 §6 [OPERATOR] live-terms confirmation not recorded — fail closed, no live conductor "
            "pane (directive §10.4)")
    # (4) CLI presence (real launch only; a mock launcher supplies its own session).
    resolved_executable = provider_commands.resolve_executable()
    if launcher is None:
        present = bool(resolved_executable) if cli_present is None else cli_present
        if not present:
            if descriptor is None and provider == CLAUDE_CODE_ADAPTER:
                raise ClaudeCliUnavailable(
                    "`claude` CLI not detected on host PATH — cannot open a live conductor pane (fail closed)")
            raise ConductorProviderUnavailable(
                "`claude` CLI not detected on host PATH — cannot open a live conductor pane (fail closed)")
    # (5) I-X3: register the authorized allowance, then acquire this pane's ONE terminal.
    governor.register_subscription(
        subscription_ref, provider,
        allowance=live_auth.terminals_for(provider))
    governor.acquire(subscription_ref, node_id)
    try:
        requested = model if model is not None else desc.model_id
        # ONE honest binding is the source of the badge, the argv slug, AND the record: CHOSEN
        # (selection label) / REQUESTED (--model slug) / EXECUTING (None until a live reply). A
        # requested model that has been probed unavailable resolves to the CLI-default fallback.
        binding = bind_conductor_selection(
            selection, requested_model=requested, model_available=model_available,
            resolver=provider_commands.resolve_model)
        resolved_slug = binding.resolved_slug  # None ⇒ CLI default (recorded fallback)
        exe = ((resolved_executable or provider_commands.executable_name)
               if descriptor is not None else executable)
        argv = provider_commands.build_command(exe, resolved_slug, desc.workspace)
        env = scrubbed_environment()  # §2.2: every credential/endpoint var removed
        selection_record = binding.as_record()

        handle = None
        launched = False
        if launcher is not None:
            # mock-first: prove the interactive launch path end-to-end with ZERO live calls.
            handle = launcher(argv=argv, env=env, node_id=node_id)
            launched = handle is not None
        node_state = "ready" if launched else "awaiting_live_conductor"

        chrome = ConductorPaneChrome(
            provider=desc.provider_id, adapter=desc.adapter_id,
            model_label=desc.display_name if descriptor is not None else selection.model,
            model_slug=resolved_slug,
            model_verified=binding.executing_verified,  # False until a live reply
            is_fallback=binding.is_fallback,
            node_id=node_id, node_state=node_state,
            subscription=_subscription_view(governor, subscription_ref, live_auth, provider),
            succession=conductor_succession_affordance(selection))
        launch = {
            "argv": argv,
            "interactive": True,
            "one_shot": False,            # NOT `claude -p` — the operator drives the session
            "env_credential_scrubbed": True,
            "launched": launched,
            "note": (f"interactive `{provider_commands.executable_name}` session for the operator's "
                     "live CONDUCTOR chat pane; provider flags were constructed by the registered "
                     "adapter and the shared ConPTY lifecycle remains provider-neutral."),
        }
    except Exception:
        governor.release(subscription_ref, node_id)  # never wedge the I-X3 count
        raise
    return ConductorPaneSession(
        chrome=chrome, launch=launch, selection_record=selection_record,
        handle=handle, launched=launched,
        _release=lambda: governor.release(subscription_ref, node_id))
