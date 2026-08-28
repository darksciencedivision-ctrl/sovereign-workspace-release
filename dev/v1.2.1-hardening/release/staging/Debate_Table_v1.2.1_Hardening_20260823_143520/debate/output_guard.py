"""Control-text leak guard (best-effort anti-echo / output sanitization).

This is NOT a confidentiality boundary. A model can paraphrase, translate,
summarize or partially reword anything placed in its context; no lexical
filter can guarantee secrecy. The guard removes prompt-control labels and
long operator-controlled literals that a model echoes back verbatim into
its public speech.

Operates on buffered, line-complete text only -- a label split across two
raw stream fragments must not slip past detection just because it arrived
in pieces.

The blocked label set is passed in by the caller (app.TURN_PROMPT_LABELS)
so the guard and the prompt builder can never drift apart.
"""

from __future__ import annotations

import re

# P0-07: ordinary short words must never become leak-blocking prefixes.
# Only operator values at least this long are registered as protected
# literals; anything shorter is documented residual risk, not machinery.
MIN_DYNAMIC_LENGTH = 12

REASONING_TAG_NAME = r"(?:think|analysis|reasoning)"
OPEN_TAG_RE = re.compile(rf"<\s*{REASONING_TAG_NAME}\b[^<>]*?>", re.I)
CLOSE_TAG_RE = re.compile(rf"<\s*/\s*{REASONING_TAG_NAME}\b[^<>]*?>", re.I)
TAG_NAME_RE = re.compile(rf"<\s*({REASONING_TAG_NAME})\b", re.I)


def _strip_emphasis(line: str) -> str:
    """Remove a leading/trailing markdown bold marker before comparison."""
    stripped = line.strip()
    if stripped.startswith("**"):
        stripped = stripped[2:]
        if stripped.endswith("**"):
            stripped = stripped[:-2]
        stripped = stripped.strip()
    return stripped


class OutputGuard:
    """Detects and removes leaked control lines from buffered public text."""

    def __init__(self, labels, dynamic_values=None):
        self.labels = tuple(labels)
        protected: list[str] = []
        for value in dynamic_values or []:
            if not value:
                continue
            normalized = value.strip().lower()
            if not normalized:
                continue
            # P0-08: a multiline control value is protected line-by-line so
            # echoing only a LATER line still blocks. Segments shorter than
            # MIN_DYNAMIC_LENGTH are dropped from protection by design.
            for segment in re.split(r"[\r\n]+", normalized):
                segment = segment.strip()
                if len(segment) >= MIN_DYNAMIC_LENGTH:
                    protected.append(segment)
        # Deduplicate, preserving order (deterministic diagnostics).
        seen: dict[str, None] = {}
        for entry in protected:
            seen.setdefault(entry, None)
        self.dynamic_values = tuple(seen)

    def _matched_label(self, candidate: str) -> str | None:
        for label in self.labels:
            if re.match(rf"^{re.escape(label)}", candidate, re.I):
                return label
        return None

    def _matched_dynamic(self, candidate_lower: str) -> bool:
        # P0-06: containment ANYWHERE in the line, not just as a prefix.
        return any(value in candidate_lower for value in self.dynamic_values)

    def scan_line(self, line: str) -> str | None:
        """Return the matched label (or a marker for a dynamic-value echo)
        if `line` is leaked control text, else None."""
        candidate = _strip_emphasis(line)
        if not candidate:
            return None
        label = self._matched_label(candidate)
        if label:
            return label
        if self._matched_dynamic(candidate.lower()):
            return "<dynamic control text>"
        return None

    def _ends_inside_dynamic(self, partial_lower: str) -> bool:
        """True if the tail of `partial_lower` could be the beginning of a
        protected literal arriving across a chunk boundary."""
        window = min(len(partial_lower), max(len(v) for v in self.dynamic_values) - 1 if self.dynamic_values else 0)
        if window <= 0:
            return False
        tail = partial_lower[-window:]
        for value in self.dynamic_values:
            for k in range(1, len(value)):
                if tail.endswith(value[:k]):
                    return True
        return False

    def could_start_with_label(self, partial_line: str) -> bool:
        """True if `partial_line` could still grow into a blocked line.

        Used to release ordinary speech before a newline shows up while
        keeping any potential leak buffered until the full-line check runs.
        """
        candidate = partial_line.lstrip()
        if not candidate or candidate == "*":
            return True
        body = candidate[2:] if candidate.startswith("**") else candidate
        lowered = body.lower()
        if not lowered:
            return True
        for label in self.labels:
            label_lower = label.lower()
            if label_lower.startswith(lowered) or lowered.startswith(label_lower):
                return True
        if self._matched_dynamic(lowered):
            return True
        return self._ends_inside_dynamic(lowered)

    def filter_lines(self, text: str) -> tuple[str, list[str]]:
        """Remove leaked control lines from buffered `text`.

        Returns (surviving_text, matched_labels). Surviving lines are
        rejoined with '\\n' in their original order; blocked lines are
        dropped entirely, and all valid speech before/after is preserved.
        """
        lines = text.split("\n")
        survivors = []
        matched = []
        for line in lines:
            hit = self.scan_line(line)
            if hit:
                matched.append(hit)
                continue
            survivors.append(line)
        return "\n".join(survivors), matched