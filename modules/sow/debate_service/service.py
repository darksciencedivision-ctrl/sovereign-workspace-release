"""Debate Service (Plan §2.15, §19.2; I-DS1, invariants 14/15/17/18).

A reusable control-plane service: ANY authorized node may request a debate (not conductor-
coupled). The Permission Broker (control_plane.policy) authorizes the caller; the cost
governor enforces budget/quota/global cap; the round manager runs ≤5 evidence-based rounds
with early stop and preserved dissent; the evidence manager keeps it evidence-based. The
result is a debate@1.0 record written immutably to MCP for a gate to reference.

Invariant 18 (no node solely judges its own work) is enforced here: the resolved participant
set must contain a node other than the caller, or the request is refused.
"""
from __future__ import annotations

import base64
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

from control_plane.policy import Identity, SovereignPolicy
from debate_service.cost_governor.governor import CostGovernor, DebateRefused
from debate_service.evidence_manager.manager import EvidenceManager
from debate_service.round_manager.manager import Debater, RoundManager

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
_SCHEMA = json.loads((_SCHEMA_DIR / "debate.schema.json").read_text(encoding="utf-8"))
_NODE_SCHEMA = json.loads((_SCHEMA_DIR / "node.schema.json").read_text(encoding="utf-8"))
# debate@1.0 $refs node@1.0's capability_descriptor; give the validator a store to resolve it
_STORE = {_SCHEMA["$id"]: _SCHEMA, _NODE_SCHEMA["$id"]: _NODE_SCHEMA}


def _validate_debate(record: dict[str, Any]) -> None:
    resolver = jsonschema.RefResolver(base_uri=_SCHEMA["$id"], referrer=_SCHEMA, store=_STORE)
    jsonschema.validate(record, _SCHEMA, resolver=resolver)


class DebateAuthorizationError(Exception):
    pass


class DebateService:
    def __init__(self, policy: SovereignPolicy, cost_governor: CostGovernor,
                 evidence_manager: EvidenceManager, mcp_client: Any, *, round_cost: int = 100) -> None:
        self._policy = policy
        self._cost = cost_governor
        self._evidence = evidence_manager
        self._mcp = mcp_client
        self._round_mgr = RoundManager(cost_governor, evidence_manager, round_cost=round_cost)

    def request_debate(self, caller: Identity, request: dict[str, Any], debaters: list[Debater]) -> dict[str, Any]:
        # 0) clean fail-closed validation of a malformed request (Directive §4), before any
        # slot is opened or round runs
        self._validate_request(request)

        # 1) authorization (Permission Broker): any authorized node may request
        verdict = self._policy.authorize_debate(caller, request)
        if not verdict.allow:
            raise DebateAuthorizationError(verdict.reason)

        # 2) invariant 18: the caller may not be the sole judge of its own work
        participant_nodes = {d.node_id for d in debaters}
        if not (participant_nodes - {caller.node_id}):
            raise DebateAuthorizationError(
                "a debate needs a participant other than the caller (invariant 18: no node "
                "solely judges its own work)")

        debate_id = "d-" + secrets.token_hex(8)
        budget = request["budget"]
        budget_units = int(budget.get("tokens") if budget.get("tokens") is not None else budget.get("usage_units"))

        # 3) cost governor opens the debate (global cap + per-caller quota + per-debate budget)
        try:
            self._cost.open_debate(debate_id, caller.node_id, budget_units)
        except DebateRefused as exc:
            raise DebateAuthorizationError(str(exc)) from exc

        # 4) run bounded rounds
        try:
            ro = self._round_mgr.run(debate_id, request["topic"], debaters, int(request["max_rounds"]))
        finally:
            spent = self._cost.close_debate(debate_id)

        record = {
            "debate_id": debate_id, "schema": "debate@1.0",
            "request": {
                "caller_node": caller.node_id, "topic": request["topic"],
                "artifact_refs": request.get("artifact_refs", []),
                "participants": request["participants"], "max_rounds": int(request["max_rounds"]),
                "budget": budget, "gate_id": request.get("gate_id"),
                "early_stop_criteria": request.get("early_stop_criteria"),
            },
            "result": {
                "rounds_used": ro.rounds_used, "positions": ro.positions, "outcome": ro.outcome,
                "dissent": ro.dissent, "evidence_map": ro.evidence_map,
                "cost_actual": {"tokens": int(spent)} if budget.get("tokens") else {"usage_units": int(spent)},
            },
        }
        _validate_debate(record)

        # 5) immutable MCP record (kind=evidence) a gate can reference
        prov = {"author_node": caller.node_id, "task_id": None, "ts": _now(),
                "directive_version": "v2.4", "confidence": "high"}
        pub = self._mcp.call("publish", kind="evidence", tier="shared_project",
                             content_b64=base64.b64encode(json.dumps(record, sort_keys=True).encode()).decode("ascii"),
                             provenance=prov, status="CANDIDATE")
        record["mcp_entry"] = pub["entry_id"]
        return record


    @staticmethod
    def _validate_request(request: dict[str, Any]) -> None:
        if not isinstance(request, dict):
            raise DebateAuthorizationError("request must be an object")
        topic = request.get("topic")
        if not isinstance(topic, str) or not topic.strip():
            raise DebateAuthorizationError("request.topic is required and non-empty")
        mr = request.get("max_rounds")
        if not isinstance(mr, int) or not (1 <= mr <= 5):
            raise DebateAuthorizationError("request.max_rounds must be an integer in 1..5")
        budget = request.get("budget")
        if not isinstance(budget, dict):
            raise DebateAuthorizationError("request.budget is required")
        tokens, units = budget.get("tokens"), budget.get("usage_units")
        if not ((isinstance(tokens, int) and tokens >= 1) or (isinstance(units, int) and units >= 1)):
            raise DebateAuthorizationError("request.budget needs tokens>=1 or usage_units>=1")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
