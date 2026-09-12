#!/usr/bin/env python
"""F-065 — the node-advisory gate must not fail open.

`npm audit --json` prints a JSON ERROR object (no metadata.vulnerabilities) with a non-0/1 exit
code when the audit cannot run (network/registry failure). The gate accepted any parseable JSON and
read a missing metadata block as "0 advisories", so an outage PASSED. _audit now requires a real
audit exit code (0 or 1) AND a real vulnerabilities block; anything else is "unavailable".
"""
from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_node_advisories as gate  # noqa: E402


def _proc(returncode: int, stdout: str, stderr: str = "") -> types.SimpleNamespace:
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class AuditFailsClosed(unittest.TestCase):
    def _audit_with(self, proc):
        with mock.patch.object(gate.shutil, "which", return_value="npm"), \
             mock.patch.object(gate.subprocess, "run", return_value=proc):
            return gate._audit(Path("."))

    def test_registry_error_object_is_not_zero_advisories(self) -> None:
        # An npm error object: parseable JSON, no metadata.vulnerabilities.
        state, report, _detail = self._audit_with(
            _proc(1, '{"error": {"code": "ENETUNREACH", "summary": "network down"}}'))
        self.assertEqual(state, "no-metadata")
        self.assertIsNone(report)

    def test_nonstandard_exit_code_is_audit_error(self) -> None:
        state, _report, detail = self._audit_with(_proc(254, "", "registry unreachable"))
        self.assertEqual(state, "audit-error")
        self.assertIn("254", detail)

    def test_a_real_clean_report_is_ok(self) -> None:
        state, report, _detail = self._audit_with(
            _proc(0, '{"metadata": {"vulnerabilities": {"total": 0, "high": 0}}}'))
        self.assertEqual(state, "ok")
        self.assertEqual(report["metadata"]["vulnerabilities"]["total"], 0)

    def test_a_real_report_with_findings_is_ok(self) -> None:
        state, report, _detail = self._audit_with(
            _proc(1, '{"metadata": {"vulnerabilities": {"total": 2, "high": 2}},'
                     ' "vulnerabilities": {"pkg": {}}}'))
        self.assertEqual(state, "ok")
        self.assertEqual(report["metadata"]["vulnerabilities"]["total"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
