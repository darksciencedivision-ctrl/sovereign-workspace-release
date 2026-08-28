from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from distillery.common import ContractError, sha256_value
from runstate import DEFAULT_RETRY_BUDGET, STAGES, RunStateEngine

AUTH = {"authority": "operator", "ref": "auth-record-1"}


def inputs() -> dict:
    return {"corpus": sha256_value("corpus-bytes"), "spec": sha256_value("spec-bytes")}


class RunStateLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine = RunStateEngine(self.tmp.name)

    def _advance_to(self, run_id: str, stage: str) -> None:
        self.engine.create(run_id, input_hashes=inputs(), authorization=AUTH)
        while True:
            record = self.engine.load(run_id)
            if record["stage"] == stage:
                return
            if record["stage"] == "PROMOTION_READY":
                raise AssertionError("overshot target stage")
            self.engine.advance(run_id)

    def test_full_lifecycle_reaches_promotion_ready_then_completes(self) -> None:
        record = self.engine.create("run-full", input_hashes=inputs(), authorization=AUTH)
        self.assertEqual(record["stage"], "CREATED")
        for expected in STAGES[1:]:
            record = self.engine.advance("run-full")
            self.assertEqual(record["stage"], expected)
            if expected != "PROMOTION_READY":
                self.assertEqual(record["last_successful_boundary"], STAGES[STAGES.index(expected) - 1])
        completed = self.engine.complete("run-full")
        self.assertEqual(completed["terminal_state"], "COMPLETED")
        with self.assertRaises(ContractError):
            self.engine.advance("run-full")

    def test_stage_order_is_strictly_linear_no_skipping_or_rewind(self) -> None:
        self.engine.create("run-order", input_hashes=inputs(), authorization=AUTH)
        self.engine.advance("run-order")
        record = self.engine.load("run-order")
        self.assertEqual(record["stage"], "PREFLIGHT")
        tampered_path = Path(self.tmp.name) / "run-order" / "run_state.json"
        forged = json.loads(tampered_path.read_text(encoding="utf-8"))
        forged["stage"] = "PACKAGING"
        forged.pop("integrity_hash")
        tampered_path.write_text(json.dumps(forged), encoding="utf-8")
        with self.assertRaises(ContractError):
            self.engine.load("run-order")

    def test_crash_recovery_from_every_boundary(self) -> None:
        for boundary in STAGES[:-1]:
            with self.subTest(boundary=boundary):
                engine = RunStateEngine(self.tmp.name)
                run_id = f"crash-{boundary}"
                engine.create(run_id, input_hashes=inputs(), authorization=AUTH)
                while engine.load(run_id)["stage"] != boundary:
                    engine.advance(run_id)
                resumed = engine.resume(run_id, expected_input_hashes=inputs())
                self.assertEqual(resumed["stage"], boundary)

    def test_resume_rejects_identity_input_artifact_and_terminal_mismatches(self) -> None:
        self._advance_to("run-resume", "CORPUS_LOCKED")
        with self.assertRaises(ContractError):
            self.engine.resume("wrong-id", expected_input_hashes=inputs())
        with self.assertRaises(ContractError):
            self.engine.resume("run-resume", expected_input_hashes={"corpus": "drift"})
        self.engine.attach_artifact("run-resume", "shard-abc", sha256_value("shard"))
        resumed = self.engine.resume("run-resume", expected_input_hashes=inputs(), required_artifacts=("shard-abc",))
        self.assertEqual(resumed["artifact_refs"][0]["ref"], "shard-abc")
        with self.assertRaises(ContractError):
            self.engine.resume("run-resume", expected_input_hashes=inputs(), required_artifacts=("missing-shard",))
        self.engine.cancel("run-resume", actor="operator")
        with self.assertRaises(ContractError):
            self.engine.resume("run-resume", expected_input_hashes=inputs())

    def test_failure_classification_and_retry_budget_gate_training_resume(self) -> None:
        self._advance_to("run-retry", "TRAINING")
        self.engine.fail("run-retry", classification="HARDWARE", detail="vram shortfall")
        failed = self.engine.load("run-retry")
        self.assertEqual(failed["terminal_state"], "FAILED")
        self.assertEqual(failed["failure_classification"], "HARDWARE")
        self.assertEqual(failed["resume_pointer"], "TRAINER_LOCKED")
        with self.assertRaises(ContractError):
            self.engine.resume("run-retry", expected_input_hashes=inputs())

    def test_retry_budget_exhaustion_blocks_further_retries(self) -> None:
        self.engine.create("run-budget", input_hashes=inputs(), authorization=AUTH, retry_budget=2)
        self.engine.record_retry("run-budget", reason="transient")
        self.engine.record_retry("run-budget", reason="transient again")
        with self.assertRaises(ContractError):
            self.engine.record_retry("run-budget", reason="third")
        self.assertEqual(self.engine.load("run-budget")["retry_count"], 2)
        self.assertEqual(DEFAULT_RETRY_BUDGET, 3)

    def test_unknown_failure_class_and_missing_authority_fail(self) -> None:
        self.engine.create("run-fail", input_hashes=inputs(), authorization=AUTH)
        with self.assertRaises(ContractError):
            self.engine.fail("run-fail", classification="MADE_UP")
        with self.assertRaises(ContractError):
            self.engine.create("run-auth", input_hashes=inputs(), authorization={"authority": "", "ref": ""})
        with self.assertRaises(ContractError):
            self.engine.cancel("run-fail", actor="")

    def test_duplicate_run_and_block_semantics(self) -> None:
        self.engine.create("run-dup", input_hashes=inputs(), authorization=AUTH)
        with self.assertRaises(ContractError):
            self.engine.create("run-dup", input_hashes=inputs(), authorization=AUTH)
        self.engine.block("run-dup", reason="trainer unassigned")
        blocked = self.engine.load("run-dup")
        self.assertEqual(blocked["terminal_state"], "BLOCKED")
        with self.assertRaises(ContractError):
            self.engine.advance("run-dup")

    def test_complete_requires_promotion_ready_boundary(self) -> None:
        self.engine.create("run-early", input_hashes=inputs(), authorization=AUTH)
        with self.assertRaises(ContractError):
            self.engine.complete("run-early")


if __name__ == "__main__":
    unittest.main()
