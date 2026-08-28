"""Mutation runner for Phase 19 unit 5 — U330/U416/U332, one write path and a gate that holds.

Same contract as its siblings: apply one deliberate defect, run one selector, record RED (a test
caught it) or GREEN (nothing did), restore the original bytes, verify the restore is
BYTE-IDENTICAL by sha256. Exit 1 if anything is GREEN or a restore diverges.

**This harness runs a per-target BASELINE first**, which its siblings do not — the limit the
round-5 spec-auditor recorded as U356. Without it, RED means only "the selector exited non-zero
under the mutation", and a target already failing for an unrelated reason would report RED while
proving nothing. Every distinct selector is run once on the unmutated tree; if any of them is not
green there, the run stops and says so rather than producing numbers that overstate.

The rows are in four groups, and a row's group is part of its claim:

  **GROUP S (S1–S3) — the fence in `persistence/store.py`.** The create paths must refuse rather
  than overwrite, and a mutation may not move a record's identity.

  **GROUP F (F1–F6) — the successor is computed INSIDE the fence.** Each row reverts one writer to
  building its successor from the caller's SNAPSHOT while still calling the transactional method.
  This is the shape that matters: routing the call through `mutate_operational_*` and then writing
  `{**snapshot, ...}` is indistinguishable from the fix in a diff, and loses exactly the same turn.
  A GREEN row here would mean the unit's central claim is guarded by nothing.

  **GROUP A (A1–A3) — U416's abort path**, including its rule, which lives in
  `control_plane/policy.py` and is graded through the collaboration path (never by calling the
  policy directly), so a re-inlined copy inside `mcp_server/` could not pass.

  **GROUP G (G1–G6) — U332's synthesis gate.** One row per clause, because the gate is a
  conjunction and a conjunction can be widened one term at a time.

Run from the repo root:  py -3.12 tools/mutation/_op19_5_write_path_mutations.py
"""
from __future__ import annotations

import hashlib
import pathlib
import signal
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PY = [sys.executable, "-m", "pytest", "-q", "-x"]

STORE = "persistence/store.py"
SERVICE = "mcp_server/collaboration_service.py"
POLICY = "control_plane/policy.py"
TOOLS = "mcp_server/sovereign_tools.py"
README = "schemas/README.md"

WRITE = "tests/unit/test_operational_write_path.py"
FENCE = WRITE + "::TestTheStoreOffersOnlyTheFencedWritePath"
RACE = WRITE + "::TestAConcurrentCommitIsNotOverwritten"
ABORT = WRITE + "::TestADebateCanBeAbortedWhenAParticipantCannotAnswer"
GATE = WRITE + "::TestTheSynthesisDebateGateCannotBeSkipped"
MATRIX = ("tests/unit/test_collaboration_policy_delegation.py"
          "::TestTheWholeVerdictSurfaceIsPinned::test_the_verdict_matrix_matches_the_pinned_table")

COLLAB = ("tests/unit/test_mcp_collaboration.py"
          "::test_a_synthesis_that_states_no_contributions_is_refused_inside_the_fence")

COLLAB_W05_TRANSITION = ("tests/unit/test_mcp_collaboration.py"
                         "::test_a_terminal_status_has_no_outbound_transition")
COLLAB_W05_FREEZE = ("tests/unit/test_mcp_collaboration.py"
                     "::test_a_candidate_that_a_synthesis_cites_cannot_be_rewritten")

