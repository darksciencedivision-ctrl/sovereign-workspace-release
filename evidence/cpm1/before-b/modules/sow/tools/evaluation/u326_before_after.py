"""Measure every observable refusal on the collaboration path BEFORE and AFTER the U326 fix.

This is the artifact behind §2 of `docs/evidence/PHASE19_UNIT2_U326_POLICY_DELEGATION_CHECKPOINT.md`.
It is TRACKED and pinned to an explicit base commit on purpose: the first version lived in the
gitignored `docs/loop/logs/` and read `HEAD:`, so the act of committing the fix turned it into a
comparison of the new module with itself and it reported "0 of 31 scenarios differ" — the
report's central quantitative claim, self-invalidated by being recorded. Found by both round-2
reviewers.

The base default is `b529314`, the commit before unit 19.2's work commit. HEAD's pre-unit
`collaboration_service.py` never called the policy object it held — that IS U326 — so importing
it beside the CURRENT `control_plane/policy.py` reproduces the pre-unit behaviour exactly.

Run from the repo root:  py -3.12 tools/evaluation/u326_before_after.py [base-commit]
"""
from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import tempfile

BASE = sys.argv[1] if len(sys.argv) > 1 else "b529314"

sys.path.insert(0, str(pathlib.Path.cwd()))

from control_plane.policy import Identity, SovereignPolicy  # noqa: E402
from persistence import SovereignStore, StoreError  # noqa: E402
import mcp_server.collaboration_service as after  # noqa: E402

BEFORE_SRC = subprocess.run(["git", "show", f"{BASE}:mcp_server/collaboration_service.py"],
                            capture_output=True, text=True, check=True).stdout
if "self._policy." in BEFORE_SRC:
    raise SystemExit(f"{BASE} already delegates to the policy - that is not a pre-U326 base")
_tmp = pathlib.Path(tempfile.mkdtemp()) / "before_collaboration_service.py"
_tmp.write_text(BEFORE_SRC, encoding="utf-8", newline="\n")
_spec = importlib.util.spec_from_file_location("before_collab", _tmp)
before = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(before)

COND = Identity("cond-1", "conductor", "proj")
W1 = Identity("worker-1", "worker", "proj")
W2 = Identity("worker-2", "worker", "proj")
OUT = Identity("worker-out", "worker", "proj")
VOICE = Identity("voice-1", "voice", "proj")
GATE = Identity("gate-1", "gate", "proj")
BAD = Identity("who-1", "hacker", "proj")


