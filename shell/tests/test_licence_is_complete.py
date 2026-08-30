"""EPC-01 P0-1 — the licence and third-party attribution must be complete before shipping.

The defect: `LICENSE` line 2 read "Interim license record; canonical license text to be
supplied by the operator before external distribution", and all five module licence files
carried the same header. No NOTICE existed at all, while 304 third-party library components
shipped. No enterprise legal review passes a licence that names itself provisional.

These tests assert completeness, not word-matching. A licence that merely avoids the string
"interim" while omitting a liability clause would still be unshippable, so the structural
assertions below are the substantive ones.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LICENSE = REPO_ROOT / "LICENSE"
NOTICE = REPO_ROOT / "NOTICE"
POSITION = REPO_ROOT / "docs" / "THIRD-PARTY-LICENCE-POSITION.md"

MODULES = ["sovereign", "sow", "debate", "distillery", "tokencenter"]

#: Phrasings that defer the licence to a document that does not exist. These are the
#: defect, and each is matched as a phrase — not as a bare keyword, so that a licence may
#: still say "this contains no placeholders" without tripping its own guard.
DEFERRAL_PHRASES = [
    "interim license record",
    "interim licence record",
    "to be supplied by the operator",
    "canonical license text to be supplied",
    "canonical licence text to be supplied",
    "license text to follow",
    "licence text to follow",
]

#: A commercial licence that omits any of these is not shippable regardless of its wording.
REQUIRED_SECTIONS = [
    ("definitions", r"\bDEFINITIONS\b"),
    ("grant of rights", r"\bGRANT\b"),
    ("restrictions", r"\bRESTRICTIONS\b"),
    ("warranty disclaimer", r"\bNO WARRANTY\b|\bWARRANT(Y|IES) DISCLAIM"),
    ("limitation of liability", r"\bLIMITATION OF LIABILITY\b"),
    ("term and termination", r"\bTERMINATION\b"),
    ("third-party components", r"\bTHIRD-PARTY COMPONENTS\b"),
]


class LicenceIsComplete(unittest.TestCase):

    def setUp(self) -> None:
        self.assertTrue(LICENSE.is_file(), "LICENSE is missing")
        self.text = LICENSE.read_text(encoding="utf-8")

    def test_the_licence_does_not_defer_itself_to_a_document_that_does_not_exist(self) -> None:
        lowered = self.text.lower()
        found = [p for p in DEFERRAL_PHRASES if p in lowered]
        self.assertEqual(
            found, [],
            "LICENSE defers its own text to a document that does not ship: " + repr(found)
        )

    def test_the_licence_contains_every_clause_a_commercial_licence_needs(self) -> None:
        missing = [
            label for label, pattern in REQUIRED_SECTIONS
            if not re.search(pattern, self.text, re.IGNORECASE)
        ]
        self.assertEqual(
            missing, [],
            "LICENSE is missing required clauses: " + ", ".join(missing)
        )

    def test_the_pending_counsel_marker_is_present_and_narrow(self) -> None:
        """The marker records that review is outstanding. It must NOT suspend any term —
        an operator reading it should not conclude the licence is inoperative."""
        self.assertIn("PENDING COUNSEL SIGN-OFF", self.text,
                      "the licence must state that counsel review is outstanding")
        self.assertRegex(
            self.text, r"Every term (below )?is in force",
            "the pending-counsel marker must state that the terms are nonetheless operative"
        )

    def test_every_module_carries_a_licence_consistent_with_the_root(self) -> None:
        for module in MODULES:
            path = REPO_ROOT / "modules" / module / "LICENSE"
            with self.subTest(module=module):
                self.assertTrue(path.is_file(), f"modules/{module}/LICENSE is missing")
                text = path.read_text(encoding="utf-8").lower()
                for phrase in DEFERRAL_PHRASES:
                    self.assertNotIn(phrase, text,
                                     f"modules/{module}/LICENSE still defers its own text")
                self.assertIn("sovereign workspace", text)

    def test_a_third_party_notice_ships_and_lists_components(self) -> None:
        self.assertTrue(NOTICE.is_file(), "NOTICE is missing; 304 third-party components ship")
        text = NOTICE.read_text(encoding="utf-8")
        match = re.search(r"^Components:\s*(\d+)", text, re.MULTILINE)
        self.assertIsNotNone(match, "NOTICE must state how many components it covers")
        self.assertGreater(int(match.group(1)), 200,
                           "NOTICE covers implausibly few components")

    def test_the_notice_resolved_every_licence(self) -> None:
        text = NOTICE.read_text(encoding="utf-8")
        self.assertNotIn("UNRESOLVED", text,
                         "NOTICE contains UNRESOLVED entries — a component's licence was "
                         "never determined, so the attribution is incomplete")
        self.assertNotIn("UNKNOWN", text,
                         "NOTICE contains UNKNOWN licences — resolve them from the "
                         "component's own metadata rather than shipping the gap")

    def test_a_written_position_exists_for_copyleft_components(self) -> None:
        self.assertTrue(POSITION.is_file(),
                        "docs/THIRD-PARTY-LICENCE-POSITION.md is missing")
        text = POSITION.read_text(encoding="utf-8")
        self.assertIn("MPL-2.0", text)
        self.assertIn("unmodified", text.lower(),
                      "the MPL-2.0 position must state whether the components are modified, "
                      "because that is the fact the obligation turns on")


if __name__ == "__main__":
    unittest.main()
