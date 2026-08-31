"""Governed LOCAL conductor spawn — the second implementation of an interface that always claimed
to have more than one. EPC-03 L5-1.

`conductor_spawn.spawn_claude_code_conductor` is the frontier path and its own docstring calls
itself "the ONE place a LIVE `claude_code`-backed conductor is born". That was true and is the
problem: with no frontier authorization it raises `ClaudeCliUnavailable`, so on this host the
conductor could not spawn at all, while `control_plane/conductor/registry.py` went on deriving
LOCAL conductor seats from the operator's model ceiling. The system offered a seat no code path
could fill.

THE GATES ARE THE SAME GATES, TRANSLATED, NOT RELAXED. Each frontier gate has a local counterpart
that answers the same question about a different kind of cost:

  frontier                                  local
  ----------------------------------------  --------------------------------------------------
  ProfileLoader.assert_startup(cap)         same call, on the local capability
  live_auth.assert_provider_live(...)       the model must genuinely run HERE - `classify_local_model`
                                            refuses a cloud-routed tag, which is the spend wall
  R8 §6 operator live-terms confirmation    not applicable: a local model spends nothing, and
                                            requiring a spend confirmation for a free call would
                                            make the confirmation meaningless where it matters
  `claude` CLI present on PATH              the Ollama runtime present, and the model with it
  SubscriptionGovernor allowance            ResidencyPlanner reservation (invariant 19: local is
                                            NOT subscription-governed; invariant 22: VRAM is)

The one gate that has NO local counterpart is the operator terms gate, and dropping it is stated
here rather than left to be noticed. It exists because a live frontier call spends the operator's
subscription. A local call spends VRAM and time, which the residency gate governs, and nothing
else. Inventing a terms confirmation for it would train the operator to click past the one that
guards real money.

WHAT THIS DOES NOT DO. It holds no credential and needs none (Ollama is loopback-local and
unauthenticated). It adds no authority: the adapter records a decomposition as CANDIDATE exactly
as the frontier path does (invariant 16 - the conductor may propose, never promote). It spawns no
process: a local conductor is an in-process backend that calls the daemon, which is why there is
no ConPTY and no pane here.
"""
from __future__ import annotations

from typing import Any

from adapters.base.contract import AdapterCapability, AdapterContext
from adapters.conductor.adapter import ConductorAdapter
from adapters.local.conductor_backend import OllamaConductorBackend
from adapters.local.ollama_session import OLLAMA_LOCAL_ADAPTER
from node_runtime.supervisor.provider_node_registration import (
    OLLAMA_LOCAL_CAPABILITY_DESCRIPTORS,
)
from scheduler.residency_planner.residency_planner import (
    LOADING,
    RESIDENT,
    ResidencyError,
    ResidencyPlanner,
)

#: Gate ids, so a refusal can be attributed to the rule that produced it rather than to whichever
#: message happened to be nearest. Same discipline as `worker_pane_spawn`'s gate ids, and for the
#: reason recorded there: one message asserting several different causes is how an operator gets
#: pointed at the wrong fix.
GATE_ROSTER = "local_conductor_roster"
GATE_NOT_LOCAL = "local_conductor_model_is_not_local"
GATE_RUNTIME_ABSENT = "local_conductor_runtime_absent"
GATE_MODEL_ABSENT = "local_conductor_model_absent"
GATE_VRAM_BUDGET = "local_conductor_vram_budget"
GATE_VRAM_ADMISSION = "local_conductor_vram_admission"


class LocalConductorRefused(Exception):
    """A gate refused. Carries the gate id so the refusal is attributable."""

    def __init__(self, message: str, *, gate: str) -> None:
        super().__init__(message)
        self.gate = gate


def capability_for_local_conductor() -> AdapterCapability:
    """The capability the profile gate evaluates for a local conductor.

    `node_class="conductor"`, not `worker_reasoning`: the provider facts in
    `provider_node_registration` describe a local PANE, which is a worker. This is the same
    adapter filling a different seat, and saying so is what lets the roster distinguish them.

    `requires_network=False` and `offline_profile_eligible=True` are the substantive difference
    from every frontier capability in this tree, and they are the point: invariant 20 (air-gap
    honesty) says the offline profile excludes every cloud adapter. A conductor that survives that
    exclusion is what makes an offline profile a workspace rather than a read-only archive.
    """
    return AdapterCapability(
        adapter=OLLAMA_LOCAL_ADAPTER, node_class="conductor", locality="local",
        offline_profile_eligible=True, requires_network=False, local_runtime=True,
        capabilities=tuple(c["capability"] for c in OLLAMA_LOCAL_CAPABILITY_DESCRIPTORS),
        subscription_backed=False)


