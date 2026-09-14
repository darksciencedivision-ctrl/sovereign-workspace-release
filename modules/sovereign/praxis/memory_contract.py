from __future__ import annotations

from typing import Any

MEMORY_ELIGIBLE = "MEMORY_ELIGIBLE"
MEMORY_REJECTED = "MEMORY_REJECTED"
MEMORY_REVIEW_REQUIRED = "MEMORY_REVIEW_REQUIRED"
MIN_SELECTION_CONFIDENCE = 0.70
UNVERIFIED_GATE_INPUTS = "UNVERIFIED_GATE_INPUTS"
REQUIRED_VERIFIED_GATE_FIELDS = (
    "selection_status",
    "selection_confidence",
    "validation_status",
    "provenance",
    "source_hash",
    "failed_validation",
    "cosmetic_duplicate",
    "unresolved_contradiction",
    "semantic_duplicate_suspected",
)


def _result(
    memory_decision: str,
    reason: str,
    *,
    tags: list[str] | None = None,
    risk_flags: list[str] | None = None,
    required_verified_fields_missing: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "memory_decision": memory_decision,
        "reason": reason,
        "tags": tags or [],
        "risk_flags": risk_flags or [],
        "required_verified_fields_missing": required_verified_fields_missing or [],
    }


def assess_memory_eligibility(payload: dict[str, Any]) -> dict[str, Any]:
    verified_gate_inputs = payload.get("verified_gate_inputs") if isinstance(payload.get("verified_gate_inputs"), dict) else {}
    verification_errors = [str(item).strip() for item in (payload.get("verification_errors") or []) if str(item).strip()]
    missing_verified_fields = [
        field
        for field in REQUIRED_VERIFIED_GATE_FIELDS
        if field not in verified_gate_inputs
    ]
    risk_flags: list[str] = []
    tags: list[str] = []

    if payload.get("payload_requested_trusted_internal"):
        return _result(
            MEMORY_REJECTED,
            "trusted_internal requests are not authorized for PRAXIS writes.",
            tags=["authorization_rejected"],
            risk_flags=["trusted_internal_requested"],
        )

    if verification_errors or missing_verified_fields:
        reason_parts = []
        if verification_errors:
            reason_parts.append("; ".join(verification_errors))
        if missing_verified_fields:
            reason_parts.append(
                "missing trusted upstream evidence for "
                + ", ".join(sorted(missing_verified_fields))
            )
        return _result(
            MEMORY_REJECTED,
            f"{UNVERIFIED_GATE_INPUTS}: {'; '.join(reason_parts)}",
            tags=["verification_failed"],
            risk_flags=["unverified_gate_inputs"],
            required_verified_fields_missing=missing_verified_fields,
        )

    selection_status = str(verified_gate_inputs.get("selection_status") or "").strip().lower()
    validation_status = str(verified_gate_inputs.get("validation_status") or "").strip().lower()
    confidence = float(verified_gate_inputs.get("selection_confidence", 0.0) or 0.0)
    provenance = verified_gate_inputs.get("provenance") if isinstance(verified_gate_inputs.get("provenance"), dict) else {}
    source_hash = str(verified_gate_inputs.get("source_hash") or "").strip()

    if selection_status in {"abstain", "manual_review"}:
        return _result(
            MEMORY_REJECTED,
            f"Selection status {selection_status or 'unknown'} is not eligible for memory writeback.",
            tags=tags,
            risk_flags=risk_flags,
        )
    if validation_status and validation_status != "pass":
        return _result(
            MEMORY_REJECTED,
            f"Validation status {validation_status} is not eligible for memory writeback.",
            tags=tags,
            risk_flags=risk_flags,
        )
    if confidence < MIN_SELECTION_CONFIDENCE:
        return _result(
            MEMORY_REJECTED,
            f"Selection confidence {confidence:.2f} is below the {MIN_SELECTION_CONFIDENCE:.2f} threshold.",
            tags=tags,
            risk_flags=risk_flags,
        )
    if not provenance:
        return _result(
            MEMORY_REJECTED,
            "Provenance is required for memory writeback eligibility.",
            tags=tags,
            risk_flags=risk_flags,
        )
    if not source_hash:
        return _result(
            MEMORY_REJECTED,
            "source_hash is required for memory writeback eligibility.",
            tags=tags,
            risk_flags=risk_flags,
        )
    if verified_gate_inputs.get("failed_validation"):
        return _result(
            MEMORY_REJECTED,
            "Failed validation artifacts cannot be written to memory.",
            tags=tags,
            risk_flags=risk_flags,
        )
    if verified_gate_inputs.get("cosmetic_duplicate"):
        return _result(
            MEMORY_REJECTED,
            "Cosmetic duplicates are not memory eligible.",
            tags=tags,
            risk_flags=risk_flags,
        )
    if verified_gate_inputs.get("unresolved_contradiction"):
        risk_flags.append("unresolved_contradiction")
        return _result(
            MEMORY_REVIEW_REQUIRED,
            "Unresolved contradiction requires human review before memory writeback.",
            tags=tags,
            risk_flags=risk_flags,
        )
    if verified_gate_inputs.get("semantic_duplicate_suspected"):
        risk_flags.append("semantic_duplicate_suspected")
        return _result(
            MEMORY_REVIEW_REQUIRED,
            "Potential semantic duplicate requires review before memory writeback.",
            tags=tags,
            risk_flags=risk_flags,
        )

    tags.extend(["memory_candidate", "selection_confident"])
    return _result(
        MEMORY_ELIGIBLE,
        "Artifact satisfies the memory eligibility contract.",
        tags=tags,
        risk_flags=risk_flags,
    )
