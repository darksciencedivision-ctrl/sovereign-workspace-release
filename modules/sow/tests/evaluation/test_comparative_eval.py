"""Phase 13 comparative evaluation: the 4-config harness runs end-to-end on the reference
project, instruments cost-to-accepted-output + a capability matrix, and states its honest
mock-backend limitation. Model-quality is NOT claimed (mock backends)."""
from __future__ import annotations

import json
from pathlib import Path

from tools.evaluation.harness import EvaluationHarness

ROOT = Path(__file__).resolve().parents[2]


def test_four_configs_run_and_are_instrumented(tmp_path) -> None:
    report = EvaluationHarness(tmp_path).run()
    names = [c["config"] for c in report["configs"]]
    assert names == ["C0_single_pass", "C2_conductor_raw", "C3_sovereign_no_debate", "C4_sovereign_debate"]
    for c in report["configs"]:
        assert c["model_tokens"] > 0 and c["accepted"] >= 1
        assert c["cost_to_accepted_tokens"] != float("inf")


def test_governance_configs_are_provenance_bearing_and_gated_baselines_are_not(tmp_path) -> None:
    report = EvaluationHarness(tmp_path).run()
    cap = report["capability_matrix"]
    # the honest capability comparison: baselines lack provenance/gating; Sovereign configs have it
    assert cap["C0_single_pass"] == {"provenance": False, "gated": False, "debated": False, "recoverable": False}
    assert cap["C2_conductor_raw"]["gated"] is False
    assert cap["C3_sovereign_no_debate"]["gated"] and cap["C3_sovereign_no_debate"]["provenance"]
    assert cap["C4_sovereign_debate"]["debated"] and cap["C4_sovereign_debate"]["recoverable"]


def test_debate_costs_more_than_no_debate_for_same_output(tmp_path) -> None:
    """Honest cost curve: the debate config spends more (tokens + control ops) than no-debate
    for the SAME mock content — governance/debate is a cost the operator pays, not free."""
    report = EvaluationHarness(tmp_path).run()
    by = {c["config"]: c for c in report["configs"]}
    assert by["C4_sovereign_debate"]["model_tokens"] > by["C3_sovereign_no_debate"]["model_tokens"]
    assert by["C3_sovereign_no_debate"]["control_ops"] > by["C2_conductor_raw"]["control_ops"]
    # and the baseline is cheapest per accepted output (it does the least)
    assert by["C0_single_pass"]["control_ops"] == 0
    # C4 ran the REAL Debate Service (a debate record exists), not a synthetic surcharge
    assert by["C4_sovereign_debate"]["debate_id"] and by["C4_sovereign_debate"]["debate_id"].startswith("d-")


def test_report_states_its_mock_limitation_honestly(tmp_path) -> None:
    report = EvaluationHarness(tmp_path).run()
    lim = report["honest_limitation"].lower()
    assert "mock" in lim and "not model reasoning quality" in lim and "track e" in lim


def test_writes_evidence_artifact(tmp_path) -> None:
    # Completion-audit F2: tests must not rewrite committed evidence (host-dependent
    # tokenizer/wallclock re-dirtied docs/evidence on every run). The harness output is
    # exercised against tmp; the committed artifact is asserted read-only.
    report = EvaluationHarness(tmp_path).run()
    out = tmp_path / "PHASE13_EVAL_REPORT.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert json.loads(out.read_text(encoding="utf-8"))["harness"] == "phase13-eval@1.0"
    committed = ROOT / "docs" / "evidence" / "PHASE13_EVAL_REPORT.json"
    assert committed.is_file() and json.loads(committed.read_text(encoding="utf-8"))["harness"] == "phase13-eval@1.0"
