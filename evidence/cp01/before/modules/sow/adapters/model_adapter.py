"""Generic model worker adapter (Plan §12.2, §9.7; I-CH1/I-SC1; Phase 6).

One adapter class, configured by a Backend + capability descriptors + locality/eligibility
flags. Instantiating it three ways gives the ≥3 Phase-6 backends behind ONE contract — a
local reasoning node, a mocked frontier node, and a coding node — all selectable by
capability descriptor, never by name. Reads scoped context from MCP, runs the node-local
gate before publish, publishes CANDIDATE with provenance (workers never self-canonize).
"""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone
from typing import Any

from adapters.base.backend import Backend, BackendAuthPause
from adapters.base.contract import AdapterCapability, AdapterContext, BaseAdapter
from node_runtime.gate.local_gate import LocalGate


class WorkerNotAssigned(Exception):
    pass


class ModelWorkerAdapter(BaseAdapter):
    def __init__(self, context: AdapterContext, mcp_client: Any, backend: Backend, *,
                 adapter_name: str, node_class: str, locality: str, offline_profile_eligible: bool,
                 requires_network: bool, capability_descriptors: list[dict[str, Any]],
                 subscription_backed: bool = False, harness: str | None = None) -> None:
        super().__init__(context)
        self._mcp = mcp_client
        self._backend = backend
        self._adapter_name = adapter_name
        self._node_class = node_class
        self._locality = locality
        self._offline_eligible = offline_profile_eligible
        self._requires_network = requires_network
        self._caps = capability_descriptors
        self._subscription_backed = subscription_backed
        self._harness = harness
        self._task_id: str | None = None
        self._context_entry: str | None = None

    @property
    def backend(self) -> Backend:
        """The bound backend, read-only.

        Exposed so a governed caller (Phase 15D `.debate`) can bind the backend of a node the
        SUPERVISOR spawned, instead of constructing its own — which would bypass the live-spawn
        gates — or reaching into `_backend` from another module. It grants no new authority: the
        backend only generates text, and every gate has already run by the time a caller holds
        the adapter.
        """
        return self._backend

    def capability(self) -> AdapterCapability:
        return AdapterCapability(
            adapter=self._adapter_name, node_class=self._node_class, locality=self._locality,
            offline_profile_eligible=self._offline_eligible, requires_network=self._requires_network,
            local_runtime=(self._locality == "local"),
            capabilities=tuple(c["capability"] for c in self._caps),
            subscription_backed=self._subscription_backed)

    def capability_descriptors(self) -> list[dict[str, Any]]:
        return list(self._caps)

    def assign(self, task_id: str, context_entry_id: str) -> None:
        self._task_id = task_id
        self._context_entry = context_entry_id
        self._log("assigned", task_id=task_id, context_entry=context_entry_id, backend=self._backend.name)

    def execute(self, *, max_tokens: int = 256) -> dict[str, Any]:
        if not self._task_id or not self._context_entry:
            raise WorkerNotAssigned("worker has no assignment")
        ctx = self._mcp.call("get_content", entry_id=self._context_entry)  # scoped context via MCP
        objective = base64.b64decode(ctx["content_b64"]).decode("utf-8")

        # a backend fault (daemon down, HTTP/JSON error) is a task failure, not a crash of the
        # scheduling loop — return structured failure symmetric with the local-gate-fail path (F3).
        # EXCEPTION: an auth/credit/rate pause (BackendAuthPause) is NOT a task failure — it must
        # propagate so the supervisor pauses the node fail-closed (Plan §18.4), never a silent
        # swallow that would let the loop keep assigning to a dead subscription.
        try:
            generated = self._backend.generate(f"Task {self._task_id}. {objective}", max_tokens=max_tokens)
        except BackendAuthPause:
            self._log("backend_auth_pause", task_id=self._task_id)
            raise
        except Exception as exc:  # noqa: BLE001 - any backend transport/decode error is fail-closed
            self._log("backend_error", task_id=self._task_id, error=f"{type(exc).__name__}: {exc}")
            return {"published": False, "backend_error": f"{type(exc).__name__}: {exc}"}
        if not generated.strip():
            self._log("backend_empty", task_id=self._task_id)
            return {"published": False, "backend_error": "backend returned empty output"}
        body = (f"# Result for {self._task_id} ({self._adapter_name})\n\n"
                f"Objective (from MCP {self._context_entry}): {objective}\n\n{generated}\n")
        content = body.encode("utf-8")
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        structured = {
            "summary": f"{self._task_id} complete via {self._adapter_name}",
            "claims": [{"text": "objective read from MCP", "evidence_refs": [self._context_entry]},
                       {"text": "artifact content-addressed", "evidence_refs": [digest]}],
            "artifact": {"artifact_id": digest, "media_type": "text/markdown", "size_bytes": len(content),
                         "created_by_node": self._context.node_id, "task_id": self._task_id,
                         "ts": _now(), "schema": "artifact@1.0"},
        }
        verdict = LocalGate().evaluate(structured, content)
        if not verdict.passed:
            self._log("local_gate_fail", task_id=self._task_id, reasons=verdict.reasons())
            return {"published": False, "local_gate": "FAIL", "reasons": verdict.reasons()}
        prov = {"author_node": self._context.node_id, "task_id": self._task_id, "ts": _now(),
                "directive_version": "v2.4", "confidence": "medium", "model": self._backend.name,
                "evidence": [self._context_entry]}
        pub = self._mcp.call("publish", kind="finding", tier="shared_project",
                             content_b64=base64.b64encode(content).decode("ascii"),
                             provenance=prov, status="CANDIDATE")
        self._log("published_candidate", task_id=self._task_id, entry_id=pub["entry_id"], backend=self._backend.name)
        # `structured` travels with the result because the STAGE gate evaluates the structured
        # output alongside the stored bytes (`LiveGovernedFlow._run_wave`), exactly as it does for
        # the LocalWorkerAdapter. Omitting it left this adapter unusable in the governed flow — the
        # gate had nothing to evaluate — which is why a live worker leg could not be run at all
        # before Phase 17B `.legs`. It is the SAME object the node-local gate just passed, so the
        # two gates judge one artifact rather than two descriptions of it.
        return {"published": True, "local_gate": "PASS", "entry_id": pub["entry_id"],
                "content_hash": digest, "generated_chars": len(generated),
                "structured": structured}

    def export_session_state(self) -> dict[str, Any]:
        return {"node_id": self._context.node_id, "task_id": self._task_id,
                "context_entry": self._context_entry, "backend": self._backend.name}

    def get_context_status(self) -> dict[str, Any]:
        return {"assigned": self._task_id is not None, "task_id": self._task_id}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
