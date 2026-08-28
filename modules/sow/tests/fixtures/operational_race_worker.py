"""Operational collaboration race worker (test fixture): one real OS process acting as ONE
Sovereign worker node against a shared task — posting debate turns to the same debates its
sibling is posting to, then publishing its candidate on the same task record.

This is the shape U330 is about. Two provider workers are two processes; a Python-level lock
in `persistence/store.py` cannot order them, and the read/modify/write the collaboration
service used to do outside a transaction let one silently overwrite the other.

    python operational_race_worker.py <db_path> <node_id> <task_id> <debate_ids_json>
                                      <turns_per_debate> <barrier_file> <refinement_burst>

Prints one JSON result line: what this process believes it wrote. The parent proves what
actually survived by reading the store.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from control_plane.policy import Identity, SovereignPolicy  # noqa: E402
from mcp_server.collaboration_service import CollaborationService  # noqa: E402
from persistence import SovereignStore  # noqa: E402


def main() -> int:
    (db_path, node_id, task_id, debate_ids_json, turns_per_debate, barrier_file,
     refinement_burst) = sys.argv[1:8]
    debate_ids = json.loads(debate_ids_json)
    rounds = int(turns_per_debate)
    burst = int(refinement_burst)
    store = SovereignStore(Path(db_path))
    service = CollaborationService(store, SovereignPolicy())
    identity = Identity(node_id, "worker", "proj")

    while not Path(barrier_file).exists():   # pounce together
        time.sleep(0.005)

    def candidate(revision: int) -> dict:
        return {
            "task_id": task_id, "worker_node_id": node_id, "provider": "p", "model": "m",
            "summary": f"{node_id} result", "claims": [f"{node_id} claim"],
            "evidence_refs": [f"{node_id}.py:1"], "peer_messages_considered": [],
            "debates_considered": debate_ids, "limitations": [], "status": "CANDIDATE",
            "artifact_ref": f"sha256:{node_id}", "content_hash": f"sha256:{node_id}",
            # The revision is what makes candidate loss VISIBLE, to the watcher process that
            # samples this record while both workers write it. Publishing once, at the end, after
            # the turn loops have drifted the two processes apart, is a schedule in which no
            # candidate write ever contends, and an assertion over it proves nothing
            # (gate-validator MAJOR-1, round 1).
            "revision": revision,
        }

    posted: list[str] = []
    errors: list[str] = []
    statuses: list[str] = []
    for round_no in range(rounds):
        for debate_id in debate_ids:         # same order in both processes: maximum overlap
            try:
                turn = service.post_debate_turn(
                    identity, debate_id=debate_id,
                    body=f"{node_id} round {round_no + 1} on {debate_id}",
                    evidence_refs=[f"{node_id}:{debate_id}:{round_no + 1}"])
                posted.append(turn["turn_id"])
            except Exception as exc:         # noqa: BLE001 — reported, never swallowed
                errors.append(f"{type(exc).__name__}: {exc}")
            # A candidate revision after EVERY turn, not once at the end and not once per round:
            # the window a stale snapshot opens is one read-to-commit gap, so a schedule with a
            # handful of candidate writes closes it by luck rather than by the fence. Both
            # processes write the SAME task row here, continuously, for the whole run.
            try:
                task = service.record_candidate(
                    identity, task_id=task_id, candidate=candidate(len(statuses) + 1))
                statuses.append(task["status"])
            except Exception as exc:         # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")

    # The refinement burst: both processes stop debating and hammer the SAME task row with
    # candidate revisions, back to back. Interleaved with turns the vulnerable window is a
    # read-to-commit gap against a peer that mostly writes elsewhere, so a stale successor is
    # reinstated on roughly a fifth of runs — measured, and too weak to be a falsification. Here
    # every write of one process contends with every write of the other.
    for _ in range(burst):
        try:
            statuses.append(service.record_candidate(
                identity, task_id=task_id, candidate=candidate(len(statuses) + 1))["status"])
        except Exception as exc:                 # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    print(json.dumps({"node_id": node_id, "turns_posted": len(posted), "turn_ids": posted,
                      "candidate_revisions": len(statuses),
                      "candidate_status": statuses[-1] if statuses else None,
                      "errors": errors}), flush=True)
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
