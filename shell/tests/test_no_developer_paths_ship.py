"""EPC-01 P0-4 / P3-2 — no shipped operator-facing document may name the build machine.

The defect: README.md step 1 told an operator to `Expand-Archive` from `D:\\Product Software\\`,
naming a ZIP whose filename ended `- Copy.zip`. That directory exists on exactly one machine, so
a recipient following the primary install document failed at step one.

This test guards the general property rather than the instance. Any absolute drive path, and any
of the known build-tree names, appearing in an operator-facing document is a failure — whether it
arrives by a fresh edit, a doc regeneration, or a copied snippet.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Documents a recipient is expected to read and act on.
OPERATOR_FACING = [
    "README.md",
    "docs/RELEASE-ASSURANCE.md",
    "docs/INSTALL.md",
    "docs/OPERATIONS.md",
    "docs/TROUBLESHOOTING.md",
    "docs/SECURITY.md",
    "docs/SUPPORT-POLICY.md",
]

#: A Windows absolute path with a drive letter. `C:\\SovereignWorkspace` is the documented
#: EXAMPLE destination and is allowed; it is an instruction to the reader, not a leaked fact
#: about the build host.
ABSOLUTE_PATH = re.compile(r"\b[A-Za-z]:\\\\?[A-Za-z0-9 _.\\-]+")

ALLOWED_ABSOLUTE = {
    r"C:\SovereignWorkspace",
}

#: Names of trees that only ever existed on the build machine.
BUILD_TREE_NAMES = [
    "Product Software",
    "producttion software 2",
    "release-worktree",
    "Sov 1",
    "Debate table",
    "multi model terminal app",
    "Sslaw",
]


class NoDeveloperPathsShip(unittest.TestCase):

    def _present(self):
        for rel in OPERATOR_FACING:
            path = REPO_ROOT / rel
            if path.is_file():
                yield rel, path.read_text(encoding="utf-8", errors="replace")

    def test_at_least_the_readme_is_checked(self) -> None:
        """A silent pass because every path was absent would make this test worthless."""
        names = [rel for rel, _ in self._present()]
        self.assertIn("README.md", names, "README.md must exist and be covered by this guard")

    def test_no_operator_facing_document_names_a_build_tree(self) -> None:
        offenders = []
        for rel, text in self._present():
            for needle in BUILD_TREE_NAMES:
                if needle in text:
                    line = next(
                        (i for i, ln in enumerate(text.splitlines(), 1) if needle in ln), 0
                    )
                    offenders.append(f"{rel}:{line} names {needle!r}")
        self.assertEqual(
            offenders, [],
            "operator-facing documents name directories that exist only on the build "
            "machine:\n  " + "\n  ".join(offenders)
        )

    def test_no_operator_facing_document_carries_an_undocumented_absolute_path(self) -> None:
        offenders = []
        for rel, text in self._present():
            for lineno, line in enumerate(text.splitlines(), 1):
                for match in ABSOLUTE_PATH.finditer(line):
                    found = match.group(0)
                    if any(found.startswith(ok) for ok in ALLOWED_ABSOLUTE):
                        continue
                    offenders.append(f"{rel}:{lineno} {found!r}")
        self.assertEqual(
            offenders, [],
            "operator-facing documents carry absolute paths that are not the documented "
            "example destination:\n  " + "\n  ".join(offenders)
        )


if __name__ == "__main__":
    unittest.main()
