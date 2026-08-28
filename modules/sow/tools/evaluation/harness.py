"""Phase 13 comparative evaluation harness (Plan §7-P13, §12.4).

Runs the reference workload under four configurations and instruments cost-to-accepted-output
plus a capability matrix, so the operator can see what the governance layers COST and what they
BUY relative to simpler baselines:

  C0_single_pass        — one model, one answer, no orchestration (ungated, no provenance).
  C2_conductor_raw      — a conductor + raw workers; outputs accepted without gate/provenance.
  C3_sovereign_no_debate— full governance: workers publish CANDIDATE via MCP, a gate promotes
                          to ACCEPTED (provenance + gate verdict), no debate.
  C4_sovereign_debate   — C3 plus a bounded evidence-based debate before the gate.

HONEST LIMITATION (must be stated): all backends are DETERMINISTIC MOCKS, so every config
produces the same content — this harness measures ORCHESTRATION cost and capabilities, NOT
model reasoning quality. No claim is made that any config reasons better; a real model-quality
comparison needs live/local models under the same harness (deferred, Track E).
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from typing import Any

from adapters.base.backend import MockBackend
from control_plane.gates import GateContext, GateEngine, define_gate
from control_plane.policy import Identity, SovereignPolicy
from control_plane.routing.token_meter import count_tokens, tokenizer_method
from debate_service import CostGovernor, DebateService, EvidenceManager, mcp_resolver
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer


class _HarnessDebater:
    """Minimal deterministic debate participant for the C4 leg (no live model)."""
    def __init__(self, node_id: str, position: str) -> None:
        self.node_id = node_id
        self._position = position

    def argue(self, topic: str, round_no: int, transcript: list) -> dict[str, Any]:
        return {"position": self._position, "evidence_refs": []}

REFERENCE_OBJECTIVE = "Design the offline conductor roster and its fallbacks."
REFERENCE_TASKS = ["t-analyze", "t-design"]

STAGE_CRITERIA = ["artifact_present", "structured_output_valid", "artifact_content_addressed",
                  "claims_cite_evidence", "no_placeholders", "no_unresolved_critical"]


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _prov(a: str, task: str | None = None) -> dict:
    return {"author_node": a, "task_id": task, "ts": "2026-07-17T00:00:00+00:00",
            "directive_version": "v2.4", "confidence": "medium"}


@dataclass
class ConfigResult:
    config: str
    model_tokens: int = 0
    control_ops: int = 0
    wallclock_s: float = 0.0
    accepted: int = 0
    provenance_bearing: bool = False
    gated: bool = False
    debated: bool = False
    recoverable: bool = False
    debate_id: str | None = None

    @property
    def cost_to_accepted(self) -> float:
        return round(self.model_tokens / self.accepted, 1) if self.accepted else float("inf")

    def as_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "cost_to_accepted_tokens": self.cost_to_accepted}


def _mock_work(backend: MockBackend, task: str) -> tuple[str, int]:
    prompt = f"Task {task}. {REFERENCE_OBJECTIVE}"
    out = backend.generate(prompt)
    return out, count_tokens(prompt) + count_tokens(out)


class EvaluationHarness:
    def __init__(self, store_dir) -> None:
        self._store_dir = store_dir

    # -- baselines (no MCP governance) ----------------------------------------
    def _c0_single_pass(self) -> ConfigResult:
        r = ConfigResult("C0_single_pass")
        t0 = time.monotonic()
        _, toks = _mock_work(MockBackend(), "single")
        r.model_tokens = toks
        r.accepted = 1                     # ungated: the one answer is "accepted" by default
        r.wallclock_s = round(time.monotonic() - t0, 4)
        return r

    def _c2_conductor_raw(self) -> ConfigResult:
        r = ConfigResult("C2_conductor_raw")
        t0 = time.monotonic()
        backend = MockBackend()
        for task in REFERENCE_TASKS:
            _, toks = _mock_work(backend, task)
            r.model_tokens += toks
            r.control_ops += 1             # conductor assignment only, no gate
            r.accepted += 1                # raw: accepted without a gate or provenance
        r.wallclock_s = round(time.monotonic() - t0, 4)
        return r

    # -- Sovereign configs (MCP + gate; +debate) ------------------------------
    def _sovereign(self, *, with_debate: bool) -> ConfigResult:
        name = "C4_sovereign_debate" if with_debate else "C3_sovereign_no_debate"
        r = ConfigResult(name, provenance_bearing=True, gated=True, debated=with_debate, recoverable=True)
        srv = MCPServer(self._store_dir / name); srv.start()
        try:
            t0 = time.monotonic()
            backend = MockBackend()
            gate_engine = GateEngine()
            gate = _client(srv, "gate-1", "gate")
            for task in REFERENCE_TASKS:
                worker = _client(srv, f"w-{task}", "worker")
                out, toks = _mock_work(backend, task)
                r.model_tokens += toks
                # worker publishes a CANDIDATE artifact with provenance (governed path)
                content = out.encode("utf-8")
                import hashlib
                digest = "sha256:" + hashlib.sha256(content).hexdigest()
                pub = worker.call("publish", kind="finding", tier="shared_project",
                                  content_b64=_b64(content), provenance=_prov(f"w-{task}", task),
                                  status="CANDIDATE")
                r.control_ops += 1
                if with_debate:
                    # run the REAL bounded Debate Service before the gate (not a synthetic surcharge)
                    debate_svc = DebateService(SovereignPolicy(), CostGovernor(),
                                               EvidenceManager(mcp_resolver(worker)), worker)
                    caller = Identity(f"w-{task}", "worker", "proj")
                    debaters = [_HarnessDebater("reviewer-1", "accept"),
                                _HarnessDebater("reviewer-2", "accept")]
                    rec = debate_svc.request_debate(
                        caller,
                        {"caller_node": f"w-{task}", "topic": f"review {task}",
                         "participants": [{"capability": "review", "requirements": {"structured_output": True}}],
                         "max_rounds": 2, "budget": {"tokens": 1000}},
                        debaters)
                    r.model_tokens += int(rec["result"]["cost_actual"].get("tokens", 0))  # real debate cost
                    r.control_ops += rec["result"]["rounds_used"] + 1  # rounds + the record publish
                    r.debate_id = rec["debate_id"]
                # gate evaluates and promotes (gated + provenance)
                structured = {"summary": f"{task} done",
                              "claims": [{"text": "objective addressed", "evidence_refs": [pub["entry_id"]]}],
                              "artifact": {"artifact_id": digest, "media_type": "text/plain",
                                           "size_bytes": len(content), "created_by_node": f"w-{task}",
                                           "task_id": task, "ts": "2026-07-17T00:00:00+00:00",
                                           "schema": "artifact@1.0"}}
                verdict = gate_engine.evaluate(define_gate("stage", STAGE_CRITERIA),
                                               GateContext(artifact_content=content, structured_output=structured,
                                                           evidence_refs=[pub["entry_id"]]), task_id=task)
                r.control_ops += 1
                if verdict["verdict"] in ("PASS", "PASS_WITH_RESERVATIONS"):
                    gate.call("transition", entry_id=pub["entry_id"], requested_status="UNDER_REVIEW")
                    gate.call("transition", entry_id=pub["entry_id"], requested_status="ACCEPTED")
                    r.control_ops += 2
                    r.accepted += 1
                worker.close()
            r.wallclock_s = round(time.monotonic() - t0, 4)
            gate.close()
        finally:
            srv.stop()
        return r

    def run(self) -> dict[str, Any]:
        results = [self._c0_single_pass(), self._c2_conductor_raw(),
                   self._sovereign(with_debate=False), self._sovereign(with_debate=True)]
        return {
            "harness": "phase13-eval@1.0", "tokenizer": tokenizer_method(),
            "reference_objective": REFERENCE_OBJECTIVE, "reference_tasks": REFERENCE_TASKS,
            "configs": [r.as_dict() for r in results],
            "capability_matrix": {r.config: {"provenance": r.provenance_bearing, "gated": r.gated,
                                             "debated": r.debated, "recoverable": r.recoverable}
                                  for r in results},
            "honest_limitation": (
                "All backends are DETERMINISTIC MOCKS: every config produces identical content, so "
                "this harness measures ORCHESTRATION cost + capabilities, NOT model reasoning quality. "
                "No config is claimed to reason better. A real model-quality comparison requires "
                "live/local models under the same harness (deferred, Track E)."),
        }


def _client(server: MCPServer, node: str, role: str) -> McpClient:
    c = McpClient("127.0.0.1", server.port, server.credentials.issue(node, role, "proj")); c.connect()
    return c
