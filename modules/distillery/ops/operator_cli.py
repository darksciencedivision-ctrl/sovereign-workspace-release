from __future__ import annotations

"""Operator CLI - one coherent deterministic surface over the governed subsystems.

There is deliberately NO generic --force: governance cannot be bypassed from
the operator surface. Fail-closed refusals (for example an unassigned trainer)
exit 0 because refusing IS the correct outcome; they are visible in the
structured status fields.
"""

import argparse
import json
import sys
from pathlib import Path

from distillery.common import ContractError, sha256_value
from distillery.identity import resolve_identity
from exclusion import exclude
from source_admission import (
    AdmissionClass,
    AdmissionEvent,
    AdmissionRegistry,
    SourceKey,
    lineage_id,
)
from source_admission.d9 import FORBIDDEN_AUTHORITY_SENTINELS
from corpus import admit_example, verify_corpus_admission_record, verify_snapshot_integrity
from train.runner import assert_measured_evidence, pinned_student, preflight_trainer
from runstate import STAGES, RunStateEngine

ROOT = Path(__file__).resolve().parents[1]
TRAINER_REGISTRY = ROOT / "registry" / "grounded" / "trainer.json"
STUDENTS_REGISTRY = ROOT / "registry" / "grounded" / "students.json"
HG3_CURRENT = ROOT / "runs" / "HG-3" / "CURRENT_STATUS.json"


def _emit(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))


def _load_json(path: Path) -> dict | list:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ContractError(f"file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in {path}: {exc}") from None


def _rebuild_registry(events_path: Path) -> AdmissionRegistry:
    rows = _load_json(events_path)
    if not isinstance(rows, list):
        raise ContractError("admission events file must be a JSON array of admission events")
    return AdmissionRegistry(AdmissionEvent(**row) for row in rows)


def cmd_status(_args: argparse.Namespace) -> int:
    payload = {"identity": resolve_identity()}
    try:
        current = _load_json(HG3_CURRENT)
        payload["hg3_current_status"] = current.get("status")
    except ContractError:
        payload["hg3_current_status"] = "UNKNOWN_NO_CANONICAL_RECORD"
    trainer = _load_json(TRAINER_REGISTRY)
    payload["hg3_hard_gate"] = trainer["hard_gate"]["HG-3"]
    # F-136(12): a missing GND-TRAINER-PRIMARY record must not crash the CLI with StopIteration.
    primary = next((row for row in trainer["records"] if row["trainer_id"] == "GND-TRAINER-PRIMARY"), None)
    if primary is None:
        payload["primary_trainer"] = {"status": "ABSENT_NO_PRIMARY_TRAINER_RECORD", "gpu_model": None}
    else:
        payload["primary_trainer"] = {"status": primary["status"], "gpu_model": primary.get("measured", {}).get("gpu_model")}
    loop_state_path = ROOT / "runs" / "completion-loop" / "LOOP_STATE.json"
    payload["completion_loop_state_present"] = loop_state_path.is_file()
    _emit(payload)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    problems = []
    for schema_path in sorted((ROOT / "schema").glob("*.json")):
        try:
            _load_json(schema_path)
        except ContractError as exc:
            problems.append(str(exc))
    for registry_path in (TRAINER_REGISTRY, STUDENTS_REGISTRY):
        try:
            _load_json(registry_path)
        except ContractError as exc:
            problems.append(str(exc))
    for student_id in ("GND-STUDENT-4B", "GND-STUDENT-8B"):
        try:
            pinned_student(STUDENTS_REGISTRY, student_id)
        except ContractError as exc:
            problems.append(str(exc))
    payload = {"status": "PASS" if not problems else "FAIL", "problems": problems}
    _emit(payload)
    return 0 if not problems else 1


def cmd_source_status(args: argparse.Namespace) -> int:
    registry = _rebuild_registry(args.events)
    keys = {
        SourceKey(event.provider, event.teacher_or_model_id, event.revision)
        for event in registry.events
    }
    payload = {
        "sources": [
            {
                "lineage_id": lineage_id(key),
                "use_class": registry.current(key).value,
            }
            for key in sorted(keys)
        ],
        "revoked_source_ids": sorted(lineage_id(key) for key in registry.revoked_keys()),
    }
    _emit(payload)
    return 0


