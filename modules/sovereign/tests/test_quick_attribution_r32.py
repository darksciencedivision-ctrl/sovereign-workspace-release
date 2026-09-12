"""R32 (F-100) — the answer-integrity guard's four hardenings.

Beyond the Q1 reproduction already covered by test_quick_acceptance_language.py, R32 closes:

  * attribution is required whenever an evidence packet EXISTS, not only when the operator's
    query used a project-fact keyword (a fabricated fact must not ride along on an off-keyword
    question);
  * a clause that pairs an abstention with a concrete assertion is a CLAIM -- the abstention
    exempts only its own predicate, even when the two are joined by a bare "and";
  * passive abstention forms ("cannot be verified from the available evidence") are accepted;
  * "unknown" as a fragment of an identifier (unknown-model:3b) is NOT read as an abstention.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.evidence import EvidencePacket, EvidenceSource  # noqa: E402
from sovereign_product.quality import validate_quick_response  # noqa: E402


def _packet(*source_ids: str) -> EvidencePacket:
    sources = tuple(
        EvidenceSource(
            source_id=sid, kind="project_file", locator=f"fixtures/{sid}.md",
            content_sha256="0" * 64, snippet_sha256="1" * 64, snippet=f"content for {sid}",
            content_bytes=32, snippet_bytes=32, snippet_tokens=8, truncated=False, metadata={},
        )
        for sid in source_ids
    )
    return EvidencePacket(
        session_id="s1", query_sha256="1" * 64, created_at="2026-09-08T00:00:00Z",
        sources=sources, omissions=(), text="\n".join(s.snippet for s in sources),
        total_bytes=32 * len(sources), total_tokens=8 * len(sources), max_bytes=4096,
        max_tokens=1024, token_count_method="fixture", packet_sha256="2" * 64,
    )


PROJECT_QUERY = "What model is configured?"
OFF_KEYWORD_QUERY = "Tell me about the setup here"  # no PROJECT_FACT_QUERY keyword


class AttributionRequiredWhenEvidenceExists(unittest.TestCase):
    def test_evidence_present_forces_attribution_even_off_keyword(self) -> None:
        # The query has no project-fact keyword, but an evidence packet exists, so a fabricated
        # uncited fact must still be rejected.
        ok, reason = validate_quick_response(
            "The configured critic is imaginary-model:999b.",
            _packet("manifest"), query=OFF_KEYWORD_QUERY)
        self.assertFalse(ok, "an uncited fact rode along because the query lacked a keyword")
        self.assertIn("exact evidence citation", reason)

    def test_no_evidence_and_off_keyword_stays_permissive(self) -> None:
        ok, reason = validate_quick_response(
            "A palindrome reads the same forwards and backwards.",
            None, query="What is a palindrome?")
        self.assertTrue(ok, reason)


class CoordinatedAssertionBesideAbstention(unittest.TestCase):
    def test_bare_and_does_not_let_the_assertion_ride_the_abstention(self) -> None:
        # No comma before "and"; the whole thing is one clause. The abstention must not exempt the
        # concrete assertion joined to it.
        ok, _ = validate_quick_response(
            "The model is imaginary-model:999b and its release date is unknown.",
            None, query=PROJECT_QUERY)
        self.assertFalse(ok, "a coordinated assertion rode along on an abstention")

    def test_a_pure_abstention_is_still_accepted(self) -> None:
        ok, reason = validate_quick_response(
            "Its release date is unknown.", None, query=PROJECT_QUERY)
        self.assertTrue(ok, reason)


class PassiveAbstentionForms(unittest.TestCase):
    def test_cannot_be_verified_is_accepted(self) -> None:
        ok, reason = validate_quick_response(
            "That cannot be verified from the available evidence.",
            None, query=PROJECT_QUERY)
        self.assertTrue(ok, reason)

    def test_could_not_be_determined_is_accepted(self) -> None:
        ok, reason = validate_quick_response(
            "The configured model could not be determined from the available evidence.",
            None, query=PROJECT_QUERY)
        self.assertTrue(ok, reason)


class UnknownInsideAnIdentifierIsNotAnAbstention(unittest.TestCase):
    def test_a_fabricated_identifier_containing_unknown_is_rejected(self) -> None:
        ok, _ = validate_quick_response(
            "The configured model is unknown-model:3b.", None, query=PROJECT_QUERY)
        self.assertFalse(
            ok, "'unknown' inside an identifier was read as an abstention and exempted a fact")

    def test_standalone_unknown_still_abstains(self) -> None:
        ok, reason = validate_quick_response(
            "The configured model is unknown.", None, query=PROJECT_QUERY)
        self.assertTrue(ok, reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
