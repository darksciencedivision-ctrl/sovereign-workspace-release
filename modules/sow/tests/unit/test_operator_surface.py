"""Phase 15E `.objective` — the operator command surface (OP-7 §12.5 item 5).

Unit coverage of the pure/deterministic governance: the unified approval queue (plan / protected
action / clarification with a badge count), invariant-1 operator authority, invariant-16 no-override
of a failed gate, the plan proposal fold, and broker mirroring. The end-to-end objective→approve→
acceptance-packet path is proven over a REAL MCP server in tests/integration/test_objective_intake.py.
"""
from __future__ import annotations

import pytest

from control_plane.orchestration.operator_surface import (
    APPROVAL_DRAWER_SCHEMA,
    ApprovalError,
    ApprovalKind,
    ApprovalQueue,
    apply_protected_decision,
    build_plan_proposal,
    mirror_broker_outcome,
    propose_plan_for_approval,
)
from control_plane.orchestration.live_flow import decompose_plan
from control_plane.policy import Identity
from voice_bridge.command_broker import CommandBroker, Disposition, ProposedCommand

OPERATOR = Identity(node_id="op", role="operator", project_id="proj")
WORKER = Identity(node_id="w", role="worker", project_id="proj")
CONDUCTOR = Identity(node_id="c", role="conductor", project_id="proj")

# A well-formed conductor decomposition (the shape MockReasoningBackend.propose_plan emits).
_GOOD_DECISION = {
    "parse_mode": "structured",
    "proposed_tasks": [
        {"desc": "survey the offline roster", "capability": "reasoning"},
        {"desc": "review the survey", "capability": "review", "deps": [1]},
    ],
}
_PLAN_GATE_PASS = {"schema": "gate@1.0", "kind": "plan", "verdict": "PASS", "decided_by": "gate_engine"}
_PLAN_GATE_FAIL = {"schema": "gate@1.0", "kind": "plan", "verdict": "FAIL", "decided_by": "gate_engine"}


# --- the queue: enqueue / ordering / badge -----------------------------------------

def test_enqueue_orders_by_insertion_and_badge_counts_pending() -> None:
    q = ApprovalQueue()
    a = q.enqueue(ApprovalKind.PLAN, summary="plan A", origin="conductor")
    b = q.enqueue(ApprovalKind.CLARIFICATION, summary="clarify B", origin="voice", approvable=False)
    assert [i.item_id for i in q.pending()] == [a, b]
    assert q.badge_count == 2
    model = q.drawer_model()
    assert model["schema"] == APPROVAL_DRAWER_SCHEMA
    assert model["badge_count"] == 2
    assert model["kind_counts"] == {"plan": 1, "protected_action": 0, "clarification": 1}


def test_enqueue_fail_closed_on_bad_kind_summary_origin() -> None:
    q = ApprovalQueue()
    with pytest.raises(ApprovalError):
        q.enqueue("not_a_kind", summary="x", origin="conductor")
    with pytest.raises(ApprovalError):
        q.enqueue(ApprovalKind.PLAN, summary="   ", origin="conductor")
    with pytest.raises(ApprovalError):
        q.enqueue(ApprovalKind.PLAN, summary="ok", origin="")


def test_badge_count_is_derived_and_drops_resolved_items() -> None:
    q = ApprovalQueue()
    a = q.enqueue(ApprovalKind.PLAN, summary="plan", origin="conductor")
    q.enqueue(ApprovalKind.PROTECTED_ACTION, summary="terminate node", origin="typed", ref="q-1")
    assert q.badge_count == 2
    q.resolve(a, OPERATOR, decision="approve")
    assert q.badge_count == 1                 # resolved item leaves the badge
    assert a not in {i.item_id for i in q.pending()}
    assert len(q.all_items()) == 2            # but stays in history (append-only spirit)


# --- invariant 1: only the operator may resolve ------------------------------------

@pytest.mark.parametrize("identity", [WORKER, CONDUCTOR])
def test_only_operator_may_resolve(identity: Identity) -> None:
    q = ApprovalQueue()
    item = q.enqueue(ApprovalKind.PLAN, summary="plan", origin="conductor")
    with pytest.raises(ApprovalError, match="invariant 1"):
        q.resolve(item, identity, decision="approve")
    assert q.badge_count == 1                 # nothing was decided


