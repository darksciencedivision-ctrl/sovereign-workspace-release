from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from distillery.common import ContractError, utc_now
from source_admission import AdmissionClass, AdmissionRegistry, AdmissionEvent, SourceKey

DECISION_CLASSES = ("ELIGIBLE", "INTERNAL_ONLY", "REJECTED")
FORBIDDEN_AUTHORITY_SENTINELS = frozenset(
    {"system", "research", "recommendation", "automated", "loop", "agent", "unsigned"}
)


@dataclass(frozen=True)
class ResearchFinding:
    """A primary-source research observation. Carries no admission authority."""

    provider: str
    teacher_or_model_id: str
    revision: str
    finding: str
    recommendation: Literal["RECOMMEND_ELIGIBLE", "RECOMMEND_INTERNAL_ONLY", "RECOMMEND_REJECTED", "INSUFFICIENT_EVIDENCE"]
    evidence_refs: tuple = ()
    researched_at: str = ""

    def __post_init__(self) -> None:
        if not all((self.provider, self.teacher_or_model_id, self.revision, self.finding)):
            raise ContractError("research finding requires complete source identity and finding text")
        if self.recommendation not in {"RECOMMEND_ELIGIBLE", "RECOMMEND_INTERNAL_ONLY", "RECOMMEND_REJECTED", "INSUFFICIENT_EVIDENCE"}:
            raise ContractError(f"invalid research recommendation: {self.recommendation}")

    def as_recommendation(self) -> dict:
        return {
            "kind": "SYSTEM_RECOMMENDATION",
            "lineage_id": f"{self.provider}:{self.teacher_or_model_id}:{self.revision}",
            "recommendation": self.recommendation,
            "authorizes_admission": False,
            "evidence_refs": list(self.evidence_refs),
        }


def apply_operator_decision(
    registry: AdmissionRegistry,
    key: SourceKey,
    *,
    research_finding: ResearchFinding | None,
    operator_decision: dict,
) -> AdmissionEvent:
    """Apply a human D-9 source-admission decision.

    Separation enforced structurally:
        research finding != system recommendation != human authorization.
    The decision fails closed unless an explicit, fully-signed operator
    decision is supplied. Recommendations - whether attached to a finding or
    standalone - can never substitute for the operator signature.
    """
    required = ("decision", "decision_authority", "evidence_ref")
    missing = [name for name in required if not isinstance(operator_decision.get(name), str) or not operator_decision.get(name, "").strip()]
    if missing:
        raise ContractError(f"operator decision is unsigned: missing {missing}")
    decision = operator_decision["decision"].strip().upper()
    authority = operator_decision["decision_authority"].strip()
    if decision not in DECISION_CLASSES:
        raise ContractError(f"operator decision must be one of {DECISION_CLASSES}: got {decision!r}")
    if authority.lower() in FORBIDDEN_AUTHORITY_SENTINELS:
        raise ContractError(
            f"authority {authority!r} is a forbidden self-authorization sentinel: D-9 decisions require a named human operator"
        )
    if operator_decision.get("decision_authority_signed") is not True:
        raise ContractError("operator decision_authority_signed must be true (explicit human signature)")
    target = AdmissionClass(decision)
    current = registry.current(key)
    if target is current:
        raise ContractError(f"no-op operator decision: source already {current.value}")

    notes_parts = []
    if research_finding is not None:
        if not isinstance(research_finding, ResearchFinding):
            raise ContractError(
                "research attachment must be a source_admission.d9.ResearchFinding: "
                "dossiers and recommendations are not decision authority"
            )
        if (research_finding.provider, research_finding.teacher_or_model_id, research_finding.revision) != (key.provider, key.teacher_or_model_id, key.revision):
            raise ContractError("attached research finding does not match the decision subject")
        notes_parts.append(f"research:{research_finding.recommendation}")
    notes = ";".join(notes_parts)

    return registry.transition(
        key,
        target,
        evidence_ref=operator_decision["evidence_ref"],
        decision_authority=f"D9:{authority}",
        effective_time=operator_decision.get("decided_at") or utc_now(),
        notes=notes,
        reason="revoked" if target is AdmissionClass.REJECTED else "d9-operator-decision",
    )


__all__ = ["ResearchFinding", "apply_operator_decision", "DECISION_CLASSES", "FORBIDDEN_AUTHORITY_SENTINELS"]
