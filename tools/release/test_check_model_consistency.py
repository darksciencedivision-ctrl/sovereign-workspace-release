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

# SWS-CORRECTIVE-01 R1. The hierarchy configures the LEGACY synthesis pipeline, which the
# shipped service never launches, so its roster deliberately differs from the product's. The
# fixture therefore names models the manifest does not, and the checks below are about the
# SCOPE DECLARATION and the absence of a product consumer - see check_hierarchy's docstring.
HIERARCHY = {
    "schema_version": 3,
    "scope": {
        "configures": "legacy-synthesis-pipeline",
        "consumed_by": ["synthesis/synth_king.py"],
        "not_consumed_by": "sovereign_product (the shipped service)",
        "product_roster_source": "SYSTEM_MANIFEST.json MODELS",
    },
    "king_synthesizer": {"role": "KING_SYNTHESIZER", "model": "deepseek-r1:8b"},
    "cross_channel": {"critique": {"role": "CROSS_CRITIC", "model": "dolphin3:8b"}},
}

PRODUCT_EVIDENCE_ONLY = {
    "evidence.py": '    "model hierarchy": "synthesis/model_hierarchy.json",\n',
    "server.py": '            "synthesis/model_hierarchy.json",\n',
    "executors.py": "# no reference to the legacy hierarchy\n",
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

    def _write(self, readme=README, hierarchy=HIERARCHY, product=None):
        with open(os.path.join(self.sov, "README_PRODUCTION.md"), "w",
                  encoding="utf-8") as f:
            f.write(readme)
        with open(os.path.join(self.sov, "synthesis", "model_hierarchy.json"),
                  "w", encoding="utf-8") as f:
            json.dump(hierarchy, f)
        package = os.path.join(self.sov, "sovereign_product")
        os.makedirs(package, exist_ok=True)
        for name, body in (product or PRODUCT_EVIDENCE_ONLY).items():
            with open(os.path.join(package, name), "w", encoding="utf-8") as f:
                f.write(body)

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

    # -- the hierarchy negative controls, replacing the old equality assertion ---------
    #
    # The old control planted `king_synthesizer.model = qwen3:14b` and required a mismatch
    # against MODELS.SYNTHESIZER. That assertion was wrong in kind - it forced two independent
    # pipelines to share one roster - so it is replaced, not removed, by controls that fail on
    # the things which actually make the scoped-apart rosters safe.

    def test_a_hierarchy_with_no_scope_declaration_is_rejected(self):
        bad = json.loads(json.dumps(HIERARCHY))
        del bad["scope"]
        self._write(hierarchy=bad)
        models = cmc.load_manifest(self.tmp)
        problems = cmc.check_hierarchy(self.tmp, models)
        self.assertTrue(any("declares no `scope`" in p for p in problems), problems)

    def test_a_hierarchy_claiming_the_product_scope_is_rejected(self):
        """A roster that says it configures the product must match the product's source."""
        bad = json.loads(json.dumps(HIERARCHY))
        bad["scope"]["configures"] = "shipped-product"
        self._write(hierarchy=bad)
        models = cmc.load_manifest(self.tmp)
        problems = cmc.check_hierarchy(self.tmp, models)
        self.assertTrue(any("scope.configures" in p for p in problems), problems)

    def test_a_wrong_product_roster_source_is_rejected(self):
        bad = json.loads(json.dumps(HIERARCHY))
        bad["scope"]["product_roster_source"] = "synthesis/model_hierarchy.json"
        self._write(hierarchy=bad)
        models = cmc.load_manifest(self.tmp)
        problems = cmc.check_hierarchy(self.tmp, models)
        self.assertTrue(any("product_roster_source" in p for p in problems), problems)

    def test_an_unusable_model_tag_in_the_scoped_roster_is_rejected(self):
        """Scoping a roster out of the product must not make it a place to put nonsense."""
        bad = json.loads(json.dumps(HIERARCHY))
        bad["king_synthesizer"]["model"] = ""
        self._write(hierarchy=bad)
        models = cmc.load_manifest(self.tmp)
        problems = cmc.check_hierarchy(self.tmp, models)
        self.assertTrue(any("not a usable model tag" in p for p in problems), problems)

    def test_a_product_file_that_consumes_the_hierarchy_is_rejected(self):
        """The scope declaration is only true while the shipped service ignores the file.

        This is the control that matters: if anything in sovereign_product ever starts
        resolving a role from the legacy hierarchy, the two rosters are no longer independent
        and the gate must fail rather than let the declaration paper over it.
        """
        product = dict(PRODUCT_EVIDENCE_ONLY)
        product["executors.py"] = (
            "hierarchy = json.load(open('synthesis/model_hierarchy.json'))\n"
            "synth = hierarchy['king_synthesizer']['model']\n"
        )
        self._write(product=product)
        models = cmc.load_manifest(self.tmp)
        problems = cmc.check_hierarchy(self.tmp, models)
        self.assertTrue(
            any("outside the evidence-document allowlist" in p for p in problems), problems)


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
