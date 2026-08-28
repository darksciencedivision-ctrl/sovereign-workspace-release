from __future__ import annotations

import unittest
from pathlib import Path

from tools.raw_source_classification import classification_report, classify

ROOT = Path(__file__).resolve().parents[1]


class RawSourceClassificationTests(unittest.TestCase):
    def test_historically_ambiguous_files_resolve_by_rule(self) -> None:
        report = classification_report(ROOT)
        self.assertEqual(report["ambiguous_count"], 0)
        self.assertEqual(report["mapping"]["tests/test_contract_files.py"], "SHARED_DISTILLERY_CORE")
        self.assertEqual(report["mapping"]["tests/test_source_and_shards.py"], "SHARED_DISTILLERY_CORE")

    def test_every_tracked_file_receives_exactly_one_non_ambiguous_class(self) -> None:
        report = classification_report(ROOT)
        self.assertEqual(sum(report["counts"].values()), len(report["mapping"]))
        self.assertNotIn("AMBIGUOUS", report["counts"])

    def test_sovereign_and_grounded_domains_classify_deterministically(self) -> None:
        self.assertEqual(classify("sovereign/teachers.py"), "SOVEREIGN_SPECIFIC")
        self.assertEqual(classify("tools/sovereign/d2_registry.py"), "SOVEREIGN_TOOLS")
        self.assertEqual(classify("registry/sovereign/teachers.json"), "SOVEREIGN_SPECIFIC")
        self.assertEqual(classify("grounded/cli.py"), "EXCLUDED_GROUNDED_ONLY_OR_NONESSENTIAL_CONFIGURATION")
        self.assertEqual(classify("registry/grounded/trainer.json"), "EXCLUDED_GROUNDED_ONLY_OR_NONESSENTIAL_CONFIGURATION")
        # Rule: any test importing treaty-shared packages is SHARED_DISTILLERY_CORE,
        # even when it primarily exercises Sovereign subsystems.
        self.assertEqual(classify("tests/test_sovereign_teachers.py"), "SHARED_DISTILLERY_CORE")
        # Export policy allows .py/.ps1/.psm1/.psd1/.json only; .toml is nonessential.
        self.assertEqual(classify("pyproject.toml"), "EXCLUDED_NONESSENTIAL")


if __name__ == "__main__":
    unittest.main()
