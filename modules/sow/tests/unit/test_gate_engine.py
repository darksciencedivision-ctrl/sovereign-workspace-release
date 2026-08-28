"""Phase 8: gate engine — declarative criteria, deterministic verdicts, no-advance-on-fail,
no conductor override."""
from __future__ import annotations

import hashlib

import pytest

from control_plane.gates import (
    GateConfigError,
    GateContext,
    GateEngine,
    UnknownCriterion,
    define_gate,
    evaluate_criterion,
)
from control_plane.tasks.graph import IllegalTaskTransition, TaskGraph, TaskState


def _good_ctx() -> GateContext:
    content = b"# result\nreal content, no markers\n"
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    return GateContext(
        artifact_content=content,
        structured_output={
            "summary": "done",
            "claims": [{"text": "c", "evidence_refs": ["m-e@1"]}],
            "artifact": {"artifact_id": digest, "media_type": "text/markdown", "size_bytes": len(content),
                         "created_by_node": "w", "task_id": "t-1", "ts": "2026-07-17T00:00:00+00:00",
                         "schema": "artifact@1.0"}},
        evidence_refs=["m-e@1"])


STAGE_CRITERIA = ["artifact_present", "structured_output_valid", "artifact_content_addressed",
                  "claims_cite_evidence", "no_placeholders", "no_unresolved_critical"]


def test_clean_artifact_passes() -> None:
    rec = GateEngine().evaluate(define_gate("stage", STAGE_CRITERIA), _good_ctx(), task_id="t-1")
    assert rec["verdict"] == "PASS" and rec["decided_by"] == "gate_engine"
    assert rec["schema"] == "gate@1.0"


@pytest.mark.parametrize("mutate,expect_reason", [
    (lambda c: setattr(c, "artifact_content", b""), "no artifact"),
    (lambda c: c.structured_output.__setitem__("claims", [{"text": "x", "evidence_refs": []}]), "without evidence"),
    (lambda c: setattr(c, "unresolved_critical", 2), "unresolved critical"),
    (lambda c: setattr(c, "artifact_content", b"has a TODO marker"), "placeholder"),
])
def test_seeded_defects_fail(mutate, expect_reason) -> None:
    ctx = _good_ctx()
    mutate(ctx)
    rec = GateEngine().evaluate(define_gate("stage", STAGE_CRITERIA), ctx, task_id="t-1")
    assert rec["verdict"] == "FAIL"
    assert any(expect_reason in r for r in rec["reasons"])


def test_advisory_dissent_is_reservation_not_fail() -> None:
    ctx = _good_ctx()
    ctx.debate_record = {"result": {"outcome": "DISSENT_PRESERVED"}}
    rec = GateEngine().evaluate(define_gate("stage", [*STAGE_CRITERIA, "debate_resolved"]), ctx,
                                debate_ref="d-abc123", task_id="t-1")
    assert rec["verdict"] == "PASS_WITH_RESERVATIONS" and rec["debate_ref"] == "d-abc123"


def test_converged_debate_passes_clean() -> None:
    ctx = _good_ctx()
    ctx.debate_record = {"result": {"outcome": "CONVERGED"}}
    rec = GateEngine().evaluate(define_gate("stage", [*STAGE_CRITERIA, "debate_resolved"]), ctx, debate_ref="d-x1")
    assert rec["verdict"] == "PASS"


def test_unknown_criterion_fails_closed() -> None:
    with pytest.raises(GateConfigError, match="unknown gate criteria"):
        define_gate("stage", ["artifact_present", "not_a_real_check"])


def test_empty_criteria_and_bad_kind_fail_closed() -> None:
    with pytest.raises(GateConfigError, match="no criteria"):
        define_gate("stage", [])
    with pytest.raises(GateConfigError, match="unknown gate kind"):
        define_gate("banana", ["artifact_present"])


def test_unknown_criterion_evaluation_raises() -> None:
    with pytest.raises(UnknownCriterion):
        evaluate_criterion("nope", _good_ctx())


# -- task-graph integration: failed artifacts cannot advance, no conductor override ----

def test_fail_verdict_blocks_task_and_dependents() -> None:
    g = TaskGraph()
    req = {"capability": "reasoning", "requirements": {}}
    g.add_task("t-1", req)
    g.add_task("t-2", req, deps=("t-1",))
    g.assign("t-1", "w", rationale="r"); g.transition("t-1", TaskState.IN_PROGRESS)
    g.transition("t-1", TaskState.AWAITING_GATE)
    ctx = _good_ctx(); ctx.artifact_content = b""  # defect
    rec = GateEngine().evaluate(define_gate("stage", STAGE_CRITERIA), ctx, task_id="t-1")
    GateEngine().apply_to_task(g, "t-1", rec)
    assert g.get("t-1").state is TaskState.BLOCKED
    assert g.get("t-2").state is TaskState.BLOCKED  # dependent cannot advance


