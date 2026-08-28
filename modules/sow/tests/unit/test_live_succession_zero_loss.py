"""Phase 15D `.succession` — the pure honesty/comparison layer.

Directive §11 15D: "kill the Fable-5 conductor mid-run, resume on a different backend, zero loss,
then restore selection." These tests pin the parts that decide whether that claim may be MADE:

  - a zero-loss verdict that cannot be reached vacuously (an empty pre-kill set proves nothing);
  - a `different backend` claim that must be structurally provable, not asserted;
  - leg vocabulary reused from `live_flow`/`live_debate`, with `live` unbacked by a verification
    record being UNREPRESENTABLE rather than merely discouraged;
  - I-X3 handoff ordering (release BEFORE acquire) recorded from observation, never assumed.

No MCP server, no adapters, no clock — every input is injected.
"""
from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError

from control_plane.orchestration.live_flow import ATTEMPTED_LEG
from control_plane.orchestration.live_succession import (
    SUCCESSION_REPORT_KEYS,
    SUCCESSION_REPORT_SCHEMA,
    ConductorParty,
    SuccessionError,
    ZeroLossReport,
    build_succession_report,
    compare_zero_loss,
    earns_zero_loss_claim,
    merge_spend_leg,
)

TS = "2026-07-20T00:00:00+00:00"

_BEFORE = {"accepted": {"e-1": "sha256:aaa", "e-2": "sha256:bbb"},
           "task_states": {"t-1": "DONE", "t-2": "PENDING"}}
_AFTER = {"accepted": {"e-1": "sha256:aaa", "e-2": "sha256:bbb", "e-3": "sha256:ccc"},
          "task_states": {"t-1": "DONE", "t-2": "DONE"}}


def _party(role: str, *, model: str, leg: str = "mock", verification=None,
           calls_spent: int = 1) -> ConductorParty:
    return ConductorParty(
        role=role, node_id=f"conductor-{role}", adapter=f"adapter_{model}", model_name=model,
        leg=leg, selection_record={"selection": {"model": model}}, verification=verification,
        calls_spent=calls_spent)


def _report(**over):
    kwargs = dict(
        objective="Design the offline conductor roster",
        predecessor=_party("predecessor", model="mock-fable5"),
        successor=_party("successor", model="mock-successor"),
        restored_selection={"model": "fable-5", "reason": "operator_selected", "since": TS},
        staleness={"ok": True, "checks": {"integrity_ok": True}},
        zero_loss=compare_zero_loss(_BEFORE, _AFTER),
        handoff_order=("release", "acquire"),
        packet_entry="m-packet",
        ts=TS,
    )
    kwargs.update(over)
    return build_succession_report(**kwargs)


# --- zero loss: the verdict that must not be reachable vacuously ---------------------

def test_zero_loss_confirmed_when_everything_survives_and_work_continued() -> None:
    z = compare_zero_loss(_BEFORE, _AFTER)
    assert z.ok is True
    assert z.checks["accepted_preserved"] is True
    assert z.checks["no_content_drift"] is True
    assert z.checks["tasks_preserved"] is True
    assert z.checks["done_tasks_preserved"] is True
    assert z.checks["pre_kill_accepted_count"] == 2
    assert z.reasons() == []


def test_an_empty_pre_kill_set_can_never_be_zero_loss_proof() -> None:
    """The load-bearing anti-vacuity rule. `all()` over an empty accepted set is True, so a
    succession performed before ANY artifact existed would otherwise report a clean zero-loss
    verdict while having put nothing at risk."""
    z = compare_zero_loss({"accepted": {}, "task_states": {"t-1": "PENDING"}},
                          {"accepted": {}, "task_states": {"t-1": "PENDING"}})
    assert z.ok is False
    assert z.checks["pre_kill_accepted_count"] == 0
    assert "nothing_at_risk" in z.reasons()


def test_a_dropped_accepted_entry_is_loss() -> None:
    after = {"accepted": {"e-1": "sha256:aaa"}, "task_states": _AFTER["task_states"]}
    z = compare_zero_loss(_BEFORE, after)
    assert z.ok is False
    assert z.checks["accepted_preserved"] is False
    assert z.checks["missing_entries"] == ["e-2"]


