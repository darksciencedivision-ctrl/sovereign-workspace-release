from __future__ import annotations

"""F-16 end-to-end deterministic dry run: paths A through I.

Composes ONLY real governed modules - no mocks beyond the directive-mandated
FixtureBackend. No path here can satisfy a measured model gate: every fixture
artifact is SYNTHETIC_FIXTURE_ONLY labeled and mechanically rejected wherever
measured evidence is required.
"""

import json
import tempfile
import unittest
from pathlib import Path

from corpus import admit_example
from curation import seal_shard
from distillery.common import ContractError, sha256_value, utc_now
from exclusion import exclude
from gate.capability import CapabilityLedger
from gate.historical import HistoricalBestStore
from gate.paired import EvaluationRun, GateMargins, paired_gate
from ops.bundle import assemble_bundle, verify_bundle
from runstate import RunStateEngine
from source_admission import AdmissionClass, AdmissionRegistry, SourceKey
from train.card_lock import TrainerCardLock
from train.runner import (
    FIXTURE_EVIDENCE_CLASS,
    FixtureBackend,
    TrainingRunControlPlane,
    assert_measured_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
STUDENTS_REGISTRY = ROOT / "registry" / "grounded" / "students.json"
AUTH = {"authority": "operator", "ref": "auth-record-1"}
ITEMS = ["item-1", "item-2", "item-3"]
SUITE_VERSION = "suite-v1"


def qualifying_trainer_registry(directory: Path) -> Path:
    registry = json.loads((ROOT / "registry" / "grounded" / "trainer.json").read_text(encoding="utf-8"))
    primary = next(row for row in registry["records"] if row["trainer_id"] == "GND-TRAINER-PRIMARY")
    primary.update(
        {
            "status": "ASSIGNED",
            "measured": {"gpu_model": "QUALIFYING-GPU", "usable_vram_gib": 32},
            "canonical_fp16_hg3_capable": True,
        }
    )
    path = directory / "trainer.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    return path


class EndToEndDryRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)

        registry = AdmissionRegistry()
        key = SourceKey("provider.example", "teacher-a", "rev-1")
        registry.transition(key, AdmissionClass.ELIGIBLE, evidence_ref="terms-v1", decision_authority="operator")
        self.registry = registry
        self.key = key

        snapshot = registry.snapshot("e2e-run")
        example = {
            "sample_id": "sample-e2e-1",
            "content": "Recovery procedure: rotate the key sk-synthetic000000000000000000 then rerun the failing test.",
            "channel": "CH1",
            "provider": key.provider,
            "teacher_of_record": key.teacher_or_model_id,
            "source_revision": key.revision,
            "client_tag": "CLIENT_A",
            "created_at": utc_now(),
        }
        self.corpus_record = admit_example(example, snapshot, client_scope="CLIENT_A", admission_registry=registry)
        self.shard_manifest = seal_shard(
            [
                {
                    "sample_id": example["sample_id"],
                    "source_trace_id": "trace-1",
                    "content": example["content"],
                    "content_hash": sha256_value(example["content"]),
                    "channel": "CH1",
                    "harness": "h",
                    "provider": key.provider,
                    "teacher_of_record": key.teacher_or_model_id,
                    "source_revision": key.revision,
                    "source_admission_class": "ELIGIBLE",
                    "generation_depth": 0,
                    "seed_trace_ids": [],
                    "seed_ref": None,
                    "derived_from": [],
                    "validator_results": {},
                    "labels": {},
                    "client_tag": "CLIENT_A",
                    "trace_fit_version": "1",
                    "normalizer_version": "1",
                    "created_at": example["created_at"],
                }
            ],
            self.directory / "shards",
            snapshot,
        )
        nodes = [
            {"sample_id": example["sample_id"], "source_ids": [f"{key.provider}:{key.teacher_or_model_id}:{key.revision}"], "derived_from": [], "shard_hash": self.shard_manifest["shard_hash"]},
            {"sample_id": "derived-sample", "source_ids": [], "derived_from": [example["sample_id"]], "shard_hash": "derived-shard"},
        ]
        self.exclusion_manifest = exclude(
            f"{key.provider}:{key.teacher_or_model_id}:{key.revision}",
            nodes,
            lineage_snapshot_hash=sha256_value(nodes),
        )
        self.engine = RunStateEngine(self.directory / "runs")

    # ------------------------------------------------------------------ PATH A
    def test_path_a_qualifying_fixture_candidate_stops_before_promotion(self) -> None:
        control_plane = TrainingRunControlPlane(
            self.engine,
            FixtureBackend(self.directory / "artifacts"),
            qualifying_trainer_registry(self.directory),
        )
        corpus_sha = sha256_value("sealed-corpus-bytes")
        spec_sha = sha256_value("spec-bytes")
        result = control_plane.execute(
            run_id="path-a",
            student_id="GND-STUDENT-4B",
            students_registry_path=STUDENTS_REGISTRY,
            corpus_sha256=corpus_sha,
            experiment_spec_hash=spec_sha,
            authorization=AUTH,
        )
        self.assertEqual(result["stage"], "PROMOTION_READY")
        candidate = result["candidate"]
        self.assertEqual(candidate["evidence_class"], FIXTURE_EVIDENCE_CLASS)

        store = HistoricalBestStore(self.directory / "historical.jsonl")
        store.append_promotion_run(
            {
                "suite_version": SUITE_VERSION,
                "n": 3,
                "mean": 0.5,
                "dispersion": 0.02,
                "ci_metadata": {"tail": "two-sided", "confidence": 0.95},
                "promotion_time": utc_now(),
                "bundle_id": "prior-bundle",
                "item_results": {"item-1": 0.5, "item-2": 0.5, "item-3": 0.5},
            }
        )
        store.append_promotion_run(
            {
                "suite_version": SUITE_VERSION,
                "n": 3,
                "mean": 0.52,
                "dispersion": 0.02,
                "ci_metadata": {"tail": "two-sided", "confidence": 0.95},
                "promotion_time": utc_now(),
                "bundle_id": "prior-bundle",
                "item_results": {"item-1": 0.52, "item-2": 0.51, "item-3": 0.53},
            }
        )
        target_reference = store.reference_vector(SUITE_VERSION, ITEMS)["values"]
        margins = GateMargins(0.01, 0.05, 0.05, margins_declared_at="2026-01-01T00:00:00.000000Z", margin_authority="operator")
        eval_run = EvaluationRun("eval-path-a", "2026-01-01T00:00:00.000001Z", SUITE_VERSION, sha256_value(SUITE_VERSION))
        verdict = paired_gate(
            ITEMS,
            candidate=[0.56, 0.57, 0.58],
            target_reference=target_reference,
            parent=target_reference,
            historical_best=target_reference,
            margins=margins,
            eval_run=eval_run,
            tail="lower-one-sided",
            confidence=0.95,
        )
        self.assertTrue(verdict["passed"])

        ledger = CapabilityLedger()
        ledger.register(capability_id="CAP-E2E", description="e2e fixture capability", criticality="CRITICAL", evaluation_suite=SUITE_VERSION)
        ledger.record_evaluation("CAP-E2E", score=verdict["comparisons"]["target"]["lcb"], checkpoint_ref=candidate["candidate_id"])
        gate_verdict = ledger.check_promotion_gate({"CAP-E2E": 0.55})
        self.assertTrue(gate_verdict.passed)

        component_dir = self.directory / "components"
        component_dir.mkdir(parents=True, exist_ok=True)
        component_paths = {}
        for component in ("retrieval", "model", "memory", "tool_schemas", "serving", "quantization", "system_prompt"):
            component_file = component_dir / component
            component_file.write_text("synthetic-fixture-component:" + component, encoding="utf-8")
            component_paths[component] = str(component_file)
        bundle = assemble_bundle("1.1.0rc3", component_paths, self.directory / "bundle")
        verify_bundle(bundle)
        evidence = json.dumps({"run": result["run_id"], "shard": self.shard_manifest["shard_hash"]}, sort_keys=True)
        with self.assertRaises(ContractError):
            assert_measured_evidence(candidate, context="HG-7 measured bundle gate")
        self.assertLess(len(evidence), 4096)

    # ------------------------------------------------------------------ PATH B
    def test_path_b_rejecting_candidate_is_a_successful_test(self) -> None:
        store = HistoricalBestStore(self.directory / "hist-b.jsonl")
        store.append_promotion_run(
            {
                "suite_version": SUITE_VERSION, "n": 3, "mean": 0.5, "dispersion": 0.005,
                "ci_metadata": {"tail": "two-sided", "confidence": 0.95},
                "promotion_time": utc_now(), "bundle_id": "b", 
                "item_results": {i: 0.9 for i in ITEMS},
            }
        )
        store.append_promotion_run(
            {
                "suite_version": SUITE_VERSION, "n": 3, "mean": 0.91, "dispersion": 0.005,
                "ci_metadata": {"tail": "two-sided", "confidence": 0.95},
                "promotion_time": utc_now(), "bundle_id": "b",
                "item_results": {i: 0.91 for i in ITEMS},
            }
        )
        reference = store.reference_vector(SUITE_VERSION, ITEMS)["values"]
        margins = GateMargins(0.01, 0.05, 0.05, margins_declared_at="2026-01-01T00:00:00.000000Z", margin_authority="operator")
        eval_run = EvaluationRun("eval-b", "2026-01-01T00:00:00.000001Z", SUITE_VERSION, sha256_value("b"))
        verdict = paired_gate(
            ITEMS, candidate=[0.90, 0.90, 0.90], target_reference=reference, parent=reference,
            historical_best=reference, margins=margins, eval_run=eval_run, tail="lower-one-sided",
        )
        self.assertFalse(verdict["passed"])

    # ------------------------------------------------------------------ PATH C
    def test_path_c_crash_and_resume_mid_pipeline(self) -> None:
        engine = RunStateEngine(self.directory / "runs-c")
        engine.create("path-c", input_hashes={"corpus": "abc"}, authorization=AUTH)
        while engine.load("path-c")["stage"] != "TRAINING":
            engine.advance("path-c")
        resumed = engine.resume("path-c", expected_input_hashes={"corpus": "abc"})
        self.assertEqual(resumed["stage"], "TRAINING")

    # ------------------------------------------------------------------ PATH D
    def test_path_d_revoked_source_stops_corpus_admission(self) -> None:
        stale = self.registry.snapshot("pre-revocation")
        self.registry.revoke(self.key, evidence_ref="license-withdrawn", decision_authority="operator")
        fresh = self.registry.snapshot("post-revocation")
        example = {
            "sample_id": "s", "content": "clean durable procedure text",
            "provider": self.key.provider, "teacher_of_record": self.key.teacher_or_model_id,
            "source_revision": self.key.revision, "client_tag": "CLIENT_A", "created_at": utc_now(),
        }
        with self.assertRaises(ContractError):
            admit_example(example, stale, client_scope="CLIENT_A", admission_registry=self.registry)
        with self.assertRaises(ContractError):
            admit_example(example, fresh, client_scope="CLIENT_A", admission_registry=self.registry)

    # ------------------------------------------------------------------ PATH E
    def test_path_e_frankensteined_historical_vector_rejected(self) -> None:
        store = HistoricalBestStore(self.directory / "hist-e.jsonl")
        store.append_promotion_run(
            {
                "suite_version": SUITE_VERSION, "n": 2, "mean": 0.5, "dispersion": 0.01,
                "ci_metadata": {}, "promotion_time": utc_now(), "bundle_id": "only-run",
                "item_results": {"item-1": 0.5, "item-2": 0.6},
            }
        )
        with self.assertRaises(ContractError):
            store.reference_vector(SUITE_VERSION, ["item-1", "item-3"])

    # ------------------------------------------------------------------ PATH F
    def test_path_f_altered_sealed_corpus_rejected_on_resume(self) -> None:
        engine = RunStateEngine(self.directory / "runs-f")
        control_plane = TrainingRunControlPlane(engine, FixtureBackend(self.directory / "a-f"), qualifying_trainer_registry(self.directory))
        control_plane.execute(
            run_id="path-f", student_id="GND-STUDENT-4B", students_registry_path=STUDENTS_REGISTRY,
            corpus_sha256="cafe" * 16, experiment_spec_hash="beef" * 16, authorization=AUTH,
        )
        with self.assertRaises(ContractError):
            engine.resume("path-f", expected_input_hashes={"student_upstream_repo": "Qwen/Qwen3-4B-Base", "student_revision": "906bfd4b4dc7f14ee4320094d8b41684abff8539", "student_snapshot_status": "NOT_ACQUIRED", "corpus_sha256": "dead" * 16, "experiment_spec_hash": "beef" * 16})

    # ------------------------------------------------------------------ PATH G
    def test_path_g_trainer_identity_change_rejected_by_card_lock(self) -> None:
        lock_path = self.directory / "card.lock"
        good = TrainerCardLock(
            lock_path, expected_gpu="gfx-correct", minimum_free_vram_mib=1000,
            probe=lambda: {"gpu_identity": "gfx-correct", "free_vram_mib": 2000, "conflicting_compute_processes": []},
            drain_serving=lambda: None, restore_serving=lambda: None,
        )
        with good:
            changed = TrainerCardLock(
                lock_path, expected_gpu="gfx-correct", minimum_free_vram_mib=1000,
                probe=lambda: {"gpu_identity": "gfx-WRONG", "free_vram_mib": 2000, "conflicting_compute_processes": []},
                drain_serving=lambda: None, restore_serving=lambda: None,
            )
            with self.assertRaises(ContractError):
                with changed:
                    pass

    # ------------------------------------------------------------------ PATH H
    def test_path_h_late_margin_declaration_rejected(self) -> None:
        started = utc_now()
        late = utc_now()
        margins = GateMargins(0.01, 0.05, 0.05, margins_declared_at=late, margin_authority="operator")
        eval_run = EvaluationRun("eval-h", started, SUITE_VERSION, sha256_value("h"))
        store = HistoricalBestStore(self.directory / "hist-h.jsonl")
        store.append_promotion_run(
            {
                "suite_version": SUITE_VERSION, "n": 3, "mean": 0.5, "dispersion": 0.005,
                "ci_metadata": {}, "promotion_time": utc_now(), "bundle_id": "h",
                "item_results": {i: 0.5 for i in ITEMS},
            }
        )
        store.append_promotion_run(
            {
                "suite_version": SUITE_VERSION, "n": 3, "mean": 0.51, "dispersion": 0.005,
                "ci_metadata": {}, "promotion_time": utc_now(), "bundle_id": "h",
                "item_results": {i: 0.51 for i in ITEMS},
            }
        )
        reference = store.reference_vector(SUITE_VERSION, ITEMS)["values"]
        with self.assertRaises(ContractError):
            paired_gate(
                ITEMS, candidate=[0.51] * 3, target_reference=reference, parent=reference,
                historical_best=reference, margins=margins, eval_run=eval_run, tail="lower-one-sided",
            )

    # ------------------------------------------------------------------ PATH I
    def test_path_i_malformed_evidence_rejected(self) -> None:
        tampered = {**self.corpus_record, "redactions_applied": 999}
        from corpus import verify_corpus_admission_record

        with self.assertRaises(ContractError):
            verify_corpus_admission_record(tampered)
        with self.assertRaises(ContractError):
            assert_measured_evidence({"evidence_class": "SYNTHETIC_FIXTURE_ONLY"}, context="HG-7")


if __name__ == "__main__":
    unittest.main()
