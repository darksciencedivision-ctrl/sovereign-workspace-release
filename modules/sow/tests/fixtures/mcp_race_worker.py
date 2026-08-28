"""Cross-process race worker (test fixture): opens the SAME SQLite store as its siblings and
tries to advance one entry's head to ACCEPTED from a shared expected head. Prints a JSON
result line. Used by test_mcp_cross_process_race to exercise the cross-process CAS fence
(SQLite BEGIN IMMEDIATE), which an in-process threaded test cannot.

    python mcp_race_worker.py <db_path> <entry_id> <expected_head> <conflict_id> <barrier_file>
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from persistence import SovereignStore  # noqa: E402


def main() -> int:
    db_path, entry_id, expected_head, conflict_id, barrier_file = sys.argv[1:6]
    store = SovereignStore(Path(db_path))
    current = store.get_entry(store.get_head(entry_id))
    new_entry = {**current, "status": "ACCEPTED",
                 "provenance": {**current["provenance"], "ts": datetime.now(timezone.utc).isoformat()}}
    # spin until the barrier file appears, so all workers pounce together
    while not Path(barrier_file).exists():
        time.sleep(0.005)
    cas = store.commit_version(new_entry, entry_id, expected_head, conflict_id=conflict_id)
    print(json.dumps({"applied": cas.ok, "head_ref": cas.head_ref,
                      "conflict": bool(cas.conflict)}), flush=True)
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
