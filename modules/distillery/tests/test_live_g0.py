from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from distillery.common import ContractError, sha256_value
from grounded.g0_live import reevaluate_hg0, run_live_acceptance
from grounded.monitoring import file_sha256, validate_instrumentation_baseline, verify_instrumentation_checksums
from grounded.telemetry import TraceStore


class LiveG0Tests(unittest.TestCase):
    def _write(self, path: Path, value: dict) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_imported_records_are_content_free_but_do_not_complete_hg0(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            success_paths = []
            for turn in (1, 2):
                success_paths.append(self._write(root / f"success-{turn}.json", {
                    "session_id": "success-source", "execution_id": "execution", "turn": turn,
                    "model": f"model-{turn}", "status": "completed", "role": f"role-{turn}",
                    "prompt_sha256": str(turn) * 64, "output_sha256": str(turn + 2) * 64,
                    "telemetry": {"reported_model": f"model-{turn}"},
                }))
            failure = self._write(root / "failure.json", {"session_id": "failure-source", "status": "timeout", "route": "deep", "model": "model-f", "answer": "PRIVATE_FAILURE", "telemetry": {"reported_model": "model-f", "failure_type": "timeout"}})
            recovery_failure = self._write(root / "recovery-failure.json", {"session_id": "recovery-source", "status": "cancelled", "route": "deep", "answer": "PRIVATE_CANCELLED", "telemetry": {"failure_type": "cancelled"}})
            recovery_success = self._write(root / "recovery-success.json", {"session_id": "recovery-source", "status": "accepted", "accepted": True, "route": "quick", "model": "model-r", "answer": "PRIVATE_READY", "telemetry": {"reported_model": "model-r"}})
            component = root / "instrumentation.py"
            component.write_text("stable\n", encoding="utf-8")
            event_log = root / "events.jsonl"
            result = run_live_acceptance(
                success_turn_paths=success_paths,
                failure_result_path=failure,
                recovery_failure_result_path=recovery_failure,
                recovery_success_result_path=recovery_success,
                no_trace_source_id="no-trace-source",
                store=TraceStore(event_log),
                expected_checksums={"component": file_sha256(component)},
                component_paths={"component": component},
            )
            self.assertEqual(result["hg0"], "LIMITED_PENDING_LIVE_OPERATOR_MARKS", result)
            self.assertFalse(result["assertions"]["G0-A"])
            self.assertFalse(result["assertions"]["G0-B"])
            self.assertTrue(all(value for key, value in result["assertions"].items() if key not in {"G0-A", "G0-B"}))
            self.assertEqual(result["label_origins"]["success"], "import_time_classification")
            self.assertEqual(result["label_origins"]["failure"], "import_time_classification")
            self.assertFalse(result["hashed_event_manifest"]["content_payload_present"])
            self.assertTrue(all(event["content_payload_present"] is False for event in result["hashed_event_manifest"]["events"]))
            fixture_alert = next(item for item in result["active_alerts"] if item["code"] == "NO_TRACE")
            self.assertTrue(fixture_alert["fixture"])
            persisted = event_log.read_text(encoding="utf-8")
            for private in ("PRIVATE_FAILURE", "PRIVATE_CANCELLED", "PRIVATE_READY", "success-source", "failure-source", "recovery-source"):
                self.assertNotIn(private, persisted)

    def test_checksum_guard_detects_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            component = Path(directory) / "hook.py"
            component.write_text("first", encoding="utf-8")
            expected = file_sha256(component)
            component.write_text("mutated", encoding="utf-8")
            result = verify_instrumentation_checksums({"hook": expected}, {"hook": component})
            self.assertFalse(result["passed"])
            self.assertEqual(result["components"]["hook"]["change_classification"], "TAMPER_OR_UNREVIEWED_CHANGE")

    def test_label_origin_is_required_and_manifest_is_hashed(self) -> None:
        store = TraceStore()
        session_id = "PRIVATE_SESSION_IDENTIFIER_123"
        store.start(session_id, harness="live", provider="provider", model_id="teacher", revision="r1", route="QUICK", recorded_at="2026-08-20T00:00:00Z")
        store.turn(session_id, "turn", content_hash="a" * 64, tool_status="passed")
        store.success(session_id)
        with self.assertRaises(ContractError):
            store.explicit_label(session_id, "success", label_origin="made_up")
        store.explicit_label(session_id, "success", label_origin="live_operator_mark")
        manifest = store.hashed_event_manifest()
        body = {key: value for key, value in manifest.items() if key != "manifest_hash"}
        self.assertEqual(manifest["manifest_hash"], sha256_value(body))
        for event in manifest["events"]:
            event_body = {key: value for key, value in event.items() if key != "event_id_hash"}
            self.assertEqual(event["event_id_hash"], sha256_value(event_body))
            self.assertEqual(event["route"], "QUICK")
        self.assertTrue(any(event["label_origin"] == "live_operator_mark" for event in manifest["events"]))
        self.assertNotIn(session_id, json.dumps(manifest))

    def test_checksum_baseline_requires_dirty_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            component = Path(directory) / "hook.py"
            component.write_text("stable", encoding="utf-8")
            baseline = {
                "runtime_repo_path": "runtime",
                "runtime_commit_sha": "a" * 40,
                "runtime_dirty": True,
                "dirty_file_list": [],
                "file_path": "hook.py",
                "sha256": file_sha256(component),
                "captured_at": "2026-08-20T00:00:00Z",
                "capture_authority": "operator",
            }
            with self.assertRaises(ContractError):
                verify_instrumentation_checksums({"hook": baseline}, {"hook": component})

    def test_canonical_checksum_registry_records_exact_dirty_runtime(self) -> None:
        root = Path(__file__).resolve().parents[1]
        registry = json.loads((root / "registry/instrumentation_checksums.json").read_text(encoding="utf-8"))
        dirty_lists = []
        for component, baseline in registry["components"].items():
            with self.subTest(component=component):
                validate_instrumentation_baseline(component, baseline)
                self.assertTrue(baseline["runtime_dirty"])
                self.assertEqual(len(baseline["dirty_file_list"]), 49)
                dirty_lists.append(baseline["dirty_file_list"])
        self.assertTrue(all(paths == dirty_lists[0] for paths in dirty_lists))

    def test_hg0_reevaluation_requires_real_marks_and_preserved_controls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            component = Path(directory) / "hook.py"
            component.write_text("stable", encoding="utf-8")
            store = TraceStore()
            store.start("live-success", harness="target", provider="local", model_id="teacher", revision="r1", route="QUICK")
            store.turn("live-success", "s1", content_hash="a" * 64, tool_status="passed")
            store.success("live-success")
            store.explicit_label("live-success", "success", label_origin="live_operator_mark")
            store.implicit_signal("live-success", "positive", "complete", evidence_hash="1" * 64)
            store.start("live-failure", harness="target", provider="local", model_id="teacher", revision="r1", route="DEEP")
            store.turn("live-failure", "f1", content_hash="b" * 64, tool_status="failed")
            store.fail("live-failure")
            store.explicit_label("live-failure", "fail", label_origin="live_operator_mark")
            store.implicit_signal("live-failure", "negative", "cancelled", evidence_hash="2" * 64)
            store.start("recovery", harness="target", provider="local", model_id="teacher", revision="r1", route="QUICK")
            store.turn("recovery", "r1", content_hash="c" * 64, tool_status="failed", superseded=True)
            store.turn("recovery", "r2", content_hash="d" * 64, tool_status="passed", recovery=True)
            store.success("recovery")
            store.explicit_label("recovery", "success", label_origin="import_time_classification")
            store.start("unknown", harness="target", provider="local", model_id="teacher", revision="r1", route="QUICK")
            store.turn("unknown", "u1", content_hash="e" * 64, tool_status="passed")
            store.success("unknown")
            store.explicit_label("unknown", "success", label_origin="import_time_classification")
            with self.assertRaises(ContractError):
                store.admit_for_corpus("unknown", "UNKNOWN")
            with self.assertRaises(ContractError):
                store.admit_as_seed("unknown", "UNKNOWN")
            store.start("fixture", harness="target", provider="local", model_id="teacher", revision="r1", fixture=True)
            result = reevaluate_hg0(
                store=store,
                success_session_id="live-success",
                failure_session_id="live-failure",
                expected_checksums={"hook": file_sha256(component)},
                component_paths={"hook": component},
            )
            self.assertEqual(result["hg0"], "PASS", result)
            self.assertTrue(all(result["assertions"].values()))
            self.assertEqual(result["live_success_evidence"]["label_path"], "/success")
            self.assertEqual(result["live_failure_evidence"]["label_path"], "/fail")
            self.assertEqual(result["live_failure_evidence"]["outcome"], "failure")
            self.assertTrue(all(event["content_payload_present"] is False for event in result["event_manifest"]["events"]))

    def test_canonical_live_manifest_is_content_free_and_row_verifiable(self) -> None:
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "runs/G0-live/hashed-event-manifest.json").read_text(encoding="utf-8"))
        rows = [json.loads(line) for line in (root / "runs/G0-live/event-manifest.jsonl").read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(manifest["schema_version"], "1.2")
        self.assertEqual(rows, manifest["events"])
        body = {key: value for key, value in manifest.items() if key != "manifest_hash"}
        self.assertEqual(manifest["manifest_hash"], sha256_value(body))
        for event in rows:
            with self.subTest(event_id_hash=event["event_id_hash"]):
                event_body = {key: value for key, value in event.items() if key != "event_id_hash"}
                self.assertEqual(event["event_id_hash"], sha256_value(event_body))
                self.assertFalse(event["content_payload_present"])
                self.assertIn("route", event)
        status = json.loads((root / "runs/G0-live/hg0-status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["hg0"], "PASS")
        self.assertTrue(all(status["assertions"].values()))
        tracked_evidence = json.dumps({"status": status, "events": rows})
        self.assertNotIn("hg0-live-success-", tracked_evidence)
        self.assertNotIn("hg0-live-failure-", tracked_evidence)


if __name__ == "__main__":
    unittest.main()
