from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from distillery.common import ContractError
from gate import EvaluationRun, GateMargins, HistoricalBestStore, paired_gate


def row(bundle: str, mean: float, when: str, item_results: dict | None = None) -> dict:
    base = {"suite_version": "v1", "bundle_id": bundle, "n": 10, "mean": mean, "dispersion": 0.1, "ci_metadata": {"confidence": 0.95}, "promotion_time": when}
    return {**base, **({"item_results": item_results} if item_results is not None else {})}


class ReferenceVectorBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.store = HistoricalBestStore(Path(self._directory.name) / "history.jsonl")

    def tearDown(self) -> None:
        self._directory.cleanup()

    def test_vector_comes_from_single_governed_run(self) -> None:
        self.store.append_promotion_run(row("b1", 0.5, "2026-01-01T00:00:00Z", {"x": 0.99}))
        self.store.append_promotion_run(row("b1", 0.7, "2026-02-01T00:00:00Z", {"x": 0.4}))
        vector = self.store.reference_vector("v1", ["x"])
        self.assertEqual(vector["governing_bundle"], "b1")
        self.assertEqual(vector["supplier_promotion_time"], "2026-02-01T00:00:00Z")
        self.assertEqual(vector["values"], [0.4])
        self.assertEqual(vector["bindings"]["x"]["supply_rule"], "SINGLE_GOVERNED_RUN_NO_COMPOSITE")

    def test_no_per_item_maxima_across_bundles_or_runs(self) -> None:
        self.store.append_promotion_run(row("low", 0.3, "2026-01-01T00:00:00Z", {"x": 0.95}))
        self.store.append_promotion_run(row("low", 0.35, "2026-01-15T00:00:00Z", {"x": 0.30}))
        self.store.append_promotion_run(row("high", 0.8, "2026-02-01T00:00:00Z", {"y": 0.9}))
        self.store.append_promotion_run(row("high", 0.85, "2026-02-15T00:00:00Z", {"y": 0.2}))
        with self.assertRaises(ContractError):
            self.store.reference_vector("v1", ["x"])
        governed = self.store.reference_vector("v1", ["y"])
        self.assertEqual(governed["governing_bundle"], "high")
        self.assertNotEqual(governed["values"], [0.9])

    def test_no_composite_stitching_within_governed_bundle(self) -> None:
        self.store.append_promotion_run(row("b1", 0.5, "2026-01-01T00:00:00Z", {"a": 0.9}))
        self.store.append_promotion_run(row("b1", 0.6, "2026-02-01T00:00:00Z", {"b": 0.9}))
        with self.assertRaises(ContractError):
            self.store.reference_vector("v1", ["a", "b"])

    def test_unqualified_bundles_fail_closed(self) -> None:
        self.store.append_promotion_run(row("solo", 0.9, "2026-01-01T00:00:00Z", {"x": 0.9}))
        with self.assertRaises(ContractError):
            self.store.reference_vector("v1", ["x"])

    def test_governing_bundle_tie_prefers_higher_n_deterministically(self) -> None:
        self.store.append_promotion_run(row("wide", 0.5, "2026-01-01T00:00:00Z", {"x": 0.5}))
        self.store.append_promotion_run(row("wide", 0.7, "2026-02-01T00:00:00Z", {"x": 0.5}))
        self.store.append_promotion_run({**row("narrow", 0.5, "2026-03-01T00:00:00Z", {"x": 0.5}), "n": 50})
        self.store.append_promotion_run({**row("narrow", 0.7, "2026-04-01T00:00:00Z", {"x": 0.5}), "n": 50})
        vector = self.store.reference_vector("v1", ["x"])
        self.assertEqual(vector["governing_bundle"], "narrow")

    def test_latest_covering_run_supplies_values(self) -> None:
        self.store.append_promotion_run(row("b1", 0.5, "2026-01-01T00:00:00Z", {"a": 0.1, "b": 0.1}))
        self.store.append_promotion_run(row("b1", 0.6, "2026-03-01T00:00:00Z", {"a": 0.4}))
        self.store.append_promotion_run(row("b1", 0.55, "2026-02-01T00:00:00Z", {"a": 0.2, "b": 0.2}))
        vector = self.store.reference_vector("v1", ["a", "b"])
        self.assertEqual([binding["promotion_time"] for binding in vector["bindings"].values()], ["2026-02-01T00:00:00Z"] * 2)
        self.assertEqual(vector["values"], [0.2, 0.2])

    def test_legacy_aggregate_rows_cannot_impersonate_items(self) -> None:
        self.store.append_promotion_run(row("legacy", 0.95, "2026-01-01T00:00:00Z"))
        self.store.append_promotion_run(row("legacy", 0.9, "2026-02-01T00:00:00Z"))
        with self.assertRaises(ContractError):
            self.store.reference_vector("v1", ["any-item"])

    def test_suite_mismatch_fails_closed(self) -> None:
        foreign = row("b1", 0.5, "2026-01-01T00:00:00Z", {"x": 0.9})
        foreign["suite_version"] = "v2"
        self.store.append_promotion_run(foreign)
        self.store.append_promotion_run({**foreign, "suite_version": "v2", "mean": 0.4})
        with self.assertRaises(ContractError):
            self.store.reference_vector("v1", ["x"])

    def test_duplicate_or_empty_item_ids_rejected(self) -> None:
        for bad in ([], ["x", "x"], [""]):
            with self.subTest(item_ids=bad), self.assertRaises(ContractError):
                self.store.reference_vector("v1", bad)

    def test_non_finite_item_values_rejected_at_ingest_and_read(self) -> None:
        for bad in ({"x": float("nan")}, {"x": float("inf")}, {"x": "0.9"}, {"": 1.0}):
            with self.subTest(item_results=bad), self.assertRaises(ContractError):
                self.store.append_promotion_run(row("b", 0.5, "2026-01-01T00:00:00Z", bad))

    def test_mutated_store_line_changes_resolution(self) -> None:
        self.store.append_promotion_run(row("b1", 0.5, "2026-01-01T00:00:00Z", {"x": 0.4}))
        self.store.append_promotion_run(row("b1", 0.6, "2026-02-01T00:00:00Z", {"x": 0.45}))
        before = self.store.reference_vector("v1", ["x"])
        lines = self.store.path.read_text(encoding="utf-8").splitlines()
        mutated = [line.replace('"x": 0.45', '"x": 0.46') if '"x": 0.45' in line else line for line in lines]
        self.store.path.write_text("\n".join(mutated) + "\n", encoding="utf-8", newline="\n")
        after = self.store.reference_vector("v1", ["x"])
        self.assertNotEqual(before["reference_vector_hash"], after["reference_vector_hash"])

    def test_vector_order_follows_request_and_feeds_paired_gate(self) -> None:
        self.store.append_promotion_run(row("b1", 0.5, "2026-01-01T00:00:00Z", {"a": 0.9, "b": 0.7}))
        self.store.append_promotion_run(row("b1", 0.6, "2026-02-01T00:00:00Z", {"a": 0.8, "b": 0.75}))
        forward = self.store.reference_vector("v1", ["a", "b"])
        reverse = self.store.reference_vector("v1", ["b", "a"])
        self.assertEqual(forward["values"], [0.8, 0.75])
        self.assertEqual(reverse["values"], [0.75, 0.8])
        margins = GateMargins(0.1, 0.05, 0.05, "2026-08-20T00:00:00Z", "operator")
        eval_run = EvaluationRun("eval-001", "2026-08-20T01:00:00Z", "v1", "a" * 64)
        result = paired_gate(["a", "b"], [1.0, 1.0], [0.8, 0.8], [0.95, 0.95], forward["values"], margins, eval_run, tail="two-sided")
        self.assertTrue(result["passed"])


if __name__ == "__main__":
    unittest.main()
