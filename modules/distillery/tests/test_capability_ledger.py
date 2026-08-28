from __future__ import annotations

import unittest

from distillery.common import ContractError
from gate.capability import (
    REQUIRED_RECORD_FIELDS,
    CapabilityLedger,
)


def make_ledger() -> CapabilityLedger:
    ledger = CapabilityLedger()
    ledger.register(
        capability_id="CAP-TOOL-REPAIR",
        description="targeted repair capability on frozen deterministic suite",
        criticality="CRITICAL",
        evaluation_suite="suite-v1",
        target_margin=0.05,
        parent_regression_margin=0.02,
        historical_regression_margin=0.02,
    )
    ledger.register(
        capability_id="CAP-NICE-EXTRA",
        description="secondary convenience capability",
        criticality="STANDARD",
        evaluation_suite="suite-v1",
    )
    return ledger


class CapabilityLedgerTests(unittest.TestCase):
    def test_record_carries_all_directive_fields(self) -> None:
        ledger = make_ledger()
        for record in ledger.to_document()["records"].values():
            self.assertTrue(set(REQUIRED_RECORD_FIELDS).issubset(record.keys()))

    def test_history_is_append_preserving_and_best_separable(self) -> None:
        ledger = make_ledger()
        ledger.record_evaluation("CAP-TOOL-REPAIR", score=0.70, checkpoint_ref="ckpt-a")
        ledger.set_governed_floor("CAP-TOOL-REPAIR", floor_value=0.60, authority_ref="DECISIONS-v1#1")
        ledger.record_evaluation("CAP-TOOL-REPAIR", score=0.65, checkpoint_ref="ckpt-b")
        record = ledger.get("CAP-TOOL-REPAIR")
        self.assertEqual(record["current_score"], 0.65)
        self.assertEqual(record["historical_best_score"], 0.70)
        self.assertEqual(record["historical_best_checkpoint"], "ckpt-a")
        actions = [event["action"] for event in ledger.events]
        self.assertEqual(actions.count("record_evaluation"), 2)
        self.assertGreaterEqual(len(ledger.events), 4)

    def test_critical_floor_breach_blocks_promotion_despite_total_gain(self) -> None:
        ledger = make_ledger()
        ledger.set_governed_floor("CAP-TOOL-REPAIR", floor_value=0.60, authority_ref="DECISIONS-v1#1")
        verdict = ledger.check_promotion_gate({"CAP-TOOL-REPAIR": 0.55, "CAP-NICE-EXTRA": 0.95})
        self.assertFalse(verdict.passed)
        self.assertIn("CAP-TOOL-REPAIR", verdict.failing_capabilities)
        failure = ledger.check_promotion_gate({"CAP-TOOL-REPAIR": 0.55})
        self.assertEqual(failure.to_dict()["failing_capabilities"], ["CAP-TOOL-REPAIR"])

    def test_passing_verdict_when_all_floors_satisfied(self) -> None:
        ledger = make_ledger()
        ledger.set_governed_floor("CAP-TOOL-REPAIR", floor_value=0.60, authority_ref="DECISIONS-v1#1")
        verdict = ledger.check_promotion_gate({"CAP-TOOL-REPAIR": 0.75, "CAP-NICE-EXTRA": 0.10})
        self.assertTrue(verdict.passed)

    def test_floor_lowering_after_observation_requires_authorized_transition(self) -> None:
        ledger = make_ledger()
        ledger.set_governed_floor("CAP-TOOL-REPAIR", floor_value=0.60, authority_ref="DECISIONS-v1#1")
        ledger.record_evaluation("CAP-TOOL-REPAIR", score=0.61, checkpoint_ref="ckpt-a")
        with self.assertRaises(ContractError):
            ledger.set_governed_floor("CAP-TOOL-REPAIR", floor_value=0.40, authority_ref="operator")
        with self.assertRaises(ContractError):
            ledger.set_governed_floor(
                "CAP-TOOL-REPAIR", floor_value=0.40, authority_ref="operator",
                authorized_policy_transition={"ref": "r", "authority": "system", "reason": "make it pass"},
            )
        ledger.set_governed_floor(
            "CAP-TOOL-REPAIR", floor_value=0.40, authority_ref="operator",
            authorized_policy_transition={"ref": "DECISIONS-v1 amendment", "authority": "Samuel Lawson", "reason": "recalibrated from measured variance"},
        )
        self.assertEqual(ledger.get("CAP-TOOL-REPAIR")["governed_floor"], 0.40)

    def test_floor_raising_needs_only_authority_ref(self) -> None:
        ledger = make_ledger()
        ledger.set_governed_floor("CAP-TOOL-REPAIR", floor_value=0.60, authority_ref="DECISIONS-v1#1")
        ledger.record_evaluation("CAP-TOOL-REPAIR", score=0.9, checkpoint_ref="c")
        ledger.set_governed_floor("CAP-TOOL-REPAIR", floor_value=0.80, authority_ref="DECISIONS-v1#1")
        self.assertEqual(ledger.get("CAP-TOOL-REPAIR")["governed_floor"], 0.80)

    def test_breach_marks_remediation_state_and_recovery(self) -> None:
        ledger = make_ledger()
        ledger.set_governed_floor("CAP-TOOL-REPAIR", floor_value=0.60, authority_ref="D#1")
        breached = ledger.record_evaluation("CAP-TOOL-REPAIR", score=0.50, checkpoint_ref="bad")
        self.assertEqual(breached["remediation_state"], "FLOOR_BREACH_OBSERVED")
        recovered = ledger.record_evaluation("CAP-TOOL-REPAIR", score=0.85, checkpoint_ref="good")
        self.assertEqual(recovered["remediation_state"], "REMEDIATION_VERIFIED")

    def test_document_roundtrip_detects_tampering(self) -> None:
        ledger = make_ledger()
        ledger.set_governed_floor("CAP-TOOL-REPAIR", floor_value=0.6, authority_ref="D#1")
        document = ledger.to_document()
        restored = CapabilityLedger.from_document(document)
        self.assertEqual(restored.integrity_snapshot(), ledger.integrity_snapshot())
        document["records"]["CAP-TOOL-REPAIR"]["governed_floor"] = 0.01
        with self.assertRaises(ContractError):
            CapabilityLedger.from_document(document)

    def test_invalid_registration_rejected(self) -> None:
        ledger = make_ledger()
        with self.assertRaises(ContractError):
            ledger.register(capability_id="X", description="d", criticality="VITAL", evaluation_suite="s")
        with self.assertRaises(ContractError):
            ledger.register(capability_id="CAP-TOOL-REPAIR", description="dup", criticality="HIGH", evaluation_suite="s")


if __name__ == "__main__":
    unittest.main()
