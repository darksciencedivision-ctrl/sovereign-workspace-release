"""Strip-only debate-turn normalizer (BOOT-FIX v2, Step B).

Scope is deliberately narrow. This module cleans a single, safe class of
model-output noncompliance surfaced by BOOT_PROOF_01 (2026-07-15):

  * axis 1 -- a leading preamble block emitted before the first ``CLAIM:``
    header (e.g. a ``<think>`` block, or a ``THINKING ABOUT POTENTIAL
    PITFALLS:`` section), and markdown decoration wrapped around section
    headers (``**CLAIM:**`` -> ``CLAIM:``).

It NEVER attempts to repair the model-behaviour failures that the same
evidence proved a normalizer must not paper over:

  * axis 2 -- an echoed ``RETRY REQUIREMENTS:`` scaffold (or any trailing
    extra section). Trailing content is left untouched, so it still trips
    the "Unexpected section structure" check and fails the contract.
  * axis 3 -- non-English code-switching or fabricated/ungrounded content.
    Section *content* is never translated, rewritten, reordered, dropped,
    or synthesised.

Permitted transforms (both only make the validator's view of headers
*stricter or unchanged*, never more permissive about content):
  1. Strip markdown decoration immediately around a header token so the
     engine's header regex recognises it (``**CLAIM:**`` -> ``CLAIM:``).
  2. Trim any text before the first recognised ``CLAIM:`` header.

If there is no ``CLAIM:`` header at all, the text is returned unchanged so
the contract fails honestly with a genuinely missing CLAIM. Already-compliant
output passes through unchanged (aside from leading whitespace the engine's
own ``normalize_text`` already strips).

The engine's contract parser (synth_king.section_headers /
section_validation_details) treats a header as: start-of-line, optional
whitespace, an uppercase token matching ``[A-Z_][A-Z_ ]{2,40}``, optional
whitespace, ``:``. This module mirrors that exact notion of a header (case
-insensitively) so it never invents structure the validator would not itself
see, and only rewrites lines that actually carried markdown decoration.
"""

from __future__ import annotations

import re

# Mirror of the engine's header token shape (synth_king.section_headers),
# matched case-insensitively on the *undecorated* token.
_HEADER_TOKEN = r"[A-Za-z_][A-Za-z_ ]{2,40}"
_HEADER_TOKEN_RE = re.compile(rf"^{_HEADER_TOKEN}$")

# Markdown emphasis characters that may wrap a header token or its content.
# NOTE: '_' is included because markdown bold/italic use it (``__CLAIM__``), but
# it is ONLY ever stripped at the *boundaries* of a token/content run -- never
# internally -- so a legitimate header token like ``FINAL_SYNTHESIS`` keeps its
# underscore. Stripping internal underscores would rewrite the header and is
# exactly the kind of masking this module must not do.
_EMPHASIS = "*_`~"
_BOUNDARY_STRIP = _EMPHASIS + " \t"
# Leading block/quote/indent markers that may precede a header on its line.
_LEAD_BLOCK_RE = re.compile(r"^[\s>#]+")
_STRIP_LEAD_EMPHASIS_RE = re.compile(rf"^[{re.escape(_EMPHASIS)}]+")
_STRIP_TRAIL_EMPHASIS_RE = re.compile(rf"[{re.escape(_EMPHASIS)}]+$")

# The first required section in BOTH contract types (debate and canonical)
# is CLAIM, so preamble-trimming keys on it universally.
_FIRST_HEADER = "CLAIM"
_CLAIM_LINE_RE = re.compile(rf"(?im)^\s*{_FIRST_HEADER}\s*:")


def _strip_header_decoration(text: str) -> str:
    """Rewrite decorated header lines to bare ``TOKEN: rest`` form.

    A line is only rewritten when, after removing surrounding markdown
    decoration, the part before the first colon is a valid header token AND
    the rewrite actually differs from the original (so already-bare lines and
    ordinary prose are left untouched).
    """
    out_lines: list[str] = []
    for line in text.split("\n"):
        # Peel leading indentation / quote (>) / ATX (#) markers.
        body = _LEAD_BLOCK_RE.sub("", line)
        left, sep, right = body.partition(":")
        if not sep:
            out_lines.append(line)
            continue
        # The token is the left side with emphasis/whitespace stripped ONLY at
        # its boundaries; internal characters (e.g. the underscore in
        # FINAL_SYNTHESIS) are preserved verbatim.
        token = left.strip(_BOUNDARY_STRIP)
        if not _HEADER_TOKEN_RE.match(token):
            out_lines.append(line)
            continue
        # Clean the same-line content after the colon: drop leading/trailing
        # runs of pure emphasis (closing ** etc.) but keep real content verbatim.
        rest = right.strip()
        rest = _STRIP_LEAD_EMPHASIS_RE.sub("", rest).strip()
        rest = _STRIP_TRAIL_EMPHASIS_RE.sub("", rest).strip()
        rebuilt = f"{token}:" if not rest else f"{token}: {rest}"
        out_lines.append(rebuilt if rebuilt != line.strip() else line)
    return "\n".join(out_lines)


def _trim_leading_preamble(text: str) -> str:
    """Drop everything before the first ``CLAIM:`` header, if any.

    No-op when the text already begins with CLAIM (only leading blank space
    precedes it) or when no CLAIM header exists.
    """
    match = _CLAIM_LINE_RE.search(text)
    if not match:
        return text
    prefix = text[: match.start()]
    if prefix.strip() == "":
        return text
    return text[match.start():]


def normalize_debate_turn(text: str) -> str:
    """Return a strip-only-normalized copy of a raw debate/king turn.

    Safe to call on any output: compliant text is returned effectively
    unchanged, and text this module cannot safely clean is returned unchanged
    so the strict contract fails it honestly.
    """
    if not text:
        return text
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _strip_header_decoration(normalized)
    normalized = _trim_leading_preamble(normalized)
    return normalized
