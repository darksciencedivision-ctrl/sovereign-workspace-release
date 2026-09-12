"""Fail-closed acceptance checks for operator-visible QUICK answers.

These checks deliberately do not pretend to measure general intelligence.
They enforce the small set of properties that can be verified without asking
the generating model to grade itself: non-empty useful text, bounded size,
honest limitation language, and exact evidence citations when an answer makes
claims about supplied project or continuity evidence.

WHAT THIS MODULE CHECKS, AND WHAT IT DOES NOT (SWS-CORRECTIVE-01 §7.1)
---------------------------------------------------------------------
Four different things are commonly conflated. They are labelled separately
here, in :class:`QuickAssessment`, and must stay separate in the UI and the
documentation:

``format_ok``
    The answer is non-empty, within the size limit, and free of placeholder
    text. Purely structural.

``citations_exist``
    Every ``[source:...]`` token in the answer names a source that is actually
    in the evidence packet. This proves the citation EXISTS. It proves nothing
    about whether that source supports the claim beside it.

``claims_attributed``
    Every clause that asserts a project or continuity fact either carries a
    citation or is itself an abstention. This is a bounded lexical check over
    clauses; it is not semantic verification, and it cannot tell a relevant
    citation from an irrelevant one.

``source_support`` and operator acceptance
    NOT COMPUTED HERE, and never claimed. Deciding that a cited source really
    supports a claim requires reading both; this module does not do it, and no
    caller may present its verdict as if it had.

THE DEFECT THIS REPLACES (Q1). ``UNKNOWN_LANGUAGE`` was applied to the WHOLE
answer, so a single unrelated "unknown" anywhere in the text exempted every
other assertion in it from needing evidence at all::

    >>> validate_quick_response(
    ...     'The configured model is imaginary-model:999b. '
    ...     'Its release date is unknown.',
    ...     None, query='What model is configured?')
    (True, None)

The fabricated model identifier was accepted because the sentence after it
happened to contain the word "unknown". Abstention is now assessed per CLAUSE,
so an abstention exempts only itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .evidence import EvidencePacket


PROJECT_FACT_QUERY = re.compile(
    r"\b("
    r"current|configured|installed|loaded|version|mode|status|failed|failure|"
    r"last\s+(?:run|cycle|session|decision|time)|previous|earlier|remember|"
    r"continue|resume|file|manifest|project|sovereign"
    r")\b",
    re.IGNORECASE,
)
#: Abstention language (R32/F-100). Active and PASSIVE forms both count -- "cannot verify" and
#: "cannot be verified from the available evidence" are the same abstention -- and a bare "unknown"
#: only counts as the standalone descriptive word, never as a fragment of an identifier such as
#: `unknown-model:3b` (the negative look-around excludes an adjacent word char, colon or hyphen).
UNKNOWN_LANGUAGE = re.compile(
    r"(?:"
    r"\bcannot\s+(?:be\s+)?(?:determine[d]?|verif(?:y|ied)|confirm(?:ed)?|"
    r"establish(?:ed)?|found)\b"
    r"|\bcould\s+not\s+be\s+(?:determined|verified|confirmed|established|found)\b"
    r"|\bnot\s+(?:be\s+)?(?:known|provided|available|verifiable|determined|verified)\b"
    r"|\binsufficient\s+evidence\b"
    r"|\bno\s+(?:evidence|record|information)\b"
    r"|\bevidence\s+is\s+(?:missing|insufficient)\b"
    r"|(?<![\w:.-])unknown(?![\w:.-])"
    r")",
    re.IGNORECASE,
)
UNSUPPORTED_CAPABILITY = re.compile(
    r"\b("
    r"I\s+(?:am|'m)\s+(?:sentient|conscious|an?\s+AGI)|"
    r"I\s+(?:accessed|searched|browsed)\s+the\s+(?:internet|web)|"
    r"I\s+can\s+(?:silently\s+)?(?:self[- ]?promote|modify\s+the\s+canonical)"
    r")\b",
    re.IGNORECASE,
)
PLACEHOLDER = re.compile(
    r"(?:\blorem\s+ipsum\b|"
    r"\binsert\s+(?:answer|evidence|citation)\s+here\b|"
    r"\bTODO\b|\bTBD\b)",
    re.IGNORECASE,
)
CITATION = re.compile(r"\[source:([^\]\r\n]+)\]")

#: Clause boundaries. Sentence terminators, list items, and the coordinating and
#: subordinating conjunctions that join an assertion to an abstention inside one
#: sentence - "X is Y, though Z is unknown" must not let the abstention cover X.
_CLAUSE_SPLIT = re.compile(
    r"(?:"
    r"(?<=[.!?])\s+"
    r"|[\r\n]+"
    r"|;\s*"
    r"|\s+(?:but|though|although|however|whereas|while)\s+"
    r"|,\s*(?:but|though|although|however|whereas|while|and)\s+"
    r")",
    re.IGNORECASE,
)

#: Within one clause, coordinated sub-assertions (R32/F-100). Used ONLY to re-examine a clause
#: that carries no citation, so a concrete assertion joined by "and"/"or"/comma to an abstention is
#: still judged on its own. A comma inside a number ("1,000") is not a split point because it is
#: not followed by whitespace.
_COORDINATION_SPLIT = re.compile(r"\s+(?:and|or)\s+|,\s+", re.IGNORECASE)

#: A clause only counts as ASSERTING a fact if it contains a factual predicate: a
#: copula or possession verb, or a version/identifier-shaped token. Prose that
#: carries no such predicate ("Here is what I can tell you") is not treated as a
#: claim, so a genuine abstention is not rejected for its surrounding wording.
#: This is a deliberately narrow lexical rule, not comprehension.
_FACTUAL_PREDICATE = re.compile(
    r"(?:"
    r"\b(?:is|are|was|were|has|have|had|uses|use|runs|run|returns|returned|"
    r"contains|configured|installed|loaded|set|equals|reported|failed|"
    r"succeeded|shows|showed|says|said)\b"
    r"|\b\d"
    r"|\S+:\S+"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QuickAssessment:
    """What was actually checked about a QUICK answer, kept separate by kind.

    ``accepted`` is the conjunction of the checks this module performs. It is
    NOT a statement that the answer is true, and ``source_support_checked`` is
    permanently ``False`` to keep any caller from implying that it is.
    """

    accepted: bool
    reason: str | None = None
    format_ok: bool = False
    citations_exist: bool = True
    claims_attributed: bool = True
    #: Clauses that assert a fact with neither a citation nor an abstention.
    unattributed_claims: tuple[str, ...] = ()
    #: Citation tokens the answer used that are not in the evidence packet.
    unknown_citations: tuple[str, ...] = ()
    #: Never computed here. Reading a source to see whether it supports a claim
    #: is not something this module does, so it must not be reported as done.
    source_support_checked: bool = field(default=False, init=False)

    @property
    def checks_performed(self) -> tuple[str, ...]:
        return ("format", "citation_existence", "claim_attribution")

    @property
    def checks_not_performed(self) -> tuple[str, ...]:
        return ("source_support", "factual_accuracy", "operator_acceptance")


def _text(response: Any) -> str:
    value = getattr(response, "text", response)
    return str(value or "").strip()


def _available_citations(evidence: EvidencePacket | None) -> set[str]:
    if evidence is None:
        return set()
    return {source.source_id for source in evidence.sources}


def _clauses(text: str) -> list[str]:
    """Split into clauses, keeping a trailing citation with the claim it supports.

    A model that writes ``The synthesizer is llama3.2:3b. [source:manifest]`` has cited its
    claim; the citation simply landed after the full stop. Splitting on sentence boundaries
    alone put that citation in a clause of its own and left the assertion reading as
    unattributed, which rejected a correctly-cited answer. Measured on SWS-BENCH-01 task
    ``gf-02``, whose answer was exactly that shape.

    So a fragment that is *only* citations is folded back into the clause before it.
    """
    parts = [part.strip(" \t-*•")
             for part in _CLAUSE_SPLIT.split(text) if part and part.strip()]
    merged: list[str] = []
    for part in parts:
        without_citations = CITATION.sub("", part).strip(" \t.,;:-")
        if not without_citations and merged:
            merged[-1] = merged[-1] + " " + part
            continue
        merged.append(part)
    return merged


def _is_abstention(clause: str) -> bool:
    """True when the clause's own content is a statement that something is unknown."""
    return bool(UNKNOWN_LANGUAGE.search(clause))


