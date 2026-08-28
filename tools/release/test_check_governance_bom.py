#!/usr/bin/env python
"""Tests for check_governance_bom.py (SWS-REM-DIR-20260828 R2 B2-5)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_governance_bom as cgb  # noqa: E402

WORKTREE_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SOV = os.path.join(WORKTREE_ROOT, "modules", "sovereign")
BOM = b"\xef\xbb\xbf"


class BomGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bom-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _put(self, rel, payload: bytes):
        full = os.path.join(self.tmp, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(payload)

    def test_clean_files_pass(self):
        for rel in cgb.DEFAULT_GOVERNANCE_JSON:
            self._put(rel, b'{"a": 1}\n')
        self.assertEqual(cgb.check(self.tmp), [])

    def test_bom_detected(self):
        for rel in cgb.DEFAULT_GOVERNANCE_JSON:
            self._put(rel, b'{"a": 1}\n')
        victim = cgb.DEFAULT_GOVERNANCE_JSON[2]
        self._put(victim, BOM + b'{"a": 1}\n')
        problems = cgb.check(self.tmp)
        self.assertEqual(problems, [f"{victim}: UTF-8 BOM present"])

    def test_missing_file_reported(self):
        for rel in cgb.DEFAULT_GOVERNANCE_JSON[1:]:
            self._put(rel, b'{}\n')
        problems = cgb.check(self.tmp)
        self.assertEqual(problems, [f"{cgb.DEFAULT_GOVERNANCE_JSON[0]}: MISSING"])


class WorktreeBomTests(unittest.TestCase):
    """Against the real worktree after B2-5: no BOMs, strict-utf-8 parseable."""

    def test_no_boms_in_worktree(self):
        if not os.path.isdir(SOV):
            self.skipTest("worktree sovereign module not present")
        self.assertEqual(cgb.check(WORKTREE_ROOT), [])

    def test_strict_utf8_parse(self):
        if not os.path.isdir(SOV):
            self.skipTest("worktree sovereign module not present")
        for rel in cgb.DEFAULT_GOVERNANCE_JSON:
            with open(os.path.join(WORKTREE_ROOT, rel.replace("/", os.sep)),
                      "r", encoding="utf-8") as f:
                json.load(f)  # raises on BOM


if __name__ == "__main__":
    unittest.main(verbosity=2)
