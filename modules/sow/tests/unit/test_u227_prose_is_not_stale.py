"""Phase 18D — the U227 boundary moved, and the sentences that described it must move with it.

**Why this file exists.** OP-12.1 (2026-08-01, `AUTONOMOUS_BUILD_DIRECTIVE.md` §17.1) resolved U227
by successor schema: `node@1.1` admits `grok_build`, `google_antigravity` and `ollama_local`, and
`NodeRegistry.register` accepts them. Before that ruling, roughly a dozen files across the product,
the tools, the tests and the operator-facing config template explained themselves with sentences
like *"U227 is operator-reserved"*, *"no schema-valid node RECORD can name them"*, and — worst —
*"that check could never pass for either provider and never will"*.

The 18D work commit corrected nine of them and its message claimed *"all nine places it lived"*.
The gate-validator found **seven more** (MAJOR-1), three of which had become flatly false, including
`tools/providers/run_frontier_providers.ps1`'s operator-facing help text and a docstring 50 lines
above the corrected text in the SAME file. The spec-auditor independently found the same class in
`config/live_operation.example.json` — the file an operator reads while deciding whether to
authorize live operation, whose own comment invokes invariant 1 ("final authority has to be
INFORMED authority") as its warrant for being accurate.

So: a hand-count of prose sites is not a mechanism, and this repo's standing rule (U275, written by
this very phase at 18B `.picker`) is that a claim with no red-able test is a defect. This is the
detector. It does not forbid the old words — a correction that QUOTES what it is correcting is the
most honest form, and several of the fixes do exactly that. It requires that any live surface still
carrying a pre-ruling claim ALSO names the ruling that overturned it, within sight of the claim.

**Deliberately out of scope:** `docs/` (evidence reports, checkpoints, registers and receipts are
append-only records of what was true when written — rewriting them is the drift, not the fix),
`docs/canonical/` (frozen), and the FINAL_*.md reports (historical, and they predate the ruling).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: Where a READER of the running system meets these sentences: product code, the operator's tools,
#: the shipped config template, the schemas, and the tests that pin behaviour.
LIVE_ROOTS = (
    "adapters", "control_plane", "node_runtime", "mcp_server", "scheduler", "debate_service",
    "persistence", "tools", "terminal", "schemas", "tests", "config",
    "apps/desktop/selfcheck", "apps/desktop/picker", "apps/desktop/conductor",
    "apps/desktop/renderer", "apps/desktop/test",
)
SUFFIXES = {".py", ".js", ".ps1", ".json", ".md"}
SKIP_PARTS = {"node_modules", ".git", "__pycache__", ".gvtmp", "dist", "build"}

#: Claims that were true before OP-12.1 and are false after it. Each is a shape actually found in
#: this repo at the 18D gate, not an invented one.
STALE_CLAIMS = (
    re.compile(r"U227[^.\n]{0,140}operator-reserved", re.I),
    re.compile(r"operator-reserved[^.\n]{0,140}U227", re.I),
    re.compile(r"no schema-valid node RECORD can name", re.I),
    re.compile(r"the amendment is operator-reserved", re.I),
    re.compile(r"refuses (?:both|either) adapter id", re.I),
    re.compile(r"canonical node-record vocabulary is unchanged", re.I),
    re.compile(r"(?:could|can) never pass[^.\n]{0,60}never will", re.I),
)

#: The ruling that overturned them. A file may keep the old sentence only in the company of this.
RULING = "OP-12.1"

#: How far from the stale sentence the ruling has to be. Twelve lines is a docstring paragraph or a
#: JSON comment value; far enough to allow "the claim, then the correction", close enough that a
#: reader who reads one reads the other.
WINDOW = 12


def _live_files() -> list[Path]:
    seen: dict[Path, None] = {}
    for root in LIVE_ROOTS:
        base = REPO / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix.lower() not in SUFFIXES or not path.is_file():
                continue
            if SKIP_PARTS & set(path.relative_to(REPO).parts):
                continue
            seen[path] = None
    return sorted(seen)


def _stale_hits(path: Path) -> list[tuple[int, str]]:
    """Hits are found on the FLATTENED text, not line by line.

    The first draft scanned lines, and missed `test_op12_probe_session.py`'s module docstring —
    *"`NodeRegistry.register` refuses both / adapter ids until the operator rules on U227"* — purely
    because the sentence wrapped. A prose detector that a line break defeats is not a detector.
    Offsets are mapped back to line numbers so the failure still points at a place.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:  # pragma: no cover - the tree is UTF-8
        return []
    flat = "\n".join(lines).replace("\n", " ")
    starts, pos = [], 0
    for line in lines:
        starts.append(pos)
        pos += len(line) + 1

    def line_of(offset: int) -> int:
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo

    hits, seen_lines = [], set()
    for claim in STALE_CLAIMS:
        for match in claim.finditer(flat):
            i = line_of(match.start())
            if i in seen_lines:
                continue
            window = lines[max(0, i - WINDOW): i + WINDOW + 1]
            if not any(RULING in w for w in window):
                seen_lines.add(i)
                hits.append((i + 1, lines[i].strip()[:160]))
    return sorted(hits)


