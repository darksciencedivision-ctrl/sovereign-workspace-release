"""Mutation runner for Phase 19 unit 2 — U326, authority returns to `control_plane/policy.py`.

Same contract as its siblings: apply one mutation, run one selector, record RED (a test caught
it) or GREEN (nothing did), restore the original bytes, verify the restore is BYTE-IDENTICAL by
sha256. Exit 1 if anything is GREEN or a restore diverges.

The unit spec (directive §18, unit 19.2) names the falsification this harness must provide:
*"a mutation that changes a policy rule must be caught by a test that goes through the
collaboration path, proving the delegation is live and not decorative."* The rows are in three
groups, and the group a row belongs to is part of its claim:

  **GROUP A (P1–P16l, except P16) — a rule changed in `control_plane/policy.py`, graded through the
  collaboration path.** Each target is a test that calls no policy method: it goes through
  `CollaborationService`. A GREEN row here would be U326 restated as a measurement rather than
  a claim. This is the group the unit spec demands, and it now includes the rules this unit
  WROTE (`_SCOPED_ROLES`, the uniform unknown-role gate) — the round-1 gate-validator proved
  those were pinned by nothing at all, which is the same blindness the unit exists to fix.
  Rounds 2 and 3 each found MORE membership sets unguarded in the WIDENING direction
  (`_DIRECTING_ROLES`; then `authorize_message_read`, the debate read scope, the candidate
  rule's role half and `ROLES` itself) — P16b–P16i. That the same class recurred three times is
  itself the finding: a deny statement and the set it consults are two different things to pin.

  **GROUP B (P16, P17–P19) — clauses the collaboration path CANNOT reach**, because
  `SovereignStore` scopes every operational read by project before the policy is asked (P17–P19),
  or because an earlier rule answers first (P16, the update rule — U343). These are graded by
  direct-policy tests, and saying so is the point: a row here has NOT been proven through the
  collaboration path and must not be counted as if it had. Every such row is labelled
  `[direct-policy]` in its own name, so the output says it too.

  **GROUP C (P20–P26) — the delegation itself**, in the two directions it can fail: DELETE a
  policy call (the rule survives in `control_plane/` and is simply not consulted), or RE-INLINE
  a rule inside `mcp_server/` with the policy call left beside it so the wiring still *looks*
  live. Both the service and the tool layer get both directions, and all four are graded
  behaviourally — the tool-layer pair became possible only once `SovereignToolRuntime` took its
  policy as a required keyword, which round 1 did not have. Before that, P23's only available
  grader was a test that grepped `sovereign_tools.py` for the token the mutation inserts: the
  circularity the cold audit condemned as mutation **O1**. It is not graded that way now.

None of these rows restores shipped code. The pre-unit tree made these decisions inline; there
is no earlier version of `control_plane/policy.py` that carried a wrong collaboration rule. Each
`new` string is a deliberate defect that names the thing it breaks.

LIMIT, found by the round-5 spec-auditor and recorded as U356: RED here means "the selector exited
non-zero under the mutation", and no row runs its selector on the UNMUTATED tree first. A target
that was already failing for an unrelated reason would report RED without proving anything. The
collateral is external — the full suite is green on the same tree, and the evidence report records
it — so the numbers are sound today; the harness's own output is what overstates. A per-target
baseline pass is the fix when someone next touches this file.

Run from the repo root:  py -3.12 tools/mutation/_op19_policy_delegation_mutations.py
"""
from __future__ import annotations

import hashlib
import pathlib
import signal
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
import _bytecode_discipline as _discipline  # CU-A1 (U534)
PY = [sys.executable, "-m", "pytest", "-q", "-x"]

