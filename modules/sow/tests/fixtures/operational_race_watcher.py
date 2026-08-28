"""Operational collaboration race WATCHER (test fixture): a third real process that does nothing
but read the shared task while two worker processes write it, and reports any moment at which a
node's candidate revision went BACKWARDS.

Why a third process is needed, and why the obvious cheaper checks are not:

  * the FINAL state only reveals a lost update that happened in the last write — measured at
    1 of 3 runs under a deliberately spliced defect;
  * a WRITER watching its peer cannot see the damage it does. Each node only ever publishes a
    higher revision of its own candidate, so what a stale successor destroys is the PEER's
    revision — and the writer's own pre-transaction snapshot is never older than what it last
    read, so its view of the peer is monotone whether or not the fence holds. Measured at 2 of 5.

A reader sampling the durable record between the peer's write and the stale write sees the
regression directly. Sampling runs thousands of times a second against a write rate in the tens,
so the window is observed rather than raced for.

    python operational_race_watcher.py <db_path> <task_id> <stop_file> [deadline_seconds]

Prints one JSON result line: every regression observed, how many samples it took, and how many
DISTINCT (node, revision) pairs it actually saw — the last of those is what says the watch was
live rather than blind, and it exists because the round-2 validator made `regressions == []`
vacuous by blinding this loop while both of the parent's other guards still held.

The deadline is not decoration: this process is spawned by a test and only stops when the parent
writes the stop file, so a parent that dies between spawn and stop would leave it spinning
(D-LOOP-1 — no orphans). It bounds itself.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from persistence import SovereignStore  # noqa: E402


def main() -> int:
    db_path, task_id, stop_file = sys.argv[1:4]
    deadline = time.monotonic() + (float(sys.argv[4]) if len(sys.argv) > 4 else 300.0)
    store = SovereignStore(Path(db_path))
    high: dict[str, int] = {}
    regressions: list[str] = []
    observed: set[tuple[str, int]] = set()
    samples = 0
    expired = False
    stop = Path(stop_file)
    while True:
        finished = stop.exists()          # sample ONCE more after the stop signal, then leave
        task = store.get_operational_task("proj", task_id)
        samples += 1
        for node_id, candidate in ((task or {}).get("candidates") or {}).items():
            seen = int(candidate.get("revision", 0))
            observed.add((node_id, seen))
            if seen < high.get(node_id, 0):
                # deduplicated: `high` never rewinds, so one lost update otherwise appends a line
                # per sample and a failing run printed megabytes (round-2 validator MINOR-1)
                entry = f"{node_id} revision {high[node_id]} -> {seen}"
                if entry not in regressions:
                    regressions.append(entry)
            high[node_id] = max(high.get(node_id, 0), seen)
        if finished:
            break
        if time.monotonic() > deadline:   # the parent died without signalling; do not orphan
            expired = True
            break
    print(json.dumps({"samples": samples, "highest": high, "regressions": regressions,
                      "distinct_observations": len(observed), "deadline_expired": expired}),
          flush=True)
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
