"""Phase 2: process-manager error paths (spec-audit MAJOR-1/MAJOR-2) — fake processes,
deterministic, no real subprocesses."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from control_plane.nodes import (
    AppendOnlyEventLog,
    HeartbeatMonitor,
    HeartbeatPolicy,
    NodeProcessManager,
    NodeRegistry,
    NodeState,
    RegistrationRefused,
    RestartPolicy,
)
from control_plane.nodes import process_manager as pm_module


class FakeProc:
    """Popen stand-in: alive until killed; stdout empty so reader threads exit at once."""
    instances: list["FakeProc"] = []
    _next_pid = 41000

    def __init__(self, argv: list[str], **_: Any) -> None:
        FakeProc._next_pid += 1
        self.pid = FakeProc._next_pid
        self.argv = argv
        self.alive = True
        self.kill_calls = 0
        self.stdout = io.StringIO("")
        FakeProc.instances.append(self)

    def poll(self) -> int | None:
        return None if self.alive else 1

    def kill(self) -> None:
        self.kill_calls += 1
        self.alive = False

    def wait(self, timeout: float | None = None) -> int:
        return 0 if not self.alive else 0


class FailingKillProc(FakeProc):
    """kill() raises OSError for the first `fail_times` attempts, then works."""
    fail_times = 2

    def kill(self) -> None:
        self.kill_calls += 1
        if self.kill_calls <= self.fail_times:
            raise OSError("access denied (simulated)")
        self.alive = False


@pytest.fixture(autouse=True)
def _reset_instances() -> None:
    FakeProc.instances = []


def _manager(tmp_path: Path, proc_cls: type[FakeProc], max_restarts: int = 3) -> NodeProcessManager:
    log = AppendOnlyEventLog(tmp_path / "events.jsonl")
    manager = NodeProcessManager(
        NodeRegistry(log), log,
        HeartbeatPolicy(interval_s=0.1, miss_factor=3.0, spawn_grace_s=60.0),
        RestartPolicy(max_restarts=max_restarts, backoff_s=0.0),
    )
    # patch the module's Popen reference for this manager's spawns
    pm_module.subprocess.Popen = proc_cls  # type: ignore[misc]
    return manager


@pytest.fixture(autouse=True)
def _restore_popen() -> Any:
    import subprocess
    original = subprocess.Popen
    yield
    pm_module.subprocess.Popen = original  # type: ignore[misc]


def _events(tmp_path: Path) -> list[dict]:
    rows = []
    with (tmp_path / "events.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def test_failed_registration_reaps_the_spawned_process(tmp_path: Path) -> None:
    """MAJOR-1: Popen-then-register failure must not leave a live orphan."""
    manager = _manager(tmp_path, FakeProc)
    manager.spawn("n1", ["fake"])
    with pytest.raises(RegistrationRefused, match="duplicate"):
        manager.spawn("n1", ["fake"], incarnation=1)
    assert len(FakeProc.instances) == 2
    orphan_candidate = FakeProc.instances[1]
    assert orphan_candidate.alive is False, "process spawned for a refused registration must be reaped"
    assert orphan_candidate.kill_calls >= 1
    refusals = [e for e in _events(tmp_path) if e["kind"] == "registration_refused"]
    assert refusals and refusals[0]["data"]["reason"] == "duplicate registration"


def test_kill_failure_is_logged_and_retried_until_dead(tmp_path: Path) -> None:
    """MAJOR-2: a failed TerminateProcess is an auditable event and the reclaim retries."""
    manager = _manager(tmp_path, FailingKillProc, max_restarts=0)
    manager.spawn("n1", ["fake"])
    manager.registry.heartbeat("n1")
    manager.registry.transition("n1", NodeState.DISCONNECTED, reason="test: hang detected")
    proc = FakeProc.instances[0]

    manager.poll()  # retry pass 1: kill raises (1st failure) -> kill_failed logged
    assert proc.alive is True
    manager.poll()  # retry pass 2: kill raises (2nd failure)
    assert proc.alive is True
    manager.poll()  # retry pass 3: kill succeeds
    assert proc.alive is False
    manager.poll()  # observes the exit, records it

    kinds = [e["kind"] for e in _events(tmp_path)]
    assert kinds.count("kill_failed") == 2, "each failed kill must be on the record"
    assert "exit" in kinds, "the reclaim must complete once kill succeeds"
    assert manager.registry.get("n1", 1).state is NodeState.TERMINATED


def test_disconnect_reclaim_exit_is_unexpected_and_restarts(tmp_path: Path) -> None:
    """Spec-audit F6: the hang-reclaim path must count as unexpected and trigger restart."""
    manager = _manager(tmp_path, FakeProc, max_restarts=3)
    manager.spawn("n1", ["fake"])
    manager.registry.heartbeat("n1")
    manager.registry.transition("n1", NodeState.DISCONNECTED, reason="test: hang detected")
    manager.poll()  # kills (FakeProc dies immediately)
    manager.poll()  # observes exit -> unexpected -> restart reserved + respawned
    assert manager.registry.get("n1").incarnation == 2
    exits = [e for e in _events(tmp_path) if e["kind"] == "exit"]
    assert exits and exits[0]["data"]["expected"] is False


def test_monitor_never_touches_paused_nodes(tmp_path: Path) -> None:
    """Spec-audit F7: PAUSED is an operator action; the monitor must not reclaim it."""
    log = AppendOnlyEventLog(tmp_path / "events.jsonl")
    registry = NodeRegistry(log)
    registry.register("n1", "worker_reasoning", "mock", spawned_by_supervisor=True)
    registry.heartbeat("n1")
    registry.transition("n1", NodeState.PAUSED, reason="operator pause")
    monitor = HeartbeatMonitor(registry, HeartbeatPolicy(interval_s=0.1, miss_factor=3.0))
    last = registry.get("n1").last_heartbeat
    assert last is not None
    assert monitor.check(now=last + 9999.0) == []
    assert registry.get("n1").state is NodeState.PAUSED
