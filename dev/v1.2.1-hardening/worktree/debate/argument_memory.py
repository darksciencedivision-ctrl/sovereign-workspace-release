"""Bounded, deterministic argument-recycling detection.

WHY THIS WAS REWRITTEN (2026-08-07, post-run audit)
---------------------------------------------------
The first implementation could not fire. It stored a 12-word `concept_string`
in memory, then compared the *next full turn's* 3-5-word shingles against that
12-word string using Jaccard over the union. A 200-word turn yields several
hundred shingles; the stored concept yields ~27. The union is dominated by the
current turn, so the score collapsed toward zero:

    record a 130-word turn, then feed the IDENTICAL turn back  ->  0.0000

against a threshold of 0.35. The mechanism was mathematically incapable of
matching at production turn lengths. Its unit test passed only because it used
two 15-word sentences, where `concept_string` retains essentially the whole
text.

Two changes fix it, and both are needed:

1. GRANULARITY. Paraphrase destroys n-grams. "hybrid models that blend
   probabilistic and deterministic elements" and "hybrid models, which could
   blend deterministic and probabilistic elements" share almost no 3-grams.
   Measured on a real recycled pair from the live run:

       Jaccard 3-5gram (old)      0.047      <- unusable
       Containment 3-5gram        0.093      <- still unusable
       Containment 2gram          0.227
       Containment content-words  0.535      <- usable

   Comparison therefore happens over content-word SETS, not shingles.

2. DENOMINATOR. Jaccard punishes length differences that carry no meaning.
   Containment -- |A intersect B| / |smaller set| -- asks the right question:
   "how much of the shorter argument reappears in the longer one?"

THRESHOLD CALIBRATION
---------------------
Calibrated against all 55 same-seat comparisons in the 59-turn v1.1 acceptance
corpus (`audit/v1_1_soak_evidence_run{1,2}.json`), each turn scored against
that seat's own previous 5 turns:

    p10 0.252   p25 0.293   p50 0.336   p75 0.384   p90 0.455   p95 0.557
    min 0.188   mean 0.359  max 0.829

Two seats arguing one topic reuse vocabulary, so the *baseline* is ~0.34. The
old threshold of 0.35 sits at the median of this metric: ported over unchanged
it would flag 47% of all turns.

Reference points from real turns (see tests/test_v1_2_audit_regressions.py):

    identical turn repeated verbatim          1.000
    known recycled pair, live run (REPEAT_A/B) 0.471   <- must fire
    distinct argument, same seat (control)     0.072   <- must not fire
    corpus median (normal same-topic reuse)    0.336

Selected operating point:

    0.45  -> flags 12.7% of the acceptance corpus (7/55)
            sits at p90, above normal reuse, below the recycled pair at 0.471

An earlier hand-transcribed probe of the same pair read 0.535 and suggested
0.50. Measured against the verbatim fixture the pair is 0.471, so 0.50 would
have missed the exact case that motivated this rewrite. The threshold is set
from the fixture, not from the probe.

This is calibrated on ONE model pair across TWO topics. It is a defensible
starting point, not a constant. Re-calibrate if the seat models change.
"""

from __future__ import annotations

import re
from collections import deque

# Containment over content-word sets. See THRESHOLD CALIBRATION above.
REPETITION_THRESHOLD = 0.45
# Retained under the old name so existing config/imports keep working.
PHRASE_REPETITION_THRESHOLD = REPETITION_THRESHOLD

MEMORY_DEPTH = 5
_MIN_CONTENT_WORD_LEN = 3
_MAX_COMPARISON_CHARS = 2400  # bounds memory; a long turn is ~1,800 chars

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "is",
    "are", "was", "were", "it", "that", "this", "as", "for", "with", "at",
    "by", "be", "been", "being", "we", "our", "us", "i", "you", "your",
    "they", "their", "not", "if", "can", "could", "would", "might", "may",
    "must", "should", "have", "has", "had", "do", "does", "did", "from",
    "which", "what", "who", "when", "where", "how", "than", "then", "there",
    "these", "those", "such", "also", "its", "his", "her", "he", "she",
    "them", "will", "more", "most", "very", "into", "about", "while",
    "even", "rather", "both", "any", "all", "one", "two",
}


