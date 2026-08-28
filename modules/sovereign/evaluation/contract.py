from __future__ import annotations

import inspect
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from runtime_integrity.provenance_stamp import attach_canonical_provenance

try:
    from evaluation.contract_trace import trace_contract_status_from_mapping
    from evaluation.integrity import IntegrityGuard, IntegrityGuardError, IntegrityViolation
except ImportError:
    from contract_trace import trace_contract_status_from_mapping
    from integrity import IntegrityGuard, IntegrityGuardError, IntegrityViolation


VALID = "VALID"
DEGRADED = "DEGRADED"
INVALID = "INVALID"
CRITICAL_VIOLATION = "CRITICAL_VIOLATION"
FAILED_COGNITIVE = "FAILED_COGNITIVE_VALIDATION"

logger = logging.getLogger(__name__)

_MISSING = object()
_CLAIM_GROUPS = ("agreed_claims", "contested_claims", "one_sided_claims")
_THRESHOLD_PROFILE_FIELDS = (
    "CLAIM_AGREE_COSINE",
    "CLAIM_VARIANCE_COSINE",
    "CHALLENGE_ANSWER_COSINE",
)
_CRITICAL_STATE_FILES = ("quality_gate_result.json", "artifact_integrity_report.json")
_SESSION_CRITICAL_STATE_DIRS = ("quality_gate", "artifact_integrity")
_RUNTIME_SIGNAL_ROOT = Path("evaluation") / "verification" / "runtime_signals"
_RUNTIME_SIGNAL_FILENAME = "contract_executed.json"
_LIVE_RUNTIME_EXECUTION_MARKERS = {
    "cycle_runner_v3.py": "cycle_runner_v3.live_contract_enforcement",
    "live_orchestrator.py": "live_orchestrator.runtime_contract_enforcement",
}


def _is_string(value: Any) -> bool:
    return isinstance(value, str)


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_dict(value: Any) -> bool:
    return isinstance(value, dict)


