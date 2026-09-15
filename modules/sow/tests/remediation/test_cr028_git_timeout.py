"""CR-028 — every SOW git invocation goes through one bounded, non-interactive wrapper."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

import node_runtime.workspace.git_runner as gr  # via sow root on sys.path (conftest)


def test_cr028_noninteractive_env_blocks_credential_prompts():
    # A hung credential/askpass prompt is the classic no-timeout hang; the wrapper's env forbids it.
    assert gr._NONINTERACTIVE_ENV["GIT_TERMINAL_PROMPT"] == "0"
    assert gr._NONINTERACTIVE_ENV["GCM_INTERACTIVE"] == "Never"
    assert gr._NONINTERACTIVE_ENV["GIT_ASKPASS"] == "echo"


def test_cr028_timeout_raises_and_kills_process_tree(monkeypatch):
    killed = {}

    class _FakeProc:
        pid = 4242

        def communicate(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd="git", timeout=timeout)

        def kill(self):
            killed["killed"] = True

    monkeypatch.setattr(gr.subprocess, "Popen", lambda *a, **k: _FakeProc())
    monkeypatch.setattr(gr, "_kill_tree", lambda proc: killed.setdefault("pid", proc.pid))

    with pytest.raises(gr.GitTimeout):
        gr.run_git(Path("."), "status", timeout=0.5)
    assert killed.get("pid") == 4242, "process tree was not killed on timeout"


def _have_git():
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=10)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


@pytest.mark.skipif(not _have_git(), reason="git not available")
def test_cr028_success_path_runs_real_git(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True, timeout=30)
    (tmp_path / "f.txt").write_text("hi", encoding="utf-8")
    rc, out, err = gr.run_git(tmp_path, "add", "f.txt")
    assert rc == 0, err
    rc, out, err = gr.run_git(tmp_path, "-c", "user.email=t@t", "-c", "user.name=t",
                              "commit", "-m", "x")
    assert rc == 0, err
    rc, out, err = gr.run_git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD")
    assert rc == 0 and out.strip()  # a branch name
    rc, out, err = gr.run_git(tmp_path, "status", "-z", "--porcelain", text=False)
    assert rc == 0 and isinstance(out, bytes)


@pytest.mark.skipif(not _have_git(), reason="git not available")
def test_cr028_sleeping_hook_times_out_and_is_killed(tmp_path):
    # A pre-commit hook that hangs must not hang orchestration: the wrapper times out and kills the
    # whole git tree (including the sleeping hook), rather than waiting forever.
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True, timeout=30)
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "pre-commit").write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8", newline="\n")
    (tmp_path / "f.txt").write_text("hi", encoding="utf-8")
    gr.run_git(tmp_path, "add", "f.txt")
    start = time.monotonic()
    with pytest.raises(gr.GitTimeout):
        gr.run_git(tmp_path, "-c", "user.email=t@t", "-c", "user.name=t",
                   "commit", "-m", "x", timeout=2.0)
    elapsed = time.monotonic() - start
    assert elapsed < 15.0, f"commit with a sleeping hook took {elapsed:.1f}s (not bounded)"