POLICY = "control_plane/policy.py"
APPROVALS = "control_plane/orchestration/session_approvals.py"
#: W-42 grader. The fence is the ONE boundary an executable side effect must pass, so a
#: mutation that bypasses it must go RED or the fence is decoration.
FENCE_SUITE = "tests/unit/test_side_effect_identity_fence.py"
#: W-43 graders. Two DIFFERENT failures of producer authenticity, so two different tests: skipping
#: the verification entirely, and verifying something that omits the decision's target identity.
#: The second is the one a plausible half-implementation actually produces — signing "what was
#: decided" and forgetting "which approval it was decided about" — and only a transplant test can
#: see it, because every other property still holds.
APPROVALS_SUITE = "tests/unit/test_session_approvals.py"
FORGED_DECISION = APPROVALS_SUITE + "::test_a_forged_decision_CANNOT_dispose_of_an_approvable_row"
STAMP_TRANSPLANT = APPROVALS_SUITE + "::test_a_stamp_transplanted_from_one_decision_to_another_is_refused"
SERVICE = "mcp_server/collaboration_service.py"
TOOLS = "mcp_server/sovereign_tools.py"

DELEG = "tests/unit/test_collaboration_policy_delegation.py"
RULES = DELEG + "::TestTheRulesStillHoldThroughTheCollaborationPath"
PERMISSIVE = DELEG + "::TestAPermissivePolicyReachesPastEveryRule"
TOOL_LAYER = DELEG + "::TestTheToolLayerAsksThePolicyToo"
DEPTH = DELEG + "::TestTheCrossProjectClausesAreDefenceInDepth"
UPDATE_RULE = DELEG + "::TestTheUpdateRuleIsTheReadRule"
MATRIX = DELEG + "::TestTheWholeVerdictSurfaceIsPinned::test_the_verdict_matrix_matches_the_pinned_table"

_TURN_CLAUSE = ('        if identity.node_id not in (debate.get("participant_node_ids") or ()):\n'
                '            return _deny("node is not a debate participant")')
_READ_CLAUSE = ('        if self._scoped(identity) and identity.node_id not in (\n'
                '                debate.get("participant_node_ids") or ()):\n'
                '            return _deny("node is not a debate participant")')
_UNKNOWN_BODY = '        return None if identity.role in ROLES else _deny(f"unknown role {identity.role!r}")'
_UPDATE_BODY = "        return self.authorize_task_read(identity, task)"
_CLOSE_CLAUSE = ('        if identity.role not in _DIRECTING_ROLES:\n'
                 '            return _deny("only conductor/operator may close a debate")')
_CAND_CALL = ("        self._authorize(self.policy.authorize_publish_candidate(\n"
              '            self.identity, self.collaboration.get_task(self.identity, args.get("task_id", ""))))\n')
_INLINE_CAND = ('        if self.identity.role != "worker":\n'
                '            raise ToolError("only a worker node may publish a candidate")\n')
_CREATE_CALL = "        self._require(self._policy.authorize_task_create(identity))\n"
_INLINE_CREATE = ('        if identity.role not in ("conductor", "operator"):\n'
                  '            raise CollaborationError("only the conductor/operator may create assignments")\n')
_SYNTH_CALL = "        self._authorize(self.policy.authorize_publish_synthesis(self.identity))\n"
#: `read_messages` opens with the same call one indentation level and 130 lines earlier, so the
#: anchor carries the line that follows it — a first-occurrence replace would otherwise mutate a
#: different guard than the row's label claims.
_SYNTH_TASK_READ = ("        self._require_task(identity, task_id)\n"
                    "        self._require(self._policy.authorize_publish_synthesis(identity))\n")
_INLINE_SYNTH = ('        if self.identity.role not in ("conductor", "operator"):\n'
                 '            raise ToolError("only conductor/operator may publish synthesis")\n')

