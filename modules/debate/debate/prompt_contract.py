"""Turn-quality contract: guidance injected into the system prompt.

This guides discourse quality through instructions only. It deliberately
produces no machine-readable structure, and nothing here (or in its
caller) parses structure out of a seat's speech -- Phase 0's
structured-output prohibition was measured only on reasoning-class
models, and phi4:14b / qwen2.5:14b-instruct were explicitly excluded
from that matrix. It is a conservative operating assumption, not a
measured fact about the seated models, and v1.1 respects it regardless
(Appendix B item 12 of the v1.1 directive).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from debate.sentence_buffer import first_sentence

TARGET_WORDS_MIN = 110
TARGET_WORDS_MAX = 160

# The v1.1 list banned five literal strings. Live observation showed the
# models simply moved to variants outside it -- 31 of 59 turns (53%) still
# opened with an agreement acknowledgement. These are the observed evasions.
STOCK_OPENINGS = (
    "your point is well taken",
    "i completely agree",
    "that's an excellent point",
    "that's a great point",
    "i couldn't agree more",
)

# Matched after an optional "<SeatName>, " address. Detection is diagnostic
# only -- speech is never rejected or rewritten on this basis.
AGREEMENT_OPENERS = (
    "you're right", "you are right", "you're correct", "you are correct",
    "you rightly", "you raise an important", "you raise a good",
    "you make an essential", "you make an excellent", "you make a good",
    "you've made a strong", "you have made a strong", "you've highlighted",
    "you have highlighted", "you've articulated", "you've raised",
    "your concerns are valid", "your point about", "your suggestion",
    "your approach", "i agree", "i see your point", "i appreciate",
    "that's a fair", "that is a fair", "well said",
)


def contract_instructions(min_words: int = TARGET_WORDS_MIN,
                          max_words: int = TARGET_WORDS_MAX) -> str:
    return (
        f"Turn shape: {min_words}-{max_words} words. This is a hard limit, "
        f"not a suggestion; do not exceed {max_words} words. "
        "Do not open by agreeing with, praising, validating, or restating "
        "the other panelist's point -- open with your own claim or your "
        "direct answer. "
        "State your position within two sentences. If you were asked a "
        "direct question, answer it before advancing. Address one "
        "identifiable claim from another panelist. Give at least one "
        "mechanism, example, or counterexample. Introduce no more than one "
        "major new argument. Avoid repeating your own prior argument. End "
        "on a complete sentence. Do not open with generic praise or stock "
        'phrases such as "Your point is well taken", "I completely agree", '
        'or "That\'s an excellent point" unless semantically necessary. '
        "Distinguish fact, engineering hypothesis, interpretation, "
        "philosophical position, and speculation through your word choice "
        "and certainty, not through literal labels -- claims about "
        "consciousness, sentience, rights, or future capability should not "
        "carry the same certainty as claims about current architecture. "
        "OPENING REQUIREMENT: Sentence 1 must directly state your own "
        "position on the current debate question. Do not address, name, "
        "summarize, praise, validate, concede to, or characterize another "
        "seat in sentence 1. Engagement with another seat begins in "
        "sentence 2."
    )


def opens_with_stock_phrase(text: str) -> str | None:
    """Bounded, deterministic check -- no model call. Diagnostic use only;
    never used to reject or rewrite a seat's speech."""
    lowered = text.strip().lower()
    for phrase in STOCK_OPENINGS:
        if lowered.startswith(phrase):
            return phrase
    return None


def opens_with_agreement(text: str) -> str | None:
    """Diagnostic: did this turn open by acknowledging the other seat?

    Bounded and deterministic, no model call. Reported to the operator drawer
    and recorded in turn metrics; never used to reject or rewrite speech.
    """
    lowered = text.strip().lower()
    if "," in lowered[:24]:
        lowered = lowered.split(",", 1)[1].strip()
    for phrase in AGREEMENT_OPENERS:
        if lowered.startswith(phrase):
            return phrase
    return None


