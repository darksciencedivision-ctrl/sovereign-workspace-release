"""Scheduler (Plan §19.3; I-SC1). Assigns READY tasks to capable nodes over the Task Graph.

Works OVER the Task Graph (it does not replace it): the graph tracks dependencies/state; the
Scheduler binds ready work to a capable node and records the assignment rationale so the
operator can inspect "why this node". Assignment is by capability descriptor; a task that
cannot be resolved is queued with a visible reason (never silently dropped).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from control_plane.tasks.graph import TaskGraph
from scheduler.capability_registry.registry import CapabilityRegistry
from scheduler.resolver.resolver import CapabilityResolver


@dataclass
class Assignment:
    task_id: str
    node_id: str
    rationale: str


@dataclass
class Queued:
    task_id: str
    reason: str


class Scheduler:
    def __init__(self, graph: TaskGraph, registry: CapabilityRegistry, *, profile_airgapped: bool = False) -> None:
        self._graph = graph
        self._registry = registry
        self._resolver = CapabilityResolver(registry)
        self._airgapped = profile_airgapped

    def schedule_ready(self) -> tuple[list[Assignment], list[Queued]]:
        """Resolve and assign every currently-READY task. Returns (assignments, queued)."""
        assignments: list[Assignment] = []
        queued: list[Queued] = []
        for task in self._graph.ready_tasks():
            res = self._resolver.resolve(task.capability_req, profile_airgapped=self._airgapped)
            if not res.resolved:
                queued.append(Queued(task.task_id, res.rationale))  # surfaced, not dropped
                continue
            self._graph.assign(task.task_id, res.node_id, rationale=res.rationale)
            self._registry.acquire_load(res.node_id)
            assignments.append(Assignment(task.task_id, res.node_id, res.rationale))
        return assignments, queued
