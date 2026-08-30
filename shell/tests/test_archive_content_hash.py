"""EPC-01 P2-7 — a consumer must be able to ask whether two archives hold the same files.

Punch List V7 recorded the six per-module archives as "byte-identical in content across two
seals but carrying different sha256", and called them not reproducible. The measurement was
right and the diagnosis was wrong.

`git archive` stamps every archive with the commit it was cut from — a pax global header
`comment=<sha>` in tar, the archive comment in zip. The difference between two archives of
IDENTICAL content cut at different commits is exactly that stamp: for a tar every byte after
the first 1024 matches, for a zip every entry name and body matches. `--mtime` does not help,
because time was never the variable.

That stamp is provenance, not a defect. What was missing is a way to ask the other question,
so a consumer diffing hashes between releases saw all eight artifacts change when only two
had. `tools/release/archive_content_hash.py` answers it, and these tests hold the two
properties that make its answer worth anything: it must say SAME for identical content cut at
different commits, and it must say DIFFERENT for different content — including when the
provenance stamp is the same.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "tools" / "release" / "archive_content_hash.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True, text=True, timeout=300,
    )


def _zip(path: Path, entries: dict[str, bytes], comment: bytes | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, blob in entries.items():
            archive.writestr(name, blob)
        if comment is not None:
            archive.comment = comment
    return path


class ArchiveContentHash(unittest.TestCase):

    def setUp(self) -> None:
        self.assertTrue(TOOL.is_file(), "tools/release/archive_content_hash.py is missing")
        self.tmp = Path(tempfile.mkdtemp(prefix="sov-archive-hash-"))

    def test_identical_content_with_different_provenance_reports_the_same(self) -> None:
        """The property the punch list was actually asking for."""
        entries = {"a/one.txt": b"hello\n", "a/two.bin": bytes(range(64))}
        left = _zip(self.tmp / "left.zip", entries, comment=b"a" * 40)
        right = _zip(self.tmp / "right.zip", entries, comment=b"b" * 40)

        self.assertNotEqual(
            left.read_bytes(), right.read_bytes(),
            "the fixture did not actually produce differing bytes"
        )
        result = _run("--compare", str(left), str(right))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SAME CONTENT", result.stdout)

    def test_different_content_reports_different_even_with_the_same_provenance(self) -> None:
        """The direction that matters more: the tool must not launder a real change."""
        stamp = b"c" * 40
        left = _zip(self.tmp / "l2.zip", {"a/one.txt": b"hello\n"}, comment=stamp)
        right = _zip(self.tmp / "r2.zip", {"a/one.txt": b"HELLO\n"}, comment=stamp)

        result = _run("--compare", str(left), str(right))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("DIFFERENT CONTENT", result.stdout)

    def test_a_renamed_entry_is_different_content(self) -> None:
        """Bodies alone are not enough — the same bytes under a different name is a change."""
        stamp = b"d" * 40
        left = _zip(self.tmp / "l3.zip", {"a/one.txt": b"same\n"}, comment=stamp)
        right = _zip(self.tmp / "r3.zip", {"a/renamed.txt": b"same\n"}, comment=stamp)

        result = _run("--compare", str(left), str(right))
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_it_reports_the_commit_each_archive_was_cut_from(self) -> None:
        """A content digest that hid the provenance would trade one blind spot for another."""
        left = _zip(self.tmp / "l4.zip", {"x.txt": b"1"}, comment=b"e" * 40)
        right = _zip(self.tmp / "r4.zip", {"x.txt": b"1"}, comment=b"f" * 40)
        result = _run("--compare", str(left), str(right))
        self.assertIn("e" * 40, result.stdout)
        self.assertIn("f" * 40, result.stdout)

    def test_it_works_on_the_real_release_artifacts(self) -> None:
        artifacts = sorted((REPO_ROOT / "release-artifacts").glob("*.zip"))
        if not artifacts:
            self.skipTest("no release artifacts present in this worktree")
        result = _run(*[str(p) for p in artifacts])
        self.assertEqual(result.returncode, 0, result.stderr[-600:])
        digests = [line.split()[0] for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(len(digests), len(artifacts))
        self.assertEqual(
            len(set(digests)), len(digests),
            "two different release artifacts produced the same content digest"
        )


if __name__ == "__main__":
    unittest.main()
