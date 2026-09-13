"""N-16: product startup-test records stay outside tracked release inputs.

R15 (remediation/p1): this suite never writes to or deletes the real checkout `.runtime`.
Default-path selection is verified by INSPECTING the computed path (no write, no mkdir);
a record is actually written only into a per-test temporary root, and only that owned root
is cleaned up. A dedicated regression proves the real `.runtime` is neither created nor
mutated and that a sentinel outside the owned root survives the suite's own cleanup.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from shell.src import startup_test


WORKTREE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_RUNTIME = os.path.join(WORKTREE, ".runtime")


def _runtime_snapshot():
    """Read-only view of the real `.runtime` lane: None when absent, else its listing.

    Used to assert the suite leaves the real directory exactly as it found it, without
    ever creating or deleting it (R15)."""
    if not os.path.exists(DEFAULT_RUNTIME):
        return None
    return sorted(os.listdir(DEFAULT_RUNTIME))


class TestStartupEvidenceLane(unittest.TestCase):
    def setUp(self):
        # A per-test owned temporary root; only this is ever cleaned up (R15). Nothing
        # in this suite passes the real `.runtime` to a destructive call.
        self._owned_root = tempfile.mkdtemp(prefix="sws-startup-evidence-")
        self.addCleanup(shutil.rmtree, self._owned_root, ignore_errors=True)

    def test_default_record_location_is_the_state_root_not_the_install(self):
        # R16/F-017. The default evidence location is the shell's per-USER state root, NOT the
        # install tree -- writing under <install>/.runtime dirtied the installed path set and
        # failed on a read-only install. evidence_root() is a pure path computation (no mkdir),
        # verified here without writing anything.
        from shell.src.adapter import workspace_state_root
        with mock.patch.dict(os.environ, {"SWS_EVIDENCE_ROOT": ""}):
            default_root = os.path.abspath(startup_test.evidence_root())

        expected_root = os.path.abspath(
            os.path.join(workspace_state_root().replace("/", os.sep), "shell", "evidence"))
        self.assertEqual(default_root, expected_root)
        # The default location is OUTSIDE the install tree (the F-017 property).
        self.assertNotIn(os.path.abspath(WORKTREE).casefold(), default_root.casefold())

    def test_record_is_written_under_the_configured_root(self):
        # An actual _save_record write is directed at the per-test owned root only.
        with mock.patch.dict(os.environ, {"SWS_EVIDENCE_ROOT": self._owned_root}):
            result = {"module_id": "n16-regression", "logs": []}
            startup_test._save_record(result, "n16-regression")

        record_path = os.path.abspath(result["_record_path"])
        self.assertEqual(
            os.path.commonpath([record_path, self._owned_root]), self._owned_root)
        self.assertTrue(os.path.isfile(record_path))

    def test_override_remains_available_for_isolated_tests(self):
        with mock.patch.dict(os.environ, {"SWS_EVIDENCE_ROOT": self._owned_root}):
            self.assertEqual(startup_test.evidence_root(), self._owned_root)

    def test_suite_never_creates_or_mutates_the_real_runtime_directory(self):
        """R15 regression: exercising the write path leaves the real `.runtime` untouched,
        and a sentinel outside the owned root survives the suite's cleanup."""
        before = _runtime_snapshot()

        # A sentinel in a separately-owned directory must survive: it proves cleanup is
        # scoped to the owned root and does not reach sibling paths (the failure mode of
        # the old `rmtree(WORKTREE/.runtime)` tearDown).
        sentinel_dir = tempfile.mkdtemp(prefix="sws-startup-sentinel-")
        self.addCleanup(shutil.rmtree, sentinel_dir, ignore_errors=True)
        sentinel = os.path.join(sentinel_dir, "keep.txt")
        with open(sentinel, "w", encoding="utf-8") as f:
            f.write("survive")

        with mock.patch.dict(os.environ, {"SWS_EVIDENCE_ROOT": self._owned_root}):
            startup_test._save_record({"module_id": "n16-guard", "logs": []}, "n16-guard")

        self.assertEqual(
            _runtime_snapshot(), before,
            "the real .runtime directory was created or mutated by this suite")
        self.assertTrue(
            os.path.isfile(sentinel), "a sentinel outside the owned root was destroyed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
