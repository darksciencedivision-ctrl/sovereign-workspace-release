"""Phase 3A D-MCP-03 mandatory test, cross-process form (spec-audit F1): N real OS processes
race to advance ONE head. Exactly one wins; the rest get conflict records; every version is
preserved; the store stays consistent. This exercises the SQLite BEGIN IMMEDIATE fence that
the in-process threaded test cannot — a regression that removed the fence would let two
processes both win, and this test would catch it."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from persistence import SovereignStore

ROOT = Path(__file__).resolve().parents[2]
WORKER = str(ROOT / "tests" / "fixtures" / "mcp_race_worker.py")


def _seed(db: Path, entry_id: str) -> str:
    """Create entry_id at CANDIDATE@1 -> UNDER_REVIEW@2 and return the head ref @2."""
    store = SovereignStore(db)
    prov = {"author_node": "seed", "task_id": None, "ts": datetime.now(timezone.utc).isoformat(),
            "directive_version": "v2.4", "confidence": "high"}
    base = {"entry_id": entry_id, "project_id": "proj", "tier": "shared_project", "kind": "finding",
            "status": "CANDIDATE", "content_hash": "sha256:" + "0" * 64, "provenance": prov}
    store.commit_version(base, entry_id, "", conflict_id="c-seed1")
    store.commit_version({**base, "status": "UNDER_REVIEW"}, entry_id, f"{entry_id}@1", conflict_id="c-seed2")
    head = store.get_head(entry_id)
    store.close()
    return head


@pytest.mark.parametrize("n", [5])
def test_cross_process_race_exactly_one_winner(tmp_path: Path, n: int) -> None:
    db = tmp_path / "sovereign.db"
    entry_id = "m-race"
    expected_head = _seed(db, entry_id)
    barrier = tmp_path / "go"

    procs = [subprocess.Popen(
        [sys.executable, WORKER, str(db), entry_id, expected_head, f"c-race{i}", str(barrier)],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) for i in range(n)]
    barrier.write_text("go")  # release all workers at once

    outs = [p.communicate(timeout=60)[0] for p in procs]
    results = [json.loads([ln for ln in o.splitlines() if ln.strip().startswith("{")][-1]) for o in outs]

    applied = [r for r in results if r["applied"]]
    lost = [r for r in results if not r["applied"]]
    assert len(applied) == 1, f"exactly one process may win the head, got {len(applied)}: {results}"
    assert len(lost) == n - 1 and all(r["conflict"] for r in lost)

    store = SovereignStore(db)
    assert store.get_head(entry_id) == applied[0]["head_ref"]      # head is the single winner
    assert len(store.list_conflicts("proj", entry_id)) == n - 1    # one conflict per loser
    assert store.verify()["ok"]                                    # consistent, no dangling head
    # every loser's version is preserved as a fork (nothing silently overwritten)
    versions = [store.get_entry(f"{entry_id}@{v}") for v in range(1, n + 3)]
    assert sum(1 for v in versions if v and v["status"] == "ACCEPTED") == n  # winner + (n-1) forks
    store.close()
