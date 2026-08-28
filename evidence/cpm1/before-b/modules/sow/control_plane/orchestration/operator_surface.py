"""Operator command surface — the objective intake + the unified approval queue (Phase 15E `.objective`).

Directive OP-7 §12.5 item 5 (a plan §10.3 requirement, a 15E exit criterion): *"an objective input
(operator types an objective → conductor decomposes → plan surfaces for approval) and the
approval-queue drawer (plan gates, protected actions, clarifications, badge count). Without this the
conductor cannot receive work or ask the operator anything."* OP-8 §13 reframed the objective input:
the operator drives a live conductor pane rather than a batch form — but the governed **pause for
operator authority** it describes (a proposed plan surfaces, protected actions queue, clarifications
surface, all with a badge count) is exactly this surface. This module is that governed pause, not a
new authority: it COMPOSES the pieces already built and re-implements no authority, gate, classifier
or lifecycle (the one re-derivation is a display-only protected/destructive LABEL, read from the
broker's own frozensets — never a re-classification).

  * The **decomposition** and the **plan gate** are `LiveGovernedFlow.begin` (Phase 15D `.flow`):
    the conductor proposes tasks, the REAL gate engine renders a `gate@1.0` plan verdict. This module
    reads that verdict; it never re-decides it.
  * The **protected/destructive/clarify** classification is the `CommandBroker` (Phase 12 voice): a
    proposed command is queued for the operator, never auto-run. This module MIRRORS a broker outcome
    into the one drawer and routes the operator's decision back to the broker — it does not
    re-classify a verb.
  * The **authority** is invariant 1: only the operator may resolve a queued item. That is enforced
    here in code (an `Identity` whose role is not "operator" is refused), not by convention.

Two load-bearing governance properties this surface adds, both fail-closed:

  1. **The plan pauses for the operator BEFORE assignment (invariant 1).** `ObjectiveIntake.submit`
     decomposes and gates the plan, then STOPS: no worker is assigned until the operator approves the
     queued plan item. The conductor proposes; the operator disposes.
  2. **A gate-failed plan is NOT operator-approvable (invariant 16).** A plan whose `gate@1.0` verdict
     did not pass is enqueued `approvable=False`; `resolve(decision="approve")` on it is refused. The
     operator holds final authority, but final authority is not an override of a failed gate — there
     is no override path (invariant 16). The operator may only dismiss (reject) such a plan.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from control_plane.policy import Identity
from voice_bridge.command_broker import (
    DESTRUCTIVE_VERBS,
    PROTECTED_VERBS,
    BrokerOutcome,
    CommandBroker,
    ControlEvent,
    Disposition,
    ProposedCommand,
)

_PASSING_VERDICTS = ("PASS", "PASS_WITH_RESERVATIONS")


class ApprovalKind(str, Enum):
    """The three things the operator's drawer surfaces (OP-7 §12.5 item 5)."""

    PLAN = "plan"
    PROTECTED_ACTION = "protected_action"
    CLARIFICATION = "clarification"


DECISION_APPROVE = "approve"
DECISION_REJECT = "reject"
_DECISIONS = (DECISION_APPROVE, DECISION_REJECT)

APPROVAL_DRAWER_SCHEMA = "approval_drawer@1.0"


class ApprovalError(ValueError):
    """A fail-closed refusal on the approval surface (bad kind, non-operator, unknown/decided item,
    or an approve of something not approvable). A programming/authority fault, not model output."""


class ObjectiveIntakeError(RuntimeError):
    """The objective intake was driven out of order (approve before submit, or a second objective)."""


