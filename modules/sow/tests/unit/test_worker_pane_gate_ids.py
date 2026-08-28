"""Worker-pane refusals name the GATE that refused, and the VRAM messages state the cause they saw.

Both come out of the 2026-07-26 gate-validator re-validation of 17B `.ticket`:

  * **BLOCKING-1c** — the in-Electron receipt's "invariant 22 admission gate refused an over-budget
    pane" leg asserted `/VRAM|residency|displacing/i` against the refusal prose. An enumeration CRASH
    whose message happened to contain "VRAM" satisfied it, so the leg went green while proving
    nothing about invariant 22. Every refusal now carries a machine-readable `gate` id, the ticket
    reports it as `refused_by`, and the legs assert THAT — an id cannot be borrowed by another gate.
  * **BLOCKING-1a/b** — a `None` planner means the budget could not be ESTABLISHED (daemon
    unreachable, or a budget the host's own residency falsified). That is not "your model does not
    fit"; reporting it as such sends the operator hunting for VRAM they already have.
  * **MINOR-1** — one message asserted "would only fit by displacing another resident model" for
    every over-budget case, including ones where nothing is resident at all.

Zero live calls, zero host dependence: the planner and the gates are injected.
"""
from __future__ import annotations

import pytest

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
from node_runtime.supervisor.pane_node_spawn import PaneSelection, SpawnRefused
from node_runtime.supervisor.subscription_governor import (
    SubscriptionGovernor,
    canonical_subscription_ref,
)
from node_runtime.supervisor.worker_pane_spawn import (
    GATE_ROLE_DEFERRED,
    GATE_RUNTIME_ABSENT,
    GATE_SUBSCRIPTION_REF,
    GATE_UNKNOWN_ADAPTER,
    GATE_VRAM_ADMISSION,
    GATE_VRAM_BUDGET,
    GATE_WORKER_ROLE,
    OLLAMA_LOCAL_ADAPTER,
    WorkerPaneRefused,
    authorize_worker_pane,
    worker_identity,
)
from scheduler.residency_planner.residency_planner import ResidencyPlanner

WORKSPACE = "D:/repo"


def _authorized() -> LiveAuthorization:
    return LiveAuthorization(
        authorized=True, providers=frozenset({CLAUDE_CODE_ADAPTER}), terminals_per_subscription=2,
        register_row="OP-6", source="(test)", reason="test authorization")


def _loader() -> ProfileLoader:
    return ProfileLoader(DeploymentProfile("cloud"))


def _frontier_option() -> dict:
    return {"provider": CLAUDE_CODE_ADAPTER, "adapter": CLAUDE_CODE_ADAPTER, "locality": "frontier",
            "subscription_backed": True, "label": "fable-5", "model_slug": "fable-5",
            "verified": False, "is_fallback": False, "roles": ["reasoning", "coding"],
            "residency": None, "available": True, "unavailable_reason": None}


def _local_option(**over: object) -> dict:
    option = {"provider": OLLAMA_LOCAL_ADAPTER, "adapter": OLLAMA_LOCAL_ADAPTER, "locality": "local",
              "subscription_backed": False, "label": "qwen3:8b", "model_slug": "qwen3:8b",
              "verified": True, "is_fallback": False, "roles": ["reasoning", "coding"],
              "residency": "not_loaded", "available": True, "unavailable_reason": None}
    option.update(over)
    return option


def _selection(option: dict, *, role: str = "reasoning", subscription_ref: str | None = None,
               ) -> PaneSelection:
    return PaneSelection(option=option, role=role, mode="autonomous", node_id="worker-pane-2",
                         permission_profile_id=f"pp-worker-{role}", subscription_ref=subscription_ref)


def _authorize(option: dict, **kw: object):
    role = str(kw.pop("role", "reasoning"))
    sub = kw.pop("subscription_ref", None)
    return authorize_worker_pane(
        _selection(option, role=role, subscription_ref=sub),  # type: ignore[arg-type]
        live_auth=_authorized(), governor=SubscriptionGovernor(), profile_loader=_loader(),
        operator_terms_confirmed=True, workspace=WORKSPACE, **kw)  # type: ignore[arg-type]


def _established_budget(total_mb: int = 12288) -> dict:
    """An ESTABLISHED budget, as the host enumeration returns alongside a usable planner. Required:
    the local gate refuses an authorization whose budget was never established (spec-audit
    MAJOR-1) — a planner alone says nothing about what its total means."""
    return {"vram_budget_mb": total_mb, "budget_source": "(test) established budget",
            "estimate": True, "established": True}


def _resident(planner: ResidencyPlanner, name: str) -> ResidencyPlanner:
    planner.request_load(name)
    planner.complete_load(name)
    return planner


# -- every refusal names its gate -----------------------------------------------------------------

def test_the_identity_minter_refuses_under_the_worker_role_gate() -> None:
    for bad in (("pane 2", "reasoning"), ("pane-2", "conductor"), ("", "reasoning"),
                ("pane#2", "reasoning")):
        with pytest.raises(WorkerPaneRefused) as exc:
            worker_identity(*bad)
        assert exc.value.gate == GATE_WORKER_ROLE


def test_an_adapter_outside_the_authorized_scope_refuses_under_its_own_gate() -> None:
    with pytest.raises(WorkerPaneRefused) as exc:
        _authorize(_local_option(adapter="some_other_vendor"))
    assert exc.value.gate == GATE_UNKNOWN_ADAPTER


