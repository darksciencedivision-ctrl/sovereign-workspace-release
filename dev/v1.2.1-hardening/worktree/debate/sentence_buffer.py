"""Buffers guarded public text into complete sentences for emission.

Pipeline position (see app.py run_turn):

    raw Ollama stream
      -> PublicStreamFilter        (existing; strips hidden reasoning)
      -> SentenceBuffer.feed()     (this module; line-guards, then splits
                                     into sentences)
      -> token events

Leak detection is line-anchored, so a label must be checked against a
complete line, not a raw fragment -- a fragment boundary can land in the
middle of a label. But most model turns never contain a literal '\\n' at
all, so gating every emission on one would silently defeat live streaming
(everything would arrive in one burst at turn end). Instead, as soon as
the buffered prefix of the *current* line has diverged from every known
label/value, that prefix is released immediately and the rest of the line
streams normally; only a genuinely label-shaped prefix stays held back
until the line is complete.
"""

from __future__ import annotations

import re

_SENTENCE_END = re.compile(r"[.!?][\"')\]”’]*(?=\s|$)")


def split_sentences(text: str) -> list[str]:
    """One-shot split of complete text into sentences, using the same
    boundary rule as SentenceBuffer's incremental streaming split.

    Unlike SentenceBuffer, this assumes `text` is already complete -- no
    pending-buffer state, no partial-line handling. Any trailing text with
    no terminal punctuation is still returned as a final "sentence".
    """
    sentences = []
    remaining = text
    while True:
        match = _SENTENCE_END.search(remaining)
        if not match:
            break
        cut = match.end()
        sentence = remaining[:cut]
        remaining = remaining[cut:]
        if sentence.strip():
            sentences.append(sentence.strip())
    if remaining.strip():
        sentences.append(remaining.strip())
    return sentences


def first_sentence(text: str) -> str:
    """The first sentence of `text` per the shared boundary rule, or the
    whole (stripped) text if it contains no recognized sentence boundary."""
    sentences = split_sentences(text)
    return sentences[0] if sentences else text.strip()


class SentenceBuffer:
    """Buffers raw filtered stream fragments into guarded, sentence-terminated emissions."""

    def __init__(self, guard):
        self.guard = guard
        self._line_buffer = ""
        self._line_confirmed_safe = False
        self._sentence_pending = ""

    def feed(self, fragment: str) -> tuple[list[str], list[str]]:
        """Feed a raw (hidden-reasoning-filtered) fragment.

        Returns (emitted_sentences, newly_blocked_labels).
        """
        if not fragment:
            return [], []
        self._line_buffer += fragment
        emitted: list[str] = []
        blocked: list[str] = []
        progressed = True
        while progressed:
            progressed = False
            newline_index = self._line_buffer.find("\n")
            if newline_index >= 0:
                line = self._line_buffer[:newline_index]
                self._line_buffer = self._line_buffer[newline_index + 1 :]
                emitted.extend(self._absorb_line(line, blocked, at_newline=True))
                self._line_confirmed_safe = False
                progressed = True
                continue
            if not self._line_confirmed_safe and self._line_buffer:
                if not self.guard.could_start_with_label(self._line_buffer):
                    emitted.extend(
                        self._absorb_line(self._line_buffer, blocked, at_newline=False)
                    )
                    self._line_buffer = ""
                    self._line_confirmed_safe = True
                    progressed = True
            elif self._line_confirmed_safe and self._line_buffer:
                self._sentence_pending += self._line_buffer
                self._line_buffer = ""
                emitted.extend(self._drain_sentences())
                progressed = True
        return emitted, blocked

    def _absorb_line(self, line: str, blocked: list[str], at_newline: bool) -> list[str]:
        survivors, matched = self.guard.filter_lines(line)
        blocked.extend(matched)
        if survivors:
            self._sentence_pending += survivors
            if at_newline:
                self._sentence_pending += "\n"
        return self._drain_sentences()

    def _drain_sentences(self) -> list[str]:
        emitted = []
        while True:
            match = _SENTENCE_END.search(self._sentence_pending)
            if not match:
                break
            cut = match.end()
            sentence = self._sentence_pending[:cut]
            # Leading whitespace on the remainder is intentionally kept
            # (not stripped) so it becomes the separator before the next
            # emitted sentence -- each sentence is sent as its own token
            # event and the client concatenates them with no separator.
            self._sentence_pending = self._sentence_pending[cut:]
            if sentence.strip():
                emitted.append(sentence)
        return emitted

    def finish(self) -> tuple[list[str], str, list[str]]:
        """Flush the trailing partial line/sentence at turn end.

        Returns (emitted_sentences, unterminated_tail, newly_blocked_labels).
        `unterminated_tail` is the guarded text with no terminal punctuation
        found -- the caller decides whether to emit it as-is or use it as
        the basis for a bounded continuation (Stage B). It is intentionally
        NOT included in `emitted_sentences`, so a caller can never emit the
        partial and then a corrected version by accident.
        """
        emitted: list[str] = []
        blocked: list[str] = []
        if self._line_buffer:
            if self._line_confirmed_safe:
                self._sentence_pending += self._line_buffer
                emitted.extend(self._drain_sentences())
            else:
                emitted.extend(
                    self._absorb_line(self._line_buffer, blocked, at_newline=False)
                )
            self._line_buffer = ""
            self._line_confirmed_safe = False
        tail = self._sentence_pending
        self._sentence_pending = ""
        if not tail.strip():
            tail = ""
        return emitted, tail, blocked
