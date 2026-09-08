"""Acceptance harness must refuse a temp junction that targets protected data."""
from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ACCEPT = REPO_ROOT / "tools" / "acceptance" / "run_acceptance.ps1"


class AcceptancePathGuard(unittest.TestCase):
    def test_junction_under_temp_targeting_protected_fixture_is_refused(self) -> None:
        protected = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / (
            "SWS-ACCEPT-PROTECTED-FIXTURE-" + os.urandom(4).hex()
        )
        bait = Path(tempfile.mkdtemp(prefix="sws-accept-junction-bait-"))
        junction = bait / "escape"
        canary = protected / "canary.txt"
        payload = b"do-not-touch\n"
        try:
            protected.mkdir(parents=True)
            canary.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            created = subprocess.run(
                ["cmd.exe", "/c", "mklink", "/J", str(junction), str(protected)],
                capture_output=True, text=True)
            if created.returncode != 0:
                self.skipTest("cannot create junction: " + (created.stdout + created.stderr)[-400:])
            dummy_art = bait / "missing.zip"
            evid = bait / "evidence"
            evid.mkdir()
            proc = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(ACCEPT),
                 "-InstallRoot", str(bait / "install"),
                 "-Artifact", str(dummy_art),
                 "-StateRoot", str(junction),
                 "-EvidenceDir", str(evid)],
                capture_output=True, text=True, timeout=60)
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            combined = (proc.stdout + proc.stderr).lower()
            self.assertTrue(
                "reparse" in combined or "canonical" in combined or "must live under" in combined,
                combined[-1500:])
            self.assertEqual(canary.read_bytes(), payload)
            self.assertEqual(hashlib.sha256(canary.read_bytes()).hexdigest(), digest)
        finally:
            if junction.exists():
                subprocess.run(["cmd.exe", "/c", "rmdir", str(junction)], capture_output=True)
            if protected.exists():
                canary.unlink(missing_ok=True)
                protected.rmdir()
            # bait is under temp; do not recurse through a leftover junction
            for child in list(bait.iterdir()) if bait.exists() else []:
                if child.is_symlink() or child.is_dir():
                    continue
                try:
                    child.unlink()
                except OSError:
                    pass


if __name__ == "__main__":
    unittest.main()