def test_conductor_cannot_override_a_gated_fail() -> None:
    g = TaskGraph()
    g.add_task("t-1", {"capability": "reasoning", "requirements": {}})
    g.assign("t-1", "w", rationale="r"); g.transition("t-1", TaskState.IN_PROGRESS)
    g.transition("t-1", TaskState.AWAITING_GATE)
    ctx = _good_ctx(); ctx.unresolved_critical = 1
    rec = GateEngine().evaluate(define_gate("stage", STAGE_CRITERIA), ctx, task_id="t-1")
    GateEngine().apply_to_task(g, "t-1", rec)
    assert g.get("t-1").state is TaskState.BLOCKED
    # no state-machine edge lets anyone (incl. the conductor) push a gated-fail task to DONE
    with pytest.raises(IllegalTaskTransition):
        g.transition("t-1", TaskState.DONE, by="conductor")


def test_pass_verdict_advances_task_to_done() -> None:
    g = TaskGraph()
    g.add_task("t-1", {"capability": "reasoning", "requirements": {}})
    g.assign("t-1", "w", rationale="r"); g.transition("t-1", TaskState.IN_PROGRESS)
    g.transition("t-1", TaskState.AWAITING_GATE)
    rec = GateEngine().evaluate(define_gate("stage", STAGE_CRITERIA), _good_ctx(), task_id="t-1")
    GateEngine().apply_to_task(g, "t-1", rec)
    assert g.get("t-1").state is TaskState.DONE


def test_plan_gate_checks_plan_wellformed() -> None:
    ctx = GateContext(plan_tasks=[{"task_id": "t-1", "deps": []}, {"task_id": "t-2", "deps": ["t-1"]}])
    assert GateEngine().evaluate(define_gate("plan", ["plan_acyclic"]), ctx)["verdict"] == "PASS"
    bad = GateContext(plan_tasks=[{"task_id": "t-2", "deps": ["t-missing"]}])
    assert GateEngine().evaluate(define_gate("plan", ["plan_acyclic"]), bad)["verdict"] == "FAIL"


def test_plan_gate_detects_real_cycle() -> None:
    """F3: a genuine dependency cycle t1<->t2 (both defined) must FAIL, not pass."""
    cyclic = GateContext(plan_tasks=[{"task_id": "t-1", "deps": ["t-2"]}, {"task_id": "t-2", "deps": ["t-1"]}])
    rec = GateEngine().evaluate(define_gate("plan", ["plan_acyclic"]), cyclic)
    assert rec["verdict"] == "FAIL" and any("cycle" in r for r in rec["reasons"])


def test_apply_to_task_fails_closed_on_malformed_or_forged_verdict() -> None:
    """F1: a record whose verdict is not an explicit PASS/PASS_WITH_RESERVATIONS must NOT
    advance the task — a forged/malformed record fails closed (invariant 16, §4)."""
    g = TaskGraph()
    g.add_task("t-1", {"capability": "reasoning", "requirements": {}})
    g.assign("t-1", "w", rationale="r"); g.transition("t-1", TaskState.IN_PROGRESS)
    g.transition("t-1", TaskState.AWAITING_GATE)
    # a well-formed schema record but with verdict=null (schema allows null) must not advance
    forged = GateEngine().evaluate(define_gate("stage", STAGE_CRITERIA), _good_ctx(), task_id="t-1")
    forged["verdict"] = None
    GateEngine().apply_to_task(g, "t-1", forged)
    assert g.get("t-1").state is TaskState.BLOCKED  # fail closed, not DONE


def test_apply_to_task_rejects_record_for_a_different_task() -> None:
    """F5: a gate record evaluated for task A cannot be applied to task B."""
    g = TaskGraph()
    g.add_task("t-1", {"capability": "reasoning", "requirements": {}})
    g.assign("t-1", "w", rationale="r"); g.transition("t-1", TaskState.IN_PROGRESS)
    g.transition("t-1", TaskState.AWAITING_GATE)
    rec_for_other = GateEngine().evaluate(define_gate("stage", STAGE_CRITERIA), _good_ctx(), task_id="t-OTHER")
    with pytest.raises(GateConfigError, match="task_id"):
        GateEngine().apply_to_task(g, "t-1", rec_for_other)


