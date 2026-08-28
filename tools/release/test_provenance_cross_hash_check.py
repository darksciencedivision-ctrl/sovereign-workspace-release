#!/usr/bin/env python
"""Tests for provenance_cross_hash_check.py (SWS-REM-DIR-20260828 R2 B2-1).

Proves the mechanical rejection of the C-2 defect class: a provenance record
carrying another module's registered source hash must FAIL (CROSS), an
unregistered hash must FAIL (UNKNOWN), a missing current record for a
registered module must FAIL (MISSING), pending modules are PENDING, and a
correct hash passes. Stdlib-only, offline.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import provenance_cross_hash_check as phc  # noqa: E402

WORKTREE_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
REGISTRY = os.path.join(HERE, "module_source_registry.json")

SOV_HASH = "150e518e6d0b15b524ff61cda8fe8eb29aec6bbfb30196f9931908d12ff7ec51"
DIS_HASH = "620e8459c74fb5fe9d2dfe0c4693cea02b8346292804d2d2a01fb71cb615be96"


def make_registry(tmp, entries):
    path = os.path.join(tmp, "registry.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "modules": entries}, f)
    return path


def write_record(tmp, rel, source_sha256):
    full = os.path.join(tmp, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        json.dump({"module": rel.split("/")[1], "source_sha256": source_sha256}, f)


class CrossHashTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="phc-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _two_module_registry(self):
        return make_registry(self.tmp, {
            "alpha": {"provenance_path": "modules/alpha/INSTALL-PROVENANCE.json",
                      "source_sha256": SOV_HASH, "status": "verified"},
            "beta": {"provenance_path": "modules/beta/INSTALL-PROVENANCE.json",
                     "source_sha256": DIS_HASH, "status": "verified"},
        })

    def test_cross_module_hash_rejected(self):
        """The C-2 defect class: alpha carrying beta's hash must FAIL."""
        reg = self._two_module_registry()
        write_record(self.tmp, "modules/alpha/INSTALL-PROVENANCE.json", DIS_HASH)
        write_record(self.tmp, "modules/beta/INSTALL-PROVENANCE.json", DIS_HASH)
        res = phc.check(self.tmp, phc.load_registry(reg))
        self.assertEqual(res["alpha"]["verdict"], "CROSS", res)
        self.assertIn("beta", res["alpha"]["detail"])
        self.assertEqual(res["beta"]["verdict"], "OK")

    def test_own_hash_passes(self):
        reg = self._two_module_registry()
        write_record(self.tmp, "modules/alpha/INSTALL-PROVENANCE.json", SOV_HASH)
        write_record(self.tmp, "modules/beta/INSTALL-PROVENANCE.json", DIS_HASH)
        res = phc.check(self.tmp, phc.load_registry(reg))
        self.assertEqual(res["alpha"]["verdict"], "OK", res)
        self.assertEqual(res["beta"]["verdict"], "OK", res)

    def test_unknown_hash_rejected(self):
        reg = self._two_module_registry()
        write_record(self.tmp, "modules/alpha/INSTALL-PROVENANCE.json", "f" * 64)
        res = phc.check(self.tmp, phc.load_registry(reg))
        self.assertEqual(res["alpha"]["verdict"], "UNKNOWN", res)

    def test_missing_registered_record_fails(self):
        reg = self._two_module_registry()
        write_record(self.tmp, "modules/beta/INSTALL-PROVENANCE.json", DIS_HASH)
        res = phc.check(self.tmp, phc.load_registry(reg))
        self.assertEqual(res["alpha"]["verdict"], "MISSING", res)

    def test_pending_module_reported_pending_not_failed(self):
        reg = make_registry(self.tmp, {
            "gamma": {"provenance_path": "modules/gamma/INSTALL-PROVENANCE.json",
                      "source_sha256": None, "status": "pending"},
        })
        res = phc.check(self.tmp, phc.load_registry(reg))
        self.assertEqual(res["gamma"]["verdict"], "PENDING", res)

    def test_glob_paths_rejected_in_registry(self):
        reg = make_registry(self.tmp, {
            "x": {"provenance_path": "modules/*/INSTALL-PROVENANCE.json",
                  "source_sha256": SOV_HASH},
        })
        with self.assertRaises(phc.RegistryError):
            phc.load_registry(reg)


class WorktreeC2Tests(unittest.TestCase):
    """Against the REAL registry: after B2-1, sovereign must be OK."""

    def test_sovereign_record_matches_own_registered_hash(self):
        if not os.path.isdir(os.path.join(WORKTREE_ROOT, "modules")):
            self.skipTest("worktree not present")
        modules = phc.load_registry(REGISTRY)
        res = phc.check(WORKTREE_ROOT, modules)
        self.assertEqual(res["sovereign"]["verdict"], "OK", res["sovereign"])
        self.assertNotEqual(res["sovereign"]["verdict"], "CROSS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
