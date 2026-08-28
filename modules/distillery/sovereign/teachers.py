from __future__ import annotations

"""Sovereign teacher registry tooling.

Deterministic characterization and smallest-to-largest processing support for
heterogeneous Sovereign teachers. Parameter counts are NEVER invented: a
teacher without usable ordering metadata is explicitly classified as
UNORDERED_MISSING_PARAMETER_METADATA with a recorded skip reason instead of
being silently interleaved by filename or registry order.
"""

import json
from pathlib import Path
from typing import Any

from distillery.common import ContractError, sha256_value

REGISTRY_SCHEMA = "sovereign-distillery/teacher_registry/v1-sanitized"
UNORDERED_CLASSIFICATION = "UNORDERED_MISSING_PARAMETER_METADATA"


def load_teacher_registry(path: str | Path) -> dict:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ContractError(f"teacher registry not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ContractError(f"corrupt teacher registry {path}: {exc}") from None
    validate_registry_document(document)
    return document


def validate_registry_document(document: Any) -> dict:
    if not isinstance(document, dict):
        raise ContractError("teacher registry must be an object")
    if document.get("schema") != REGISTRY_SCHEMA:
        raise ContractError(f"unexpected teacher registry schema: {document.get('schema')!r}")
    teachers = document.get("teachers")
    if not isinstance(teachers, list) or not teachers:
        raise ContractError("teacher registry must contain a non-empty teachers array")
    seen: set[str] = set()
    orders: set[int] = set()
    for teacher in teachers:
        model_id = teacher.get("model_id")
        if not isinstance(model_id, str) or not model_id:
            raise ContractError("teacher missing stable model_id")
        if model_id in seen:
            raise ContractError(f"duplicate teacher model_id: {model_id}")
        seen.add(model_id)
        order = teacher.get("teacher_order")
        if not isinstance(order, int) or order < 1:
            raise ContractError(f"teacher {model_id} missing positive integer teacher_order")
        if order in orders:
            raise ContractError(f"duplicate teacher_order {order}")
        orders.add(order)
        for required in ("display_name", "source_runtime", "architecture", "license_class"):
            if not isinstance(teacher.get(required), str) or not teacher[required]:
                raise ContractError(f"teacher {model_id} missing {required}")
    declared = document.get("teacher_count")
    if declared != len(teachers):
        raise ContractError(f"teacher_count mismatch: declared {declared}, actual {len(teachers)}")
    return document


def field_provenance(teacher: dict) -> dict:
    """Classify characterization fields as MEASURED_FROM_ARTIFACT, DERIVED_LABEL, or UNKNOWN."""
    metadata = teacher.get("gguf_metadata") or {}
    parameter_count = teacher.get("parameter_count") or metadata.get("general.parameter_count")
    label_source = "MEASURED_FROM_ARTIFACT" if parameter_count else ("DERIVED_LABEL" if teacher.get("parameter_label") else "UNKNOWN")
    return {
        "architecture": "MEASURED_FROM_ARTIFACT",
        "context_length": "MEASURED_FROM_ARTIFACT" if teacher.get("context_length") else "UNKNOWN",
        "quantization": "MEASURED_FROM_ARTIFACT" if teacher.get("quantization") else "UNKNOWN",
        "disk_size_bytes": "MEASURED_FROM_ARTIFACT",
        "parameter_count": "MEASURED_FROM_ARTIFACT" if parameter_count else "UNKNOWN_NOT_INVENTED",
        "parameter_label": label_source,
        "artifact_content_hash": "MEASURED_FROM_ARTIFACT" if teacher.get("content_hash") else "UNKNOWN_NOT_YET_HASHED",
        "license_class": "PENDING_PRIMARY_TEXT_VERIFICATION" if teacher.get("license_class") == "UNKNOWN" else "VERIFIED_REQUIRED_BEFORE_ELIGIBILITY",
    }


def _ordering_key(teacher: dict) -> tuple:
    metadata = teacher.get("gguf_metadata") or {}
    count = teacher.get("parameter_count") or metadata.get("general.parameter_count")
    if isinstance(count, int) and count > 0:
        return (0, count, teacher["model_id"])
    return (1, 0, teacher["model_id"])


def order_teachers(teachers: list[dict]) -> dict:
    """Deterministic smallest-to-largest processing plan.

    Teachers with a measured GGUF parameter_count are ordered ascending.
    Teachers lacking usable ordering metadata are EXPLICITLY classified
    UNORDERED with a skip reason; they are never silently interleaved.
    """
    ordered = sorted(teachers, key=_ordering_key)
    processing_plan = []
    unordered = []
    position = 0
    for teacher in ordered:
        entry = {
            "model_id": teacher["model_id"],
            "display_name": teacher["display_name"],
            "source_runtime": teacher["source_runtime"],
            "parameter_count": teacher.get("parameter_count"),
            "parameter_label": teacher.get("parameter_label"),
            "license_class": teacher["license_class"],
        }
        if _ordering_key(teacher)[0] == 0:
            position += 1
            entry["processing_position"] = position
            entry["disposition"] = "ORDERED_BY_MEASURED_PARAMETER_COUNT"
            processing_plan.append(entry)
        else:
            entry["processing_position"] = None
            entry["skip_reason"] = UNORDERED_CLASSIFICATION + ": no measured general.parameter_count in GGUF metadata"
            unordered.append(entry)
    return {
        "processing_plan": processing_plan,
        "unordered_explicit": unordered,
        "plan_hash": sha256_value({"ordered": processing_plan, "unordered": unordered}),
    }


def eligibility_interaction(teacher: dict, source_admission_class: str) -> dict:
    """Fail-closed interaction between teacher license state and admission class."""
    from source_admission import assert_admitted

    assert_admitted(source_admission_class)
    trainable = teacher["license_class"] != "UNKNOWN"
    return {
        "model_id": teacher["model_id"],
        "source_admission_class": source_admission_class,
        "license_verified": trainable,
        "trainable_as_teacher": trainable,
        "reason": None
        if trainable
        else "license_class UNKNOWN: requires verification against primary license text before teacher use",
    }


def capability_delta_record_path(run_root: str | Path, model_id: str, evaluation_suite: str) -> Path:
    """Deterministic evidence path binding a capability-delta record to its teacher."""
    if not model_id or not evaluation_suite:
        raise ContractError("capability delta record path requires model_id and evaluation_suite")
    digest = sha256_value({"model_id": model_id, "evaluation_suite": evaluation_suite})[:16]
    return Path(run_root) / "sovereign-capability-deltas" / f"{model_id}-{evaluation_suite}-{digest}.json"


__all__ = [
    "REGISTRY_SCHEMA",
    "UNORDERED_CLASSIFICATION",
    "load_teacher_registry",
    "validate_registry_document",
    "field_provenance",
    "order_teachers",
    "eligibility_interaction",
    "capability_delta_record_path",
]
