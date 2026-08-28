#!/usr/bin/env python
"""Tests for release_manifest_check.py (SWS-REM-DIR-20260828 R2 B2-2).

Stdlib-only, offline. Includes the real-worktree pass proof and tamper
detection (corrupted hash, missing enumerated file).
"""

from __future__ import annotations

import copy
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import release_manifest_check as rmc  # noqa: E402

WORKTREE_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
MANIFEST = os.path.join(WORKTREE_ROOT, "RELEASE-MANIFEST.json")


def load_manifest():
    with open(MANIFEST, "r", encoding="utf-8") as f:
        return json.load(f)


class ManifestValidatorTests(unittest.TestCase):
    def setUp(self):
        if not os.path.isfile(MANIFEST):
            self.skipTest("worktree RELEASE-MANIFEST.json not present")
        self.manifest = load_manifest()

    def test_real_manifest_passes(self):
        problems = rmc.check(WORKTREE_ROOT, self.manifest)
        self.assertFalse(problems, problems)

    def test_corrupted_record_hash_detected(self):
        tampered = copy.deepcopy(self.manifest)
        entry = tampered["modules"]["sovereign"]
        entry["provenance_record_sha256"] = "0" * 64
        problems = rmc.check(WORKTREE_ROOT, tampered)
        self.assertTrue(any("provenance record hash mismatch" in p
                            for p in problems), problems)

    def test_corrupted_lock_hash_detected(self):
        tampered = copy.deepcopy(self.manifest)
        entry = tampered["modules"]["debate"]
        entry["locks"][0]["sha256"] = "f" * 64
        problems = rmc.check(WORKTREE_ROOT, tampered)
        self.assertTrue(any("locks hash mismatch" in p for p in problems),
                        problems)

    def test_missing_superseded_path_detected(self):
        tampered = copy.deepcopy(self.manifest)
        tampered["modules"]["sow"]["superseded_provenance_paths"].append(
            "modules/sow/THIS-DOES-NOT-EXIST.previous.json")
        problems = rmc.check(WORKTREE_ROOT, tampered)
        self.assertTrue(any("superseded record missing" in p for p in problems),
                        problems)

    def test_record_source_identity_consistency_enforced(self):
        tampered = copy.deepcopy(self.manifest)
        tampered["modules"]["distillery"]["source_identity"][
            "content_digest_sha256"] = "a" * 64
        problems = rmc.check(WORKTREE_ROOT, tampered)
        self.assertTrue(any("source identity" in p for p in problems), problems)

    def test_no_glob_enumeration(self):
        """Every enumerated path must be a concrete path, never a pattern."""
        def walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(k, str) and k.endswith("_path") or k == "path":
                        if isinstance(v, str):
                            self.assertFalse(
                                any(c in v for c in "*?["),
                                f"glob-like enumerated path: {v}")
                    walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)
        walk(self.manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
