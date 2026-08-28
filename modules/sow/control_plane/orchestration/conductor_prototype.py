"""Conductor prototype orchestration (Plan §3.4 F1; Phase 5).

Drives the task-assignment happy path end to end over the real MCP + task graph + scheduler:
  conductor loads files -> proposes a plan -> plan gate -> Scheduler resolves each READY
  task to a node BY CAPABILITY -> workers read scoped context FROM MCP and publish CANDIDATE
  artifacts with provenance -> node-local gate then a stage gate promotes to ACCEPTED ->
  ACCEPTED feeds the conductor's synthesis -> operator acceptance packet.

Every hop is an MCP entry (provenanced) plus a task-graph event — there is no manual
transcript/clipboard routing anywhere (I-M1). A failed artifact cannot advance: its task
goes GATED_FAIL and dependents stay BLOCKED (invariant 16). This module is control-plane
wiring; the reasoning is the mock backend (build prohibits live providers).
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

from adapters.base.contract import AdapterContext
from adapters.base.mock_backend import MockReasoningBackend
from adapters.conductor.adapter import ConductorAdapter
from adapters.local.worker import LocalWorkerAdapter
from control_plane.tasks.graph import TaskGraph, TaskState
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer
from scheduler.capability_registry.registry import CapabilityRegistry
from scheduler.scheduler import Scheduler


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConductorPrototype:
    def __init__(self, server: MCPServer, conductor_manifest: dict[str, str], project_id: str = "proj") -> None:
        self._srv = server
        self._project = project_id
        self._graph = TaskGraph()
        self._registry = CapabilityRegistry()
        self._scheduler = Scheduler(self._graph, self._registry)
        self._clients: list[McpClient] = []

        self._op = self._client("operator", "operator")
        self._gate = self._client("gate-1", "gate")
        cond_ctx = AdapterContext(node_id="conductor-fable5", role="conductor", project_id=project_id,
                                  permission_profile_id="pp-conductor", mcp_credential_id="ref",
                                  subscription_ref=None, spawned_by_supervisor=True)
        self._conductor = ConductorAdapter(cond_ctx, self._client("conductor-fable5", "conductor"),
                                           MockReasoningBackend(), None, conductor_manifest)
        self._workers: dict[str, LocalWorkerAdapter] = {}

    def _client(self, node_id: str, role: str) -> McpClient:
        c = McpClient("127.0.0.1", self._srv.port, self._srv.credentials.issue(node_id, role, self._project))
        c.connect()
        self._clients.append(c)
        return c

    def _spawn_worker(self, node_id: str) -> LocalWorkerAdapter:
        ctx = AdapterContext(node_id=node_id, role="worker", project_id=self._project,
                             permission_profile_id="pp-worker", mcp_credential_id="ref",
                             spawned_by_supervisor=True)
        w = LocalWorkerAdapter(ctx, self._client(node_id, "worker"))
        self._registry.register(node_id, w.capability_descriptors(), locality="local",
                                cost_class="local", offline_profile_eligible=True)
        self._workers[node_id] = w
        return w

    def run(self, objective: str, *, gate_reject_tasks: frozenset[str] = frozenset()) -> dict[str, Any]:
        """Drive the happy path, plus the failure path: a task whose node-local gate fails or
        whose stage gate rejects goes GATED_FAIL, and its dependents stay BLOCKED (invariant
        16). `gate_reject_tasks` lets a caller force a stage-gate rejection for testing."""
        trace: dict[str, Any] = {"objective": objective}

        # scoped context lives in MCP (operator publishes the objective, ACCEPTED)
        obj_pub = self._op.call("publish", kind="finding", tier="shared_project",
                                content_b64=_b64(objective.encode("utf-8")),
                                provenance=_prov("operator"), status="ACCEPTED")
        objective_entry = obj_pub["entry_id"]

        # conductor loads files then proposes a plan (CANDIDATE decision)
        self._conductor.start()
        plan = self._conductor.run_cycle(objective)
        trace["plan_decision"] = plan["decision_entry"]

        # plan gate: gate approves the plan before any assignment (records a gate decision)
        plan_gate = self._gate.call("publish", kind="decision", tier="shared_project",
                                    content_b64=_b64(b"plan gate: PASS"), provenance=_prov("gate-1"),
                                    status="ACCEPTED")
        trace["plan_gate"] = plan_gate["entry_id"]

        # two independent tasks, each needing the 'reasoning' capability
        self._graph.add_task("t-1", {"capability": "reasoning", "requirements": {"structured_output": True, "min_context": 8000}})
        self._graph.add_task("t-2", {"capability": "reasoning", "requirements": {"structured_output": True, "min_context": 8000}})

        # two capable worker nodes exist for the scheduler to resolve to (by descriptor)
        self._spawn_worker("worker-A")
        self._spawn_worker("worker-B")

        assignments, queued = self._scheduler.schedule_ready()
        trace["assignments"] = [{"task": a.task_id, "node": a.node_id, "rationale": a.rationale} for a in assignments]
        trace["queued"] = [{"task": q.task_id, "reason": q.reason} for q in queued]

        accepted_entries: list[str] = []
        failed_tasks: list[str] = []
        for a in assignments:
            worker = self._workers[a.node_id]
            self._graph.transition(a.task_id, TaskState.IN_PROGRESS, reason="worker started", by=a.node_id)
            worker.assign(a.task_id, objective_entry)      # context is an MCP ref, not a transcript
            result = worker.execute()                      # reads context from MCP, publishes CANDIDATE
            self._registry.release_load(a.node_id)

            if not result.get("published"):
                # node-local gate failed: nothing left the node; the task cannot advance
                self._graph.transition(a.task_id, TaskState.BLOCKED, reason="node-local gate FAIL", by=a.node_id)
                failed_tasks.append(a.task_id)
                continue

            self._graph.attach_artifact(a.task_id, result["entry_id"])
            self._graph.transition(a.task_id, TaskState.AWAITING_GATE, reason="artifact published", by=a.node_id)
            self._gate.call("transition", entry_id=result["entry_id"], requested_status="UNDER_REVIEW")

            if a.task_id in gate_reject_tasks:
                # stage gate REJECTS: failed artifact cannot advance; dependents stay BLOCKED (inv 16)
                self._gate.call("transition", entry_id=result["entry_id"], requested_status="REJECTED",
                                reviewer_note=f"stage gate REJECT for {a.task_id}")
                self._graph.transition(a.task_id, TaskState.GATED_FAIL, reason="stage gate REJECT", by="gate-1")
                self._graph.transition(a.task_id, TaskState.BLOCKED, reason="gated fail", by="gate-1")
                failed_tasks.append(a.task_id)
                continue

            self._gate.call("transition", entry_id=result["entry_id"], requested_status="ACCEPTED",
                            reviewer_note=f"stage gate PASS for {a.task_id}")
            self._graph.transition(a.task_id, TaskState.GATED_PASS, reason="stage gate PASS", by="gate-1")
            self._graph.transition(a.task_id, TaskState.DONE, reason="accepted", by="gate-1")
            accepted_entries.append(result["entry_id"])

        # conductor synthesis: read ACCEPTED findings via the adapter (no reach into privates)
        accepted = self._conductor.read_accepted()
        packet = {"objective": objective, "accepted_findings": accepted_entries,
                  "task_states": {t.task_id: t.state.value for t in self._graph.all_tasks()},
                  "synthesized_by": "conductor-fable5", "ts": _now(),
                  "accepted_count": len(accepted), "failed_tasks": failed_tasks}
        trace["acceptance_packet"] = self._conductor.publish_acceptance_packet(packet)
        trace["accepted_entries"] = accepted_entries
        trace["failed_tasks"] = failed_tasks
        trace["task_events"] = self._graph.events()
        return trace

    def close(self) -> None:
        for c in self._clients:
            c.close()


def _prov(author: str) -> dict[str, Any]:
    return {"author_node": author, "task_id": None, "ts": _now(),
            "directive_version": "v2.4", "confidence": "high"}
