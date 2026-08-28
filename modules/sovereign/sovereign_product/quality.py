"""Fail-closed acceptance checks for operator-visible QUICK answers.

These checks deliberately do not pretend to measure general intelligence.
They enforce the small set of properties that can be verified without asking
the generating model to grade itself: non-empty useful text, bounded size,
honest limitation language, and exact evidence citations when an answer makes
claims about supplied project or continuity evidence.
"""

from __future__ import annotations

import re
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
UNKNOWN_LANGUAGE = re.compile(
    r"\b("
    r"cannot\s+(?:determine|verify|confirm)|not\s+(?:known|provided|available)|"
    r"insufficient\s+evidence|evidence\s+is\s+(?:missing|insufficient)|unknown"
    r")\b",
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


def _text(response: Any) -> str:
    value = getattr(response, "text", response)
    return str(value or "").strip()


def _available_citations(evidence: EvidencePacket | None) -> set[str]:
    if evidence is None:
        return set()
    return {source.source_id for source in evidence.sources}


def validate_quick_response(
    response: Any,
    evidence: EvidencePacket | None,
    *,
    query: str = "",
    max_characters: int = 24_000,
) -> tuple[bool, str | None]:
    """Return whether a QUICK response is safe to present as accepted.

    ``query`` should be bound by the service when it constructs the executor's
    validator.  A project/continuity claim must cite at least one exact source
    ID from the packet, unless the answer explicitly says the fact is unknown.
    Unknown citations are always rejected.
    """

    text = _text(response)
    if not text:
        return False, "response is empty"
    if len(text) > max_characters:
        return False, "response exceeds the operator-visible QUICK size limit"
    if PLACEHOLDER.search(text):
        return False, "response contains placeholder content"
    if UNSUPPORTED_CAPABILITY.search(text):
        return False, "response makes an unsupported capability or identity claim"

    available = _available_citations(evidence)
    cited = set(CITATION.findall(text))
    unknown = cited - available
    if unknown:
        return False, f"response cites unknown evidence source(s): {', '.join(sorted(unknown))}"

    asks_project_fact = bool(PROJECT_FACT_QUERY.search(str(query or "")))
    if asks_project_fact and not UNKNOWN_LANGUAGE.search(text):
        if not available:
            return False, "project or continuity facts were asserted without evidence"
        if not cited:
            return False, "project or continuity facts require an exact evidence citation"
    return True, None


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
            + "- Put the citation immediately after each claim it supports.\n"
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
