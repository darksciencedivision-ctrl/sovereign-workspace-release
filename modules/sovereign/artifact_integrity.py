from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

try:
    from evaluation.integrity import IntegrityGuard
except ImportError:  # pragma: no cover - fallback for direct module execution
    from integrity import IntegrityGuard

UNKNOWN_EXECUTION_MODE = "UNKNOWN"
MISSING_DIALOG_ORIGIN = "missing"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_failure_reason(reason: Any) -> str | None:
    if reason is None:
        return None
    text = str(reason).strip()
    return text or None


def normalize_model_turns(model_turns: Any) -> list[dict[str, Any]]:
    if not isinstance(model_turns, list):
        return []
    return [dict(item) for item in model_turns if isinstance(item, dict)]


def infer_dialog_origin(dialog_origin: str = "", dialog_source_path: str = "") -> str:
    explicit = str(dialog_origin or "").strip()
    if explicit:
        return explicit

    source = str(dialog_source_path or "").strip()
    if not source:
        return MISSING_DIALOG_ORIGIN

    normalized = source.replace("/", "\\").lower()
    if normalized.endswith("_dialog.txt"):
        return "session_dialog_artifact"
    if normalized.endswith("debate_dialog.txt"):
        return "shared_dialog_artifact"
    return "dialog_artifact"


def apply_provenance(
    payload: Dict[str, Any],
    *,
    execution_mode: str,
    dialog_origin: str,
    model_calls_observed: bool,
    execution_complete: bool,
    failure_reason: Any,
    session_id: str,
    timestamp: str | None = None,
    model_turns: Any = None,
) -> Dict[str, Any]:
    normalized_turns = normalize_model_turns(model_turns)
    payload.update(
        {
            "execution_mode": str(execution_mode or UNKNOWN_EXECUTION_MODE).strip() or UNKNOWN_EXECUTION_MODE,
            "dialog_origin": infer_dialog_origin(dialog_origin=dialog_origin),
            "model_calls_observed": bool(model_calls_observed or normalized_turns),
            "execution_complete": bool(execution_complete),
            "failure_reason": normalize_failure_reason(failure_reason),
            "timestamp": str(timestamp or utc_now_iso()),
            "session_id": str(session_id or "unknown").strip() or "unknown",
            "model_turns": normalized_turns,
        }
    )
    return payload


def build_stage_state(
    stage: str,
    status: str,
    executed: bool,
    *,
    failure_reason: Any = None,
    artifact_path: str | None = None,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "stage": str(stage or "").strip(),
        "status": str(status or "").strip() or "unknown",
        "executed": bool(executed),
        "failure_reason": normalize_failure_reason(failure_reason),
        "artifact_path": str(artifact_path).strip() if artifact_path else None,
    }
    if details:
        state["details"] = dict(details)
    return state


def write_json_atomic(
    path: str | Path,
    data: Any,
    *,
    guard: IntegrityGuard | None = None,
    allowed_roots: list[str | Path] | None = None,
    session_id: str = "",
) -> None:
    if guard is not None:
        guard.safe_write_json(path, data, allowed_roots=allowed_roots, session_id=session_id)
        return

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    tmp_path = Path(tmp)
    try:
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            if not payload.endswith("\n"):
                handle.write("\n")
        os.replace(str(tmp_path), str(target))
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def persist_artifact_integrity_report(root: str | Path, session_id: str, report: Dict[str, Any]) -> Dict[str, Any]:
    root_path = Path(root).resolve()
    scheduler_state = root_path / "scheduler" / "state"
    output_path = scheduler_state / "artifact_integrity_report.json"
    normalized_session_id = str(session_id or "unknown").strip() or "unknown"
    session_output_path = scheduler_state / "artifact_integrity" / f"{normalized_session_id}.json"
    guard = IntegrityGuard(base_dir=root_path)
    allowed_roots: list[Path] = [scheduler_state]

    persisted = dict(report)
    persisted["output_path"] = str(output_path)
    persisted["session_output_path"] = str(session_output_path)

    write_json_atomic(output_path, persisted, guard=guard, allowed_roots=allowed_roots, session_id=normalized_session_id)
    write_json_atomic(session_output_path, persisted, guard=guard, allowed_roots=allowed_roots, session_id=normalized_session_id)
    return persisted