def _is_list(value: Any) -> bool:
    return isinstance(value, list)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_integer(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return value.is_integer()
    return False


def _is_list_of_strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _timestamp_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _dedupe_strings(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _stable_path_key(base_dir: Path, path: Path) -> str:
    resolved = Path(path).expanduser().resolve(strict=False)
    try:
        return resolved.relative_to(base_dir).as_posix()
    except ValueError:
        return resolved.as_posix()


def _critical_state_keys(base_dir: Path, state_paths: list[Path]) -> list[str]:
    return [_stable_path_key(base_dir, path) for path in state_paths]


def _session_id_from_data(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    return str(data.get("session_id", "")).strip()


def _critical_state_paths(data: Any, guard: IntegrityGuard) -> list[Path]:
    state_root = guard.base_dir / "scheduler" / "state"
    paths = [state_root / filename for filename in _CRITICAL_STATE_FILES]

    session_id = _session_id_from_data(data)
    if session_id:
        for dirname in _SESSION_CRITICAL_STATE_DIRS:
            paths.append(state_root / dirname / f"{session_id}.json")

    unique_paths: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = path.resolve(strict=False)
        identity = str(resolved).casefold()
        if identity in seen:
            continue
        seen.add(identity)
        unique_paths.append(resolved)
    return unique_paths


def _capture_state_hashes(guard: IntegrityGuard, state_paths: list[Path]) -> dict[str, str | None]:
    return {
        _stable_path_key(guard.base_dir, path): guard.hash_file(path)
        for path in state_paths
    }


def _detect_protected_state_drift(
    guard: IntegrityGuard,
    state_paths: list[Path],
    pre_hashes: dict[str, str | None],
    post_hashes: dict[str, str | None],
) -> list[dict[str, Any]]:
    drift: list[dict[str, Any]] = []
    timestamp = _timestamp_utc()
    for path in state_paths:
        path_key = _stable_path_key(guard.base_dir, path)
        pre_hash = pre_hashes.get(path_key)
        post_hash = post_hashes.get(path_key)
        stable = guard.verify_state_atomic(pre_hash, path)
        if stable and pre_hash == post_hash:
            continue
        drift.append(
            {
                "violation_type": "STATE_DRIFT",
                "path": path_key,
                "protected_root": _stable_path_key(guard.base_dir, path.parent),
                "severity": "CRITICAL",
                "timestamp_utc": timestamp,
                "pre_hash": pre_hash,
                "post_hash": post_hash,
                "details": {
                    "summary": "Critical state file changed during contract validation.",
                    "expected_stable": True,
                },
            }
        )
    return drift


def _integrity_error_violation(phase: str, error: Exception) -> dict[str, Any]:
    return {
        "violation_type": "INTEGRITY_ERROR",
        "path": phase,
        "protected_root": "INTEGRITY_GUARD",
        "severity": "CRITICAL",
        "timestamp_utc": _timestamp_utc(),
        "details": {
            "summary": f"Integrity guard failed during {phase}.",
            "error": str(error),
            "expected_stable": True,
        },
    }


def _integrity_status_message(integrity_violations: list[dict[str, Any]], protected_state_drift: list[dict[str, Any]]) -> str:
    manifest_count = len(integrity_violations)
    drift_count = len(protected_state_drift)
    details: list[str] = []
    if manifest_count:
        noun = "violation" if manifest_count == 1 else "violations"
        details.append(f"{manifest_count} protected manifest {noun}")
    if drift_count:
        noun = "event" if drift_count == 1 else "events"
        details.append(f"{drift_count} critical state drift {noun}")
    detail_text = " and ".join(details) if details else "an integrity failure"
    return f"Artifact failed integrity validation during contract enforcement: {detail_text} detected."


def _integrity_violation_messages(
    integrity_violations: list[dict[str, Any]],
    protected_state_drift: list[dict[str, Any]],
) -> list[str]:
    messages: list[str] = []
    for violation in integrity_violations:
        violation_type = str(violation.get("violation_type", "VIOLATION")).strip()
        if violation_type == "INTEGRITY_ERROR":
            details = violation.get("details") if isinstance(violation, dict) else {}
            summary = str((details or {}).get("summary", "")).strip()
            messages.append(summary or "Integrity guard failed during contract enforcement.")
            continue
        path = str(violation.get("path", "")).strip()
        messages.append(f"integrity violation {violation_type}: {path}")
    for drift in protected_state_drift:
        path = str(drift.get("path", "")).strip()
        if path:
            messages.append(f"protected state drift: {path}")
    return _dedupe_strings(messages)


def _attach_integrity_results(
    report: dict[str, Any],
    *,
    base_dir: Path,
    validation_status: str,
    validation_message: str,
    validation_violations: list[str],
    state_paths: list[Path],
    pre_manifest: dict[str, str],
    post_manifest: dict[str, str],
    integrity_violations: list[dict[str, Any]],
    protected_state_drift: list[dict[str, Any]],
) -> dict[str, Any]:
    report["integrity_violations"] = integrity_violations
    report["protected_state_drift"] = protected_state_drift
    report["state_drift"] = bool(protected_state_drift)
    report["integrity_summary"] = {
        "status": CRITICAL_VIOLATION if integrity_violations or protected_state_drift else "PASS",
        "manifest_changed": bool(integrity_violations),
        "protected_state_stable": not protected_state_drift,
        "pre_manifest_entry_count": len(pre_manifest),
        "post_manifest_entry_count": len(post_manifest),
        "critical_state_file_count": len(state_paths),
        "critical_state_files_checked": _critical_state_keys(base_dir, state_paths),
        "integrity_violation_count": len(integrity_violations),
        "protected_state_drift_count": len(protected_state_drift),
        "validation_contract_status": validation_status,
        "validation_contract_message": validation_message,
        "validation_contract_violations": list(validation_violations),
    }

    if integrity_violations or protected_state_drift:
        integrity_message = _integrity_status_message(integrity_violations, protected_state_drift)
        report["contract_status"] = CRITICAL_VIOLATION
        report["contract_message"] = integrity_message
        report["contract_violations"] = _dedupe_strings(
            [*report["contract_violations"], integrity_message, *_integrity_violation_messages(integrity_violations, protected_state_drift)]
        )

    return report


def _attach_integrity_error(
    report: dict[str, Any],
    *,
    base_dir: Path,
    phase: str,
    error: Exception,
    validation_status: str,
    validation_message: str,
    validation_violations: list[str],
    state_paths: list[Path],
    pre_manifest: dict[str, str] | None = None,
    post_manifest: dict[str, str] | None = None,
) -> dict[str, Any]:
    integrity_violation = _integrity_error_violation(phase, error)
    error_message = f"Integrity guard failed during contract enforcement ({phase}): {error}"

    report["integrity_violations"] = [integrity_violation]
    report["protected_state_drift"] = []
    report["state_drift"] = False
    report["integrity_summary"] = {
        "status": CRITICAL_VIOLATION,
        "manifest_changed": False,
        "protected_state_stable": False,
        "pre_manifest_entry_count": len(pre_manifest or {}),
        "post_manifest_entry_count": len(post_manifest or {}),
        "critical_state_file_count": len(state_paths),
        "critical_state_files_checked": _critical_state_keys(base_dir, state_paths),
        "integrity_violation_count": 1,
        "protected_state_drift_count": 0,
        "validation_contract_status": validation_status,
        "validation_contract_message": validation_message,
        "validation_contract_violations": list(validation_violations),
        "guard_error": str(error),
        "guard_phase": phase,
    }
    report["contract_status"] = CRITICAL_VIOLATION
    report["contract_message"] = error_message
    report["contract_violations"] = _dedupe_strings([*report["contract_violations"], error_message])
    return report


def _raise_integrity_violation(
    report: dict[str, Any],
    *,
    session_id: str,
    integrity_violations: list[dict[str, Any]],
    protected_state_drift: list[dict[str, Any]],
) -> None:
    combined: list[dict[str, Any]] = [
        dict(item)
        for item in integrity_violations
        if isinstance(item, dict)
    ]
    combined.extend(
        dict(item)
        for item in protected_state_drift
        if isinstance(item, dict)
    )
    raise IntegrityViolation(
        session_id=session_id,
        violations=combined,
        state_drifted=bool(protected_state_drift),
        message=str(report.get("contract_message", "Integrity violation detected.")).strip() or "Integrity violation detected.",
        report=report,
    )


_BASELINE_TOP_LEVEL_FIELDS: dict[str, Callable[[Any], bool]] = {
    "session_id": _is_nonempty_string,
    "topic": _is_nonempty_string,
    "metrics": _is_dict,
    "agreed_claims": _is_list,
    "contested_claims": _is_list,
    "one_sided_claims": _is_list,
    "unresolved_conflicts": _is_list,
}

_BASELINE_METRIC_FIELDS: dict[str, Callable[[Any], bool]] = {
    "metrics.arbitration_score": _is_number,
    "metrics.evidence_overlap": _is_number,
    "metrics.unresolved_conflict_count": _is_integer,
}

_ENHANCED_TELEMETRY_FIELDS: dict[str, Callable[[Any], bool]] = {
    "matching_backend": _is_nonempty_string,
    "embedding_version": _is_nonempty_string,
    "threshold_profile": _is_dict,
    "model_turns": _is_list,
    "bounded_challenges": _is_list,
    "total_unique_claims": _is_integer,
    "metrics.bounded_challenge_count": _is_integer,
}

_CLAIM_GROUP_FIELD_VALIDATORS: dict[str, Callable[[Any], bool]] = {
    "cluster_id": _is_nonempty_string,
    "claim": _is_nonempty_string,
    "supporting_models": _is_list_of_strings,
    "supporting_roles": _is_list_of_strings,
    "record_count": _is_integer,
    "evidence_items": _is_list_of_strings,
    "challenge_items": _is_list_of_strings,
    "uncertainty_items": _is_list_of_strings,
}

_MODEL_TURN_FIELD_VALIDATORS: dict[str, Callable[[Any], bool]] = {
    "tag": _is_nonempty_string,
    "role": _is_nonempty_string,
    "model": _is_nonempty_string,
    "sections": _is_dict,
}

_BOUNDED_CHALLENGE_FIELD_VALIDATORS: dict[str, Callable[[Any], bool]] = {
    "bounded_id": _is_nonempty_string,
    "cluster_id": _is_nonempty_string,
    "claim": _is_nonempty_string,
    "challenge": _is_nonempty_string,
    "supporting_models": _is_list_of_strings,
    "supporting_roles": _is_list_of_strings,
    "reason": _is_nonempty_string,
}


def _path_value(data: dict[str, Any], dotted_path: str) -> Any:
    current: Any = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _path_exists(data: dict[str, Any], dotted_path: str) -> bool:
    return _path_value(data, dotted_path) is not _MISSING


def _validate_mapping(
    item: Any,
    prefix: str,
    validators: dict[str, Callable[[Any], bool]],
) -> list[str]:
    if not isinstance(item, dict):
        return [f"{prefix} must be an object"]

    violations: list[str] = []
    for key, validator in validators.items():
        if key not in item:
            violations.append(f"{prefix}.{key} missing")
            continue
        if not validator(item[key]):
            violations.append(f"{prefix}.{key} has invalid type")
    return violations


def _validate_sections(item: dict[str, Any], prefix: str) -> list[str]:
    sections = item.get("sections")
    if not isinstance(sections, dict):
        return [f"{prefix}.sections has invalid type"]
    violations: list[str] = []
    for key, value in sections.items():
        if not isinstance(key, str):
            violations.append(f"{prefix}.sections contains a non-string key")
        if not isinstance(value, str):
            violations.append(f"{prefix}.sections.{key} has invalid type")
    return violations


def _validate_claim_groups(data: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for group_name in _CLAIM_GROUPS:
        group = data.get(group_name)
        if not isinstance(group, list):
            continue
        for index, item in enumerate(group):
            violations.extend(_validate_mapping(item, f"{group_name}[{index}]", _CLAIM_GROUP_FIELD_VALIDATORS))
    return violations


def _validate_unresolved_conflicts(data: dict[str, Any]) -> list[str]:
    conflicts = data.get("unresolved_conflicts")
    if not isinstance(conflicts, list):
        return []
    violations: list[str] = []
    for index, item in enumerate(conflicts):
        if not isinstance(item, dict):
            violations.append(f"unresolved_conflicts[{index}] must be an object")
    return violations


def _validate_threshold_profile(profile: Any) -> list[str]:
    if not isinstance(profile, dict):
        return []
    violations: list[str] = []
    for key in _THRESHOLD_PROFILE_FIELDS:
        if key not in profile:
            violations.append(f"threshold_profile.{key} missing")
            continue
        value = profile[key]
        if value == -1.0:
            continue
        if not _is_number(value):
            violations.append(f"threshold_profile.{key} has invalid type")
    return violations


def _validate_model_turns(data: dict[str, Any]) -> list[str]:
    turns = data.get("model_turns")
    if not isinstance(turns, list):
        return []
    violations: list[str] = []
    for index, item in enumerate(turns):
        prefix = f"model_turns[{index}]"
        violations.extend(_validate_mapping(item, prefix, _MODEL_TURN_FIELD_VALIDATORS))
        if isinstance(item, dict):
            violations.extend(_validate_sections(item, prefix))
    return violations


def _validate_bounded_challenges(data: dict[str, Any]) -> list[str]:
    challenges = data.get("bounded_challenges")
    if not isinstance(challenges, list):
        return []
    violations: list[str] = []
    for index, item in enumerate(challenges):
        violations.extend(_validate_mapping(item, f"bounded_challenges[{index}]", _BOUNDED_CHALLENGE_FIELD_VALIDATORS))
    return violations


def _resolve_identity(base_dir: Path, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "://" in text:
        return text
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return _stable_path_key(base_dir, candidate)


def _input_artifact_identity(data: Any, *, base_dir: Path) -> str:
    if not isinstance(data, dict):
        return ""
    for key in ("input_artifact_identity", "artifact_path", "output_path"):
        value = data.get(key)
        if str(value or "").strip():
            return _resolve_identity(base_dir, value)
    return ""


def _live_runtime_execution_marker() -> str:
    frame = inspect.currentframe()
    try:
        current = frame.f_back if frame is not None else None
        while current is not None:
            marker = _LIVE_RUNTIME_EXECUTION_MARKERS.get(Path(current.f_code.co_filename).name.casefold())
            if marker:
                return marker
            current = current.f_back
        return ""
    finally:
        del frame


def _write_contract_execution_signal(data: Any, *, guard: IntegrityGuard, session_id: str) -> None:
    execution_marker = _live_runtime_execution_marker()
    if not execution_marker or not session_id:
        return

    signal_path = guard.base_dir / _RUNTIME_SIGNAL_ROOT / session_id / _RUNTIME_SIGNAL_FILENAME
    artifact_identity = _input_artifact_identity(data, base_dir=guard.base_dir)
    signal_payload = {
        "timestamp": _timestamp_utc(),
        "session_id": session_id,
        "contract_function": "evaluation.contract.enforce_contract",
        "source_file": _stable_path_key(guard.base_dir, Path(__file__)),
        "input_artifact_identity": artifact_identity or None,
        "execution_marker": execution_marker,
        "note": "Live runtime contract enforcement was reached.",
    }
    if isinstance(data, dict):
        runtime_root = str(data.get("runtime_root", "")).strip()
        broker_root = str(data.get("broker_root", "")).strip()
        if runtime_root and broker_root:
            signal_payload = attach_canonical_provenance(signal_payload, runtime_root, broker_root)
    guard.safe_write_json(
        signal_path,
        signal_payload,
        allowed_roots=[guard.base_dir / _RUNTIME_SIGNAL_ROOT],
        session_id=session_id,
    )


def _write_contract_created_trace(report: dict[str, Any], *, guard: IntegrityGuard, session_id: str) -> None:
    if not session_id or not _live_runtime_execution_marker():
        return
    trace_contract_status_from_mapping(
        base_dir=guard.base_dir,
        session_id=session_id,
        checkpoint="CONTRACT_CREATED",
        container=report,
        container_name="contract_report",
        source_file=Path(__file__),
        guard=guard,
    )


def detect_version(data: dict[str, Any]) -> str:
    if not isinstance(data, dict):
        return "heuristic:invalid-root"

    declared = str(data.get("schema_version", "")).strip() or "1.0"
    enhanced_present = sum(1 for path in _ENHANCED_TELEMETRY_FIELDS if _path_exists(data, path))
    if enhanced_present == len(_ENHANCED_TELEMETRY_FIELDS):
        return "heuristic:1.1-inferred"
    if enhanced_present > 0:
        return f"heuristic:{declared}-plus-inferred"
    return f"heuristic:{declared}-baseline"


def check(data: dict[str, Any]) -> tuple[str, str, list[str]]:
    if not isinstance(data, dict):
        return INVALID, "Artifact root must be a JSON object.", ["artifact root must be an object"]

    baseline_violations: list[str] = []
    for path, validator in _BASELINE_TOP_LEVEL_FIELDS.items():
        value = _path_value(data, path)
        if value is _MISSING:
            baseline_violations.append(f"{path} missing")
            continue
        if not validator(value):
            baseline_violations.append(f"{path} has invalid type")

    metrics_block = data.get("metrics")
    if not isinstance(metrics_block, dict):
        baseline_violations.append("metrics block must be an object")
    else:
        for path, validator in _BASELINE_METRIC_FIELDS.items():
            value = _path_value(data, path)
            if value is _MISSING:
                baseline_violations.append(f"{path} missing")
                continue
            if not validator(value):
                baseline_violations.append(f"{path} has invalid type")

    baseline_violations.extend(_validate_claim_groups(data))
    baseline_violations.extend(_validate_unresolved_conflicts(data))

    if baseline_violations:
        return (
            INVALID,
            "Artifact violates the required baseline arbitration contract and is unsafe for metric computation.",
            baseline_violations,
        )

    threshold_profile = data.get("threshold_profile")
    if isinstance(threshold_profile, dict):
        sentinel_count = sum(
            1 for key in _THRESHOLD_PROFILE_FIELDS
            if threshold_profile.get(key) == -1.0
        )
        if sentinel_count == len(_THRESHOLD_PROFILE_FIELDS):
            analysis_status = str(data.get("analysis_status", "")).strip().lower()
            if analysis_status == "failed":
                return (
                    FAILED_COGNITIVE,
                    "Session failed cognitive validation gate (structural variance check). Arbitration not performed due to upstream validation failure.",
                    [],
                )

    degraded_violations: list[str] = []
    for path, validator in _ENHANCED_TELEMETRY_FIELDS.items():
        value = _path_value(data, path)
        if value is _MISSING:
            degraded_violations.append(f"{path} missing")
            continue
        if not validator(value):
            degraded_violations.append(f"{path} has invalid type")

    degraded_violations.extend(_validate_threshold_profile(data.get("threshold_profile")))
    degraded_violations.extend(_validate_model_turns(data))
    degraded_violations.extend(_validate_bounded_challenges(data))

    if degraded_violations:
        return (
            DEGRADED,
            "Artifact satisfies the baseline contract but is missing enhanced telemetry required for full-fidelity measurement.",
            degraded_violations,
        )

    return (
        VALID,
        "Artifact satisfies the baseline contract and includes the enhanced telemetry required for full-fidelity measurement.",
        [],
    )


def enforce_contract(data: dict[str, Any], *, guard: IntegrityGuard | None = None) -> dict[str, Any]:
    guard = guard or IntegrityGuard()
    session_id = _session_id_from_data(data)
    _write_contract_execution_signal(data, guard=guard, session_id=session_id)
    state_paths = _critical_state_paths(data, guard)
    pre_manifest: dict[str, str] = {}
    pre_hashes: dict[str, str | None] = {}

    try:
        pre_manifest = guard.generate_manifest()
        pre_hashes = _capture_state_hashes(guard, state_paths)
    except IntegrityViolation:
        raise
    except Exception as exc:
        logger.exception(
            "contract_integrity_guard_failed",
            extra={
                "event": "contract_integrity_guard_failed",
                "phase": "pre_validation_snapshot",
                "session_id": session_id,
                "error": str(exc),
            },
        )
        status, message, violations = check(data)
        report = {
            "contract_status": status,
            "contract_message": message,
            "contract_violations": list(violations),
            "schema_version": detect_version(data),
            "session_id": session_id,
        }
        report = _attach_integrity_error(
            report,
            base_dir=guard.base_dir,
            phase="pre_validation_snapshot",
            error=exc,
            validation_status=status,
            validation_message=message,
            validation_violations=list(violations),
            state_paths=state_paths,
            pre_manifest=pre_manifest,
        )
        _write_contract_created_trace(report, guard=guard, session_id=session_id)
        _raise_integrity_violation(
            report,
            session_id=session_id,
            integrity_violations=report["integrity_violations"],
            protected_state_drift=report["protected_state_drift"],
        )

    status, message, violations = check(data)
    report = {
        "contract_status": status,
        "contract_message": message,
        "contract_violations": list(violations),
        "schema_version": detect_version(data),
        "session_id": session_id,
    }

    try:
        post_manifest = guard.generate_manifest()
        post_hashes = _capture_state_hashes(guard, state_paths)
        integrity_violations = guard.detect_violations(pre_manifest, post_manifest)
        protected_state_drift = _detect_protected_state_drift(guard, state_paths, pre_hashes, post_hashes)
    except IntegrityViolation:
        raise
    except Exception as exc:
        logger.exception(
            "contract_integrity_guard_failed",
            extra={
                "event": "contract_integrity_guard_failed",
                "phase": "post_validation_snapshot",
                "session_id": session_id,
                "error": str(exc),
            },
        )
        report = _attach_integrity_error(
            report,
            base_dir=guard.base_dir,
            phase="post_validation_snapshot",
            error=exc,
            validation_status=status,
            validation_message=message,
            validation_violations=list(violations),
            state_paths=state_paths,
            pre_manifest=pre_manifest,
        )
        _write_contract_created_trace(report, guard=guard, session_id=session_id)
        _raise_integrity_violation(
            report,
            session_id=session_id,
            integrity_violations=report["integrity_violations"],
            protected_state_drift=report["protected_state_drift"],
        )

    report = _attach_integrity_results(
        report,
        base_dir=guard.base_dir,
        validation_status=status,
        validation_message=message,
        validation_violations=list(violations),
        state_paths=state_paths,
        pre_manifest=pre_manifest,
        post_manifest=post_manifest,
        integrity_violations=integrity_violations,
        protected_state_drift=protected_state_drift,
    )
    _write_contract_created_trace(report, guard=guard, session_id=session_id)
    if integrity_violations or protected_state_drift:
        _raise_integrity_violation(
            report,
            session_id=session_id,
            integrity_violations=integrity_violations,
            protected_state_drift=protected_state_drift,
        )
    return report