#: (label, file, anchor, replacement, selector)
MUTATIONS: list[tuple[str, str, str, str, str]] = [
    # -- GROUP S: the fence exists -------------------------------------------------------
    ("S1 create_operational_task overwrites instead of refusing", STORE,
     '                if conn.execute("SELECT 1 FROM operational_tasks WHERE task_id=?",\n'
     '                                (task["task_id"],)).fetchone():\n'
     '                    raise StoreError(f"operational task {task[\'task_id\']} already exists")\n'
     '                conn.execute(\n'
     '                    "INSERT INTO operational_tasks "',
     '                conn.execute(\n'
     '                    "INSERT OR REPLACE INTO operational_tasks "',
     FENCE + "::test_creating_a_task_twice_is_refused_rather_than_overwriting"),

    ("S2 create_operational_debate overwrites instead of refusing", STORE,
     '                if conn.execute("SELECT 1 FROM operational_debates WHERE debate_id=?",\n'
     '                                (debate["debate_id"],)).fetchone():\n'
     '                    raise StoreError(f"operational debate {debate[\'debate_id\']} already exists")\n'
     '                conn.execute(\n'
     '                    "INSERT INTO operational_debates "',
     '                conn.execute(\n'
     '                    "INSERT OR REPLACE INTO operational_debates "',
     FENCE + "::test_creating_a_debate_twice_is_refused_rather_than_overwriting"),

    ("S3 a debate mutation may silently change task scope", STORE,
     '                        or updated.get("project_id") != project_id \\\n'
     '                        or updated.get("task_id") != current.get("task_id"):',
     '                        or updated.get("project_id") != project_id:',
     FENCE + "::test_a_mutation_may_not_move_a_debate_to_another_task"),

    # -- GROUP F: the successor is built from the snapshot again --------------------------
    ("F1 post_debate_turn appends to the SNAPSHOT's turn list", SERVICE,
     '            turns = list(current["turns"])\n'
     '            round_no = 1 + sum(1 for t in turns if t["node_id"] == identity.node_id)',
     '            turns = list(debate["turns"])\n'
     '            round_no = 1 + sum(1 for t in turns if t["node_id"] == identity.node_id)',
     RACE + "::test_a_debate_turn_that_lands_first_is_not_lost"),

    # F2 is a DIFFERENT defect from F1 on the same two lines: the successor is still appended to
    # the committed turn list, but the bounded-round count (invariant 14) is taken from the
    # snapshot — so a node's turn is admitted past the ceiling under contention while the record
    # itself looks intact. The first draft of this row mutated `current["max_rounds"]` instead and
    # came back GREEN: the ceiling VALUE is immutable, so reading it from the snapshot is not a
    # defect. The count is what moves.
    ("F2 the round ceiling is counted on the SNAPSHOT", SERVICE,
     '            round_no = 1 + sum(1 for t in turns if t["node_id"] == identity.node_id)',
     '            round_no = 1 + sum(1 for t in debate["turns"] if t["node_id"] == identity.node_id)',
     RACE + "::test_the_round_limit_is_evaluated_against_the_committed_record"),

    ("F3 update_task writes the SNAPSHOT back over the row", SERVICE,
     '            updated = {**current, "status": status, "updated_at": _now()}',
     '            updated = {**task, "status": status, "updated_at": _now()}',
     RACE + "::test_a_candidate_published_first_survives_a_status_update"),

    ("F4 close_debate takes its transcript from the SNAPSHOT", SERVICE,
     '            turns = current.get("turns", [])\n'
     '            represented = {turn["node_id"] for turn in turns}',
     '            turns = debate.get("turns", [])\n'
     '            represented = {turn["node_id"] for turn in turns}',
     RACE + "::test_a_turn_that_lands_during_closure_is_carried_into_the_record"),

    ("F5 close_debate trusts the snapshot's OPEN state", SERVICE,
     '            if current["state"] != "OPEN":\n'
     '                raise CollaborationError("debate is not open")\n'
     '            self._require(self._policy.authorize_debate_close(identity, current))',
     '            self._require(self._policy.authorize_debate_close(identity, current))',
     RACE + "::test_the_close_quorum_is_evaluated_against_the_committed_record"),

    # F6 grades the SERVICE half of the create refusal: the store raising is worth nothing if the
    # caller never hears it. (The first draft made `create_task` write twice and graded it with the
    # STORE-level test, which the service cannot affect — GREEN, correctly.)
    ("F6 create_task swallows the store's duplicate refusal", SERVICE,
     '        self._store.create_operational_task(task)',
     '        try:\n'
     '            self._store.create_operational_task(task)\n'
     '        except Exception:  # noqa: BLE001 — the defect\n'
     '            pass',
     FENCE + "::test_creating_a_task_over_an_existing_id_is_refused_at_the_service"),

    # F7 covers the writer this unit did NOT change: `record_candidate` was already inside the
    # fence and graded by nothing, so the defect could be spliced back into it with the whole
    # suite green (round-1 gate-validator, MAJOR-1). The charter names candidate loss FIRST.
    ("F7 record_candidate rebuilds the task from the SNAPSHOT", SERVICE,
     '            candidates = dict(current.get("candidates") or {})',
     '            candidates = dict(task.get("candidates") or {})',
     RACE + "::test_a_peer_candidate_published_first_is_not_overwritten"),

    # -- GROUP A: U416's abort path -------------------------------------------------------
    ("A1 [policy, graded through the collaboration path] a participant may abort", POLICY,
     '        if identity.role not in _DIRECTING_ROLES:\n'
     '            return _deny("only conductor/operator may abort a debate")',
     '        if identity.role not in _DIRECTING_ROLES and identity.node_id not in (\n'
     '                debate.get("participant_node_ids") or ()):\n'
     '            return _deny("only conductor/operator may abort a debate")',
     ABORT + "::test_a_worker_participant_may_not_abort_the_debate_it_is_arguing"),

    # A2 targets the IN-FENCE state check, which is the load-bearing one: the pre-transaction
    # check that reads identically cannot see a commit that has not happened yet, so only a
    # racing abort can tell them apart. (The first draft removed the OUTER check and came back
    # GREEN — correctly: with the in-fence check present the refusal still arrives. That result
    # is why the outer checks are now documented as early/ordering guards rather than as the
    # guarantee.)
    ("A2 a racing second abort overwrites the first one's reason", SERVICE,
     '        def apply(current: dict[str, Any]) -> dict[str, Any]:\n'
     '            if current["state"] != "OPEN":\n'
     '                raise CollaborationError("debate is not open")\n'
     '            self._require(self._policy.authorize_debate_abort(identity, current))',
     '        def apply(current: dict[str, Any]) -> dict[str, Any]:\n'
     '            self._require(self._policy.authorize_debate_abort(identity, current))',
     RACE + "::test_a_second_abort_that_races_the_first_is_refused"),

    ("A3 an abort need not say why", SERVICE,
     '        if not isinstance(reason, str) or not reason.strip():\n'
     '            raise CollaborationError("abort reason must be non-empty")',
     '        if not isinstance(reason, str):\n'
     '            raise CollaborationError("abort reason must be non-empty")',
     ABORT + "::test_an_abort_must_say_why"),

    # -- GROUP G: U332's synthesis gate ---------------------------------------------------
    ("G1 an empty debate_ids list is admitted again", TOOLS,
     '        debate_ids = (_nonempty_strings(raw, "debate_ids") if closed_ids\n'
     '                      else _string_list(raw, "debate_ids"))',
     '        debate_ids = _string_list(raw, "debate_ids")',
     GATE + "::test_an_empty_debate_id_list_no_longer_walks_past_the_gate"),

    ("G2 a closed debate may be left unnamed", TOOLS,
     '        unnamed = [d for d in closed_ids if d not in debate_ids]\n'
     '        if unnamed:',
     '        unnamed: list[str] = []\n'
     '        if unnamed:',
     GATE + "::test_omitting_one_closed_debate_is_refused_and_the_refusal_names_it"),

    ("G3 an open debate no longer blocks publication", TOOLS,
     '        still_open = sorted(d for d, rec in known.items() if rec.get("state") == "OPEN")\n'
     '        if still_open:',
     '        still_open: list[str] = []\n'
     '        if still_open:',
     GATE + "::test_an_open_debate_blocks_the_synthesis_even_when_unnamed"),

    ("G4 a debate from another task satisfies the gate", TOOLS,
     '        foreign = [d for d in debate_ids if d not in known]\n'
     '        if foreign:',
     '        known.update({d: self.collaboration.get_debate(self.identity, d)\n'
     '                      for d in debate_ids if d not in known})\n'
     '        foreign: list[str] = []\n'
     '        if foreign:',
     GATE + "::test_a_closed_debate_from_another_task_does_not_satisfy_the_gate"),

    ("G5 an aborted debate counts as a considered one", TOOLS,
     '        not_closed = [d for d in debate_ids if known[d].get("state") != "CLOSED"]',
     '        not_closed = [d for d in debate_ids\n'
     '                      if known[d].get("state") not in ("CLOSED", "ABORTED")]',
     GATE + "::test_an_aborted_debate_is_disclosed_and_never_counted_as_considered"),

    ("G6 aborted debates are not disclosed in the synthesis", TOOLS,
     '        aborted_ids = sorted(d for d, rec in known.items()\n'
     '                             if rec.get("state") not in ("OPEN", "CLOSED"))',
     '        aborted_ids: list[str] = []',
     GATE + "::test_an_aborted_debate_is_disclosed_and_never_counted_as_considered"),

    # -- the pinned verdict surface still moves when the abort rule does -------------------
    ("A1b [policy] the abort rule's move is visible in the pinned verdict table", POLICY,
     '        if identity.role not in _DIRECTING_ROLES:\n'
     '            return _deny("only conductor/operator may abort a debate")',
     '        if identity.role not in (*_DIRECTING_ROLES, "gate"):\n'
     '            return _deny("only conductor/operator may abort a debate")',
     MATRIX),
    # -- W-16: publication-time synthesis integrity is enforced by the FENCE, not the caller ----
    # The binding validation was gated on `contribution_bindings is not None`, so the invariant
    # "a synthesis must prove which candidates it used" held only because the ONE product caller
    # happened to pass them. This row restores the opt-in and must go red.
    ("W16 the synthesis binding validation goes back to opt-in", SERVICE,
     '            if contribution_bindings is None:\n'
     '                raise CollaborationError(\n'
     '                    "synthesis must state the candidate contributions it is built from; "\n'
     '                    "publication-time integrity is enforced inside the write fence, not by the "\n'
     '                    "caller that happens to pass them")\n',
     '            if contribution_bindings is None:\n'
     '                return {**current, "synthesis": synthesis, "status": "COMPLETED",\n'
     '                        "updated_at": _now()}\n',
     COLLAB),
    # -- W-05: post-publication stability, enforced by the FENCE ------------------------------
    # Both rows delete the check from INSIDE `apply`, which is the whole claim: a status a caller
    # validated may be one commit old by the time the transaction opens, so a check anywhere else
    # is a race. If either row survives, the guard is the caller's and not the fence's.
    ("W05a the transition check leaves the write fence", SERVICE,
     '            _assert_legal_transition(current.get("status", ""), status)\n',
     "",
     COLLAB_W05_TRANSITION),

    ("W05b the candidate freeze is removed, so a cited candidate can be rewritten", SERVICE,
     '            if identity.node_id in cited:\n',
     '            if False:\n',
     COLLAB_W05_FREEZE),

    # -- W-55: startup diagnosability ----------------------------------------------------------
    # The repaired server answers the first frame BEFORE the capability round-trip and degrades a
    # failed resolution into a durably-logged, per-call structured error. Removing the swallow
    # restores the shipped defect's observable shape: the first failed resolution kills the
    # process, so the tool call is never answered and nothing durable is written.
    ("W55 a failed startup capability check kills the process again", TOOLS,
     '    def warm(self) -> None:\n'
     '        try:\n'
     '            self._ensure()\n'
     '        except ToolError:\n'
     '            pass  # diagnosed and durably logged in _build; the next tool call retries',
     '    def warm(self) -> None:\n'
     '        self._ensure()',
     "tests/unit/test_mcp_startup_diagnosability.py"),

    # W-56 restores the OBSERVED defect shape (R-09b): resources/list answered -32601. One line is
    # mutated — the branch's answer — so the row cannot be defeated by editing the comment above it.
    ("W56 resources/list goes back to method-not-found", TOOLS,
     '        return {"jsonrpc": "2.0", "id": rid, "result": {"resources": []}}\n',
     '        return {"jsonrpc": "2.0", "id": rid, "error": '
     '{"code": -32601, "message": f"method not found: {method}"}}\n',
     "tests/unit/test_mcp_resources_list.py"),

    # W-59 deletes the in-fence OPEN-debate gate (U410): record_synthesis completes a task again
    # while a debate on it is still OPEN. The whole block is deleted — not one line — so a partial
    # revert (the check kept, the refusal dropped, or vice versa) reads as anchor-missing rather
    # than silently grading a half-gate.
    ("W59 record_synthesis completes a task over a debate still OPEN", SERVICE,
     '            debates = self._store.list_operational_debates(identity.project_id, task_id)\n'
     '            still_open = sorted(d["debate_id"] for d in debates if d.get("state") == "OPEN")\n'
     '            if still_open:\n'
     '                raise CollaborationError(\n'
     '                    "synthesis requires every debate on this task to be concluded; still open: "\n'
     '                    + ", ".join(still_open))\n',
     '',
     "tests/unit/test_mcp_collaboration.py"
     "::test_record_synthesis_is_refused_while_a_debate_on_the_task_is_open"),

    # W-60 restores the README's universal claim, deleting the retraction's opening sentence: the
    # file once said it was the single source of truth for EVERY governed object while the
    # operational record family pinned no schema. One sentence is the anchor; the boundary section
    # below it is graded by the same test, which also checks the opening claim is rescoped.
    ("W60 schemas/README claims every governed object again", README,
     'Single source of truth for the governed objects its files GROUND — the twelve frozen `@1.0`\n'
     'schemas plus recorded successors, each with its Grounding row below. JSON Schema draft-07. Frozen\n'
     'at Phase 0 (2026-07-16); any change after the operator signs the freeze manifest requires a new\n'
     'schema version (@1.1+), a decision-register entry, and a recorded hash change.\n',
     'Single source of truth for every governed object. JSON Schema draft-07. Frozen at Phase 0\n'
     '(2026-07-16); any change after the operator signs the freeze manifest requires a new schema\n'
     'version (@1.1+), a decision-register entry, and a recorded hash change.\n',
     "tests/unit/test_operational_schema_scope.py"
     "::test_the_readme_states_the_operational_family_is_unschematized"),

    # W-61 deletes the note AT THE WRITE (U349): the stored budget reads as governance again the
    # moment the absence is unwritten. The anchor is the whole open_debate note block — the
    # module-docstring sentence stays, so only the at-write marker is graded here, exactly as the
    # negative test declares.
    ("W61 the unenforced budget at the write goes silent again", SERVICE,
     "        # W-61 / U349, said exactly: the check above is the ONLY thing on this path that reads\n"
     "        # `budget_units`. It is written into the debate record below and never consulted again \u2014\n"
     "        # NO CostGovernor, no per-caller quota, no global cap: invariant 17 is NOT implemented\n"
     "        # here (the donor that implements it, `debate_service/cost_governor/governor.py`, guards\n"
     "        # the Phase-7 Debate Service path only). A stored budget that nothing enforces must not\n"
     "        # read as governance, so the absence is written AT THE WRITE instead of implied. Wiring\n"
     "        # the governor into this path \u2014 or revoking the gate role's debate authority instead \u2014\n"
     "        # is the operator-ruled unit U349 assigns; until then `max_rounds` is the only bound a\n"
     "        # debate here actually feels.\n",
     '',
     "tests/unit/test_invariant17_unimplemented.py"
     "::test_the_service_states_the_stored_budget_is_not_enforced"),

    # W-62 silences the heartbeat (U434): the beat keeps its bookkeeping but never reaches the
    # gateway, so the node's liveness evidence ages out exactly as it did before the repair. One
    # line — the call — is the anchor; leaving `beat()`'s rest intact grades precisely the
    # difference between a heartbeat that RUNS and one that ARRIVES.
    ("W62 the heartbeat beats but never reaches the gateway", TOOLS,
     '            self._app.call("identity", timeout=self._call_timeout_s)\n',
     '            pass  # mutation: the beat no longer reaches the gateway\n',
     "tests/unit/test_mcp_node_heartbeat.py"
     "::test_an_established_node_keeps_itself_verifiably_alive_without_being_provoked"),
]

