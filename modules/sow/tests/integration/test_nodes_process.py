"""Phase 2: real-process supervision — spawn, crash-restart, hang-disconnect, no orphans."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from control_plane.nodes import (
    AppendOnlyEventLog,
    HeartbeatPolicy,
    NodeProcessManager,
    NodeRegistry,
    NodeState,
    RestartPolicy,
    verify_file,
)

SIM = str(Path(__file__).resolve().parents[1] / "fixtures" / "sim_node.py")


def _pid_alive(pid: int) -> bool:
    import ctypes
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        return code.value == 259  # STILL_ACTIVE
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


@pytest.fixture()
def manager(tmp_path: Path) -> NodeProcessManager:
    log = AppendOnlyEventLog(tmp_path / "events.jsonl")
    m = NodeProcessManager(
        NodeRegistry(log), log,
        HeartbeatPolicy(interval_s=0.25, miss_factor=4.0, spawn_grace_s=8.0),
        RestartPolicy(max_restarts=2, backoff_s=0.1),
    )
    yield m
    leftovers = m.terminate_all()
    assert leftovers == []


def _wait_for(predicate, timeout_s: float = 15.0, manager: NodeProcessManager | None = None) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if manager is not None:
            manager.poll()
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError("condition not reached in time")


def test_spawn_reaches_ready_via_heartbeat(manager: NodeProcessManager) -> None:
    manager.spawn("n1", [sys.executable, SIM, "--hb-ms", "100"])
    _wait_for(lambda: manager.registry.get("n1").state is NodeState.READY, manager=manager)


def test_crash_is_unexpected_and_restarted_as_next_incarnation(manager: NodeProcessManager) -> None:
    manager.spawn("n1", [sys.executable, SIM, "--hb-ms", "100", "--crash-after-s", "1"])
    _wait_for(lambda: manager.registry.get("n1").incarnation == 2, manager=manager)
    assert manager.registry.get("n1", 1).state is NodeState.TERMINATED
    assert manager.registry.get("n1", 1).exit_code == 3
    assert manager.restarts_used("n1") == 1


def test_restart_budget_is_finite(manager: NodeProcessManager) -> None:
    manager.spawn("n1", [sys.executable, SIM, "--hb-ms", "100", "--crash-after-s", "0.5"])
    _wait_for(lambda: manager.restarts_used("n1") == 2, timeout_s=30.0, manager=manager)
    _wait_for(lambda: not manager.registry.alive(), timeout_s=30.0, manager=manager)  # exhausted, not respawned


def test_hang_becomes_disconnected_then_reclaimed(manager: NodeProcessManager) -> None:
    manager.spawn("n1", [sys.executable, SIM, "--hb-ms", "100", "--hang-after-s", "1"])
    _wait_for(lambda: manager.registry.get("n1").state is NodeState.READY, manager=manager)
    _wait_for(
        lambda: any(r.state is NodeState.TERMINATED for r in manager.registry.all_records() if r.incarnation == 1),
        timeout_s=30.0, manager=manager,
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only semantics (target platform); POSIX treats backslash/junctions/kernel APIs differently")
def test_terminate_all_leaves_no_orphans(tmp_path: Path) -> None:
    log = AppendOnlyEventLog(tmp_path / "events.jsonl")
    manager = NodeProcessManager(
        NodeRegistry(log), log,
        HeartbeatPolicy(interval_s=0.25, miss_factor=4.0), RestartPolicy(max_restarts=0),
    )
    for i in range(4):
        manager.spawn(f"n{i}", [sys.executable, SIM, "--hb-ms", "100"])
    pids = manager.managed_pids()
    assert len(pids) == 4
    assert manager.terminate_all() == []
    time.sleep(0.5)
    assert all(not _pid_alive(pid) for pid in pids)
    assert verify_file(tmp_path / "events.jsonl").ok