def test_a_rewritten_artifact_is_loss_even_though_the_id_survives() -> None:
    """Same entry_id, different bytes: an id-only comparison would call this preserved."""
    after = {"accepted": {"e-1": "sha256:aaa", "e-2": "sha256:TAMPERED"},
             "task_states": _AFTER["task_states"]}
    z = compare_zero_loss(_BEFORE, after)
    assert z.ok is False
    assert z.checks["no_content_drift"] is False
    assert z.checks["drifted_entries"] == ["e-2"]


def test_a_task_that_regressed_out_of_DONE_is_loss() -> None:
    after = {"accepted": _AFTER["accepted"], "task_states": {"t-1": "BLOCKED", "t-2": "DONE"}}
    z = compare_zero_loss(_BEFORE, after)
    assert z.ok is False
    assert z.checks["done_tasks_preserved"] is False


def test_a_task_that_vanished_from_the_graph_is_loss() -> None:
    after = {"accepted": _AFTER["accepted"], "task_states": {"t-1": "DONE"}}
    z = compare_zero_loss(_BEFORE, after)
    assert z.ok is False
    assert z.checks["tasks_preserved"] is False
    assert z.checks["missing_tasks"] == ["t-2"]


def test_preserving_only_the_bootstrap_files_does_not_count_as_advancing_work() -> None:
    """The anti-vacuity guard (`pre_kill_accepted_count > 0`) is far weaker in practice than it
    reads: bootstrap publishes the 12 conductor files as ACCEPTED, so a real run's pre-kill set is
    never empty and the emptiness rule can only fire against a project this runner cannot build.
    `work_advanced` is what actually distinguishes "the successor finished work the predecessor
    never saw" from "nothing was lost because nothing happened" (U49).
    """
    frozen = {f"conductor-{i}": f"sha256:{i}" for i in range(12)}
    z = compare_zero_loss({"accepted": frozen, "task_states": {}},
                          {"accepted": dict(frozen), "task_states": {}})
    # nothing was LOST — that much is true and `ok` says so honestly
    assert z.ok is True
    # but nothing was ACCOMPLISHED either, and the durable claim requires this to be True
    assert z.checks["work_advanced"] is False


def test_work_advanced_is_true_only_when_the_accepted_set_grew() -> None:
    assert compare_zero_loss(_BEFORE, _AFTER).checks["work_advanced"] is True
    assert compare_zero_loss(_BEFORE, _BEFORE).checks["work_advanced"] is False


def test_the_durable_claim_needs_BOTH_zero_loss_and_advancement() -> None:
    """`ok` alone does not earn the claim — preserving the 12 bootstrap conductor files is not a
    demonstrated succession (U49). Pinned here because inlining this rule left it unenforced."""
    assert earns_zero_loss_claim(_report()) is True                      # ok + advanced

    frozen = {"e-1": "sha256:aaa"}
    stalled = _report(zero_loss=compare_zero_loss({"accepted": frozen, "task_states": {}},
                                                  {"accepted": dict(frozen), "task_states": {}}))
    assert stalled["zero_loss"]["ok"] is True                            # nothing was lost...
    assert earns_zero_loss_claim(stalled) is False                       # ...but nothing advanced

    lossy = _report(zero_loss=compare_zero_loss(_BEFORE, {"accepted": {}, "task_states": {}}))
    assert earns_zero_loss_claim(lossy) is False


# --- the report: claims that must be backed --------------------------------------------

def test_report_carries_both_conductors_and_the_restored_selection() -> None:
    r = _report()
    assert r["schema"] == SUCCESSION_REPORT_SCHEMA
    assert set(r) == set(SUCCESSION_REPORT_KEYS)
    assert r["predecessor"]["model_name"] == "mock-fable5"
    assert r["successor"]["model_name"] == "mock-successor"
    assert r["zero_loss"]["ok"] is True
    assert r["restored_selection"]["reason"] == "operator_selected"
    assert r["handoff_order"] == ["release", "acquire"]
    assert r["acceptance_packet"] == "m-packet"