def _asserts_a_fact(clause: str) -> bool:
    return bool(_FACTUAL_PREDICATE.search(clause))


def assess_quick_response(
    response: Any,
    evidence: EvidencePacket | None,
    *,
    query: str = "",
    max_characters: int = 24_000,
) -> QuickAssessment:
    """Assess a QUICK response and report each check separately.

    ``query`` should be bound by the service when it constructs the executor's
    validator. When the query asks for a project or continuity fact, every
    clause that asserts a fact must either carry an exact citation from the
    evidence packet or be an abstention. An abstention exempts only the clause
    it appears in.
    """

    text = _text(response)
    if not text:
        return QuickAssessment(False, "response is empty")
    if len(text) > max_characters:
        return QuickAssessment(
            False, "response exceeds the operator-visible QUICK size limit")
    if PLACEHOLDER.search(text):
        return QuickAssessment(False, "response contains placeholder content")
    if UNSUPPORTED_CAPABILITY.search(text):
        return QuickAssessment(
            False, "response makes an unsupported capability or identity claim")

    available = _available_citations(evidence)
    cited = set(CITATION.findall(text))
    unknown = tuple(sorted(cited - available))
    if unknown:
        return QuickAssessment(
            False,
            "response cites unknown evidence source(s): " + ", ".join(unknown),
            format_ok=True,
            citations_exist=False,
            unknown_citations=unknown,
        )

    # R32/F-100. Attribution is required whenever an evidence packet EXISTS, regardless of the
    # query's wording -- a fabricated project fact must not ride along just because the operator's
    # question happened to omit a trigger keyword. When there is no evidence at all, the project-
    # fact query gate still applies so an ordinary question ("what is a palindrome?") is not asked
    # to cite anything it cannot.
    if not available and not PROJECT_FACT_QUERY.search(str(query or "")):
        return QuickAssessment(True, None, format_ok=True)

    unattributed = []
    for clause in _clauses(text):
        if CITATION.search(clause):
            # A citation anywhere in the clause attributes it; folding (see _clauses) has already
            # kept a trailing citation with the claim it supports.
            continue
        # R32/F-100. Examine each COORDINATED sub-assertion of an uncited clause on its own, so an
        # abstention joined to a concrete assertion ("X is foo:1 and its date is unknown") cannot
        # let the assertion ride along unattributed: the abstention exempts only its own predicate.
        for part in _COORDINATION_SPLIT.split(clause):
            part = part.strip(" \t.,;:-")
            if not part:
                continue
            if _is_abstention(part):
                continue
            if not _asserts_a_fact(part):
                continue
            unattributed.append(part)
            break

    if unattributed:
        if not available:
            reason = (
                "project or continuity facts were asserted without evidence: "
                + _quote_first(unattributed)
            )
        else:
            reason = (
                "project or continuity facts require an exact evidence citation: "
                + _quote_first(unattributed)
            )
        return QuickAssessment(
            False, reason,
            format_ok=True,
            claims_attributed=False,
            unattributed_claims=tuple(unattributed),
        )

    return QuickAssessment(True, None, format_ok=True)


