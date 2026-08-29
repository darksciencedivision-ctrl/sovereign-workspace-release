"""N-16: product startup-test records stay outside tracked release inputs."""
from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from unittest import mock

from shell.src import startup_test


WORKTREE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class TestStartupEvidenceLane(unittest.TestCase):
    def tearDown(self):
        shutil.rmtree(os.path.join(WORKTREE, ".runtime"), ignore_errors=True)

    def test_default_record_is_ignored_runtime_evidence(self):
        with mock.patch.dict(os.environ, {"SWS_EVIDENCE_ROOT": ""}):
            result = {"module_id": "n16-regression", "logs": []}
            startup_test._save_record(result, "n16-regression")

        record_path = os.path.abspath(result["_record_path"])
        expected_root = os.path.join(WORKTREE, ".runtime", "evidence")
        self.assertEqual(os.path.commonpath([record_path, expected_root]), expected_root)
        self.assertTrue(os.path.isfile(record_path))

        ignored = subprocess.run(
            ["git", "check-ignore", "--quiet", record_path],
            cwd=WORKTREE, check=False)
        self.assertEqual(ignored.returncode, 0, record_path)

    def test_override_remains_available_for_isolated_tests(self):
        override = os.path.join(WORKTREE, ".runtime", "override")
        with mock.patch.dict(os.environ, {"SWS_EVIDENCE_ROOT": override}):
            self.assertEqual(startup_test.evidence_root(), override)


if __name__ == "__main__":
    unittest.main(verbosity=2)
