"""CR-004 (private-journal LIMIT applied before owner filtering) and
CR-029 (journal retrieval lacks indexes for its access patterns)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conftest import StubPolicy, sample_provenance  # type: ignore

from control_plane.policy import Identity
from mcp_server.memory_service import MemoryService
from persistence import ContentAddressedStore, SovereignStore

MODULE_ROOT = Path(__file__).resolve().parents[2]  # modules/sow
JOURNAL_STORE = MODULE_ROOT / "apps" / "desktop" / "control" / "journal-store.py"


def _seed_private(root: Path, project_id: str, node_id: str, session_id: str, n: int) -> None:
    """Seed n private_node journal entries authored by node_id. Rows are stored exactly as the
    product would; only the authorizing policy is stubbed (it does not affect stored bytes)."""
    store = SovereignStore(root / "sovereign.db")
    svc = MemoryService(store, ContentAddressedStore(root / "cas"), StubPolicy(allow=True))
    try:
        for i in range(n):
            content = json.dumps({"node_id": node_id, "session_id": session_id,
                                  "pane_id": f"pane-{i}", "text": f"obs {i}"}).encode()
            svc.publish(Identity(node_id, "worker", project_id), kind="evidence",
                        tier="private_node", content=content,
                        provenance=sample_provenance(author_node=node_id))
    finally:
        store.close()


def _run_journal(request: dict) -> dict:
    proc = subprocess.run([sys.executable, str(JOURNAL_STORE)],
                          input=json.dumps(request).encode(), capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode()
    return json.loads(proc.stdout.decode())


def test_cr004_target_row_survives_saturation_by_other_nodes(tmp_path):
    project = "proj-1"
    # 128 private rows for OTHER nodes inserted first, then ONE row for the target node.
    for k in range(128):
        _seed_private(tmp_path, project, f"node-other-{k}", "s-other", 1)
    _seed_private(tmp_path, project, "node-target", "s-target", 1)

    ans = _run_journal({"op": "private_entries", "store_root": str(tmp_path),
                        "project_id": project, "node_id": "node-target"})  # default limit 128
    assert ans["ok"], ans
    entries = ans["result"]
    # Before the fix the default LIMIT was consumed by the 128 other-node rows and the target
    # returned zero (the review's reproduction). Now it returns exactly its own row.
    assert [e.get("node_id") for e in entries] == ["node-target"], entries


def test_cr004_owner_only_never_leaks_other_nodes(tmp_path):
    project = "proj-1"
    _seed_private(tmp_path, project, "node-a", "s", 5)
    _seed_private(tmp_path, project, "node-b", "s", 5)
    ans = _run_journal({"op": "private_entries", "store_root": str(tmp_path),
                        "project_id": project, "node_id": "node-a"})
    assert ans["ok"], ans
    assert {e["node_id"] for e in ans["result"]} == {"node-a"}
    assert len(ans["result"]) == 5


def test_cr029_private_query_plan_uses_indexes(tmp_path):
    store = SovereignStore(tmp_path / "sovereign.db")
    try:
        conn = store._conn()
        plan = conn.execute(
            "EXPLAIN QUERY PLAN "
            "SELECT me.entry_id FROM memory_entries me JOIN heads h ON h.head_ref = me.ref "
            "WHERE me.project_id=? AND me.tier=? "
            "AND json_extract(me.entry_json, '$.provenance.author_node') = ? "
            "ORDER BY me.inserted_ts ASC, me.rowid ASC LIMIT ?",
            ("p", "private_node", "node-a", 128)).fetchall()
        text = " | ".join(r["detail"] for r in plan)
        assert "idx_mem_private" in text, text
        assert "USE TEMP B-TREE" not in text.upper(), text  # index satisfies the ORDER BY
    finally:
        store.close()


def test_cr029_artifact_journal_query_plan_uses_index(tmp_path):
    store = SovereignStore(tmp_path / "sovereign.db")
    try:
        conn = store._conn()
        plan = conn.execute(
            "EXPLAIN QUERY PLAN "
            "SELECT artifact_id, meta_json FROM artifact_meta WHERE project_id=? "
            "AND json_extract(meta_json, '$.created_by_node') = 'shell-journal-observer' "
            "AND json_extract(meta_json, '$.media_type') LIKE ? "
            "ORDER BY inserted_ts DESC, rowid DESC LIMIT ?",
            ("p", "%", 128)).fetchall()
        text = " | ".join(r["detail"] for r in plan)
        assert "idx_artifact_journal" in text, text
    finally:
        store.close()


def test_cr029_indexes_created_on_legacy_store_without_them(tmp_path):
    """Migration/back-compat: a store created before these indexes gains them on the next
    write-open (idempotent CREATE INDEX IF NOT EXISTS in _init_schema)."""
    import sqlite3
    db = tmp_path / "sovereign.db"
    # Build a minimal legacy DB with the tables but none of the CR-029 indexes.
    legacy = sqlite3.connect(db)
    legacy.executescript(
        "CREATE TABLE memory_entries (ref TEXT PRIMARY KEY, entry_id TEXT, version INTEGER, "
        "project_id TEXT, tier TEXT, kind TEXT, status TEXT, content_hash TEXT, prev_version_ref TEXT, "
        "provenance_json TEXT, entry_json TEXT, inserted_ts REAL);"
        "CREATE TABLE heads (key TEXT PRIMARY KEY, head_ref TEXT, updated_ts REAL);"
        "CREATE TABLE artifact_meta (artifact_id TEXT, project_id TEXT, meta_json TEXT, inserted_ts REAL, "
        "PRIMARY KEY(artifact_id, project_id));")
    legacy.commit()
    legacy.close()
    # Opening through SovereignStore runs _init_schema, which must add the indexes idempotently.
    store = SovereignStore(db)
    try:
        names = {r["name"] for r in store._conn().execute(
            "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
        assert {"idx_mem_private", "idx_heads_head_ref", "idx_artifact_journal"} <= names, names
    finally:
        store.close()
