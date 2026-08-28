"""U330's falsification, and the one the directive says is absent everywhere in this repo: a
GENUINELY concurrent test — two OS processes, not two threads — publishing candidates and
posting debate turns against the same task, proving neither is lost.

Why two processes and not two threads. Every orchestration writer runs in its own MCP adapter
process, one per live node. `persistence/store.py` holds a `threading.Lock` around its writes,
so a threaded test is ordered by that lock and passes against code with no database transaction
at all — it cannot see the defect. Only separate interpreters, contending through SQLite's own
`BEGIN IMMEDIATE`, exercise what the product does.

What "neither is lost" means concretely — with each claim labelled by what it can actually
catch, because the round-1 gate-validator found one of them decorative (MAJOR-1) and the honest
labelling is now part of the test:

  * **[falsifies]** every turn both processes believe they posted is IN the durable debate
    record, and each debate holds exactly `2 x rounds` of them. Measured: on the parent commit
    this assertion failed on every run;
  * **[falsifies]** no node's candidate revision on the task record ever goes BACKWARDS, watched
    by a third process (`operational_race_watcher.py`) sampling the record while both workers
    write it. A revision is monotone by construction, so one regression IS a lost update.
    Getting this claim to a state where it could fail took four drafts, each measured against the
    defect spliced back into `record_candidate` rather than reasoned about:
      1. publish once at the end → 0/3 detection (the turn loops drift the processes apart, so no
         candidate write ever contends). This is the decorative version the round-1 validator
         caught;
      2. publish once per round, assert the FINAL revision → 1/3 (the final state only reveals a
         loss in the last write);
      3. publish after every turn and have each WRITER watch its peer → 2/5. A writer cannot see
         the damage it does: it destroys the PEER's revision, and its own pre-transaction snapshot
         is never older than what it last read, so its view of the peer is monotone either way;
      4. a third process watching, plus a 1000-revision burst per worker where both hammer the
         one task row back to back → **6/6 detection, 0/4 false positives on the fixed tree**.
    The burst is why the detection is reliable: interleaved with debate turns the vulnerable
    read-to-commit window is a fraction of each writer's loop, and a fifth of runs found it;
  * **[falsifies, but never first]** the per-node round set `1..ROUNDS`. The CEILING cannot be
    breached across processes however the successor is built — each node is the sole writer of its
    own turns — so this claim does not grade the bounded-round rule (the racing unit test in
    `tests/unit/test_operational_write_path.py` §2 and mutation row F2 do). It does fail under a
    lost-turn schedule, because a node whose turn was destroyed recomputes a duplicate round
    number; assertion 1 simply reaches that failure first;
  * **[falsifies]** every turn produced its peer message — the append-only path, verified
    alongside so a regression that trades one loss for another is visible;
  * the store's own integrity check still passes.

The test is deliberately mute about ORDER. Two concurrent nodes have no canonical interleaving,
and asserting one would be asserting a scheduler. What it asserts is that nothing was dropped.

One correction to the directive's premise, since repeating it would be the easy error: a
two-process falsification is not absent from this repo — `tests/integration/test_mcp_cross_process_race.py`
has raced the CAS fence since Phase 3A. What was absent is one for the OPERATIONAL collaboration
writers, which is why five of them could bypass their transaction for two phases unnoticed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from control_plane.policy import Identity, SovereignPolicy
from mcp_server.collaboration_service import CollaborationService
from persistence import SovereignStore

ROOT = Path(__file__).resolve().parents[2]
WORKER = str(ROOT / "tests" / "fixtures" / "operational_race_worker.py")
WATCHER = str(ROOT / "tests" / "fixtures" / "operational_race_watcher.py")

COND = Identity("cond-1", "conductor", "proj")
WORKERS = ("worker-1", "worker-2")
DEBATES = 6          # enough concurrent records that a lost update is not a coin flip
ROUNDS = 5           # the bounded-debate ceiling (invariant 14), per node per debate
BURST = 1000         # candidate revisions each worker publishes back-to-back at the end
REVISIONS = DEBATES * ROUNDS + BURST
WATCH_DEADLINE_S = 300   # the watcher bounds ITSELF too, so a dead parent cannot orphan it


def _seed(db: Path) -> tuple[str, list[str]]:
    """One task owned by both workers, and DEBATES debates they are both party to."""
    store = SovereignStore(db)
    try:
        service = CollaborationService(store, SovereignPolicy())
        task = service.create_task(
            COND, objective="rank the integration risks", owner_node_ids=list(WORKERS),
            acceptance_criteria=["one candidate per worker"])
        debates = [service.open_debate(
            COND, task_id=task["task_id"], proposition=f"proposition {i}",
            participant_node_ids=list(WORKERS), max_rounds=ROUNDS)["debate_id"]
            for i in range(DEBATES)]
        return task["task_id"], debates
    finally:
        store.close()


def test_two_processes_lose_neither_a_debate_turn_nor_a_candidate(tmp_path: Path) -> None:
    # bounded by `communicate(timeout=...)` below rather than a plugin mark, so the bound holds
    # under a bare `pytest` invocation too (there is no committed pytest configuration yet — U339)
    db = tmp_path / "sovereign.db"
    task_id, debate_ids = _seed(db)
    barrier = tmp_path / "go"
    stop = tmp_path / "stop"

    watcher = subprocess.Popen(
        [sys.executable, WATCHER, str(db), task_id, str(stop), str(WATCH_DEADLINE_S)],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        procs = [subprocess.Popen(
            [sys.executable, WORKER, str(db), node_id, task_id, json.dumps(debate_ids),
             str(ROUNDS), str(barrier), str(BURST)],
            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for node_id in WORKERS]
        barrier.write_text("go")   # release both at once
        outs = [p.communicate(timeout=300)[0] for p in procs]
    finally:
        # D-LOOP-1: a worker that hangs must not leave a sampling loop spinning at 100% CPU with
        # nobody left to signal it. The stop file is written on every exit path, and the watcher
        # is killed if it does not take it (it also bounds itself — belt and braces, because the
        # process that would be orphaned is the one that cannot be relied on to notice).
        stop.write_text("stop")
        try:
            watcher_out = watcher.communicate(timeout=60)[0]
        except subprocess.TimeoutExpired:
            watcher.kill()
            watcher_out = watcher.communicate()[0]

    def _report(out: str, who: str) -> dict:
        lines = [ln for ln in out.splitlines() if ln.strip().startswith("{")]
        assert lines, f"{who} produced no result line; output was:\n{out}"
        return json.loads(lines[-1])

    reports = [_report(out, "worker") for out in outs]
    observed = _report(watcher_out, "watcher")

    for report in reports:
        assert report["errors"] == [], f"{report['node_id']} hit errors: {report['errors']}"
        assert report["turns_posted"] == DEBATES * ROUNDS
        assert report["candidate_revisions"] == REVISIONS

    # the strong form of "no candidate is lost": a THIRD process sampled the shared task record
    # throughout, and no node's candidate revision ever went backwards. A revision is monotone by
    # construction, so a single regression IS a lost update, whenever in the run it happened.
    #
    # The three guards before the regression check are anti-vacuity, and they are not decoration:
    # the round-2 validator BLINDED this watcher (tracking only the final post-stop sample) and
    # got one run in four through completely undetected while the sample count and the highest
    # revisions still held — because both of those are satisfied by a single last sample.
    # `distinct_observations` is the one that cannot be: it counts distinct (node, revision) pairs
    # the loop actually saw, which is ~2,000 in a live watch and 2 in a blind one.
    assert not observed["deadline_expired"], "the watcher hit its own deadline; the run did not finish"
    assert observed["samples"] > REVISIONS, "the watcher barely sampled; the run was too short"
    assert observed["distinct_observations"] > REVISIONS, (
        "the watcher saw too few distinct revisions to have been watching: "
        f"{observed['distinct_observations']}")
    assert observed["regressions"] == [], (
        "a candidate write was built from a stale snapshot and reinstated an older revision: "
        + "; ".join(observed["regressions"]))
    assert observed["highest"] == {node: REVISIONS for node in WORKERS}

    store = SovereignStore(db)
    try:
        service = CollaborationService(store, SovereignPolicy())

        # 1. every turn either process believes it posted is in the durable record
        claimed = {turn_id for report in reports for turn_id in report["turn_ids"]}
        persisted = {turn["turn_id"]
                     for debate_id in debate_ids
                     for turn in service.get_debate(COND, debate_id)["turns"]}
        assert claimed <= persisted, f"{len(claimed - persisted)} acknowledged turns were lost"

        # 2. each debate holds exactly the turns the bound allows, per node — no loss, no
        #    double-admission past the round ceiling
        for debate_id in debate_ids:
            debate = service.get_debate(COND, debate_id)
            assert len(debate["turns"]) == len(WORKERS) * ROUNDS, (
                f"{debate_id} holds {len(debate['turns'])} turns")
            for node_id in WORKERS:
                rounds = sorted(t["round"] for t in debate["turns"] if t["node_id"] == node_id)
                assert rounds == list(range(1, ROUNDS + 1)), f"{node_id} in {debate_id}: {rounds}"

        # 3. both candidates are on the one task record, each at the LAST revision its own node
        #    published — the assertion a lost update actually breaks — and the status both imply
        task = service.get_task(COND, task_id)
        candidates = task.get("candidates") or {}
        assert sorted(candidates.keys()) == sorted(WORKERS)
        assert {node: candidates[node]["revision"] for node in WORKERS} == \
            {node: REVISIONS for node in WORKERS}, (
                "a candidate write was built from a stale snapshot and reinstated an old revision")
        assert task["status"] == "CANDIDATE_READY"

        # 4. the append-only peer messages every turn emits (1 assignment + one per turn)
        messages = service.read_messages(COND, task_id=task_id, include_all=True)
        assert sum(1 for m in messages if m["message_kind"] == "debate_turn") == \
            len(WORKERS) * DEBATES * ROUNDS
        assert sum(1 for m in messages if m["message_kind"] == "assignment") == 1

        # 5. the store is still internally consistent
        assert store.verify()["ok"]
    finally:
        store.close()
