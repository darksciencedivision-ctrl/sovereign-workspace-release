"""Deterministic semantic invariants for high-risk mechanism claims.

These checks are intentionally narrow.  They do not grade style or substitute
for model review; they prevent a verifier from accepting well-known category
errors when an operator explicitly asks about transactional crash safety and a
tamper-evident audit history.
"""

from __future__ import annotations

import re


def _has(value: str, pattern: str) -> bool:
    return re.search(pattern, value, re.IGNORECASE | re.DOTALL) is not None


def _has_unnegated_trusted_anchor(value: str) -> bool:
    pattern = re.compile(
        r"\btrusted\b[^.!?\n]{0,48}\b"
        r"(?:anchor|checkpoint|head|root|digest|reference)\b|"
        r"\b(?:anchor|checkpoint|head|root|digest|reference)\b"
        r"[^.!?\n]{0,48}\btrusted\b|"
        r"\bexternal(?:ly)?\b[^.!?\n]{0,48}\b"
        r"(?:anchor|checkpoint|head|root|digest|reference)\b",
        re.IGNORECASE,
    )
    for match in pattern.finditer(value):
        sentence_start = max(
            value.rfind(boundary, 0, match.start())
            for boundary in (".", "!", "?")
        )
        sentence_end_candidates = [
            position
            for boundary in (".", "!", "?")
            if (position := value.find(boundary, match.end())) >= 0
        ]
        sentence_end = (
            min(sentence_end_candidates)
            if sentence_end_candidates
            else len(value)
        )
        sentence = value[sentence_start + 1 : sentence_end]
        relative_start = match.start() - sentence_start - 1
        relative_end = match.end() - sentence_start - 1
        prefix = sentence[:relative_start]
        suffix = sentence[relative_end:]
        if re.search(
            r"\b(?:without|lacks?|missing|no|not|doesn't|does\s+not)\b"
            r"[^.!?]{0,56}$",
            prefix,
            re.IGNORECASE,
        ):
            continue
        if re.search(
            r"^[^.!?]{0,160}\b(?:is|are|remains?|was|were)\s+"
            r"(?:not\s+(?:required|needed|trusted|available)|unnecessary|"
            r"optional|absent|untrusted|anything\s+but\s+"
            r"(?:required|needed|necessary|essential))\b",
            suffix,
            re.IGNORECASE | re.DOTALL,
        ):
            continue
        if re.search(
            r"\b(?:can|may|could)\s+(?:safely\s+)?"
            r"(?:dispense|do\s+away)\s+with\b|"
            r"\b(?:can|may|could)\s+(?:safely\s+)?(?:forgo|forego)\b|"
            r"\b(?:is|are|can\s+be|may\s+be|could\s+be)\s+"
            r"(?:dispensed\s+with|forgone|foregone|omitted)\b",
            sentence,
            re.IGNORECASE,
        ):
            continue
        return True
    return False


def _has_unnegated_immutability(value: str) -> bool:
    for match in re.finditer(
        r"\bimmutab(?:le|ility)\b",
        value,
        re.IGNORECASE,
    ):
        clause_start = max(
            value.rfind(boundary, 0, match.start())
            for boundary in (".", "!", "?", ";", ":", "\n")
        )
        prefix = value[clause_start + 1 : match.start()]
        suffix = value[match.end() : match.end() + 48]
        prefix = re.sub(
            r"\bnot\s+(?:merely|only|just|simply)\b",
            "",
            prefix,
            flags=re.IGNORECASE,
        )
        if re.search(
            r"^\s+(?:is|remains?|was)?\s*not\s+"
            r"(?:merely|only|just|simply)\b",
            suffix,
            re.IGNORECASE,
        ):
            return True
        if re.search(
            r"\b(?:not|never|cannot|can't|does\s+not|isn't|is\s+not)\b"
            r"[^.!?\n]{0,40}$",
            prefix,
            re.IGNORECASE,
        ):
            continue
        if re.search(
            r"^\s+(?:is|remains?|was)?\s*"
            r"(?:not|unproven|unsupported|not\s+(?:guaranteed|established))\b",
            suffix,
            re.IGNORECASE,
        ):
            continue
        return True
    return False


