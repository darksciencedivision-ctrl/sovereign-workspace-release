"""EPC-01 P4-1/2/3/8 and P4-7 — the scoped-out limitations must stay disclosed.

The operator ruled at T-1 that this release is enterprise-grade SINGLE-OPERATOR: no
authentication, no RBAC, no security audit log, no multi-user mode. Those are scope
decisions, and the ruling required them to be *named limitations, never silent ones*.

A statement nothing enforces is a statement that will eventually disappear. That is not
hypothetical here: `modules/sow/docs/THREAT_MODEL.md` lost a registered-absence marker when
the underlying gap was closed — the right outcome, reached without anyone noticing the
disclosure had gone with it. This guard means a disclosure can only be removed deliberately,
by someone who also has to change a test.

The assertions are on HEADINGS and on the specific claim each one makes, not on prose, so the
document can be rewritten freely as long as it keeps saying these things.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LIMITATIONS = REPO_ROOT / "docs" / "LIMITATIONS.md"
TELEMETRY_ADR = REPO_ROOT / "docs" / "ADR-006-no-telemetry.md"
SUPPORT_POLICY = REPO_ROOT / "docs" / "SUPPORT-POLICY.md"

#: (heading, a phrase that must appear under it) — the heading proves the topic is covered,
#: the phrase proves it still says the same thing.
REQUIRED_DISCLOSURES = [
    ("No authentication", "unauthenticated"),
    ("No authorization or role separation", "no roles"),
    ("No security audit log", "neither is a security audit log"),
    ("Single operator, loopback only", "loopback"),
    ("No telemetry, no crash reporting, no phone-home", "transmits nothing"),
    ("Windows only", "no macOS or Linux build"),
    ("Nineteen of twenty-nine gates have never been reviewed", "CANDIDATE"),
    ("Verification not performed", "clean-room install"),
    ("The licence is not final", "PENDING COUNSEL SIGN-OFF"),
    ("Uninstall does not work on a used installation", "never been used"),
]


class LimitationsAreDisclosed(unittest.TestCase):

    def setUp(self) -> None:
        self.assertTrue(LIMITATIONS.is_file(), "docs/LIMITATIONS.md is missing")
        self.text = LIMITATIONS.read_text(encoding="utf-8")
        # Phrases are checked against whitespace-collapsed text: the document is wrapped for
        # reading, so a required phrase can legitimately straddle a line break. Headings are
        # still matched line-anchored against the raw text.
        self.flat = re.sub(r"\s+", " ", self.text).lower()

    def test_every_scoped_out_limitation_is_still_disclosed(self) -> None:
        missing = []
        for heading, phrase in REQUIRED_DISCLOSURES:
            if not re.search(r"^#{2,4}\s+" + re.escape(heading) + r"\s*$",
                             self.text, re.MULTILINE):
                missing.append(f"heading {heading!r}")
            elif phrase.lower() not in self.flat:
                missing.append(f"heading {heading!r} present but no longer says {phrase!r}")
        self.assertEqual(
            missing, [],
            "docs/LIMITATIONS.md no longer discloses these. If a limitation was genuinely "
            "REMOVED — the capability now exists — delete its entry from REQUIRED_DISCLOSURES "
            "in the same change, so the removal is a decision somebody made rather than a "
            "disclosure that quietly went away:\n  " + "\n  ".join(missing)
        )

    def test_the_single_operator_ruling_is_stated_as_a_decision_not_a_defect(self) -> None:
        """The operator ruled these OUT of scope. The document must not read as a bug list."""
        self.assertRegex(
            self.text, r"deliberate scope decision",
            "LIMITATIONS.md must say these are scope decisions, or a reader takes the whole "
            "document as a defect backlog"
        )

    def test_the_no_telemetry_decision_is_recorded_as_an_architecture_decision(self) -> None:
        self.assertTrue(TELEMETRY_ADR.is_file(), "docs/ADR-006-no-telemetry.md is missing")
        adr = TELEMETRY_ADR.read_text(encoding="utf-8")
        self.assertIn("Accepted", adr)
        self.assertIn("transmits nothing", adr)
        self.assertRegex(
            adr, r"(?i)consequences",
            "an ADR that records no consequences is a preference, not a decision"
        )

    def test_the_support_policy_states_what_is_not_promised(self) -> None:
        self.assertTrue(SUPPORT_POLICY.is_file(), "docs/SUPPORT-POLICY.md is missing")
        policy = SUPPORT_POLICY.read_text(encoding="utf-8")
        for phrase in ("no SLA", "What is not promised", "responsibility"):
            self.assertIn(
                phrase, policy,
                f"the support policy must state {phrase!r} — an unstated promise is the one "
                f"that gets assumed"
            )


if __name__ == "__main__":
    unittest.main()
