"""EPC-01 P4-5 — operator state must be capturable and restorable, and the round trip proven.

There was no backup or restore tooling and no documented state inventory, while uninstall
could not run on a used installation (P0-5) and no upgrade path existed (P1-1). The only
honest advice was "copy some directories by hand", with no way to check the copy afterwards.

P4-4 gave state a single home, so it can be captured as one thing. These tests drive the real
scripts against a synthetic state root — never the operator's — and prove the properties that
make the tooling trustworthy rather than merely present:

  * a round trip reproduces every file BYTE-FOR-BYTE, not just by name or count;
  * restore REFUSES an archive whose sidecar does not match, before writing anything;
  * restore refuses to overwrite live state unless asked, and even then MOVES it aside.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP = REPO_ROOT / "tools" / "release" / "backup_state.ps1"
RESTORE = REPO_ROOT / "tools" / "release" / "restore_state.ps1"


def _ps(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(script), *args],
        capture_output=True, text=True, timeout=300,
    )


def _tree(root: Path) -> dict[str, str]:
    """relative posix path -> sha256, for every file under root."""
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


class StateBackupRoundTrip(unittest.TestCase):

    def setUp(self) -> None:
        self.assertTrue(BACKUP.is_file(), "tools/release/backup_state.ps1 is missing")
        self.assertTrue(RESTORE.is_file(), "tools/release/restore_state.ps1 is missing")
        self.tmp = tempfile.mkdtemp(prefix="sov-state-test-")
        self.state = Path(self.tmp) / "SovereignWorkspace"
        # A synthetic state root shaped like the real one: several modules, nested paths,
        # binary content, and an empty-ish file.
        for module, files in {
            "sovereign": {"runtime/sovereign.db": b"\x00\x01binary\xff",
                          "logs/run.log": b"line one\nline two\n"},
            "sow": {"receipts/r1.json": b'{"ok":true}\n'},
            "tokencenter": {"data/piggybank.sqlite": bytes(range(256))},
        }.items():
            for rel, blob in files.items():
                target = self.state / module / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(blob)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_round_trip_reproduces_every_file_byte_for_byte(self) -> None:
        before = _tree(self.state)
        self.assertEqual(len(before), 4, "the fixture did not build as expected")

        archive = Path(self.tmp) / "state.zip"
        made = _ps(BACKUP, "-StateRoot", str(self.state), "-Out", str(archive))
        self.assertEqual(made.returncode, 0, made.stderr[-800:])
        self.assertTrue(archive.is_file(), "backup produced no archive")
        self.assertTrue(Path(str(archive) + ".sha256").is_file(), "backup produced no sidecar")

        shutil.rmtree(self.state)
        back = _ps(RESTORE, "-Archive", str(archive), "-StateRoot", str(self.state))
        self.assertEqual(back.returncode, 0, back.stderr[-800:])

        after = _tree(self.state)
        self.assertEqual(
            after, before,
            "the restored state differs from what was captured. Differences:\n"
            + "\n".join(
                f"  {k}: {before.get(k, 'ABSENT')} -> {after.get(k, 'ABSENT')}"
                for k in sorted(set(before) | set(after))
                if before.get(k) != after.get(k)
            )
        )

    def test_restore_refuses_an_archive_whose_sidecar_does_not_match(self) -> None:
        archive = Path(self.tmp) / "tampered.zip"
        made = _ps(BACKUP, "-StateRoot", str(self.state), "-Out", str(archive))
        self.assertEqual(made.returncode, 0, made.stderr[-400:])

        # Corrupt the archive AFTER its sidecar was written.
        with open(archive, "ab") as fh:
            fh.write(b"tampered")

        target = Path(self.tmp) / "restored"
        back = _ps(RESTORE, "-Archive", str(archive), "-StateRoot", str(target))
        self.assertNotEqual(back.returncode, 0, "restore accepted a tampered archive")
        self.assertIn("mismatch", (back.stderr + back.stdout).lower())
        self.assertFalse(
            target.exists(),
            "restore wrote to the destination before verifying the archive"
        )

    def test_restore_refuses_an_archive_with_no_sidecar(self) -> None:
        archive = Path(self.tmp) / "unsigned.zip"
        made = _ps(BACKUP, "-StateRoot", str(self.state), "-Out", str(archive))
        self.assertEqual(made.returncode, 0, made.stderr[-400:])
        os.remove(str(archive) + ".sha256")

        back = _ps(RESTORE, "-Archive", str(archive),
                   "-StateRoot", str(Path(self.tmp) / "nowhere"))
        self.assertNotEqual(back.returncode, 0, "restore accepted an unverifiable archive")

    def test_restore_does_not_overwrite_live_state_without_being_asked(self) -> None:
        archive = Path(self.tmp) / "state2.zip"
        self.assertEqual(
            _ps(BACKUP, "-StateRoot", str(self.state), "-Out", str(archive)).returncode, 0)

        back = _ps(RESTORE, "-Archive", str(archive), "-StateRoot", str(self.state))
        self.assertNotEqual(
            back.returncode, 0,
            "restore overwrote a state root that already held files, without -Force"
        )
        self.assertEqual(len(_tree(self.state)), 4, "the live state was disturbed anyway")

    def test_forced_restore_moves_live_state_aside_rather_than_deleting_it(self) -> None:
        archive = Path(self.tmp) / "state3.zip"
        self.assertEqual(
            _ps(BACKUP, "-StateRoot", str(self.state), "-Out", str(archive)).returncode, 0)

        marker = self.state / "sovereign" / "logs" / "only-in-live.log"
        marker.write_bytes(b"this file is not in the archive\n")

        back = _ps(RESTORE, "-Archive", str(archive), "-StateRoot", str(self.state), "-Force")
        self.assertEqual(back.returncode, 0, back.stderr[-800:])

        displaced = list(Path(self.tmp).glob("SovereignWorkspace.displaced-*"))
        self.assertTrue(
            displaced,
            "forced restore did not preserve the state it replaced; a mistaken restore would "
            "be unrecoverable"
        )
        survivor = displaced[0] / "sovereign" / "logs" / "only-in-live.log"
        self.assertTrue(survivor.is_file(), "the displaced copy is incomplete")


if __name__ == "__main__":
    unittest.main()
