from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(*relative_paths: str) -> str:
    return "\n".join((ROOT / path).read_text(encoding="utf-8") for path in relative_paths)


class TreatyContractTests(unittest.TestCase):
    def test_import_map_destination_hashes(self) -> None:
        mapping = (ROOT / "docs/integration/SOVEREIGN_CANON_IMPORT_MAP.md").read_text(encoding="utf-8")
        checked = 0
        row = re.compile(
            r"^\| `[^`]+` \| `([^`]+)` \| `[0-9a-f]{64}` \| `([0-9a-f]{64})` \| \*\*(?:CANONICAL_IMPORT|REFERENCE_ONLY)\*\* \|",
            re.MULTILINE,
        )
        for destination, expected_hash in row.findall(mapping):
            with self.subTest(destination=destination):
                observed = hashlib.sha256((ROOT / destination).read_bytes()).hexdigest()
                self.assertEqual(observed, expected_hash)
            checked += 1
        self.assertEqual(checked, 20)

    def test_grounded_scope_contract(self) -> None:
        grounded = text("docs/THESIS.md")
        for doctrine in (
            "one measured operational workload",
            "one designated synthesis teacher",
            "The working candidate range is a planning envelope, not a permanent architecture ceiling",
            "One 4B/8B student result does not impose a permanent Sovereign scale ceiling",
        ):
            with self.subTest(doctrine=doctrine):
                self.assertIn(doctrine, grounded)

    def test_sovereign_scope_contract(self) -> None:
        sovereign = text(
            "docs/sovereign/DESIGN.md",
            "docs/sovereign/VALIDATION.md",
            "docs/sovereign/DECISIONS-v1.md",
            "docs/sovereign/INVARIANTS.md",
            "docs/sovereign/KNOWLEDGE_LINEAGE.md",
        )
        for doctrine in (
            "persistent Sovereign model lineage",
            "smallest-to-largest",
            "SKIPPED_NO_DELTA",
            "no useful capability delta",
            "Model scale does not increase automatically",
            "native Sovereign trajectory",
            "governed floor",
            "human operator retains final canonical promotion authority",
        ):
            with self.subTest(doctrine=doctrine):
                self.assertIn(doctrine, sovereign)

    def test_shared_infrastructure_and_fail_closed_registry_contract(self) -> None:
        expected_paths = (
            "validators/__init__.py",
            "schema/shard.json",
            "curation/shard.py",
            "exclusion/__init__.py",
            "gate/paired.py",
            "gate/historical.py",
            "ops/evidence.py",
            "ops/promotion.py",
            "train/card_lock.py",
            "docs/integration/SOVEREIGN_CANON_IMPORT_MAP.md",
        )
        for relative in expected_paths:
            with self.subTest(relative=relative):
                self.assertTrue((ROOT / relative).is_file())
        shared = text("docs/THESIS.md", "docs/sovereign/INVARIANTS.md")
        for doctrine in (
            "provenance",
            "immutable",
            "exclusion",
            "paired",
            "historical-best",
            "evidence",
            "rollback",
        ):
            with self.subTest(doctrine=doctrine):
                self.assertIn(doctrine.lower(), shared.lower())
        registry = json.loads((ROOT / "registry/sovereign/teachers.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["teacher_count"], 43)
        self.assertTrue(all(item["license_class"] == "UNKNOWN" for item in registry["teachers"]))
        self.assertTrue(all("path" not in item for item in registry["teachers"]))


if __name__ == "__main__":
    unittest.main()