def _assert_model_is_local(model: str, model_record: Any) -> None:
    """The spend wall, in the only form it can take on a local path.

    The frontier path asserts `live_auth.assert_provider_live(...)` because a call there costs
    money. Here the equivalent risk is a tag that LOOKS local and is routed to a cloud endpoint by
    the daemon - the operator's own SOVEREIGN picker accepted one earlier in this programme, which
    is what put a live spend path behind a "local" label. `classify_local_model`'s cloud refusal is
    that check, and it is deliberately independent of the parameter ceiling: a cloud model is
    refused whatever its size, and an over-ceiling LOCAL model is the operator's call to make.

    A caller that supplies no record cannot be checked, and is refused rather than assumed local.
    """
    if model_record is None:
        raise LocalConductorRefused(
            f"no model record was supplied for {model!r}, so whether it runs on this host could "
            f"not be DECIDED — refused fail closed. A tag that looks local and is routed to a "
            f"cloud endpoint is a spend path wearing a local label",
            gate=GATE_NOT_LOCAL)
    from adapters.local.model_ceiling import (  # noqa: PLC0415 - import cost only on this path
        AUDIENCE_OPERATOR,
        classify_local_model,
    )
    # AUDIENCE_OPERATOR deliberately. Under that audience the PARAMETER ceiling only advises - an
    # over-ceiling local model is the operator's call, per his own ruling (ENTRY 030) - so a
    # refusal that survives it is the cloud refusal, which is the one that must hold for everyone.
    # Checking against the testing audience here would refuse the operator a 14B local conductor
    # and call it a spend-wall violation, which it is not.
    verdict = classify_local_model(model_record, audience=AUDIENCE_OPERATOR)
    if not getattr(verdict, "admitted", False):
        raise LocalConductorRefused(
            f"{model!r} is refused as a LOCAL conductor: "
            f"{getattr(verdict, 'reason', 'no reason given')}",
            gate=GATE_NOT_LOCAL)


def _reserve_vram(planner: ResidencyPlanner | None, budget: dict[str, Any] | None,
                  model: str) -> Any:
    """The residency gate, run in the same order and with the same refusals as a local PANE.

    This mirrors `worker_pane_spawn._authorize_local` deliberately rather than importing it: that
    function is bound to a `PaneSelection` and builds an interactive `ollama run` argv, which a
    conductor has no use for. What is shared is the RULE, and the rule is repeated here with its
    reasoning intact so the two cannot drift into disagreeing about whether a model fits.

    Order matters: everything decidable WITHOUT mutating the planner is decided first, because
    `request_load` mutates and the planner has no cancel primitive - a refusal after it leaves a
    phantom residency entry in the view the operator sees.
    """
    budget = budget or {}
    if planner is None or budget.get("established") is not True:
        why = str(budget.get("budget_source")
                  or ("no planner supplied" if planner is None
                      else "no VRAM budget provenance supplied with the planner"))
        raise LocalConductorRefused(
            f"a local conductor must route through the ResidencyPlanner (invariant 22) and this "
            f"host's VRAM budget could not be established: {why}. Fail closed — an authorization "
            f"is never granted against a budget nothing could verify",
            gate=GATE_VRAM_BUDGET)
    declared = budget.get("vram_budget_mb")
    enforced = planner.total_vram_mb()
    if declared != enforced:
        raise LocalConductorRefused(
            f"the VRAM budget this authorization would DISCLOSE ({declared}MB) is not the one the "
            f"planner ENFORCES ({enforced}MB) — refused (invariant 27)",
            gate=GATE_VRAM_BUDGET)

    snapshot = planner.snapshot()
    entry = next((m for m in snapshot.get("models", []) if m.get("model") == model), None)
    if entry is not None and entry.get("status") not in (RESIDENT, LOADING):
        footprint, free = entry.get("footprint_mb"), snapshot.get("free_vram_mb")
        if not isinstance(footprint, int) or not isinstance(free, int) or footprint > free:
            raise LocalConductorRefused(
                f"a local conductor on {model!r} ({footprint}MB) does not fit in the free VRAM "
                f"({free}MB of {snapshot.get('total_vram_mb')}MB) — refused rather than scheduled, "
                f"because this planner MIRRORS the daemon's residency and cannot tell whether a "
                f"model it considers idle is answering a prompt right now (invariant 22)",
                gate=GATE_VRAM_ADMISSION)
    try:
        decision = planner.request_load(model)
    except ResidencyError as exc:
        raise LocalConductorRefused(
            f"residency/VRAM planner refused {model!r}: {exc} (invariant 22)",
            gate=GATE_VRAM_ADMISSION) from exc
    displaced = list(decision.evicted) + list(decision.awaiting_eviction)
    if displaced:
        raise LocalConductorRefused(
            f"a local conductor on {model!r} would only fit by displacing {displaced} — refused "
            f"(invariant 22, never a mid-generation eviction)", gate=GATE_VRAM_ADMISSION)
    return decision


