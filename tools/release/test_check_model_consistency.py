#!/usr/bin/env python
"""Tests for check_model_consistency.py (SWS-REM-DIR-20260828 R2 B2-6)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_model_consistency as cmc  # noqa: E402

WORKTREE_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

MANIFEST = {
    "MODELS": {
        "PRIMARY_REASONER": "qwen3:14b",
        "ADVERSARIAL_CHALLENGER": "ornith:9b",
        "CRITIC": "qwen3:8b",
        "SYNTHESIZER": "qwen3.8:27b",
        "EMBEDDING_MODEL": "nomic-embed-text:latest",
    }
}

README = """# t

## Current default model assignments

- Primary reasoner: `qwen3:14b`
- Adversarial challenger: `ornith:9b`
- Critic: `qwen3:8b`
- Synthesizer: `qwen3.8:27b`
- Embedding model: `nomic-embed-text:latest`
"""

HIERARCHY = {
    "king_synthesizer": {"role": "KING_SYNTHESIZER", "model": "qwen3.8:27b"},
    "cross_channel": {"critique": {"role": "CROSS_CRITIC", "model": "qwen3:8b"}},
}


class ConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="model-cons-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        sov = os.path.join(self.tmp, "modules", "sovereign")
        os.makedirs(os.path.join(sov, "synthesis"))
        with open(os.path.join(sov, "SYSTEM_MANIFEST.json"), "w",
                  encoding="utf-8") as f:
            json.dump(MANIFEST, f)
        self.sov = sov

    def _write(self, readme=README, hierarchy=HIERARCHY):
        with open(os.path.join(self.sov, "README_PRODUCTION.md"), "w",
                  encoding="utf-8") as f:
            f.write(readme)
        with open(os.path.join(self.sov, "synthesis", "model_hierarchy.json"),
                  "w", encoding="utf-8") as f:
            json.dump(hierarchy, f)

    def test_consistent_passes(self):
        self._write()
        models = cmc.load_manifest(self.tmp)
        self.assertEqual(cmc.check_readme(self.tmp, models), [])
        self.assertEqual(cmc.check_hierarchy(self.tmp, models), [])

    def test_readme_mismatch_detected(self):
        self._write(readme=README.replace("ornith:9b", "qwen3:32b"))
        models = cmc.load_manifest(self.tmp)
        problems = cmc.check_readme(self.tmp, models)
        self.assertEqual(len(problems), 1)
        self.assertIn("Adversarial challenger", problems[0])

    def test_missing_bullet_detected(self):
        self._write(readme=README.replace(
            "- Embedding model: `nomic-embed-text:latest`\n", ""))
        models = cmc.load_manifest(self.tmp)
        problems = cmc.check_readme(self.tmp, models)
        self.assertTrue(any("Embedding model" in p for p in problems))

    def test_king_mismatch_detected(self):
        bad = json.loads(json.dumps(HIERARCHY))
        bad["king_synthesizer"]["model"] = "qwen3:14b"
        self._write(hierarchy=bad)
        models = cmc.load_manifest(self.tmp)
        problems = cmc.check_hierarchy(self.tmp, models)
        self.assertTrue(any("king_synthesizer" in p for p in problems))


class WorktreeConsistencyTests(unittest.TestCase):
    def test_real_worktree_consistent(self):
        if not os.path.isdir(os.path.join(WORKTREE_ROOT, "modules",
                                          "sovereign")):
            self.skipTest("worktree sovereign module absent")
        models = cmc.load_manifest(WORKTREE_ROOT)
        problems = (cmc.check_readme(WORKTREE_ROOT, models)
                    + cmc.check_hierarchy(WORKTREE_ROOT, models))
        self.assertFalse(problems, problems)


if __name__ == "__main__":
    unittest.main(verbosity=2)