@dataclass(frozen=True)
class ApprovalItem:
    """One row in the operator's approval drawer. The object is immutable and `resolve` produces a
    NEW frozen item (a decided item is never mutated in place), and re-resolve is refused — so the
    recorded decision cannot be altered. NOTE: the authoritative append-only history (invariant 12) is
    the MCP log, which this ephemeral in-process queue does not itself write; this is decision
    integrity for the surface, not the canonical record."""

    item_id: str
    seq: int
    kind: ApprovalKind
    summary: str
    origin: str                       # "conductor" | "voice" | "typed"
    approvable: bool
    detail: dict[str, Any] = field(default_factory=dict)
    #: an external id this item routes its decision back to (a `CommandBroker` pending_id). The
    #: queue never invents one — a protected action carries the broker's, a plan carries None.
    ref: str | None = None
    resolved: bool = False
    decision: str | None = None
    resolve_reason: str = ""

    def as_row(self) -> dict[str, Any]:
        """The JSON row the drawer renders and a future read-only IPC feed returns (deterministic)."""
        return {
            "item_id": self.item_id, "seq": self.seq, "kind": self.kind.value,
            "summary": self.summary, "origin": self.origin, "approvable": self.approvable,
            "ref": self.ref, "resolved": self.resolved, "decision": self.decision,
            "resolve_reason": self.resolve_reason, "detail": dict(self.detail),
        }


class ApprovalQueue:
    """The unified operator-facing approval queue — plan gates, protected actions and clarifications
    in ONE drawer with a badge count. Pure/deterministic: no clock, no I/O, monotonic ids. It stores
    and gates operator decisions; it performs no side effect (a resolved protected action is routed to
    the broker by `apply_protected_decision`, a resolved plan by `ObjectiveIntake`)."""

    def __init__(self) -> None:
        self._items: dict[str, ApprovalItem] = {}
        self._seq = 0

    def enqueue(self, kind: ApprovalKind | str, *, summary: str, origin: str,
                detail: Mapping[str, Any] | None = None, approvable: bool = True,
                ref: str | None = None) -> str:
        """Add a pending item, FAIL CLOSED on a malformed one. Returns the queue-local item id."""
        try:
            k = ApprovalKind(kind)
        except ValueError as exc:
            raise ApprovalError(f"unknown approval kind {kind!r} (fail closed)") from exc
        if not isinstance(summary, str) or not summary.strip():
            raise ApprovalError("an approval item needs a real summary")
        if not isinstance(origin, str) or not origin.strip():
            raise ApprovalError("an approval item must name its origin")
        self._seq += 1
        item_id = f"ap-{self._seq}"
        self._items[item_id] = ApprovalItem(
            item_id=item_id, seq=self._seq, kind=k, summary=summary.strip(), origin=origin.strip(),
            approvable=bool(approvable), detail=dict(detail or {}),
            ref=ref if (isinstance(ref, str) and ref.strip()) else None)
        return item_id

    def get(self, item_id: str) -> ApprovalItem:
        item = self._items.get(item_id)
        if item is None:
            raise ApprovalError(f"no approval item {item_id!r}")
        return item

    def pending(self) -> list[ApprovalItem]:
        """Unresolved items in deterministic (insertion) order."""
        return [i for i in sorted(self._items.values(), key=lambda x: x.seq) if not i.resolved]

    def all_items(self) -> list[ApprovalItem]:
        return sorted(self._items.values(), key=lambda x: x.seq)

    @property
    def badge_count(self) -> int:
        """The number the drawer badge shows — pending items only. Never negative, never inflated."""
        return len(self.pending())

    def resolve(self, item_id: str, operator: Identity, *, decision: str, reason: str = "") -> ApprovalItem:
        """The OPERATOR decides a queued item. Invariant 1 is enforced in code: a non-operator
        identity is refused. Invariant 16 is enforced too: `approve` of a non-approvable item (a
        gate-failed plan) is refused — final authority is not an override of a failed gate."""
        if not isinstance(operator, Identity) or operator.role != "operator":
            role = getattr(operator, "role", None)
            raise ApprovalError(
                f"only the operator may resolve an approval item (got role {role!r}) — invariant 1")
        if decision not in _DECISIONS:
            raise ApprovalError(f"decision must be one of {_DECISIONS}, got {decision!r}")
        item = self.get(item_id)
        if item.resolved:
            raise ApprovalError(f"approval item {item_id!r} is already {item.decision!r} — not re-decidable")
        if decision == DECISION_APPROVE and not item.approvable:
            raise ApprovalError(
                f"approval item {item_id!r} is not approvable (a failed-gate plan cannot be approved "
                f"into execution — invariant 16, no override path); it may only be rejected")
        resolved = ApprovalItem(
            item_id=item.item_id, seq=item.seq, kind=item.kind, summary=item.summary,
            origin=item.origin, approvable=item.approvable, detail=item.detail, ref=item.ref,
            resolved=True, decision=decision, resolve_reason=str(reason or ""))
        self._items[item_id] = resolved
        return resolved

    def drawer_model(self) -> dict[str, Any]:
        """The operator-facing drawer snapshot — the render model and a future read-only IPC payload.
        `badge_count` is DERIVED from the pending set here so no caller can inflate it."""
        pending = self.pending()
        counts = {k.value: 0 for k in ApprovalKind}
        for item in pending:
            counts[item.kind.value] += 1
        return {
            "schema": APPROVAL_DRAWER_SCHEMA,
            "badge_count": len(pending),
            "kind_counts": counts,
            "pending": [i.as_row() for i in pending],
        }


