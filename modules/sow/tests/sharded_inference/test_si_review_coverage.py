"""Overnight review: branches of the new code that no test reached (found with a line tracer).

The renderings of a sum and a group count reach the operator verbatim; the "input not available"
and the alternation branches decide whether the exact route runs; the role-plan skips decide
what the health report says.
"""
from __future__ import annotations

import sys
from pathlib import Path

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import exact_counting as EC  # noqa: E402
from sovereign_product import exact_worker as EW  # noqa: E402
from sovereign_product import role_plans as RP  # noqa: E402

from test_si_exact_counting import (  # noqa: E402,F401
    OBJECTIVE, SPEC, Script, _counter, _notes, _spec)
from test_si_p4_role_plans import MANIFEST, _plan, _no_blob_hashing  # noqa: E402,F401


def test_a_sum_and_a_group_count_are_rendered_for_the_operator():
    text, rows = _notes(120)
    spec = EW.parse_spec(_spec(aggregates=[{"op": "sum", "field": "records"},
                                           {"op": "group_count", "field": "warnings"}]))
    table = EC.render_table(EW.execute(text, spec))
    assert f"- sum of records: {sum(r for _, r, _ in rows)}" in table
    assert "- records per warnings (" in table and "distinct values; top" in table
    assert table.startswith("Computed by the product over 120 records")


def test_without_the_input_the_exact_route_falls_back_with_a_note(tmp_path):
    outcome = _counter(Script(), tmp_path).run(OBJECTIVE, None)
    assert outcome.answer is None and "input is not available" in outcome.note


def test_a_top_level_alternation_is_accepted():
    ok = _spec(pattern=r"Operations note (?P<note>\d+)(?:: | - )the batch (?P<step>\d+) "
                       r"(?P<records>\d+) (?P<warnings>\d+)")
    assert EW.parse_spec(ok).anchor == "Operations note "


def test_a_model_the_manifest_maps_to_the_embedding_model_is_not_planned():
    manifest = {"MODELS": {"CRITIC": "nomic-embed-text:latest", "PRIMARY_REASONER": "qwen3:14b"}}
    _, report = _plan(manifest=manifest)
    assert "nomic-embed-text:latest" not in report and "qwen3:14b" in report


def test_a_role_model_without_an_enforceable_context_cap_keeps_its_default(monkeypatch):
    monkeypatch.setattr(RP, "context_resolution", lambda name: {"effective_cap": None})
    _, report = _plan()
    assert report["qwen3:14b"]["applied"] is False
    assert "no enforceable context cap" in report["qwen3:14b"]["reason"]
    assert RP.role_model_status(report, "qwen3:14b")[0] == "degraded"