def test_resolve_fail_closed_unknown_item_bad_decision_and_double_resolve() -> None:
    q = ApprovalQueue()
    item = q.enqueue(ApprovalKind.PLAN, summary="plan", origin="conductor")
    with pytest.raises(ApprovalError):
        q.resolve("ap-999", OPERATOR, decision="approve")
    with pytest.raises(ApprovalError):
        q.resolve(item, OPERATOR, decision="maybe")
    q.resolve(item, OPERATOR, decision="reject", reason="not now")
    with pytest.raises(ApprovalError, match="already"):
        q.resolve(item, OPERATOR, decision="approve")


# --- invariant 16: a failed-gate plan is not operator-approvable --------------------

def test_non_approvable_item_can_be_rejected_but_never_approved() -> None:
    q = ApprovalQueue()
    item = q.enqueue(ApprovalKind.PLAN, summary="blocked plan", origin="conductor", approvable=False)
    with pytest.raises(ApprovalError, match="invariant 16"):
        q.resolve(item, OPERATOR, decision="approve")
    resolved = q.resolve(item, OPERATOR, decision="reject", reason="gate failed")
    assert resolved.resolved and resolved.decision == "reject"


# --- plan proposal fold -------------------------------------------------------------

def test_plan_proposal_is_approvable_only_when_gate_passed() -> None:
    decomp = decompose_plan(_GOOD_DECISION)
    passing = build_plan_proposal(objective="o", decomposition=decomp, plan_gate=_PLAN_GATE_PASS,
                                  plan_blocked=False)
    assert passing.approvable is True
    assert passing.plan_gate_verdict == "PASS"
    assert [t["task_id"] for t in passing.tasks] == ["t-1", "t-2"]
    assert "review" in {t["capability"] for t in passing.tasks}

    failed = build_plan_proposal(objective="o", decomposition=decomp, plan_gate=_PLAN_GATE_FAIL,
                                 plan_blocked=True)
    assert failed.approvable is False
    assert "BLOCKED" in failed.summary()


def test_propose_plan_for_approval_enqueues_a_plan_item_without_assigning() -> None:
    q = ApprovalQueue()
    decomp = decompose_plan(_GOOD_DECISION)
    item_id, proposal = propose_plan_for_approval(
        q, objective="Design the roster", decomposition=decomp, plan_gate=_PLAN_GATE_PASS,
        plan_blocked=False)
    row = q.get(item_id)
    assert row.kind is ApprovalKind.PLAN and row.approvable is True and not row.resolved
    assert row.detail["task_count"] == 2 and proposal.objective == "Design the roster"
    assert q.badge_count == 1


# --- broker mirroring: protected actions + clarifications reach the same drawer ------

def test_protected_command_is_mirrored_and_routes_back_to_the_broker() -> None:
    broker = CommandBroker()
    q = ApprovalQueue()
    outcome = broker.submit(ProposedCommand(source="typed", verb="terminate", target="node-7"))
    assert outcome.disposition is Disposition.APPROVAL_QUEUED
    item_id = mirror_broker_outcome(q, outcome, ProposedCommand("typed", "terminate", "node-7"))
    item = q.get(item_id)
    assert item.kind is ApprovalKind.PROTECTED_ACTION and item.ref == outcome.pending_id
    assert item.detail["category"] == "destructive"

    # a non-operator cannot resolve the drawer item (invariant 1) ...
    with pytest.raises(ApprovalError):
        q.resolve(item_id, WORKER, decision="approve")
    # ... the operator approves -> the decision routes to the REAL broker -> a control event fires
    resolved = q.resolve(item_id, OPERATOR, decision="approve")
    event = apply_protected_decision(broker, resolved, OPERATOR, decision="approve")
    assert event is not None and event.verb == "terminate" and event.target == "node-7"
    assert outcome.pending_id not in broker.pending()   # dequeued from the broker


def test_clarification_is_mirrored_not_approvable() -> None:
    broker = CommandBroker()
    q = ApprovalQueue()
    cmd = ProposedCommand(source="voice", verb="frobnicate", target="thing", raw_text="frobnicate the thing")
    outcome = broker.submit(cmd)
    assert outcome.disposition is Disposition.CLARIFY
    item_id = mirror_broker_outcome(q, outcome, cmd)
    item = q.get(item_id)
    assert item.kind is ApprovalKind.CLARIFICATION and item.approvable is False
    with pytest.raises(ApprovalError):
        q.resolve(item_id, OPERATOR, decision="approve")   # a question is not "approved"


