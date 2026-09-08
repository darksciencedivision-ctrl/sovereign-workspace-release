"""
SWS-CORRECTIVE-01 workstream 1.1 - the upgrade transaction (L1).

The recorded reproduction is `test_upgrade_from_inside_the_outgoing_install`: the previous
controller bound `$here = $PSScriptRoot`, moved the installation containing `$here`, and then
invoked `install.ps1` through the path it had just emptied. The installation directory ceased to
exist and nothing rolled back.

These tests drive the real `tools/release/upgrade.ps1` against a fixture installation under
`%TEMP%`. The two network-bound steps - `install.ps1` (three venvs, two npm trees, a hash-verified
Electron download) and `verify_install.ps1` - are represented by fast stand-ins inside the fixture,
because L1 is a transaction-control defect and not an install defect: what is under test is which
path the controller resolves, what it checks before it moves anything, and what survives each
injected failure. `tools/ci/run_ci.ps1` exercises the real install through the clean-room stage.

The operator's own installation and state root are never touched: every path here is built under
`tempfile.mkdtemp`, and `SOVEREIGN_WORKSPACE_STATE` is redirected into it.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UPGRADE = REPO_ROOT / "tools" / "release" / "upgrade.ps1"

STUB_INSTALL = """param([string]$Dest,[string]$TargetDir,[string]$Artifact)
$ErrorActionPreference = 'Stop'
if ($env:SOVEREIGN_TEST_INSTALL_FAILS -eq '1') {
    Write-Output 'stub-install: refusing (SOVEREIGN_TEST_INSTALL_FAILS)'
    exit 9
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
New-Item -ItemType Directory -Path $Dest -Force | Out-Null
$zip = [IO.Compression.ZipFile]::OpenRead($Artifact)
try {
    foreach ($e in $zip.Entries) {
        $rel = $e.FullName.Replace('\\','/').Substring('sovereign-workspace/'.Length)
        if (-not $rel) { continue }
        $target = Join-Path $Dest $rel
        if (-not $e.Name) { New-Item -ItemType Directory -Path $target -Force | Out-Null; continue }
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        [IO.Compression.ZipFileExtensions]::ExtractToFile($e, $target, $true)
    }
}
finally { $zip.Dispose() }
Set-Content -LiteralPath (Join-Path $Dest 'install-manifest.json') -Value '{"schema":"sovereign.install-manifest.v1"}'
Write-Output "stub-install: installed to $Dest"
exit 0
"""

STUB_VERIFY = """param([string]$Dest)
if ($env:SOVEREIGN_TEST_VERIFY_FAILS -eq '1') {
    Write-Output 'stub-verify: refusing (SOVEREIGN_TEST_VERIFY_FAILS)'
    exit 7
}
if (-not (Test-Path -LiteralPath (Join-Path $Dest 'VERSION.json'))) {
    Write-Output 'stub-verify: VERSION.json missing'
    exit 8
}
Write-Output "stub-verify: ok $Dest"
exit 0
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="ascii", newline="\r\n")


