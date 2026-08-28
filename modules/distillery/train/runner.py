from __future__ import annotations

import json
from pathlib import Path

from distillery.common import ContractError, sha256_value, utc_now
from runstate import STAGES, RunStateEngine

FIXTURE_EVIDENCE_CLASS = "SYNTHETIC_FIXTURE_ONLY"
MEASURED_EVIDENCE_CLASS = "MEASURED"
MINIMUM_USABLE_VRAM_MIB = 24 * 1024
PREFERRED_USABLE_VRAM_MIB = 32 * 1024


def load_trainer_registry(path: str | Path) -> dict:
    target = Path(path)
    try:
        registry = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ContractError(f"trainer registry not found: {target}") from None
    except json.JSONDecodeError as exc:
        raise ContractError(f"corrupt trainer registry {target}: {exc}") from None
    if "records" not in registry or "hard_gate" not in registry:
        raise ContractError("trainer registry missing records or hard_gate section")
    return registry


def preflight_trainer(registry_path: str | Path) -> dict:
    """Fail-closed trainer preflight for canonical compute.

    No qualified physical trainer designated means BLOCKED_HARDWARE_CAPACITY -
    which is SUCCESS for a fail-closed preflight. The development machine is
    never an eligible fallback for canonical FP16 HG-3 work.
    """
    registry = load_trainer_registry(registry_path)
    by_id = {row["trainer_id"]: row for row in registry["records"]}
    primary = by_id.get("GND-TRAINER-PRIMARY")
    checks = {
        "primary_assigned": bool(primary and primary.get("status") not in {None, "UNASSIGNED"}),
        "physical_identity_present": False,
        "usable_vram_meets_minimum": False,
        "canonical_fp16_capable": False,
        "dev_fallback_explicitly_refused": True,
    }
    if primary and primary.get("status") not in {None, "UNASSIGNED"}:
        measured = primary.get("measured") or {}
        checks["physical_identity_present"] = bool(measured.get("gpu_model"))
        vram_gib = measured.get("usable_vram_gib")
        checks["usable_vram_meets_minimum"] = isinstance(vram_gib, (int, float)) and vram_gib >= MINIMUM_USABLE_VRAM_MIB / 1024
        checks["canonical_fp16_capable"] = bool(primary.get("canonical_fp16_hg3_capable"))
    passed = all(checks.values())
    return {
        "status": "PASS" if passed else "BLOCKED_HARDWARE_CAPACITY",
        "checks": checks,
        "hard_gate_hg3": registry["hard_gate"].get("HG-3"),
        "requirement": {"minimum_usable_vram_mib": MINIMUM_USABLE_VRAM_MIB, "preferred_usable_vram_mib": PREFERRED_USABLE_VRAM_MIB},
        "evaluated_at": utc_now(),
        "evidence_class": MEASURED_EVIDENCE_CLASS,
    }


def assert_measured_evidence(record: dict, *, context: str) -> None:
    """Mechanically reject fixture-labeled evidence wherever measured proof is required."""
    evidence_class = record.get("evidence_class")
    if evidence_class == FIXTURE_EVIDENCE_CLASS or record.get("fixture") is True:
        raise ContractError(f"{context}: synthetic-fixture evidence cannot satisfy a measured-evidence requirement")
    if evidence_class != MEASURED_EVIDENCE_CLASS:
        raise ContractError(f"{context}: unknown evidence class {evidence_class!r} is not measurable proof")


def pinned_student(registry_path: str | Path, student_id: str) -> dict:
    registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    students = {row["student_id"]: row for row in registry.get("students", [])}
    student = students.get(student_id)
    if not student:
        raise ContractError(f"unknown student id: {student_id}")
    if student.get("status") != "PINNED_FOR_HG3":
        raise ContractError(f"student {student_id} is not pinned for training")
    return student


class FixtureBackend:
    """Deterministic no-compute training backend.

    Every artifact it emits carries SYNTHETIC_FIXTURE_ONLY and can therefore
    never be promoted into a measured-evidence slot.
    """

    def __init__(self, output_root: str | Path, *, now_fn=None) -> None:
        self.output_root = Path(output_root)
        from distillery.common import utc_now as _default_clock

        self._now = now_fn or _default_clock

    def run(self, *, run_id: str, student: dict, corpus_sha256: str, experiment_spec_hash: str, seed: str) -> dict:
        material = "|".join(
            [run_id, student["student_id"], student["upstream_repo"], student["revision"], corpus_sha256, experiment_spec_hash, seed]
        )
        candidate_id = "FIXTURE-" + sha256_value(material)[:16]
        checkpoint_hashes = [
            sha256_value({"candidate": candidate_id, "checkpoint": index, "kind": "SYNTHETIC_FIXTURE_ONLY"})
            for index in range(2)
        ]
        metrics = [
            {"step": step, "loss": round(1.0 / (step + 1), 6), "source": "deterministic_fixture"}
            for step in range(1, 4)
        ]
        record = {
            "candidate_id": candidate_id,
            "run_id": run_id,
            "student_id": student["student_id"],
            "evidence_class": FIXTURE_EVIDENCE_CLASS,
            "warning": "SYNTHETIC FIXTURE ONLY - NOT A MEASURED MODEL ARTIFACT",
            "output_dir": str(self.output_root / candidate_id),
            "checkpoint_refs": [
                {"ref": f"{candidate_id}/checkpoint-{index}", "sha256": digest}
                for index, digest in enumerate(checkpoint_hashes)
            ],
            "metric_records": metrics,
            "provenance": {
                "corpus_sha256": corpus_sha256,
                "experiment_spec_hash": experiment_spec_hash,
                "seed": seed,
                "backend": "FixtureBackend",
            },
            "failure_class": None,
        }
        record["recorded_at"] = self._now()
        record["candidate_hash"] = sha256_value(
            {key: value for key, value in record.items() if key not in {"candidate_hash", "recorded_at"}}
        )
        return record