def scenarios(svc):
    task = svc.create_task(COND, objective="o", owner_node_ids=[W1.node_id, W2.node_id])
    tid = task["task_id"]
    svc.send_message(W1, task_id=tid, thread_id=None, recipient_node_ids=[COND.node_id],
                     message_kind="progress", body="half")
    deb = svc.open_debate(COND, task_id=tid, proposition="p",
                          participant_node_ids=[W1.node_id, W2.node_id], max_rounds=1)
    did = deb["debate_id"]
    # a CLOSED debate, so the disclosure-before-authority ordering is measured and not argued
    shut = svc.open_debate(COND, task_id=tid, proposition="p3",
                           participant_node_ids=[W1.node_id, W2.node_id], max_rounds=1)
    svc.post_debate_turn(W1, debate_id=shut["debate_id"], body="a")
    svc.post_debate_turn(W2, debate_id=shut["debate_id"], body="b")
    svc.close_debate(COND, debate_id=shut["debate_id"], decision="done")
    sid = shut["debate_id"]
    return [
        ("stranger post to CLOSED debate", lambda: svc.post_debate_turn(OUT, debate_id=sid, body="x")),
        ("voice post to CLOSED debate", lambda: svc.post_debate_turn(VOICE, debate_id=sid, body="x")),
        ("worker create_task", lambda: svc.create_task(W1, objective="o", owner_node_ids=[W1.node_id])),
        ("gate create_task", lambda: svc.create_task(GATE, objective="o", owner_node_ids=[W1.node_id])),
        ("stranger get_task", lambda: svc.get_task(OUT, tid)),
        ("stranger update_task", lambda: svc.update_task(OUT, task_id=tid, status="CANCELLED")),
        ("stranger list_tasks", lambda: svc.list_tasks(OUT)),
        ("voice get_task", lambda: svc.get_task(VOICE, tid)),
        ("voice update_task", lambda: svc.update_task(VOICE, task_id=tid, status="CANCELLED")),
        ("voice send_message", lambda: svc.send_message(VOICE, task_id=tid, thread_id=None,
                                                        recipient_node_ids=[W1.node_id],
                                                        message_kind="question", body="?")),
        ("voice list_tasks", lambda: svc.list_tasks(VOICE)),
        ("voice open_debate", lambda: svc.open_debate(VOICE, task_id=tid, proposition="p",
                                                      participant_node_ids=[W1.node_id, W2.node_id])),
        ("voice get_debate", lambda: svc.get_debate(VOICE, did)),
        ("voice list_debates", lambda: svc.list_debates(VOICE)),
        ("gate open_debate", lambda: svc.open_debate(GATE, task_id=tid, proposition="p2",
                                                     participant_node_ids=[W1.node_id, W2.node_id])),
        ("gate get_task", lambda: svc.get_task(GATE, tid)),
        ("gate list_debates", lambda: svc.list_debates(GATE)),
        ("badrole create_task", lambda: svc.create_task(BAD, objective="o", owner_node_ids=[W1.node_id])),
        ("badrole get_task", lambda: svc.get_task(BAD, tid)),
        ("badrole list_tasks", lambda: svc.list_tasks(BAD)),
        ("badrole get_debate", lambda: svc.get_debate(BAD, did)),
        ("badrole list_debates", lambda: svc.list_debates(BAD)),
        ("worker msg to outsider", lambda: svc.send_message(W1, task_id=tid, thread_id=None,
                                                            recipient_node_ids=[OUT.node_id],
                                                            message_kind="question", body="?")),
        ("worker read_messages", lambda: svc.read_messages(W2, task_id=tid)),
        ("worker include_all", lambda: svc.read_messages(W2, task_id=tid, include_all=True)),
        ("cond include_all", lambda: svc.read_messages(COND, task_id=tid, include_all=True)),
        ("worker close_debate", lambda: svc.close_debate(W1, debate_id=did, decision="d")),
        ("cond post_turn", lambda: svc.post_debate_turn(COND, debate_id=did, body="b")),
        ("stranger get_debate", lambda: svc.get_debate(OUT, did)),
        ("cond record_candidate", lambda: svc.record_candidate(COND, task_id=tid, candidate={
            "provider": "p", "model": "m", "summary": "s", "claims": ["c"], "evidence_refs": ["e"],
            "peer_messages_considered": [], "debates_considered": [], "limitations": ["l"],
            "artifact_ref": "a", "content_hash": "h", "status": "CANDIDATE"})),
        ("worker record_synthesis", lambda: svc.record_synthesis(W1, task_id=tid, synthesis={})),
        # added at round 3: the gate-validator measured a delta outside the first matrix. The
        # round-2 remediation put `_require_task` in front of `record_synthesis`, so a scoped
        # non-owner now meets the scope refusal instead of the role refusal. Measured here
        # rather than described in prose.
        ("stranger record_synthesis", lambda: svc.record_synthesis(OUT, task_id=tid, synthesis={})),
        ("open_debate empty parts, bad task", lambda: svc.open_debate(
            COND, task_id="t-nope", proposition="p", participant_node_ids=[])),
        ("open_debate 1 part", lambda: svc.open_debate(COND, task_id=tid, proposition="p",
                                                       participant_node_ids=[W1.node_id])),
    ]


class _PreU330Store(SovereignStore):
    """The historical module is run VERBATIM, and the pre-U326 module writes through
    `put_operational_task` / `put_operational_debate` — which unit 19.5 deleted (U330), because
    they were the blind upsert five orchestration writers used instead of the store's transaction.
    Without this shim the comparison dies on `AttributeError` and the U326 evidence stops being
    reproducible (found by the round-1 gate-validator at 19.5, MEDIUM-4).

    The shim belongs HERE and not in `persistence/`: it deliberately re-creates the overwrite
    semantics that module expects, so the verdicts observed are the pre-unit ones rather than
    19.5's refusals. Nothing in the product may reach it.
    """

    def put_operational_task(self, task: dict) -> None:
        try:
            self.create_operational_task(task)
        except StoreError:
            self.mutate_operational_task(task["project_id"], task["task_id"], lambda _cur: task)

    def put_operational_debate(self, debate: dict) -> None:
        try:
            self.create_operational_debate(debate)
        except StoreError:
            self.mutate_operational_debate(
                debate["project_id"], debate["debate_id"], lambda _cur: debate)


def observe(mod, tmp):
    store = _PreU330Store(pathlib.Path(tmp) / "s.db")
    svc = mod.CollaborationService(store, SovereignPolicy())
    out = {}
    try:
        for name, call in scenarios(svc):
            try:
                value = call()
                out[name] = ("OK", f"len={len(value)}" if isinstance(value, list) else "ok")
            except Exception as exc:
                out[name] = (type(exc).__name__, str(exc))
    finally:
        store.close()
    return out


def main() -> None:
    print(f"base={BASE}\n")
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        old, new = observe(before, a), observe(after, b)
    width = max(len(k) for k in old)
    diffs = 0
    for key in old:
        o, n = old[key], new[key]
        mark = "  " if o == n else "DIFF"
        if o != n:
            diffs += 1
        print(f"{mark} {key.ljust(width)} | BEFORE {o[0]}: {o[1][:58]:<58} | AFTER {n[0]}: {n[1][:58]}")
    print(f"\n{diffs} of {len(old)} scenarios differ")


main()
