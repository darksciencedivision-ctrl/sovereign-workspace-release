"""Gate engine (Plan §9.3, §7-P8; invariant 16).

Declarative gate definitions produce gate@1.0 verdicts (PASS | PASS_WITH_RESERVATIONS |
FAIL) computed deterministically from criteria, referencing evidence/debate records, with
traceable reasons. A FAIL cannot advance: applied to the Task Graph it forces GATED_FAIL →
BLOCKED, and there is NO bypass — the engine never emits PASS unless every CRITICAL criterion
passes, and the task state machine has no GATED_FAIL→DONE edge for ANY caller (the machine is
absolute; recovery is redo-and-repass a fresh gate). An operator override path is not
implemented in this phase. The conductor cannot override a gate.
"""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

from control_plane.gates.criteria import GateContext, Severity, evaluate_criterion, known_criteria
from control_plane.tasks.graph import TaskGraph, TaskState

_SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "schemas" / "gate.schema.json").read_text(encoding="utf-8"))

VALID_KINDS = ("local", "stage", "plan", "acceptance")


class GateConfigError(Exception):
    pass


@dataclass(frozen=True)
class GateDefinition:
    gate_id: str
    kind: str
    criteria: tuple[str, ...]      # stated before evaluation (declarative)

    def __post_init__(self) -> None:
        if self.kind not in VALID_KINDS:
            raise GateConfigError(f"unknown gate kind {self.kind!r}")
        if not self.criteria:
            raise GateConfigError("a gate with no criteria cannot pass anything (fail closed)")
        unknown = [c for c in self.criteria if c not in known_criteria()]
        if unknown:
            raise GateConfigError(f"unknown gate criteria (fail closed): {unknown}")


def define_gate(kind: str, criteria: list[str], *, gate_id: str | None = None) -> GateDefinition:
    return GateDefinition(gate_id or ("g-" + secrets.token_hex(6)), kind, tuple(criteria))


class GateEngine:
    """Evaluates gate definitions and (optionally) applies verdicts to the Task Graph."""

    def evaluate(self, gate: GateDefinition, ctx: GateContext, *, evidence: list[str] | None = None,
                 debate_ref: str | None = None, task_id: str | None = None) -> dict[str, Any]:
        results = [evaluate_criterion(name, ctx) for name in gate.criteria]
        critical_fail = [r for r in results if not r.passed and r.severity is Severity.CRITICAL]
        advisory_fail = [r for r in results if not r.passed and r.severity is Severity.ADVISORY]
        if critical_fail:
            verdict = "FAIL"
        elif advisory_fail:
            verdict = "PASS_WITH_RESERVATIONS"
        else:
            verdict = "PASS"
        reasons = [f"{r.name}: {r.reason}" for r in results if not r.passed] or \
                  [f"{r.name}: {r.reason}" for r in results]
        record = {
            "gate_id": gate.gate_id, "kind": gate.kind, "criteria": list(gate.criteria),
            "verdict": verdict, "evidence": list(evidence or ctx.evidence_refs),
            "debate_ref": debate_ref, "decided_by": "gate_engine", "reasons": reasons,
            "task_id": task_id, "schema": "gate@1.0",
        }
        self._validate(record)
        return record

    @staticmethod
    def _validate(record: dict[str, Any]) -> None:
        jsonschema.validate(record, _SCHEMA)

    def apply_to_task(self, graph: TaskGraph, task_id: str, record: dict[str, Any]) -> None:
        """Drive the task graph from a gate verdict, FAIL CLOSED. A task advances to DONE ONLY
        on an explicit PASS/PASS_WITH_RESERVATIONS; FAIL → GATED_FAIL → BLOCKED; ANY other or
        malformed verdict is treated as a failure (never advanced). The record is re-validated
        against gate@1.0 and must name this task, so a forged/mismatched record cannot advance
        it. No conductor override: the state machine also forbids GATED_FAIL→DONE for anyone."""
        self._validate(record)  # re-validate: a hand-built/forged record is refused here too
        if record.get("task_id") not in (None, task_id):
            raise GateConfigError(f"gate record task_id {record.get('task_id')!r} != target {task_id!r}")
        graph.get(task_id).gate_id = record["gate_id"]
        verdict = record.get("verdict")
        if verdict in ("PASS", "PASS_WITH_RESERVATIONS"):
            graph.transition(task_id, TaskState.GATED_PASS, reason=f"gate {record['gate_id']} {verdict}", by="gate_engine")
            graph.transition(task_id, TaskState.DONE, reason="accepted", by="gate_engine")
        else:
            # FAIL, null, or anything unexpected -> the artifact does not advance (fail closed)
            graph.transition(task_id, TaskState.GATED_FAIL, reason=f"gate {record['gate_id']} {verdict}", by="gate_engine")
            graph.transition(task_id, TaskState.BLOCKED, reason="gated fail", by="gate_engine")
