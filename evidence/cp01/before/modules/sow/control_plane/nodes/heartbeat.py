"""Heartbeat monitor: liveness policy over the registry (Plan section 7-P2).

Pure policy object — `check(now)` is deterministic given the registry snapshot, so the
missed-heartbeat path is unit-testable without wall-clock sleeps. A node whose heartbeat
is older than `interval_s * miss_factor` is marked DISCONNECTED (once); resumed
heartbeats re-enter READY via the registry. SPAWNING nodes get `spawn_grace_s` before
they are expected to beat at all.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from .registry import NodeRegistry
from .states import NodeState


@dataclass(frozen=True)
class HeartbeatPolicy:
    interval_s: float
    miss_factor: float = 3.0
    spawn_grace_s: float = 10.0


class HeartbeatMonitor:
    def __init__(self, registry: NodeRegistry, policy: HeartbeatPolicy) -> None:
        self._registry = registry
        self._policy = policy
        self._spawn_seen: dict[tuple[str, int], float] = {}

    def check(self, now: float | None = None) -> list[tuple[str, int]]:
        """Mark overdue nodes DISCONNECTED; return the keys newly disconnected."""
        now = time.monotonic() if now is None else now
        deadline = self._policy.interval_s * self._policy.miss_factor
        newly_disconnected: list[tuple[str, int]] = []
        live_keys = {record.key for record in self._registry.alive()}
        for key in list(self._spawn_seen):
            if key not in live_keys:
                del self._spawn_seen[key]  # bounded: grace clocks die with their incarnation
        for record in self._registry.alive():
            if record.state in (NodeState.DISCONNECTED, NodeState.PAUSED):
                continue
            if record.last_heartbeat is None:
                first_seen = self._spawn_seen.setdefault(record.key, now)
                if now - first_seen < self._policy.spawn_grace_s:
                    continue
                overdue = True
            else:
                overdue = (now - record.last_heartbeat) > deadline
            if overdue:
                self._registry.transition(
                    record.node_id, NodeState.DISCONNECTED, incarnation=record.incarnation,
                    reason=f"heartbeat overdue (> {deadline:.3f}s)",
                )
                newly_disconnected.append(record.key)
        return newly_disconnected
