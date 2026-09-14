"""F-031: Electron zip verification fails closed and never writes a trusted pin."""
from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
PROVISIONER = REPO_ROOT / "shell" / "tools" / "install_sow.py"

import importlib.util

spec = importlib.util.spec_from_file_location("install_sow_f031", PROVISIONER)
sow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sow)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _BytesURL:
    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)

    def __enter__(self):
        return self._buf

    def __exit__(self, *exc):
        return False


class InstallSowHashTests(unittest.TestCase):
    def setUp(self) -> None:
        sow._log_lines.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.desktop = root / "desktop"
        self.electron = self.desktop / "node_modules" / "electron"
        self.electron.mkdir(parents=True)
        self.pin = root / "ADR-005-ELECTRON-ZIP-SHA256.txt"
        self.cache = root / "cache"
        self.cache.mkdir()
        self.ver = "1.2.3"
        self.zip_name = "electron-v{}-win32-x64.zip".format(self.ver)
        self.good = b"good-electron-zip-bytes"
        self.poison = b"poisoned-cached-zip-bytes"
        self.good_digest = _sha(self.good)
        self.poison_digest = _sha(self.poison)

    def _write_checksums(self, mapping) -> None:
        (self.electron / "checksums.json").write_text(
            json.dumps(mapping), encoding="utf-8")

    def _write_pin(self, digest: str) -> None:
        self.pin.write_text("{} {}\n".format(digest, self.zip_name), encoding="utf-8")

    def _write_cache(self, data: bytes) -> Path:
        entry = self.cache / "slot1"
        entry.mkdir(parents=True, exist_ok=True)
        path = entry / self.zip_name
        path.write_bytes(data)
        return path

    def _run(self, allow_unverified=False, url_payload=None):
        def urlopen(url, timeout=None):
            if url_payload is None:
                raise AssertionError("download was not expected: " + url)
            return _BytesURL(url_payload)

        return sow.step_4_5_zip(
            self.ver,
            allow_unverified=allow_unverified,
            desktop=str(self.desktop),
            hash_record=str(self.pin),
            cache_root=str(self.cache),
            urlopen=urlopen,
        )

    def test_matching_digest_from_cache(self) -> None:
        self._write_checksums({self.zip_name: self.good_digest})
        cached = self._write_cache(self.good)
        before = self.pin.exists()
        path, digest, verified = self._run()
        self.assertTrue(verified)
        self.assertEqual(digest, self.good_digest)
        self.assertEqual(Path(path), cached)
        self.assertEqual(self.pin.exists(), before)

    def test_wrong_cached_digest_is_skipped_then_good_download(self) -> None:
        self._write_checksums({self.zip_name: self.good_digest})
        self._write_cache(self.poison)
        path, digest, verified = self._run(url_payload=self.good)
        self.assertTrue(verified)
        self.assertEqual(digest, self.good_digest)
        self.assertNotEqual(Path(path).read_bytes(), self.poison)

    def test_wrong_downloaded_digest_is_rejected_and_removed(self) -> None:
        self._write_checksums({self.zip_name: self.good_digest})
        with self.assertRaises(SystemExit):
            self._run(url_payload=self.poison)
        leftover = list(Path(self.cache).rglob(self.zip_name))
        downloaded = [p for p in leftover if p.read_bytes() == self.poison]
        self.assertFalse(downloaded, "mismatched download must be removed")

    def test_missing_expected_digest_fails_closed(self) -> None:
        self._write_cache(self.good)
        with self.assertRaises(SystemExit) as ctx:
            self._run(url_payload=self.good)
        self.assertNotEqual(ctx.exception.code, 0)
        self.assertFalse(self.pin.exists())

    def test_malformed_checksums_json_fails_closed(self) -> None:
        (self.electron / "checksums.json").write_text("{not json", encoding="utf-8")
        self._write_cache(self.good)
        with self.assertRaises(SystemExit):
            self._run(url_payload=self.good)

    def test_malformed_checksums_entry_fails_closed(self) -> None:
        self._write_checksums({self.zip_name: "not-a-sha"})
        self._write_cache(self.good)
        with self.assertRaises(SystemExit):
            self._run()

    def test_malformed_pin_file_fails_closed(self) -> None:
        self.pin.write_text("gg this is not a hash {}\n".format(self.zip_name), encoding="utf-8")
        with self.assertRaises(SystemExit):
            self._run()

    def test_explicit_unverified_bootstrap_does_not_pin_or_claim_verified(self) -> None:
        path, digest, verified = self._run(allow_unverified=True, url_payload=self.good)
        self.assertFalse(verified)
        self.assertEqual(digest, self.good_digest)
        self.assertTrue(Path(path).is_file())
        self.assertFalse(self.pin.exists())
        joined = "\n".join(sow._log_lines)
        self.assertIn("UNVERIFIED", joined)
        self.assertNotIn("SHA-256 VERIFIED", joined)

    def test_env_var_is_not_an_escape_hatch(self) -> None:
        self._write_cache(self.good)
        with patch.dict(os.environ, {"SWS_ALLOW_UNVERIFIED_ELECTRON": "1"}, clear=False):
            with self.assertRaises(SystemExit):
                self._run(allow_unverified=False, url_payload=self.good)
        self.assertFalse(self.pin.exists())

    def test_no_tracked_document_mutation(self) -> None:
        self._write_pin(self.good_digest)
        before = self.pin.read_bytes()
        self._write_cache(self.good)
        path, digest, verified = self._run()
        self.assertTrue(verified)
        self.assertEqual(self.pin.read_bytes(), before)
        self.assertEqual(digest, self.good_digest)
        self.assertTrue(Path(path).is_file())

    def test_read_only_pin_and_docs_are_not_written(self) -> None:
        self._write_checksums({self.zip_name: self.good_digest})
        self._write_pin("0" * 64)
        os.chmod(self.pin, stat.S_IREAD)
        self.addCleanup(lambda: os.chmod(self.pin, stat.S_IWRITE | stat.S_IREAD))
        before = self.pin.read_bytes()
        self._write_cache(self.good)
        path, digest, verified = self._run()
        self.assertTrue(verified)
        self.assertEqual(digest, self.good_digest)
        self.assertEqual(self.pin.read_bytes(), before)
        self.assertTrue(Path(path).is_file())

    def test_log_default_is_outside_tracked_evidence(self) -> None:
        path = sow.default_log_path()
        self.assertNotIn(os.path.join("evidence", "phase2-sow-install.txt"), path.replace("/", os.sep))
        tracked = str(REPO_ROOT / "evidence")
        self.assertFalse(os.path.normcase(path).startswith(os.path.normcase(tracked)))


class InstallerStillInvokesProvisioner(unittest.TestCase):
    def test_install_ps1_does_not_pass_unverified_flag(self) -> None:
        text = (REPO_ROOT / "tools" / "release" / "install.ps1").read_text(encoding="utf-8")
        self.assertIn("install_sow.py", text)
        self.assertNotIn("allow-unverified-electron", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
