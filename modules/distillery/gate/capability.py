from __future__ import annotations

"""Executable Sovereign capability ledger and governed-floor enforcement (F-10/F-11).

Append-preserving by construction: every mutation appends to an event history;
current state and historical best are stored separately and neither silently
overwrites the other. Historical best and governed floor are DIFFERENT concepts:
a candidate may improve total capability and still be rejected for breaching a
governed CRITICAL floor.

Floor policy changes require explicit accepted authority. Lowering a floor
after results have been observed requires an authorized policy transition
record; raising a floor also requires authority. No silent floor mutation.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from distillery.common import ContractError, sha256_value, utc_now

CRITICALITY_LEVELS = ("CRITICAL", "HIGH", "STANDARD")
REMEDIATION_STATES = (
    "NOT_APPLICABLE",
    "OK",
    "FLOOR_BREACH_OBSERVED",
    "REMEDIATION_REQUIRED",
    "REMEDIATION_IN_PROGRESS",
    "REMEDIATION_VERIFIED",
)
REQUIRED_RECORD_FIELDS = (
    "capability_id", "description", "criticality", "evaluation_suite",
    "current_checkpoint", "current_score", "dispersion",
    "historical_best_checkpoint", "historical_best_score",
    "governed_floor", "floor_authority", "target_margin",
    "parent_regression_margin", "historical_regression_margin",
    "remediation_state", "last_evaluated_at", "evidence_refs",
)


@dataclass(frozen=True)
class PromotionVerdict:
    passed: bool
    failing_capabilities: tuple
    rationale: str

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "failing_capabilities": list(self.failing_capabilities),
            "rationale": self.rationale,
        }


class CapabilityLedger:
    def __init__(self) -> None:
        self._records: dict[str, dict] = {}
        self._events: list[dict] = []

    def _append(self, action: str, **payload) -> None:
        self._events.append({"action": action, "at": utc_now(), **payload})

    @property
    def events(self) -> tuple:
        return tuple(self._events)

    def integrity_snapshot(self) -> str:
        return sha256_value({"records": self._records, "events": self._events})

    def register(
        self,
        *,
        capability_id: str,
        description: str,
        criticality: str,
        evaluation_suite: str,
        target_margin: float = 0.0,
        parent_regression_margin: float = 0.0,
        historical_regression_margin: float = 0.0,
    ) -> dict:
        if not capability_id or capability_id in self._records:
            raise ContractError(f"capability_id must be unique and non-empty: {capability_id!r}")
        if criticality not in CRITICALITY_LEVELS:
            raise ContractError(f"criticality must be one of {CRITICALITY_LEVELS}")
        if not description or not evaluation_suite:
            raise ContractError("capability registration requires description and evaluation_suite")
        record = {
            "capability_id": capability_id,
            "description": description,
            "criticality": criticality,
            "evaluation_suite": evaluation_suite,
            "current_checkpoint": None,
            "current_score": None,
            "dispersion": None,
            "historical_best_checkpoint": None,
            "historical_best_score": None,
            "governed_floor": None,
            "floor_authority": None,
            "target_margin": target_margin,
            "parent_regression_margin": parent_regression_margin,
            "historical_regression_margin": historical_regression_margin,
            "remediation_state": "NOT_APPLICABLE",
            "last_evaluated_at": None,
            "evidence_refs": [],
        }
        assert set(REQUIRED_RECORD_FIELDS).issubset(record.keys())
        self._records[capability_id] = record
        self._append("register", capability_id=capability_id, criticality=criticality)
        return record

    def get(self, capability_id: str) -> dict:
        if capability_id not in self._records:
            raise ContractError(f"unknown capability: {capability_id}")
        return self._records[capability_id]

    def set_governed_floor(
        self,
        capability_id: str,
        *,
        floor_value: float,
        authority_ref: str,
        authorized_policy_transition: dict | None = None,
    ) -> dict:
        """Set or change a governed floor under explicit accepted authority.

        Lowering a floor AFTER observations exist requires an authorized policy
        transition record ({ref, authority, reason}); attempting it without one
        fails closed. Raising or first-setting requires authority_ref alone.
        """
        record = self.get(capability_id)
        if not isinstance(authority_ref, str) or not authority_ref.strip():
            raise ContractError("floor change requires an authority reference")
        current = record["governed_floor"]
        lowering_after_observation = (
            current is not None
            and floor_value < current
            and record["last_evaluated_at"] is not None
        )
        if lowering_after_observation:
            if not isinstance(authorized_policy_transition, dict):
                raise ContractError(
                    f"lowering governed floor of evaluated capability {capability_id} "
                    "requires an explicit authorized policy transition"
                )
            for field in ("ref", "authority", "reason"):
                value = authorized_policy_transition.get(field)
                if not isinstance(value, str) or not value.strip():
                    raise ContractError(f"authorized policy transition missing {field}")
            if authorized_policy_transition["authority"].lower() in {"system", "loop", "agent"}:
                raise ContractError("policy transition authority must be human")
        record["governed_floor"] = floor_value
        record["floor_authority"] = authority_ref
        self._append(
            "set_governed_floor",
            capability_id=capability_id,
            floor_value=floor_value,
            authority_ref=authority_ref,
            authorized_policy_transition=dict(authorized_policy_transition) if authorized_policy_transition else None,
        )
        return record

    def record_evaluation(
        self,
        capability_id: str,
        *,
        score: float,
        checkpoint_ref: str,
        dispersion: float | None = None,
        evidence_refs: tuple = (),
    ) -> dict:
        record = self.get(capability_id)
        previous_best = record["historical_best_score"]
        new_best = previous_best is None or (score is not None and previous_best is not None and score > previous_best)
        if new_best:
            record["historical_best_score"] = score
            record["historical_best_checkpoint"] = checkpoint_ref
        record["current_score"] = score
        record["current_checkpoint"] = checkpoint_ref
        record["dispersion"] = dispersion
        record["last_evaluated_at"] = utc_now()
        for ref in evidence_refs:
            if ref not in record["evidence_refs"]:
                record["evidence_refs"].append(ref)
        floor = record["governed_floor"]
        breached = floor is not None and score is not None and score < floor
        if breached:
            record["remediation_state"] = "FLOOR_BREACH_OBSERVED"
        elif record["remediation_state"] == "FLOOR_BREACH_OBSERVED":
            record["remediation_state"] = "REMEDIATION_VERIFIED"
        else:
            record["remediation_state"] = "OK"
        self._append(
            "record_evaluation",
            capability_id=capability_id,
            score=score,
            checkpoint_ref=checkpoint_ref,
            new_historical_best=new_best,
            floor_breached=breached,
        )
        return record

    def check_promotion_gate(self, candidate_scores: dict) -> PromotionVerdict:
        """Governed-floor enforcement: ordinary promotion gate MUST fail when any
        governed CRITICAL capability measures below its floor - even if total
        capability improved."""
        failures = []
        for capability_id, measured in sorted(candidate_scores.items()):
            record = self.get(capability_id)
            floor = record["governed_floor"]
            if floor is None:
                continue
            if measured is None or measured < floor:
                failures.append(
                    {
                        "capability_id": capability_id,
                        "criticality": record["criticality"],
                        "governed_floor": floor,
                        "measured_candidate_value": measured,
                        "evidence_refs": list(record["evidence_refs"]),
                        "remediation_state": record["remediation_state"],
                    }
                )
        critical_failures = [f for f in failures if f["criticality"] == "CRITICAL"]
        if critical_failures:
            return PromotionVerdict(
                passed=False,
                failing_capabilities=tuple(f["capability_id"] for f in critical_failures),
                rationale="governed CRITICAL floor breach blocks promotion regardless of total improvement",
            )
        if failures:
            return PromotionVerdict(
                passed=False,
                failing_capabilities=tuple(),
                rationale="non-critical floor breaches recorded; remediation required before promotion review",
            )
        return PromotionVerdict(passed=True, failing_capabilities=tuple(), rationale="all governed floors satisfied")

    def to_document(self) -> dict:
        body = {"records": self._records, "events": self._events}
        return {**body, "integrity_hash": sha256_value(body)}

    @classmethod
    def from_document(cls, document: dict) -> "CapabilityLedger":
        if not isinstance(document, dict) or "integrity_hash" not in document:
            raise ContractError("capability ledger document missing integrity hash")
        body = {key: value for key, value in document.items() if key != "integrity_hash"}
        if sha256_value(body) != document["integrity_hash"]:
            raise ContractError("capability ledger integrity failure: tampered history")
        ledger = cls()
        ledger._records = {row["capability_id"]: row for row in document["records"].values()}
        ledger._records = document["records"]
        ledger._events = list(document["events"])
        return ledger


__all__ = [
    "CRITICALITY_LEVELS",
    "REMEDIATION_STATES",
    "REQUIRED_RECORD_FIELDS",
    "PromotionVerdict",
    "CapabilityLedger",
]
