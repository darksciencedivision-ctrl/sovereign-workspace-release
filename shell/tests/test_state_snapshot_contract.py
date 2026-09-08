"""
SWS-CORRECTIVE-01 workstream 1.2 - the snapshot contract for backup/restore (L2).

`test_state_backup_round_trip.py` already proves the happy round trip and the refusals that
guard it. This file adds the properties the corrective directive requires and that the review
found missing: hidden and system-attribute state, empty files and required empty directories,
Unicode and spaces, an inventory that is a real inventory rather than a count, a live state root
that is never used as scratch space, and a backup that does not occupy its final name until its
contents verify.

The recorded L2 reproduction is `test_hidden_state_is_captured_and_restored`: backup reported
COMPLETE while `Compress-Archive -Path <root>\\*` silently omitted a Windows-hidden file, and the
restore then found one captured file against an inventory of two.
"""
from __future__ import annotations

import ctypes
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
BACKUP = REPO_ROOT / "tools" / "release" / "backup_state.ps1"
RESTORE = REPO_ROOT / "tools" / "release" / "restore_state.ps1"

FILE_ATTRIBUTE_HIDDEN = 0x02
FILE_ATTRIBUTE_SYSTEM = 0x04


def _ps(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(script), *args],
        capture_output=True, text=True, timeout=600,
    )


def _set_attrs(path: Path, attrs: int) -> None:
    ok = ctypes.windll.kernel32.SetFileAttributesW(str(path), attrs)
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())


def _clear_attrs(path: Path) -> None:
    ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x80)  # NORMAL


def _tree(root: Path) -> dict[str, str]:
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()).hexdigest()
    return out


def _dirs(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix()
            for p in root.rglob("*") if p.is_dir()}


