from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from distillery.common import ContractError
from exclusion import e7_acceptance, exclude
from grounded.harness_adapters import import_turn_record
from grounded.telemetry import TraceStore, run_g0_probes


class ExclusionAndTelemetryTests(unittest.TestCase):
    def test_e7(self) -> None:
        result = e7_acceptance()
        self.assertTrue(result["passed"], result)

    def test_exclusion_rejects_dangling_edges(self) -> None:
        with self.assertRaises(ContractError):
            exclude("missing", [{"sample_id": "child", "derived_from": ["missing"], "shard_hash": "s"}], lineage_snapshot_hash="snapshot")

    def test_g0_acceptance_probes(self) -> None:
        result = run_g0_probes()
        self.assertTrue(result["passed"], result)
        self.assertEqual(set(result["assertions"]), {"G0-A", "G0-B", "G0-C", "G0-D"})

    def test_event_log_replays_and_outcome_is_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "events.jsonl"
            store = TraceStore(log)
            store.start("s", harness="h", provider="p", model_id="m", revision="r")
            store.turn("s", "1", content_hash="0" * 64)
            store.success("s")
            self.assertEqual(TraceStore(log).get("s")["outcome"], "success")
            with self.assertRaises(ContractError):
                store.fail("s")

    def test_sovereign_adapter_copies_no_content(self) -> None:
        record = {
            "session_id": "session", "turn": 1, "model": "qwen:test", "status": "completed",
            "prompt_sha256": "1" * 64, "output_sha256": "2" * 64,
            "prompt": "PRIVATE_PROMPT_VALUE", "output": "PRIVATE_OUTPUT_VALUE",
            "telemetry": {"reported_model": "qwen:test"},
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "turn.json"
            source.write_text(json.dumps(record), encoding="utf-8")
            log = Path(directory) / "events.jsonl"
            store = TraceStore(log)
            imported = import_turn_record(source, store)
            self.assertFalse(imported["content_copied"])
            self.assertFalse(imported["duplicate_ignored"])
            self.assertTrue(import_turn_record(source, store)["duplicate_ignored"])
            persisted = log.read_text(encoding="utf-8")
            self.assertNotIn("PRIVATE_PROMPT_VALUE", persisted)
            self.assertNotIn("PRIVATE_OUTPUT_VALUE", persisted)


if __name__ == "__main__":
    unittest.main()