def test_artifact_size_mismatch_fails() -> None:
    ctx = _good_ctx()
    ctx.structured_output["artifact"]["size_bytes"] = 99999  # wrong size, hash still right
    rec = GateEngine().evaluate(define_gate("stage", STAGE_CRITERIA), ctx)
    assert rec["verdict"] == "FAIL" and any("size_bytes" in r for r in rec["reasons"])


def test_placeholder_word_boundary_no_false_positive() -> None:
    """F4: 'mastodon'/'photodocument' must not trip the 'todo' placeholder check."""
    ctx = _good_ctx()
    ctx.artifact_content = b"# result\nWe deployed to the mastodon photodocument server.\n"
    ctx.structured_output["artifact"]["artifact_id"] = "sha256:" + hashlib.sha256(ctx.artifact_content).hexdigest()
    ctx.structured_output["artifact"]["size_bytes"] = len(ctx.artifact_content)
    rec = GateEngine().evaluate(define_gate("stage", STAGE_CRITERIA), ctx)
    assert rec["verdict"] == "PASS"


@pytest.mark.parametrize("marker", [b"XXX left here", b"a WIP note", b"HACK: fix", b"a stub only"])
def test_placeholder_expanded_markers_fail(marker) -> None:
    ctx = _good_ctx()
    ctx.artifact_content = b"# result\n" + marker + b"\n"
    ctx.structured_output["artifact"]["artifact_id"] = "sha256:" + hashlib.sha256(ctx.artifact_content).hexdigest()
    ctx.structured_output["artifact"]["size_bytes"] = len(ctx.artifact_content)
    rec = GateEngine().evaluate(define_gate("stage", STAGE_CRITERIA), ctx)
    assert rec["verdict"] == "FAIL"


# --- W-67: the CRITICAL resolution criterion failed OPEN with no resolver ---------------------

def test_evidence_refs_resolve_fails_closed_with_no_resolver() -> None:
    """U13/W-67: with no resolver configured there is NO verification, so the criterion must
    refuse - silently skipping was a CRITICAL criterion that never verified anything."""
    res = evaluate_criterion("evidence_refs_resolve", GateContext(evidence_refs=["m-e@1"]))
    assert res.passed is False, "a missing resolver must not read as a pass"
    assert "resolver" in res.reason


def test_a_gate_listing_the_criterion_without_a_resolver_now_fails() -> None:
    ctx = _good_ctx()
    rec = GateEngine().evaluate(
        define_gate("stage", [*STAGE_CRITERIA, "evidence_refs_resolve"]), ctx, task_id="t-1")
    assert rec["verdict"] == "FAIL"
    assert any("resolver" in r for r in rec["reasons"])


def test_configured_resolver_behaviour_is_unchanged() -> None:
    ok = evaluate_criterion("evidence_refs_resolve", GateContext(
        evidence_refs=["m-e@1"], evidence_resolver=lambda ref: ref == "m-e@1"))
    bad = evaluate_criterion("evidence_refs_resolve", GateContext(
        evidence_refs=["m-e@1", "m-gone"], evidence_resolver=lambda ref: ref == "m-e@1"))
    assert ok.passed is True and ok.reason == "all evidence resolves"
    assert bad.passed is False and "unresolved evidence" in bad.reason


# --- W-68: model-authored prose reached no_placeholders via the acceptance packet -------------

def test_prose_in_structured_output_cannot_trip_no_placeholders_artifacts_still_can() -> None:
    """Both directions: the node's wording lives in claim/summary records, so scanning the
    structured packet judged PROSE by an artifact rule; the published bytes stay scanned."""
    prose_ctx = GateContext(
        artifact_content=b"# result\nsettled real content\n",
        structured_output={"summary": "todo: write the summary",
                           "claims": [{"text": "fixme later", "evidence_refs": ["m-e@1"]}]})
    assert evaluate_criterion("no_placeholders", prose_ctx).passed is True, (
        "model-authored prose tripped a CRITICAL criterion")
    artifact_ctx = GateContext(
        artifact_content=b"# result\nhas a TODO marker\n",
        structured_output={"summary": "settled", "claims": [{"text": "c", "evidence_refs": ["m-e@1"]}]})
    res = evaluate_criterion("no_placeholders", artifact_ctx)
    assert res.passed is False and "placeholder markers" in res.reason