_PINNED: dict[pathlib.Path, bytes] = {}
_LOCK = ROOT / ".mutation-run.lock"


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _restore_all(*_a: object) -> None:
    for path, original in _PINNED.items():
        try:
            path.write_bytes(original)
        except OSError:                                  # pragma: no cover - best effort teardown
            pass
    _LOCK.unlink(missing_ok=True)


def baseline(target: str) -> bool:
    proc = subprocess.run(PY + [target], cwd=ROOT, capture_output=True, text=True)
    return proc.returncode == 0


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
    try:
        proc = subprocess.run(PY + [target], cwd=ROOT, capture_output=True, text=True)
        verdict = "RED" if proc.returncode != 0 else "GREEN (guard does not hold)"
    finally:
        path.write_bytes(before)
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

    rows: list[tuple[str, str, str]] = []
    try:
        # U356: RED is only meaningful against a target that is green to begin with.
        print("baseline (unmutated tree):")
        unhealthy = []
        for target in dict.fromkeys(m[4] for m in MUTATIONS):
            ok = baseline(target)
            print(f"  {'PASS' if ok else 'FAIL'}  {target}")
            if not ok:
                unhealthy.append(target)
        if unhealthy:
            print("\nrefusing to grade: these selectors are not green before any mutation:\n  "
                  + "\n  ".join(unhealthy))
            return 1
        print()
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