def word_count_status(text: str, min_words: int = TARGET_WORDS_MIN,
                      max_words: int = TARGET_WORDS_MAX) -> tuple[int, str]:
    """(word_count, "under" | "within" | "over") -- makes the contract
    measurable instead of aspirational. v1.1 targeted 110-160 and shipped a
    measured mean of 188 with a max of 305, unrecorded."""
    count = len(text.split())
    if count < min_words:
        return count, "under"
    if count > max_words:
        return count, "over"
    return count, "within"


# ---------------------------------------------------------------------------
# Opening-move constraint (v1.1 closeout)
#
# Three blocklist attempts failed against unlimited paraphrase, most
# decisively against a literally-banned phrase with words inserted
# mid-string ("your point ON CO-OPTING DECISION-MAKING PLATFORMS is well
# taken"), which defeated startswith matching. This constrains what
# sentence 1 may CONTAIN instead of which phrases it may use.
#
# This verifies only the machine-checkable half of the opening-move rule:
# that sentence 1 contains no opponent name, second-person reference, or
# opponent-directed acknowledgment/validation construction. It does NOT
# verify sentence 1 actually states the seat's own position -- that half
# is not machine-checkable. A passing check is not evidence the
# behavioural goal was met.
# ---------------------------------------------------------------------------

_CURLY_APOSTROPHES = {"’": "'", "‘": "'"}


def _normalize_apostrophes(text: str) -> str:
    for curly, straight in _CURLY_APOSTROPHES.items():
        text = text.replace(curly, straight)
    return text


_SECOND_PERSON = re.compile(
    r"\b(you're|you've|yourselves|yourself|yours|your|you)\b", re.IGNORECASE
)

# Relational verbs that are inherently other-directed when a turn opens
# with them in first person -- "I agree/acknowledge/appreciate/concede"
# has nothing else to refer to in a two-seat debate but the opponent's
# just-stated point. Unconditional: no name or "you" required.
_FIRST_PERSON_ACK_VERBS = re.compile(
    r"\b(agrees?|appreciates?|acknowledges?|concedes?)\b", re.IGNORECASE
)

# Validation adjectives / attribution verbs. Conservative by design: these
# fire ONLY via the opponent-name, second-person, or discourse-reference
# checks above/below -- never standalone. "The evidence is compelling" is
# a legitimate opening that happens to contain a listed word (Appendix B
# item 12); this list exists for documentation and the discourse-reference
# pattern below, not as an independent unconditional trigger.
ACK_ADJECTIVES = (
    "right", "correct", "valid", "fair", "compelling", "insightful",
    "well taken", "good point", "raise", "highlight", "pinpoint", "outline",
)

# "That concern is valid" / "the objection is fair" -- validates a
# preceding opponent argument by discourse reference, without naming them
# or using "you". Adjacent noun+copula+adjective only, deliberately
# narrow: "the argument for restraint is compelling" (own position, with
# an intervening phrase) must not match.
_DISCOURSE_REFERENCE = re.compile(
    r"\b(that|this|the)\s+(concern|objection|point|argument|claim|worry|issue)"
    r"\s+(is|was)\s+(valid|fair|well[- ]taken|compelling|insightful|legitimate|right|correct)\b",
    re.IGNORECASE,
)


def _opponent_name_pattern(name: str) -> re.Pattern:
    return re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)


def opening_move_violation(text: str, opponent_names: Iterable[str]) -> str | None:
    """Diagnostic-only structural check on sentence 1 of a turn.

    Deterministic, no model call. Never used to reject, regenerate,
    rewrite, or clip a seat's speech -- diagnostic only.

    Returns a stable short reason string, or None.
    """
    sentence = _normalize_apostrophes(first_sentence(text))
    if not sentence:
        return None

    for name in opponent_names:
        if not name:
            continue
        if _opponent_name_pattern(name).search(sentence):
            return f"opponent_name:{name}"

    second_person = _SECOND_PERSON.search(sentence)
    if second_person:
        return f"second_person:{second_person.group(0).lower()}"

    ack_verb = _FIRST_PERSON_ACK_VERBS.search(sentence)
    if ack_verb:
        return f"acknowledgment_construction:{ack_verb.group(0).lower()}"

    if _DISCOURSE_REFERENCE.search(sentence):
        return "discourse_reference_validation"

    return None