class RealBackendAdapter:
    """Adapter to the canonical training implementation path.

    Canonical compute begins ONLY after preflight passes against the current
    trainer registry. Today that preflight fails closed with
    BLOCKED_HARDWARE_CAPACITY, so this adapter refuses every invocation.
    """

    def __init__(self, registry_path: str | Path) -> None:
        self.registry_path = registry_path

    def run(self, **kwargs) -> dict:
        verdict = preflight_trainer(self.registry_path)
        if verdict["status"] != "PASS":
            raise ContractError(
                f"canonical training refused: {verdict['status']} (hard_gate HG-3={verdict['hard_gate_hg3']})"
            )
        raise ContractError("canonical training path requires the qualified-trainer execution contract (not yet authorized)")


class TrainingRunControlPlane:
    """Drives one governed training run through the runstate semantic boundaries."""

    def __init__(self, engine: RunStateEngine, backend, trainer_registry_path: str | Path) -> None:
        self.engine = engine
        self.backend = backend
        self.trainer_registry_path = trainer_registry_path

    def _seal_inputs(self, student: dict, corpus_sha256: str, experiment_spec_hash: str) -> dict:
        return {
            "student_upstream_repo": student["upstream_repo"],
            "student_revision": student["revision"],
            "student_snapshot_status": student["snapshot"]["status"],
            "corpus_sha256": corpus_sha256,
            "experiment_spec_hash": experiment_spec_hash,
        }

    def execute(
        self,
        *,
        run_id: str,
        student_id: str,
        students_registry_path: str | Path,
        corpus_sha256: str,
        experiment_spec_hash: str,
        authorization: dict,
        seed: str = "fixture-seed",
    ) -> dict:
        student = pinned_student(students_registry_path, student_id)
        input_hashes = self._seal_inputs(student, corpus_sha256, experiment_spec_hash)
        record = self.engine.create(run_id, input_hashes=input_hashes, authorization=authorization)

        record = self.engine.advance(run_id, actor="preflight")
        verdict = preflight_trainer(self.trainer_registry_path)
        if verdict["status"] != "PASS":
            self.engine.block(run_id, reason=f"trainer preflight: {verdict['status']}")
            return {"run_id": run_id, "status": "BLOCKED", "preflight": verdict}

        record = self.engine.advance(run_id, actor="corpus")
        self.engine.attach_artifact(run_id, f"sealed-corpus:{corpus_sha256[:16]}", corpus_sha256)
        record = self.engine.advance(run_id, actor="trainer")
        record = self.engine.advance(run_id, actor="training")
        candidate = self.backend.run(
            run_id=run_id,
            student=student,
            corpus_sha256=corpus_sha256,
            experiment_spec_hash=experiment_spec_hash,
            seed=seed,
        )
        self.engine.attach_artifact(run_id, f"candidate:{candidate['candidate_id']}", candidate["candidate_hash"])
        record = self.engine.advance(run_id, actor="evaluating")
        record = self.engine.advance(run_id, actor="adjudicating")
        record = self.engine.advance(run_id, actor="packaging")
        record = self.engine.advance(run_id, actor="promotion_ready_fixture_stop")
        assert record["stage"] == "PROMOTION_READY"
        return {
            "run_id": run_id,
            "stage": record["stage"],
            "candidate": candidate,
            "promotion_eligibility": "FORBIDDEN_WITHOUT_MEASURED_EVIDENCE_AND_HUMAN_AUTHORITY",
            "evidence_class": FIXTURE_EVIDENCE_CLASS,
        }


__all__ = [
    "FIXTURE_EVIDENCE_CLASS",
    "MEASURED_EVIDENCE_CLASS",
    "MINIMUM_USABLE_VRAM_MIB",
    "PREFERRED_USABLE_VRAM_MIB",
    "preflight_trainer",
    "assert_measured_evidence",
    "pinned_student",
    "FixtureBackend",
    "RealBackendAdapter",
    "TrainingRunControlPlane",
]
