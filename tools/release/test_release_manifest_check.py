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

    def test_corrupted_batch_file_hash_detected(self):
        tampered = copy.deepcopy(self.manifest)
        self.assertTrue(tampered.get("batch_files"),
                        "manifest has no batch_files enumeration")
        tampered["batch_files"][0]["sha256"] = "e" * 64
        problems = rmc.check(WORKTREE_ROOT, tampered)
        self.assertTrue(any("batch_files: hash mismatch" in p for p in problems),
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


class UncheckedHashSectionTests(unittest.TestCase):
    """CLOSEOUT-01 X-1 / standing rule S-15.

    A manifest may not carry a ``path``+``sha256`` pair that this checker does
    not actually verify. Before the X-1 hardening every one of these cases
    returned PASS (see bundles/CLOSEOUT01/X-1/fail-before.txt, captured against
    the pristine bytes of 32f191e): 17 wrong release-artifact hashes passed, an
    invented section passed, and corrupting identity_documents or ui_assets
    passed. The A-1 defect was that silence, not the wrong numbers.
    """

    def setUp(self):
        if not os.path.isfile(MANIFEST):
            self.skipTest("worktree RELEASE-MANIFEST.json not present")
        self.manifest = load_manifest()

    def test_unknown_hash_bearing_section_is_rejected(self):
        tampered = copy.deepcopy(self.manifest)
        tampered["a_future_section_nobody_taught_the_checker_about"] = [
            {"path": "VERSION.json", "sha256": "0" * 64}
        ]
        problems = rmc.check(WORKTREE_ROOT, tampered)
        self.assertTrue(
            any("unverified hash-bearing entry" in p for p in problems),
            problems)

    def test_unknown_section_rejected_even_when_its_hash_is_correct(self):
        """Rejection is for being unverified, not merely for being wrong."""
        version_path = os.path.join(WORKTREE_ROOT, "VERSION.json")
        correct = rmc.sha256_file(version_path)
        tampered = copy.deepcopy(self.manifest)
        tampered["some_new_section"] = [{"path": "VERSION.json",
                                         "sha256": correct}]
        problems = rmc.check(WORKTREE_ROOT, tampered)
        self.assertTrue(
            any("unverified hash-bearing entry" in p for p in problems),
            problems)

    def test_hash_added_inside_a_handled_section_is_still_caught(self):
        """Identity tracking, not key names: a new group under an already
        handled section cannot smuggle an unverified hash through."""
        tampered = copy.deepcopy(self.manifest)
        tampered["modules"]["sovereign"]["extra_unchecked_files"] = [
            {"path": "VERSION.json", "sha256": "1" * 64}
        ]
        problems = rmc.check(WORKTREE_ROOT, tampered)
        self.assertTrue(
            any("unverified hash-bearing entry" in p for p in problems),
            problems)

    def test_release_archive_hashes_are_not_carried_by_this_manifest(self):
        """A-1 structural fix: a tracked manifest enters the archive it would
        describe, so it must carry no release-artifact hash at all."""
        self.assertNotIn("release_archives_gitignored", self.manifest)
        self.assertEqual(
            self.manifest.get("release_archive_hash_authority"),
            "release-artifacts/release-build-manifest.json")
        for section, entries in self.manifest.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                    self.assertFalse(
                        entry["path"].startswith("release-artifacts/"),
                        f"{section} enumerates a release artifact: {entry['path']}")


class HandledSectionsStillValidateTests(unittest.TestCase):
    """The hardening must not have been achieved by checking less."""

    def setUp(self):
        if not os.path.isfile(MANIFEST):
            self.skipTest("worktree RELEASE-MANIFEST.json not present")
        self.manifest = load_manifest()

    def test_real_manifest_still_passes_after_hardening(self):
        problems = rmc.check(WORKTREE_ROOT, self.manifest)
        self.assertFalse(problems, problems)

    def test_every_hash_bearing_entry_is_covered(self):
        """Counts the whole file, so a section added later without a checker
        change fails here as well as at the gate."""
        found = list(rmc._hash_bearing_objects(self.manifest))
        self.assertTrue(found, "manifest carries no hash-bearing entries")
        problems = rmc.check(WORKTREE_ROOT, self.manifest)
        self.assertFalse([p for p in problems
                          if "unverified hash-bearing entry" in p], problems)

    def test_corrupted_identity_document_hash_detected(self):
        tampered = copy.deepcopy(self.manifest)
        tampered["identity_documents"][0]["sha256"] = "f" * 64
        problems = rmc.check(WORKTREE_ROOT, tampered)
        self.assertTrue(
            any("identity_documents: hash mismatch" in p for p in problems),
            problems)

    def test_corrupted_ui_asset_hash_detected(self):
        tampered = copy.deepcopy(self.manifest)
        tampered["ui_assets"][0]["sha256"] = "e" * 64
        problems = rmc.check(WORKTREE_ROOT, tampered)
        self.assertTrue(
            any("ui_assets: hash mismatch" in p for p in problems), problems)

    def test_missing_identity_document_detected(self):
        tampered = copy.deepcopy(self.manifest)
        tampered["identity_documents"].append(
            {"path": "THIS-DOES-NOT-EXIST.json", "sha256": "a" * 64})
        problems = rmc.check(WORKTREE_ROOT, tampered)
        self.assertTrue(
            any("identity_documents: file missing" in p for p in problems),
            problems)


if __name__ == "__main__":
    unittest.main(verbosity=2)
