#!/usr/bin/env python
"""F-073 tests — INSTALL-PROVENANCE records are verifiable against the tracked tree.

The records hard-coded "integrity_verified": true and a stale build-host worktree path, and there
was no way to detect a record that had drifted from the candidate bytes. `--check` now recomputes
the content digest (and version / lockfile / artifact hashes) from the git-tracked tree -- a pure
function of tracked bytes, so it gives the same verdict on the build host and in CI.
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
import generate_module_provenance as gmp  # noqa: E402

WORKTREE_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


class ProvenanceCheck(unittest.TestCase):
    def test_committed_records_match_the_tracked_tree(self) -> None:
        self.assertEqual(gmp.check(WORKTREE_ROOT), 0,
                         "committed INSTALL-PROVENANCE records are stale against the tracked tree")

    def test_records_no_longer_hard_code_integrity_verified(self) -> None:
        for name in gmp.MODULES:
            path = os.path.join(WORKTREE_ROOT, "modules", name, gmp.RECORD_NAME)
            with open(path, "r", encoding="utf-8-sig") as f:
                record = json.load(f)
            self.assertNotIn("integrity_verified", record,
                             f"{name} record still hard-codes integrity_verified")

    def test_records_do_not_leak_a_build_host_path(self) -> None:
        for name in gmp.MODULES:
            path = os.path.join(WORKTREE_ROOT, "modules", name, gmp.RECORD_NAME)
            text = open(path, "r", encoding="utf-8-sig").read()
            self.assertNotIn("producttion software 2", text, f"{name} carries the stale worktree")
            self.assertNotIn("D:/producttion", text)

    def test_check_detects_a_stale_record(self) -> None:
        # Copy just enough of the tree to run check against a deliberately corrupted record.
        tmp = tempfile.mkdtemp(prefix="f073-")
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        # A minimal git checkout is required for content_digest (git ls-files); copy the .git and
        # one module. Simpler: run check in the real tree but with a monkeypatched record read.
        name = "debate"
        record_path = os.path.join(WORKTREE_ROOT, "modules", name, gmp.RECORD_NAME)
        original = open(record_path, "r", encoding="utf-8-sig").read()
        record = json.loads(original)
        record["source_sha256"] = "0" * 64  # corrupt it
        try:
            with open(record_path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(record, f, indent=2, ensure_ascii=False)
                f.write("\n")
            self.assertEqual(gmp.check(WORKTREE_ROOT), 1,
                             "check did not detect a corrupted source_sha256")
        finally:
            with open(record_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(original)
        # And it is clean again once restored.
        self.assertEqual(gmp.check(WORKTREE_ROOT), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