def cmd_corpus_preflight(args: argparse.Namespace) -> int:
    snapshot = _load_json(args.snapshot)
    verify_snapshot_integrity(snapshot)
    registry = _rebuild_registry(args.events)
    from source_admission import assert_snapshot_matches_registry

    assert_snapshot_matches_registry(snapshot, registry)
    payload = {"status": "FRESH_AND_INTEGRITY_VERIFIED"}
    if args.example:
        example = _load_json(args.example)
        record = admit_example(example, snapshot, client_scope=args.client_scope, admission_registry=registry)
        payload["scrub_dry_run"] = {
            "redactions_applied": record["redactions_applied"],
            "categories": sorted({finding["category"] for finding in record["scan_findings"]}),
            "retention": record["retention"],
        }
    _emit(payload)
    return 0


def cmd_exclusion_verify(args: argparse.Namespace) -> int:
    nodes = _load_json(args.nodes)
    manifest = exclude(args.source_id, nodes, lineage_snapshot_hash=sha256_value(nodes))
    _emit(
        {
            "status": "VERIFIED",
            "excluded_sample_count": len(manifest["excluded_sample_ids"]),
            "remaining_sample_count": len(manifest["remaining_sample_ids"]),
            "manifest_hash": manifest["manifest_hash"],
        }
    )
    return 0


def cmd_trainer_status(_args: argparse.Namespace) -> int:
    _emit(_load_json(TRAINER_REGISTRY))
    return 0


def cmd_trainer_probe(args: argparse.Namespace) -> int:
    verdict = preflight_trainer(args.registry or TRAINER_REGISTRY)
    _emit(verdict)
    return 0


def cmd_hg3_preflight(_args: argparse.Namespace) -> int:
    verdict = preflight_trainer(TRAINER_REGISTRY)
    students = [pinned_student(STUDENTS_REGISTRY, sid)["student_id"] for sid in ("GND-STUDENT-4B", "GND-STUDENT-8B")]
    _emit({"preflight": verdict, "pinned_students": students})
    return 0


def cmd_g2_preflight(_args: argparse.Namespace) -> int:
    verdict = preflight_trainer(TRAINER_REGISTRY)
    work_items_present = (ROOT / "docs" / "G2_WORK_ITEMS.md").is_file()
    _emit(
        {
            "status": "NOT_EXECUTED",
            "reason": "real G2 workload execution requires prerequisites that remain external",
            "work_items_document_present": work_items_present,
            "trainer_preflight": verdict["status"],
        }
    )
    return 0


def cmd_run_plan(args: argparse.Namespace) -> int:
    _emit({"run_id": args.run_id, "stages": list(STAGES), "note": "plan only; no state was created"})
    return 0


def cmd_run_status(args: argparse.Namespace) -> int:
    engine = RunStateEngine(args.runs_root)
    _emit(engine.load(args.run_id))
    return 0


def cmd_run_resume(args: argparse.Namespace) -> int:
    engine = RunStateEngine(args.runs_root)
    expected = _load_json(args.expected_inputs)
    required = args.required_artifact or []
    record = engine.resume(args.run_id, expected_input_hashes=expected, required_artifacts=tuple(required))
    _emit({"status": "RESUMABLE", "stage": record["stage"], "retry_count": record["retry_count"]})
    return 0


def cmd_run_dry_run(args: argparse.Namespace) -> int:
    from train.runner import FixtureBackend, RealBackendAdapter, TrainingRunControlPlane

    engine = RunStateEngine(args.runs_root)
    control_plane = TrainingRunControlPlane(engine, FixtureBackend(args.output_root), TRAINER_REGISTRY)
    result = control_plane.execute(
        run_id=args.run_id,
        student_id=args.student_id,
        students_registry_path=STUDENTS_REGISTRY,
        corpus_sha256=sha256_value(args.corpus_material),
        experiment_spec_hash=sha256_value(args.spec_material),
        authorization={"authority": "operator-cli-dry-run", "ref": args.authorization_ref},
    )
    real_refusal = None
    try:
        RealBackendAdapter(TRAINER_REGISTRY).run(run_id="probe")
    except ContractError as exc:
        real_refusal = str(exc)
    result["real_backend_refusal"] = real_refusal
    _emit(result)
    return 0


def cmd_evidence_verify(args: argparse.Namespace) -> int:
    record = _load_json(args.record)
    if set(record.keys()) >= {"source_lineage", "deletion_lineage_ids"} and "scan_findings" in record:
        verify_corpus_admission_record(record)
        result = {"status": "CORPUS_ADMISSION_RECORD_VALID"}
    else:
        result = {"status": "NOT_RECOGNIZED_AS_CORPUS_RECORD"}
    if args.require_measured:
        assert_measured_evidence(record, context="operator evidence verification")
        result["measured_evidence"] = True
    _emit(result)
    return 0


