"""SW-JOURNAL-001 headless store/budget integration; temporary stores, no model or app."""
import importlib.util
import json
import sqlite3
from pathlib import Path
import pytest
from persistence import SovereignStore, ContentAddressedStore
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("workspace_journal_store", ROOT/"apps/desktop/control/journal-store.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

def request(tmp_path, **kw):
    return {"store_root":str(tmp_path), "project_id":"proj", **kw}

def seed(tmp_path):
    s=SovereignStore(tmp_path/"sovereign.db");s.close()
    ContentAddressedStore(tmp_path/"cas")

def entry(session="test-session", **kw):
    return {"schema":"workspace_journal@1.0","session_id":session,"event_id":"e-1",
            "node_id":"node-2","pane_id":"pane-2","model":"stub-model","utc":"2026-09-06T00:00:00Z",
            "self_published":False,"source":"observed_pane_output","answer":"bounded answer",**kw}

def test_existing_artifact_operations_roundtrip_without_fabricating_an_operational_task(tmp_path):
    seed(tmp_path)
    e=entry(task_id="observed-delegation-task")
    meta=bridge.handle(request(tmp_path,op="append",entry=e))
    assert meta["created_by_node"]=="shell-journal-observer"
    assert meta["task_id"] is None
    assert bridge.handle(request(tmp_path,op="entries",session_id="test-session"))==[e]
    with sqlite3.connect(tmp_path/"sovereign.db") as db:
        assert db.execute("select count(*) from operational_tasks").fetchone()[0]==0

def test_absent_store_is_not_constructed_by_read_or_write(tmp_path):
    for op in ("entries","append"):
        with pytest.raises(ValueError,match=r"no journal store \(sovereign.db absent\)"):
            bridge.handle(request(tmp_path,op=op,entry=entry()))
    assert list(tmp_path.iterdir())==[]

def test_reads_are_project_and_session_scoped(tmp_path):
    seed(tmp_path)
    bridge.handle(request(tmp_path,op="append",entry=entry()))
    assert bridge.handle(request(tmp_path,op="entries",session_id="other"))==[]
    assert bridge.handle({**request(tmp_path,op="entries"),"project_id":"other"})==[]

def test_missing_provenance_never_reaches_store(tmp_path):
    seed(tmp_path)
    for e in (entry(self_published=True),entry(source="self_asserted")):
        with pytest.raises(ValueError,match="provenance"):
            bridge.handle(request(tmp_path,op="append",entry=e))
    assert bridge.handle(request(tmp_path,op="entries"))==[]

def test_unreadable_blob_is_explicit_and_reads_leave_store_unchanged(tmp_path):
    seed(tmp_path)
    meta=bridge.handle(request(tmp_path,op="append",entry=entry()))
    cas=ContentAddressedStore(tmp_path/"cas")
    cas._path_for(meta["artifact_id"]).unlink()
    before=(tmp_path/"sovereign.db").read_bytes()
    rows=bridge.handle(request(tmp_path,op="entries"))
    assert rows[0]["unreadable"] is True
    assert rows[0]["reason"]=="journal artifact unreadable"
    assert (tmp_path/"sovereign.db").read_bytes()==before

def test_budget_uses_existing_derivation_and_shrinks_with_stub_host():
    from control_plane.orchestration.pane_observation import observation_budget, recommended_num_ctx
    large=bridge.budget({"vram_mib":8151})
    small=bridge.budget({"vram_mib":7400})
    assert large["num_ctx"]==recommended_num_ctx(8151)[0]
    assert small["total_max_chars"]==observation_budget(7400)["total_max_chars"]
    assert small["total_max_chars"]<large["total_max_chars"]

@pytest.mark.parametrize("profile",[{},{"vram_mib":0},{"vram_mib":None}])
def test_unmeasurable_runtime_budget_does_not_use_advisory_fallback(profile):
    result=bridge.budget(profile)
    assert result["available"] is False
    assert "total_max_chars" not in result

def test_positive_hardware_fallback_is_not_a_measured_runtime_budget(monkeypatch):
    monkeypatch.setattr(bridge,"hardware_profile",lambda:{"vram_mib":8192,
        "source":"not detected; assuming the historical default"})
    assert bridge.budget()["available"] is False

# SW-JOURNAL-001-A1 F-30: temp stores only, including the real JSON CLI boundary.
def test_database_without_cas_bootstraps_and_persists(tmp_path):
    store = SovereignStore(tmp_path / "sovereign.db")
    store.close()
    assert not (tmp_path / "cas").exists()
    meta = bridge.handle(request(tmp_path, op="append", entry=entry()))
    assert (tmp_path / "cas").is_dir()
    assert meta["created_by_node"] == "shell-journal-observer"
    assert bridge.handle(request(tmp_path, op="entries")) == [entry()]


def test_read_bootstraps_empty_cas_without_changing_database(tmp_path):
    store = SovereignStore(tmp_path / "sovereign.db")
    store.close()
    before = (tmp_path / "sovereign.db").read_bytes()
    assert bridge.handle(request(tmp_path, op="entries")) == []
    assert (tmp_path / "cas").is_dir()
    assert list((tmp_path / "cas").iterdir()) == []
    assert (tmp_path / "sovereign.db").read_bytes() == before


@pytest.mark.parametrize("op", ["append", "entries"])
def test_entirely_absent_root_still_refuses(tmp_path, op):
    absent = tmp_path / "absent"
    with pytest.raises(ValueError, match=r"no journal store \(sovereign.db absent\)"):
        bridge.handle(request(absent, op=op, entry=entry()))
    assert not absent.exists()


@pytest.mark.parametrize("op", ["append", "entries"])
def test_unreadable_database_refuses_before_store_construction(tmp_path, monkeypatch, op):
    seed(tmp_path)
    db = tmp_path / "sovereign.db"
    before = db.read_bytes()
    original = Path.open
    def denied(path, *args, **kwargs):
        if path == db:
            raise PermissionError("private host path must not reach the diagnostic")
        return original(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", denied)
        with pytest.raises(ValueError, match="^journal store could not be opened$"):
            bridge.handle(request(tmp_path, op=op, entry=entry()))
    assert db.read_bytes() == before


@pytest.mark.parametrize("op", ["append", "entries"])
def test_invalid_database_is_unopenable_not_absent(tmp_path, op):
    db = tmp_path / "sovereign.db"
    db.write_bytes(b"not a sqlite database")
    with pytest.raises(ValueError, match="^journal store could not be opened$"):
        bridge.handle(request(tmp_path, op=op, entry=entry()))
    assert db.read_bytes() == b"not a sqlite database"
    assert not (tmp_path / "cas").exists()


def test_bootstrapped_artifact_bytes_equal_preexisting_cas_artifact(tmp_path):
    roots = [tmp_path / "bootstrap", tmp_path / "existing"]
    content = []
    for index, root in enumerate(roots):
        store = SovereignStore(root / "sovereign.db")
        store.close()
        if index:
            ContentAddressedStore(root / "cas")
        meta = bridge.handle(request(root, op="append", entry=entry()))
        content.append(ContentAddressedStore(root / "cas").get(meta["artifact_id"]))
    assert content[0] == content[1] == json.dumps(entry(), sort_keys=True, ensure_ascii=False).encode("utf-8")
    assert json.loads(content[0])["self_published"] is False
    assert json.loads(content[0])["source"] == "observed_pane_output"


def test_cas_creation_failure_is_an_open_refusal(tmp_path):
    store = SovereignStore(tmp_path / "sovereign.db")
    store.close()
    (tmp_path / "cas").write_bytes(b"not a directory")
    with pytest.raises(ValueError, match="^journal store could not be opened$"):
        bridge.handle(request(tmp_path, op="append", entry=entry()))
    assert (tmp_path / "cas").read_bytes() == b"not a directory"


def cli_request(payload):
    import subprocess
    import sys
    result = subprocess.run([sys.executable, "-B", str(Path(bridge.__file__))],
        input=json.dumps(payload).encode("utf-8"), capture_output=True, check=True, timeout=20)
    return json.loads(result.stdout)


@pytest.mark.parametrize("present", [False, True])
def test_cli_preserves_safe_absent_vs_unopenable_diagnostics(tmp_path, present):
    if present:
        (tmp_path / "sovereign.db").write_bytes(b"not a sqlite database")
    answer = cli_request(request(tmp_path, op="append", entry=entry()))
    assert answer == {"ok": False, "error": "journal store could not be opened" if present
                      else "no journal store (sovereign.db absent)"}
    assert str(tmp_path) not in json.dumps(answer)


def test_windows_share_denied_database_is_unreadable_over_cli(tmp_path):
    import ctypes
    import os
    from ctypes import wintypes
    if os.name != "nt":
        pytest.skip("Windows share-deny check; injected unreadability is tested on every host")
    seed(tmp_path)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    handle = create(str(tmp_path / "sovereign.db"), 0x80000000, 0, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value, ctypes.get_last_error()
    try:
        assert cli_request(request(tmp_path, op="append", entry=entry())) == {
            "ok": False, "error": "journal store could not be opened"}
    finally:
        assert close(handle)


def test_mutation_combined_guard_breaks_bootstrap_without_touching_source(tmp_path):
    import types
    source_path = Path(bridge.__file__)
    before = source_path.read_bytes()
    source = before.decode("utf-8")
    anchor = '    try:\n        with db.open("rb") as source:'
    assert source.count(anchor) == 1
    mutant = source.replace(anchor, '    if not db.is_file() or not (root / "cas").is_dir():\n'
        '        raise ValueError("journal store unavailable")\n' + anchor)
    namespace = {"__file__": str(source_path), "__name__": "journal_guard_mutant"}
    exec(compile(mutant, str(source_path), "exec"), namespace)
    store = SovereignStore(tmp_path / "sovereign.db")
    store.close()
    with pytest.raises(ValueError, match="journal store unavailable"):
        namespace["handle"](request(tmp_path, op="append", entry=entry()))
    # The same setup succeeds through production; the mutation is the sole difference.
    bridge.handle(request(tmp_path, op="append", entry=entry()))
    assert bridge.handle(request(tmp_path, op="entries")) == [entry()]
    assert source_path.read_bytes() == before