MUTATIONS = [
    # == W-43: producer authenticity for decision events (U206) ===========================
    ("P39 the reducer stops verifying producer authenticity, so a forged decision disposes a row",
     APPROVALS, "    if not decision_is_authentic(dec, key=approval_decision_key()):",
     "    if False:",
     FORGED_DECISION),
    ("P40 the stamp covers the decision VALUE but not its TARGET, so a stamp transplants",
     APPROVALS, '    body = {k: v for k, v in decision.items() if k != "authenticity"}',
     '    body = {k: v for k, v in decision.items() if k not in ("authenticity", "item_id")}',
     STAMP_TRANSPLANT),
    # == W-42: the presumed-identity side-effect fence ====================================
    ("P38 the presumed-identity fence is bypassed, so a presumed approval may execute",
     APPROVALS, '    if bool(decision.get("operator_identity_presumed")):',
     "    if False:",
     FENCE_SUITE),
    # == GROUP A: one policy rule each, graded THROUGH the collaboration path =============
    ("P1  a worker may create assignments (task-create rule)",
     POLICY, '            return _deny("only the conductor/operator may create assignments")',
     "            return _ALLOW",
     RULES + "::test_a_worker_may_not_create_an_assignment"),
    ("P2  task scope drops: any worker reads any task",
     POLICY, '            return _deny("cross-task access denied")', "            return _ALLOW",
     RULES + "::test_a_stranger_may_not_read_a_task_it_does_not_own"),
    # P3 is the SAME anchor as P2 with a different selector, not a second mutation: the one
    # rule serves the by-id read and the list filter, and both paths are asserted separately.
    ("P3  (same mutation as P2) the rule is also what filters list_tasks",
     POLICY, '            return _deny("cross-task access denied")', "            return _ALLOW",
     RULES + "::test_list_tasks_shows_a_worker_only_its_own"),
    ("P4  a message may be addressed outside its task",
     POLICY, '            return _deny("cross-task recipient denied")', "            return _ALLOW",
     RULES + "::test_a_message_may_not_be_addressed_outside_the_task"),
    ("P5  per-message visibility drops (invariant 8)",
     POLICY, '        return _deny("message is not addressed to this node")', "        return _ALLOW",
     RULES + "::test_a_worker_reads_only_the_messages_it_is_party_to"),
    ("P6  any node may read the full task transcript",
     POLICY, '            return _deny("only the conductor/operator may read a full task transcript")',
     "            return _ALLOW",
     RULES + "::test_only_the_conductor_reads_the_full_transcript"),
    ("P7  authorize_debate's caller rule (the pre-existing entry point) admits voice",
     POLICY, '            return _deny(f"role {identity.role!r} may not request debate")',
     "            return _ALLOW",
     RULES + "::test_any_authorized_node_may_open_a_debate_but_voice_may_not"),
    ("P8  a debate may name nodes outside the task",
     POLICY, '            return _deny("debate needs at least two task participants")',
     "            return _ALLOW",
     RULES + "::test_a_debate_may_not_be_opened_over_nodes_outside_the_task"),
    ("P9  a non-participant may post a debate turn",
     POLICY, _TURN_CLAUSE, '        if False:\n            return _deny("node is not a debate participant")',
     RULES + "::test_a_non_participant_may_not_post_a_turn"),
    ("P10 a worker may close a debate",
     POLICY, '            return _deny("only conductor/operator may close a debate")',
     "            return _ALLOW",
     RULES + "::test_a_worker_may_not_close_a_debate"),
    ("P11 a non-participant worker may read a debate",
     POLICY, _READ_CLAUSE, '        if False:\n            return _deny("node is not a debate participant")',
     RULES + "::test_a_non_participant_worker_may_not_read_a_debate"),
    ("P12 anyone may publish a candidate (I-M6)",
     POLICY, '            return _deny("only an assigned worker may publish a candidate")',
     "            return _ALLOW",
     RULES + "::test_only_an_assigned_worker_publishes_a_candidate"),
    ("P13 a worker may publish the synthesis",
     POLICY, '            return _deny("only conductor/operator may publish synthesis")',
     "            return _ALLOW",
     RULES + "::test_a_worker_may_not_publish_the_synthesis"),
    # P14/P15/P16 cover the rules THIS UNIT wrote. Round 1 had none of them, and the
    # gate-validator demonstrated that changing either left the whole suite green.
    ("P14 _SCOPED_ROLES stops pairing voice with worker (this unit's own rule)",
     POLICY, '_SCOPED_ROLES = frozenset({"worker", "voice"})', '_SCOPED_ROLES = frozenset({"worker"})',
     RULES + "::test_a_voice_identity_is_scoped_like_a_worker_on_reads_and_writes"),
    ("P15 the uniform unknown-role gate fails open (this unit's own rule)",
     POLICY, _UNKNOWN_BODY, "        return None",
     RULES + "::test_a_malformed_role_is_refused_everywhere_it_is_asked"),
    # P16 sits in the Group A block for readability and is NOT a Group A row: its grader calls the
    # policy directly, and the mutation is unreachable through the service anyway (`_require_task`
    # answers first - that is U343's whole finding). Round 4 was right that counting it as
    # collaboration-path proof was the same over-claim the harness exists to prevent.
    ("P16 [direct-policy] update authority stops tracking read authority (U343 inverted)",
     POLICY, _UPDATE_BODY, "        return _ALLOW",
     UPDATE_RULE + "::test_update_authority_is_exactly_read_authority_today"),
    # P16b-P16e close the four rules round 2 found unguarded. P16b is the one that matters most:
    # the MEMBERSHIP SET behind four rules, in the WIDENING direction - the deny statements were
    # mutated by P1/P6/P10/P13 while the set an operator would actually edit was not.
    ("P16b _DIRECTING_ROLES admits gate (the membership set, widening)",
     POLICY, '_DIRECTING_ROLES = ("conductor", "operator")',
     '_DIRECTING_ROLES = ("conductor", "operator", "gate")',
     RULES + "::test_a_gate_node_is_not_one_of_the_directing_roles"),
    ("P16c the two-participant floor goes (bounded debate, invariants 14/15)",
     POLICY, "        if not participants.issubset(self._task_participants(task)) or len(participants) < 2:",
     "        if not participants.issubset(self._task_participants(task)):",
     RULES + "::test_a_debate_needs_two_participants_not_one"),
    ("P16d the task authority set silently absorbs peer_nodes (U347's open question)",
     POLICY, '        return set(task.get("owner_node_ids") or ()) | {task.get("created_by_node_id")}',
     '        return (set(task.get("owner_node_ids") or ()) | {task.get("created_by_node_id")}\n'
     '                | set(task.get("peer_nodes") or ()))',
     RULES + "::test_a_peer_node_that_is_not_an_owner_is_outside_the_authority_set"),
    ("P16e the candidate rule drops the role half and keeps only assignment",
     POLICY, '        if identity.role != "worker" or identity.node_id not in set(task.get("owner_node_ids") or ()):',
     '        if identity.node_id not in set(task.get("owner_node_ids") or ()):',
     RULES + "::test_only_the_worker_role_publishes_a_candidate_even_when_assigned"),
    # P16f-P16i are round 3's. The gate-validator wrote its own twelve-row probe and FIVE
    # widenings survived the full suite; four of them are policy rules and are pinned here (the
    # fifth is P26). Every one is a WIDENING of a membership set or a scope clause - the same
    # class as round 1's `_SCOPED_ROLES` and round 2's `_DIRECTING_ROLES`, on four more constants.
    ("P16f authorize_message_read short-circuits for the directing roles (invariant 8)",
     POLICY, '        if identity.node_id == message.get("sender_node_id"):',
     "        if identity.role in _DIRECTING_ROLES:\n"
     "            return _ALLOW\n"
     '        if identity.node_id == message.get("sender_node_id"):',
     RULES + "::test_the_default_read_gives_the_conductor_only_its_own_traffic"),
    ("P16g debate read admits the opener (a reachable widening, not an equivalent mutant)",
     POLICY, _READ_CLAUSE,
     '        if self._scoped(identity) and identity.node_id not in (\n'
     '                debate.get("participant_node_ids") or ()) and (\n'
     '                identity.node_id != debate.get("opened_by_node_id")):\n'
     '            return _deny("node is not a debate participant")',
     RULES + "::test_opening_a_debate_does_not_make_the_opener_a_reader_of_it"),
    ("P16h the candidate rule's role membership widens to admit the conductor (I-M6)",
     POLICY, '        if identity.role != "worker" or identity.node_id not in set(task.get("owner_node_ids") or ()):',
     '        if identity.role not in ("worker", "conductor") or identity.node_id not in set(task.get("owner_node_ids") or ()):',
     RULES + "::test_a_conductor_named_as_an_owner_still_may_not_publish_a_candidate"),
    ("P16i ROLES gains a member (this unit made it a collaboration READ rule)",
     POLICY, 'ROLES = frozenset({"worker", "conductor", "gate", "operator", "voice"})',
     'ROLES = frozenset({"worker", "conductor", "gate", "operator", "voice", "auditor"})',
     RULES + "::test_every_role_the_policy_admits_has_a_pinned_collaboration_reach"),
    # P16j-P16l are ROUND 4's, and they are graded by the MATRIX rather than by three more
    # one-off tests, because round 4 was the FOURTH consecutive round to find this same class:
    # the deny statement pinned, the membership set or scope clause behind it not. Each of these
    # three survived the entire Python suite when the round-4 gate-validator wrote them.
    ("P16j _DIRECTING_ROLES admits voice (invariant 25 - four authorities at once)",
     POLICY, '_DIRECTING_ROLES = ("conductor", "operator")',
     '_DIRECTING_ROLES = ("conductor", "operator", "voice")', MATRIX),
    ("P16k a debate's opener may close it (invariant 18 territory, U350)",
     POLICY, _CLOSE_CLAUSE,
     '        if identity.role not in _DIRECTING_ROLES and identity.node_id != debate.get(\n'
     '                "opened_by_node_id"):\n'
     '            return _deny("only conductor/operator may close a debate")', MATRIX),
    ("P16l open_debate's task-scope absorbs the caller (a gate names itself in)",
     POLICY, "        if not participants.issubset(self._task_participants(task)) or len(participants) < 2:",
     "        if not participants.issubset(\n"
     "                self._task_participants(task) | {identity.node_id}) or len(participants) < 2:",
     MATRIX),
    # == GROUP B: defence-in-depth clauses the collaboration path CANNOT reach =============
    # Graded by DIRECT policy tests. Stated at the row so no reader counts them as
    # collaboration-path proof: the store scopes reads by project before the policy is asked.
    ("P17 [direct-policy] the cross-project task clause goes",
     POLICY, '            return _deny("cross-project task read denied (scope)")',
     "            return _ALLOW", DEPTH + "::test_a_foreign_project_record_is_refused_by_each_read_rule"),
    ("P18 [direct-policy] the cross-project message clause goes",
     POLICY, '            return _deny("cross-project message read denied (scope)")',
     "            return _ALLOW", DEPTH + "::test_a_foreign_project_record_is_refused_by_each_read_rule"),
    ("P19 [direct-policy] the cross-project debate clause goes",
     POLICY, '            return _deny("cross-project debate read denied (scope)")',
     "            return _ALLOW", DEPTH + "::test_a_foreign_project_record_is_refused_by_each_read_rule"),
    # == GROUP C: the delegation itself, both directions, on BOTH layers ===================
    ("P20 the service stops asking the policy (call deleted, rule intact)",
     SERVICE, _CREATE_CALL, "",
     RULES + "::test_a_worker_may_not_create_an_assignment"),
    ("P21 the service re-inlines the rule beside the call (U326's shape returning)",
     SERVICE, _CREATE_CALL, _CREATE_CALL + _INLINE_CREATE,
     PERMISSIVE + "::test_task_create"),
    ("P22 the tool layer stops asking the policy (call deleted)",
     TOOLS, _SYNTH_CALL, "",
     TOOL_LAYER + "::test_a_worker_may_not_publish_the_synthesis"),
    ("P23 the tool layer re-inlines its own copy of the synthesis rule",
     TOOLS, _SYNTH_CALL, _INLINE_SYNTH + _SYNTH_CALL,
     TOOL_LAYER + "::test_an_injected_permissive_policy_reaches_past_the_tool_layer_gate"),
    # P24/P25 are the CANDIDATE path's twins. Round 2 demonstrated that the tool layer's other
    # gate had no behavioural row at all - both TOOLS rows anchored on the synthesis call - so a
    # re-inlined `getattr(self.identity, "r"+"ole")` check survived the entire suite, reverting
    # the pre-CAS gate this unit claims as an improvement.
    ("P24 the tool layer stops asking about candidates (call deleted)",
     TOOLS, _CAND_CALL, "",
     TOOL_LAYER + "::test_an_unassigned_worker_is_refused_before_anything_reaches_cas"),
    ("P25 the tool layer re-inlines the OLD, coarser candidate rule",
     TOOLS, _CAND_CALL, _INLINE_CAND,
     TOOL_LAYER + "::test_an_injected_permissive_policy_reaches_past_the_candidate_gate"),
    # P26 is round 3's fifth survivor and the one that is a DELETED CALL rather than a widened
    # rule: the round-2 remediation put `_require_task` in front of `record_synthesis` (the one
    # write path that skipped read authority) and removing it again was green.
    ("P26 record_synthesis stops asking task-read authority (round-2's own fix, reverted)",
     SERVICE, _SYNTH_TASK_READ,
     "        self._require(self._policy.authorize_publish_synthesis(identity))\n",
     RULES + "::test_synthesis_asks_task_read_before_it_publishes"),
]