def test_report_refuses_a_successor_that_is_not_a_different_backend() -> None:
    """"resume on a DIFFERENT backend" is the criterion. A succession onto the same backend
    identity proves interchangeability of nothing, so it cannot be reported as one."""
    with pytest.raises(SuccessionError, match="different backend"):
        _report(successor=_party("successor", model="mock-fable5"))


def test_report_refuses_a_live_leg_with_no_verification_record() -> None:
    with pytest.raises(SuccessionError, match="verification"):
        _report(predecessor=_party("predecessor", model="mock-fable5", leg="live"))


def test_report_accepts_a_live_leg_that_carries_its_verification_record() -> None:
    r = _report(predecessor=_party("predecessor", model="mock-fable5", leg="live",
                                   verification={"model": "claude-fable-5-20260101", "verified": True}))
    assert r["predecessor"]["leg"] == "live"
    assert r["run_spend_leg"] == "live"


def test_report_refuses_an_unknown_leg() -> None:
    with pytest.raises(SuccessionError, match="not one of"):
        _report(successor=_party("successor", model="mock-successor", leg="probably-live"))


def test_report_refuses_a_handoff_order_that_acquires_before_releasing() -> None:
    """I-X3: the predecessor's terminal is released BEFORE the successor acquires it. A recorded
    order that says otherwise is a governance defect, not a field to store."""
    with pytest.raises(SuccessionError, match="release"):
        _report(handoff_order=("acquire", "release"))


def test_report_records_an_unobserved_handoff_as_absent_not_as_correct() -> None:
    r = _report(handoff_order=())
    assert r["handoff_order"] == []
    assert "not observed" in r["handoff_note"]


def test_report_refuses_a_restored_selection_that_is_not_the_operator_reason() -> None:
    """Restoring the operator's selection must land on `operator_selected`; anything else means the
    restore did not happen and must not be recorded as though it had."""
    with pytest.raises(SuccessionError, match="operator_selected"):
        _report(restored_selection={"model": "fable-5", "reason": "succession", "since": TS})


def test_report_refuses_a_blank_objective_or_timestamp() -> None:
    with pytest.raises(SuccessionError):
        _report(objective="   ")
    with pytest.raises(SuccessionError):
        _report(ts="")


def test_report_deep_copies_its_inputs_so_later_mutation_cannot_rewrite_the_artifact() -> None:
    selection = {"model": "fable-5", "reason": "operator_selected", "since": TS}
    r = _report(restored_selection=selection)
    selection["model"] = "something-else"
    assert r["restored_selection"]["model"] == "fable-5"


# --- spend merging: under-reporting is the dishonest direction --------------------------

@pytest.mark.parametrize("legs,expected", [
    (("mock", "mock"), "mock"),
    (("skipped", "mock"), "mock"),
    (("live", "mock"), "live"),
    (("mock", "live"), "live"),
    ((ATTEMPTED_LEG, "mock"), ATTEMPTED_LEG),
    (("live", ATTEMPTED_LEG), "live"),
    (("skipped", "skipped"), "skipped"),
])
def test_merge_spend_leg_takes_the_strongest_spend_claim(legs, expected) -> None:
    """The merged value answers "did this RUN reach a real provider", across both conductors.
    Merging downward would let a succession erase the predecessor's spend."""
    assert merge_spend_leg(*legs) == expected


def test_merge_spend_leg_refuses_an_unknown_leg() -> None:
    with pytest.raises(SuccessionError):
        merge_spend_leg("mock", "sort-of-live")


def test_merge_spend_leg_of_nothing_is_skipped() -> None:
    assert merge_spend_leg() == "skipped"


def test_zero_loss_report_is_immutable_from_the_outside() -> None:
    z = compare_zero_loss(_BEFORE, _AFTER)
    with pytest.raises(FrozenInstanceError):
        z.ok = False  # type: ignore[misc]
    assert isinstance(z, ZeroLossReport)
