"""CR-018 (startup evidence loses exit code + non-atomic write) and
CR-019 (relative state override escapes the intended state root)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

RELEASE_ROOT = Path(__file__).resolve().parents[4]
SHELL_SRC = RELEASE_ROOT / "shell" / "src"
for p in (str(RELEASE_ROOT), str(SHELL_SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

import startup_test  # noqa: E402
from shell.src import adapter as adapter_mod  # noqa: E402


# -- CR-018 ----------------------------------------------------------------
class _FakePh:
    def __init__(self, code):
        self._code = code

    @property
    def exit_code(self):
        return self._code


class _FakeSupervisor:
    def __init__(self, ph):
        self._ph = ph

    def get_process(self, _mid):
        return self._ph


class _FakeRunner:
    def __init__(self):
        self.stopped = False

    def start(self, env_overrides=None, readiness_override=None):
        return "READY", None

    def stop(self):
        self.stopped = True


class _Ring:
    def read_lines(self):
        return ["hello world"]


def test_cr018_exit_code_is_captured_before_handle_is_dropped(tmp_path, monkeypatch):
    monkeypatch.setenv("SWS_EVIDENCE_ROOT", str(tmp_path))
    monkeypatch.setattr(startup_test, "check_quota_guard", lambda *a, **k: None)
    monkeypatch.setattr(startup_test, "build_env", lambda *a, **k: {})
    ph = _FakePh(0)
    adapter = {"launch": {"argv": ["x"], "env_set": {}}, "readiness": {"kind": "none"}}
    result = startup_test.run_startup_test(
        "mod", adapter, _FakeSupervisor(ph), _Ring(), keep=False, runner=_FakeRunner())
    # Before the fix, ph was nulled before this read and the evidence recorded null.
    assert result["exit_code"] == 0, result


def test_cr018_evidence_written_atomically_no_temp_left(tmp_path):
    rec_path = tmp_path / "startup-tests" / "rec.json"
    result = {"module_id": "m", "exit_code": 0, "value": "ok"}
    # call the writer directly
    import types
    monkey = types.SimpleNamespace()
    saved = {}
    orig_record_path = startup_test._record_path
    startup_test._record_path = lambda mid: str(rec_path)
    try:
        startup_test._save_record(result, "m")
    finally:
        startup_test._record_path = orig_record_path
    assert rec_path.exists()
    data = json.loads(rec_path.read_text(encoding="utf-8"))
    assert data["exit_code"] == 0
    # no temporary residue left behind
    leftovers = [p.name for p in rec_path.parent.iterdir() if ".tmp-" in p.name]
    assert not leftovers, leftovers


# -- CR-019 ----------------------------------------------------------------
@pytest.fixture
def local_root(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("SOVEREIGN_WORKSPACE_STATE", raising=False)
    return tmp_path


def _set_override(monkeypatch, value):
    monkeypatch.setenv("SOVEREIGN_WORKSPACE_STATE", value)


def test_cr019_relative_traversal_is_rejected(local_root, monkeypatch):
    for bad in ("../escape", "../../escape", "a/../../escape", "..\\..\\escape", "a/../../../x"):
        _set_override(monkeypatch, bad)
        with pytest.raises(ValueError):
            adapter_mod.workspace_state_root()


def test_cr019_unc_and_device_paths_rejected(local_root, monkeypatch):
    for bad in (r"\\server\share", r"\\?\C:\x", r"\\.\PhysicalDrive0", "//server/share"):
        _set_override(monkeypatch, bad)
        with pytest.raises(ValueError):
            adapter_mod.workspace_state_root()


def test_cr019_contained_relative_override_is_accepted(local_root, monkeypatch):
    _set_override(monkeypatch, "sub/dir")
    root = adapter_mod.workspace_state_root()
    expected = os.path.realpath(os.path.join(str(local_root), "sub", "dir")).replace("\\", "/")
    assert root == os.path.abspath(expected).replace("\\", "/")


def test_cr019_absolute_override_accepted(local_root, monkeypatch, tmp_path):
    abs_target = tmp_path / "explicit_state"
    _set_override(monkeypatch, str(abs_target))
    root = adapter_mod.workspace_state_root()
    assert root == os.path.abspath(os.path.realpath(str(abs_target))).replace("\\", "/")


def test_cr019_no_override_uses_default(local_root, monkeypatch):
    root = adapter_mod.workspace_state_root()
    assert root.endswith("/" + adapter_mod.STATE_ROOT_DIRNAME)
