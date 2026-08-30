"""EPC-01 P3-3 — the distribution's docs/ is for the recipient, not the build.

OD-35 removed `evidence/` and `dev/` from the archive. It did not touch `docs/`, which shipped
90 markdown files of which 58 were internal build directives, review pastes, resume pastes,
conflict audits and stop reports — the same class of artifact, in a directory OD-35 did not
reach. `tools-operator/` went with them: its six `Start-OpenCode-*.ps1` launchers are the only
things that reference the cut documents, and no product file references the launchers.

This asserts against the ARCHIVE, built by `git archive`, because that is what a recipient
receives — a working tree still holds every one of those files, correctly.
"""
from __future__ import annotations

import io
import subprocess
import tarfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Prefixes that mark a document as belonging to the build rather than to the recipient.
INTERNAL_PREFIXES = ("CP-", "REM-0", "REVIEW-", "STOP-", "OX-", "EXPORT-", "CLAUDE-")

#: Documents a recipient is expected to read. Each must survive the cut.
MUST_SHIP = (
    "docs/LIMITATIONS.md",
    "docs/SUPPORT-POLICY.md",
    "docs/RELEASE-ASSURANCE.md",
    "docs/THIRD-PARTY-LICENCE-POSITION.md",
    "docs/DECISIONS.md",
    "docs/DISCOVERY.md",
    "docs/ADR-006-no-telemetry.md",
)


def _archive_members() -> set[str]:
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "archive", "--format=tar", "HEAD"],
        capture_output=True, check=True, timeout=600,
    )
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
        return {m.name for m in tar.getmembers() if m.isfile()}


class ArchiveShipsOnlyOperatorDocs(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.members = _archive_members()

    def test_the_archive_is_not_empty(self) -> None:
        """Without this the assertions below could pass on a failed export."""
        self.assertGreater(
            len(self.members), 1000,
            f"only {len(self.members)} members in the archive — the export looks wrong"
        )

    def test_no_internal_build_document_ships(self) -> None:
        offenders = sorted(
            name for name in self.members
            if name.startswith("docs/")
            and Path(name).name.startswith(INTERNAL_PREFIXES)
        )
        self.assertEqual(
            offenders, [],
            "internal build documents are in the distribution. A recipient opening docs/ "
            "should find what was written FOR them, not the running commentary of the build "
            "that produced their copy:\n  " + "\n  ".join(offenders)
        )

    def test_the_build_harness_launchers_do_not_ship(self) -> None:
        offenders = sorted(n for n in self.members if n.startswith("tools-operator/"))
        self.assertEqual(
            offenders, [],
            "tools-operator/ ships. Its launchers drive the build harness and reference "
            "documents the archive no longer contains:\n  " + "\n  ".join(offenders)
        )

    def test_every_operator_facing_document_still_ships(self) -> None:
        """The cut must not take the documents the recipient actually needs."""
        missing = [name for name in MUST_SHIP if name not in self.members]
        self.assertEqual(
            missing, [],
            "the docs cut removed operator-facing documents:\n  " + "\n  ".join(missing)
        )

    def test_the_architecture_decisions_still_ship(self) -> None:
        adrs = sorted(n for n in self.members if n.startswith("docs/ADR-"))
        self.assertGreaterEqual(
            len(adrs), 5,
            f"only {len(adrs)} ADRs ship; a recipient needs the architecture decisions to "
            f"understand what they are running"
        )


if __name__ == "__main__":
    unittest.main()
