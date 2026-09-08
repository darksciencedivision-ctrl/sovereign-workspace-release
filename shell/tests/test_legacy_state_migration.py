"""
SWS-CORRECTIVE-01 workstream 3.3 - the legacy-state migration contract.

Before this release runtime state lived inside the install root. `docs/LIMITATIONS.md` recorded
the consequence honestly and stopped: "Nothing migrates it automatically. Copy it into the new
state root, or start fresh." These tests pin the three properties that make a migration safe to
offer instead of that advice: it never modifies the legacy installation, it never silently
overwrites, and it never silently abandons a file.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATE = REPO_ROOT / "tools" / "release" / "migrate_legacy_state.ps1"


def _ps(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(MIGRATE), *args],
        capture_output=True, text=True, timeout=600)


def _tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class LegacyStateMigration(unittest.TestCase):

    def setUp(self) -> None:
        self.assertTrue(MIGRATE.is_file(), "the migration script is missing")
        self.tmp = Path(tempfile.mkdtemp(prefix="sov-migrate-"))
        self.legacy = self.tmp / "OldInstall"
        self.state = self.tmp / "NewState"
        self.receipt = self.tmp / "receipt.json"

        # A legacy installation with state beside its code, in the places it used to live.
        for rel, blob in {
            "modules/sovereign/runtime/sovereign.db": b"\x00legacy-db\xff",
            "modules/sovereign/logs/run.log": b"old log\n",
            "modules/debate/config.json": b'{"seats": 4}\n',
            "modules/tokencenter/data/piggybank.sqlite": bytes(range(64)),
            "modules/sow/.runtime/receipts/SHELL-LIVE-READY.json": b'{"ok":true}\n',
            # product code, which must NOT be migrated
            "modules/sovereign/sovereign_product/server.py": b"# code\n",
            "shell/src/__main__.py": b"# code\n",
        }.items():
            target = self.legacy / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *extra: str) -> subprocess.CompletedProcess:
        return _ps("-LegacyInstall", str(self.legacy), "-StateRoot", str(self.state),
                   "-ReceiptPath", str(self.receipt), *extra)

    def _receipt(self) -> dict:
        return json.loads(self.receipt.read_text(encoding="utf-8"))

    # -- plan first ---------------------------------------------------------
    def test_without_apply_nothing_is_written_but_a_receipt_is(self) -> None:
        r = self._run()
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-1500:])
        self.assertIn("PLAN ONLY", r.stdout)
        self.assertFalse(self.state.exists(),
                         "a plan-only run created state")
        self.assertTrue(self.receipt.is_file(), "a plan-only run wrote no receipt")
        self.assertFalse(self._receipt()["applied"])
        self.assertGreater(self._receipt()["counts"]["migrate"], 0)

    # -- non-destructive ----------------------------------------------------
    def test_the_legacy_installation_is_never_modified(self) -> None:
        before = _tree(self.legacy)
        r = self._run("-Apply")
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-1500:])
        self.assertEqual(_tree(self.legacy), before,
                         "the migration modified the legacy installation")

    def test_product_code_is_not_migrated(self) -> None:
        """The plan is enumerated explicitly; a glob over an install root would sweep up code."""
        self._run("-Apply")
        migrated = {d["destination"] for d in self._receipt()["decisions"]
                    if d["decision"] == "migrate"}
        for code in migrated:
            self.assertNotIn("server.py", code)
            self.assertNotIn("__main__.py", code)
        self.assertFalse((self.state / "shell").exists())

    def test_state_lands_where_the_new_layout_expects_it(self) -> None:
        self._run("-Apply")
        self.assertEqual((self.state / "sovereign" / "runtime" / "sovereign.db").read_bytes(),
                         b"\x00legacy-db\xff")
        self.assertEqual((self.state / "debate" / "config.json").read_bytes(),
                         b'{"seats": 4}\n')
        # SOW's receipts move from the in-install .runtime lane to the state lane (C3).
        self.assertTrue((self.state / "sow" / "receipts" / "SHELL-LIVE-READY.json").is_file())

    # -- no silent overwrite ------------------------------------------------
    def test_a_conflicting_destination_is_kept_by_default(self) -> None:
        target = self.state / "debate" / "config.json"
        target.parent.mkdir(parents=True)
        target.write_bytes(b'{"seats": 99}\n')  # current state, newer

        r = self._run("-Apply")
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-1500:])
        self.assertEqual(target.read_bytes(), b'{"seats": 99}\n',
                         "the migration overwrote current state with older state")
        conflicts = [d for d in self._receipt()["decisions"] if d["decision"] == "conflict"]
        self.assertTrue(conflicts, "the conflict was not recorded")
        self.assertIn("CONFLICTS", r.stdout)

    def test_keepboth_writes_the_legacy_copy_alongside(self) -> None:
        target = self.state / "debate" / "config.json"
        target.parent.mkdir(parents=True)
        target.write_bytes(b'{"seats": 99}\n')

        r = self._run("-Apply", "-OnConflict", "KeepBoth")
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-1500:])
        self.assertEqual(target.read_bytes(), b'{"seats": 99}\n',
                         "KeepBoth still overwrote the existing file")
        alongside = list((self.state / "debate").glob("config.legacy-*.json"))
        self.assertTrue(alongside, "the legacy copy was not written alongside")
        self.assertEqual(alongside[0].read_bytes(), b'{"seats": 4}\n')

    def test_an_identical_destination_is_recorded_as_such_not_as_a_conflict(self) -> None:
        target = self.state / "debate" / "config.json"
        target.parent.mkdir(parents=True)
        target.write_bytes(b'{"seats": 4}\n')  # same bytes

        self._run("-Apply")
        decisions = {d["destination"]: d for d in self._receipt()["decisions"]}
        self.assertEqual(decisions["debate\\config.json"]["decision"], "identical")

    # -- no silent abandonment ----------------------------------------------
    def test_every_legacy_state_file_appears_in_the_receipt(self) -> None:
        self._run("-Apply")
        receipt = self._receipt()
        recorded = {d["source"] for d in receipt["decisions"] if d["source"]}
        for expected in ("modules\\sovereign\\runtime\\sovereign.db",
                         "modules\\debate\\config.json",
                         "modules\\tokencenter\\data\\piggybank.sqlite"):
            self.assertIn(expected, recorded,
                          "a legacy state file is absent from the receipt: " + expected)
        for d in receipt["decisions"]:
            self.assertIn(d["decision"], ("migrate", "conflict", "skip", "identical"))
            if d["decision"] == "skip":
                self.assertTrue(d["reason"], "a skipped file was recorded with no reason")

    def test_the_receipt_records_hashes_and_the_conflict_policy(self) -> None:
        self._run("-Apply")
        receipt = self._receipt()
        self.assertEqual(receipt["schema"], "sovereign.state-migration.v1")
        self.assertEqual(receipt["on_conflict"], "KeepExisting")
        self.assertTrue(receipt["applied"])
        migrated = [d for d in receipt["decisions"] if d["decision"] == "migrate"]
        self.assertTrue(migrated)
        for d in migrated:
            self.assertRegex(d["source_sha256"], r"^[0-9a-f]{64}$")

    def test_overlapping_legacy_install_and_state_root_are_refused(self) -> None:
        r = _ps("-LegacyInstall", str(self.legacy),
                "-StateRoot", str(self.legacy / "inside"),
                "-ReceiptPath", str(self.receipt))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("overlapping", (r.stdout + r.stderr).lower())

    def test_a_filesystem_root_state_root_is_refused(self) -> None:
        r = _ps("-LegacyInstall", str(self.legacy),
                "-StateRoot", "C:\\",
                "-ReceiptPath", str(self.receipt))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("filesystem-root", (r.stdout + r.stderr).lower())

    def test_a_junction_state_root_that_lands_inside_legacy_is_refused(self) -> None:
        bait = self.tmp / "state-bait"
        bait.mkdir()
        junction = bait / "escape"
        created = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(junction), str(self.legacy)],
            capture_output=True, text=True)
        if created.returncode != 0:
            self.skipTest("cannot create a junction: " + (created.stdout + created.stderr)[-400:])
        r = _ps("-LegacyInstall", str(self.legacy),
                "-StateRoot", str(junction),
                "-ReceiptPath", str(self.receipt))
        self.assertNotEqual(r.returncode, 0, created.stdout + created.stderr + r.stdout + r.stderr)
        self.assertIn("overlapping", (r.stdout + r.stderr).lower())


if __name__ == "__main__":
    unittest.main()
