"""EPC-01 P4-9 — the operator documentation must exist, ship, and stay honest.

Before this, the product had a 97-line README that began by telling the operator to extract
archives from a directory on the build machine, and nothing else. No install guide, no
operations guide, no troubleshooting, no security document, and no workspace-level threat
model — `THREAT_MODEL.md` existed only inside `modules/sow`.

These assertions are deliberately about STRUCTURE and CROSS-REFERENCE rather than prose. A
document can be rewritten freely; what must not happen is one of them disappearing, or the set
drifting apart so that a limitation disclosed in one is silently absent from another.
"""
from __future__ import annotations

import io
import re
import subprocess
import tarfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"

REQUIRED = {
    "INSTALL.md": ("install.ps1", "verify_install.ps1", "uninstall.ps1"),
    "OPERATIONS.md": ("/v1/health", "/ready", "package_boundary_gate"),
    "TROUBLESHOOTING.md": ("OLLAMA_MODELS", "degraded", "upgrade.ps1"),
    "SECURITY.md": ("loopback", "No authentication", "NOT tested"),
    "THREAT_MODEL.md": ("NOT IMPLEMENTED", "OUT OF SCOPE", "ENFORCED"),
}

#: Defects an operator will meet in normal use. Each must be findable from the document a
#: person would actually open, not only from LIMITATIONS.md.
CROSS_REFERENCED_DEFECTS = {
    # P0-5 (uninstall), P1-1 (upgrade) and P4-4 (state location) were listed here and are now
    # CLOSED, so their ids no longer appear in the operator documentation — correctly, because
    # a troubleshooting guide should not send a reader chasing a defect that no longer exists.
    # This guard caught their removal and made it deliberate, which is what it is for.
    "P4-6": ("OPERATIONS.md", "THREAT_MODEL.md"),
}

#: Capabilities that replaced closed defects. An operator must be able to find these from the
#: document they would actually open, for the same reason the defects had to be findable.
CROSS_REFERENCED_CAPABILITIES = {
    "upgrade.ps1": ("TROUBLESHOOTING.md", "INSTALL.md"),
    "backup_state.ps1": ("TROUBLESHOOTING.md", "OPERATIONS.md", "INSTALL.md"),
    "PurgeData": ("TROUBLESHOOTING.md", "INSTALL.md"),
    "LOCALAPPDATA": ("OPERATIONS.md", "INSTALL.md", "THREAT_MODEL.md"),
}


class OperatorDocumentationExists(unittest.TestCase):

    def test_every_operator_document_exists(self) -> None:
        missing = [name for name in REQUIRED if not (DOCS / name).is_file()]
        self.assertEqual(missing, [], "operator documentation missing: " + ", ".join(missing))

    def test_each_document_covers_what_it_claims_to(self) -> None:
        problems = []
        for name, needles in REQUIRED.items():
            path = DOCS / name
            if not path.is_file():
                continue
            flat = re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))
            for needle in needles:
                if needle not in flat:
                    problems.append(f"{name} no longer mentions {needle!r}")
        self.assertEqual(problems, [], "\n  ".join([""] + problems))

    def test_known_defects_are_findable_where_an_operator_would_look(self) -> None:
        problems = []
        for defect, documents in CROSS_REFERENCED_DEFECTS.items():
            for name in documents:
                path = DOCS / name
                if not path.is_file():
                    problems.append(f"{name} is missing entirely")
                    continue
                if defect not in path.read_text(encoding="utf-8"):
                    problems.append(f"{name} no longer names {defect}")
        self.assertEqual(
            problems, [],
            "a defect an operator meets in normal use is documented in LIMITATIONS.md but "
            "not where they would actually look:\n  " + "\n  ".join(problems)
        )

    def test_lifecycle_capabilities_are_findable_where_an_operator_would_look(self) -> None:
        """The counterpart to the defect check above. A capability an operator needs in a
        crisis — how do I back this up, how do I roll back — must be in the document they
        reach for, not only in a release note."""
        problems = []
        for capability, documents in CROSS_REFERENCED_CAPABILITIES.items():
            for name in documents:
                path = DOCS / name
                if not path.is_file():
                    problems.append(f"{name} is missing entirely")
                    continue
                if capability not in path.read_text(encoding="utf-8"):
                    problems.append(f"{name} does not mention {capability}")
        self.assertEqual(
            problems, [],
            "an operator cannot find a lifecycle capability from the document they would "
            "actually open:\n  " + "\n  ".join(problems)
        )

    def test_no_operator_document_promises_a_support_channel(self) -> None:
        """The product transmits nothing and there is no ticketing system. A document that
        implies otherwise is worse than silence."""
        for name in REQUIRED:
            path = DOCS / name
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8").lower()
            with self.subTest(document=name):
                self.assertNotRegex(
                    text, r"(contact support|support team will|we will respond|open a ticket)",
                    f"{name} implies a support channel that does not exist"
                )

    def test_the_operator_documentation_actually_ships(self) -> None:
        """P3-3 export-ignores most of docs/. These must survive that cut."""
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "archive", "--format=tar", "HEAD"],
            capture_output=True, check=True, timeout=600,
        )
        with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
            members = {m.name for m in tar.getmembers() if m.isfile()}
        missing = [f"docs/{name}" for name in REQUIRED if f"docs/{name}" not in members]
        self.assertEqual(
            missing, [],
            "operator documentation was cut from the distribution:\n  " + "\n  ".join(missing)
        )


if __name__ == "__main__":
    unittest.main()