# --------------------------------------------------------------------------------------
# plan proposal — the conductor's decomposition surfaced for operator approval
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanProposal:
    """The conductor's decomposition + the REAL plan-gate verdict, packaged for the operator to
    approve or reject. It carries the gate outcome; it never re-decides it."""

    objective: str
    tasks: tuple[dict[str, Any], ...]
    refused: tuple[dict[str, Any], ...]
    plan_gate_verdict: str
    plan_gate_record: dict[str, Any]
    approvable: bool

    def summary(self) -> str:
        n = len(self.tasks)
        state = "ready for approval" if self.approvable else f"BLOCKED by plan gate ({self.plan_gate_verdict})"
        return f"Plan for “{self.objective}”: {n} task(s), {state}"

    def as_detail(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "task_count": len(self.tasks),
            "tasks": [dict(t) for t in self.tasks],
            "refused": [dict(r) for r in self.refused],
            "plan_gate_verdict": self.plan_gate_verdict,
            "approvable": self.approvable,
        }


def build_plan_proposal(*, objective: str, decomposition: Any, plan_gate: Mapping[str, Any],
                        plan_blocked: bool) -> PlanProposal:
    """Fold a `Decomposition` + the flow's `gate@1.0` plan verdict into an operator-facing proposal.

    `approvable` is DERIVED from the gate, never asserted: a plan is approvable only when the flow did
    not block it AND the recorded verdict passed. A gate-failed plan is still surfaced (observability,
    Buildout §4) but cannot be approved into execution (invariant 16)."""
    verdict = str(plan_gate.get("verdict")) if isinstance(plan_gate, Mapping) else "UNKNOWN"
    approvable = (not plan_blocked) and verdict in _PASSING_VERDICTS
    tasks = tuple({"task_id": t.task_id, "capability": t.capability, "description": t.description,
                   "deps": list(t.deps)} for t in getattr(decomposition, "tasks", ()))
    refused = tuple(dict(r) for r in getattr(decomposition, "refused", ()))
    return PlanProposal(objective=objective, tasks=tasks, refused=refused,
                        plan_gate_verdict=verdict, plan_gate_record=dict(plan_gate), approvable=approvable)


def propose_plan_for_approval(queue: ApprovalQueue, *, objective: str, decomposition: Any,
                              plan_gate: Mapping[str, Any], plan_blocked: bool,
                              origin: str = "conductor",
                              extra_detail: Mapping[str, Any] | None = None) -> tuple[str, PlanProposal]:
    """Surface a decomposed plan in the approval drawer and return `(item_id, proposal)`.

    The plan pauses here for operator authority (invariant 1): enqueuing does NOT assign any work.

    `extra_detail` (Phase 17D `.events`) is provenance the caller attaches to the row — which recorded
    session event produced it, over which channel (invariant 11). It is merged UNDER the derived
    detail, so provenance can never overwrite the plan's own gate-derived facts."""
    proposal = build_plan_proposal(objective=objective, decomposition=decomposition,
                                   plan_gate=plan_gate, plan_blocked=plan_blocked)
    detail = {**dict(extra_detail or {}), **proposal.as_detail()}
    item_id = queue.enqueue(ApprovalKind.PLAN, summary=proposal.summary(), origin=origin,
                            detail=detail, approvable=proposal.approvable, ref=None)
    return item_id, proposal


