"""SW-JOURNAL-002 F-32: private_node writes, isolation, worker budget. Temp stores only."""
import importlib.util
import json
from pathlib import Path
import pytest
from persistence import SovereignStore, ContentAddressedStore
from control_plane.policy import Identity, SovereignPolicy
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("workspace_journal_store", ROOT / "apps/desktop/control/journal-store.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

def request(tmp_path, **kw):
    return {"store_root": str(tmp_path), "project_id": "proj", **kw}

def seed(tmp_path):
    s = SovereignStore(tmp_path / "sovereign.db"); s.close()
    ContentAddressedStore(tmp_path / "cas")

def entry(node="node-2", session="test-session", **kw):
    return {"schema": "workspace_journal@1.0", "session_id": session, "event_id": "e-" + node,
            "node_id": node, "pane_id": "pane-" + node[-1], "model": "stub-model",
            "utc": "2026-09-06T00:00:00Z", "self_published": False,
            "source": "observed_pane_output", "status": "answered", "prompt": "q",
            "answer": "answer from " + node, "reason": "", "objective": "obj",
            "task_id": "obj-1", "redactions": 0, "redaction_kinds": [], "truncated": False, **kw}

def test_delegation_shape_is_shared_artifact_plus_private_node(tmp_path):
    seed(tmp_path)
    shared = bridge.handle(request(tmp_path, op="append", entry=entry()))
    private = bridge.handle(request(tmp_path, op="append_private", entry=entry()))
    assert shared["created_by_node"] == "shell-journal-observer"
    assert private["status"] == "CANDIDATE"
    rows = bridge.handle(request(tmp_path, op="private_entries", node_id="node-2", session_id="test-session"))
    assert len(rows) == 1
    assert rows[0]["node_id"] == "node-2"
    assert rows[0]["self_published"] is False
    assert rows[0]["source"] == "observed_pane_output"

def test_worker_a_private_entries_exclude_worker_b(tmp_path):
    seed(tmp_path)
    bridge.handle(request(tmp_path, op="append_private", entry=entry("node-2")))
    bridge.handle(request(tmp_path, op="append_private", entry=entry("node-3")))
    a = bridge.handle(request(tmp_path, op="private_entries", node_id="node-2"))
    b = bridge.handle(request(tmp_path, op="private_entries", node_id="node-3"))
    assert [row["node_id"] for row in a] == ["node-2"]
    assert [row["node_id"] for row in b] == ["node-3"]
    assert all("answer from node-3" not in json.dumps(row) for row in a)

def test_policy_denies_a_reading_b_private_entry(tmp_path):
    seed(tmp_path)
    published = bridge.handle(request(tmp_path, op="append_private", entry=entry("node-3")))
    with pytest.raises(ValueError, match="readable only by its author"):
        bridge.handle(request(tmp_path, op="private_get", reader_id="node-2",
                              entry_id=published["entry_id"]))
    policy = SovereignPolicy()
    denied = policy.authorize_read_entry(
        Identity("node-2", "worker", "proj"),
        {"project_id": "proj", "tier": "private_node", "provenance": {"author_node": "node-3"}})
    assert denied.allow is False

def test_worker_budget_uses_runtime_ctx_and_shrinks(tmp_path):
    large = bridge.budget({"worker": True, "num_ctx": 8192, "vram_mib": 8151})
    small = bridge.budget({"worker": True, "num_ctx": 4096, "vram_mib": 8151})
    assert large["available"] is True and small["available"] is True
    assert small["total_max_chars"] < large["total_max_chars"]
    assert small["num_ctx"] == 4096

def test_missing_provenance_never_reaches_private_store(tmp_path):
    seed(tmp_path)
    for e in (entry(self_published=True), entry(source="self_asserted")):
        with pytest.raises(ValueError, match="provenance"):
            bridge.handle(request(tmp_path, op="append_private", entry=e))
    assert bridge.handle(request(tmp_path, op="private_entries", node_id="node-2")) == []

def test_mutation_removing_private_tier_breaks_isolation(tmp_path):
    source_path = Path(bridge.__file__)
    before = source_path.read_bytes()
    source = before.decode("utf-8")
    anchor = 'return service.publish(worker, kind="evidence", tier="private_node",'
    assert source.count(anchor) == 1
    mutant = source.replace(anchor, 'return service.publish(worker, kind="evidence", tier="shared_project",')
    namespace = {"__file__": str(source_path), "__name__": "journal_tier_mutant"}
    exec(compile(mutant, str(source_path), "exec"), namespace)
    seed(tmp_path)
    published = namespace["handle"](request(tmp_path, op="append_private", entry=entry("node-3")))
    leaked = namespace["handle"](request(tmp_path, op="private_get", reader_id="node-2",
                                         entry_id=published["entry_id"]))
    assert json.loads(__import__("base64").b64decode(leaked["content_b64"]))["node_id"] == "node-3"
    seed(tmp_path / "prod")
    prod = bridge.handle(request(tmp_path / "prod", op="append_private", entry=entry("node-3")))
    with pytest.raises(ValueError, match="readable only by its author"):
        bridge.handle(request(tmp_path / "prod", op="private_get", reader_id="node-2",
                              entry_id=prod["entry_id"]))
    assert source_path.read_bytes() == before
