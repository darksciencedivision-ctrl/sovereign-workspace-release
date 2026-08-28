"""Phase 2: registry semantics — I-C1 refusal, pause/resume, heartbeat recovery, exits."""
from __future__ import annotations

from pathlib import Path

import pytest

from control_plane.nodes import (
    AppendOnlyEventLog,
    HeartbeatMonitor,
    HeartbeatPolicy,
    IllegalTransition,
    NodeRegistry,
    NodeState,
    RegistrationRefused,
    verify_file,
)


@pytest.fixture()
def registry(tmp_path: Path) -> NodeRegistry:
    return NodeRegistry(AppendOnlyEventLog(tmp_path / "events.jsonl"))


def test_unsupervised_registration_refused_and_logged(registry: NodeRegistry, tmp_path: Path) -> None:
    with pytest.raises(RegistrationRefused, match="I-C1"):
        registry.register("naked", "worker_reasoning", "mock", spawned_by_supervisor=False)
    result = verify_file(tmp_path / "events.jsonl")
    assert result.ok and result.rows == 1  # the refusal itself is on the record


def test_duplicate_incarnation_refused(registry: NodeRegistry) -> None:
    registry.register("n1", "worker_reasoning", "mock", spawned_by_supervisor=True)
    with pytest.raises(RegistrationRefused, match="duplicate"):
        registry.register("n1", "worker_reasoning", "mock", spawned_by_supervisor=True)


def test_first_heartbeat_promotes_spawning_to_ready(registry: NodeRegistry) -> None:
    registry.register("n1", "worker_reasoning", "mock", spawned_by_supervisor=True)
    registry.heartbeat("n1")
    assert registry.get("n1").state is NodeState.READY


def test_pause_resumes_only_to_interrupted_state(registry: NodeRegistry) -> None:
    registry.register("n1", "worker_reasoning", "mock", spawned_by_supervisor=True)
    registry.heartbeat("n1")
    registry.transition("n1", NodeState.ASSIGNED, reason="test")
    registry.transition("n1", NodeState.BUSY, reason="test")
    registry.transition("n1", NodeState.PAUSED, reason="operator pause")
    with pytest.raises(IllegalTransition):
        registry.transition("n1", NodeState.READY, reason="wrong resume")
    registry.transition("n1", NodeState.BUSY, reason="resume")
    assert registry.get("n1").state is NodeState.BUSY


def test_heartbeat_recovers_disconnected_to_ready(registry: NodeRegistry) -> None:
    registry.register("n1", "worker_reasoning", "mock", spawned_by_supervisor=True)
    registry.heartbeat("n1")
    registry.transition("n1", NodeState.DISCONNECTED, reason="test")
    registry.heartbeat("n1")
    assert registry.get("n1").state is NodeState.READY


def test_monitor_disconnects_overdue_node_once(registry: NodeRegistry) -> None:
    registry.register("n1", "worker_reasoning", "mock", spawned_by_supervisor=True)
    registry.heartbeat("n1")
    monitor = HeartbeatMonitor(registry, HeartbeatPolicy(interval_s=0.1, miss_factor=3.0))
    last = registry.get("n1").last_heartbeat
    assert last is not None
    assert monitor.check(now=last + 0.05) == []
    assert monitor.check(now=last + 1.0) == [("n1", 1)]
    assert registry.get("n1").state is NodeState.DISCONNECTED
    assert monitor.check(now=last + 2.0) == []  # not re-flagged


def test_spawn_grace_prevents_premature_disconnect(registry: NodeRegistry) -> None:
    registry.register("n1", "worker_reasoning", "mock", spawned_by_supervisor=True)
    monitor = HeartbeatMonitor(registry, HeartbeatPolicy(interval_s=0.1, miss_factor=3.0, spawn_grace_s=5.0))
    assert monitor.check(now=100.0) == []       # first sighting starts the grace clock
    assert monitor.check(now=104.0) == []       # inside grace
    assert monitor.check(now=106.0) == [("n1", 1)]  # grace expired, never beat


def test_unexpected_exit_terminates_and_logs(registry: NodeRegistry, tmp_path: Path) -> None:
    registry.register("n1", "worker_reasoning", "mock", spawned_by_supervisor=True)
    registry.heartbeat("n1")
    record = registry.record_exit("n1", 1, 3, expected=False)
    assert record.state is NodeState.TERMINATED
    assert record.exit_code == 3
    assert verify_file(tmp_path / "events.jsonl").ok


def test_restart_registers_next_incarnation(registry: NodeRegistry) -> None:
    registry.register("n1", "worker_reasoning", "mock", spawned_by_supervisor=True)
    registry.record_exit("n1", 1, 3, expected=False)
    registry.register("n1", "worker_reasoning", "mock", spawned_by_supervisor=True, incarnation=2)
    assert registry.get("n1").incarnation == 2
    assert registry.get("n1", 1).state is NodeState.TERMINATED


# --- W-71: paused_from was memory-only; a rehydrated PAUSED node could resume to any table-legal state

def _spawn_ready_pause(tmp_path: Path, pause: bool):
    log_path = tmp_path / "events.jsonl"
    a = NodeRegistry(AppendOnlyEventLog(log_path))
    a.register("n1", "worker_reasoning", "mock", spawned_by_supervisor=True)
    a.heartbeat("n1")  # SPAWNING -> READY
    if pause:
        a.transition("n1", NodeState.PAUSED, reason="operator pause")
    a._log.close()
    return log_path


def _rehydrate_paused(log_path: Path) -> NodeRegistry:
    from control_plane.nodes.registry import NodeRecord
    b = NodeRegistry(AppendOnlyEventLog(log_path))
    record = NodeRecord(node_id="n1", incarnation=1, node_class="worker_reasoning",
                        adapter="mock", state=NodeState.PAUSED)  # paused_from LOST, as cross-process
    b.rehydrate(record)
    return b


def test_rehydrated_paused_node_resumes_only_to_the_recorded_state(tmp_path: Path) -> None:
    """Red 1: the interrupted state IS in the log (the to=PAUSED row carries frm); the resume
    guard must read it back instead of trusting in-process memory that died with the process."""
    log_path = _spawn_ready_pause(tmp_path, pause=True)
    b = _rehydrate_paused(log_path)
    with pytest.raises(IllegalTransition):
        b.transition("n1", NodeState.ASSIGNED, reason="wrong resume after rehydrate")
    b.transition("n1", NodeState.READY, reason="resume to the recorded state")
    assert b.get("n1").state is NodeState.READY


def test_resume_refuses_fail_closed_when_the_log_has_no_pause_row(tmp_path: Path) -> None:
    """Red 2: a PAUSED record whose history carries no pause row cannot ground ANY resume;
    refusing beats guessing."""
    log_path = _spawn_ready_pause(tmp_path, pause=False)
    b = _rehydrate_paused(log_path)
    with pytest.raises(IllegalTransition):
        b.transition("n1", NodeState.BUSY, reason="no recorded interruption to resume")