# --------------------------------------------------------------------------------------
# broker mirroring — protected actions and clarifications reach the SAME drawer
# --------------------------------------------------------------------------------------

def _protected_category(verb: str) -> str:
    # match the broker's own canonicalization (it lowercases verbs) so a caller passing an
    # un-canonicalized verb still labels the category correctly rather than falling to "unknown"
    v = verb.strip().lower() if isinstance(verb, str) else ""
    if v in PROTECTED_VERBS:
        return "protected"
    if v in DESTRUCTIVE_VERBS:
        return "destructive"
    return "unknown"


def mirror_broker_outcome(queue: ApprovalQueue, outcome: BrokerOutcome,
                          command: ProposedCommand,
                          extra_detail: Mapping[str, Any] | None = None) -> str | None:
    """Reflect a `CommandBroker` outcome into the unified drawer so protected actions and
    clarifications surface beside plan approvals (OP-7 §12.5 item 5). Returns the queue item id, or
    None for an EXECUTED safe command (nothing for the operator to decide).

    The broker already classified and (for protected/destructive) queued the command; this does not
    re-classify — it carries the broker's `pending_id` in `ref` so the operator's decision routes back
    to the same broker (`apply_protected_decision`).

    `extra_detail` (Phase 17D `.events`) is provenance the caller attaches to the row — which recorded
    session event produced it, over which channel (invariant 11). It is merged UNDER the broker-derived
    detail, so a caller can never overwrite what the broker said about the command."""
    base = dict(extra_detail or {})
    if outcome.disposition is Disposition.APPROVAL_QUEUED:
        category = _protected_category(command.verb)
        return queue.enqueue(
            ApprovalKind.PROTECTED_ACTION,
            summary=f"{category} command: {command.verb} {command.target}".strip(),
            origin=command.source or "typed",
            detail={**base,
                    "verb": command.verb, "target": command.target, "args": dict(command.args),
                    "category": category, "reason": outcome.reason},
            approvable=True, ref=outcome.pending_id)
    if outcome.disposition is Disposition.CLARIFY:
        # A clarification is a QUESTION to the operator, not something to approve into execution:
        # enqueued approvable=False, so it can only be dismissed here. Answering it re-enters through
        # the broker as a fresh command (that loop is the `.voice` sub-step's concern).
        text = command.raw_text.strip() or f"{command.verb} {command.target}".strip()
        return queue.enqueue(
            ApprovalKind.CLARIFICATION, summary=f"clarify: {text}", origin=command.source or "typed",
            detail={**base,
                    "verb": command.verb, "target": command.target, "raw_text": command.raw_text,
                    "reason": outcome.reason},
            approvable=False, ref=None)
    return None


def apply_protected_decision(broker: CommandBroker, item: ApprovalItem, operator: Identity, *,
                             decision: str | None = None, reason: str = "") -> ControlEvent | None:
    """Route a RESOLVED protected-action drawer item back to the real broker — approve executes the
    queued command as a logged control event, reject declines it. Returns the control event on
    approve, None on reject.

    The routed action is DERIVED from the item's own recorded operator decision (`item.decision`) —
    immutable once resolved (invariants 12/13, decision integrity) — so the command handed to the
    broker can never diverge from what the operator actually decided in the drawer. A `decision` argument, if
    supplied, must MATCH the recorded decision; a contradicting one is refused fail-closed (it cannot
    override the record — there is no override path here either). The broker independently re-checks
    operator authority (invariant 1 in two places by design), so this also cannot route a non-operator
    decision through."""
    if item.kind is not ApprovalKind.PROTECTED_ACTION or not item.ref:
        raise ApprovalError("apply_protected_decision needs a protected-action item carrying a broker ref")
    # defense-in-depth (fail-closed parity with the rest of the surface): only a RESOLVED item is
    # routed to the broker. The broker independently re-checks operator authority (invariant 1), so
    # this cannot bypass authority — it prevents routing a still-pending item by mistake.
    if not item.resolved:
        raise ApprovalError("apply_protected_decision requires a resolved item (operator has decided)")
    recorded = item.decision
    if recorded not in _DECISIONS:
        raise ApprovalError(f"resolved item {item.item_id!r} carries no usable decision ({recorded!r})")
    # The recorded operator decision is authoritative. A supplied decision may only CONFIRM it; a
    # contradicting one is refused so the action can never diverge from the append-only record.
    if decision is not None and decision != recorded:
        raise ApprovalError(
            f"supplied decision {decision!r} contradicts the operator's recorded decision {recorded!r} "
            f"for item {item.item_id!r} — the recorded decision is authoritative (no override)")
    if recorded == DECISION_APPROVE:
        return broker.approve(item.ref, operator)
    broker.reject(item.ref, operator, reason=reason)
    return None


