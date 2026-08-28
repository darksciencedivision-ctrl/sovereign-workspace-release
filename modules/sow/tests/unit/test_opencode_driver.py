"""Phase 14C `.worktree` (unit): deterministic proof of the OpenCode worktree drive orchestration.

No real `opencode` spawn — a scripted fake `Runner` stands in for the subprocess so every
governance property is proven reliably (the live drive is the integration suite). What these
prove, fail-closed:
  - scoped context: EXACTLY the one assigned MCP entry is read (invariant 8), never a store sweep;
  - isolated worktree modification (Phase 10): the drive's changes are read from the worktree's own
    git status; an out-of-worktree modification is detected + logged (escaped=True);
  - U30: a session-local OPENCODE_CONFIG is written (loopback Ollama only) and pointed at, and a
    non-loopback baseURL / non-local model is refused;
  - §2.2/§2.3: the child env is credential-scrubbed and the model is pinned to ollama/*;
  - "tests run": the worktree's tests execute after the drive, pass/fail reported honestly.
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest

from adapters.coding.opencode.driver import (
    DEFAULT_OLLAMA_BASE_URL,
    DriveRefused,
    OpenCodeDriver,
    RunOutcome,
    write_scoped_opencode_config,
)
from adapters.coding.opencode.harness import ModelNotLocal, MockOpenCodeHarness
from node_runtime.supervisor.opencode_spawn import spawn_opencode_harness
from node_runtime.workspace.worktree import WorktreeManager

_MODELS = ["nomic-embed-text:latest", "devstral-small-2:latest", "qwen3:14b"]
_CODER = "devstral-small-2:latest"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path):
    base = tmp_path / "proj"
    base.mkdir()
    _git(base, "init", "-b", "main")
    _git(base, "config", "user.email", "op@sovereign.local")
    _git(base, "config", "user.name", "operator")
    (base / "README.md").write_text("trunk\n", encoding="utf-8")
    _git(base, "add", "-A")
    _git(base, "commit", "-m", "initial")
    return base


class _FakeMcp:
    """Records every entry_id fetched, so a test can assert the driver reads ONLY the scoped one."""

    def __init__(self, entries: dict[str, bytes]) -> None:
        self._entries = entries
        self.fetched: list[str] = []

    def call(self, op: str, **kw):
        assert op == "get_content"  # the driver's scoped read uses only this op
        entry_id = kw["entry_id"]
        self.fetched.append(entry_id)
        return {"content_b64": base64.b64encode(self._entries[entry_id]).decode("ascii")}


def _supervised(repo: Path, *, coder=True):
    return spawn_opencode_harness(
        mcp_client=object(), node_id="coder-A", permission_profile_id="pp-coding",
        workspace_root=str(repo), harness=MockOpenCodeHarness(version="1.17.13"),
        available_models=_MODELS if coder else [], require_coder_model=coder)


def _driver(repo, mcp, tmp_path, *, runner, on_event=None, coder=True):
    mgr = WorktreeManager(repo)
    wt = mgr.create("coder-A")
    return OpenCodeDriver(
        _supervised(repo, coder=coder), wt, mcp, base_repo=repo,
        session_dir=tmp_path / "session", runner=runner, on_event=on_event), wt


def _edit_runner(rel_path: str, content: str):
    """A fake OpenCode that deterministically edits a file in its --dir worktree and emits a JSON
    tool event, exactly as `opencode run --format json` would when a tool executes."""
    def run(argv, *, cwd, env, timeout):
        assert "--dir" in argv and "--auto" in argv  # scoped + non-interactive
        assert "-m" in argv and argv[argv.index("-m") + 1].startswith("ollama/")  # local pin
        assert env.get("OPENCODE_CONFIG")  # U30: config pointer present
        (Path(cwd) / rel_path).parent.mkdir(parents=True, exist_ok=True)
        (Path(cwd) / rel_path).write_text(content, encoding="utf-8")
        stream = json.dumps({"type": "tool", "name": "edit", "filePath": rel_path}) + "\n"
        return RunOutcome(returncode=0, stdout=stream, stderr="> build\n")
    return run


# ---- scoped context: only the assigned entry is read (invariant 8) -------------------------

def test_drive_reads_only_scoped_entry_and_edits_worktree(repo, tmp_path):
    mcp = _FakeMcp({"m-obj": b"Add a subtract() to calc.py", "m-other": b"unrelated project memory"})
    events = []
    drv, wt = _driver(repo, mcp, tmp_path, runner=_edit_runner("calc.py", "def add(a,b): return a+b\n"),
                      on_event=lambda k, **d: events.append((k, d)))
    objective = drv.read_scoped_objective("m-obj")
    assert objective == "Add a subtract() to calc.py"
    res = drv.drive(objective)
    assert mcp.fetched == ["m-obj"]  # ONLY the scoped entry — no store sweep, no full transcript
    assert res.drove and res.edit_completed and "calc.py" in res.changed_files
    assert res.escaped is False and res.tool_events >= 1
    assert res.model == "ollama/devstral-small-2:latest"
    assert any(k == "scoped_context_read" for k, _ in events)
    assert any(k == "drive_done" for k, _ in events)


def test_missing_or_empty_scoped_entry_fails_closed(repo, tmp_path):
    mcp = _FakeMcp({"m-empty": b""})
    drv, _ = _driver(repo, mcp, tmp_path, runner=_edit_runner("x.py", "x=1\n"))
    with pytest.raises(DriveRefused):
        drv.read_scoped_objective("")            # no assignment
    with pytest.raises(DriveRefused):
        drv.read_scoped_objective("m-empty")     # entry with no content


# ---- U30: session-local config isolation ---------------------------------------------------

def test_scoped_config_written_loopback_only_and_pointed_to(repo, tmp_path):
    mcp = _FakeMcp({"m-obj": b"edit"})
    drv, _ = _driver(repo, mcp, tmp_path, runner=_edit_runner("calc.py", "def add(a,b): return a+b\n"))
    res = drv.drive("edit")
    cfg_path = Path(res.config_path)
    assert cfg_path.is_file() and cfg_path.parent == (tmp_path / "session")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert list(cfg["provider"].keys()) == ["ollama"]  # ONLY the local provider — no cloud
    assert cfg["provider"]["ollama"]["options"]["baseURL"] == DEFAULT_OLLAMA_BASE_URL
    assert "devstral-small-2:latest" in cfg["provider"]["ollama"]["models"]


def test_config_refuses_non_loopback_baseurl_and_non_local_model(tmp_path):
    with pytest.raises(DriveRefused):  # off-box routing refused (§2.3)
        write_scoped_opencode_config(tmp_path, model=_CODER, base_url="http://10.0.0.5:11434/v1")
    with pytest.raises(ModelNotLocal):  # cloud model refused (§2.3)
        write_scoped_opencode_config(tmp_path, model="openai/gpt-4o")


def test_build_env_scrubs_credentials_and_sets_config(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic")
    mcp = _FakeMcp({"m-obj": b"edit"})
    drv, _ = _driver(repo, mcp, tmp_path, runner=_edit_runner("calc.py", "x=1\n"))
    cfg = write_scoped_opencode_config(tmp_path / "session", model=_CODER)
    env = drv.build_env(cfg)
    assert "OPENAI_API_KEY" not in env and "ANTHROPIC_API_KEY" not in env  # §2.2 scrub
    assert env["OPENCODE_CONFIG"] == str(cfg)                              # U30 pointer set
    assert "sk-secret" not in "".join(env.values())


# ---- isolated worktree modification: an out-of-worktree change is detected + logged --------

def test_out_of_worktree_modification_flagged_escaped(repo, tmp_path):
    def escaping_runner(argv, *, cwd, env, timeout):
        (repo / "escaped.py").write_text("leaked = True\n", encoding="utf-8")  # OUTSIDE the worktree
        return RunOutcome(returncode=0, stdout="", stderr="")
    mcp = _FakeMcp({"m-obj": b"edit"})
    events = []
    drv, _ = _driver(repo, mcp, tmp_path, runner=escaping_runner,
                     on_event=lambda k, **d: events.append((k, d)))
    res = drv.drive("edit")
    assert res.escaped is True
    assert any(k == "drive_escape_detected" for k, _ in events)
    (repo / "escaped.py").unlink()  # clean the temp repo


def test_unverifiable_containment_fails_closed(repo, tmp_path):
    """MAJOR-1: if the base-trunk escape check cannot run (base_repo is not a git repo), the drive
    must NOT read as 'confined' — escaped is forced True and containment_verified False (fail
    closed, Buildout §4), never a clean-looking empty diff."""
    not_a_repo = tmp_path / "bogus"
    not_a_repo.mkdir()
    mgr = WorktreeManager(repo)
    wt = mgr.create("coder-A")
    mcp = _FakeMcp({"m-obj": b"edit"})
    drv = OpenCodeDriver(_supervised(repo), wt, mcp, base_repo=not_a_repo,
                         session_dir=tmp_path / "session",
                         runner=_edit_runner("calc.py", "x=1\n"))
    res = drv.drive("edit")
    assert res.containment_verified is False and res.escaped is True


def test_driver_refuses_unsupervised_context(repo, tmp_path):
    """MINOR-4: a hand-built SupervisedOpenCode whose context was not spawned by the supervisor is
    refused (invariant 2 / never trust the harness), not silently driven."""
    import dataclasses
    from adapters.coding.opencode.driver import DriveRefused as _DR
    sup = _supervised(repo)
    forged = dataclasses.replace(
        sup, context=dataclasses.replace(sup.context, spawned_by_supervisor=False))
    mgr = WorktreeManager(repo)
    wt = mgr.create("coder-A")
    with pytest.raises(_DR):
        OpenCodeDriver(forged, wt, _FakeMcp({"m-obj": b"x"}), base_repo=repo,
                       session_dir=tmp_path / "session", runner=_edit_runner("x.py", "x=1\n"))


def test_no_edit_is_honestly_reported_not_faked(repo, tmp_path):
    """A drive where the (flaky) model changes nothing must report edit_completed=False — the
    driver never invents an edit. Mirrors the real local-model flakiness deterministically."""
    def noop_runner(argv, *, cwd, env, timeout):
        return RunOutcome(returncode=0, stdout="I could not complete the edit.", stderr="")
    mcp = _FakeMcp({"m-obj": b"edit"})
    drv, _ = _driver(repo, mcp, tmp_path, runner=noop_runner)
    res = drv.drive("edit")
    assert res.drove is True and res.edit_completed is False and res.changed_files == ()


def test_timeout_marks_not_drove(repo, tmp_path):
    def timeout_runner(argv, *, cwd, env, timeout):
        return RunOutcome(returncode=124, stdout="", stderr="", timed_out=True)
    mcp = _FakeMcp({"m-obj": b"edit"})
    drv, _ = _driver(repo, mcp, tmp_path, runner=timeout_runner)
    res = drv.drive("edit")
    assert res.timed_out is True and res.drove is False


# ---- "tests run": the worktree's tests execute after the drive -----------------------------

def test_worktree_tests_run_and_pass_after_a_correct_edit(repo, tmp_path):
    mcp = _FakeMcp({"m-obj": b"implement add"})
    drv, wt = _driver(repo, mcp, tmp_path,
                      runner=_edit_runner("calc.py", "def add(a, b):\n    return a + b\n"))
    res = drv.drive("implement add")
    assert res.edit_completed
    out = drv.run_worktree_tests([sys.executable, "-c", "import calc; assert calc.add(2, 3) == 5"])
    assert out.ran and out.passed and out.returncode == 0


def test_worktree_tests_report_failure_honestly(repo, tmp_path):
    mcp = _FakeMcp({"m-obj": b"implement add"})
    drv, wt = _driver(repo, mcp, tmp_path,
                      runner=_edit_runner("calc.py", "def add(a, b):\n    return a - b\n"))  # bug
    drv.drive("implement add")
    out = drv.run_worktree_tests([sys.executable, "-c", "import calc; assert calc.add(2, 3) == 5"])
    assert out.ran and out.passed is False and out.returncode != 0


def test_run_tests_refuses_empty_command(repo, tmp_path):
    mcp = _FakeMcp({"m-obj": b"edit"})
    drv, _ = _driver(repo, mcp, tmp_path, runner=_edit_runner("x.py", "x=1\n"))
    with pytest.raises(DriveRefused):
        drv.run_worktree_tests([])  # 'tests run' cannot be satisfied vacuously


# ---- fail closed: no coder model to drive --------------------------------------------------

def test_driver_refuses_construction_without_coder_model(repo, tmp_path):
    mcp = _FakeMcp({"m-obj": b"edit"})
    with pytest.raises(DriveRefused):
        _driver(repo, mcp, tmp_path, runner=_edit_runner("x.py", "x=1\n"), coder=False)
