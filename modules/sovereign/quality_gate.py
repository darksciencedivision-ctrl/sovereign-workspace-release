#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
quality_gate.py
SOVEREIGN canonical quality gate

Legacy behavior is preserved and arbitration-aware gating is added on top.
Older callers may still call evaluate(synthesis, session_id, confidence, root=...).
Newer callers may also pass dialog_text so claim arbitration can run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from artifact_integrity import apply_provenance, infer_dialog_origin, normalize_failure_reason
from claim_arbitrator import analyze_dialog, persist_arbitration_stub

try:
    from evaluation.integrity import IntegrityGuard, IntegrityViolation
except ImportError:  # pragma: no cover - fallback for direct module execution
    from integrity import IntegrityGuard, IntegrityViolation


SCHEMA_VERSION = "1.0"
VALID_SUCCESS_STATUS = "completed"
MODULE_NAME = "QUALITY_GATE"
MAX_LOG_BYTES = 10 * 1024 * 1024
TIMESTAMP_FLOOR = datetime(1970, 1, 1, tzinfo=timezone.utc)
DEFAULT_ROOT = str(Path(__file__).resolve().parent)  # portable; active root resolved in main()
DEFAULT_MIN_CONVERGENCE = 0.85
DEFAULT_MIN_CONFIDENCE = 0.75
DEFAULT_MIN_ARBITRATION_STRICT = 0.20
DEFAULT_MAX_UNRESOLVED_CONFLICTS = 0

# Operator-facing disclosure emitted with every quality-gate result. structural_completeness
# and response_elaboration are FORM metrics (structure/length/bullet counts), not truth.
STRUCTURAL_METRIC_DISCLOSURE = (
    "structural_completeness and response_elaboration measure output form (structure, "
    "length, bullet counts), not truth. Acceptance authority rests on the arbitration and "
    "concurrence result. No independent truth-validation is claimed."
)


