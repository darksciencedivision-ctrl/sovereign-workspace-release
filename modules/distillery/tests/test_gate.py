from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from distillery.common import ContractError
from gate import EvaluationRun, GateMargins, HistoricalBestStore, paired_gate, paired_mean_ci, power_report
from gate.controlled import controlled_model_effect


class GateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.margins = GateMargins(0.1, 0.05, 0.05, "2026-08-20T00:00:00Z", "operator")
        self.eval_run = EvaluationRun("eval-001", "2026-08-20T01:00:00Z", "v1", "a" * 64)
        self.ids = [f"i{i}" for i in range(8)]

    def test_paired_gate_pass_and_anti_ratchet(self) -> None:
        passed = paired_gate(self.ids, [1.0] * 8, [0.8] * 8, [0.95] * 8, [0.96] * 8, self.margins, self.eval_run, tail="two-sided")
        self.assertTrue(passed["passed"])
        self.assertEqual(passed["predeclaration"]["margins_declared_at"], "2026-08-20T00:00:00Z")
        self.assertEqual(passed["predeclaration"]["eval_started_at"], "2026-08-20T01:00:00Z")
        self.assertEqual(len(passed["predeclaration"]["predeclaration_evidence_hash"]), 64)
        failed = paired_gate(self.ids, [0.8] * 8, [0.6] * 8, [0.8] * 8, [0.9] * 8, self.margins, self.eval_run, tail="two-sided")
        self.assertFalse(failed["passed"])
        self.assertFalse(failed["rules"]["historical_best"])

    def test_unpaired_path_rejected(self) -> None:
        with self.assertRaises(ContractError):
            paired_gate(self.ids, [1.0], [0.0], [0.0], [0.0], self.margins, self.eval_run, tail="two-sided")

    def test_power_does_not_select_policy(self) -> None:
        report = power_report([0.1, 0.2, 0.0, 0.2, 0.1], policy_margins=self.margins, tail="two-sided")
        self.assertFalse(report["margins_selected_from_power"])
        self.assertEqual(report["tail"], "two-sided")
        self.assertAlmostEqual(report["z_value"], 1.959963984540054, places=6)

    def test_tail_semantics_are_explicit(self) -> None:
        two_sided = paired_mean_ci([0.1, 0.2, 0.3], tail="two-sided", seed=1)
        one_sided = paired_mean_ci([0.1, 0.2, 0.3], tail="lower-one-sided", seed=1)
        self.assertEqual(two_sided["lcb_one_sided_equivalent_confidence"], 0.975)
        self.assertEqual(one_sided["lcb_one_sided_equivalent_confidence"], 0.95)
        self.assertIsNotNone(two_sided["ucb"])
        self.assertIsNone(one_sided["ucb"])

    def test_predeclaration_ordering_rejects_late_equal_missing_and_unparseable(self) -> None:
        for declared in ("2026-08-20T02:00:00Z", "2026-08-20T01:00:00Z"):
            with self.subTest(declared=declared), self.assertRaises(ContractError):
                paired_gate(self.ids, [1.0] * 8, [0.8] * 8, [0.95] * 8, [0.96] * 8, GateMargins(0.1, 0.05, 0.05, declared, "operator"), self.eval_run, tail="two-sided")
        for bad in (None, "", "not-a-time", "2026-08-20T00:00:00"):
            with self.subTest(margins_declared_at=bad), self.assertRaises(ContractError):
                GateMargins(0.1, 0.05, 0.05, bad, "operator")
        for bad in (None, "", "not-a-time", "2026-08-20T01:00:00"):
            with self.subTest(eval_started_at=bad), self.assertRaises(ContractError):
                EvaluationRun("eval-001", bad, "v1", "a" * 64)

    def test_historical_best_rejects_single_run_max(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = HistoricalBestStore(Path(directory) / "history.jsonl")
            row = {"suite_version": "v1", "bundle_id": "b", "n": 10, "mean": 0.8, "dispersion": 0.1, "ci_metadata": {"confidence": 0.95}, "promotion_time": "2026-01-01T00:00:00Z"}
            store.append_promotion_run(row)
            with self.assertRaises(ContractError):
                store.reference("v1")
            store.append_promotion_run({**row, "mean": 0.6, "promotion_time": "2026-02-01T00:00:00Z"})
            self.assertAlmostEqual(store.reference("v1")["mean"], 0.7)

    def test_controlled_eval_rejects_serving_change(self) -> None:
        baseline = {name: "same" for name in ("prompt", "tools", "retrieval", "memory", "sandbox", "serving_policy", "eval_suite")}
        baseline["model_intervention"] = "base"
        candidate = {**baseline, "model_intervention": "lora"}
        evaluator = lambda config: (self.ids, [1.0 if config["model_intervention"] == "lora" else 0.8] * 8)
        self.assertTrue(controlled_model_effect(baseline, candidate, evaluator, target_reference=[0.8] * 8, historical_best=[0.9] * 8, margins=self.margins, eval_run=self.eval_run, tail="two-sided")["gate"]["passed"])
        candidate["retrieval"] = "changed"
        with self.assertRaises(ContractError):
            controlled_model_effect(baseline, candidate, evaluator, target_reference=[0.8] * 8, historical_best=[0.9] * 8, margins=self.margins, eval_run=self.eval_run, tail="two-sided")


if __name__ == "__main__":
    unittest.main()