def spawn_local_conductor(
    *,
    mcp_client: Any,
    model: str,
    node_id: str,
    permission_profile_id: str,
    profile_loader: Any,
    conductor_file_refs: dict[str, str],
    residency_planner: ResidencyPlanner | None = None,
    residency_budget: dict[str, Any] | None = None,
    model_record: Any = None,
    installed_models: Any = None,
    runtime_present: bool | None = None,
    project_id: str = "proj",
    backend: Any = None,
) -> tuple[ConductorAdapter, dict[str, Any]]:
    """Build a LOCAL conductor, or refuse. Returns the adapter and its authorization record.

    The adapter is NOT started; the caller calls `.start()`, which loads the conductor files from
    MCP. No subscription terminal is acquired at start because there is none to acquire - the
    context carries no `subscription_ref` and no governor, so `ConductorAdapter.start()` skips the
    acquire branch by its own existing condition rather than by a special case added for this path.

    `backend` is injected only by tests and by a mock-first proof. Every gate applies in both cases:
    a mock backend does not exempt a caller from the residency reservation, because the reservation
    is about the HOST's VRAM and not about whether this particular call reaches the daemon.
    """
    if not isinstance(model, str) or not model.strip():
        raise LocalConductorRefused("a local conductor needs a model tag", gate=GATE_ROSTER)
    model = model.strip()

    # (1) roster eligibility. No `live_auth` argument: this capability is not a live provider, and
    #     passing one would assert a live gate on a path that can never spend.
    capability = capability_for_local_conductor()
    try:
        profile_loader.assert_startup([capability])
    except Exception as exc:  # noqa: BLE001 - re-raised as an attributable refusal
        raise LocalConductorRefused(
            f"the profile roster refused a local conductor on {model!r}: {exc}",
            gate=GATE_ROSTER) from exc

    # (2) the spend wall: this model must genuinely run on this host.
    _assert_model_is_local(model, model_record)

    # (3) the runtime, and the model with it. Two conditions because they fail differently: a
    #     missing runtime is an install problem, a missing model is a `pull` the operator has not
    #     run, and one message covering both sends him to the wrong fix.
    if runtime_present is None:
        from adapters import detect  # noqa: PLC0415
        runtime_present = detect.ollama_executable() is not None
    if not runtime_present:
        raise LocalConductorRefused(
            "the local `ollama` runtime is not available on this host — cannot spawn a local "
            "conductor (fail closed)", gate=GATE_RUNTIME_ABSENT)
    if installed_models is not None:
        names = {str(n) for n in installed_models}
        if model not in names:
            raise LocalConductorRefused(
                f"{model!r} is not installed on this host (`ollama pull {model}` has not been "
                f"run) — refused rather than spawned against a tag the daemon would have to "
                f"fetch mid-dispatch", gate=GATE_MODEL_ABSENT)

    # (4) VRAM residency — the local counterpart of the subscription allowance.
    decision = _reserve_vram(residency_planner, residency_budget, model)

    conductor_backend = backend if backend is not None else OllamaConductorBackend(model)
    context = AdapterContext(
        node_id=node_id, role="conductor", project_id=project_id,
        permission_profile_id=permission_profile_id, mcp_credential_id="mcp-ref",
        # No subscription: invariant 19. An empty ref is not a placeholder for one that exists -
        # `ConductorAdapter.start()` reads it as "nothing to acquire", which is the truth here.
        subscription_ref="", spawned_by_supervisor=True)
    adapter = ConductorAdapter(context, mcp_client, conductor_backend, None, conductor_file_refs)

    authorization = {
        "adapter": OLLAMA_LOCAL_ADAPTER,
        "locality": "local",
        "node_class": "conductor",
        "model": model,
        "model_name": getattr(conductor_backend, "model_name", None),
        "subscription": None,          # invariant 19, stated rather than omitted
        "residency": decision.as_dict() if hasattr(decision, "as_dict") else None,
        "credential_held": False,
        "spawned_by_supervisor": True,
        "note": ("A local conductor PROPOSES; the ConductorAdapter records the result as "
                 "CANDIDATE. It holds no credential and spends no subscription."),
    }
    return adapter, authorization
