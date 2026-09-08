"""Debate round manager (Plan §19.2; invariants 14, 15).

Runs structured rounds — each participant states a position with evidence citations; the
manager records them, checks the evidence, charges the round cost, and decides whether to
continue. Hard cap ≤5 rounds. Early stop on convergence. If the participants do not converge
by the cap, dissent is PRESERVED verbatim (no consensus forcing). Budget exhaustion cuts off
cleanly with the partial record kept. Deterministic control logic; the participants
(debaters) are where any model would plug in.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from debate_service.cost_governor.governor import CostGovernor
from debate_service.evidence_manager.manager import EvidenceManager

HARD_ROUND_CAP = 5


class Debater(Protocol):
    node_id: str

    def argue(self, topic: str, round_no: int, transcript: list[dict[str, Any]]) -> dict[str, Any]:
        """Return {"position": str, "evidence_refs": [str, ...]}."""


@dataclass
class RoundOutcome:
    outcome: str                       # CONVERGED | DISSENT_PRESERVED | BUDGET_EXHAUSTED | CUT_OFF
    rounds_used: int
    positions: list[dict[str, Any]]    # latest position per node (with evidence_refs)
    dissent: str | None
    evidence_map: dict[str, Any]
    transcript: list[dict[str, Any]] = field(default_factory=list)


class RoundManager:
    def __init__(self, cost_governor: CostGovernor, evidence_manager: EvidenceManager,
                 *, round_cost: int = 100) -> None:
        self._cost = cost_governor
        self._evidence = evidence_manager
        self._round_cost = round_cost

    def run(self, debate_id: str, topic: str, debaters: list[Debater], max_rounds: int) -> RoundOutcome:
        max_rounds = min(max_rounds, HARD_ROUND_CAP)  # hard cap regardless of request (inv 14)
        transcript: list[dict[str, Any]] = []
        latest: dict[str, dict[str, Any]] = {}
        evidence_map: dict[str, Any] = {}
        outcome = "CUT_OFF"
        rounds_used = 0

        for round_no in range(1, max_rounds + 1):
            if not self._cost.charge(debate_id, self._round_cost):
                outcome = "BUDGET_EXHAUSTED"  # clean cutoff, partial record kept
                break
            rounds_used = round_no
            round_positions = []
            for d in debaters:
                stmt = d.argue(topic, round_no, transcript)
                position, refs = stmt.get("position", ""), stmt.get("evidence_refs", [])
                cls = self._evidence.classify_assertion(position, refs)
                evidence_map[f"{d.node_id}@r{round_no}"] = {"position": position, **cls}
                entry = {"node": d.node_id, "position": position, "evidence_refs": refs,
                         "round": round_no, "reference_resolved": cls["reference_resolved"]}
                round_positions.append(entry)
                latest[d.node_id] = entry
            transcript.append({"round": round_no, "positions": round_positions})
            if self._converged(latest):
                outcome = "CONVERGED"
                break
        else:
            # loop finished without break: reached the cap without convergence
            outcome = "DISSENT_PRESERVED"

        positions = [{"node": n, "position": e["position"], "evidence_refs": e["evidence_refs"]}
                     for n, e in latest.items()]
        dissent = None
        if outcome in ("DISSENT_PRESERVED", "BUDGET_EXHAUSTED") and not self._converged(latest):
            distinct = sorted({e["position"] for e in latest.values()})
            if len(distinct) > 1:
                dissent = " | ".join(distinct)  # preserved verbatim, never smoothed away
        return RoundOutcome(outcome, rounds_used, positions, dissent, evidence_map, transcript)

    @staticmethod
    def _converged(latest: dict[str, dict[str, Any]]) -> bool:
        if len(latest) < 2:
            return False  # a single voice is not concurrence
        positions = {e["position"] for e in latest.values()}
        # convergence requires aligned positions plus at least one resolved reference
        return len(positions) == 1 and any(e["reference_resolved"] for e in latest.values())
