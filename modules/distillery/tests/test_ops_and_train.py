from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from distillery.common import ContractError
from gate.experiment_db import ExperimentDB, REQUIRED_ROW_FIELDS
from ops import PromotionRouter, ShadowPlanner, assemble_bundle, verify_bundle
from train import TrainerCardLock


def build_bundle(root: Path, name: str) -> dict:
    components = {}
    for component in ("model", "quantization", "system_prompt", "tool_schemas", "retrieval", "memory", "serving"):
        path = root / name / f"{component}.cfg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{name}:{component}\n", encoding="utf-8")
        components[component] = path
    return assemble_bundle(name, components, root / "bundles")


class OpsAndTrainTests(unittest.TestCase):
    def test_exact_bundle_and_mutation_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = build_bundle(root, "v1")
            self.assertTrue(verify_bundle(bundle))
            Path(bundle["components"]["retrieval"]["path"]).write_text("mutated", encoding="utf-8")
            with self.assertRaises(ContractError):
                verify_bundle(bundle)

    def test_promotion_requires_human_and_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prior, candidate = build_bundle(root, "prior"), build_bundle(root, "candidate")
            router_path = root / "router.json"
            router_path.write_text(json.dumps({"bundle": prior, "promoted_at": "before", "authority": "operator"}), encoding="utf-8")
            router = PromotionRouter(router_path)
            hg7 = {"finalized": True, "passed": True, "bundle_hash": candidate["bundle_hash"]}
            with self.assertRaises(ContractError):
                router.promote(candidate, hg7_evidence=hg7, human_decision={"decision": "PROMOTE"}, readiness_check=lambda _: True)
            with self.assertRaises(ContractError):
                router.promote(candidate, hg7_evidence=hg7, human_decision={"decision": "PROMOTE", "authority": "human-op"}, readiness_check=lambda _: False)
            self.assertEqual(router.current()["bundle"]["bundle_hash"], prior["bundle_hash"])

    def test_successful_promotion_and_write_failure_states(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prior, candidate = build_bundle(root, "prior"), build_bundle(root, "candidate")
            router_path = root / "router.json"
            router_path.write_text(json.dumps({"bundle": prior, "promoted_at": "before", "authority": "operator"}), encoding="utf-8")
            router = PromotionRouter(router_path)
            hg7 = {"finalized": True, "passed": True, "bundle_hash": candidate["bundle_hash"]}
            with self.assertRaises(ContractError):
                router.promote(candidate, hg7_evidence=hg7, human_decision={"decision": "PROMOTE", "authority": "human-op"}, readiness_check=lambda _: True)
            self.assertEqual(router.current()["bundle"]["bundle_hash"], prior["bundle_hash"])
            with mock.patch.object(router, "_atomic_write", side_effect=OSError("candidate write failed")):
                failed = router.rollback({"bundle": prior, "promoted_at": "before", "authority": "operator"})
            self.assertEqual(failed["status"], "ROLLBACK_FAILED")
            self.assertEqual(failed["exception"]["type"], "OSError")

    def test_rollback_write_failure_is_terminal_and_prior_is_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prior, candidate = build_bundle(root, "prior"), build_bundle(root, "candidate")
            router_path = root / "router.json"
            router_path.write_text(json.dumps({"bundle": candidate, "promoted_at": "before", "authority": "operator"}), encoding="utf-8")
            router = PromotionRouter(router_path)
            with mock.patch.object(router, "_atomic_write", side_effect=OSError("rollback media failure")):
                result = router.rollback({"bundle": prior, "promoted_at": "before", "authority": "operator"})
            self.assertEqual(result["status"], "ROLLBACK_FAILED")
            self.assertEqual(result["prior"]["bundle"]["bundle_hash"], prior["bundle_hash"])
            self.assertEqual(router.current()["bundle"]["bundle_hash"], candidate["bundle_hash"])
            recovered = router.rollback({"bundle": prior, "promoted_at": "before", "authority": "operator"})
            self.assertEqual(recovered["status"], "ROLLED_BACK")
            self.assertEqual(router.current()["bundle"]["bundle_hash"], prior["bundle_hash"])

    def test_corrupted_router_read_is_classified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            router_path = Path(directory) / "router.json"
            router_path.write_text("{not-json", encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "unreadable or corrupted"):
                PromotionRouter(router_path).current()

    def test_router_fsync_precedes_closed_file_replace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prior = build_bundle(root, "prior")
            router_path = root / "router.json"
            router_path.write_text(json.dumps({"bundle": prior, "promoted_at": "before", "authority": "operator"}), encoding="utf-8")
            router = PromotionRouter(router_path)
            events = []
            real_replace = __import__("os").replace

            def observed_fsync(_fd):
                events.append("fsync")

            def observed_replace(source, destination):
                events.append("replace")
                real_replace(source, destination)

            with mock.patch("ops.promotion.os.fsync", side_effect=observed_fsync), mock.patch("ops.promotion.os.replace", side_effect=observed_replace):
                router._atomic_write({"bundle": prior, "promoted_at": "again", "authority": "operator"})
            self.assertEqual(events, ["fsync", "replace"])

    def test_shadow_has_no_execute_surface(self) -> None:
        shadow = ShadowPlanner()
        self.assertFalse(hasattr(shadow, "execute"))
        self.assertFalse(shadow.plan_diff([], [])["mutating_execution_available"])

    def test_trainer_lock_validates_identity_and_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "card.lock"
            events = []
            probe = lambda: {"gpu_identity": "gfx906", "free_vram_mib": 32000, "conflicting_compute_processes": []}
            with TrainerCardLock(lock_path, expected_gpu="gfx906", minimum_free_vram_mib=30000, probe=probe, drain_serving=lambda: events.append("drain"), restore_serving=lambda: events.append("restore")):
                self.assertTrue(lock_path.exists())
            self.assertEqual(events, ["drain", "restore"])
            bad_probe = lambda: {"gpu_identity": "other", "free_vram_mib": 32000, "conflicting_compute_processes": []}
            with self.assertRaises(ContractError):
                with TrainerCardLock(lock_path, expected_gpu="gfx906", minimum_free_vram_mib=1, probe=bad_probe, drain_serving=lambda: None, restore_serving=lambda: None):
                    pass

    def test_experiment_db_refuses_incomplete_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db = ExperimentDB(Path(directory) / "experiments.sqlite")
            with self.assertRaises(ContractError):
                db.complete("run", {})
            complete = {name: {} for name in REQUIRED_ROW_FIELDS}
            db.complete("run", complete)
            self.assertEqual(db.get("run"), complete)
            with self.assertRaises(ContractError):
                db.complete("run", complete)


if __name__ == "__main__":
    unittest.main()
