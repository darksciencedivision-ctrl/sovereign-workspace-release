"""Sovereign authorization policy — THE authority (Plan section 3.2; invariants 7, 10, 13).

This is deliberately OUTSIDE mcp_server/: MCP is access/transport, not authority (I-M2).
The MCP server authenticates a node's identity and then asks this policy for a verdict on
every write. Deny-by-default. All role/scope decisions live here and nowhere else:

  - workers publish CANDIDATE only, and may move only their OWN entries to UNDER_REVIEW;
  - promotion to ACCEPTED*/REJECTED is reserved to the gate engine and the operator
    (I-M6: no worker self-canonization);
  - the canonical directive (kind=directive) and conductor files (kind=conductor_file)
    are not worker-writable (Plan Phase 3A exit criterion);
  - reads are project-scoped; candidate vs accepted are distinct read scopes.

The collaboration surface at the bottom of this module (tasks, node-to-node messages,
bounded debates, candidates, synthesis) was added at Phase 19 unit 2 (U326). Those decisions
had been made inline inside `mcp_server/collaboration_service.py` — a second, divergent copy
of the authority in the one package invariant 7 names. The directive named twelve; the file
carried FIFTEEN of that class: fourteen moved here and the fifteenth (`update_task`'s owner clause)
was deleted as provably dead, its entry point returning the read verdict (U343). They are
relocated, and THREE of the surviving rules are
also changed — measured scenario by scenario, never asserted (§2 of
`docs/evidence/PHASE19_UNIT2_U326_POLICY_DELEGATION_CHECKPOINT.md`, 19 of 34 scenarios differ):
`voice` joined `_SCOPED_ROLES`, so a voice identity can no longer read or cancel any task in the
project; a `gate` node may now open a debate, because `authorize_debate` is the canonical I-DS1
rule and the inline copy was stricter (a directed widening, recorded in U349); and a malformed
role is refused where the inline copy served it. Beyond those three the RULES are the ones the
service already raised; §2's remaining deltas are what a caller is TOLD, not what it may do —
including a `voice` caller's `open_debate` refusal, which now reads as the canonical rule's own
sentence. There is no second copy of these rules left to edit — though a DELETED call site in
`mcp_server/` still moves a verdict without touching this file, which is what the harness's Group C
rows exist to catch.
"""
from __future__ import annotations

from dataclasses import dataclass

from mcp_server.lifecycle import is_promotion

ROLES = frozenset({"worker", "conductor", "gate", "operator", "voice"})

# kinds only the operator/system may write (never workers or conductor sessions)
_OPERATOR_ONLY_KINDS = frozenset({"directive", "conductor_file"})

# roles whose collaboration reach is confined to what they were assigned. Everywhere else in
# this module `worker` and `voice` are already paired this way (authorize_publish,
# authorize_transition); the collaboration copy restricted `worker` alone, which left a voice
# identity able to read any task in the project. Paired here — fail-closed direction, recorded.
_SCOPED_ROLES = frozenset({"worker", "voice"})

# the conductor/operator pair. Assignment creation, debate closure, synthesis publication and
# full-transcript reads are theirs; a worker doing any of them is self-canonization (I-M6) or
# a blanket-context read (invariant 8).
_DIRECTING_ROLES = ("conductor", "operator")


@dataclass(frozen=True)
class Identity:
    node_id: str
    role: str
    project_id: str


@dataclass(frozen=True)
class Verdict:
    allow: bool
    reason: str


def _deny(reason: str) -> Verdict:
    return Verdict(False, reason)


_ALLOW = Verdict(True, "allowed by policy")


