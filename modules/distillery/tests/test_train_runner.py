from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from distillery.common import ContractError, sha256_value
from runstate import RunStateEngine
from train.runner import (
    FIXTURE_EVIDENCE_CLASS,
    FixtureBackend,
    RealBackendAdapter,
    TrainingRunControlPlane,
    assert_measured_evidence,
    pinned_student,
    preflight_trainer,
)

ROOT = Path(__file__).resolve().parents[1]
TRAINER_REGISTRY = ROOT / "registry" / "grounded" / "trainer.json"
STUDENTS_REGISTRY = ROOT / "registry" / "grounded" / "students.json"
AUTH = {"authority": "operator", "ref": "auth-record-1"}
CORPUS_SHA = sha256_value("sealed-corpus-bytes")
SPEC_SHA = sha256_value("experiment-spec-bytes")


class TrainerPreflightTests(unittest.TestCase):
    def test_unassigned_primary_blocks_canonical_compute_fail_closed(self) -> None:
        verdict = preflight_trainer(TRAINER_REGISTRY)
        self.assertEqual(verdict["status"], "BLOCKED_HARDWARE_CAPACITY")
        self.assertFalse(verdict["checks"]["primary_assigned"])
        self.assertEqual(verdict["hard_gate_hg3"], "BLOCKED_HARDWARE_CAPACITY")
        self.assertGreaterEqual(verdict["requirement"]["minimum_usable_vram_mib"], 24 * 1024)

    def test_real_adapter_refuses_without_qualified_trainer(self) -> None:
        backend = RealBackendAdapter(TRAINER_REGISTRY)
        with self.assertRaises(ContractError) as caught:
            backend.run(run_id="x")
        self.assertIn("BLOCKED_HARDWARE_CAPACITY", str(caught.exception))

    def test_dev_machine_is_never_an_eligible_canonical_fallback(self) -> None:
        registry = json.loads(TRAINER_REGISTRY.read_text(encoding="utf-8"))
        development = next(row for row in registry["records"] if row["trainer_id"] == "GND-DEV-EXEC-01")
        self.assertFalse(development["canonical_primary_trainer"])
        self.assertFalse(development["canonical_fp16_hg3_capable"])
        verdict = preflight_trainer(TRAINER_REGISTRY)
        self.assertNotEqual(verdict["status"], "PASS")

    def test_assigned_primary_with_sufficient_measured_vram_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = json.loads(TRAINER_REGISTRY.read_text(encoding="utf-8"))
            primary = next(row for row in registry["records"] if row["trainer_id"] == "GND-TRAINER-PRIMARY")
            primary.update(
                {
                    "status": "ASSIGNED",
                    "measured": {"gpu_model": "QUALIFYING-GPU", "usable_vram_gib": 32},
                    "canonical_fp16_hg3_capable": True,
                }
            )
            path = Path(directory) / "trainer.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            verdict = preflight_trainer(path)
            self.assertEqual(verdict["status"], "PASS")

    def test_assigned_primary_below_vram_floor_still_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = json.loads(TRAINER_REGISTRY.read_text(encoding="utf-8"))
            primary = next(row for row in registry["records"] if row["trainer_id"] == "GND-TRAINER-PRIMARY")
            primary.update(
                {
                    "status": "ASSIGNED",
                    "measured": {"gpu_model": "SMALL-GPU", "usable_vram_gib": 8},
                    "canonical_fp16_hg3_capable": False,
                }
            )
            path = Path(directory) / "trainer.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            verdict = preflight_trainer(path)
            self.assertEqual(verdict["status"], "BLOCKED_HARDWARE_CAPACITY")
            self.assertTrue(verdict["checks"]["primary_assigned"])
            self.assertFalse(verdict["checks"]["usable_vram_meets_minimum"])


class FixtureBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.backend = FixtureBackend(self.tmp.name)

    def _student(self) -> dict:
        return pinned_student(STUDENTS_REGISTRY, "GND-STUDENT-4B")

    def test_fixture_run_is_deterministic_and_labeled_synthetic(self) -> None:
        first = self.backend.run(run_id="r1", student=self._student(), corpus_sha256=CORPUS_SHA, experiment_spec_hash=SPEC_SHA, seed="s")
        second = self.backend.run(run_id="r1", student=self._student(), corpus_sha256=CORPUS_SHA, experiment_spec_hash=SPEC_SHA, seed="s")
        self.assertEqual(first["candidate_hash"], second["candidate_hash"])
        self.assertEqual(
            {key: value for key, value in first.items() if key != "recorded_at"},
            {key: value for key, value in second.items() if key != "recorded_at"},
        )
        self.assertIsInstance(first["recorded_at"], str)
        self.assertEqual(first["evidence_class"], FIXTURE_EVIDENCE_CLASS)
        self.assertIn("SYNTHETIC", first["warning"])

    def test_different_seed_changes_candidate(self) -> None:
        first = self.backend.run(run_id="r1", student=self._student(), corpus_sha256=CORPUS_SHA, experiment_spec_hash=SPEC_SHA, seed="a")
        second = self.backend.run(run_id="r1", student=self._student(), corpus_sha256=CORPUS_SHA, experiment_spec_hash=SPEC_SHA, seed="b")
        self.assertNotEqual(first["candidate_id"], second["candidate_id"])

    def test_fixture_evidence_mechanically_rejected_for_measured_slots(self) -> None:
        fixture_record = self.backend.run(run_id="r1", student=self._student(), corpus_sha256=CORPUS_SHA, experiment_spec_hash=SPEC_SHA, seed="s")
        with self.assertRaises(ContractError):
            assert_measured_evidence(fixture_record, context="promotion gate")
        with self.assertRaises(ContractError):
            assert_measured_evidence({"evidence_class": "UNVERIFIED"}, context="promotion gate")


class ControlPlaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine = RunStateEngine(Path(self.tmp.name) / "runs")
        self.control_plane = TrainingRunControlPlane(self.engine, FixtureBackend(Path(self.tmp.name) / "artifacts"), TRAINER_REGISTRY)

    def test_blocked_run_stops_at_preflight_when_no_trainer(self) -> None:
        result = self.control_plane.execute(
            run_id="run-blocked",
            student_id="GND-STUDENT-4B",
            students_registry_path=STUDENTS_REGISTRY,
            corpus_sha256=CORPUS_SHA,
            experiment_spec_hash=SPEC_SHA,
            authorization=AUTH,
        )
        self.assertEqual(result["status"], "BLOCKED")
        record = self.engine.load("run-blocked")
        self.assertEqual(record["terminal_state"], "BLOCKED")
        self.assertEqual(record["last_successful_boundary"], "CREATED")

    def test_full_fixture_path_with_preflight_override_reaches_promotion_ready_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = json.loads(TRAINER_REGISTRY.read_text(encoding="utf-8"))
            primary = next(row for row in registry["records"] if row["trainer_id"] == "GND-TRAINER-PRIMARY")
            primary.update(
                {
                    "status": "ASSIGNED",
                    "measured": {"gpu_model": "QUALIFYING-GPU", "usable_vram_gib": 32},
                    "canonical_fp16_hg3_capable": True,
                }
            )
            registry_path = Path(directory) / "trainer.json"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            control_plane = TrainingRunControlPlane(self.engine, FixtureBackend(Path(self.tmp.name) / "artifacts"), registry_path)
            result = control_plane.execute(
                run_id="run-fixture",
                student_id="GND-STUDENT-4B",
                students_registry_path=STUDENTS_REGISTRY,
                corpus_sha256=CORPUS_SHA,
                experiment_spec_hash=SPEC_SHA,
                authorization=AUTH,
            )
            self.assertEqual(result["stage"], "PROMOTION_READY")
            self.assertEqual(result["candidate"]["evidence_class"], FIXTURE_EVIDENCE_CLASS)
            self.assertEqual(result["promotion_eligibility"], "FORBIDDEN_WITHOUT_MEASURED_EVIDENCE_AND_HUMAN_AUTHORITY")
            with self.assertRaises(ContractError):
                assert_measured_evidence(result["candidate"], context="HG-7 measured gate")

    def test_corpus_or_spec_drift_detected_on_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = json.loads(TRAINER_REGISTRY.read_text(encoding="utf-8"))
            primary = next(row for row in registry["records"] if row["trainer_id"] == "GND-TRAINER-PRIMARY")
            primary.update({"status": "ASSIGNED", "measured": {"gpu_model": "QUALIFYING-GPU", "usable_vram_gib": 32}, "canonical_fp16_hg3_capable": True})
            registry_path = Path(directory) / "trainer.json"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            control_plane = TrainingRunControlPlane(self.engine, FixtureBackend(Path(self.tmp.name) / "artifacts"), registry_path)
            control_plane.execute(
                run_id="run-drift",
                student_id="GND-STUDENT-8B",
                students_registry_path=STUDENTS_REGISTRY,
                corpus_sha256=CORPUS_SHA,
                experiment_spec_hash=SPEC_SHA,
                authorization=AUTH,
            )
            drifted = CORPUS_SHA + "x"
            with self.assertRaises(ContractError):
                self.engine.resume(
                    "run-drift",
                    expected_input_hashes={
                        "student_upstream_repo": "Qwen/Qwen3-8B-Base",
                        "student_revision": "49e3418fbbbca6ecbdf9608b4d22e5a407081db4",
                        "student_snapshot_status": "NOT_ACQUIRED",
                        "corpus_sha256": drifted,
                        "experiment_spec_hash": SPEC_SHA,
                    },
                )

    def test_unknown_student_and_missing_authorization_fail(self) -> None:
        with self.assertRaises(ContractError):
            pinned_student(STUDENTS_REGISTRY, "GND-STUDENT-UNKNOWN")
        with self.assertRaises(ContractError):
            self.control_plane.execute(
                run_id="run-noauth",
                student_id="GND-STUDENT-4B",
                students_registry_path=STUDENTS_REGISTRY,
                corpus_sha256=CORPUS_SHA,
                experiment_spec_hash=SPEC_SHA,
                authorization={"authority": "", "ref": ""},
            )


if __name__ == "__main__":
    unittest.main()
