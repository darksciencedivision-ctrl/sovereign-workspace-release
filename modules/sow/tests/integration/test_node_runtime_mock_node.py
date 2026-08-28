"""Phase 3 exit criteria end-to-end: mock node loads role+permissions, produces a
schema-valid artifact, fails its local gate on every seeded defect, and cannot write
outside its workspace. Plus Job Object process-tree containment (invariant 29)."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from node_runtime import DEFECT_MODES, WorkspaceBinding, run_mock_node
from node_runtime.supervisor.containment import JobObjectContainment
from tests.unit.test_node_runtime_loaders import make_config


def make_ws(tmp_path: Path, refusals: list) -> WorkspaceBinding:
    root = tmp_path / "ws"
    root.mkdir(exist_ok=True)
    return WorkspaceBinding(root, "n-mock", on_refusal=lambda kind, **data: refusals.append((kind, data)))


def test_clean_run_passes_gate_and_stays_inside(tmp_path: Path) -> None:
    refusals: list = []
    result = run_mock_node("n-mock", make_config(tmp_path), make_ws(tmp_path, refusals))
    assert result.gate.passed, result.gate.reasons()
    assert result.artifact_path is not None and result.artifact_path.is_file()
    assert (tmp_path / "ws" / "out" / "structured_output.json").is_file()
    assert refusals == []
    assert result.config.hashes  # provenance pinning available


@pytest.mark.parametrize("defect", [d for d in DEFECT_MODES if d not in ("none", "workspace_escape")])
def test_every_seeded_defect_fails_the_gate(tmp_path: Path, defect: str) -> None:
    refusals: list = []
    result = run_mock_node("n-mock", make_config(tmp_path), make_ws(tmp_path, refusals), defect=defect)
    assert not result.gate.passed, f"defect {defect} must fail the local gate"
    assert result.gate.reasons()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only semantics (target platform); POSIX treats backslash/junctions/kernel APIs differently")
def test_workspace_escape_is_refused_and_logged(tmp_path: Path) -> None:
    refusals: list = []
    result = run_mock_node("n-mock", make_config(tmp_path), make_ws(tmp_path, refusals), defect="workspace_escape")
    assert result.escape_attempted and result.escape_refused
    assert refusals and refusals[0][0] == "workspace_escape_refused"
    assert not (tmp_path / "outside_the_fence.md").exists()


def _pid_alive(pid: int) -> bool:
    import ctypes
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        return code.value == 259
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only semantics (target platform); POSIX treats backslash/junctions/kernel APIs differently")
def test_job_object_kills_grandchildren_on_close(tmp_path: Path) -> None:
    """Spawn a child that spawns a grandchild; closing the job must kill both."""
    pid_file = tmp_path / "grandchild_pid.txt"
    child_code = (
        "import subprocess, sys, time, pathlib;"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)']);"
        f"pathlib.Path(r'{pid_file}').write_text(str(p.pid));"
        "time.sleep(600)"
    )
    child = subprocess.Popen([sys.executable, "-c", child_code])
    job = JobObjectContainment(name=None)
    job.assign(child.pid)
    deadline = time.monotonic() + 15
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert pid_file.exists(), "grandchild never started"
    grandchild_pid = int(pid_file.read_text())
    assert _pid_alive(child.pid) and _pid_alive(grandchild_pid)

    job.close()  # KILL_ON_JOB_CLOSE must take the whole tree
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and (_pid_alive(child.pid) or _pid_alive(grandchild_pid)):
        time.sleep(0.1)
    assert not _pid_alive(child.pid), "child survived job close"
    assert not _pid_alive(grandchild_pid), "grandchild survived job close (tree not contained)"