def mechanism_analysis_issues(topic: str, answer: str) -> list[str]:
    """Return exact, actionable defects for supported high-risk mechanisms."""

    request = str(topic or "")
    candidate = str(answer or "")
    issues: list[str] = []
    asks_transaction_crash = _has(
        request,
        r"\btransaction(?:al)?\b.*\bcrash\b|\bcrash\b.*\btransaction(?:al)?\b",
    )
    asks_tamper_lineage = _has(
        request,
        r"\btamper[- ]evident\b.*\b(?:audit|lineage|history)\b|"
        r"\b(?:audit|lineage|history)\b.*\btamper[- ]evident\b",
    )

    if asks_transaction_crash:
        if not _has(
            candidate,
            r"\bcommit(?:ted)?\b.*\b(?:durab|persist|recover|rollback)\w*\b|"
            r"\bcommit(?:ted)?\b.*\broll(?:ed)?\s*back\b|"
            r"\b(?:durab|persist|recover|rollback)\w*\b.*\bcommit(?:ted)?\b|"
            r"\broll(?:ed)?\s*back\b.*\bcommit(?:ted)?\b",
        ):
            issues.append(
                "crash-safety analysis must state the committed-state boundary "
                "and the durability/recovery assumptions; loss of uncommitted "
                "work alone is not a crash-consistency failure"
            )
        if _has(
            candidate,
            r"\bcrash safety\b[^.!?\n]{0,64}\buncommitted\b"
            r"[^.!?\n]{0,48}\b(?:not guaranteed|data loss|lost)\b",
        ) and not _has(
            candidate,
            r"\buncommitted\b[^.!?\n]{0,48}\b"
            r"(?:expected|not a (?:crash|consistency) failure)\b",
        ):
            issues.append(
                "loss or rollback of uncommitted work is expected and must not "
                "be presented as failure of committed-state crash safety"
            )

    if asks_tamper_lineage:
        if _has_unnegated_immutability(candidate):
            issues.append(
                "tamper evidence must not be described as an immutable history"
            )
        if not _has(
            candidate,
            r"\bdetect\w*\b[^.!?\n]{0,96}\b(?:not|doesn't|does not|cannot)\b"
            r"[^.!?\n]{0,48}\bprevent\w*\b|"
            r"\b(?:not|doesn't|does not|cannot)\b[^.!?\n]{0,48}\bprevent\w*\b"
            r"[^.!?\n]{0,96}\bdetect\w*\b",
        ):
            issues.append(
                "tamper-evidence analysis must distinguish detection from "
                "prevention"
            )
        has_trusted_anchor = _has_unnegated_trusted_anchor(candidate)
        if not has_trusted_anchor:
            issues.append(
                "audit-lineage analysis must state the separately trusted "
                "anchor/checkpoint assumption"
            )
        if _has(
            candidate,
            r"\bdetect\w*\b[^.!?\n]{0,64}\bomission\b|"
            r"\bomission\b[^.!?\n]{0,64}\bdetect\w*\b",
        ) and not has_trusted_anchor:
            issues.append(
                "a local hash chain cannot claim omission detection without "
                "a separately trusted completeness reference"
            )
        if not _has(candidate, r"\b(?:truncat\w*|roll(?:ed)?\s*back|rollback)\b"):
            issues.append(
                "audit-lineage limits must cover history truncation or rollback"
            )
        if not _has(candidate, r"\b(?:omission|omitted|completeness|complete history)\b"):
            issues.append(
                "audit-lineage limits must distinguish edit detection from "
                "history completeness/omission detection"
            )

    if asks_transaction_crash and asks_tamper_lineage:
        if not _has(
            candidate,
            r"\b(?:same|single|shared)\b[^.!?\n]{0,48}\b"
            r"(?:atomic|transaction|commit)\b[^.!?\n]{0,48}\b"
            r"(?:boundary|store|event|chain|record)\b|"
            r"\b(?:atomic|transactional)\b[^.!?\n]{0,48}\b"
            r"(?:coupl\w*|outbox|two[- ]phase|store and (?:the )?chain)\b",
        ):
            issues.append(
                "combined guarantee must address the atomic commit boundary "
                "between store state and event-chain append"
            )
    return issues
