from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


TRACE_ROOT = Path("evaluation") / "verification" / "runtime_signals"
SUMMARY_FILENAME = "contract_trace_summary.json"
REPORT_FILENAME = "contract_trace_report.md"
CONTRACT_STATUS_FIELD = "contract_status"
CHECKPOINTS = (
    "CONTRACT_CREATED",
    "CONTRACT_RETURNED",
    "CONTRACT_ATTACHED",
    "CONTRACT_METADATA",
    "CONTRACT_LEDGER",
)
_CHECKPOINT_ORDER = {name: index for index, name in enumerate(CHECKPOINTS)}
_LOSS_PENDING = "pending"
_LOSS_INTACT = "intact"
_LOSS_NEVER_CREATED = "never_created"
_LOSS_CREATED_THEN_DROPPED = "created_then_dropped"
_LOSS_BLANKED_OUT = "blanked_out"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_path_key(base_dir: Path, path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve(strict=False)
    try:
        return resolved.relative_to(base_dir).as_posix()
    except ValueError:
        return resolved.as_posix()


def _session_dir(base_dir: Path, session_id: str) -> Path:
    return base_dir / TRACE_ROOT / session_id


def _checkpoint_path(base_dir: Path, session_id: str, checkpoint: str) -> Path:
    return _session_dir(base_dir, session_id) / f"contract_trace_{checkpoint}.json"


def _summary_path(base_dir: Path, session_id: str) -> Path:
    return _session_dir(base_dir, session_id) / SUMMARY_FILENAME


def _normalize_contract_status(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_blank_contract_status(value: Any) -> bool:
    return not _normalize_contract_status(value)


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            if text and not text.endswith("\n"):
                handle.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _write_payload(
    path: Path,
    payload: Any,
    *,
    guard: Any | None,
    session_id: str,
    allowed_roots: Sequence[Path],
) -> None:
    if guard is not None and hasattr(guard, "safe_write_json"):
        guard.safe_write_json(path, payload, allowed_roots=allowed_roots, session_id=session_id)
        return
    _atomic_write_json(path, payload)


def _write_text(
    path: Path,
    text: str,
    *,
    guard: Any | None,
    session_id: str,
    allowed_roots: Sequence[Path],
) -> None:
    if guard is not None and hasattr(guard, "safe_write_text"):
        guard.safe_write_text(path, text, allowed_roots=allowed_roots, session_id=session_id)
        return
    _atomic_write_text(path, text)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_context(context: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(context, Mapping):
        return {}
    normalized: dict[str, Any] = {}
    for key in (
        "campaign_id",
        "manifest_index",
        "prompt_id",
        "category",
        "bucket",
        "run_index",
        "attempt_number",
        "succeeded",
        "invalid_for_campaign",
        "failure_class",
        "failure_reason",
    ):
        if key not in context:
            continue
        value = context[key]
        if isinstance(value, str):
            value = value.strip()
        normalized[key] = value
    return normalized


def _merge_context(existing: Mapping[str, Any] | None, update: Mapping[str, Any] | None) -> dict[str, Any]:
    merged = dict(existing or {})
    for key, value in _normalize_context(update).items():
        if value in ("", None, [], {}):
            continue
        merged[key] = value
    return merged


def _summary_timeline_entry(payload: Mapping[str, Any] | None, checkpoint: str) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or not payload:
        return {
            "checkpoint": checkpoint,
            "observed": False,
            "contract_status": "",
            "field_exists": False,
            "is_blank": True,
            "container_name": "",
            "source_file": "",
            "timestamp": "",
        }
    return {
        "checkpoint": checkpoint,
        "observed": True,
        "contract_status": _normalize_contract_status(payload.get("contract_status")),
        "field_exists": bool(payload.get("field_exists", False)),
        "is_blank": bool(payload.get("is_blank", True)),
        "container_name": str(payload.get("container_name", "")).strip(),
        "source_file": str(payload.get("source_file", "")).strip(),
        "timestamp": str(payload.get("timestamp", "")).strip(),
    }


def _summary_state_label(item: Mapping[str, Any]) -> str:
    if not item.get("observed", False):
        return "MISSING"
    if not item.get("field_exists", False):
        return "DROPPED"
    if item.get("is_blank", True):
        return "BLANK"
    return str(item.get("contract_status", "")).strip() or "BLANK"


def _last_observed_index(timeline: Sequence[Mapping[str, Any]]) -> int:
    for index in range(len(timeline) - 1, -1, -1):
        if timeline[index].get("observed", False):
            return index
    return -1


def _first_nonblank_index(timeline: Sequence[Mapping[str, Any]]) -> int:
    for index, item in enumerate(timeline):
        if item.get("observed", False) and item.get("field_exists", False) and not item.get("is_blank", True):
            return index
    return -1


def _classify_loss(timeline: Sequence[Mapping[str, Any]]) -> tuple[str, str, str]:
    last_observed = _last_observed_index(timeline)
    if last_observed < 0:
        return "", "no trace observed", _LOSS_PENDING

    created = timeline[0]
    if not created.get("observed", False) or not created.get("field_exists", False):
        return CHECKPOINTS[0], "contract_status was never created in live contract enforcement", _LOSS_NEVER_CREATED
    if created.get("is_blank", True):
        return CHECKPOINTS[0], "contract_status was blank when the contract report was created", _LOSS_BLANKED_OUT

    for index in range(1, last_observed + 1):
        item = timeline[index]
        checkpoint = CHECKPOINTS[index]
        if not item.get("observed", False) or not item.get("field_exists", False):
            return checkpoint, "contract_status was created and later dropped from the container", _LOSS_CREATED_THEN_DROPPED
        if item.get("is_blank", True):
            return checkpoint, "contract_status was created and later blanked out", _LOSS_BLANKED_OUT

    if last_observed < len(CHECKPOINTS) - 1:
        return "", "trace is still in progress", _LOSS_PENDING
    return "", "contract_status remained populated through all traced checkpoints", _LOSS_INTACT


def trace_contract_status(
    *,
    base_dir: Path,
    session_id: str,
    checkpoint: str,
    contract_status: Any,
    field_exists: bool,
    container_name: str,
    source_file: str | Path,
    guard: Any | None = None,
    summary_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_base_dir = Path(base_dir).resolve()
    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        return {}
    if checkpoint not in _CHECKPOINT_ORDER:
        raise ValueError(f"Unsupported checkpoint: {checkpoint}")

    trace_root = normalized_base_dir / TRACE_ROOT
    payload = {
        "session_id": normalized_session_id,
        "checkpoint": checkpoint,
        "contract_status": _normalize_contract_status(contract_status),
        "field_exists": bool(field_exists),
        "is_blank": _is_blank_contract_status(contract_status),
        "container_name": str(container_name or "").strip(),
        "source_file": _stable_path_key(normalized_base_dir, source_file),
        "timestamp": utc_now_iso(),
    }
    _write_payload(
        _checkpoint_path(normalized_base_dir, normalized_session_id, checkpoint),
        payload,
        guard=guard,
        session_id=normalized_session_id,
        allowed_roots=[trace_root],
    )
    write_session_trace_summary(
        base_dir=normalized_base_dir,
        session_id=normalized_session_id,
        guard=guard,
        context=summary_context,
    )
    return payload


def trace_contract_status_from_mapping(
    *,
    base_dir: Path,
    session_id: str,
    checkpoint: str,
    container: Mapping[str, Any] | None,
    container_name: str,
    source_file: str | Path,
    guard: Any | None = None,
    summary_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    mapping = container if isinstance(container, Mapping) else {}
    field_exists = CONTRACT_STATUS_FIELD in mapping
    return trace_contract_status(
        base_dir=base_dir,
        session_id=session_id,
        checkpoint=checkpoint,
        contract_status=mapping.get(CONTRACT_STATUS_FIELD, ""),
        field_exists=field_exists,
        container_name=container_name,
        source_file=source_file,
        guard=guard,
        summary_context=summary_context,
    )


def write_session_trace_summary(
    *,
    base_dir: Path,
    session_id: str,
    guard: Any | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_base_dir = Path(base_dir).resolve()
    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        return {}

    trace_root = normalized_base_dir / TRACE_ROOT
    existing_summary = _load_json(_summary_path(normalized_base_dir, normalized_session_id))
    checkpoint_payloads = {
        checkpoint: _load_json(_checkpoint_path(normalized_base_dir, normalized_session_id, checkpoint))
        for checkpoint in CHECKPOINTS
    }
    timeline = [_summary_timeline_entry(checkpoint_payloads[checkpoint], checkpoint) for checkpoint in CHECKPOINTS]
    last_observed_index = _last_observed_index(timeline)
    first_nonblank_index = _first_nonblank_index(timeline)
    first_lost_checkpoint, loss_reason, loss_classification = _classify_loss(timeline)
    observed_checkpoint_count = sum(1 for item in timeline if item["observed"])
    run_context = _merge_context(existing_summary.get("run_context"), context)
    summary = {
        "session_id": normalized_session_id,
        "generated_at": utc_now_iso(),
        "trace_root": str(_session_dir(normalized_base_dir, normalized_session_id)),
        "expected_checkpoints": list(CHECKPOINTS),
        "observed_checkpoints": [item["checkpoint"] for item in timeline if item["observed"]],
        "observed_checkpoint_count": observed_checkpoint_count,
        "last_observed_checkpoint": CHECKPOINTS[last_observed_index] if last_observed_index >= 0 else "",
        "first_nonblank_checkpoint": CHECKPOINTS[first_nonblank_index] if first_nonblank_index >= 0 else "",
        "first_lost_checkpoint": first_lost_checkpoint,
        "loss_reason": loss_reason,
        "loss_classification": loss_classification,
        "all_checkpoints_observed": observed_checkpoint_count == len(CHECKPOINTS),
        "run_context": run_context,
        "timeline": timeline,
    }
    _write_payload(
        _summary_path(normalized_base_dir, normalized_session_id),
        summary,
        guard=guard,
        session_id=normalized_session_id,
        allowed_roots=[trace_root],
    )
    return summary


def load_session_trace_summary(*, base_dir: Path, session_id: str) -> dict[str, Any]:
    return _load_json(_summary_path(Path(base_dir).resolve(), str(session_id or "").strip()))


def _row_context(row: Mapping[str, Any]) -> dict[str, Any]:
    return _normalize_context(row)


def _branch_key(summary: Mapping[str, Any]) -> str:
    context = summary.get("run_context") if isinstance(summary.get("run_context"), Mapping) else {}
    bucket = str(context.get("bucket", "")).strip()
    category = str(context.get("category", "")).strip()
    if bucket and category:
        return f"{bucket}/{category}"
    if category:
        return category
    if bucket:
        return bucket
    return "unknown"


def _issue_scope(summaries: Sequence[Mapping[str, Any]]) -> tuple[str, list[str]]:
    affected = [
        summary
        for summary in summaries
        if str(summary.get("loss_classification", "")).strip() not in {_LOSS_INTACT, _LOSS_PENDING, ""}
    ]
    if not affected:
        return "no loss observed", []
    if len(affected) == len(summaries):
        return "universal", sorted({_branch_key(summary) for summary in affected})
    return "branch-specific", sorted({_branch_key(summary) for summary in affected})


def _render_counter(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"{key}={counter[key]}" for key in sorted(counter))


def _timeline_state_map(summary: Mapping[str, Any]) -> dict[str, str]:
    timeline = summary.get("timeline") if isinstance(summary.get("timeline"), list) else []
    return {
        str(item.get("checkpoint", "")).strip(): _summary_state_label(item)
        for item in timeline
        if isinstance(item, Mapping)
    }


def write_contract_trace_report(
    *,
    base_dir: Path,
    report_path: Path,
    sessions: Sequence[Mapping[str, Any]] | Sequence[str],
    guard: Any | None = None,
) -> str:
    normalized_base_dir = Path(base_dir).resolve()
    normalized_report_path = Path(report_path).resolve()
    trace_root = normalized_base_dir / TRACE_ROOT

    session_contexts: dict[str, dict[str, Any]] = {}
    session_order: list[str] = []
    for item in sessions:
        if isinstance(item, Mapping):
            session_id = str(item.get("session_id", "")).strip()
            context = _row_context(item)
        else:
            session_id = str(item or "").strip()
            context = {}
        if not session_id:
            continue
        session_contexts[session_id] = _merge_context(session_contexts.get(session_id), context)
        if session_id not in session_order:
            session_order.append(session_id)

    summaries: list[dict[str, Any]] = []
    for session_id in session_order:
        summaries.append(
            write_session_trace_summary(
                base_dir=normalized_base_dir,
                session_id=session_id,
                guard=guard,
                context=session_contexts.get(session_id),
            )
        )

    affected = [
        summary
        for summary in summaries
        if str(summary.get("loss_classification", "")).strip() not in {_LOSS_INTACT, _LOSS_PENDING, ""}
    ]
    first_lost_counts = Counter(
        str(summary.get("first_lost_checkpoint", "")).strip()
        for summary in affected
        if str(summary.get("first_lost_checkpoint", "")).strip()
    )
    loss_classification_counts = Counter(
        str(summary.get("loss_classification", "")).strip()
        for summary in affected
        if str(summary.get("loss_classification", "")).strip()
    )
    issue_scope, affected_branches = _issue_scope(summaries)

    overall_first_lost_checkpoint = ""
    if first_lost_counts:
        overall_first_lost_checkpoint = min(first_lost_counts, key=lambda item: _CHECKPOINT_ORDER.get(item, len(CHECKPOINTS)))
    overall_issue_shape = "mixed"
    if len(loss_classification_counts) == 1:
        overall_issue_shape = next(iter(loss_classification_counts))
    elif not loss_classification_counts:
        overall_issue_shape = _LOSS_INTACT

    lines = [
        "# Contract Trace Report",
        "",
        f"- Generated at: `{utc_now_iso()}`",
        f"- Sessions traced: `{len(summaries)}`",
        f"- Sessions with contract_status loss: `{len(affected)}`",
        f"- First checkpoint where contract_status is lost: `{overall_first_lost_checkpoint or 'none'}`",
        f"- Issue shape: `{overall_issue_shape}`",
        f"- Scope: `{issue_scope}`",
    ]
    if affected_branches:
        lines.append(f"- Affected branches: `{', '.join(affected_branches)}`")
    lines.extend(
        [
            f"- First lost checkpoint counts: `{_render_counter(first_lost_counts)}`",
            f"- Loss classification counts: `{_render_counter(loss_classification_counts)}`",
            "",
            "## Per Session",
            "",
            "| session_id | branch | first_lost_checkpoint | loss_classification | CONTRACT_CREATED | CONTRACT_RETURNED | CONTRACT_ATTACHED | CONTRACT_METADATA | CONTRACT_LEDGER |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    for summary in summaries:
        states = _timeline_state_map(summary)
        lines.append(
            "| {session_id} | {branch} | {first_lost_checkpoint} | {loss_classification} | {created} | {returned} | {attached} | {metadata} | {ledger} |".format(
                session_id=str(summary.get("session_id", "")).strip() or "-",
                branch=_branch_key(summary),
                first_lost_checkpoint=str(summary.get("first_lost_checkpoint", "")).strip() or "-",
                loss_classification=str(summary.get("loss_classification", "")).strip() or "-",
                created=states.get("CONTRACT_CREATED", "MISSING"),
                returned=states.get("CONTRACT_RETURNED", "MISSING"),
                attached=states.get("CONTRACT_ATTACHED", "MISSING"),
                metadata=states.get("CONTRACT_METADATA", "MISSING"),
                ledger=states.get("CONTRACT_LEDGER", "MISSING"),
            )
        )

    report_text = "\n".join(lines) + "\n"
    _write_text(
        normalized_report_path,
        report_text,
        guard=guard,
        session_id="",
        allowed_roots=[normalized_report_path.parent, trace_root],
    )
    return report_text
