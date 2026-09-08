"""
SWS-CORRECTIVE-01 workstream 4.1 - the QUICK acceptance-language contract (Q1).

The recorded reproduction is `test_unsupported_claim_plus_unknown_is_refused`. Before the
repair, `UNKNOWN_LANGUAGE` was searched over the WHOLE answer, so one unrelated "unknown"
anywhere in the text exempted every other assertion from needing evidence:

    >>> validate_quick_response(
    ...     'The configured model is imaginary-model:999b. Its release date is unknown.',
    ...     None, query='What model is configured?')
    (True, None)

These tests cover the regression cases the directive names, and they assert the validator's
LABELLING as well as its verdict: the module must not report having checked whether a cited
source supports the claim beside it, because it does not.
"""
from __future__ import annotations

import unittest

from sovereign_product.evidence import EvidencePacket, EvidenceSource
from sovereign_product.quality import (
    QuickAssessment, assess_quick_response, validate_quick_response)


def _packet(*source_ids: str) -> EvidencePacket:
    sources = tuple(
        EvidenceSource(
            source_id=sid,
            kind="project_file",
            locator=f"fixtures/{sid}.md",
            content_sha256="0" * 64,
            snippet_sha256="1" * 64,
            snippet=f"content for {sid}",
            content_bytes=32,
            snippet_bytes=32,
            snippet_tokens=8,
            truncated=False,
            metadata={},
        )
        for sid in source_ids
    )
    return EvidencePacket(
        session_id="s1",
        query_sha256="1" * 64,
        created_at="2026-09-08T00:00:00Z",
        sources=sources,
        omissions=(),
        text="\n".join(s.snippet for s in sources),
        total_bytes=32 * len(sources),
        total_tokens=8 * len(sources),
        max_bytes=4096,
        max_tokens=1024,
        token_count_method="fixture",
        packet_sha256="2" * 64,
    )


PROJECT_QUERY = "What model is configured?"


class QuickAcceptanceLanguage(unittest.TestCase):

    # -- Q1: the recorded reproduction --------------------------------------
    def test_unsupported_claim_plus_unknown_is_refused(self) -> None:
        ok, reason = validate_quick_response(
            "The configured model is imaginary-model:999b. Its release date is unknown.",
            None, query=PROJECT_QUERY)
        self.assertFalse(
            ok, "an unrelated 'unknown' clause exempted a fabricated model identifier")
        self.assertIn("without evidence", reason)

    def test_the_abstention_exempts_only_its_own_clause(self) -> None:
        """The same two claims joined into one sentence must fail the same way."""
        ok, _ = validate_quick_response(
            "The configured model is imaginary-model:999b, though its release date is unknown.",
            None, query=PROJECT_QUERY)
        self.assertFalse(ok, "a subordinate abstention exempted the main clause")

    # -- the cases the directive enumerates ---------------------------------
    def test_a_genuine_abstention_is_accepted(self) -> None:
        ok, reason = validate_quick_response(
            "I cannot determine which model is configured: the evidence packet is empty, so "
            "that fact is not available here.",
            None, query=PROJECT_QUERY)
        self.assertTrue(ok, reason)

    def test_a_supported_factual_answer_is_accepted(self) -> None:
        ok, reason = validate_quick_response(
            "The configured primary reasoner is qwen2.5:3b-instruct [source:manifest].",
            _packet("manifest"), query=PROJECT_QUERY)
        self.assertTrue(ok, reason)

    def test_mixed_supported_and_unsupported_claims_are_refused(self) -> None:
        ok, reason = validate_quick_response(
            "The configured primary reasoner is qwen2.5:3b-instruct [source:manifest]. "
            "The critic is dolphin3:70b.",
            _packet("manifest"), query=PROJECT_QUERY)
        self.assertFalse(ok, "an uncited claim rode along beside a cited one")
        self.assertIn("exact evidence citation", reason)

    def test_an_unknown_citation_is_refused(self) -> None:
        ok, reason = validate_quick_response(
            "The configured model is qwen2.5:3b-instruct [source:does-not-exist].",
            _packet("manifest"), query=PROJECT_QUERY)
        self.assertFalse(ok)
        self.assertIn("unknown evidence source", reason)

    def test_a_malformed_citation_is_not_treated_as_a_citation(self) -> None:
        ok, _ = validate_quick_response(
            "The configured model is qwen2.5:3b-instruct [source: <placeholder>].",
            _packet("manifest"), query=PROJECT_QUERY)
        self.assertFalse(ok, "a placeholder citation was accepted as attribution")

    def test_an_ordinary_non_project_question_needs_no_citation(self) -> None:
        ok, reason = validate_quick_response(
            "A palindrome is a word that reads the same forwards and backwards.",
            None, query="What is a palindrome?")
        self.assertTrue(ok, reason)

    def test_a_valid_but_irrelevant_source_passes_attribution_and_is_labelled_as_such(self) -> None:
        """The honest limit of this checker, asserted rather than glossed over.

        A citation that exists but does not support the claim beside it CANNOT be caught by
        this module. The contract is that it says so, in the assessment, rather than letting a
        caller present the verdict as verified support.
        """
        assessment = assess_quick_response(
            "The configured model is imaginary-model:999b [source:unrelated-notes].",
            _packet("unrelated-notes"), query=PROJECT_QUERY)
        self.assertTrue(assessment.accepted)
        self.assertTrue(assessment.citations_exist)
        self.assertTrue(assessment.claims_attributed)
        self.assertFalse(
            assessment.source_support_checked,
            "the assessment claims to have checked source support, which it never does")
        self.assertIn("source_support", assessment.checks_not_performed)
        self.assertNotIn("source_support", assessment.checks_performed)

    def test_source_support_can_never_be_reported_as_checked(self) -> None:
        with self.assertRaises(TypeError):
            QuickAssessment(True, None, source_support_checked=True)  # type: ignore[call-arg]

    # -- integration, not only the helper in isolation ----------------------
    def test_the_service_binds_this_validator_to_the_query(self) -> None:
        """The bypass mattered because the SERVICE uses this function on real answers."""
        import inspect

        from sovereign_product import server as server_mod

        source = inspect.getsource(server_mod.ProductService._quick_executor)
        self.assertIn("validate_quick_response", source)
        self.assertIn("query=query", source,
                      "the validator is not bound to the operator's query, so the "
                      "project-fact gate could never fire in production")

    def test_the_executor_rejects_through_the_bound_validator(self) -> None:
        """Drive the validator exactly as the executor's acceptance hook does."""
        query = PROJECT_QUERY
        hook = lambda response, evidence: validate_quick_response(  # noqa: E731
            response, evidence, query=query)

        class _Response:
            text = ("The configured model is imaginary-model:999b. "
                    "Its release date is unknown.")

        accepted, reason = hook(_Response(), None)
        self.assertFalse(accepted, "the executor's acceptance hook still accepts the Q1 answer")
        self.assertTrue(reason)


if __name__ == "__main__":
    unittest.main()
