from __future__ import annotations

import unittest

from distillery.common import ContractError
from source_admission import AdmissionClass, AdmissionRegistry, SourceKey
from source_admission.d9 import ResearchFinding, apply_operator_decision


def make_registry() -> tuple:
    registry = AdmissionRegistry()
    key = SourceKey("provider.example", "teacher-a", "rev-1")
    return registry, key


SIGNED = {
    "decision": "ELIGIBLE",
    "decision_authority": "Samuel Lawson",
    "decision_authority_signed": True,
    "evidence_ref": "d9-evidence-1",
}


class D9AuthorityBoundaryTests(unittest.TestCase):
    def test_recommendation_cannot_self_authorize_eligibility(self) -> None:
        registry, key = make_registry()
        finding = ResearchFinding(
            provider=key.provider,
            teacher_or_model_id=key.teacher_or_model_id,
            revision=key.revision,
            finding="license permits output training",
            recommendation="RECOMMEND_ELIGIBLE",
        )
        with self.assertRaises(ContractError):
            apply_operator_decision(registry, key, research_finding=finding, operator_decision={
                "decision": "ELIGIBLE",
                "decision_authority": "system",
                "decision_authority_signed": True,
                "evidence_ref": finding.as_recommendation()["kind"],
            })
        self.assertIs(registry.current(key), AdmissionClass.UNKNOWN)

    def test_unsigned_fields_fail_closed(self) -> None:
        registry, key = make_registry()
        for field in ("decision", "decision_authority", "evidence_ref"):
            broken = {**SIGNED, field: ""}
            with self.subTest(field=field), self.assertRaises(ContractError):
                apply_operator_decision(registry, key, research_finding=None, operator_decision=broken)
        unsigned = {**SIGNED, "decision_authority_signed": False}
        with self.assertRaises(ContractError):
            apply_operator_decision(registry, key, research_finding=None, operator_decision=unsigned)
        self.assertIs(registry.current(key), AdmissionClass.UNKNOWN)

    def test_forbidden_authority_sentinels_rejected(self) -> None:
        registry, key = make_registry()
        for authority in ("system", "research", "recommendation", "agent", "UNSIGNED"):
            with self.subTest(authority=authority), self.assertRaises(ContractError):
                apply_operator_decision(registry, key, research_finding=None, operator_decision={**SIGNED, "decision_authority": authority})

    def test_valid_signed_operator_decision_admits_and_is_recorded(self) -> None:
        registry, key = make_registry()
        finding = ResearchFinding(
            provider=key.provider,
            teacher_or_model_id=key.teacher_or_model_id,
            revision=key.revision,
            finding="official license text examined",
            recommendation="RECOMMEND_ELIGIBLE",
            evidence_refs=("LICENSE",),
        )
        event = apply_operator_decision(registry, key, research_finding=finding, operator_decision=SIGNED)
        self.assertEqual(event.new_class, "ELIGIBLE")
        self.assertTrue(event.decision_authority.startswith("D9:"))
        self.assertIn("RECOMMEND_ELIGIBLE", event.notes)
        self.assertIs(registry.current(key), AdmissionClass.ELIGIBLE)

    def test_operator_can_reject_or_revoke_after_prior_admission(self) -> None:
        registry, key = make_registry()
        registry.transition(key, AdmissionClass.ELIGIBLE, evidence_ref="terms", decision_authority="operator")
        rejected = apply_operator_decision(
            registry, key, research_finding=None,
            operator_decision={**SIGNED, "decision": "REJECTED", "evidence_ref": "license-withdrawn"},
        )
        self.assertEqual(rejected.reason, "revoked")
        self.assertIs(registry.current(key), AdmissionClass.REJECTED)

    def test_mismatched_finding_and_invalid_decisions_fail(self) -> None:
        registry, key = make_registry()
        wrong = ResearchFinding("other", "x", "r", "text", "INSUFFICIENT_EVIDENCE")
        with self.assertRaises(ContractError):
            apply_operator_decision(registry, key, research_finding=wrong, operator_decision=SIGNED)
        with self.assertRaises(ContractError):
            apply_operator_decision(registry, key, research_finding=None, operator_decision={**SIGNED, "decision": "UNKNOWN"})
        no_op = {**SIGNED, "decision": "UNKNOWN"}
        with self.assertRaises(ContractError):
            apply_operator_decision(registry, key, research_finding=None, operator_decision=no_op)


if __name__ == "__main__":
    unittest.main()
