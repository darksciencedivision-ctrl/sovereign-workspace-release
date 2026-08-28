"""W-83: every THREAT_MODEL.md mitigation/boundary claim carries a STATUS with an
enforcement location. The document used to assert five mitigations with no
implementation and three-of-four build-harness sub-claims contradicted by the
review; the honesty column (containment.py's shape, applied to the document)
makes over-reporting a test failure instead of a discovery."""
from __future__ import annotations

import pathlib
import re

TM = pathlib.Path(__file__).resolve().parents[2] / "docs" / "THREAT_MODEL.md"

STATUSES = ("IMPLEMENTED", "PARTIAL", "NOT IMPLEMENTED", "PLANNED", "SUPERSEDED")


def _rows():
    text = TM.read_text(encoding="utf-8")
    for line in text.splitlines():
        if not (line.startswith("| T") or line.startswith("| TB")):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if not cells or cells[0] in ("TB", "#") or set(cells[0]) <= {"-", " "}:
            continue  # header / separator rows
        yield line, cells


def test_every_threat_row_carries_a_status_token():
    rows = list(_rows())
    assert len(rows) >= 22, f"expected the full boundary+threat tables, got {len(rows)} rows"
    status_re = re.compile(r"\*\*(?:" + "|".join(STATUSES) + r")\*\*")
    missing = [cells[0] for _, cells in rows if not any(status_re.search(c) for c in cells)]
    assert not missing, f"rows without a status token: {missing}"


def test_every_status_names_an_enforcement_location_or_register_anchor():
    bad = []
    for line, cells in _rows():
        status_cell = next((c for c in cells if re.search(
            r"\*\*(?:IMPLEMENTED|PARTIAL|NOT IMPLEMENTED|PLANNED|SUPERSEDED)\*\*", c)), None)
        if status_cell is None:
            continue
        if not ("" in status_cell or "U1" in status_cell or "U2" in status_cell
                or "U3" in status_cell or "W-" in status_cell):
            bad.append((cells[0], status_cell[:80]))
    assert not bad, f"statuses without a location/anchor: {bad}"


def test_the_t9_silence_only_retraction_is_recorded_here():
    """W-80 transfer: the T9 row must say PARTIAL and name the silence-only truth - the old
    blanket 'Confidence threshold' claim protected against mishearing that the threshold never
    measured (U140)."""
    for line, cells in _rows():
        if cells[0] == "T9":
            joined = " ".join(cells)
            assert "PARTIAL" in joined and "SILENCE" in joined.upper()
            return
    raise AssertionError("T9 row vanished from THREAT_MODEL.md")


def test_not_implemented_claims_are_enumerated():
    """The card's registration duty: the four claims the review found asserted-but-unbuilt must be
    visible as NOT IMPLEMENTED in this document - T2's adversarial tests, T3 as specified, T4's
    periodic process audit, T14 entire."""
    text = TM.read_text(encoding="utf-8")
    for token in ("ADVERSARIAL TESTS are **NOT IMPLEMENTED**",
                  "**NOT IMPLEMENTED** as specified",
                  "PERIODIC PROCESS AUDIT is **NOT IMPLEMENTED**",
                  "**NOT IMPLEMENTED** — one docstring mention"):
        assert token in text, f"missing registered-absence marker: {token!r}"