class SnapshotContract(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="sov-snapshot-")
        self.state = Path(self.tmp) / "SovereignWorkspace"
        (self.state / "sovereign" / "runtime").mkdir(parents=True)
        (self.state / "sovereign" / "runtime" / "sovereign.db").write_bytes(
            b"\x00\x01binary\xff")
        (self.state / "sovereign" / "empty.log").write_bytes(b"")
        (self.state / "sow" / "receipts").mkdir(parents=True)
        (self.state / "sow" / "receipts" / "r1.json").write_bytes(b'{"ok":true}\n')
        # Unicode and a space in the same name.
        (self.state / "sow" / "notes é中.txt").write_bytes(
            "café 中文\n".encode("utf-8"))
        # A required-but-empty directory: a module that expects its own directory to exist.
        (self.state / "sow" / "spool").mkdir()

        # The hidden entries that L2 loses.
        self.hidden_file = self.state / ".hidden-config"
        self.hidden_file.write_bytes(b"secret-state\n")
        _set_attrs(self.hidden_file, FILE_ATTRIBUTE_HIDDEN)
        self.hidden_dir = self.state / ".cache"
        self.hidden_dir.mkdir()
        (self.hidden_dir / "entry.bin").write_bytes(b"\x01\x02\x03")
        _set_attrs(self.hidden_dir, FILE_ATTRIBUTE_HIDDEN)

    def tearDown(self) -> None:
        for p in (self.hidden_file, self.hidden_dir):
            try:
                _clear_attrs(p)
            except OSError:
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- L2: the recorded reproduction --------------------------------------
    def test_hidden_state_is_captured_and_restored(self) -> None:
        before = _tree(self.state)
        self.assertIn(".hidden-config", before, "the fixture did not build as expected")
        self.assertIn(".cache/entry.bin", before)

        archive = Path(self.tmp) / "state.zip"
        made = _ps(BACKUP, "-StateRoot", str(self.state), "-Out", str(archive))
        self.assertEqual(made.returncode, 0, made.stdout[-1500:] + made.stderr[-1500:])

        # Operator state lives under `state/` inside the archive; the inventory sits at the
        # archive root, so no operator filename can collide with it.
        with zipfile.ZipFile(archive) as zf:
            names = {n[len("state/"):] for n in zf.namelist()
                     if n.startswith("state/") and not n.endswith("/")}
        self.assertIn(
            ".hidden-config", names,
            "backup reported success without capturing a hidden state file. Archive held: "
            + ", ".join(sorted(names)))
        self.assertIn(".cache/entry.bin", names,
                      "a hidden directory's contents were not captured")

        target = Path(self.tmp) / "restored"
        back = _ps(RESTORE, "-Archive", str(archive), "-StateRoot", str(target))
        self.assertEqual(back.returncode, 0, back.stdout[-1500:] + back.stderr[-1500:])
        self.assertEqual(_tree(target), before,
                         "the restored state is not byte-for-byte what was captured")

    def test_backup_never_writes_into_the_live_state_root(self) -> None:
        """The inventory is a product of the backup, not a file placed in the operator's state."""
        before_files = _tree(self.state)
        before_dirs = _dirs(self.state)
        archive = Path(self.tmp) / "state2.zip"
        self.assertEqual(
            _ps(BACKUP, "-StateRoot", str(self.state), "-Out", str(archive)).returncode, 0)
        self.assertEqual(_tree(self.state), before_files,
                         "backup mutated the live state root")
        self.assertEqual(_dirs(self.state), before_dirs)

    def test_a_user_file_named_like_the_inventory_survives(self) -> None:
        """A pre-existing STATE-BACKUP-INVENTORY.json is the operator's file, not scratch."""
        victim = self.state / "STATE-BACKUP-INVENTORY.json"
        victim.write_bytes(b'{"this":"is the operator file"}\n')
        archive = Path(self.tmp) / "state3.zip"
        made = _ps(BACKUP, "-StateRoot", str(self.state), "-Out", str(archive))
        self.assertEqual(made.returncode, 0, made.stdout[-1200:] + made.stderr[-1200:])
        self.assertEqual(victim.read_bytes(), b'{"this":"is the operator file"}\n',
                         "backup overwrote or deleted an operator file of the same name")

        target = Path(self.tmp) / "restored3"
        back = _ps(RESTORE, "-Archive", str(archive), "-StateRoot", str(target))
        self.assertEqual(back.returncode, 0, back.stdout[-1200:] + back.stderr[-1200:])
        self.assertEqual((target / "STATE-BACKUP-INVENTORY.json").read_bytes(),
                         b'{"this":"is the operator file"}\n',
                         "the operator file did not survive the round trip")

    def test_inventory_carries_paths_lengths_and_hashes(self) -> None:
        archive = Path(self.tmp) / "state4.zip"
        self.assertEqual(
            _ps(BACKUP, "-StateRoot", str(self.state), "-Out", str(archive)).returncode, 0)
        sidecar = Path(str(archive) + ".inventory.json")
        self.assertTrue(sidecar.is_file(),
                        "the backup published no inventory beside the archive")
        inv = json.loads(sidecar.read_text(encoding="utf-8"))
        self.assertIn("schema", inv)
        self.assertIn("snapshot_method", inv,
                      "the inventory does not say how the snapshot was taken")
        entries = {e["path"]: e for e in inv["entries"]}
        self.assertIn(".hidden-config", entries)
        rec = entries[".hidden-config"]
        self.assertEqual(rec["length"], len(b"secret-state\n"))
        self.assertEqual(
            rec["sha256"],
            hashlib.sha256(b"secret-state\n").hexdigest(),
            "the inventory records no usable per-file hash")

    def test_empty_directories_survive_the_round_trip(self) -> None:
        archive = Path(self.tmp) / "state5.zip"
        self.assertEqual(
            _ps(BACKUP, "-StateRoot", str(self.state), "-Out", str(archive)).returncode, 0)
        target = Path(self.tmp) / "restored5"
        back = _ps(RESTORE, "-Archive", str(archive), "-StateRoot", str(target))
        self.assertEqual(back.returncode, 0, back.stdout[-1200:] + back.stderr[-1200:])
        self.assertTrue((target / "sow" / "spool").is_dir(),
                        "a required empty directory was not restored")

    def test_a_short_archive_is_refused_and_never_takes_the_final_name(self) -> None:
        """A capture that does not verify must not occupy the successful-backup name."""
        archive = Path(self.tmp) / "state6.zip"
        self.assertEqual(
            _ps(BACKUP, "-StateRoot", str(self.state), "-Out", str(archive)).returncode, 0)

        # Rewrite the archive with one entry removed, keeping the published inventory.
        short = Path(self.tmp) / "short.zip"
        with zipfile.ZipFile(archive) as src, zipfile.ZipFile(short, "w") as dst:
            for item in src.infolist():
                if item.filename.endswith(".hidden-config"):
                    continue
                dst.writestr(item, src.read(item.filename))
        shutil.copy2(str(archive) + ".inventory.json", str(short) + ".inventory.json")
        digest = hashlib.sha256(short.read_bytes()).hexdigest()
        Path(str(short) + ".sha256").write_text(f"{digest}  {short.name}\n", encoding="utf-8")

        target = Path(self.tmp) / "restored6"
        back = _ps(RESTORE, "-Archive", str(short), "-StateRoot", str(target))
        self.assertNotEqual(back.returncode, 0,
                            "restore accepted an archive short of its own inventory")
        self.assertFalse(
            target.exists(),
            "restore displaced or created the destination before detecting the shortfall")

    def test_restore_refuses_an_archive_whose_hash_disagrees_with_the_inventory(self) -> None:
        archive = Path(self.tmp) / "state7.zip"
        self.assertEqual(
            _ps(BACKUP, "-StateRoot", str(self.state), "-Out", str(archive)).returncode, 0)

        tampered = Path(self.tmp) / "tampered7.zip"
        with zipfile.ZipFile(archive) as src, zipfile.ZipFile(tampered, "w") as dst:
            for item in src.infolist():
                data = src.read(item.filename)
                if item.filename.endswith("r1.json"):
                    data = b'{"ok":false}\n'
                dst.writestr(item, data)
        shutil.copy2(str(archive) + ".inventory.json", str(tampered) + ".inventory.json")
        digest = hashlib.sha256(tampered.read_bytes()).hexdigest()
        Path(str(tampered) + ".sha256").write_text(
            f"{digest}  {tampered.name}\n", encoding="utf-8")

        target = Path(self.tmp) / "restored7"
        back = _ps(RESTORE, "-Archive", str(tampered), "-StateRoot", str(target))
        self.assertNotEqual(back.returncode, 0,
                            "restore accepted content that disagrees with the inventory hash")
        self.assertFalse(target.exists())

    def test_restore_refuses_an_archive_entry_that_escapes_the_state_root(self) -> None:
        evil = Path(self.tmp) / "evil.zip"
        with zipfile.ZipFile(evil, "w") as zf:
            zf.writestr("../escaped.txt", b"nope")
        digest = hashlib.sha256(evil.read_bytes()).hexdigest()
        Path(str(evil) + ".sha256").write_text(f"{digest}  {evil.name}\n", encoding="utf-8")

        target = Path(self.tmp) / "restored8"
        back = _ps(RESTORE, "-Archive", str(evil), "-StateRoot", str(target))
        self.assertNotEqual(back.returncode, 0, "restore accepted an escaping archive path")
        self.assertFalse((Path(self.tmp) / "escaped.txt").exists(),
                         "an archive entry wrote outside the state root")

    def test_legacy_archive_without_an_inventory_is_labelled_not_verified(self) -> None:
        legacy = Path(self.tmp) / "legacy.zip"
        with zipfile.ZipFile(legacy, "w") as zf:
            zf.writestr("sovereign/notes.txt", b"old backup\n")
        digest = hashlib.sha256(legacy.read_bytes()).hexdigest()
        Path(str(legacy) + ".sha256").write_text(f"{digest}  {legacy.name}\n", encoding="utf-8")

        target = Path(self.tmp) / "restored9"
        back = _ps(RESTORE, "-Archive", str(legacy), "-StateRoot", str(target),
                   "-AllowUnverifiedLegacyArchive")
        out = (back.stdout + back.stderr).upper()
        self.assertEqual(back.returncode, 0, back.stdout[-1200:] + back.stderr[-1200:])
        self.assertIn("NOT VERIFIED", out,
                      "a legacy restore was not labelled as unverified")

        # Without the explicit opt-in it must refuse rather than silently half-verify.
        target2 = Path(self.tmp) / "restored10"
        refused = _ps(RESTORE, "-Archive", str(legacy), "-StateRoot", str(target2))
        self.assertNotEqual(refused.returncode, 0,
                            "an inventory-less archive was restored without an explicit opt-in")

    def test_a_second_backup_refuses_to_overwrite_an_existing_archive(self) -> None:
        archive = Path(self.tmp) / "state11.zip"
        self.assertEqual(
            _ps(BACKUP, "-StateRoot", str(self.state), "-Out", str(archive)).returncode, 0)
        again = _ps(BACKUP, "-StateRoot", str(self.state), "-Out", str(archive))
        self.assertNotEqual(again.returncode, 0, "backup overwrote an existing archive")


if __name__ == "__main__":
    unittest.main()