#: Files this run may have mutated, pinned at import so the signal handler can restore ALL of
#: them even if it fires between the write and the restore.
_PINNED: dict[pathlib.Path, bytes] = {}
_LOCK = ROOT / ".mutation-lock"


def digest(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _restore_all(*_a: object) -> None:
    for path, original in _PINNED.items():
        try:
            path.write_bytes(original)
            _discipline.invalidate_for(path)
        except OSError:                                  # pragma: no cover - best effort teardown
            pass
    _LOCK.unlink(missing_ok=True)


def run_one(rel: str, old: str, new: str, target: str) -> tuple[str, str]:
    path = ROOT / rel
    before = _PINNED[path]
    before_hash = digest(path)
    text = before.decode("utf-8")
    if old not in text:
        return "SKIPPED-ANCHOR-MISSING", "unchanged"
    mutated = text.replace(old, new, 1)
    if mutated == text:
        return "SKIPPED-ANCHOR-MISSING", "unchanged"
    path.write_bytes(mutated.encode("utf-8"))
    _discipline.invalidate_for(path)
    try:
        proc = subprocess.run(PY + [target], cwd=ROOT, capture_output=True, text=True, env=_discipline.child_env())
        verdict = "RED" if proc.returncode != 0 else "GREEN (guard does not hold)"
    finally:
        path.write_bytes(before)
    _discipline.invalidate_for(path)
    return verdict, ("restored" if digest(path) == before_hash else "RESTORE FAILED")


def main() -> int:
    if _LOCK.exists():
        print(f"another mutation run holds {_LOCK} - refusing to mutate product files concurrently")
        return 1
    _LOCK.write_text(str(__file__), encoding="utf-8")
    for _, rel, _o, _n, _t in MUTATIONS:
        _PINNED.setdefault(ROOT / rel, (ROOT / rel).read_bytes())
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_a: (_restore_all(), sys.exit(130)))

    rows = []
    try:
        for label, rel, old, new, target in MUTATIONS:
            verdict, restore = run_one(rel, old, new, target)
            rows.append((label, verdict, restore))
    finally:
        _restore_all()

    width = max(len(r[0]) for r in rows)
    for label, verdict, restore in rows:
        print(f"{label.ljust(width)}  {verdict:<26} {restore}")
    ok = all(r[1] == "RED" and r[2] == "restored" for r in rows)
    failed = [r[0] for r in rows if r[2] == "RESTORE FAILED"]
    print(f"\n{sum(1 for r in rows if r[1] == 'RED')}/{len(rows)} RED, "
          + ("all restores byte-identical" if not failed
             else "RESTORE FAILED: " + "; ".join(failed)))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
