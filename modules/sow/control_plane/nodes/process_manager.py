"""Node process manager: spawn, watch, crash-detect, restart (Plan section 7-P2).

Owns real OS processes for nodes; the registry stays the single state authority.
Liveness signal = "HB" lines on the child's stdout (pipe read doubles as a supervision
channel). Crash detection = process exit without a manager-issued terminate; restart
policy spawns the NEXT incarnation (same node_id) up to max_restarts, never resurrecting
a TERMINATED incarnation. `terminate_all` is the no-orphan guarantee and is verified by
the soak driver against the OS process table.
"""
from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field

from .event_log import AppendOnlyEventLog
from .heartbeat import HeartbeatMonitor, HeartbeatPolicy
from .registry import NodeRecord, NodeRegistry
from .states import NodeState


@dataclass(frozen=True)
class RestartPolicy:
    max_restarts: int = 3
    backoff_s: float = 0.5


@dataclass
class _Managed:
    record: NodeRecord
    process: subprocess.Popen[str]
    reader: threading.Thread
    manager_killed: bool = False
    restarts_used: int = 0
    spawn_argv: list[str] = field(default_factory=list)


class NodeProcessManager:
    def __init__(
        self,
        registry: NodeRegistry,
        log: AppendOnlyEventLog,
        heartbeat_policy: HeartbeatPolicy,
        restart_policy: RestartPolicy = RestartPolicy(),
    ) -> None:
        self._registry = registry
        self._log = log
        self._monitor = HeartbeatMonitor(registry, heartbeat_policy)
        self._restart_policy = restart_policy
        self._lock = threading.RLock()
        self._managed: dict[tuple[str, int], _Managed] = {}
        self._restarts: dict[str, int] = {}
        self._stopping = False

    # -- spawning -------------------------------------------------------------
    def spawn(self, node_id: str, argv: list[str], *, node_class: str = "worker_reasoning", adapter: str = "mock", incarnation: int = 1) -> NodeRecord:
        with self._lock:
            process = subprocess.Popen(  # noqa: S603 - argv is manager-controlled, no shell
                argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                encoding="utf-8", errors="replace",  # undecodable child bytes must not kill the reader
            )
            try:
                record = self._registry.register(
                    node_id, node_class, adapter,
                    spawned_by_supervisor=True, pid=process.pid, incarnation=incarnation, argv=argv,
                )
            except Exception:
                # registration failed after the OS process started: reap it or it is an
                # orphan invisible to terminate_all (spec-audit MAJOR-1; exit criterion
                # "no orphan processes" applies to error paths too)
                try:
                    process.kill()
                    process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                raise
            reader = threading.Thread(target=self._read_stdout, args=(record, process), daemon=True, name=f"reader-{node_id}#{incarnation}")
            managed = _Managed(record=record, process=process, reader=reader, spawn_argv=list(argv))
            self._managed[record.key] = managed
            reader.start()
            return record

    def _read_stdout(self, record: NodeRecord, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if line == "HB":
                try:
                    self._registry.heartbeat(record.node_id, incarnation=record.incarnation)
                except KeyError:
                    return
            elif line:
                self._log.append("node_output", node_id=record.node_id, incarnation=record.incarnation, line=line[:500])

    # -- supervision loop -----------------------------------------------------
    def poll(self) -> None:
        """One supervision pass: exits, heartbeat deadlines, disconnect-kill, restarts."""
        restarts: list[_Managed] = []
        with self._lock:
            for key, managed in list(self._managed.items()):
                code = managed.process.poll()
                if code is not None:
                    del self._managed[key]
                    expected = managed.manager_killed or self._stopping
                    self._registry.record_exit(key[0], key[1], code, expected=expected)
                    if not expected and self._reserve_restart(key[0], managed):
                        restarts.append(managed)
            for node_id, incarnation in self._monitor.check():
                managed = self._managed.get((node_id, incarnation))
                if managed is not None and not self._stopping:
                    # hung process: reclaim it and let restart policy decide (fail closed)
                    self._log.append("disconnect_kill", node_id=node_id, incarnation=incarnation, pid=managed.process.pid)
                    managed.manager_killed = False  # unexpected from the node's viewpoint
                    self._kill(managed)
            if not self._stopping:
                # kill can fail (spec-audit MAJOR-2): retry reclaim of any DISCONNECTED
                # node whose process is still alive until poll() observes its exit
                for key, managed in list(self._managed.items()):
                    record = self._registry.get(key[0], key[1])
                    if record.state is NodeState.DISCONNECTED and managed.process.poll() is None:
                        self._kill(managed)
        # backoff + respawn happen OUTSIDE the lock (spec-audit MINOR-3: no sleeps under lock)
        for managed in restarts:
            time.sleep(self._restart_policy.backoff_s)
            self.spawn(
                managed.record.node_id, managed.spawn_argv,
                node_class=managed.record.node_class, adapter=managed.record.adapter,
                incarnation=managed.record.incarnation + 1,
            )

    def _reserve_restart(self, node_id: str, managed: _Managed) -> bool:
        used = self._restarts.get(node_id, 0)
        if used >= self._restart_policy.max_restarts:
            self._log.append("restart_exhausted", node_id=node_id, incarnation=managed.record.incarnation, restarts_used=used)
            return False
        self._restarts[node_id] = used + 1
        self._log.append("restart", node_id=node_id, incarnation=managed.record.incarnation + 1, previous=managed.record.incarnation, restarts_used=used + 1)
        return True

    # -- induced faults + teardown ---------------------------------------------
    def kill_node(self, node_id: str, *, incarnation: int | None = None, expected: bool = True) -> None:
        with self._lock:
            record = self._registry.get(node_id, incarnation)
            managed = self._managed.get(record.key)
            if managed is None:
                return
            managed.manager_killed = expected
            self._log.append("kill", node_id=record.node_id, incarnation=record.incarnation, pid=managed.process.pid, expected=expected)
            self._kill(managed)

    def _kill(self, managed: _Managed) -> bool:
        """Attempt to kill; a failure is an auditable event, never silent (fail closed)."""
        try:
            managed.process.kill()
            return True
        except OSError as exc:
            self._log.append(
                "kill_failed", node_id=managed.record.node_id, incarnation=managed.record.incarnation,
                pid=managed.process.pid, error=str(exc),
            )
            return False

    def terminate_all(self, timeout_s: float = 10.0) -> list[int]:
        """Kill every managed process; return pids still alive after the deadline (must be [])."""
        with self._lock:
            self._stopping = True
            targets = list(self._managed.values())
            for managed in targets:
                managed.manager_killed = True
                self._kill(managed)
        deadline = time.monotonic() + timeout_s
        for managed in targets:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                managed.process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                pass
        self.poll()
        return [m.process.pid for m in targets if m.process.poll() is None]

    # -- introspection ----------------------------------------------------------
    def managed_pids(self) -> list[int]:
        with self._lock:
            return [m.process.pid for m in self._managed.values()]

    def restarts_used(self, node_id: str) -> int:
        return self._restarts.get(node_id, 0)

    @property
    def registry(self) -> NodeRegistry:
        return self._registry

    @property
    def states(self) -> dict[str, str]:
        return {f"{r.node_id}#{r.incarnation}": r.state.value for r in self._registry.all_records()}
