"""Capability registry (Plan §9.7; I-SC1).

Maps registered node ids to their capability descriptors. Scheduling is by *capability*,
never by vendor/model name — the registry is the only place node identity meets capability,
and the resolver queries descriptors, not names. Load is tracked so the resolver can rank.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RegisteredNode:
    node_id: str
    capabilities: list[dict[str, Any]]
    locality: str                     # local | frontier
    cost_class: str                   # local | subscription
    offline_profile_eligible: bool
    active_tasks: int = 0
    benchmark_score: float = 0.5      # placeholder until Track E/R10 (Phase 6); ranking input


class CapabilityRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._nodes: dict[str, RegisteredNode] = {}

    def register(self, node_id: str, capabilities: list[dict[str, Any]], *, locality: str,
                 cost_class: str, offline_profile_eligible: bool, benchmark_score: float = 0.5) -> None:
        with self._lock:
            self._nodes[node_id] = RegisteredNode(
                node_id=node_id, capabilities=list(capabilities), locality=locality,
                cost_class=cost_class, offline_profile_eligible=offline_profile_eligible,
                benchmark_score=benchmark_score)

    def unregister(self, node_id: str) -> None:
        with self._lock:
            self._nodes.pop(node_id, None)

    def acquire_load(self, node_id: str) -> None:
        with self._lock:
            self._nodes[node_id].active_tasks += 1

    def release_load(self, node_id: str) -> None:
        with self._lock:
            n = self._nodes.get(node_id)
            if n and n.active_tasks > 0:
                n.active_tasks -= 1

    def all_nodes(self) -> list[RegisteredNode]:
        with self._lock:
            return list(self._nodes.values())