def cmd_candidate_status(args: argparse.Namespace) -> int:
    record = _load_json(args.record)
    payload = {
        "candidate_id": record.get("candidate_id"),
        "evidence_class": record.get("evidence_class"),
        "promotion_eligible": False,
        "reason": "promotion requires measured evidence and explicit human authority (never automatic)",
    }
    try:
        assert_measured_evidence(record, context="candidate promotion check")
        payload["promotion_eligible"] = None
        payload["reason"] = "measured evidence present; promotion still requires finalized gates and human decision"
    except ContractError as exc:
        payload["blocker"] = str(exc)
    _emit(payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="distillery", description="Sovereign x Grounded Distillery operator surface")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("status").set_defaults(func=cmd_status)
    commands.add_parser("validate").set_defaults(func=cmd_validate)

    source_status = commands.add_parser("source-status")
    source_status.add_argument("--events", type=Path, required=True)
    source_status.set_defaults(func=cmd_source_status)

    corpus_preflight = commands.add_parser("corpus-preflight")
    corpus_preflight.add_argument("--snapshot", type=Path, required=True)
    corpus_preflight.add_argument("--events", type=Path, required=True)
    corpus_preflight.add_argument("--example", type=Path)
    corpus_preflight.add_argument("--client-scope", default="CLIENT_A")
    corpus_preflight.set_defaults(func=cmd_corpus_preflight)

    exclusion_verify = commands.add_parser("exclusion-verify")
    exclusion_verify.add_argument("--nodes", type=Path, required=True)
    exclusion_verify.add_argument("--source-id", required=True)
    exclusion_verify.set_defaults(func=cmd_exclusion_verify)

    commands.add_parser("trainer-status").set_defaults(func=cmd_trainer_status)
    trainer_probe = commands.add_parser("trainer-probe")
    trainer_probe.add_argument("--registry", type=Path, default=None)
    trainer_probe.set_defaults(func=cmd_trainer_probe)
    commands.add_parser("hg3-preflight").set_defaults(func=cmd_hg3_preflight)
    commands.add_parser("g2-preflight").set_defaults(func=cmd_g2_preflight)

    run_plan = commands.add_parser("run-plan")
    run_plan.add_argument("--run-id", required=True)
    run_plan.set_defaults(func=cmd_run_plan)
    run_status = commands.add_parser("run-status")
    run_status.add_argument("--runs-root", type=Path, required=True)
    run_status.add_argument("--run-id", required=True)
    run_status.set_defaults(func=cmd_run_status)
    run_resume = commands.add_parser("run-resume")
    run_resume.add_argument("--runs-root", type=Path, required=True)
    run_resume.add_argument("--run-id", required=True)
    run_resume.add_argument("--expected-inputs", type=Path, required=True)
    run_resume.add_argument("--required-artifact", action="append", default=[])
    run_resume.set_defaults(func=cmd_run_resume)

    dry_run = commands.add_parser("run-dry-run")
    dry_run.add_argument("--runs-root", type=Path, required=True)
    dry_run.add_argument("--output-root", type=Path, required=True)
    dry_run.add_argument("--run-id", required=True)
    dry_run.add_argument("--student-id", default="GND-STUDENT-4B")
    dry_run.add_argument("--corpus-material", required=True)
    dry_run.add_argument("--spec-material", required=True)
    dry_run.add_argument("--authorization-ref", required=True)
    dry_run.set_defaults(func=cmd_run_dry_run)

    evidence_verify = commands.add_parser("evidence-verify")
    evidence_verify.add_argument("--record", type=Path, required=True)
    evidence_verify.add_argument("--require-measured", action="store_true")
    evidence_verify.set_defaults(func=cmd_evidence_verify)

    candidate_status = commands.add_parser("candidate-status")
    candidate_status.add_argument("--record", type=Path, required=True)
    candidate_status.set_defaults(func=cmd_candidate_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ContractError as exc:
        _emit({"status": "REFUSED_FAIL_CLOSED", "error": str(exc)})
        return 0 if any(token in str(exc) for token in ("BLOCKED_HARDWARE_CAPACITY", "not admitted", "unsigned")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