def test_the_live_surfaces_are_scanned_at_all() -> None:
    """A detector over an empty file list passes vacuously. This is the guard on the guard: the
    roots must resolve, and the corpus must be large enough to be the corpus it claims to be."""
    files = _live_files()
    assert len(files) > 200, f"only {len(files)} live files scanned - LIVE_ROOTS has gone stale"
    names = {p.name for p in files}
    for expected in ("registry.py", "run_frontier_providers.ps1", "live_operation.example.json",
                     "op12-acceptance-selfcheck.js", "statusbar-model.js"):
        assert expected in names, f"{expected} is not in the scanned corpus"


def test_no_live_surface_claims_u227_is_still_unruled_without_naming_the_ruling() -> None:
    """The 18D validator MAJOR-1, mechanised. Reintroduce any pre-ruling sentence on a live surface
    without OP-12.1 within twelve lines and this goes red, naming the file and line."""
    offenders = []
    for path in _live_files():
        for line_no, text in _stale_hits(path):
            offenders.append(f"{path.relative_to(REPO).as_posix()}:{line_no}: {text}")
    assert not offenders, (
        "these live surfaces still describe U227 as unruled, with no mention of OP-12.1 nearby:\n  "
        + "\n  ".join(offenders)
    )


def test_the_detector_actually_fires(tmp_path: Path) -> None:
    """Mutation-proof, in-test: the exact sentence the validator found in the operator-facing runner
    must be caught, and the same sentence in the company of the ruling must not be."""
    stale = tmp_path / "stale.ps1"
    stale.write_text(
        "    What is still NOT claimed: no Sovereign node RECORD exists for either\n"
        "    provider (U227 is operator-reserved).\n",
        encoding="utf-8",
    )
    assert _stale_hits(stale), "the detector missed the sentence it was written for"

    corrected = tmp_path / "corrected.ps1"
    corrected.write_text(
        "    Until 2026-08-01 no schema-valid node RECORD can name them; the operator ruled\n"
        "    OP-12.1 that day and node@1.1 admits both.\n",
        encoding="utf-8",
    )
    assert not _stale_hits(corrected), "a quoted-and-corrected claim must not be flagged"


@pytest.mark.parametrize("claim", [c.pattern for c in STALE_CLAIMS])
def test_every_pattern_was_a_real_sentence_in_this_repo(claim: str) -> None:
    """Guard against a detector padded with shapes that never occurred: every pattern here was found
    verbatim at the 18D gate by the gate-validator or the spec-auditor, and the checkpoint records
    where. Compiling is all this asserts - the record is the checkpoint - but a pattern that cannot
    compile would silently narrow the scan."""
    assert re.compile(claim, re.I) is not None