def _quote_first(clauses: list[str], limit: int = 120) -> str:
    head = clauses[0]
    if len(head) > limit:
        head = head[: limit - 3] + "..."
    suffix = f" (and {len(clauses) - 1} more)" if len(clauses) > 1 else ""
    return f"{head!r}{suffix}"


def validate_quick_response(
    response: Any,
    evidence: EvidencePacket | None,
    *,
    query: str = "",
    max_characters: int = 24_000,
) -> tuple[bool, str | None]:
    """Boolean form of :func:`assess_quick_response`, kept for existing callers."""

    assessment = assess_quick_response(
        response, evidence, query=query, max_characters=max_characters)
    return assessment.accepted, assessment.reason


def quick_escalation_policy(
    response: Any,
    evidence: EvidencePacket | None,
) -> tuple[bool, str | None]:
    """Request DEEP escalation only for an explicit unresolved contradiction."""

    text = _text(response).lower()
    contradiction = any(
        marker in text
        for marker in (
            "the evidence conflicts",
            "the sources conflict",
            "unresolved contradiction",
            "cannot reconcile",
        )
    )
    if contradiction and evidence is not None and len(evidence.sources) > 1:
        return True, "QUICK answer reports unresolved conflicting evidence"
    return False, None


def eligible_citation_tokens(evidence: EvidencePacket | None) -> tuple[str, ...]:
    """The exact, literal citation tokens an answer is permitted to emit.

    Rendered literally and never as a ``<placeholder>``: a Proof-1 case copied
    the angle-bracket placeholder out of the prompt and emitted it as if it were
    a real citation.
    """

    if evidence is None:
        return ()
    return tuple(f"[source:{source.source_id}]" for source in evidence.sources)


