from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

ARBITRATION_ARTIFACT_SCHEMA_VERSION = "sovereign.arbitration_artifact.v1"
REQUIRED_FIELDS: dict[str, type | tuple[type, ...]] = {
    "schema_version": str,
    "session_id": str,
    "timestamp_utc": str,
    "arbitration_score": (int, float),
    "evidence_overlap": (int, float),
    "unresolved_conflict_count": int,
    "agreed_claims": list,
    "contested_claims": list,
    "one_sided_claims": list,
    "unresolved_conflicts": list,
    "source_paths": list,
    "generation_context": dict,
}
GENERATION_CONTEXT_FIELDS: dict[str, type | tuple[type, ...]] = {
    "run_type": str,
    "batch_id": str,
}


class ArbitrationArtifactValidationError(ValueError):
    pass


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _coerce_string(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _coerce_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _coerce_string(item)
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _metrics_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload.get("metrics")
    if isinstance(metrics, dict):
        return metrics
    metrics = {}
    payload["metrics"] = metrics
    return metrics


def normalize_artifact_payload(
    artifact: dict[str, Any],
    *,
    session_id: str | None = None,
    batch_id: str | None = None,
    run_type: str | None = None,
    source_paths: list[str] | None = None,
    default_batch_id: str = "",
    default_run_type: str = "quality_gate",
) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        raise ArbitrationArtifactValidationError("artifact must be a JSON object")

    payload = copy.deepcopy(artifact)
    if session_id is not None:
        payload["session_id"] = session_id

    schema_version = payload.get("schema_version")
    if schema_version in (None, ""):
        payload["schema_version"] = ARBITRATION_ARTIFACT_SCHEMA_VERSION
    elif schema_version != ARBITRATION_ARTIFACT_SCHEMA_VERSION:
        raise ArbitrationArtifactValidationError(
            f"schema_version must be {ARBITRATION_ARTIFACT_SCHEMA_VERSION!r}, got {schema_version!r}"
        )

    timestamp_utc = _coerce_string(payload.get("timestamp_utc"))
    if not timestamp_utc:
        timestamp_utc = _coerce_string(payload.get("generated_at")) or _coerce_string(payload.get("timestamp"))
    if timestamp_utc:
        payload["timestamp_utc"] = timestamp_utc

    metrics = _metrics_mapping(payload)
    for field_name in ("arbitration_score", "evidence_overlap", "unresolved_conflict_count"):
        top_level_value = payload.get(field_name)
        metric_value = metrics.get(field_name)
        if top_level_value is None and metric_value is not None:
            payload[field_name] = metric_value
        elif top_level_value is not None and metric_value is None:
            metrics[field_name] = top_level_value

    merged_source_paths = _coerce_string_list(payload.get("source_paths"))
    if source_paths:
        merged_source_paths.extend(_coerce_string_list(source_paths))
    artifact_path = _coerce_string(payload.get("artifact_path"))
    if artifact_path:
        merged_source_paths.append(artifact_path)
    payload["source_paths"] = _coerce_string_list(merged_source_paths)

    generation_context = payload.get("generation_context")
    if not isinstance(generation_context, dict):
        generation_context = {}
    generation_context["run_type"] = _coerce_string(run_type) or _coerce_string(generation_context.get("run_type")) or default_run_type
    generation_context["batch_id"] = _coerce_string(batch_id) or _coerce_string(generation_context.get("batch_id")) or default_batch_id
    payload["generation_context"] = generation_context
    return payload


def validate_artifact_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["payload must be an object"]

    for field_name, expected_type in REQUIRED_FIELDS.items():
        if field_name not in payload:
            errors.append(f"missing required field: {field_name}")
            continue
        value = payload[field_name]
        if field_name == "schema_version":
            if value != ARBITRATION_ARTIFACT_SCHEMA_VERSION:
                errors.append(
                    f"invalid field: schema_version expected {ARBITRATION_ARTIFACT_SCHEMA_VERSION!r}, got {value!r}"
                )
            continue
        if field_name in {"arbitration_score", "evidence_overlap"}:
            if not _is_number(value):
                errors.append(f"invalid field: {field_name} must be a number")
            continue
        if field_name == "unresolved_conflict_count":
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(f"invalid field: {field_name} must be an integer")
            continue
        if not isinstance(value, expected_type):
            errors.append(f"invalid field: {field_name} must be {getattr(expected_type, '__name__', expected_type)}")
            continue
        if field_name in {"session_id", "timestamp_utc"} and not _coerce_string(value):
            errors.append(f"invalid field: {field_name} must be a non-empty string")

    generation_context = payload.get("generation_context")
    if isinstance(generation_context, dict):
        for field_name, expected_type in GENERATION_CONTEXT_FIELDS.items():
            if field_name not in generation_context:
                errors.append(f"missing required field: generation_context.{field_name}")
                continue
            value = generation_context[field_name]
            if not isinstance(value, expected_type):
                errors.append(f"invalid field: generation_context.{field_name} must be a string")
                continue
            if not _coerce_string(value) and field_name == "run_type":
                errors.append("invalid field: generation_context.run_type must be a non-empty string")
    else:
        errors.append("invalid field: generation_context must be an object")

    source_paths = payload.get("source_paths")
    if isinstance(source_paths, list):
        for index, item in enumerate(source_paths):
            if not isinstance(item, str) or not item.strip():
                errors.append(f"invalid field: source_paths[{index}] must be a non-empty string")

    metrics = payload.get("metrics")
    if metrics is not None and not isinstance(metrics, dict):
        errors.append("invalid field: metrics must be an object when present")

    for group_name in ("agreed_claims", "contested_claims", "one_sided_claims", "unresolved_conflicts"):
        value = payload.get(group_name)
        if isinstance(value, list):
            continue
        errors.append(f"invalid field: {group_name} must be an array")

    return errors


def load_artifact(path: str | Path) -> dict[str, Any]:
    artifact_path = Path(path).expanduser().resolve()
    return json.loads(artifact_path.read_text(encoding="utf-8-sig"))


def validate_artifact_file(path: str | Path) -> list[str]:
    payload = load_artifact(path)
    return validate_artifact_payload(payload)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a SOVEREIGN arbitration artifact JSON file.")
    parser.add_argument("artifact_path", help="Path to the arbitration artifact JSON file.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    artifact_path = Path(args.artifact_path).expanduser().resolve()
    try:
        payload = load_artifact(artifact_path)
    except FileNotFoundError:
        print(f"INVALID {artifact_path}")
        print("missing file")
        return 1
    except json.JSONDecodeError as exc:
        print(f"INVALID {artifact_path}")
        print(f"invalid json: {exc}")
        return 1
    except OSError as exc:
        print(f"INVALID {artifact_path}")
        print(f"read error: {exc}")
        return 1

    errors = validate_artifact_payload(payload)
    if errors:
        print(f"INVALID {artifact_path}")
        for error in errors:
            print(error)
        return 1

    print(f"VALID {artifact_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