def _normalize_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def content_words(text: str) -> set[str]:
    """Content-word set: lowercased, stopworded, very short tokens dropped.

    This is the comparison surface. Set semantics are deliberate -- a seat
    that restates the same argument reuses the same content vocabulary even
    when it rearranges every sentence.
    """
    return {
        word
        for word in _normalize_words(text)
        if word not in _STOPWORDS and len(word) >= _MIN_CONTENT_WORD_LEN
    }


def containment(previous_texts, current_text: str) -> float:
    """Max containment of `current_text` against any one of `previous_texts`.

    containment(A, B) = |A intersect B| / min(|A|, |B|)

    Returns 0.0 when either side has no content words.
    """
    current = content_words(current_text)
    if not current:
        return 0.0
    best = 0.0
    for previous_text in previous_texts:
        previous = content_words(previous_text)
        if not previous:
            continue
        shared = len(current & previous)
        best = max(best, shared / min(len(current), len(previous)))
    return best


def _shingles(words: list[str], size: int) -> set[str]:
    if len(words) < size:
        return set()
    return {
        " ".join(words[i : i + size])
        for i in range(len(words) - size + 1)
        if not all(word in _STOPWORDS for word in words[i : i + size])
    }


def phrase_overlap(previous_texts, current_text: str) -> float:
    """DEPRECATED -- Jaccard over 3-5 word shingles.

    Retained only so the failure is reproducible and the regression tests can
    assert that it is NOT used for detection. Do not call this for repetition
    detection: it scores 0.047 on a genuinely recycled production-length pair.
    """
    current_words = _normalize_words(current_text)
    current_shingles: set[str] = set()
    for size in (3, 4, 5):
        current_shingles |= _shingles(current_words, size)
    if not current_shingles:
        return 0.0
    best = 0.0
    for previous_text in previous_texts:
        previous_words = _normalize_words(previous_text)
        previous_shingles: set[str] = set()
        for size in (3, 4, 5):
            previous_shingles |= _shingles(previous_words, size)
        if not previous_shingles:
            continue
        union = current_shingles | previous_shingles
        best = max(best, len(current_shingles & previous_shingles) / len(union) if union else 0.0)
    return best


def concept_string(text: str, max_words: int = 12) -> str:
    """A compact, deterministic label for an argument.

    Used for the operator-facing `move_reason` and for the recent-arguments
    list handed back to the seat in its prompt. NOT used for comparison --
    that was the original defect.
    """
    words = [word for word in _normalize_words(text) if word not in _STOPWORDS]
    return " ".join(words[:max_words])


class ArgumentMemory:
    """Per-seat bounded memory of recent arguments. In-memory only.

    Each entry keeps two things:
      * `concept` -- compact label, what the seat sees in its prompt and what
        appears in `move_reason`;
      * `comparison` -- bounded full text, what detection actually scores
        against. Keeping these separate is the fix: the prompt needs something
        short, the detector needs something representative.
    """

    def __init__(self, seat_names, depth: int = MEMORY_DEPTH):
        self.depth = depth
        self._memory: dict[str, deque[tuple[str, str]]] = {
            name: deque(maxlen=depth) for name in seat_names
        }
        # Per-instance, not class-level: a shared dict would leak scores
        # between ArgumentMemory instances (and between tests).
        self._scores: dict[str, float] = {}

    def reset(self):
        for entries in self._memory.values():
            entries.clear()

    def recent(self, seat_name: str) -> list[str]:
        """Compact concept labels, for the seat's prompt. Unchanged interface."""
        return [concept for concept, _comparison in self._memory.get(seat_name, ())]

    def last_score(self, seat_name: str) -> float:
        """Most recent containment score for this seat, for diagnostics."""
        return self._scores.get(seat_name, 0.0)

    def check_and_record(self, seat_name: str, text: str) -> str | None:
        """Record `text`, and report whether it recycles this seat's own recent
        argument above `REPETITION_THRESHOLD`.

        Comparison is per-seat only -- one seat's arguments never flag another's.
        Returns the matched concept label, or None.
        """
        entries = self._memory.setdefault(seat_name, deque(maxlen=self.depth))
        score = containment([comparison for _concept, comparison in entries], text)
        self._scores[seat_name] = score

        concept = concept_string(text)
        matched = concept if (score >= REPETITION_THRESHOLD and concept) else None

        if concept:
            entries.append((concept[:200], text[:_MAX_COMPARISON_CHARS]))
        return matched
