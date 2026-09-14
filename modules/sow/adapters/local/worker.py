"""Local mock worker adapter (Plan §12.2; Phase 5).

A worker_reasoning node backed by a local (mock) model. It receives an assignment as a
task id + the MCP entry id of its scoped context — it READS the context from MCP, never
from a passed transcript (I-M1/invariant 8: no manual transcript routing). It produces a
structured output + artifact, runs the node-local gate (Phase 3) before anything leaves the
node, and publishes the result to MCP as a CANDIDATE with provenance carrying its task id.
Workers publish CANDIDATE only; promotion is the gate's job (I-M6).
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from adapters.base.contract import AdapterCapability, AdapterContext, BaseAdapter
from node_runtime.gate.local_gate import LocalGate


class WorkerNotAssigned(Exception):
    pass


class LocalWorkerAdapter(BaseAdapter):
    def __init__(self, context: AdapterContext, mcp_client: Any, model_name: str = "mock-local-worker") -> None:
        super().__init__(context)
        self._mcp = mcp_client
        self._model = model_name
        self._task_id: str | None = None
        self._context_entry: str | None = None

    def capability(self) -> AdapterCapability:
        return AdapterCapability(
            adapter="local_mock_worker", node_class="worker_reasoning", locality="local",
            offline_profile_eligible=True, requires_network=False, local_runtime=True,
            capabilities=("reasoning", "review"), subscription_backed=False)

    def capability_descriptors(self) -> list[dict[str, Any]]:
        return [
            {"capability": "reasoning", "requirements": {"tool_use": True, "structured_output": True,
                                                         "min_context": 8000, "locality": "any"}},
            {"capability": "review", "requirements": {"structured_output": True, "min_context": 8000}},
        ]

    def assign(self, task_id: str, context_entry_id: str) -> None:
        """Bind an assignment. Context is an MCP entry ref — the worker fetches it itself."""
        self._task_id = task_id
        self._context_entry = context_entry_id
        self._log("assigned", task_id=task_id, context_entry=context_entry_id)

    def execute(self) -> dict[str, Any]:
        if not self._task_id or not self._context_entry:
            raise WorkerNotAssigned("worker has no assignment")
        # scoped context arrives via MCP, not a transcript
        ctx = self._mcp.call("get_content", entry_id=self._context_entry)
        objective = base64.b64decode(ctx["content_b64"]).decode("utf-8")

        # deterministic mock work product for this task
        body = (f"# Result for {self._task_id}\n\n"
                f"Objective (from MCP {self._context_entry}): {objective}\n\n"
                f"Deterministic finding produced by {self._context.node_id}.\n")
        content = body.encode("utf-8")
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        structured = {
            "summary": f"{self._task_id} complete",
            "claims": [{"text": "objective was read from MCP", "evidence_refs": [self._context_entry]},
                       {"text": "artifact is content-addressed", "evidence_refs": [digest]}],
            "artifact": {"artifact_id": digest, "media_type": "text/markdown", "size_bytes": len(content),
                         "created_by_node": self._context.node_id, "task_id": self._task_id,
                         "ts": _now(), "schema": "artifact@1.0"},
        }
        # local gate BEFORE publish (invariant 16: failed artifacts don't leave the node)
        verdict = LocalGate().evaluate(structured, content)
        if not verdict.passed:
            self._log("local_gate_fail", task_id=self._task_id, reasons=verdict.reasons())
            return {"published": False, "local_gate": "FAIL", "reasons": verdict.reasons()}
        prov = {"author_node": self._context.node_id, "task_id": self._task_id, "ts": _now(),
                "directive_version": "v2.4", "confidence": "medium",
                "model": "mock-local-worker", "evidence": [self._context_entry]}
        pub = self._mcp.call("publish", kind="finding", tier="shared_project",
                             content_b64=base64.b64encode(content).decode("ascii"),
                             provenance=prov, status="CANDIDATE")
        self._log("published_candidate", task_id=self._task_id, entry_id=pub["entry_id"])
        return {"published": True, "local_gate": "PASS", "entry_id": pub["entry_id"],
                "content_hash": digest, "structured": structured}

    def export_session_state(self) -> dict[str, Any]:
        return {"node_id": self._context.node_id, "task_id": self._task_id,
                "context_entry": self._context_entry}

    def get_context_status(self) -> dict[str, Any]:
        return {"assigned": self._task_id is not None, "task_id": self._task_id}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
