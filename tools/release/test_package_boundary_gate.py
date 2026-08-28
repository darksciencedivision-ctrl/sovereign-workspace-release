#!/usr/bin/env python
"""Regression tests for package_boundary_gate.py (SWS-REM-DIR-20260828 R2 B1-1).

Each rejected class must FAIL the gate; a declared fixture (value-based:
exact path + exact sha256) must PASS; glob allow-list entries must be
rejected as configuration errors; quarantined-historical lanes must never
fail the scan; and a clean git archive must PASS.

Stdlib-only (unittest) so the suite runs offline with no provisioning.
Run: python -m unittest tools.release.test_package_boundary_gate -v
 or: python tools/release/test_package_boundary_gate.py -v
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.dont_write_bytecode = True  # never leave __pycache__ in the scanned tree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import package_boundary_gate as gate  # noqa: E402

WORKTREE_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def write(path: str, content: bytes = b"x") -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return path


def sha256(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


class GateFixtureBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pbg-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def scan(self, root=None, allowlist_path=None):
        return gate.scan_tree(
            root or self.tmp,
            gate.DEFAULT_QUARANTINE_LANES,
            gate.load_allowlist(allowlist_path))


class TestRejectedClasses(GateFixtureBase):
    def _expect_violation(self, rel, cls):
        write(os.path.join(self.tmp, rel))
        res = self.scan()
        hits = [v for v in res["violations"] if v["path"] == rel.replace(os.sep, "/")]
        self.assertTrue(hits, f"expected violation for {rel}, got {res['violations']}")
        self.assertEqual(hits[0]["class"], cls)

    def test_rejects_sqlite_db(self):
        self._expect_violation("state/sovereign.db", "database")

    def test_rejects_sqlite3(self):
        self._expect_violation("state/store.sqlite3", "database")

    def test_rejects_db_wal_sidecar(self):
        self._expect_violation("state/app.db-wal", "database")

    def test_rejects_env_bare(self):
        self._expect_violation(".env", "env-file")

    def test_rejects_env_local(self):
        self._expect_violation("ui/.env.local", "env-file")

    def test_rejects_key_material(self):
        self._expect_violation("keys/server.pem", "env-file")

    def test_rejects_log(self):
        self._expect_violation("logs/phase17c_iter90_main.log", "log")

    def test_rejects_node_modules(self):
        self._expect_violation("app/node_modules/x/index.js",
                               "runtime-session-state")

    def test_rejects_pycache(self):
        self._expect_violation("pkg/__pycache__/mod.pyc", "runtime-session-state")

    def test_rejects_venv(self):
        self._expect_violation(".venv/pyvenv.cfg", "runtime-session-state")

    def test_rejects_approvals_state(self):
        self._expect_violation("app/.approvals/session-events.jsonl",
                               "runtime-session-state")

    def test_rejects_recovery_state(self):
        self._expect_violation("app/.recovery/layout.json",
                               "runtime-session-state")

    def test_rejects_runs_history(self):
        self._expect_violation("runs/G0-live/events.jsonl",
                               "runtime-session-state")

    def test_rejects_sovereign_runtime_lane_any_file(self):
        self._expect_violation(
            "modules/sovereign/runtime/evidence/status/job.json",
            "runtime-session-state")

    def test_rejects_cache_junk(self):
        self._expect_violation("dir/Thumbs.db", "cache-junk")

    def test_rejects_live_operation_state(self):
        self._expect_violation("config/live_operation.json",
                               "runtime-operation-state")

    def test_rejects_settings_local(self):
        self._expect_violation(".claude/settings.local.json", "local-settings")


class TestCredentialPatterns(GateFixtureBase):
    def test_rejects_aws_key_content(self):
        write(os.path.join(self.tmp, "notes.txt"),
              b"aws_access_key_id = AKIAIOSFODNN7EXAMPLE\n")
        res = self.scan()
        self.assertTrue(any(h["class"] == "credential-pattern"
                            for h in res["credential_hits"]), res)

    def test_rejects_private_key_block(self):
        write(os.path.join(self.tmp, "blob.dat.txt"),
              b"-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----\n")
        res = self.scan()
        self.assertTrue(res["credential_hits"], res)

    def test_clean_text_passes(self):
        write(os.path.join(self.tmp, "readme.txt"), b"no secrets here\n")
        res = self.scan()
        self.assertFalse(res["violations"])
        self.assertFalse(res["credential_hits"])


class TestAllowList(GateFixtureBase):
    def _allowlist_file(self, entries):
        p = os.path.join(self.tmp, "allow.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "entries": entries}, f)
        return p

    def test_value_based_fixture_passes_with_exact_hash(self):
        fx = write(os.path.join(self.tmp, "fixtures/sample.db"), b"fixture-bytes")
        al = self._allowlist_file([{"path": "fixtures/sample.db",
                                    "sha256": sha256(fx),
                                    "reason": "declared test fixture"}])
        res = self.scan(allowlist_path=al)
        self.assertFalse(res["violations"], res)
        self.assertEqual(len(res["allowlisted"]), 1)

    def test_value_based_fixture_fails_on_tampered_content(self):
        fx = write(os.path.join(self.tmp, "fixtures/sample.db"), b"fixture-bytes")
        declared = sha256(fx)
        write(fx, b"tampered")
        al = self._allowlist_file([{"path": "fixtures/sample.db",
                                    "sha256": declared, "reason": "x"}])
        res = self.scan(allowlist_path=al)
        self.assertTrue(any("allow-list sha256 mismatch" in v["rule"]
                            for v in res["violations"]), res)

    def test_glob_path_rejected_as_config_error(self):
        al = self._allowlist_file([{"path": "fixtures/*.db",
                                    "sha256": "0" * 64, "reason": "x"}])
        with self.assertRaises(gate.AllowlistError):
            gate.load_allowlist(al)

    def test_missing_hash_rejected_as_config_error(self):
        al = self._allowlist_file([{"path": "fixtures/a.db", "reason": "x"}])
        with self.assertRaises(gate.AllowlistError):
            gate.load_allowlist(al)


class TestQuarantineLanes(GateFixtureBase):
    def test_allowlist_config_itself_not_content_scanned(self):
        # The allow-list's reason text may quote synthetic fixture values;
        # the gate must not fail on its own hash-governed configuration.
        al = os.path.join(self.tmp, "fixture_allowlist.json")
        with open(al, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "entries": [
                {"path": "does/not/exist.db",
                 "sha256": "0" * 64,
                 "reason": "quotes sk-synthetic000000000000000000 by design"}
            ]}, f)
        res = gate.scan_tree(self.tmp, gate.DEFAULT_QUARANTINE_LANES,
                             gate.load_allowlist(al),
                             allowlist_source_path=al)
        self.assertFalse(res["violations"], res)
        self.assertFalse(res["credential_hits"], res)

    def test_evidence_lane_never_fails(self):
        write(os.path.join(self.tmp, "evidence", "cp01", "before", "cache.db"))
        write(os.path.join(self.tmp, "evidence", "gate5", "driver.log"))
        res = self.scan()
        self.assertFalse(res["violations"], res)
        self.assertEqual(len(res["quarantined"]), 2)

    def test_dev_lane_never_fails(self):
        write(os.path.join(self.tmp, "dev", "staging", "worktree", "debate.log"))
        res = self.scan()
        self.assertFalse(res["violations"], res)
        self.assertEqual(len(res["quarantined"]), 1)

    def test_active_tree_still_fails_with_quarantine_present(self):
        write(os.path.join(self.tmp, "evidence", "old.db"))
        write(os.path.join(self.tmp, "modules", "active.db"))
        res = self.scan()
        self.assertEqual(len(res["violations"]), 1)
        self.assertEqual(res["violations"][0]["path"], "modules/active.db")


class TestCleanedWorktree(GateFixtureBase):
    """Pass-after proof: the tracked release archive must PASS the gate."""

    def test_archive_passes(self):
        if not os.path.isdir(os.path.join(WORKTREE_ROOT, "modules")):
            self.skipTest("worktree not present beside this checkout")
        with tempfile.TemporaryDirectory(prefix="pbg-archive-") as extracted:
            archive = os.path.join(extracted, "release.tar")
            cp = subprocess.run(
                ["git", "archive", "--format=tar", "--output", archive, "HEAD"],
                cwd=WORKTREE_ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            archive_root = os.path.join(extracted, "tree")
            os.makedirs(archive_root)
            with tarfile.open(archive, "r") as tf:
                tf.extractall(archive_root, filter="data")
            allowlist_path = os.path.join(
                archive_root, "tools", "release", "fixture_allowlist.json")
            res = gate.scan_tree(
                archive_root, gate.DEFAULT_QUARANTINE_LANES,
                gate.load_allowlist(allowlist_path),
                allowlist_source_path=allowlist_path)
        problems = res["violations"] + res["credential_hits"]
        self.assertFalse(
            problems,
            "clean archive must pass; first problems: %r" % problems[:10])
        self.assertGreater(res["files_scanned"], 1000)
        self.assertGreater(len(res["quarantined"]), 0,
                           "evidence/dev lanes must be present and quarantined")
        self.assertGreaterEqual(len(res["allowlisted"]), 1,
                                "declared fixtures must be recognized")


if __name__ == "__main__":
    unittest.main(verbosity=2)
