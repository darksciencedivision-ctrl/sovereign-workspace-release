from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    from .memory_contract import REQUIRED_VERIFIED_GATE_FIELDS, assess_memory_eligibility
except ImportError:
    from memory_contract import REQUIRED_VERIFIED_GATE_FIELDS, assess_memory_eligibility

MODULE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = MODULE_ROOT.parent
CANONICAL_SELECTION_LEDGER_PATH = (REPO_ROOT / "evaluation" / "selection" / "selection_ledger.jsonl").resolve()
TRUSTED_SELECTION_LEDGER_PATHS: tuple[Path, ...] = tuple(
    path
    for path in (CANONICAL_SELECTION_LEDGER_PATH,)
    if path.exists() and path.is_file()
)
TRUSTED_CANDIDATE_ROOTS: tuple[Path, ...] = ()
PAYLOAD_GATE_FIELDS = (
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
BOOLEAN_GATE_FIELDS = {
    "failed_validation",
    "cosmetic_duplicate",
    "unresolved_contradiction",
    "semantic_duplicate_suspected",
}
TRUSTED_LEDGER_REQUIRED_FIELDS = (
    "candidate_file",
    "source_hash",
    "selection_status",
    "selection_confidence",
    "validation_status",
    "provenance",
    "failed_validation",
    "cosmetic_duplicate",
    "unresolved_contradiction",
    "semantic_duplicate_suspected",
)


def _coerce_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_hash(value: Any) -> str:
    return _normalize_text(value).lower()


def _resolve_path(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (REPO_ROOT / candidate).resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        raw = line.strip()
        if not raw:
            continue
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _normalize_windows_path(value: str) -> str:
    return str(Path(value)).replace("/", "\\").lower()


def _normalize_provenance(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    text = _normalize_text(value)
    if text:
        return {"value": text}
    return {}


def _normalize_entry_payload(entry: dict[str, Any]) -> dict[str, str]:
    entry_type = _normalize_text(entry.get("type")).lower()
    channel = _normalize_text(entry.get("channel")).lower()
    content = _normalize_text(entry.get("content", entry.get("text", "")))
    return {
        "type": entry_type,
        "channel": channel,
        "content": content,
    }


def _entries_hash(entries: Any) -> str:
    normalized_entries: list[dict[str, str]] = []
    if not isinstance(entries, list):
        return ""
    for entry in entries:
        if not isinstance(entry, dict):
            normalized_entries.append({"type": "", "channel": "", "content": _normalize_text(entry)})
            continue
        normalized_entries.append(_normalize_entry_payload(entry))
    payload = json.dumps(normalized_entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _candidate_entries_from_file(path: Path) -> tuple[list[dict[str, str]], str]:
    text = path.read_text(encoding="utf-8-sig")
    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized_text:
        raise ValueError("verified candidate_file content is empty")
    entries = [
        {
            "type": "synthesis",
            "channel": "canonical",
            "content": normalized_text,
        }
    ]
    return entries, _entries_hash(entries)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _trusted_root_policy() -> dict[str, Any]:
    return {
        "selection_ledger_paths": [str(path) for path in TRUSTED_SELECTION_LEDGER_PATHS],
        "candidate_roots": [str(path.resolve()) for path in TRUSTED_CANDIDATE_ROOTS],
        "candidate_policy": "trusted_ledger_row_reference" if not TRUSTED_CANDIDATE_ROOTS else "trusted_root_containment",
        "selection_ledger_policy": "exact_path_allowlist",
    }


def _resolve_trusted_selection_ledger_path(raw_path: str) -> Path:
    if not TRUSTED_SELECTION_LEDGER_PATHS:
        raise ValueError("no code-owned canonical trusted selection ledger path is configured")
    resolved = _resolve_path(raw_path)
    if resolved not in TRUSTED_SELECTION_LEDGER_PATHS:
        raise ValueError(f"selection_ledger_path is outside the trusted ledger allowlist: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"selection_ledger_path is not readable: {resolved}")
    return resolved


def _resolve_trusted_candidate_path(raw_path: str) -> Path:
    resolved = _resolve_path(raw_path)
    if TRUSTED_CANDIDATE_ROOTS:
        resolved_roots = tuple(root.resolve() for root in TRUSTED_CANDIDATE_ROOTS)
        if not any(_is_relative_to(resolved, root) for root in resolved_roots):
            raise ValueError(f"candidate_file is outside the trusted candidate roots: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"candidate_file is not readable: {resolved}")
    return resolved


def _selection_status_from_record(record: dict[str, Any]) -> str:
    explicit = _normalize_text(record.get("selection_status")).lower()
    if explicit:
        return explicit
    winner = _normalize_text(record.get("winner")).lower()
    if _coerce_bool(record.get("abstained")) or winner == "abstain":
        return "abstain"
    if _coerce_bool(record.get("human_review_required")) or winner in {"equivalent", "incomparable", "contradiction"}:
        return "manual_review"
    if winner in {"a", "b"}:
        return "selected"
    return ""


def _selection_confidence_from_record(record: dict[str, Any]) -> float | None:
    for key in ("selection_confidence", "confidence"):
        if key not in record:
            continue
        try:
            return float(record.get(key, 0.0) or 0.0)
        except (TypeError, ValueError):
            return None
    return None


def _extract_requested_fields(payload: dict[str, Any]) -> dict[str, Any]:
    raw_fields = payload.get("payload_gate_fields") if isinstance(payload.get("payload_gate_fields"), dict) else {}
    if raw_fields:
        requested = dict(raw_fields)
    else:
        requested = {field: payload[field] for field in PAYLOAD_GATE_FIELDS if field in payload}
    provenance = _coerce_dict(requested.get("provenance"))
    payload_provenance = _coerce_dict(payload.get("provenance"))
    if "candidate_file" not in provenance and "candidate_file" in payload_provenance:
        provenance["candidate_file"] = payload_provenance["candidate_file"]
    if "selection_ledger_path" not in provenance and "selection_ledger_path" in payload_provenance:
        provenance["selection_ledger_path"] = payload_provenance["selection_ledger_path"]
    if "candidate_file" not in provenance and "candidate_file" in payload:
        provenance["candidate_file"] = payload["candidate_file"]
    if "selection_ledger_path" not in provenance and "selection_ledger_path" in payload:
        provenance["selection_ledger_path"] = payload["selection_ledger_path"]
    if provenance:
        requested["provenance"] = provenance
    return requested


def _find_matching_selection_record(
    records: list[dict[str, Any]],
    *,
    candidate_file: Path | None,
    source_hash: str,
    artifact_id: str,
    selection_id: str,
) -> tuple[int | None, dict[str, Any] | None, list[str], bool]:
    matches: list[tuple[int, dict[str, Any], list[str]]] = []
    normalized_candidate = _normalize_windows_path(str(candidate_file)) if candidate_file is not None else ""
    for index, record in enumerate(records):
        reasons: list[str] = []
        record_selection_id = _normalize_text(record.get("selection_id"))
        record_artifact_id = _normalize_text(record.get("artifact_id"))
        record_candidate = _normalize_text(record.get("candidate_file"))
        record_source_hash = _normalize_hash(record.get("source_hash"))
        if selection_id and record_selection_id == selection_id:
            reasons.append("selection_id")
        if artifact_id and record_artifact_id == artifact_id:
            reasons.append("artifact_id")
        if normalized_candidate and record_candidate:
            try:
                resolved_record_candidate = _resolve_path(record_candidate)
            except OSError:
                resolved_record_candidate = None
            if resolved_record_candidate is not None and _normalize_windows_path(str(resolved_record_candidate)) == normalized_candidate:
                reasons.append("candidate_file")
        if source_hash and record_source_hash == source_hash:
            reasons.append("source_hash")
        if reasons:
            matches.append((index, record, reasons))
    if not matches:
        return None, None, [], False
    if len(matches) == 1:
        index, record, reasons = matches[0]
        return index, record, reasons, False
    max_reasons = max(len(reasons) for _, _, reasons in matches)
    strongest = [item for item in matches if len(item[2]) == max_reasons]
    if len(strongest) == 1:
        index, record, reasons = strongest[0]
        return index, record, reasons, False
    return None, None, [], True


def _trusted_ledger_row_id(record: dict[str, Any], row_index: int | None) -> str:
    for key in ("selection_id", "artifact_id", "timestamp"):
        value = _normalize_text(record.get(key))
        if value:
            return f"{key}:{value}"
    if row_index is not None:
        return f"row_index:{row_index}"
    return "row:unknown"


def _missing_trusted_fields(record: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not _normalize_text(record.get("candidate_file")):
        missing.append("candidate_file")
    if not _normalize_hash(record.get("source_hash")):
        missing.append("source_hash")
    if not _selection_status_from_record(record):
        missing.append("selection_status")
    if _selection_confidence_from_record(record) is None:
        missing.append("selection_confidence")
    if not _normalize_text(record.get("validation_status")):
        missing.append("validation_status")
    if not _normalize_provenance(record.get("provenance")):
        missing.append("provenance")
    for field in BOOLEAN_GATE_FIELDS:
        if field not in record:
            missing.append(field)
    return sorted(set(missing))


def _build_unverified_payload_fields(
    requested_fields: dict[str, Any],
    verified_gate_inputs: dict[str, Any],
) -> list[str]:
    unverified: set[str] = set()
    for key, requested_value in requested_fields.items():
        if key == "provenance":
            requested_provenance = _coerce_dict(requested_value)
            verified_provenance = _coerce_dict(verified_gate_inputs.get("provenance"))
            for provenance_key in sorted(requested_provenance):
                if provenance_key not in {"candidate_file", "selection_ledger_path"}:
                    unverified.add(f"provenance.{provenance_key}")
                    continue
                if _normalize_text(requested_provenance.get(provenance_key)) != _normalize_text(verified_provenance.get(provenance_key)):
                    unverified.add(f"provenance.{provenance_key}")
            continue
        if key not in verified_gate_inputs:
            unverified.add(key)
            continue
        verified_value = verified_gate_inputs.get(key)
        if key in BOOLEAN_GATE_FIELDS:
            if _coerce_bool(requested_value) != _coerce_bool(verified_value):
                unverified.add(key)
            continue
        if key == "selection_confidence":
            try:
                if float(requested_value) != float(verified_value):
                    unverified.add(key)
            except (TypeError, ValueError):
                unverified.add(key)
            continue
        if key == "source_hash":
            if _normalize_hash(requested_value) != _normalize_hash(verified_value):
                unverified.add(key)
            continue
        if _normalize_text(requested_value).lower() != _normalize_text(verified_value).lower():
            unverified.add(key)
    return sorted(unverified)


def evaluate_memory_gate(payload: dict[str, Any]) -> dict[str, Any]:
    requested_fields = _extract_requested_fields(payload)
    requested_provenance = _coerce_dict(requested_fields.get("provenance"))
    verification_errors: list[str] = []
    verified_gate_inputs: dict[str, Any] = {}
    authorized_entries: list[dict[str, str]] = []
    missing_trusted_fields: list[str] = []
    trusted_root_policy = _trusted_root_policy()

    candidate_file_raw = _normalize_text(requested_provenance.get("candidate_file"))
    selection_ledger_path_raw = _normalize_text(requested_provenance.get("selection_ledger_path"))
    requested_source_hash = _normalize_hash(requested_fields.get("source_hash"))
    artifact_id = _normalize_text(payload.get("artifact_id"))
    selection_id = _normalize_text(payload.get("selection_id"))
    requested_entries = payload.get("entries")
    requested_entries_hash = _entries_hash(requested_entries)
    requested_candidate_path: Path | None = None
    selection_ledger_path: Path | None = None
    verified_candidate_path: Path | None = None
    verified_candidate_file_hash = ""
    authorized_source_hash = ""
    authorized_entries_hash = ""
    committed_content_hash = ""
    trusted_ledger_row_id = ""
    content_binding_method = "fail_closed"
    content_binding_result = "unavailable_or_untrusted"
    payload_entries_used_for_write = False
    entries_derived_from_verified_candidate = False

    if candidate_file_raw:
        try:
            requested_candidate_path = _resolve_path(candidate_file_raw)
        except OSError as exc:
            verification_errors.append(f"candidate_file provenance could not be resolved: {exc}")

    if not selection_ledger_path_raw:
        verification_errors.append("selection_ledger_path provenance is required to verify selection evidence")
    else:
        try:
            selection_ledger_path = _resolve_trusted_selection_ledger_path(selection_ledger_path_raw)
        except (OSError, ValueError) as exc:
            verification_errors.append(str(exc))

    if not candidate_file_raw and not requested_source_hash and not artifact_id and not selection_id:
        verification_errors.append("candidate lookup hint is required (candidate_file, source_hash, artifact_id, or selection_id)")

    if selection_ledger_path is not None and selection_ledger_path.is_file():
        try:
            ledger_rows = _load_jsonl_rows(selection_ledger_path)
        except (OSError, json.JSONDecodeError) as exc:
            verification_errors.append(f"selection_ledger_path could not be parsed: {exc}")
        else:
            row_index, matched_record, match_reasons, ambiguous_match = _find_matching_selection_record(
                ledger_rows,
                candidate_file=requested_candidate_path,
                source_hash=requested_source_hash,
                artifact_id=artifact_id,
                selection_id=selection_id,
            )
            if ambiguous_match:
                verification_errors.append("selection_ledger_path contains multiple matching trusted ledger rows")
            elif matched_record is None:
                verification_errors.append(
                    "selection_ledger_path does not contain a matching trusted ledger row for the supplied lookup hints"
                )
            else:
                trusted_ledger_row_id = _trusted_ledger_row_id(matched_record, row_index)
                missing_trusted_fields = _missing_trusted_fields(matched_record)
                if missing_trusted_fields:
                    verification_errors.append(
                        "trusted ledger row is missing required authorization fields: "
                        + ", ".join(missing_trusted_fields)
                    )
                authorized_source_hash = _normalize_hash(matched_record.get("source_hash"))
                trusted_candidate_file_raw = _normalize_text(matched_record.get("candidate_file"))
                if trusted_candidate_file_raw:
                    try:
                        verified_candidate_path = _resolve_trusted_candidate_path(trusted_candidate_file_raw)
                    except (OSError, ValueError) as exc:
                        verification_errors.append(str(exc))
                    else:
                        if requested_candidate_path is not None and requested_candidate_path != verified_candidate_path:
                            verification_errors.append(
                                "payload candidate_file does not match the trusted ledger candidate_file"
                            )
                        verified_candidate_file_hash = _sha256_file(verified_candidate_path)
                        if authorized_source_hash and verified_candidate_file_hash != authorized_source_hash:
                            verification_errors.append(
                                "trusted ledger source_hash does not match the recomputed trusted candidate_file SHA-256"
                            )
                        elif requested_source_hash and requested_source_hash != authorized_source_hash:
                            verification_errors.append(
                                "payload source_hash does not match the trusted ledger source_hash"
                            )
                        else:
                            try:
                                authorized_entries, authorized_entries_hash = _candidate_entries_from_file(verified_candidate_path)
                            except (OSError, UnicodeDecodeError, ValueError) as exc:
                                verification_errors.append(f"verified candidate_file content could not be derived: {exc}")
                            else:
                                committed_content_hash = authorized_entries_hash
                                content_binding_method = "candidate_file_derived"
                                entries_derived_from_verified_candidate = True
                                if requested_entries_hash and requested_entries_hash != authorized_entries_hash:
                                    content_binding_result = "mismatch"
                                    verification_errors.append(
                                        "payload entries do not match the verified candidate-derived content"
                                    )
                                else:
                                    content_binding_result = "bound"

                selection_status = _selection_status_from_record(matched_record)
                confidence = _selection_confidence_from_record(matched_record)
                trusted_provenance = _normalize_provenance(matched_record.get("provenance"))
                if selection_status:
                    verified_gate_inputs["selection_status"] = selection_status
                if confidence is not None:
                    verified_gate_inputs["selection_confidence"] = confidence
                if "validation_status" in matched_record:
                    verified_gate_inputs["validation_status"] = _normalize_text(matched_record.get("validation_status")).lower()
                for field in BOOLEAN_GATE_FIELDS:
                    if field in matched_record:
                        verified_gate_inputs[field] = _coerce_bool(matched_record.get(field))
                if authorized_source_hash:
                    verified_gate_inputs["source_hash"] = authorized_source_hash
                if trusted_provenance and verified_candidate_path is not None:
                    verified_gate_inputs["provenance"] = {
                        "candidate_file": str(verified_candidate_path),
                        "selection_ledger_path": str(selection_ledger_path),
                        "trusted_ledger_row_id": trusted_ledger_row_id,
                        "trusted_provenance": trusted_provenance,
                        "selection_record_match": ",".join(match_reasons),
                    }

    contract_payload = {
        "payload_requested_trusted_internal": _coerce_bool(
            payload.get("payload_requested_trusted_internal", payload.get("trusted_internal"))
        ),
        "verification_errors": verification_errors,
        "verified_gate_inputs": verified_gate_inputs,
    }
    result = assess_memory_eligibility(contract_payload)
    required_missing = [
        field for field in REQUIRED_VERIFIED_GATE_FIELDS if field not in verified_gate_inputs
    ]
    verification_status = "verified" if not verification_errors and not required_missing else "unverified"
    unverified_payload_fields = _build_unverified_payload_fields(requested_fields, verified_gate_inputs)
    if requested_entries_hash and requested_entries_hash != authorized_entries_hash:
        unverified_payload_fields = sorted(set(unverified_payload_fields + ["entries"]))
    result.update(
        {
            "verification_errors": verification_errors,
            "verified_gate_inputs": verified_gate_inputs,
            "authorized_entries": authorized_entries,
            "unverified_payload_fields": unverified_payload_fields,
            "authorization_basis": "gate_memory_decision derived only from trusted ledger fields and candidate_file-derived content binding",
            "verification_status": verification_status,
            "requested_candidate_file": candidate_file_raw,
            "verified_candidate_file": str(verified_candidate_path) if verified_candidate_path is not None else "",
            "requested_selection_ledger_path": selection_ledger_path_raw,
            "verified_selection_ledger_path": str(selection_ledger_path) if selection_ledger_path is not None else "",
            "trusted_root_policy": trusted_root_policy,
            "trusted_ledger_row_id": trusted_ledger_row_id,
            "missing_trusted_fields": missing_trusted_fields,
            "requested_entries_hash": requested_entries_hash,
            "verified_candidate_file_hash": verified_candidate_file_hash,
            "authorized_source_hash": authorized_source_hash,
            "authorized_entries_hash": authorized_entries_hash,
            "committed_content_hash": committed_content_hash,
            "content_binding_method": content_binding_method,
            "content_binding_result": content_binding_result,
            "payload_entries_used_for_write": payload_entries_used_for_write,
            "entries_derived_from_verified_candidate": entries_derived_from_verified_candidate,
        }
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate memory eligibility without writing to PRAXIS.")
    parser.add_argument("--input", default="", help="Optional JSON file containing the memory-gate payload.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.input:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
    else:
        payload = json.load(sys.stdin)
    result = evaluate_memory_gate(payload)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