class UpgradeTransaction(unittest.TestCase):

    def setUp(self) -> None:
        self.assertTrue(UPGRADE.is_file(), "tools/release/upgrade.ps1 is missing")
        self.tmp = Path(tempfile.mkdtemp(prefix="sov-upgrade-"))
        self.install = self.tmp / "Sovereign Workspace"
        self._lay_install(self.install, version="1.0.0")
        self.artifact = self._make_artifact(self.tmp / "sovereign-workspace-2.0.0-install.zip",
                                            version="2.0.0")
        self.state = self.tmp / "state"
        self.state.mkdir()
        (self.state / "keep.txt").write_text("operator data\n", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- fixtures -----------------------------------------------------------
    def _lay_install(self, root: Path, version: str, state_schema: str | None = None) -> None:
        tools = root / "tools" / "release"
        tools.mkdir(parents=True)
        shutil.copy2(UPGRADE, tools / "upgrade.ps1")
        _write(tools / "install.ps1", STUB_INSTALL)
        _write(tools / "verify_install.ps1", STUB_VERIFY)
        # backup_state.ps1 is the real one: the snapshot phase must exercise real tooling.
        shutil.copy2(REPO_ROOT / "tools" / "release" / "backup_state.ps1",
                     tools / "backup_state.ps1")
        doc: dict = {"version": version}
        if state_schema:
            doc["state_schema"] = state_schema
        (root / "VERSION.json").write_text(json.dumps(doc), encoding="utf-8")
        (root / "install-manifest.json").write_text(
            '{"schema":"sovereign.install-manifest.v1"}', encoding="utf-8")
        (root / "shell" / "src").mkdir(parents=True)
        (root / "shell" / "src" / "__main__.py").write_text("# fixture\n", encoding="utf-8")

    def _make_artifact(self, path: Path, version: str,
                       state_schema: str | None = None,
                       omit: str | None = None,
                       escape: bool = False) -> Path:
        doc: dict = {"version": version}
        if state_schema:
            doc["state_schema"] = state_schema
        entries = {
            "sovereign-workspace/VERSION.json": json.dumps(doc),
            "sovereign-workspace/shell/src/__main__.py": "# incoming\n",
            "sovereign-workspace/tools/release/install.ps1": STUB_INSTALL,
            "sovereign-workspace/tools/release/verify_install.ps1": STUB_VERIFY,
        }
        if omit:
            entries.pop(omit, None)
        with zipfile.ZipFile(path, "w") as zf:
            for name, body in entries.items():
                zf.writestr(name, body)
            if escape:
                zf.writestr("../escaped.txt", "nope")
        self._sidecar(path)
        return path

    @staticmethod
    def _sidecar(path: Path) -> None:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        Path(str(path) + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="ascii")

    def _run(self, script: Path, *args: str, env_extra: dict | None = None,
             timeout: int = 600) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["SOVEREIGN_WORKSPACE_STATE"] = str(self.state)
        env.pop("SOVEREIGN_TEST_INSTALL_FAILS", None)
        env.pop("SOVEREIGN_TEST_VERIFY_FAILS", None)
        env.update(env_extra or {})
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(script), *args],
            capture_output=True, text=True, timeout=timeout, env=env)

    def _inside(self, *args: str, **kw) -> subprocess.CompletedProcess:
        """Invoke the controller that lives INSIDE the outgoing installation."""
        return self._run(self.install / "tools" / "release" / "upgrade.ps1", *args, **kw)

    @staticmethod
    def _tx_roots(parent: Path):
        return sorted(parent.glob(".sovereign-upgrade-*"))

    @staticmethod
    def _previous(parent: Path):
        return sorted(parent.glob("Sovereign Workspace.previous-*"))

    # -- L1: the recorded reproduction --------------------------------------
    def test_upgrade_from_inside_the_outgoing_install(self) -> None:
        r = self._inside("-Dest", str(self.install), "-Artifact", str(self.artifact))
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out[-3000:])
        self.assertTrue(self.install.is_dir(),
                        "the installation directory did not survive the upgrade\n" + out[-3000:])
        self.assertEqual(
            json.loads((self.install / "VERSION.json").read_text())["version"], "2.0.0",
            "the upgrade did not leave the new version in place")
        self.assertEqual((self.state / "keep.txt").read_text(), "operator data\n",
                         "operator state was not preserved")
        self.assertTrue(self._previous(self.tmp), "the previous installation was not retained")
        self.assertIn("upgrade: COMPLETE", out)

    def test_upgrade_invoked_externally(self) -> None:
        """The same controller, run from a copy that is not inside the installation at all.

        This is the operator who downloaded the new release and runs its upgrade script from
        the download directory. The controller is the real one; only the two network-bound
        steps beside it are the fixture stand-ins, exactly as in the in-place case.
        """
        external = self.tmp / "downloaded" / "tools" / "release"
        external.mkdir(parents=True)
        shutil.copy2(UPGRADE, external / "upgrade.ps1")
        _write(external / "install.ps1", STUB_INSTALL)
        _write(external / "verify_install.ps1", STUB_VERIFY)
        shutil.copy2(REPO_ROOT / "tools" / "release" / "backup_state.ps1",
                     external / "backup_state.ps1")

        r = self._run(external / "upgrade.ps1",
                      "-Dest", str(self.install), "-Artifact", str(self.artifact))
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-3000:])
        self.assertTrue(self.install.is_dir())
        self.assertEqual(
            json.loads((self.install / "VERSION.json").read_text())["version"], "2.0.0")

    def test_paths_with_spaces_are_handled(self) -> None:
        # The fixture install path already contains a space; assert the retained copy does too.
        r = self._inside("-Dest", str(self.install), "-Artifact", str(self.artifact))
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-2000:])
        previous = self._previous(self.tmp)
        self.assertTrue(previous)
        self.assertIn(" ", previous[0].name)

    def test_artifact_stored_inside_the_outgoing_install(self) -> None:
        inner = self.install / "release-artifacts"
        inner.mkdir()
        moved = inner / self.artifact.name
        shutil.move(str(self.artifact), moved)
        shutil.move(str(self.artifact) + ".sha256", str(moved) + ".sha256")

        r = self._inside("-Dest", str(self.install), "-Artifact", str(moved))
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out[-3000:])
        self.assertIn("stable copy", out,
                      "the controller consumed an artifact it was about to move away")
        self.assertTrue(self.install.is_dir())

    # -- refusals BEFORE anything moves -------------------------------------
    def test_a_malformed_archive_is_refused_before_the_move(self) -> None:
        bad = self._make_artifact(self.tmp / "bad.zip", version="2.0.0",
                                  omit="sovereign-workspace/shell/src/__main__.py")
        r = self._inside("-Dest", str(self.install), "-Artifact", str(bad))
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(self.install.is_dir(), "a malformed archive still displaced the install")
        self.assertFalse(self._previous(self.tmp))

    def test_an_escaping_archive_entry_is_refused(self) -> None:
        evil = self._make_artifact(self.tmp / "evil.zip", version="2.0.0", escape=True)
        r = self._inside("-Dest", str(self.install), "-Artifact", str(evil))
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(self.install.is_dir())

    def test_a_tampered_archive_is_refused(self) -> None:
        with open(self.artifact, "ab") as fh:
            fh.write(b"tampered")
        r = self._inside("-Dest", str(self.install), "-Artifact", str(self.artifact))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("mismatch", (r.stdout + r.stderr).lower())
        self.assertTrue(self.install.is_dir())

    def test_an_occupied_rollback_location_is_refused(self) -> None:
        occupied = self.tmp / "already-there"
        occupied.mkdir()
        r = self._inside("-Dest", str(self.install), "-Artifact", str(self.artifact),
                         "-BackupTo", str(occupied))
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(self.install.is_dir())

    def test_overlapping_rollback_location_is_refused(self) -> None:
        r = self._inside("-Dest", str(self.install), "-Artifact", str(self.artifact),
                         "-BackupTo", str(self.install / "inside"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("overlapping", (r.stdout + r.stderr).lower())
        self.assertTrue(self.install.is_dir())

    def test_overlapping_transaction_root_is_refused(self) -> None:
        r = self._inside("-Dest", str(self.install), "-Artifact", str(self.artifact),
                         "-TransactionRoot", str(self.install / "tx"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("overlapping", (r.stdout + r.stderr).lower())
        self.assertTrue(self.install.is_dir())

    def test_a_filesystem_root_destination_is_refused(self) -> None:
        drive = os.path.splitdrive(str(self.tmp))[0] + os.sep
        r = self._run(UPGRADE, "-Dest", drive, "-Artifact", str(self.artifact))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("root", (r.stdout + r.stderr).lower())

    def test_a_missing_dependency_is_found_before_the_move(self) -> None:
        """A PATH with no `py` launcher must be refused at preflight, not after the cutover."""
        stripped = os.pathsep.join(
            p for p in os.environ.get("PATH", "").split(os.pathsep)
            if p and not (Path(p) / "py.exe").exists())
        r = self._inside("-Dest", str(self.install), "-Artifact", str(self.artifact),
                         env_extra={"PATH": stripped})
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 2, out[-2500:])
        self.assertIn("REFUSED", out)
        self.assertTrue(self.install.is_dir(),
                        "a missing interpreter was discovered after the install had moved")
        self.assertFalse(self._previous(self.tmp))

    def test_a_state_schema_change_requires_acknowledgement(self) -> None:
        shutil.rmtree(self.install)
        self._lay_install(self.install, version="1.0.0", state_schema="v1")
        art = self._make_artifact(self.tmp / "schema.zip", version="2.0.0", state_schema="v2")

        refused = self._inside("-Dest", str(self.install), "-Artifact", str(art))
        self.assertEqual(refused.returncode, 2, (refused.stdout + refused.stderr)[-2000:])
        self.assertIn("state schema", (refused.stdout + refused.stderr).lower())
        self.assertTrue(self.install.is_dir())

        allowed = self._inside("-Dest", str(self.install), "-Artifact", str(art),
                               "-AcceptStateSchemaChange")
        out = allowed.stdout + allowed.stderr
        self.assertEqual(allowed.returncode, 0, out[-2500:])
        self.assertIn("STATE SCHEMA CHANGED", out,
                      "a schema change completed without telling the operator that rolling the "
                      "binaries back would not reverse it")

    # -- failure injection AFTER work has begun -----------------------------
    def test_preparation_failure_leaves_the_installation_untouched(self) -> None:
        r = self._inside("-Dest", str(self.install), "-Artifact", str(self.artifact),
                         "-InjectFailureAt", "prepare")
        self.assertEqual(r.returncode, 3, (r.stdout + r.stderr)[-2000:])
        self.assertTrue(self.install.is_dir())
        self.assertFalse(self._previous(self.tmp))

    def test_cutover_failure_rolls_back_automatically(self) -> None:
        r = self._inside("-Dest", str(self.install), "-Artifact", str(self.artifact),
                         env_extra={"SOVEREIGN_TEST_INSTALL_FAILS": "1"})
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 4, out[-3000:])
        self.assertTrue(self.install.is_dir(), "the install was not restored after a failed cutover")
        self.assertEqual(json.loads((self.install / "VERSION.json").read_text())["version"],
                         "1.0.0", "rollback did not restore the previous version")
        self.assertNotIn("upgrade: COMPLETE", out,
                         "a success line was printed for a failed upgrade")

    def test_postcheck_failure_rolls_back_and_preserves_the_incoming_tree(self) -> None:
        r = self._inside("-Dest", str(self.install), "-Artifact", str(self.artifact),
                         env_extra={"SOVEREIGN_TEST_VERIFY_FAILS": "1"})
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 4, out[-3000:])
        self.assertEqual(json.loads((self.install / "VERSION.json").read_text())["version"],
                         "1.0.0")
        tx = self._tx_roots(self.tmp)
        self.assertTrue(tx, "no transaction root survived for diagnosis")
        preserved = list(tx[0].glob("failed-incoming-*"))
        self.assertTrue(preserved,
                        "the failed incoming installation was discarded instead of preserved")
        self.assertTrue((preserved[0] / "VERSION.json").is_file())

    def test_a_failed_rollback_reports_exact_surviving_locations(self) -> None:
        r = self._inside("-Dest", str(self.install), "-Artifact", str(self.artifact),
                         "-InjectFailureAt", "rollback",
                         env_extra={"SOVEREIGN_TEST_VERIFY_FAILS": "1"})
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 5, out[-3000:])
        self.assertIn("ROLLBACK DID NOT COMPLETE", out)
        previous = self._previous(self.tmp)
        self.assertTrue(previous, "the previous installation is gone AND unreported")
        self.assertIn(str(previous[0]), out,
                      "the report does not name the exact surviving installation path")
        self.assertNotIn("upgrade: COMPLETE", out)

    # -- durability ---------------------------------------------------------
    def test_every_phase_is_journalled(self) -> None:
        r = self._inside("-Dest", str(self.install), "-Artifact", str(self.artifact))
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-2500:])
        tx = self._tx_roots(self.tmp)
        self.assertTrue(tx)
        journal = tx[0] / "upgrade-journal.jsonl"
        self.assertTrue(journal.is_file(), "the transaction left no durable journal")
        phases = [json.loads(l)["phase"]
                  for l in journal.read_text(encoding="utf-8").splitlines() if l.strip()]
        for required in ("resolve", "verify", "preflight", "cutover", "postcheck", "complete"):
            self.assertIn(required, phases,
                          f"phase {required} is absent from the journal: {phases}")

    def test_a_failed_transaction_journals_the_phase_that_failed(self) -> None:
        r = self._inside("-Dest", str(self.install), "-Artifact", str(self.artifact),
                         env_extra={"SOVEREIGN_TEST_INSTALL_FAILS": "1"})
        self.assertEqual(r.returncode, 4)
        tx = self._tx_roots(self.tmp)
        records = [json.loads(l)
                   for l in (tx[0] / "upgrade-journal.jsonl").read_text().splitlines() if l.strip()]
        failed = [x for x in records if x["status"] == "FAILED"]
        self.assertTrue(failed, "the journal does not record which phase failed")
        self.assertEqual(failed[0]["phase"], "cutover")
        self.assertTrue([x for x in records if x["phase"] == "rollback" and x["status"] == "OK"])

    def test_the_controller_runs_from_outside_both_installations(self) -> None:
        """The staged controller must not resolve through the directory being replaced."""
        r = self._inside("-Dest", str(self.install), "-Artifact", str(self.artifact))
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-2500:])
        tx = self._tx_roots(self.tmp)
        self.assertTrue(tx)
        staged = tx[0] / "controller" / "upgrade.ps1"
        self.assertTrue(staged.is_file(),
                        "the controller was never staged outside the installation")


if __name__ == "__main__":
    unittest.main()
