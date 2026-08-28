"""Turn completion classification and bounded continuation policy.

`app.py` previously had no notion of a truncated turn: budget-cut output
was displayed as if it were the model's finished thought. This module
classifies every generation attempt into exactly one state and records
which signal fired, so a heuristic guess is never presented as certainty.
"""

from __future__ import annotations

import re

from enum import Enum


class TurnOutcome(str, Enum):
    """Explicit lifecycle of one attempted public turn (P0-15).

    Only COMPLETED represents a finished public debate turn; every other
    value must not advance completed-turn counters or anchor cadence.
    """

    COMPLETED = "completed"
    SKIPPED_GENERATION_ERROR = "skipped_generation_error"
    SKIPPED_EMPTY_PUBLIC = "skipped_empty_public"
    INTERRUPTED = "interrupted"
    PROTOCOL_INCOMPLETE = "protocol_incomplete"
    PROTOCOL_ERROR = "protocol_error"


TURN_COMPLETE = "TURN_COMPLETE"
TURN_TRUNCATED_BY_BUDGET = "TURN_TRUNCATED_BY_BUDGET"
TURN_INTERRUPTED = "TURN_INTERRUPTED"
TURN_EMPTY_AFTER_REASONING = "TURN_EMPTY_AFTER_REASONING"
TURN_FAILED = "TURN_FAILED"

MAX_CONTINUATION_WORDS = 35

_TERMINAL_PUNCTUATION = ('.', '!', '?', '"', "'", ')', ']', '”', '’')
_TRAILING_CONJUNCTIONS = {
    "and", "but", "or", "nor", "so", "yet", "because", "although", "since",
    "while", "if", "when", "as", "though", "unless", "until", "than",
}
_TRAILING_DETERMINERS = {
    "a", "an", "the", "this", "that", "these", "those", "its", "their",
    "his", "her",
}


def _ends_mid_word(stripped: str) -> bool:
    return bool(stripped) and stripped[-1].isalpha()


def _unclosed_quote(stripped: str) -> bool:
    straight_odd = stripped.count('"') % 2 == 1
    curly_mismatch = stripped.count("“") != stripped.count("”")
    return straight_odd or curly_mismatch


def _trailing_function_word(stripped: str) -> str | None:
    words = re.findall(r"[A-Za-z']+", stripped.lower())
    if not words:
        return None
    last = words[-1]
    if last in _TRAILING_CONJUNCTIONS or last in _TRAILING_DETERMINERS:
        return last
    return None


def heuristic_signals(text: str) -> list[str]:
    """Bounded textual signals suggesting the text stopped mid-thought.

    These are heuristics, not proof -- callers must not present them as
    certainty (§0.3 of the v1.1 directive).
    """
    signals: list[str] = []
    stripped = text.rstrip()
    if not stripped:
        return signals
    if stripped[-1] not in _TERMINAL_PUNCTUATION:
        signals.append("missing_terminal_punctuation")
    if _ends_mid_word(stripped):
        signals.append("ends_mid_word")
    if _unclosed_quote(stripped):
        signals.append("unclosed_quote")
    trailing = _trailing_function_word(stripped)
    if trailing:
        signals.append(f"trailing_function_word:{trailing}")
    return signals


def classify(
    *,
    text: str,
    budget_exhausted: bool,
    hidden_reasoning_present: bool,
    interrupted: bool = False,
    generation_failed: bool = False,
) -> tuple[str, list[str], bool]:
    """Classify one generation attempt.

    Returns (state, signals, confident). `signals` names the evidence that
    drove the classification. `confident` is True when the classification
    is reliable enough to act on (issue a continuation); it is backed
    either by Ollama's own `done_reason == "length"` metadata or by
    multiple independent heuristic signals agreeing.
    """
    if interrupted:
        return TURN_INTERRUPTED, ["operator_interruption_or_shutdown"], True
    if generation_failed:
        return TURN_FAILED, ["generation_exception"], True
    if not text.strip():
        if hidden_reasoning_present:
            return (
                TURN_EMPTY_AFTER_REASONING,
                ["hidden_reasoning_present", "empty_public_text"],
                True,
            )
        return TURN_FAILED, ["empty_public_text"], True

    signals = heuristic_signals(text)
    if budget_exhausted:
        return TURN_TRUNCATED_BY_BUDGET, ["done_reason:length", *signals], True
    if len(signals) >= 2:
        return TURN_TRUNCATED_BY_BUDGET, signals, True
    if signals:
        # A single weak heuristic signal without the budget flag: recorded,
        # but not confident enough alone to justify spending a continuation
        # call on it.
        return TURN_TRUNCATED_BY_BUDGET, signals, False
    return TURN_COMPLETE, [], True


def _normalize_token(word: str) -> str:
    return re.sub(r"[^a-z0-9']+", "", word.lower())


CONTINUATION_LOOKBACK_WORDS = 16


def merge_continuation(tail: str, continuation: str,
                       lookback_words: int = CONTINUATION_LOOKBACK_WORDS) -> str:
    """Join a truncated tail to its continuation, dropping restated overlap.

    v1.1 joined these with a bare f-string, so when a model restated the
    tail's closing words instead of continuing from them, the duplication
    reached the public stage:

      "...revising our foundational standards then we might need to consider
       revising our foundational standards of truth and belief"

    Word order commonly shifts in the restatement ("only then might we need"
    -> "then we might need"), so exact suffix/prefix matching does not catch
    it. Instead: walk forward through the continuation and drop the leading
    run of words already present in the tail's closing window, stopping at the
    first genuinely new word. A single-word run is dropped only when it exactly
    repeats the tail's final word, so an ordinary continuation that happens to
    open with a common word is left untouched.
    """
    tail = tail.rstrip()
    continuation = continuation.strip()
    if not continuation:
        return tail
    if not tail:
        return continuation

    tail_words = [_normalize_token(w) for w in tail.split()]
    window = {word for word in tail_words[-lookback_words:] if word}
    continuation_words = continuation.split()

    run = 0
    for word in continuation_words:
        token = _normalize_token(word)
        if token and token in window:
            run += 1
        else:
            break
    if run == 1 and (not tail_words or _normalize_token(continuation_words[0]) != tail_words[-1]):
        run = 0

    rest = continuation_words[run:]
    return tail if not rest else f"{tail} {' '.join(rest)}".strip()


def bound_continuation(text: str, max_words: int = MAX_CONTINUATION_WORDS) -> str:
    """Hard-trim a continuation response to the word budget the directive requires."""
    words = text.split()
    if len(words) > max_words:
        words = words[:max_words]
    return " ".join(words)
