#!/usr/bin/env python
"""F-071 tests for tools/release/hash_python_locks.py. Offline: the index is a fake.

The locks were `==`-pinned with zero `--hash=` entries, so pip could not verify a single downloaded
byte and install.ps1 (correctly) refused every shipped lock. These tests pin the three properties the
gate exists for: --write records hashes WITHOUT changing versions; --check refuses a lock that is
missing, malformed or partially hashed; and --check is not satisfied by content it did not produce.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hash_python_locks as subject  # noqa: E402

A, B, C = "a" * 64, "b" * 64, "c" * 64


def _file(filename: str, digest: str, kind: str = "bdist_wheel") -> dict:
    return {"filename": filename, "packagetype": kind, "digests": {"sha256": digest}}


INDEX = {
    ("demo", "1.0"): [
        _file("demo-1.0-cp312-cp312-win_amd64.whl", B),
        _file("demo-1.0-cp312-cp312-manylinux_2_17_x86_64.whl", C),  # other platform: not pinned
        _file("demo-1.0-py3-none-any.whl", A),
        _file("demo-1.0.tar.gz", C, kind="sdist"),                    # --only-binary: not pinned
    ],
    ("linuxonly", "2.0"): [_file("linuxonly-2.0-cp312-cp312-manylinux_2_17_x86_64.whl", C)],
}


def fake_fetch(name: str, version: str) -> list[dict]:
    return INDEX[(name, version)]


class HashPythonLocksTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path

    def test_write_records_supported_wheel_hashes_and_keeps_versions(self) -> None:
        path = self._write("lock.txt", "# keep me\n\ndemo==1.0\n")
        self.assertEqual([], subject.write_lock(self.root, "lock.txt", (3, 12), fake_fetch))
        text = path.read_text(encoding="utf-8")
        self.assertEqual(
            f"# keep me\n\ndemo==1.0 \\\n    --hash=sha256:{A} \\\n    --hash=sha256:{B}\n", text)
        self.assertNotIn(C, text, "an sdist or another platform's wheel must not be pinned")
        self.assertEqual([], subject.check_lock(self.root, "lock.txt", {"lock.txt"}))

    def test_write_is_idempotent_and_reads_a_utf16_freeze(self) -> None:
        path = self.root / "lock.txt"
        path.write_bytes("demo==1.0\r\n".encode("utf-16"))
        subject.write_lock(self.root, "lock.txt", (3, 12), fake_fetch)
        first = path.read_bytes()
        subject.write_lock(self.root, "lock.txt", (3, 12), fake_fetch)
        self.assertEqual(first, path.read_bytes())
        self.assertFalse(first.startswith(b"\xff\xfe"), "rewritten as UTF-8")

    def test_write_refuses_a_pin_the_target_interpreter_cannot_install(self) -> None:
        path = self._write("lock.txt", "linuxonly==2.0\n")
        problems = subject.write_lock(self.root, "lock.txt", (3, 12), fake_fetch)
        self.assertTrue(any("no wheel installable" in p for p in problems), problems)
        self.assertEqual("linuxonly==2.0\n", path.read_text(encoding="utf-8"), "nothing written")

    def test_check_refuses_an_unhashed_lock(self) -> None:
        self._write("lock.txt", "demo==1.0\n")
        problems = subject.check_lock(self.root, "lock.txt", {"lock.txt"})
        self.assertTrue(any("carries no --hash" in p for p in problems), problems)

    def test_check_refuses_a_partially_hashed_lock(self) -> None:
        self._write("lock.txt", f"demo==1.0 \\\n    --hash=sha256:{A}\nother==3.0\n")
        problems = subject.check_lock(self.root, "lock.txt", {"lock.txt"})
        self.assertTrue(any("other==3.0 carries no --hash" in p for p in problems), problems)

    def test_check_refuses_malformed_hashes_and_non_exact_pins(self) -> None:
        for body in (f"demo==1.0 --hash=sha256:{'A' * 64}\n",       # uppercase hex
                     "demo==1.0 --hash=sha256:deadbeef\n",           # short
                     f"demo==1.0 --hash=md5:{A[:32]}\n",             # wrong algorithm
                     f"demo>=1.0 \\\n    --hash=sha256:{A}\n"):      # not an exact pin
            with self.subTest(body=body):
                self._write("lock.txt", body)
                self.assertNotEqual([], subject.check_lock(self.root, "lock.txt", {"lock.txt"}))

    def test_check_refuses_options_other_than_a_checked_include(self) -> None:
        hashed = f"demo==1.0 \\\n    --hash=sha256:{A}\n"
        self._write("base.txt", hashed)
        self._write("dev.txt", f"-r base.txt\n\n{hashed}")
        self.assertEqual([], subject.check_lock(self.root, "dev.txt", {"dev.txt", "base.txt"}))
        self.assertTrue(subject.check_lock(self.root, "dev.txt", {"dev.txt"}),
                        "an include the gate does not also check must be refused")
        self._write("dev.txt", f"--extra-index-url https://example.invalid/simple\n{hashed}")
        self.assertTrue(subject.check_lock(self.root, "dev.txt", {"dev.txt"}))

    def test_check_refuses_duplicates_and_non_canonical_bytes(self) -> None:
        self._write("lock.txt", f"demo==1.0 \\\n    --hash=sha256:{A}\nDemo==1.0 \\\n    --hash=sha256:{A}\n")
        self.assertTrue(any("duplicate" in p for p in
                            subject.check_lock(self.root, "lock.txt", {"lock.txt"})))
        self._write("lock.txt", f"demo==1.0 --hash=sha256:{B} --hash=sha256:{A}\r\n")
        self.assertTrue(any("canonical" in p for p in
                            subject.check_lock(self.root, "lock.txt", {"lock.txt"})))

    def test_verify_index_detects_a_substituted_hash(self) -> None:
        self._write("lock.txt", f"demo==1.0 \\\n    --hash=sha256:{A} \\\n    --hash=sha256:{C}\n")
        problems = subject.verify_lock(self.root, "lock.txt", (3, 12), fake_fetch)
        self.assertTrue(any("differ from the index" in p for p in problems), problems)

    def test_the_shipped_locks_are_hashed_and_canonical(self) -> None:
        """The real gate, against the real tree (offline)."""
        root = subject.REPO_ROOT
        checked = {rel for rel, _ in subject.LOCKS}
        for rel, _target in subject.LOCKS:
            with self.subTest(lock=rel):
                self.assertEqual([], subject.check_lock(root, rel, checked))

    def test_installable_by_follows_the_tag_rules_it_relies_on(self) -> None:
        ok = subject.installable_by
        self.assertTrue(ok("x-1-cp312-cp312-win_amd64.whl", (3, 12)))
        self.assertFalse(ok("x-1-cp313-cp313-win_amd64.whl", (3, 12)))
        self.assertTrue(ok("x-1-cp39-abi3-win_amd64.whl", (3, 12)))
        self.assertFalse(ok("x-1-cp313-abi3-win_amd64.whl", (3, 12)))
        self.assertTrue(ok("x-1-py2.py3-none-any.whl", (3, 14)))
        self.assertFalse(ok("x-1-cp314-cp314t-win_amd64.whl", (3, 14)))
        self.assertFalse(ok("x-1-cp312-cp312-win32.whl", (3, 12)))


if __name__ == "__main__":
    unittest.main()
