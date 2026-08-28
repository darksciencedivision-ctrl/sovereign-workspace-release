from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from curation import seal_shard
from distillery.common import ContractError, sha256_value
from grounded.curation import mine_ch1, screen_volatile_facts
from source_admission import AdmissionClass, AdmissionRegistry, SourceKey, assert_admitted
from validators import code_vs_tests, exact_answer, structured_output


class SourceAndShardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = SourceKey("provider", "teacher", "r1")
        self.registry = AdmissionRegistry()

    def test_unknown_is_default_and_fails_closed(self) -> None:
        self.assertEqual(self.registry.current(self.key), AdmissionClass.UNKNOWN)
        for classification in ("UNKNOWN", "REJECTED"):
            with self.subTest(classification=classification), self.assertRaises(ContractError):
                assert_admitted(classification)

    def test_state_machine_and_snapshot_are_append_only(self) -> None:
        self.registry.transition(self.key, AdmissionClass.INTERNAL_ONLY, evidence_ref="terms/1", decision_authority="operator")
        with self.assertRaises(ContractError):
            assert_admitted("INTERNAL_ONLY")
        assert_admitted("INTERNAL_ONLY", internal_use_authorized=True)
        self.registry.transition(self.key, AdmissionClass.ELIGIBLE, evidence_ref="terms/2", decision_authority="operator")
        self.assertEqual(self.registry.snapshot("run-1"), self.registry.snapshot("run-1"))
        with self.assertRaises(ContractError):
            self.registry.transition(self.key, AdmissionClass.UNKNOWN, evidence_ref="x", decision_authority="operator")

    def _sample(self, client: str = "CLIENT_A", use_class: str = "ELIGIBLE") -> dict:
        content = {"messages": [{"role": "user", "content": "x"}]}
        return {
            "sample_id": "sample-1", "source_trace_id": "trace-1", "content": content,
            "content_hash": sha256_value(content), "channel": "CH1", "harness": "local",
            "provider": "provider", "teacher_of_record": "teacher", "source_revision": "r1",
            "source_admission_class": use_class, "generation_depth": 0, "seed_trace_ids": [],
            "seed_ref": None, "derived_from": [], "validator_results": [], "labels": {"outcome": "success"},
            "client_tag": client, "trace_fit_version": "fit-v1", "normalizer_version": "norm-v1",
            "created_at": "2026-08-20T00:00:00Z",
        }

    def test_shard_seal_hash_and_immutability(self) -> None:
        self.registry.transition(self.key, AdmissionClass.ELIGIBLE, evidence_ref="terms", decision_authority="operator")
        with tempfile.TemporaryDirectory() as directory:
            first = seal_shard([self._sample()], directory, self.registry.snapshot("run"))
            second = seal_shard([self._sample()], directory, self.registry.snapshot("run"))
            self.assertEqual(first, second)
            manifest = json.loads((Path(directory) / first["shard_hash"] / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["payload_hash"], first["payload_hash"])

    def test_shard_rejects_multi_client_and_snapshot_forgery(self) -> None:
        self.registry.transition(self.key, AdmissionClass.ELIGIBLE, evidence_ref="terms", decision_authority="operator")
        second = self._sample("CLIENT_B")
        second["sample_id"] = "sample-2"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ContractError):
                seal_shard([self._sample(), second], directory, self.registry.snapshot("run"))
            with self.assertRaises(ContractError):
                seal_shard([self._sample(use_class="INTERNAL_ONLY")], directory, self.registry.snapshot("run"), internal_use_authorized=True)

    def test_miner_preserves_recovery_but_masks_failed_turn(self) -> None:
        trace = {"trace_id": "t", "outcome": "success", "source_admission_class": "ELIGIBLE", "turns": [
            {"id": "1", "tool_status": "failed"},
            {"id": "2", "recovery": True, "tool_status": "passed"},
            {"id": "3", "superseded": True},
        ]}
        mined = mine_ch1(trace)
        self.assertEqual([turn["id"] for turn in mined["turns"]], ["2"])
        self.assertTrue(mined["recovery_arc_preserved"])

    def test_ch_m_volatile_fact_is_retrieval_only(self) -> None:
        screened = screen_volatile_facts({"channel": "CH-M", "frequently_changing_fact": True})
        self.assertTrue(screened["prefer_lookup"])
        self.assertEqual(screened["training_weight"], 0.0)

    def test_deterministic_validators_share_result_contract(self) -> None:
        self.assertTrue(code_vs_tests(compile_exit=0, test_exit=0, tests_collected=2).passed)
        self.assertFalse(code_vs_tests(compile_exit=0, test_exit=1, tests_collected=2).passed)
        self.assertTrue(exact_answer({"a": 1}, {"a": 1}).passed)
        schema = {"type": "object", "required": ["x"], "additionalProperties": False, "properties": {"x": {"type": "integer"}}}
        self.assertTrue(structured_output('{"x": 1}', schema).passed)
        self.assertFalse(structured_output('{"x": "1"}', schema).passed)


if __name__ == "__main__":
    unittest.main()