def test_a_frontier_selection_with_no_subscription_ref_refuses_under_the_ix3_gate() -> None:
    with pytest.raises(WorkerPaneRefused) as exc:
        _authorize(_frontier_option())
    assert exc.value.gate == GATE_SUBSCRIPTION_REF


def test_both_coding_paths_refuse_under_the_deferred_role_gate() -> None:
    with pytest.raises(WorkerPaneRefused) as exc:
        _authorize(_frontier_option(), role="coding",
                   subscription_ref=canonical_subscription_ref(CLAUDE_CODE_ADAPTER))
    assert exc.value.gate == GATE_ROLE_DEFERRED
    with pytest.raises(WorkerPaneRefused) as exc2:
        _authorize(_local_option(), role="coding")
    assert exc2.value.gate == GATE_ROLE_DEFERRED


def test_an_absent_local_runtime_refuses_under_the_runtime_gate_not_the_vram_one() -> None:
    with pytest.raises(WorkerPaneRefused) as exc:
        _authorize(_local_option(), ollama_present=False)
    assert exc.value.gate == GATE_RUNTIME_ABSENT


def test_the_selection_guard_carries_its_own_gate_id() -> None:
    """The shared guard's refusals must be distinguishable from the emitter's host-enumeration
    check, which uses the same exception class — that is exactly the pair BLOCKING-1c confused."""
    with pytest.raises(SpawnRefused) as exc:
        _authorize(_local_option(available=False, unavailable_reason="daemon down"))
    assert exc.value.gate == "selection_guard"


# -- the VRAM gate says what it saw ----------------------------------------------------------------

def test_a_budget_that_could_not_be_established_is_refused_as_such_not_as_no_room() -> None:
    budget = {"vram_budget_mb": None, "established": False, "estimate": True,
              "budget_source": "STAND-IN 12288MB constant — FALSIFIED by the host: 16000MB is "
                               "already resident. Set SOW_VRAM_BUDGET_MB to this host's real VRAM"}
    with pytest.raises(WorkerPaneRefused) as exc:
        _authorize(_local_option(), residency_planner=None, residency_budget=budget,
                   ollama_present=True, executable="ollama")
    # its OWN gate, not the fit gate: nothing was measured, so this refusal is not evidence that a
    # model does not fit (spec-audit MAJOR-1, 2026-07-26).
    assert exc.value.gate == GATE_VRAM_BUDGET
    assert exc.value.gate != GATE_VRAM_ADMISSION
    assert "could not be established" in str(exc.value)
    assert "FALSIFIED" in str(exc.value)               # the enumeration's own reason is repeated
    assert "SOW_VRAM_BUDGET_MB" in str(exc.value)
    assert "does not fit" not in str(exc.value)        # never a claim about the model


def test_a_model_larger_than_the_whole_budget_is_not_blamed_on_a_resident_model() -> None:
    planner = ResidencyPlanner(1)
    planner.register_model("qwen3:8b", 4983)
    with pytest.raises(WorkerPaneRefused) as exc:
        _authorize(_local_option(), residency_planner=planner,
                   residency_budget=_established_budget(1), ollama_present=True,
                   executable="ollama")
    assert exc.value.gate == GATE_VRAM_ADMISSION
    assert "larger than the whole 1MB VRAM budget" in str(exc.value)
    assert "displacing" not in str(exc.value)


def test_a_genuine_displacement_case_is_the_only_one_that_blames_a_resident_model() -> None:
    """The claim "would only fit by displacing" is now made ONLY when the snapshot shows something
    resident to displace: budget 5000, 4000 in use, the model needs 4983."""
    planner = ResidencyPlanner(5000)
    planner.register_model("qwen3:8b", 4983)
    planner.register_model("other:8b", 4000)
    _resident(planner, "other:8b")                     # 1000MB free, 4000MB in use
    with pytest.raises(WorkerPaneRefused) as exc:
        _authorize(_local_option(), residency_planner=planner,
                   residency_budget=_established_budget(5000), ollama_present=True,
                   executable="ollama")
    assert exc.value.gate == GATE_VRAM_ADMISSION
    assert "would only fit by displacing another resident model" in str(exc.value)
    assert "free VRAM 1000MB of 5000MB, 4000MB in use" in str(exc.value)


def test_a_model_that_exactly_fills_the_budget_is_admitted_not_refused() -> None:
    """A fail-closed check that refuses the boundary case it was built to allow is just a bug."""
    planner = ResidencyPlanner(4000)
    planner.register_model("qwen3:8b", 4000)
    session = _authorize(_local_option(), residency_planner=planner,
                         residency_budget=_established_budget(4000), ollama_present=True,
                         executable="ollama")
    assert session.residency_decision["scheduled"] is True


def test_an_authorization_with_no_budget_provenance_is_refused_not_recorded_as_unknown() -> None:
    """A planner with no provenance used to be admitted and merely DISCLOSED as unknown. That is a
    fail-open: the total the planner enforces came from somewhere nobody vouched for, and the
    disclosure was a `null` a consumer had to notice (spec-audit MAJOR-1)."""
    planner = ResidencyPlanner(20000)
    planner.register_model("qwen3:8b", 5000)
    with pytest.raises(WorkerPaneRefused) as exc:
        _authorize(_local_option(), residency_planner=planner, ollama_present=True,
                   executable="ollama")
    assert exc.value.gate == GATE_VRAM_BUDGET
    assert "no VRAM budget provenance supplied with the planner" in str(exc.value)
