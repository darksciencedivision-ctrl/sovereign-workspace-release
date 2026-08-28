"""Task graph manager (Plan §9.3; invariant 16).

Deterministic control-plane state (never model output). Tasks advance through the task@1.0
state machine; a task becomes READY only when every dependency is DONE. Failed artifacts
cannot advance: a GATED_FAIL task and every task transitively depending on it are BLOCKED,
and there is no conductor override — only the operator may force a state, and that is logged
by the caller. Emits an ordered event trace so an end-to-end run has no unrecorded hop.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskState(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_GATE = "AWAITING_GATE"
    GATED_PASS = "GATED_PASS"
    GATED_FAIL = "GATED_FAIL"
    BLOCKED = "BLOCKED"
    DONE = "DONE"


_LEGAL: dict[TaskState, frozenset[TaskState]] = {
    TaskState.PENDING: frozenset({TaskState.READY, TaskState.BLOCKED}),
    TaskState.READY: frozenset({TaskState.ASSIGNED, TaskState.BLOCKED}),
    TaskState.ASSIGNED: frozenset({TaskState.IN_PROGRESS, TaskState.READY, TaskState.BLOCKED}),
    TaskState.IN_PROGRESS: frozenset({TaskState.AWAITING_GATE, TaskState.BLOCKED}),
    TaskState.AWAITING_GATE: frozenset({TaskState.GATED_PASS, TaskState.GATED_FAIL}),
    TaskState.GATED_PASS: frozenset({TaskState.DONE}),
    TaskState.GATED_FAIL: frozenset({TaskState.BLOCKED}),
    TaskState.BLOCKED: frozenset({TaskState.READY}),  # only after the blocking cause clears
    TaskState.DONE: frozenset(),
}


class IllegalTaskTransition(Exception):
    pass


@dataclass
class Task:
    task_id: str
    capability_req: dict[str, Any]
    deps: tuple[str, ...] = ()
    parent: str | None = None
    state: TaskState = TaskState.PENDING
    assigned_node: str | None = None
    artifacts: list[str] = field(default_factory=list)
    gate_id: str | None = None


class TaskGraph:
    def __init__(self, event_sink: Any = None) -> None:
        self._lock = threading.RLock()
        self._tasks: dict[str, Task] = {}
        self._events: list[dict[str, Any]] = []
        self._sink = event_sink  # optional callable(kind, **data)

    def add_task(self, task_id: str, capability_req: dict[str, Any], deps: tuple[str, ...] = (),
                 parent: str | None = None) -> Task:
        with self._lock:
            if task_id in self._tasks:
                raise ValueError(f"duplicate task {task_id}")
            for d in deps:
                if d not in self._tasks:
                    raise ValueError(f"dependency {d} not defined before {task_id}")
            task = Task(task_id=task_id, capability_req=capability_req, deps=tuple(deps), parent=parent)
            self._tasks[task_id] = task
            self._emit("task_added", task_id=task_id, deps=list(deps), capability=capability_req.get("capability"))
            self._recompute_readiness()
            return task

    def _emit(self, kind: str, **data: Any) -> None:
        ev = {"ts": time.time(), "kind": kind, **data}
        self._events.append(ev)
        if self._sink is not None:
            self._sink(kind, **data)

    def transition(self, task_id: str, to: TaskState, *, reason: str = "", by: str = "scheduler") -> Task:
        with self._lock:
            task = self._tasks[task_id]
            if to not in _LEGAL[task.state]:
                raise IllegalTaskTransition(f"{task_id}: {task.state.value} -> {to.value}")
            self._emit("task_transition", task_id=task_id, frm=task.state.value, to=to.value, reason=reason, by=by)
            task.state = to
            if to in (TaskState.GATED_FAIL, TaskState.DONE, TaskState.BLOCKED):
                self._recompute_readiness()
            return task

    def _recompute_readiness(self) -> None:
        for task in self._tasks.values():
            if task.state is TaskState.PENDING:
                dep_states = [self._tasks[d].state for d in task.deps]
                if any(s in (TaskState.GATED_FAIL, TaskState.BLOCKED) for s in dep_states):
                    self._emit("task_transition", task_id=task.task_id, frm=task.state.value,
                               to=TaskState.BLOCKED.value, reason="a dependency failed/blocked", by="graph")
                    task.state = TaskState.BLOCKED
                elif all(s is TaskState.DONE for s in dep_states):  # empty deps -> vacuously ready
                    self._emit("task_transition", task_id=task.task_id, frm=task.state.value,
                               to=TaskState.READY.value, reason="dependencies satisfied", by="graph")
                    task.state = TaskState.READY

    def assign(self, task_id: str, node_id: str, *, rationale: str) -> None:
        with self._lock:
            self.transition(task_id, TaskState.ASSIGNED, reason=rationale, by="scheduler")  # validates legality
            self._tasks[task_id].assigned_node = node_id
            self._emit("task_assigned", task_id=task_id, node_id=node_id, rationale=rationale)

    def attach_artifact(self, task_id: str, artifact_ref: str) -> None:
        with self._lock:
            self._tasks[task_id].artifacts.append(artifact_ref)
            self._emit("artifact_attached", task_id=task_id, artifact=artifact_ref)

    def ready_tasks(self) -> list[Task]:
        with self._lock:
            return [t for t in self._tasks.values() if t.state is TaskState.READY]

    def get(self, task_id: str) -> Task:
        with self._lock:
            return self._tasks[task_id]

    def all_tasks(self) -> list[Task]:
        with self._lock:
            return list(self._tasks.values())

    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)
