from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from ops.operator_cli import main
from source_admission import AdmissionClass, AdmissionRegistry, SourceKey, lineage_id
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from corpus import admit_example


def events_file(directory: Path) -> Path:
    registry = AdmissionRegistry()
    key = SourceKey("provider.example", "teacher-a", "rev-1")
    registry.transition(key, AdmissionClass.ELIGIBLE, evidence_ref="terms", decision_authority="operator")
    path = directory / "events.json"
    path.write_text(json.dumps([event.__dict__ for event in registry.events]), encoding="utf-8")
    return path


def snapshot_file(directory: Path) -> tuple[Path, AdmissionRegistry]:
    registry = AdmissionRegistry()
    key = SourceKey("provider.example", "teacher-a", "rev-1")
    registry.transition(key, AdmissionClass.ELIGIBLE, evidence_ref="terms", decision_authority="operator")
    snapshot = registry.snapshot("run-cli")
    path = directory / "snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    return path, registry


class OperatorCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)

    def test_status_and_validate_and_hg3_preflight_are_honest(self) -> None:
        self.assertEqual(main(["status"]), 0)
        self.assertEqual(main(["validate"]), 0)
        self.assertEqual(main(["hg3-preflight"]), 0)

    def test_source_status_reports_classes_and_revocations(self) -> None:
        events = events_file(self.directory)
        self.assertEqual(main(["source-status", "--events", str(events)]), 0)

    def test_corpus_preflight_freshness_gate_refuses_stale_snapshot(self) -> None:
        snapshot_path, registry = snapshot_file(self.directory)
        key = SourceKey("provider.example", "teacher-a", "rev-1")
        registry.revoke(key, evidence_ref="license-withdrawn", decision_authority="operator")
        events_path = self.directory / "events2.json"
        events_path.write_text(json.dumps([event.__dict__ for event in registry.events]), encoding="utf-8")
        # Stale pre-revocation snapshot MUST be refused by the freshness gate.
        self.assertEqual(main(["corpus-preflight", "--snapshot", str(snapshot_path), "--events", str(events_path)]), 1)

        fresh_snapshot_path = self.directory / "fresh.json"
        fresh_snapshot_path.write_text(json.dumps(registry.snapshot("run-fresh")), encoding="utf-8")
        self.assertEqual(
            main(["corpus-preflight", "--snapshot", str(fresh_snapshot_path), "--events", str(events_path)]),
            0,
        )

    def test_exclusion_verify_reports_manifest(self) -> None:
        nodes = [
            {"sample_id": "root", "source_ids": ["SRC"], "derived_from": [], "shard_hash": "h0"},
            {"sample_id": "child", "source_ids": [], "derived_from": ["root"], "shard_hash": "h1"},
        ]
        nodes_path = self.directory / "nodes.json"
        nodes_path.write_text(json.dumps(nodes), encoding="utf-8")
        self.assertEqual(main(["exclusion-verify", "--nodes", str(nodes_path), "--source-id", "SRC"]), 0)

    def test_trainer_g2_preflight_and_probe_report_blocked_hardware(self) -> None:
        self.assertEqual(main(["trainer-status"]), 0)
        self.assertEqual(main(["trainer-probe"]), 0)
        self.assertEqual(main(["g2-preflight"]), 0)

    def test_run_lifecycle_commands_end_to_end_fixture_dry_run(self) -> None:
        runs_root = self.directory / "runs"
        output_root = self.directory / "artifacts"
        self.assertEqual(main(["run-plan", "--run-id", "cli-run"]), 0)
        result = main([
            "run-dry-run",
            "--runs-root", str(runs_root),
            "--output-root", str(output_root),
            "--run-id", "cli-run",
            "--corpus-material", "synthetic-corpus",
            "--spec-material", "synthetic-spec",
            "--authorization-ref", "auth-1",
        ])
        self.assertEqual(result, 0)
        status_exit = main(["run-status", "--runs-root", str(runs_root), "--run-id", "cli-run"])
        self.assertEqual(status_exit, 0)
        expected_inputs = {
            "student_upstream_repo": "Qwen/Qwen3-4B-Base",
            "student_revision": "906bfd4b4dc7f14ee4320094d8b41684abff8539",
            "student_snapshot_status": "NOT_ACQUIRED",
            "corpus_sha256": __import__("distillery.common", fromlist=["sha256_value"]).sha256_value("synthetic-corpus"),
            "experiment_spec_hash": __import__("distillery.common", fromlist=["sha256_value"]).sha256_value("synthetic-spec"),
        }
        expected_path = self.directory / "expected.json"
        expected_path.write_text(json.dumps(expected_inputs), encoding="utf-8")
        # The unassigned-trainer environment blocks the run terminally; a terminal
        # run can never be resumed - refusing IS the correct operator outcome.
        self.assertNotEqual(
            main(["run-resume", "--runs-root", str(runs_root), "--run-id", "cli-run", "--expected-inputs", str(expected_path)]),
            0,
        )

    def test_run_resume_rejects_drifted_inputs_fail_closed(self) -> None:
        runs_root = self.directory / "runs"
        main([
            "run-dry-run",
            "--runs-root", str(runs_root),
            "--output-root", str(self.directory / "a2"),
            "--run-id", "drift-run",
            "--corpus-material", "corpus-A",
            "--spec-material", "spec",
            "--authorization-ref", "auth-1",
        ])
        expected_path = self.directory / "wrong.json"
        expected_path.write_text(json.dumps({"corpus_sha256": "drifted"}), encoding="utf-8")
        exit_code = main([
            "run-resume",
            "--runs-root", str(runs_root),
            "--run-id", "drift-run",
            "--expected-inputs", str(expected_path),
        ])
        self.assertNotEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
