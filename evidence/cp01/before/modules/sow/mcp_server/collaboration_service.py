"""Task-scoped operational collaboration over Sovereign's existing durable store.

Same contract as `memory_service.py`, and for the same reason: **every ROLE OR SCOPE decision
is asked of `control_plane.policy` (I-M2 delegation, invariant 7 — MCP is access, not
authority).** This module makes no role or scope decision of its own: it validates shapes,
enforces lifecycle legality, persists, and raises whatever reason the policy hands back. The
rules about *who* live one package over, where the operator can change them once for this package.
(Not once for the product: `apps/desktop/main.js` holds a fourth, DIVERGENT copy for the Electron
control surface — stricter in one place, ungated in another — U345, which no Phase-19 unit owns.)

Until Phase 19 unit 2 that was not true here. The policy was accepted in the constructor and
never read, while fifteen role/scope decisions were made inline (cold audit finding B1 named
twelve of them; U326) — a second copy of the authority, free to diverge from the one memory
operations obey.

Phase 19 unit 5 changed HOW those writes reach the store, not who may make them (U330). Every
writer that reads a record and writes a successor now computes that successor inside the store's
`BEGIN IMMEDIATE` boundary, from the row read there, through `mutate_operational_task` /
`mutate_operational_debate`; the two creators use `create_operational_*`, which refuse to
overwrite. Five of the seven used to build a successor from a Python-side snapshot and blind-write
it back, so two live workers posting to one debate lost a turn with no error and no conflict
record. The rules that depend on record CONTENT — the bounded-round ceiling, the close quorum —
moved inside the fence with the write they guard, and each asks the policy again on the row it
actually acts on.

One consequence, stated because the mutation harness measured it rather than assumed it: the
`state != "OPEN"` checks that remain BEFORE each debate transaction are early guards, not the
guarantee. Deleting one changes no observable refusal — the in-fence check raises the same
sentence — so they are graded by nothing on their own. They are kept for message ORDER (a caller
sending a malformed decision to a closed debate still hears "debate is not open" first, as it
always did) and because refusing before opening a write transaction is cheaper. The load-bearing
copy is the one inside the mutator, and the racing tests in
`tests/unit/test_operational_write_path.py` §2 are what hold it there.

What is deliberately still here, because it is legality rather than authority — the same split
`memory_service.py` has always had with `mcp_server/lifecycle.py`: the bounded-debate round
limit and the `budget_units` RANGE CHECK — range check only: the stored budget is NOT enforced
on this path (no CostGovernor here; invariant 17 unimplemented, U349; the donor that does
enforce it is `debate_service/cost_governor/governor.py`, and wiring it is an operator-ruled
unit, not a prose claim) — the "a debate may not close without a turn from every participant"
quorum, the "synthesis requires candidates from every worker" completeness rule, the
`debate is not open` state gate, the referential checks that a candidate names only messages
and debates that exist, and the CANDIDATE-status check. They are recorded as U344 so the
boundary is argued in the open rather than assumed; none of them asks who the caller is. The
CANDIDATE-status check is the closest call and U344 says so: it is the SHAPE half of a rule
whose *who* half lives at `control_plane/policy.py:authorize_publish` ("workers may publish
only CANDIDATE entries"), so it can drift from its twin even though it never reads a caller.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from control_plane.policy import Identity, SovereignPolicy, Verdict
from persistence import SovereignStore


TASK_STATES = (
    "CREATED", "ASSIGNED", "ACCEPTED", "IN_PROGRESS", "WAITING_FOR_PEER", "BLOCKED",
    "CANDIDATE_READY", "UNDER_REVIEW", "COMPLETED", "FAILED", "CANCELLED",
)

#: A status is a member of TASK_STATES; a TRANSITION is a different question, and until W-05 nothing
#: asked it. `update_task` validated membership only, and `record_candidate`/`record_synthesis` set
#: the status directly inside their own applies — so a worker drove a shared task
#: COMPLETED → CANCELLED → IN_PROGRESS and then rewrote its candidate, leaving the stored synthesis
#: binding a content hash that no longer existed.
#:
#: DONOR, and the divergence is deliberate: `control_plane/tasks/graph.py` defines `_LEGAL` over
#: `TaskState` with a terminal `DONE: frozenset()` and an `IllegalTaskTransition`. That is the GATE
#: lifecycle — a different vocabulary for a different thing — so what is reused here is the PATTERN
#: (a frozen table, a terminal state with no outbound edges, a named exception), NOT the table.
#: Contorting the operational lifecycle through the gate lifecycle's states to satisfy a rule about
#: reuse would have been the wrong kind of obedience.
#:
#: The edges are DERIVED from the lifecycle this build actually drives: `create_task` opens at
#: ASSIGNED; `publish_progress` offers ACCEPTED/IN_PROGRESS/WAITING_FOR_PEER/BLOCKED/
#: CANDIDATE_READY/UNDER_REVIEW/COMPLETED/FAILED/CANCELLED; `record_candidate` moves to
#: IN_PROGRESS or CANDIDATE_READY; `record_synthesis` moves to COMPLETED.
_TERMINAL_TASK_STATES = frozenset({"COMPLETED", "FAILED", "CANCELLED"})

_LEGAL_TASK_TRANSITIONS: dict[str, frozenset[str]] = {
    "CREATED": frozenset({"ASSIGNED", "BLOCKED", "CANCELLED", "FAILED"}),
    "ASSIGNED": frozenset({"ACCEPTED", "IN_PROGRESS", "WAITING_FOR_PEER", "BLOCKED",
                           "CANDIDATE_READY", "CANCELLED", "FAILED"}),
    "ACCEPTED": frozenset({"IN_PROGRESS", "WAITING_FOR_PEER", "BLOCKED", "CANDIDATE_READY",
                           "CANCELLED", "FAILED"}),
    "IN_PROGRESS": frozenset({"WAITING_FOR_PEER", "BLOCKED", "CANDIDATE_READY", "UNDER_REVIEW",
                              "CANCELLED", "FAILED"}),
    "WAITING_FOR_PEER": frozenset({"IN_PROGRESS", "BLOCKED", "CANDIDATE_READY",
                                   "CANCELLED", "FAILED"}),
    "BLOCKED": frozenset({"IN_PROGRESS", "ASSIGNED", "WAITING_FOR_PEER", "CANCELLED", "FAILED"}),
    "CANDIDATE_READY": frozenset({"UNDER_REVIEW", "IN_PROGRESS", "COMPLETED",
                                  "CANCELLED", "FAILED"}),
    "UNDER_REVIEW": frozenset({"COMPLETED", "CANDIDATE_READY", "IN_PROGRESS",
                               "CANCELLED", "FAILED"}),
    # terminal: no outbound edges at all. This is the row the reproduction escaped through.
    "COMPLETED": frozenset(),
    "FAILED": frozenset(),
    "CANCELLED": frozenset(),
}
MESSAGE_KINDS = (
    "assignment", "question", "answer", "progress", "blocker", "challenge", "debate_turn",
    "decision", "artifact_notice", "completion",
)
#: A debate is OPEN until it reaches one of two terminal states: CLOSED (a decision was reached
#: with a turn from every participant) or ABORTED (U416 — it can no longer reach one, because a
#: participant cannot answer). The distinction is load-bearing downstream: only CLOSED counts as
#: a considered deliberation in the synthesis gate ON THE `sovereign_tools` TOOL PATH
#: (`SovereignToolRuntime._considered_debates`), and since W-59 (U410) `record_synthesis` below
#: ALSO refuses inside its write fence while a debate on the task is OPEN — the transition itself
#: is guarded, not merely the tool boundary, and a caller reaching the service by another route
#: gets the same refusal. ABORTED blocks neither layer: it cannot conclude, must not hold the task
#: forever (U416), and the tool path reports it separately. (History, preserved: this comment once
#: recorded that `record_synthesis` performed no debate check of its own, and was the FOURTH site
#: of that unqualified sentence — the 19.6 repair enumerated three and missed this one, 250 lines
#: above them in this file (spec-auditor MEDIUM-5). W-59 removed the defect the sentence
#: described.) Deliberately NOT exported as a constant: an
#: exported tuple nothing consults is drift waiting to happen (round-1 gate-validator MINOR-1 —
#: unlike MESSAGE_KINDS/TASK_STATES, which are validated against on every write, it would have
#: been decorative). The states are pinned by the tests that exercise each transition.


class CollaborationError(ValueError):
    pass


class IllegalTaskTransition(CollaborationError):
    """A status change the operational lifecycle does not permit. A subclass of CollaborationError
    so every existing caller that fails closed on one still does, while the specific class stays
    nameable — the donor's `IllegalTaskTransition`, in this module's own error family."""


def _assert_legal_transition(current_status: str, next_status: str) -> None:
    """Checked INSIDE the write fence, against the row the transaction actually read. Checked
    anywhere else it is a race: the status a caller validated may be one commit old by the time the
    transaction opens (the same argument U330 records for the successor row)."""
    if current_status == next_status:
        return          # restating a status is not a transition; progress updates do it constantly
    allowed = _LEGAL_TASK_TRANSITIONS.get(current_status)
    if allowed is None:
        raise IllegalTaskTransition(
            f"task is in unknown status {current_status!r}; refusing to move it to "
            f"{next_status!r} — fail closed")
    if next_status not in allowed:
        terminal = " (terminal: it has no outbound transition)" if not allowed else ""
        raise IllegalTaskTransition(
            f"illegal task transition {current_status!r} -> {next_status!r}{terminal}")



def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(8)}"


def _strings(value: Any, field: str, *, nonempty: bool = True) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise CollaborationError(f"{field} must be a list of non-empty strings")
    out = list(dict.fromkeys(v.strip() for v in value))
    if nonempty and not out:
        raise CollaborationError(f"{field} must not be empty")
    return out


class CollaborationService:
    def __init__(self, store: SovereignStore, policy: SovereignPolicy) -> None:
        self._store = store
        self._policy = policy

    @staticmethod
    def _require(verdict: Verdict) -> None:
        """The only place this module turns an authority verdict into a refusal. It never
        computes one."""
        if not verdict.allow:
            raise CollaborationError(verdict.reason)

    def create_task(self, identity: Identity, *, objective: str, owner_node_ids: list[str],
                    scope: dict[str, Any] | None = None, constraints: list[str] | None = None,
                    expected_output: str | None = None, acceptance_criteria: list[str] | None = None,
                    peer_nodes: list[str] | None = None, task_id: str | None = None,
                    thread_id: str | None = None) -> dict[str, Any]:
        self._require(self._policy.authorize_task_create(identity))
        if not isinstance(objective, str) or not objective.strip():
            raise CollaborationError("objective must be non-empty")
        owners = _strings(owner_node_ids, "owner_node_ids")
        now = _now()
        tid = (task_id or _new("t")).strip()
        thread = (thread_id or _new("thread")).strip()
        task = {
            "task_id": tid, "thread_id": thread, "project_id": identity.project_id,
            "objective": objective.strip(), "scope": scope or {},
            "constraints": list(constraints or []), "expected_output": expected_output or "candidate result",
            "acceptance_criteria": list(acceptance_criteria or []),
            "peer_nodes": list(peer_nodes or owners), "owner_node_ids": owners,
            "status": "ASSIGNED", "created_by_node_id": identity.node_id,
            "created_at": now, "updated_at": now,
        }
        self._store.create_operational_task(task)
        self.send_message(
            identity, task_id=tid, thread_id=thread, recipient_node_ids=owners,
            message_kind="assignment", body=objective.strip(), evidence_refs=[], artifact_refs=[],
        )
        return task

    def update_task(self, identity: Identity, *, task_id: str, status: str,
                    progress: dict[str, Any] | None = None) -> dict[str, Any]:
        if status not in TASK_STATES:
            raise CollaborationError(f"unknown task status {status!r}")
        if progress is not None and not isinstance(progress, dict):
            raise CollaborationError("progress must be an object")
        task = self._require_task(identity, task_id)
        self._require(self._policy.authorize_task_update(identity, task))

        def apply(current: dict[str, Any]) -> dict[str, Any]:
            # The successor is built from `current` — the row read inside the fence — not from
            # the snapshot above (U330). `{**task, "status": ...}` was how a status update erased
            # a candidate a worker had just published through `mutate_operational_task`.
            # The authority is asked AGAIN on that row: the record a verdict was computed against
            # may be one commit old by the time the transaction opens, and this module's rule is
            # that it asks rather than assumes (invariant 7).
            self._require(self._policy.authorize_task_update(identity, current))
            # W-05: legality, not membership — and on `current`, the row read inside the fence.
            _assert_legal_transition(current.get("status", ""), status)
            updated = {**current, "status": status, "updated_at": _now()}
            if progress is not None:
                updated["latest_progress"] = {**progress, "node_id": identity.node_id, "at": _now()}
            return updated

        return self._store.mutate_operational_task(identity.project_id, task_id, apply)

    def get_task(self, identity: Identity, task_id: str) -> dict[str, Any]:
        return self._require_task(identity, task_id)

    def list_tasks(self, identity: Identity) -> list[dict[str, Any]]:
        tasks = self._store.list_operational_tasks(identity.project_id)
        return [t for t in tasks if self._policy.authorize_task_read(identity, t).allow]

    def send_message(self, identity: Identity, *, task_id: str, thread_id: str | None,
                     recipient_node_ids: list[str], message_kind: str, body: str,
                     evidence_refs: list[str] | None = None, artifact_refs: list[str] | None = None,
                     reply_to: str | None = None) -> dict[str, Any]:
        if message_kind not in MESSAGE_KINDS:
            raise CollaborationError(f"unknown message kind {message_kind!r}")
        if not isinstance(body, str) or not body.strip():
            raise CollaborationError("message body must be non-empty")
        recipients = _strings(recipient_node_ids, "recipient_node_ids")
        task = self._require_task(identity, task_id)
        self._require(self._policy.authorize_send_message(identity, task, recipients))
        msg = {
            "message_id": _new("msg"), "thread_id": thread_id or task["thread_id"],
            "task_id": task_id, "project_id": identity.project_id,
            "sender_node_id": identity.node_id, "recipient_node_ids": recipients,
            "message_kind": message_kind, "body": body.strip(),
            "evidence_refs": list(evidence_refs or []), "artifact_refs": list(artifact_refs or []),
            "reply_to": reply_to, "created_at": _now(), "delivery_state": "persisted",
        }
        self._store.append_operational_message(msg)
        return msg

    def read_messages(self, identity: Identity, *, task_id: str,
                      include_all: bool = False) -> list[dict[str, Any]]:
        self._require_task(identity, task_id)
        messages = self._store.list_operational_messages(identity.project_id, task_id)
        if include_all and self._policy.authorize_read_task_transcript(identity).allow:
            return messages
        return [m for m in messages if self._policy.authorize_message_read(identity, m).allow]

    def open_debate(self, identity: Identity, *, task_id: str, proposition: str,
                    participant_node_ids: list[str], evidence_refs: list[str] | None = None,
                    artifact_refs: list[str] | None = None, max_rounds: int = 3,
                    budget_units: int = 1000) -> dict[str, Any]:
        # caller authority first, before this node learns anything about the task — the order the
        # inline check had. `authorize_open_debate` asks it again together with the task scope;
        # the policy is pure, so asking twice costs nothing and keeps the ordering visible here.
        self._require(self._policy.authorize_debate(
            identity, {"caller_node": identity.node_id,
                       "participants": list(participant_node_ids or ())}))
        task = self._require_task(identity, task_id)
        participants = _strings(participant_node_ids, "participant_node_ids")
        self._require(self._policy.authorize_open_debate(identity, task, participants))
        if not isinstance(max_rounds, int) or not 1 <= max_rounds <= 5:
            raise CollaborationError("max_rounds must be in 1..5")
        if not isinstance(budget_units, int) or budget_units < 1:
            raise CollaborationError("budget_units must be positive")
        # W-61 / U349, said exactly: the check above is the ONLY thing on this path that reads
        # `budget_units`. It is written into the debate record below and never consulted again —
        # NO CostGovernor, no per-caller quota, no global cap: invariant 17 is NOT implemented
        # here (the donor that implements it, `debate_service/cost_governor/governor.py`, guards
        # the Phase-7 Debate Service path only). A stored budget that nothing enforces must not
        # read as governance, so the absence is written AT THE WRITE instead of implied. Wiring
        # the governor into this path — or revoking the gate role's debate authority instead —
        # is the operator-ruled unit U349 assigns; until then `max_rounds` is the only bound a
        # debate here actually feels.
        if not isinstance(proposition, str):  # .strip() below would raise AttributeError instead
            raise CollaborationError("proposition must be non-empty")
        debate = {
            "debate_id": _new("d"), "task_id": task_id, "thread_id": task["thread_id"],
            "project_id": identity.project_id, "opened_by_node_id": identity.node_id,
            "participant_node_ids": participants, "proposition": proposition.strip(),
            "evidence_refs": list(evidence_refs or []), "artifact_refs": list(artifact_refs or []),
            "max_rounds": max_rounds, "budget_units": budget_units, "turns": [],
            "state": "OPEN", "created_at": _now(), "updated_at": _now(),
            "agreements": [], "dissent": [], "decision": None,
        }
        if not debate["proposition"]:
            raise CollaborationError("proposition must be non-empty")
        self._store.create_operational_debate(debate)
        return debate

    def post_debate_turn(self, identity: Identity, *, debate_id: str, body: str,
                         evidence_refs: list[str] | None = None,
                         reply_to: str | None = None) -> dict[str, Any]:
        debate = self._require_debate(identity, debate_id)
        if debate["state"] != "OPEN":
            raise CollaborationError("debate is not open")
        self._require(self._policy.authorize_debate_turn(identity, debate))
        if not isinstance(body, str) or not body.strip():
            raise CollaborationError("debate turn body must be non-empty")
        posted: dict[str, Any] = {}

        def apply(current: dict[str, Any]) -> dict[str, Any]:
            # Everything that depends on the debate's CONTENT is decided here, against the row
            # read inside the transaction: the two-worker case is the ordinary one, and appending
            # to the snapshot's turn list silently dropped whichever turn committed first (U330).
            # The round ceiling (invariant 14) moves with it — counted on a snapshot, a node's
            # last turn could be admitted twice under contention.
            if current["state"] != "OPEN":
                raise CollaborationError("debate is not open")
            self._require(self._policy.authorize_debate_turn(identity, current))
            turns = list(current["turns"])
            round_no = 1 + sum(1 for t in turns if t["node_id"] == identity.node_id)
            if round_no > current["max_rounds"]:
                raise CollaborationError("bounded debate round limit reached")
            posted["turn"] = {
                "turn_id": _new("turn"), "node_id": identity.node_id, "round": round_no,
                "body": body.strip(), "evidence_refs": list(evidence_refs or []),
                "reply_to": reply_to, "created_at": _now(),
            }
            return {**current, "turns": [*turns, posted["turn"]], "updated_at": _now()}

        self._store.mutate_operational_debate(identity.project_id, debate_id, apply)
        turn = posted["turn"]
        self.send_message(
            identity, task_id=debate["task_id"], thread_id=debate["thread_id"],
            recipient_node_ids=[n for n in debate["participant_node_ids"] if n != identity.node_id],
            message_kind="debate_turn", body=body, evidence_refs=evidence_refs or [],
            artifact_refs=[], reply_to=reply_to,
        )
        return turn

    def close_debate(self, identity: Identity, *, debate_id: str, decision: str,
                     agreements: list[str] | None = None, dissent: list[str] | None = None,
                     disagreements: list[str] | None = None,
                     unresolved_points: list[str] | None = None,
                     closure_reason: str | None = None) -> dict[str, Any]:
        debate = self._require_debate(identity, debate_id)
        self._require(self._policy.authorize_debate_close(identity, debate))
        if debate["state"] != "OPEN":
            raise CollaborationError("debate is not open")
        if not isinstance(decision, str) or not decision.strip():
            raise CollaborationError("decision must be non-empty")
        disagreements = list(disagreements if disagreements is not None else (dissent or []))

        def apply(current: dict[str, Any]) -> dict[str, Any]:
            # A closing debate is the worst case for a stale snapshot: `claims` and
            # `turn_evidence_refs` ARE the record of what was argued, and they feed the acceptance
            # packet. Both the quorum rule and the transcript are therefore taken from the row
            # inside the fence — a turn that landed a millisecond ago is part of this debate.
            if current["state"] != "OPEN":
                raise CollaborationError("debate is not open")
            self._require(self._policy.authorize_debate_close(identity, current))
            turns = current.get("turns", [])
            represented = {turn["node_id"] for turn in turns}
            missing = [n for n in current["participant_node_ids"] if n not in represented]
            if missing:
                raise CollaborationError("debate cannot close without a turn from every participant: "
                                         + ", ".join(missing))
            return {
                **current, "state": "CLOSED", "decision": decision.strip(),
                "claims": [turn["body"] for turn in turns],
                "turn_evidence_refs": list(dict.fromkeys(
                    ref for turn in turns for ref in turn.get("evidence_refs", []))),
                "agreements": list(agreements or []), "dissent": disagreements,
                "disagreements": disagreements, "unresolved_points": list(unresolved_points or []),
                "closure_reason": (closure_reason or decision).strip(),
                "closed_by_node_id": identity.node_id, "closed_at": _now(), "updated_at": _now(),
            }

        return self._store.mutate_operational_debate(identity.project_id, debate_id, apply)

    def abort_debate(self, identity: Identity, *, debate_id: str, reason: str) -> dict[str, Any]:
        """End a debate that can no longer reach a decision (U416).

        Closure requires a turn from every participant, so a participant whose pane dies leaves
        the debate OPEN permanently — its peers accumulating stall timers, and any caller that
        gates on open debates blocked behind a node that will never answer. ABORTED is that
        debate's terminal state. It is not a quiet deletion: the turns that were posted stay,
        `decision` stays None because none was reached, and the reason is recorded and surfaced.

        SCOPE, said exactly ([[U425]](b), unit 19.6; updated by W-59): the "synthesis gate" both
        sentences above referred to is `SovereignToolRuntime._considered_debates` in
        `mcp_server/sovereign_tools.py` — the TOOL path a conductor CLI reaches. It is that gate
        which refuses to publish while a debate on the task is open and which reports aborted
        debates separately. Since W-59 ([[U410]]), `record_synthesis` in this class ALSO refuses,
        inside its own write fence, while a debate on the task is OPEN — so a caller that reaches
        the service by another route gets the same protection, and the transition itself (not only
        the tool boundary) is guarded. ABORTED still blocks neither layer: it cannot conclude and
        must not hold the task forever. Before W-59, `record_synthesis` performed no debate check
        of its own, and an unqualified sentence here described a defence this file did not provide;
        the round-2 scoping repair fixed two sites and missed this one, the only one of the three
        in live product code.
        """
        debate = self._require_debate(identity, debate_id)
        self._require(self._policy.authorize_debate_abort(identity, debate))
        if debate["state"] != "OPEN":
            raise CollaborationError("debate is not open")
        if not isinstance(reason, str) or not reason.strip():
            raise CollaborationError("abort reason must be non-empty")

        def apply(current: dict[str, Any]) -> dict[str, Any]:
            if current["state"] != "OPEN":
                raise CollaborationError("debate is not open")
            self._require(self._policy.authorize_debate_abort(identity, current))
            return {
                **current, "state": "ABORTED", "abort_reason": reason.strip(),
                "claims": [turn["body"] for turn in current.get("turns", [])],
                "aborted_by_node_id": identity.node_id, "aborted_at": _now(), "updated_at": _now(),
            }

        return self._store.mutate_operational_debate(identity.project_id, debate_id, apply)

    def record_candidate(self, identity: Identity, *, task_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
        task = self._require_task(identity, task_id)
        self._require(self._policy.authorize_publish_candidate(identity, task))
        required = ("provider", "model", "summary", "claims", "evidence_refs",
                    "peer_messages_considered", "debates_considered", "limitations",
                    "artifact_ref", "content_hash")
        missing = [key for key in required if candidate.get(key) in (None, "")]
        if missing:
            raise CollaborationError("candidate missing required fields: " + ", ".join(missing))
        if candidate.get("status") != "CANDIDATE":
            raise CollaborationError("candidate status must be CANDIDATE")
        messages = {m["message_id"] for m in self._store.list_operational_messages(
            identity.project_id, task_id)}
        unknown_messages = set(candidate["peer_messages_considered"]) - messages
        if unknown_messages:
            raise CollaborationError("candidate names unknown peer messages")
        known_debates = {d["debate_id"] for d in self._store.list_operational_debates(
            identity.project_id, task_id)}
        if set(candidate["debates_considered"]) - known_debates:
            raise CollaborationError("candidate names an unknown debate")

        def apply(current: dict[str, Any]) -> dict[str, Any]:
            # W-05, operator ruling D-5 — CANDIDATE FREEZE. Once a candidate revision has
            # participated in a COMMITTED synthesis, that revision is immutable and an overwrite is
            # REFUSED. Synthesis invalidation is deliberately NOT built: the accepted synthesis
            # stands, and iterating means publishing a NEW candidate revision on a NEW task, never
            # mutating bytes an accepted synthesis already cites.
            #
            # This is checked before the transition below because it is the more specific rule and
            # gives the more useful reason. W-16 is what makes it decidable: a synthesis now always
            # carries the contributions it was built from, so "did this node's candidate participate"
            # is a fact on the row rather than an inference.
            committed = current.get("synthesis") or {}
            cited = {row.get("node_id") for row in (committed.get("contributions") or [])
                     if isinstance(row, dict)}
            if identity.node_id in cited:
                raise CollaborationError(
                    f"candidate from {identity.node_id!r} is frozen: it is cited by the committed "
                    f"synthesis for this task, and a synthesis may not be left binding a content "
                    f"hash that no longer exists (D-5: candidate freeze)")
            candidates = dict(current.get("candidates") or {})
            candidates[identity.node_id] = candidate
            complete = set(current["owner_node_ids"]).issubset(candidates)
            next_status = "CANDIDATE_READY" if complete else "IN_PROGRESS"
            # …and this path sets the status ITSELF, so it is governed by the same table rather than
            # by `update_task` alone — which is how the reproduction regressed a COMPLETED task.
            _assert_legal_transition(current.get("status", ""), next_status)
            return {**current, "candidates": candidates,
                    "status": next_status, "updated_at": _now()}

        return self._store.mutate_operational_task(identity.project_id, task_id, apply)

    def record_synthesis(self, identity: Identity, *, task_id: str,
                         synthesis: dict[str, Any],
                         contribution_bindings: list[dict[str, Any]] | None = None
                         ) -> dict[str, Any]:
        # existence + read authority before the write — the one write path that skipped it.
        # SHADOWED FOR AUTHORITY (U343), and the round-3 gate-validator was right that the unit
        # owed this the same analysis it gave the update and sender rules: only the directing
        # roles pass `authorize_publish_synthesis`, and neither is in `_SCOPED_ROLES`, so
        # `authorize_task_read` can refuse here on project/existence and never on authority.
        # It is not decorative — deleting it changes an observable verdict, which
        # `test_synthesis_asks_task_read_before_it_publishes` and mutation row P26 pin.
        self._require_task(identity, task_id)
        self._require(self._policy.authorize_publish_synthesis(identity))

        def apply(current: dict[str, Any]) -> dict[str, Any]:
            candidates = current.get("candidates") or {}
            missing = [node for node in current["owner_node_ids"] if node not in candidates]
            if missing:
                raise CollaborationError("synthesis requires candidates from every worker: "
                                         + ", ".join(missing))
            # W-59 / U410: the OPEN-debate gate, enforced at the state transition, not only at the
            # tool boundary. `_considered_debates` (sovereign_tools.py) refuses this on the TOOL
            # path, but `record_synthesis` is the writer that moves the task to COMPLETED, and it
            # is reachable by other routes; checked anywhere but HERE — inside the write fence, on
            # the rows this transaction actually reads — it would be a race (the doctrine
            # `_assert_legal_transition` records). The read is on this transaction's own connection
            # (`list_operational_debates` takes no write lock), so it sees the debates as of this
            # transaction's serialization point. Semantics mirror the tool path exactly: OPEN
            # blocks; CLOSED passes; ABORTED does NOT — a deliberation that can no longer conclude
            # must not hold the task forever (U416), and the tool path reports it separately.
            #
            # ORDERING, said exactly: this runs AFTER the completeness check above. Both are state
            # gates inside the same fence, so the order decides only WHICH reason a doubly-refused
            # call hears, never whether it is refused. Completeness stays first because its verdict
            # is deterministic and pinned in the delegation matrix; debate ids are random
            # (`secrets.token_hex`), so a matrix cell that quoted this message could never be
            # pinned. The tool path checks debates first at the boundary; the service's ordering is
            # its own, and neither layer can complete a task over an OPEN debate.
            debates = self._store.list_operational_debates(identity.project_id, task_id)
            still_open = sorted(d["debate_id"] for d in debates if d.get("state") == "OPEN")
            if still_open:
                raise CollaborationError(
                    "synthesis requires every debate on this task to be concluded; still open: "
                    + ", ".join(still_open))
            # W-16: this is NOT gated on `contribution_bindings is not None` any more. The block
            # below IS the publication-time integrity invariant -- "a synthesis must prove which
            # candidates it used" -- and making it conditional on the argument being supplied
            # enforced it by CALLER CONVENTION rather than by the state-mutating service. The only
            # product caller (sovereign_tools.py:302) does supply it; anything else reaching this
            # service published a synthesis that named no candidates and bound no content hashes.
            #
            # The refusal belongs HERE, inside the write fence, on the row this call actually read
            # -- not in the caller, and not before the fence, where it would be a race.
            if contribution_bindings is None:
                raise CollaborationError(
                    "synthesis must state the candidate contributions it is built from; "
                    "publication-time integrity is enforced inside the write fence, not by the "
                    "caller that happens to pass them")
            stated = {row.get("node_id"): row for row in contribution_bindings
                      if isinstance(row, dict)}
            candidate_nodes = sorted(candidates)
            omitted = [node for node in candidate_nodes if node not in stated]
            invented = sorted(node for node in stated if node not in candidates)
            if omitted:
                raise CollaborationError(
                    "synthesis must report every candidate committed inside the write fence; missing: "
                    + ", ".join(omitted))
            if invented:
                raise CollaborationError(
                    "synthesis reports nodes with no candidate inside the write fence: "
                    + ", ".join(invented))
            changed = [node for node in candidate_nodes
                       if stated[node].get("candidate_content_hash")
                       != candidates[node].get("content_hash")]
            if changed:
                raise CollaborationError(
                    "synthesis contribution is not bound to the committed candidate content_hash: "
                    + ", ".join(changed))
            canonical = {**synthesis, "candidate_node_ids": candidate_nodes,
                         "contributions": [stated[node] for node in candidate_nodes]}
            return {**current, "synthesis": canonical, "status": "COMPLETED", "updated_at": _now()}

        return self._store.mutate_operational_task(identity.project_id, task_id, apply)

    def list_debates(self, identity: Identity, task_id: str | None = None) -> list[dict[str, Any]]:
        if task_id is not None:
            self._require_task(identity, task_id)
        rows = self._store.list_operational_debates(identity.project_id, task_id)
        return [d for d in rows if self._policy.authorize_debate_read(identity, d).allow]

    def get_debate(self, identity: Identity, debate_id: str) -> dict[str, Any]:
        return self._require_debate(identity, debate_id)

    def _require_task(self, identity: Identity, task_id: str) -> dict[str, Any]:
        task = self._store.get_operational_task(identity.project_id, task_id)
        if task is None:
            raise CollaborationError("no such task in this project")
        self._require(self._policy.authorize_task_read(identity, task))
        return task

    def _require_debate(self, identity: Identity, debate_id: str) -> dict[str, Any]:
        """Read authority BEFORE anything is disclosed about the debate — the ordering
        `_require_task` already had, and which `post_debate_turn` did not: it reported "debate is
        not open" to callers the policy would refuse. Existence within the caller's own project
        is still disclosed by the lookup itself; the store is keyed by (project, id), so that
        much is unavoidable without a second index."""
        debate = self._store.get_operational_debate(identity.project_id, debate_id)
        if debate is None:
            raise CollaborationError("no such debate in this project")
        self._require(self._policy.authorize_debate_read(identity, debate))
        return debate


__all__ = ["CollaborationError", "CollaborationService", "IllegalTaskTransition",
           "MESSAGE_KINDS", "TASK_STATES"]
