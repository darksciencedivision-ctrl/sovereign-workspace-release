from __future__ import annotations

"""SD-RBR-v1.0 W-3: the cold-restore evidence must be machine-checked, not prose.

Locks in that COLD_RESTORE_RECORD.json exists with a PASS verdict and an empty
mismatch list, that its bundle hash is verifiable against the tracked bundle,
and that EVIDENCE_INDEX F-21/F-24 reference the tool, the record, and real
hashes instead of a prose-only sentence.
"""

import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD_PATH = ROOT / "runs" / "export" / "COLD_RESTORE_RECORD.json"
BUNDLE_PATH = ROOT / "runs" / "export" / "SOVEREIGN_DISTILLERY_fa89a2b9.bundle"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ColdRestoreRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = json.loads(RECORD_PATH.read_text(encoding="utf-8"))
        cls.index = json.loads(
            (ROOT / "runs" / "completion-loop" / "EVIDENCE_INDEX.json").read_text(encoding="utf-8")
        )["requirements"]

    def test_record_exists_with_pass_verdict(self) -> None:
        self.assertEqual(self.record["kind"], "COLD_RESTORE_RECORD")
        self.assertEqual(self.record["verdict"], "PASS")
        self.assertTrue(self.record["temp_clone_cleaned_up"])

    def test_restored_head_matches_declared_source_commit(self) -> None:
        self.assertEqual(self.record["restored_head"], self.record["source_commit"])
        self.assertRegex(self.record["source_commit"], r"^[0-9a-f]{40}$")

    def test_blob_comparison_is_complete_and_clean(self) -> None:
        self.assertGreater(self.record["files_compared"], 0)
        self.assertEqual(self.record["mismatches"], [])

    def test_bundle_sha256_matches_tracked_bundle(self) -> None:
        self.assertTrue(BUNDLE_PATH.is_file(), "tracked bundle missing; cold-restore evidence would be unverifiable")
        self.assertTrue(HEX64.match(self.record["bundle_sha256"]))
        self.assertEqual(_sha256_file(BUNDLE_PATH), self.record["bundle_sha256"])

    def test_suite_ran_green_inside_restored_tree(self) -> None:
        self.assertEqual(self.record["suite"]["exit_code"], 0)
        self.assertRegex(self.record["suite"]["result"] or "", r"^\d+ passed")

    def test_evidence_index_references_tool_record_and_hashes(self) -> None:
        for item_id in ("F-21", "F-24"):
            with self.subTest(item=item_id):
                entry = self.index[item_id]
                joined_tests = " ".join(entry.get("tests", []))
                self.assertIn("tools/verify_cold_restore.py", joined_tests)
                self.assertIn("runs/export/COLD_RESTORE_RECORD.json", entry.get("reports", []))
                self.assertTrue(entry.get("hashes"), f"{item_id} hashes must be populated")
                self.assertTrue(
                    any(self.record["bundle_sha256"] in value for value in entry["hashes"]),
                    f"{item_id} hashes must carry the verified bundle sha256",
                )

    def test_no_f_item_retains_prose_only_tests_entry(self) -> None:
        for item_id, entry in self.index.items():
            for value in entry.get("tests", []):
                looks_machine_checkable = (
                    value.endswith(".py") or "::" in value or value.startswith(("python ", "tools/", "git "))
                )
                with self.subTest(item=item_id, value=value):
                    self.assertTrue(looks_machine_checkable, f"prose-only tests entry: {value!r}")


class PostRemediationColdRestoreTests(unittest.TestCase):
    """SD-RBR-v1.1 R-4: the terminal state carries its own restore proof.

    The independently verified fa89a2b9 record remains untouched; this class
    locks the additional post-remediation record at db83a94c.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.record = json.loads(
            (ROOT / "runs" / "export" / "COLD_RESTORE_RECORD_db83a94c.json").read_text(encoding="utf-8")
        )

    def test_record_exists_with_pass_verdict(self) -> None:
        self.assertEqual(self.record["kind"], "COLD_RESTORE_RECORD")
        self.assertEqual(self.record["verdict"], "PASS")

    def test_locus_and_blob_parity(self) -> None:
        self.assertEqual(self.record["source_commit"], "db83a94cbcd665cecd9c59134800fc084d86c5ca")
        self.assertEqual(self.record["restored_head"], self.record["source_commit"])
        self.assertGreater(self.record["files_compared"], 0)
        self.assertEqual(self.record["mismatches"], [])

    def test_bundle_hash_verifiable_against_tracked_bundle(self) -> None:
        bundle = ROOT / "runs" / "export" / "SOVEREIGN_DISTILLERY_db83a94c.bundle"
        self.assertTrue(bundle.is_file())
        self.assertEqual(_sha256_file(bundle), self.record["bundle_sha256"])

    def test_suite_green_inside_restored_tree(self) -> None:
        self.assertEqual(self.record["suite"]["exit_code"], 0)
        self.assertRegex(self.record["suite"]["result"] or "", r"^\d+ passed")

    def test_verified_fa89a2b9_record_untouched_in_place(self) -> None:
        prior = json.loads((ROOT / "runs" / "export" / "COLD_RESTORE_RECORD.json").read_text(encoding="utf-8"))
        self.assertEqual(prior["verdict"], "PASS")
        self.assertEqual(prior["source_commit"], "fa89a2b94ca6946714f44e3853771907caed6503")


if __name__ == "__main__":
    unittest.main()