# --------------------------------------------------------------------------------------
# objective intake — the operator gives the conductor work; the plan pauses for approval
# --------------------------------------------------------------------------------------

class ObjectiveIntake:
    """One objective driven through the governed pause: submit → the conductor decomposes and the
    plan gate runs → the plan SURFACES in the drawer → the operator approves (assignment proceeds) or
    rejects (the objective is declined, nothing is assigned).

    Composes a `LiveGovernedFlow` (Phase 15D) unchanged. One flow runs one objective, so one intake
    handles one objective; a second `submit` is refused fail-closed rather than silently reusing a
    consumed flow."""

    def __init__(self, flow: Any, queue: ApprovalQueue, *, origin: str = "conductor") -> None:
        self._flow = flow
        self._queue = queue
        self._origin = origin
        self._plan_item_id: str | None = None
        self._objective: str | None = None
        self._proposal: PlanProposal | None = None
        self._assigned = False

    def submit(self, objective: str) -> dict[str, Any]:
        """The operator gives the conductor an objective. The conductor decomposes and the plan gate
        runs (via `flow.begin`); the plan then SURFACES for approval. NO work is assigned here
        (invariant 1). Returns the queued plan item + the proposal the operator will decide."""
        if not isinstance(objective, str) or not objective.strip():
            raise ObjectiveIntakeError("an objective must be real text")
        if self._plan_item_id is not None:
            raise ObjectiveIntakeError("this intake already carries an objective (one objective per intake)")
        run_state = self._flow.begin(objective)
        plan_gate = run_state.trace["plan_gate"]
        item_id, proposal = propose_plan_for_approval(
            self._queue, objective=objective, decomposition=run_state.decomposition,
            plan_gate=plan_gate, plan_blocked=run_state.plan_blocked, origin=self._origin)
        self._plan_item_id = item_id
        self._objective = objective
        self._proposal = proposal
        return {"item_id": item_id, "proposal": proposal.as_detail(),
                "plan_blocked": run_state.plan_blocked, "approvable": proposal.approvable,
                "badge_count": self._queue.badge_count}

    def approve(self, operator: Identity, *, gate_reject_tasks: frozenset[str] = frozenset()) -> dict[str, Any]:
        """The operator APPROVES the plan. Only now does the flow assign, gate and synthesize. The
        queue resolve enforces operator authority (invariant 1) AND refuses a gate-failed plan
        (invariant 16) before a single worker is touched."""
        item = self._queue.resolve(self._require_item(), operator, decision=DECISION_APPROVE)
        self._assigned = True
        self._flow.run_waves(gate_reject_tasks=gate_reject_tasks)
        trace = self._flow.finish()
        return {"item": item.as_row(), "trace": trace,
                "acceptance_packet": trace.get("acceptance_packet"), "packet": trace.get("packet")}

    def reject(self, operator: Identity, *, reason: str = "") -> dict[str, Any]:
        """The operator DECLINES the objective. The flow is abandoned — no worker is assigned. The
        conductor proposed; the operator disposed (invariant 1)."""
        item = self._queue.resolve(self._require_item(), operator, decision=DECISION_REJECT, reason=reason)
        return {"item": item.as_row(), "declined": True, "assigned": self._assigned}

    @property
    def plan_item_id(self) -> str | None:
        return self._plan_item_id

    def _require_item(self) -> str:
        if self._plan_item_id is None:
            raise ObjectiveIntakeError("no objective submitted yet — call submit() first")
        return self._plan_item_id
