from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ContractFileTests(unittest.TestCase):
    def test_all_json_parses(self) -> None:
        for path in ROOT.rglob("*.json"):
            with self.subTest(path=path):
                json.loads(path.read_text(encoding="utf-8"))

    def test_canonical_docs_exist(self) -> None:
        for relative in ("README.md", "docs/THESIS.md", "docs/SPEC-v1.1-draft.md", "docs/DECISIONS.md", "docs/SHIP_CHECKLIST.md", "docs/integration/RC3_INTEGRATION_MAP.md"):
            self.assertTrue((ROOT / relative).is_file())

    def test_local_markdown_links_resolve(self) -> None:
        pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")
        for path in ROOT.rglob("*.md"):
            for target in pattern.findall(path.read_text(encoding="utf-8")):
                if "://" in target or target.startswith("#"):
                    continue
                local = target.split("#", 1)[0]
                if local:
                    with self.subTest(path=path, target=target):
                        self.assertTrue((path.parent / local).resolve().exists())

    def test_grounded_hg3_identity_and_trainer_registries_fail_closed(self) -> None:
        registry = json.loads((ROOT / "registry/grounded/students.json").read_text(encoding="utf-8"))
        students = {row["student_id"]: row for row in registry["students"]}
        expected = {
            "GND-STUDENT-4B": ("Qwen/Qwen3-4B-Base", "906bfd4b4dc7f14ee4320094d8b41684abff8539", "4B"),
            "GND-STUDENT-8B": ("Qwen/Qwen3-8B-Base", "49e3418fbbbca6ecbdf9608b4d22e5a407081db4", "8B"),
        }
        self.assertEqual(set(students), set(expected))
        for student_id, (repo, revision, size) in expected.items():
            with self.subTest(student_id=student_id):
                row = students[student_id]
                self.assertEqual((row["upstream_repo"], row["revision"], row["parameter_class"]), (repo, revision, size))
                self.assertEqual(row["status"], "PINNED_FOR_HG3")
                self.assertEqual(row["architecture"], "Qwen3ForCausalLM")
                self.assertEqual(row["native_context"], 32768)
                self.assertEqual(row["upstream_dtype"], "bfloat16")
                self.assertEqual(row["training_dtype"], "float16")
                self.assertEqual(row["dtype_conversion"], "explicit_runtime_cast")
                self.assertEqual(row["snapshot"]["status"], "NOT_ACQUIRED")

        trainer_registry = json.loads((ROOT / "registry/grounded/trainer.json").read_text(encoding="utf-8"))
        trainers = {row["trainer_id"]: row for row in trainer_registry["records"]}
        self.assertEqual(set(trainers), {"GND-TRAINER-GFX906", "GND-DEV-EXEC-01", "GND-TRAINER-PRIMARY"})

        retired = trainers["GND-TRAINER-GFX906"]
        self.assertEqual(retired["status"], "TARGET_NOT_FOUND")
        self.assertEqual(retired["disposition"], "RETIRED_AS_UNVERIFIED_PLANNING_TARGET")
        self.assertEqual(retired["historical_expected"]["gpu_arch"], "gfx906")
        self.assertTrue(all(value is None for value in retired["measured"].values()))

        development = trainers["GND-DEV-EXEC-01"]
        self.assertEqual(development["status"], "ACCESS_VERIFIED_LOCAL")
        self.assertEqual(development["measured"]["physical_host"], "DESKTOP-03PTABH")
        self.assertEqual(development["measured"]["gpu_model"], "NVIDIA GeForce RTX 5060 Ti")
        self.assertEqual(development["measured"]["vram_mib"], 8151)
        self.assertFalse(development["canonical_primary_trainer"])
        self.assertFalse(development["canonical_fp16_hg3_capable"])

        primary = trainers["GND-TRAINER-PRIMARY"]
        self.assertEqual(primary["status"], "UNASSIGNED")
        self.assertIsNone(primary["gpu_model"])
        self.assertEqual(primary["hardware_requirement_v1"]["provisional_minimum_usable_vram_gib"], 24)
        self.assertEqual(primary["hardware_requirement_v1"]["preferred_vram_gib"], 32)
        self.assertEqual(trainer_registry["hard_gate"]["HG-3"], "BLOCKED_HARDWARE_CAPACITY")


if __name__ == "__main__":
    unittest.main()
