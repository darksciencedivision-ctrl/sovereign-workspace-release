"""EPC-01 P3-1 — running this suite must not dirty the source tree.

A full run left sixteen untracked directories under `modules/debate/tests/`. That is not
merely untidy: `tools/release/build_release.ps1` refuses to cut a release from a tree with
modifications, and `package_boundary_gate` counts stray files as violations. SOW guards this
class with `test_runtime_writes_are_gitignored.py`; debate had nothing.

Asserting "the tree is clean right now" from inside the session would be circular — the
sweeper in conftest.py has not run yet, and the scratch directories these tests need are
legitimately present while they run. So this checks the two things that make the outcome
inevitable instead: every prefix the suite writes is swept, and every prefix is also ignored
so a hard-killed run cannot leave a tracked-tree change behind.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
MODULE_ROOT = TESTS_DIR.parent
GITIGNORE = MODULE_ROOT / ".gitignore"
CONFTEST = TESTS_DIR / "conftest.py"

#: Every `tempfile.mkdtemp(prefix=..., dir=ROOT / "tests")` call in the suite.
MKDTEMP_PREFIX = re.compile(r'mkdtemp\(\s*prefix\s*=\s*"([^"]+)"')


def _prefixes_the_suite_writes() -> set[str]:
    found: set[str] = set()
    for path in TESTS_DIR.glob("*.py"):
        for match in MKDTEMP_PREFIX.finditer(path.read_text(encoding="utf-8")):
            found.add(match.group(1))
    return found


class SuiteLeavesNoLitter(unittest.TestCase):

    def test_the_suite_really_does_write_scratch_directories(self) -> None:
        """If this ever finds none, the two tests below would pass vacuously."""
        self.assertTrue(
            _prefixes_the_suite_writes(),
            "no mkdtemp prefixes found — this guard has gone blind"
        )

    def test_every_scratch_prefix_is_swept_by_conftest(self) -> None:
        swept = CONFTEST.read_text(encoding="utf-8")
        unswept = [
            prefix for prefix in sorted(_prefixes_the_suite_writes())
            # conftest sweeps by startswith, so a registered prefix may be shorter
            if not any(prefix.startswith(known) for known in _registered_prefixes(swept))
        ]
        self.assertEqual(
            unswept, [],
            "these scratch prefixes are created by the suite but not swept by "
            "tests/conftest.py, so they survive the session:\n  " + "\n  ".join(unswept)
        )

    def test_every_scratch_prefix_is_also_gitignored(self) -> None:
        """The sweeper does not run if the session is hard-killed. The ignore rule is what
        stops that leaving a dirty tree behind."""
        self.assertTrue(GITIGNORE.is_file(), "modules/debate/.gitignore is missing")
        ignored = GITIGNORE.read_text(encoding="utf-8")
        missing = [
            prefix for prefix in sorted(_prefixes_the_suite_writes())
            if f"tests/{prefix}" not in ignored
            and not any(
                f"tests/{known}*" in ignored and prefix.startswith(known)
                for known in _registered_prefixes(ignored, from_gitignore=True)
            )
        ]
        self.assertEqual(
            missing, [],
            "these scratch prefixes are not covered by .gitignore, so a hard-killed run "
            "leaves untracked files in the source tree:\n  " + "\n  ".join(missing)
        )


def _registered_prefixes(text: str, from_gitignore: bool = False) -> list[str]:
    if from_gitignore:
        return [
            line.strip()[len("tests/"):].rstrip("*")
            for line in text.splitlines()
            if line.strip().startswith("tests/.")
        ]
    match = re.search(r"SCRATCH_PREFIXES\s*=\s*\((.*?)\)", text, re.S)
    if not match:
        return []
    return re.findall(r'"([^"]+)"', match.group(1))


if __name__ == "__main__":
    unittest.main()