def test_safe_command_produces_no_drawer_item() -> None:
    broker = CommandBroker()
    q = ApprovalQueue()
    cmd = ProposedCommand(source="typed", verb="focus", target="pane-2")
    outcome = broker.submit(cmd)
    assert outcome.disposition is Disposition.EXECUTED
    assert mirror_broker_outcome(q, outcome, cmd) is None
    assert q.badge_count == 0


def test_apply_protected_decision_rejects_non_protected_item() -> None:
    q = ApprovalQueue()
    plan = q.get(q.enqueue(ApprovalKind.PLAN, summary="plan", origin="conductor"))
    with pytest.raises(ApprovalError):
        apply_protected_decision(CommandBroker(), plan, OPERATOR, decision="approve")


def test_apply_protected_decision_requires_a_resolved_item() -> None:
    """Defense-in-depth: an UNRESOLVED protected-action item is not routed to the broker."""
    broker = CommandBroker()
    q = ApprovalQueue()
    outcome = broker.submit(ProposedCommand(source="typed", verb="spawn", target="node-9"))
    item = q.get(mirror_broker_outcome(q, outcome, ProposedCommand("typed", "spawn", "node-9")))
    assert not item.resolved
    with pytest.raises(ApprovalError, match="resolved"):
        apply_protected_decision(broker, item, OPERATOR, decision="approve")


def test_apply_protected_decision_derives_the_action_from_the_recorded_decision() -> None:
    """Decision integrity (inv 12/13): the action routed to the broker derives from the item's OWN
    recorded operator decision. A caller-supplied decision that CONTRADICTS the record is refused
    (no override), so the executed action can never diverge from what the drawer recorded."""
    broker = CommandBroker()
    q = ApprovalQueue()
    outcome = broker.submit(ProposedCommand(source="typed", verb="terminate", target="node-3"))
    item_id = mirror_broker_outcome(q, outcome, ProposedCommand("typed", "terminate", "node-3"))
    rejected = q.resolve(item_id, OPERATOR, decision="reject", reason="no")
    # the operator REJECTED it in the drawer; a caller cannot smuggle an approve past the record
    with pytest.raises(ApprovalError, match="recorded"):
        apply_protected_decision(broker, rejected, OPERATOR, decision="approve")
    assert outcome.pending_id in broker.pending()          # nothing executed/dequeued
    # deriving from the record (no decision arg) rejects it cleanly
    assert apply_protected_decision(broker, rejected, OPERATOR) is None
    assert outcome.pending_id not in broker.pending()


# ---- W-78b: the confidence gate keys on voice-derived PROVENANCE, not on one literal ----

def test_a_voice_derived_source_under_any_spelling_cannot_bypass_the_confidence_gate():
    """W-78b. `source="voice_recorded"` used to sail past the CLARIFY threshold because the gate
    compared the source to the single literal "voice" - it protected a spelling, not a
    provenance."""
    from voice_bridge.command_broker import CommandBroker, Disposition, ProposedCommand

    outcome = CommandBroker().submit(ProposedCommand(
        source="voice_recorded", verb="focus", target="pane 3", confidence=0.0))
    assert outcome.disposition is Disposition.CLARIFY


def test_an_unknown_source_fails_closed_into_clarify_too():
    """W-78b: an unseen source id must not execute ungated either - fail closed."""
    from voice_bridge.command_broker import CommandBroker, Disposition, ProposedCommand

    outcome = CommandBroker().submit(ProposedCommand(
        source="something-new", verb="focus", target="pane 3"))
    assert outcome.disposition is Disposition.CLARIFY


def test_the_typed_path_is_still_not_confidence_gated():
    """Control: the one KNOWN non-voice surface keeps its no-confidence execution."""
    from voice_bridge.command_broker import CommandBroker, Disposition, ProposedCommand

    outcome = CommandBroker().submit(ProposedCommand(source="typed", verb="focus", target="pane 3"))
    assert outcome.disposition is Disposition.EXECUTED


def test_voice_with_low_confidence_still_clarifies():
    """Control: the original literal path is unchanged."""
    from voice_bridge.command_broker import CommandBroker, Disposition, ProposedCommand

    outcome = CommandBroker().submit(ProposedCommand(
        source="voice", verb="focus", target="pane 3", confidence=0.0))
    assert outcome.disposition is Disposition.CLARIFY
