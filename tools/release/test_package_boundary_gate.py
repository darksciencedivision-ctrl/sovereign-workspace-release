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
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


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

    def _expect_clean(self, rel):
        """The other direction. A rejection set is only as good as what it lets THROUGH, and this
        gate's job is to be usable — a rule that flags curated product content trains its readers
        to reach for an exemption, which is how a lane came to cover shipped bytes."""
        write(os.path.join(self.tmp, rel))
        res = self.scan()
        hits = [v for v in res["violations"] if v["path"] == rel.replace(os.sep, "/")]
        self.assertFalse(hits, f"{rel} must not be a violation, got {hits}")
        quarantined = [q for q in res["quarantined"] if q["path"] == rel.replace(os.sep, "/")]
        self.assertFalse(quarantined,
                         f"{rel} was not flagged, but it was QUARANTINED — an exemption is not a "
                         f"clean result: {quarantined}")

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

    def test_rejects_runtime_evidence_lane(self):
        self._expect_violation(".runtime/evidence/startup-tests/module.json",
                               "runtime-session-state")

    def test_a_curated_runs_tree_is_NOT_runtime_state(self):
        """SUPERSEDED CONTRACT (SYSTEM-REVIEW 2026-08-31, F-2). This asserted the opposite.

        `runs` sat in `COMPONENT_RULES["runtime-session-state"]` beside `node_modules`, `.venv`
        and `__pycache__`. Those are directories a TOOL creates and nobody curates. `runs` is a
        name a project may choose for material it maintains on purpose, and on this tree
        `modules/distillery/runs/` was the ONLY tracked path with that component — 80 files of
        curated release-gate evidence, cited by four shipped tests and a shipped tool.

        So the rule produced 79 false positives on shipped files and a quarantine lane existed
        only to suppress them, which made the gate report `violations: 0` while 79 shipped files
        had matched a violation rule. Rule and lane were removed together: a name-based rule that
        needs a standing exemption to be usable is the wrong rule.

        The volatile half is still excluded, at the right layer — the Distillery's own
        .gitignore drops `runs/G0-live/*.jsonl`, which is the very path this test used to name.
        """
        self._expect_clean("runs/release-baseline/GR0_PREFLIGHT.json")

    def test_the_tool_generated_caches_are_still_rejected(self):
        """What the removal must NOT have cost. Every remaining member of the set is a directory
        no human curates, and each still fails the scan."""
        for path in ("node_modules/pkg/index.js", ".venv/pyvenv.cfg",
                     "__pycache__/mod.cpython-312.pyc", ".pytest_cache/v/cache/lastfailed",
                     ".approvals/session-events.jsonl", ".runtime/receipts/READY.json"):
            with self.subTest(path=path):
                self._expect_violation(path, "runtime-session-state")

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
                runtime_members = [
                    name for name in tf.getnames()
                    if ".runtime" in name.replace("\\", "/").split("/")
                ]
                self.assertFalse(
                    runtime_members,
                    "runtime-evidence classes must never enter a release archive")
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
        # SUPERSEDED CONTRACT (SYSTEM-REVIEW 2026-08-31, F-2). This asserted the archive must
        # CONTAIN quarantined bytes, and its message named the evidence/ and dev/ lanes as the
        # reason. Both are export-ignored and contribute nothing to an archive, so the assertion
        # was in fact being satisfied by the `modules/distillery/runs/` lane — the one covering
        # shipped bytes. An archive with quarantined content is an archive carrying an exemption,
        # which is the defect, not the requirement.
        self.assertEqual(len(res["quarantined"]), 0,
                         f"a release archive must carry NO quarantined bytes — an exemption in "
                         f"the distribution makes `violations: 0` a claim about the exemption: "
                         f"{res['quarantined'][:5]}")
        self.assertGreaterEqual(len(res["allowlisted"]), 1,
                                "declared fixtures must be recognized")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class NoLaneCoversShippedBytes(unittest.TestCase):
    """The property that makes `violations: 0` mean something.

    A quarantine lane suppresses a whole subtree. That is defensible over bytes a recipient never
    receives and indefensible over bytes that ship: it turns the gate's headline number into a
    statement about the lane rather than about the distribution. Measured before this test existed:
    the `modules/distillery/runs/` lane covered 79 shipped files, and it was hiding four
    credential-pattern hits that nobody had had to dispose of.

    This holds the rule going forward rather than leaving it to be re-derived by the next person
    who adds a lane to make a red gate green.
    """

    def test_every_default_lane_is_export_ignored(self):
        if not os.path.isdir(os.path.join(WORKTREE_ROOT, "modules")):
            self.skipTest("worktree not present beside this checkout")
        attributes = os.path.join(WORKTREE_ROOT, ".gitattributes")
        with open(attributes, encoding="utf-8") as handle:
            rules = [line.split()[0] for line in handle
                     if line.strip() and not line.startswith("#") and "export-ignore" in line]
        for lane in gate.DEFAULT_QUARANTINE_LANES:
            with self.subTest(lane=lane):
                stem = lane.rstrip("/")
                self.assertTrue(
                    any(r.rstrip("/*").lstrip("/") == stem for r in rules),
                    f"quarantine lane {lane!r} is not export-ignored, so it covers bytes that "
                    f"SHIP. Either exclude the lane from the distribution or stop quarantining "
                    f"it — an exemption over shipped bytes makes `violations: 0` a claim about "
                    f"the exemption. Current export-ignore rules: {rules}")

    def test_no_lane_matches_a_file_in_the_distribution(self):
        """The same property, measured against the archive rather than against the rules."""
        if not os.path.isdir(os.path.join(WORKTREE_ROOT, "modules")):
            self.skipTest("worktree not present beside this checkout")
        with tempfile.TemporaryDirectory(prefix="pbg-lane-") as work:
            archive = os.path.join(work, "release.tar")
            cp = subprocess.run(
                ["git", "archive", "--format=tar", "--output", archive, "HEAD"],
                cwd=WORKTREE_ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            with tarfile.open(archive, "r") as tf:
                shipped = [m.name for m in tf.getmembers() if m.isfile()]
        for lane in gate.DEFAULT_QUARANTINE_LANES:
            covered = [n for n in shipped if n.startswith(lane)]
            self.assertFalse(covered,
                             f"lane {lane!r} covers {len(covered)} shipped file(s), e.g. "
                             f"{covered[:3]}")


class CredentialPatternTests(GateFixtureBase):
    def test_detects_product_key_shapes(self):
        body = (
            "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123\n"
            "sk-proj-abcdefghijklmnopqrstuvwxyz0123\n"
            "hf_abcdefghijklmnopqrstuvwx\n"
            "AIzaSyDabcdefghijklmnopqrstuv\n"
            "npm_abcdefghijklmnopqrstuvwx\n"
            "glpat-abcdefghijklmnopqrstuv\n"
            "AccountKey=abcdefghijklmnopqrstuvwx+/==\n"
        )
        write(os.path.join(self.tmp, "secrets.txt"), body.encode("utf-8"))
        res = self.scan()
        rules = {h["rule"] for h in res["credential_hits"]}
        for name in ("anthropic-key", "openai-proj-key", "huggingface-token",
                     "google-api-key", "npm-token", "gitlab-pat", "azure-account-key"):
            self.assertTrue(any(name in r for r in rules), (name, rules))

    def test_unrelated_fixture_allowlist_name_is_still_scanned(self):
        write(os.path.join(self.tmp, "vendor", "fixture_allowlist.json"),
              b'{"token": "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123"}')
        res = self.scan()
        self.assertTrue(any("anthropic-key" in h["rule"] for h in res["credential_hits"]),
                        res["credential_hits"])