def _defaults(root: Path) -> Dict[str, Path]:
    return {
        "session_graph_path": root / "orchestra" / "session_graph.json",
        "output_path": root / "scheduler" / "state" / "quality_gate_result.json",
        "per_session_dir": root / "scheduler" / "state" / "quality_gate",
        "log_file": root / "logs" / "quality_gate_log.txt",
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig") if path.exists() else ""


def load_optional_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return load_json(path)
    except (OSError, json.JSONDecodeError):
        return None


def _write_json_atomic(
    path: Path,
    data: Any,
    *,
    guard: IntegrityGuard | None = None,
    allowed_roots: list[str | Path] | None = None,
    session_id: str = "",
) -> None:
    if guard is not None:
        guard.safe_write_json(path, data, allowed_roots=allowed_roots, session_id=session_id)
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    tmp_path = Path(tmp)
    try:
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            if not payload.endswith("\n"):
                fh.write("\n")
        os.replace(str(tmp_path), str(path))
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _rotate_log_if_needed(log_file: Path) -> None:
    try:
        if not log_file.exists():
            return
        if log_file.stat().st_size <= MAX_LOG_BYTES:
            return
        backup = Path(str(log_file) + ".1")
        if backup.exists():
            backup.unlink()
        os.replace(str(log_file), str(backup))
    except OSError:
        pass


def log(msg: str, log_file: Path, level: str = "INFO") -> None:
    lvl = str(level or "INFO").upper()
    if lvl not in {"INFO", "WARN", "ERROR"}:
        lvl = "INFO"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    line = f"[{ts}] [{MODULE_NAME}] [{lvl}] {msg}"
    print(line, flush=True)
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        _rotate_log_if_needed(log_file)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def validate_graph_shape(data: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(data, dict):
        return ["session_graph must be a JSON object, not a flat array or other type"]

    sv = data.get("schema_version")
    if sv != SCHEMA_VERSION:
        errors.append(f"schema_version must be '{SCHEMA_VERSION}', got {sv!r}")

    sessions = data.get("sessions")
    if not isinstance(sessions, list):
        errors.append("sessions must be a list")
        return errors

    for i, session in enumerate(sessions):
        prefix = f"sessions[{i}]"
        if not isinstance(session, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if not session.get("session_id"):
            errors.append(f"{prefix}.session_id is required and non-empty")
        if "status" not in session:
            errors.append(f"{prefix}.status is required")
        metrics = session.get("metrics")
        if not isinstance(metrics, dict):
            errors.append(f"{prefix}.metrics is required and must be an object")
            continue
        for key in ("structural_completeness", "response_elaboration"):
            val = metrics.get(key)
            if not isinstance(val, (int, float)):
                errors.append(f"{prefix}.metrics.{key} must be numeric, got {type(val).__name__!r}")
            elif not (0.0 <= float(val) <= 1.0):
                errors.append(f"{prefix}.metrics.{key} = {val} is outside [0.0, 1.0]")
    return errors


def _timestamp_key(session: Dict[str, Any]) -> datetime:
    ts = session.get("timestamp")
    if not isinstance(ts, str) or not ts:
        return TIMESTAMP_FLOOR
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return TIMESTAMP_FLOOR


def select_session(data: Dict[str, Any], session_id: Optional[str]) -> Optional[Dict[str, Any]]:
    sessions = data.get("sessions", [])
    if not sessions:
        return None
    if session_id:
        for session in sessions:
            if session.get("session_id") == session_id:
                return session
        return None
    return max(enumerate(sessions), key=lambda pair: (_timestamp_key(pair[1]), pair[0]))[1]


def _coerce_metric(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _load_convergence_score(root: Path, session_id: str) -> Optional[float]:
    graph_path = _defaults(root)["session_graph_path"]
    if not graph_path.exists():
        return None
    try:
        data = load_json(graph_path)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    session = select_session(data, session_id)
    if not session:
        return None
    metrics = session.get("metrics") or {}
    if not isinstance(metrics, dict):
        return None
    value = metrics.get("structural_completeness")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _derive_conflict_status(arbitration_executed: bool, unresolved_conflict_count: int, warnings: list[str]) -> str:
    if not arbitration_executed:
        return "error"
    if unresolved_conflict_count > 0:
        return "unresolved"
    if warnings:
        return "none"
    return "none"


def _zero_arbitration_metrics() -> Dict[str, Any]:
    return {
        "arbitration_score": 0.0,
        "arbitration_score_strict": 0.0,
        "arbitration_score_soft": 0.0,
        "evidence_overlap": 0.0,
        "contradiction_count": 0,
        "agreed_ratio": 0.0,
        "contradiction_density": 0.0,
        "coverage_factor": 0.0,
        "unresolved_conflict_count": 0,
    }


def build_result(
    *,
    session_id: str,
    topic: str,
    status: str,
    passed: bool,
    reasons: List[str] | None = None,
    warnings: List[str] | None = None,
    arbitration_executed: bool = False,
    arbitration_skipped_reason: str = "",
    arbitration_artifact_path: str = "",
    arbitration_warnings: List[str] | None = None,
    arbitration_metrics: Dict[str, Any] | None = None,
    arbitration_status: str = "not_run",
    arbitration_failure_reason: str | None = None,
    convergence_value: Optional[float] = None,
    confidence_value: float = 0.0,
    min_convergence: float = DEFAULT_MIN_CONVERGENCE,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    min_arbitration_strict: float = DEFAULT_MIN_ARBITRATION_STRICT,
    max_unresolved_conflicts: int = DEFAULT_MAX_UNRESOLVED_CONFLICTS,
    execution_mode: str = "UNKNOWN",
    dialog_origin: str = "",
    model_calls_observed: bool = False,
    execution_complete: bool = True,
    failure_reason: str | None = None,
    model_turns: list[dict[str, Any]] | None = None,
    quality_gate_state: str = "evaluated",
) -> Dict[str, Any]:
    reasons_list = [str(item) for item in (reasons or []) if str(item).strip()]
    warnings_list = [str(item) for item in (warnings or []) if str(item).strip()]
    arbitration_warning_list = [str(item) for item in (arbitration_warnings or []) if str(item).strip()]
    metrics = _zero_arbitration_metrics()
    metrics.update(arbitration_metrics or {})

    convergence_metric = 0.0 if convergence_value is None else float(convergence_value)
    confidence_metric = float(confidence_value)
    conflict_status = _derive_conflict_status(arbitration_executed, int(metrics["unresolved_conflict_count"]), arbitration_warning_list)

    result = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "quality_gate_result",
        "quality_gate_state": str(quality_gate_state or "evaluated").strip() or "evaluated",
        "timestamp": utc_now_iso(),
        "session_id": session_id,
        "topic": topic,
        "status": status,
        "passed": bool(passed),
        "arbitration_executed": arbitration_executed,
        "metrics": {
            "structural_completeness": round(convergence_metric, 4),
            "response_elaboration": round(confidence_metric, 4),
            "arbitration_score": round(float(metrics["arbitration_score"]), 4),
            "arbitration_score_strict": round(float(metrics["arbitration_score_strict"]), 4),
            "arbitration_score_soft": round(float(metrics["arbitration_score_soft"]), 4),
            "unresolved_conflict_count": int(metrics["unresolved_conflict_count"]),
            "contradiction_count": int(metrics["contradiction_count"]),
            "agreed_ratio": round(float(metrics["agreed_ratio"]), 4),
            "contradiction_density": round(float(metrics["contradiction_density"]), 4),
            "coverage_factor": round(float(metrics["coverage_factor"]), 4),
            "evidence_overlap": round(float(metrics["evidence_overlap"]), 4),
        },
        "scores": {
            "structural_completeness": None if convergence_value is None else round(convergence_metric, 4),
            "response_elaboration": round(confidence_metric, 6),
            "conflicts": conflict_status,
        },
        "thresholds": {
            "min_structural_completeness": min_convergence,
            "min_response_elaboration": min_confidence,
            "min_arbitration_strict": min_arbitration_strict,
            "max_unresolved_conflicts": max_unresolved_conflicts,
        },
        "structural_metric_disclosure": STRUCTURAL_METRIC_DISCLOSURE,
        "reasons": reasons_list,
        "warnings": warnings_list,
        "arbitration": {
            "status": arbitration_status,
            "executed": arbitration_executed,
            "skipped_reason": arbitration_skipped_reason,
            "artifact_path": arbitration_artifact_path,
            "warnings": arbitration_warning_list,
            "failure_reason": normalize_failure_reason(arbitration_failure_reason),
        },
    }
    apply_provenance(
        result,
        execution_mode=execution_mode,
        dialog_origin=dialog_origin,
        model_calls_observed=model_calls_observed,
        execution_complete=execution_complete,
        failure_reason=failure_reason or ("; ".join(reasons_list) if reasons_list else None),
        session_id=session_id,
        timestamp=result["timestamp"],
        model_turns=model_turns,
    )
    return result


def persist_result(
    root: Path,
    result: Dict[str, Any],
    *,
    output_path: Path | None = None,
    session_output_path: Path | None = None,
) -> Dict[str, Any]:
    defaults = _defaults(root)
    final_output_path = output_path or defaults["output_path"]
    final_session_output_path = session_output_path or defaults["per_session_dir"] / f"{result.get('session_id', 'unknown')}.json"
    persisted = dict(result)
    persisted["output_path"] = str(final_output_path)
    persisted["session_output_path"] = str(final_session_output_path)
    session_id = str(result.get("session_id", "")).strip()
    guard = IntegrityGuard(base_dir=root)
    allowed_roots: list[Path] = [root / "scheduler" / "state"]
    _write_json_atomic(final_output_path, persisted, guard=guard, allowed_roots=allowed_roots, session_id=session_id)
    _write_json_atomic(final_session_output_path, persisted, guard=guard, allowed_roots=allowed_roots, session_id=session_id)
    return persisted


def evaluate(
    synthesis: str,
    session_id: str,
    confidence: float,
    root: str = DEFAULT_ROOT,
    dialog_text: Optional[str] = None,
    topic: str = "",
    convergence: Optional[float] = None,
    status: str = VALID_SUCCESS_STATUS,
    min_convergence: float = DEFAULT_MIN_CONVERGENCE,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    min_arbitration_strict: float = DEFAULT_MIN_ARBITRATION_STRICT,
    max_unresolved_conflicts: int = DEFAULT_MAX_UNRESOLVED_CONFLICTS,
    dialog_source_path: str = "",
    execution_mode: str = "UNKNOWN",
    dialog_origin: str = "",
    model_calls_observed: Optional[bool] = None,
    persist: bool = False,
) -> Dict[str, Any]:
    root_path = Path(root).resolve()
    log_file = _defaults(root_path)["log_file"]
    reasons: List[str] = []
    warnings: List[str] = []
    session_id = str(session_id or "").strip()
    topic = str(topic or "").strip()

    log(f"Evaluating session_id={session_id} response_elaboration={confidence}", log_file, "INFO")

    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0
        reasons.append(f"response_elaboration value invalid: {confidence!r}")

    convergence_value: Optional[float]
    if convergence is None:
        convergence_value = _load_convergence_score(root_path, session_id)
    else:
        try:
            convergence_value = float(convergence)
        except (TypeError, ValueError):
            convergence_value = None
    if convergence_value is None:
        reasons.append("structural_completeness_score unavailable (session_graph.json missing or session not found)")
        convergence_metric = 0.0
    else:
        convergence_metric = convergence_value
        if convergence_metric < min_convergence:
            reasons.append(f"structural_completeness_below_floor {convergence_metric:.4f} < {min_convergence:.4f}")

    if confidence_value < min_confidence:
        reasons.append(f"response_elaboration_below_floor {confidence_value:.4f} < {min_confidence:.4f}")

    if status != VALID_SUCCESS_STATUS:
        reasons.append(f"status must be '{VALID_SUCCESS_STATUS}', got '{status}'")

    dialog_origin_value = infer_dialog_origin(dialog_origin=dialog_origin, dialog_source_path=dialog_source_path)
    arbitration_executed = False
    arbitration_skipped_reason = ""
    arbitration_artifact_path = ""
    arbitration_warnings: list[str] = []
    arbitration_metrics = _zero_arbitration_metrics()
    arbitration_status = "not_run"
    arbitration_failure_reason: str | None = None
    arbitration_model_turns: list[dict[str, Any]] = []
    existing_arbitration_path = root_path / "arbitration" / f"{session_id}.json"
    existing_arbitration_artifact = load_optional_json(existing_arbitration_path)

    if not synthesis or not synthesis.strip():
        reasons.append("synthesis text is empty - cannot evaluate conflicts")
    if dialog_text is None or not str(dialog_text).strip():
        if isinstance(existing_arbitration_artifact, dict):
            artifact = dict(existing_arbitration_artifact)
            arbitration_executed = bool(artifact.get("executed"))
            arbitration_status = str(artifact.get("analysis_status", "")).strip() or "completed"
        else:
            arbitration_skipped_reason = "dialog_text missing"
            arbitration_status = "skipped"
            arbitration_failure_reason = "dialog_text missing"
            warnings.append("arbitration skipped: dialog_text missing")
            reasons.append("arbitration was not executed because dialog_text is missing")
            artifact = persist_arbitration_stub(
                root=root_path,
                session_id=session_id,
                topic=topic,
                source_path=dialog_source_path,
                warnings=["arbitration skipped: dialog_text missing"],
                failure_reason=arbitration_failure_reason,
                analysis_status="skipped",
                execution_mode=execution_mode,
                dialog_origin=dialog_origin_value,
                model_calls_observed=bool(model_calls_observed),
                model_turns=[],
            )
        arbitration_artifact_path = str(artifact.get("artifact_path", ""))
        arbitration_model_turns = list(artifact.get("model_turns") or [])
    else:
        if isinstance(existing_arbitration_artifact, dict):
            artifact = dict(existing_arbitration_artifact)
            arbitration_executed = bool(artifact.get("executed"))
            arbitration_status = str(artifact.get("analysis_status", "")).strip() or "completed"
        else:
            try:
                artifact = analyze_dialog(
                    dialog_text=str(dialog_text),
                    session_id=session_id,
                    root=root_path,
                    topic=topic,
                    source_path=dialog_source_path,
                    execution_mode=execution_mode,
                    dialog_origin=dialog_origin_value,
                    model_calls_observed=bool(model_calls_observed),
                )
            except IntegrityViolation:
                raise
            except Exception as exc:
                arbitration_status = "failed"
                arbitration_failure_reason = str(exc)
                warnings.append(f"arbitration failed: {exc}")
                reasons.append(f"arbitration failed: {exc}")
                artifact = persist_arbitration_stub(
                    root=root_path,
                    session_id=session_id,
                    topic=topic,
                    source_path=dialog_source_path,
                    warnings=[f"arbitration failed: {exc}"],
                    failure_reason=arbitration_failure_reason,
                    analysis_status="failed",
                    execution_mode=execution_mode,
                    dialog_origin=dialog_origin_value,
                    model_calls_observed=bool(model_calls_observed),
                    model_turns=[],
                )
            else:
                arbitration_executed = True
                arbitration_status = "completed"

        arbitration_artifact_path = str(artifact.get("artifact_path", ""))
        arbitration_warnings = [str(item) for item in artifact.get("warnings", []) if str(item).strip()]
        warnings.extend(arbitration_warnings)
        arbitration_metrics.update(artifact.get("metrics") or {})
        arbitration_model_turns = [dict(item) for item in artifact.get("model_turns", []) if isinstance(item, dict)]
        if arbitration_executed:
            if arbitration_metrics["arbitration_score_strict"] < min_arbitration_strict:
                reasons.append(
                    f"arbitration_score_strict {arbitration_metrics['arbitration_score_strict']:.4f} < threshold {min_arbitration_strict:.4f}"
                )
            if int(arbitration_metrics["unresolved_conflict_count"]) > int(max_unresolved_conflicts):
                reasons.append(
                    f"unresolved_conflict_count {int(arbitration_metrics['unresolved_conflict_count'])} > threshold {int(max_unresolved_conflicts)}"
                )

    passed = len(reasons) == 0
    result = build_result(
        session_id=session_id,
        topic=topic,
        status=status,
        passed=passed,
        reasons=reasons,
        warnings=warnings,
        arbitration_executed=arbitration_executed,
        arbitration_skipped_reason=arbitration_skipped_reason,
        arbitration_artifact_path=arbitration_artifact_path,
        arbitration_warnings=arbitration_warnings,
        arbitration_metrics=arbitration_metrics,
        arbitration_status=arbitration_status,
        arbitration_failure_reason=arbitration_failure_reason,
        convergence_value=convergence_value,
        confidence_value=confidence_value,
        min_convergence=min_convergence,
        min_confidence=min_confidence,
        min_arbitration_strict=min_arbitration_strict,
        max_unresolved_conflicts=max_unresolved_conflicts,
        execution_mode=execution_mode,
        dialog_origin=dialog_origin_value,
        model_calls_observed=bool(model_calls_observed) or bool(arbitration_model_turns),
        execution_complete=True,
        failure_reason=("; ".join(reasons) if reasons else arbitration_failure_reason),
        model_turns=arbitration_model_turns,
        quality_gate_state="evaluated",
    )

    if persist:
        result = persist_result(root_path, result)

    verdict = "PASS" if passed else "FAIL"
    log(
        f"{verdict} | session={session_id} structural_completeness={result['metrics']['structural_completeness']} response_elaboration={result['metrics']['response_elaboration']} arb={result['metrics']['arbitration_score']}",
        log_file,
        "INFO" if passed else "WARN",
    )
    for reason in reasons:
        log(f"reason: {reason}", log_file, "WARN")
    for warning in warnings:
        log(f"warning: {warning}", log_file, "WARN")
    return result


def _session_artifact_text(session: Dict[str, Any], keys: list[str]) -> tuple[str, str]:
    artifacts = session.get("artifacts") or {}
    if not isinstance(artifacts, dict):
        return "", ""
    for key in keys:
        candidate = str(artifacts.get(key, "")).strip()
        if candidate:
            path = Path(candidate)
            if path.exists():
                return load_text(path), str(path)
    return "", ""


def evaluate_session(
    session: Dict[str, Any],
    min_convergence: float,
    min_confidence: float,
    root: str = DEFAULT_ROOT,
    persist: bool = False,
) -> Dict[str, Any]:
    metrics = session.get("metrics") or {}
    synthesis_text, _ = _session_artifact_text(session, ["synthesis_session_path", "synthesis_path"])
    dialog_text, dialog_path = _session_artifact_text(session, ["dialog_session_path", "dialog_path"])
    return evaluate(
        synthesis=synthesis_text,
        session_id=str(session.get("session_id", "")),
        confidence=metrics.get("response_elaboration", 0.0),
        root=root,
        dialog_text=dialog_text or None,
        topic=str(session.get("topic", "")),
        convergence=metrics.get("structural_completeness"),
        status=str(session.get("status", "")),
        min_convergence=min_convergence,
        min_confidence=min_confidence,
        dialog_source_path=dialog_path,
        persist=persist,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SOVEREIGN canonical quality gate")
    parser.add_argument("--root", default=None,
                        help="SOVEREIGN root (default: auto-detect via .sovereign-root marker)")
    parser.add_argument("--session-id", default=None, help="Evaluate a specific session_id (default: latest)")
    parser.add_argument("--min-convergence", type=float, default=DEFAULT_MIN_CONVERGENCE)
    parser.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE)
    parser.add_argument("--min-arbitration-strict", type=float, default=DEFAULT_MIN_ARBITRATION_STRICT)
    parser.add_argument("--max-unresolved-conflicts", type=int, default=DEFAULT_MAX_UNRESOLVED_CONFLICTS)
    parser.add_argument("--dry-run", action="store_true", help="Print result but do not write output file")
    parser.add_argument("--session-graph-path", default=None)
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def _resolve_root(cli_root):
    """Resolve SOVEREIGN root via the single authority (tools/sovereign_paths.py)."""
    repo = Path(__file__).resolve().parent
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from tools.sovereign_paths import get_repo_root, configure_root
    return configure_root(str(cli_root)) if cli_root else get_repo_root()


def main() -> int:
    args = _parse_args()
    root = _resolve_root(args.root)
    args.root = str(root)
    defaults = _defaults(root)
    log_file = defaults["log_file"]
    graph_path = Path(args.session_graph_path) if args.session_graph_path else defaults["session_graph_path"]
    output_path = Path(args.output_path) if args.output_path else defaults["output_path"]

    log(f"=== quality_gate starting | graph={graph_path} ===", log_file, "INFO")

    def _fail(code: int, error: str, **extra: Any) -> int:
        failure_session_id = str(extra.pop("session_id", args.session_id or "unknown")).strip() or "unknown"
        failure_topic = str(extra.pop("topic", "")).strip()
        result = build_result(
            session_id=failure_session_id,
            topic=failure_topic,
            status="failed",
            passed=False,
            reasons=[error],
            warnings=[],
            arbitration_executed=False,
            arbitration_status="not_run",
            arbitration_failure_reason="quality gate bootstrap failure",
            convergence_value=None,
            confidence_value=0.0,
            execution_mode="UNKNOWN",
            dialog_origin="missing",
            model_calls_observed=False,
            execution_complete=False,
            failure_reason=error,
            model_turns=[],
            quality_gate_state="failed",
        )
        result["error"] = error
        result.update(extra)
        log(f"FAIL [{code}]: {error}", log_file, "ERROR")
        if not args.dry_run:
            result = persist_result(root, result, output_path=output_path)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return code

    if not graph_path.exists():
        return _fail(2, f"session_graph not found: {graph_path}")

    try:
        data = load_json(graph_path)
    except Exception as exc:
        return _fail(3, f"failed to parse session_graph.json: {exc}")

    shape_errors = validate_graph_shape(data)
    if shape_errors:
        return _fail(4, "session_graph shape/schema validation failed", details=shape_errors)

    session = select_session(data, args.session_id)
    if not session:
        return _fail(5, "no matching session found", requested_session_id=args.session_id, total_sessions=len(data.get("sessions", [])))

    result = evaluate(
        synthesis=_session_artifact_text(session, ["synthesis_session_path", "synthesis_path"])[0],
        session_id=str(session.get("session_id", "")),
        confidence=(session.get("metrics") or {}).get("response_elaboration", 0.0),
        root=str(root),
        dialog_text=_session_artifact_text(session, ["dialog_session_path", "dialog_path"])[0] or None,
        topic=str(session.get("topic", "")),
        convergence=(session.get("metrics") or {}).get("structural_completeness", 0.0),
        status=str(session.get("status", "")),
        min_convergence=args.min_convergence,
        min_confidence=args.min_confidence,
        min_arbitration_strict=args.min_arbitration_strict,
        max_unresolved_conflicts=args.max_unresolved_conflicts,
        dialog_source_path=_session_artifact_text(session, ["dialog_session_path", "dialog_path"])[1],
        persist=False,
    )

    if not args.dry_run:
        result = persist_result(root, result, output_path=output_path)
        log(f"result written to {output_path}", log_file, "INFO")

    print(json.dumps(result, indent=2, ensure_ascii=False))
    log("=== quality_gate complete ===", log_file, "INFO")
    return 0 if result["passed"] else 6


if __name__ == "__main__":
    raise SystemExit(main())