class SovereignPolicy:
    """Pure decision function. No I/O, no storage — given identity + action, returns a
    verdict. The store performs the op only if this says allow."""

    def authorize_read(self, identity: Identity, resource_kind: str, project_id: str, status_scope: str | None) -> Verdict:
        if identity.role not in ROLES:
            return _deny(f"unknown role {identity.role!r}")
        if project_id != identity.project_id:
            return _deny("cross-project read denied (scope)")
        return _ALLOW

    def authorize_read_entry(self, identity: Identity, entry: dict) -> Verdict:
        """Read authority for a SPECIFIC entry (direct-read paths get_content/get_head).
        Enforces tier isolation (invariant 9): private_node and local_conversational entries
        are readable only by their author; shared_project is project-scoped. The list read
        path is shared-only by query shape, but a by-id read must enforce tier at the
        authority so a same-project node can't fetch another node's private bytes."""
        if identity.role not in ROLES:
            return _deny(f"unknown role {identity.role!r}")
        if entry.get("project_id") != identity.project_id:
            return _deny("cross-project read denied (scope)")
        tier = entry.get("tier")
        if tier != "shared_project":
            author = entry.get("provenance", {}).get("author_node")
            if author != identity.node_id:
                return _deny(f"tier {tier!r} is readable only by its author (invariant 9)")
        return _ALLOW

    def authorize_publish(self, identity: Identity, entry: dict) -> Verdict:
        """A fresh publish of a memory version (version 1 or a new-content candidate)."""
        if identity.role not in ROLES:
            return _deny(f"unknown role {identity.role!r}")
        if entry.get("project_id") != identity.project_id:
            return _deny("cross-project write denied (scope)")
        kind = entry.get("kind")
        status = entry.get("status")
        if kind in _OPERATOR_ONLY_KINDS and identity.role != "operator":
            return _deny(f"kind {kind!r} is operator-only (canonical directive not worker-writable)")
        author = entry.get("provenance", {}).get("author_node")
        if author != identity.node_id:
            return _deny("provenance.author_node must be the publishing node")
        if identity.role in ("worker", "voice") and status != "CANDIDATE":
            return _deny("workers may publish only CANDIDATE entries (I-M6: no self-canonization)")
        if is_promotion(status or ""):
            if identity.role not in ("gate", "operator"):
                return _deny(f"publishing directly into {status} requires gate/operator authority")
            # invariant 18 also applies to the publish path (not only transition): a gate may
            # not publish its OWN WORK PRODUCT (finding/evidence/artifact_ref) directly into a
            # promoted state. A gate's own decision/gate-record is its authoritative verdict,
            # not self-judged work, so kind=decision is allowed (e.g. a plan-gate verdict).
            if identity.role == "gate" and kind in ("finding", "evidence", "artifact_ref"):
                return _deny("a gate may not publish its own work product directly into a promoted state (invariant 18)")
        return _ALLOW

    def authorize_transition(self, identity: Identity, current_entry: dict, requested_status: str) -> Verdict:
        """A status transition on an existing entry."""
        if identity.role not in ROLES:
            return _deny(f"unknown role {identity.role!r}")
        if current_entry.get("project_id") != identity.project_id:
            return _deny("cross-project transition denied (scope)")
        if is_promotion(requested_status):
            if identity.role not in ("gate", "operator"):
                return _deny("promotion to ACCEPTED*/REJECTED is gate/operator-only (I-M6)")
            # invariant 18 (no node solely judges its own work): a GATE may not promote an
            # entry it authored. The operator is the human final authority and is exempt (logged).
            author = current_entry.get("provenance", {}).get("author_node")
            if identity.role == "gate" and author == identity.node_id:
                return _deny("a gate may not promote an entry it authored (invariant 18)")
            return _ALLOW
        # non-promotion transitions (e.g. -> UNDER_REVIEW): workers only on their own entries
        if identity.role in ("worker", "voice"):
            author = current_entry.get("provenance", {}).get("author_node")
            if author != identity.node_id:
                return _deny("a worker may transition only its own entries")
        return _ALLOW

    def authorize_put_artifact(self, identity: Identity, project_id: str) -> Verdict:
        if identity.role not in ROLES:
            return _deny(f"unknown role {identity.role!r}")
        if project_id != identity.project_id:
            return _deny("cross-project artifact write denied (scope)")
        return _ALLOW

    def authorize_checkpoint(self, identity: Identity) -> Verdict:
        if identity.role not in ("conductor", "operator"):
            return _deny("only the conductor/operator may serialize succession state")
        return _ALLOW

    def authorize_health(self, identity: Identity) -> Verdict:
        # store health is an operational view; reserve it to operator/conductor (spec-audit F8)
        if identity.role not in ("operator", "conductor"):
            return _deny("store health is operator/conductor-only")
        return _ALLOW

    def authorize_debate(self, identity: Identity, request: dict) -> Verdict:
        """Any AUTHORIZED node may request a debate (I-DS1) — not conductor-coupled. Voice is a
        transducer, not a reasoning caller. The cost governor + invariant-18 check (in the
        Debate Service) enforce budget and self-judging separately."""
        if identity.role not in ("worker", "conductor", "gate", "operator"):
            return _deny(f"role {identity.role!r} may not request debate")
        if request.get("caller_node") not in (None, identity.node_id):
            return _deny("debate caller_node must be the requesting node")
        if not request.get("participants"):
            return _deny("a debate requires at least one participant descriptor")
        return _ALLOW

    # -- collaboration: tasks, messages, bounded debates, candidates, synthesis --------
    # U326 (cold audit B1, 2026-08-06). Every entry point below answers ONE question the
    # collaboration service used to answer for itself. The service now raises whatever reason
    # comes back and decides nothing.

    def _scoped(self, identity: Identity) -> bool:
        return identity.role in _SCOPED_ROLES

    @staticmethod
    def _unknown(identity: Identity) -> Verdict | None:
        """Deny-by-default on the role itself, asked first by every collaboration entry point
        that does not already carry an explicit role list (`authorize_debate` and, through it,
        `authorize_open_debate`, refuse an unknown role by their own four-role set). The first
        draft gated the task rules and not the debate ones, so a malformed role read zero tasks
        and every debate in the project: an asymmetry in a deny-by-default surface is a
        fail-open."""
        return None if identity.role in ROLES else _deny(f"unknown role {identity.role!r}")

    @staticmethod
    def _task_participants(task: dict) -> set[str]:
        """A task's authority set: its assigned owners plus whoever created it."""
        return set(task.get("owner_node_ids") or ()) | {task.get("created_by_node_id")}

    def authorize_task_create(self, identity: Identity) -> Verdict:
        if unknown := self._unknown(identity):
            return unknown
        if identity.role not in _DIRECTING_ROLES:
            return _deny("only the conductor/operator may create assignments")
        return _ALLOW

    def authorize_task_read(self, identity: Identity, task: dict) -> Verdict:
        """Read authority for one task record — also the filter behind list_tasks."""
        if unknown := self._unknown(identity):
            return unknown
        if task.get("project_id") != identity.project_id:
            return _deny("cross-project task read denied (scope)")
        if self._scoped(identity) and identity.node_id not in set(task.get("owner_node_ids") or ()):
            return _deny("cross-task access denied")
        return _ALLOW

    def authorize_task_update(self, identity: Identity, task: dict) -> Verdict:
        """Update authority — today it IS the read rule, and that is a finding, not a shortcut.

        The inline check this replaces ("worker may update only an assigned task") tested a
        condition byte-identical to the one inside `authorize_task_read`, which ran first on the
        same path. It could not fire for any input, and widening the read scope would widen both
        clauses together, so no future change makes it live either. It is therefore NOT carried
        forward as dead code with an invented justification (U343). This stays a separate entry
        point so update authority can diverge from read authority later — in `control_plane/`,
        which is the whole point — and `TestTheUpdateRuleIsTheReadRule` pins that it does not
        diverge today."""
        return self.authorize_task_read(identity, task)

    def authorize_send_message(self, identity: Identity, task: dict,
                               recipient_node_ids: list[str]) -> Verdict:
        """Sender must be party to the task; recipients may not reach outside it (invariant 8 —
        context is scoped, so a message is not a route to a node the task never named)."""
        if unknown := self._unknown(identity):
            return unknown
        participants = self._task_participants(task)
        # SHADOWED ON THE SERVICE PATH (U343): `_require_task` refuses a scoped non-owner before
        # this is ever asked, so only a DIRECT caller of this entry point can reach the clause.
        # Kept — unlike the update rule, deleting it changes an observable verdict, and
        # `test_the_sender_rule_is_live_for_a_direct_caller` is red if it goes.
        if self._scoped(identity) and identity.node_id not in participants:
            return _deny("sender is not a participant in this task")
        if not set(recipient_node_ids).issubset(participants):
            return _deny("cross-task recipient denied")
        return _ALLOW

    def authorize_message_read(self, identity: Identity, message: dict) -> Verdict:
        """Per-message visibility: sender or addressee. The filter behind read_messages."""
        if unknown := self._unknown(identity):
            return unknown
        if message.get("project_id") != identity.project_id:
            return _deny("cross-project message read denied (scope)")
        if identity.node_id == message.get("sender_node_id"):
            return _ALLOW
        if identity.node_id in (message.get("recipient_node_ids") or ()):
            return _ALLOW
        return _deny("message is not addressed to this node")

    def authorize_read_task_transcript(self, identity: Identity) -> Verdict:
        """The whole task transcript, unfiltered. Reserved to the conductor/operator: a worker
        receiving every message would be the blanket forwarding invariant 8 forbids. Note it
        takes no task — any conductor in the project reads any task's transcript; expressing
        "the conductor OF THIS TASK" needs a task-scoped conductor identity the build does not
        have yet (U348)."""
        if unknown := self._unknown(identity):
            return unknown
        if identity.role not in _DIRECTING_ROLES:
            return _deny("only the conductor/operator may read a full task transcript")
        return _ALLOW

    def authorize_open_debate(self, identity: Identity, task: dict,
                              participant_node_ids: list[str]) -> Verdict:
        """I-DS1: any AUTHORIZED node may request a debate — the caller rule is
        `authorize_debate` above, unchanged and now shared. What this adds is the task scope:
        the participants must be that task's own, and a debate needs two of them."""
        verdict = self.authorize_debate(
            identity, {"caller_node": identity.node_id, "participants": list(participant_node_ids)})
        if not verdict.allow:
            return verdict
        participants = set(participant_node_ids)
        if not participants.issubset(self._task_participants(task)) or len(participants) < 2:
            return _deny("debate needs at least two task participants")
        return _ALLOW

    def authorize_debate_turn(self, identity: Identity, debate: dict) -> Verdict:
        if unknown := self._unknown(identity):
            return unknown
        if identity.node_id not in (debate.get("participant_node_ids") or ()):
            return _deny("node is not a debate participant")
        return _ALLOW

    def authorize_debate_close(self, identity: Identity, debate: dict) -> Verdict:
        if unknown := self._unknown(identity):
            return unknown
        if identity.role not in _DIRECTING_ROLES:
            return _deny("only conductor/operator may close a debate")
        return _ALLOW

    def authorize_debate_abort(self, identity: Identity, debate: dict) -> Verdict:
        """Ending a bounded debate WITHOUT a conclusion (U416: a participant whose pane died can
        never post the turn closure requires, so the debate stayed OPEN forever, its peers
        accumulated stall timers, and the task's synthesis gate was blocked behind a node that
        would never answer).

        This is a ROLE rule, not a participation rule, and the distinction matters more than the
        first draft of this docstring admitted (19.5 spec-auditor MAJOR-1). It refuses every
        worker and voice identity, including the participants a debate is most likely to stall
        between — but it does NOT refuse a DIRECTING node that is itself a participant, and the
        conductor usually is one: `_task_participants` includes the task's creator, so a debate
        opened between the conductor and a worker admits the conductor here on role alone. A
        conductor can therefore abort a deliberation it is arguing in, which is **U350's** open
        question (recorded there for `authorize_debate_close`, whose shape this copies) and not a
        protection this rule provides. `test_the_conductor_may_abort_a_debate_it_is_arguing_in`
        and the verdict matrix's `abort_own_debate` column pin that as the CURRENT behaviour, so
        U350's eventual answer moves a cell rather than passing unnoticed.

        Why role and not participation, given that: a rule refusing every participant would put
        the stall back. The conductor is frequently a participant, and if it could not abort, the
        debate it opened with a dead worker would be permanent again — the exact defect. The
        operator is admitted here too, on role alone (`operator | abort_fresh_debate` reads 'ok'
        in the verdict matrix). That is all this module decides. WHICH identities any surface
        actually mints, and what recourse exists when the conductor's own pane dies, are
        questions about the product and not about this rule — asked and answered on the evidence
        in **U420**, where two successive drafts of this docstring answered them here and were
        wrong in opposite directions (19.5 spec-auditor rounds 2 and 3). An authority module
        states its verdicts.

        What keeps an abort from being a gate override is downstream, not here: ABORTED is not
        CLOSED, and the store reports the two separately (no UI renders that distinction yet —
        **U412**, owned by 19.8). The synthesis gate that refuses to
        count it lives on the `sovereign_tools` tool path — `CollaborationService.record_synthesis`
        has no debate check of its own (**U410**), so that defence is as wide as the product's
        single caller, not as wide as this module.
        """
        if unknown := self._unknown(identity):
            return unknown
        if identity.role not in _DIRECTING_ROLES:
            return _deny("only conductor/operator may abort a debate")
        return _ALLOW

    def authorize_debate_read(self, identity: Identity, debate: dict) -> Verdict:
        """Read authority for one debate — also the filter behind list_debates."""
        if unknown := self._unknown(identity):
            return unknown
        if debate.get("project_id") != identity.project_id:
            return _deny("cross-project debate read denied (scope)")
        if self._scoped(identity) and identity.node_id not in (
                debate.get("participant_node_ids") or ()):
            return _deny("node is not a debate participant")
        return _ALLOW

    def authorize_publish_candidate(self, identity: Identity, task: dict) -> Verdict:
        """I-M6 again, on the operational path: a worker publishes CANDIDATE for work it was
        actually assigned, and nobody else publishes on its behalf."""
        if unknown := self._unknown(identity):
            return unknown
        if identity.role != "worker" or identity.node_id not in set(task.get("owner_node_ids") or ()):
            return _deny("only an assigned worker may publish a candidate")
        return _ALLOW

    def authorize_publish_synthesis(self, identity: Identity) -> Verdict:
        if unknown := self._unknown(identity):
            return unknown
        if identity.role not in _DIRECTING_ROLES:
            return _deny("only conductor/operator may publish synthesis")
        return _ALLOW
