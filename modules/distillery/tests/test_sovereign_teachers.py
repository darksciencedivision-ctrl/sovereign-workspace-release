from __future__ import annotations

import json
import unittest
from pathlib import Path

from distillery.common import ContractError
from sovereign import (
    UNORDERED_CLASSIFICATION,
    capability_delta_record_path,
    eligibility_interaction,
    field_provenance,
    load_teacher_registry,
    order_teachers,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "registry" / "sovereign" / "teachers.json"


class TeacherRegistryToolingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = load_teacher_registry(REGISTRY)
        cls.teachers = cls.document["teachers"]

    def test_real_registry_parses_deterministically(self) -> None:
        again = load_teacher_registry(REGISTRY)
        self.assertEqual(self.document, again)
        self.assertEqual(self.document["teacher_count"], len(self.teachers))
        ids = [t["model_id"] for t in self.teachers]
        self.assertEqual(len(ids), len(set(ids)))

    def test_ordering_is_smallest_to_largest_and_never_invents_parameters(self) -> None:
        first = order_teachers(self.teachers)
        second = order_teachers(list(reversed(self.teachers)))
        self.assertEqual(first, second)
        counts = [row["parameter_count"] for row in first["processing_plan"]]
        self.assertEqual(counts, sorted(counts))
        for row in first["unordered_explicit"]:
            self.assertEqual(row["skip_reason"].split(":")[0], UNORDERED_CLASSIFICATION)
            self.assertIsNone(row["processing_position"])
        known = {t["model_id"] for t in self.teachers if t.get("parameter_count")}
        planned = {row["model_id"] for row in first["processing_plan"]}
        self.assertEqual(known, planned)

    def test_field_provenance_separates_measured_from_derived_and_unknown(self) -> None:
        measured = next(t for t in self.teachers if t.get("parameter_count"))
        unknown = next(t for t in self.teachers if not t.get("parameter_count"))
        provenance_measured = field_provenance(measured)
        self.assertEqual(provenance_measured["parameter_count"], "MEASURED_FROM_ARTIFACT")
        provenance_unknown = field_provenance(unknown)
        self.assertEqual(provenance_unknown["parameter_count"], "UNKNOWN_NOT_INVENTED")
        if unknown.get("parameter_label"):
            self.assertEqual(provenance_unknown["parameter_label"], "DERIVED_LABEL")
        self.assertEqual(provenance_unknown["artifact_content_hash"], "UNKNOWN_NOT_YET_HASHED")

    def test_license_unknown_blocks_teacher_use_even_when_admitted(self) -> None:
        teacher = next(t for t in self.teachers if t["license_class"] == "UNKNOWN")
        verdict = eligibility_interaction(teacher, "ELIGIBLE")
        self.assertFalse(verdict["trainable_as_teacher"])
        self.assertIn("primary license text", verdict["reason"])
        verified = dict(teacher, license_class="VERIFIED_APACHE_2")
        self.assertTrue(eligibility_interaction(verified, "ELIGIBLE")["trainable_as_teacher"])
        with self.assertRaises(ContractError):
            eligibility_interaction(verified, "REJECTED")

    def test_capability_delta_path_is_deterministic_per_suite(self) -> None:
        path_a = capability_delta_record_path("runs/x", "T001", "suiteA")
        path_b = capability_delta_record_path("runs/x", "T001", "suiteA")
        path_c = capability_delta_record_path("runs/x", "T001", "suiteB")
        self.assertEqual(path_a, path_b)
        self.assertNotEqual(path_a, path_c)
        with self.assertRaises(ContractError):
            capability_delta_record_path("runs/x", "", "suite")

    def test_tampered_registry_rejected(self) -> None:
        broken = {**self.document, "teacher_count": 999}
        from sovereign import validate_registry_document

        with self.assertRaises(ContractError):
            validate_registry_document(broken)
        duplicated = {**self.document, "teachers": self.teachers + [dict(self.teachers[0])], "teacher_count": len(self.teachers) + 1}
        with self.assertRaises(ContractError):
            validate_registry_document(duplicated)


if __name__ == "__main__":
    unittest.main()