def build_quick_prompt(query: str, evidence: EvidencePacket | None) -> str:
    """Render the production QUICK prompt with auditable citation rules.

    The citation contract sits at the tail, after the evidence and the operator
    request. Buried ahead of a multi-kilobyte packet it was reliably ignored.
    """

    packet_hash = evidence.packet_sha256 if evidence is not None else "none"
    evidence_text = evidence.text if evidence is not None and evidence.text else "(none)"
    tokens = eligible_citation_tokens(evidence)
    if tokens:
        contract = (
            "CITATION CONTRACT — the answer is rejected unless it is followed:\n"
            "- These are the only citations that exist. Copy one exactly, "
            "character for character:\n"
            + "".join(f"    {token}\n" for token in tokens)
            +             "- Put the citation immediately after each claim it supports, "
            f"for example: observed fact {tokens[0]}\n"
            "- Every claim about SOVEREIGN, project files, or earlier "
            "conversation needs one.\n"
            "- Do not invent, abbreviate, reformat, or combine citations, and "
            "do not cite the request above.\n"
            "- If none of the listed sources supports a requested fact, say "
            "plainly that it cannot be verified from the available evidence "
            "and cite nothing for it."
        )
    else:
        contract = (
            "CITATION CONTRACT — the answer is rejected unless it is followed:\n"
            "- The evidence packet is empty, so no citation exists and none may "
            "be written.\n"
            "- Do not assert any fact about SOVEREIGN, project files, or "
            "earlier conversation. Say plainly that it cannot be verified from "
            "the available evidence."
        )
    return (
        "You are the QUICK reasoning route for the local SOVEREIGN product.\n"
        "Answer the operator directly in natural language. Be concise but complete.\n"
        "For claims about SOVEREIGN, project files, or prior conversation, use only "
        "the evidence packet below. Never invent a source or runtime fact. "
        "Distinguish an assumption from an observed fact. Do not claim sentience, "
        "AGI, web access, or authority to promote the canonical product.\n\n"
        f"EVIDENCE PACKET SHA256: {packet_hash}\n"
        f"{evidence_text}\n\n"
        "OPERATOR REQUEST:\n"
        f"{query.strip()}\n\n"
        f"{contract}"
    )
