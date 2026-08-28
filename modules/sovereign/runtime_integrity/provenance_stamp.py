from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .root_authority import ACTIVE_D_ROOT, classify_root, detect_root_mismatch, normalize_windows_path

ROOT_STAMP_SCHEMA_VERSION = "21.5C"
CANONICAL_PROVENANCE_FIELDS = (
    "runtime_root",
    "broker_root",
    "root_classification",
    "broker_root_verified",
    "root_stamp_schema_version",
)
ROOT_FIELD_ALIASES = CANONICAL_PROVENANCE_FIELDS + (
    "root",
    "repo_root",
    "root_path",
)

BROKER_ROOT_RE = re.compile(r"BROKER_ROOT=([^\r\n]+)")
COMMAND_ROOT_RE = re.compile(r"(?:^|\s)-Root\s+(?:\"([^\"]+)\"|(\S+))", re.IGNORECASE)


def _resolved_path_text(path: str | Path) -> str:
    value = str(path or "").strip()
    if not value:
        return ""
    return str(Path(value).expanduser().resolve(strict=False))


def build_canonical_provenance(runtime_root: str | Path, broker_root: str | Path) -> dict[str, Any]:
    runtime_text = _resolved_path_text(runtime_root)
    broker_text = _resolved_path_text(broker_root)
    runtime_classification = classify_root(runtime_text) if runtime_text else ""
    broker_root_verified = bool(runtime_text and broker_text) and not detect_root_mismatch(runtime_text, broker_text)
    canonical_classification = ACTIVE_D_ROOT if broker_root_verified and runtime_classification == ACTIVE_D_ROOT else runtime_classification
    return {
        "runtime_root": runtime_text,
        "broker_root": broker_text,
        "root_classification": canonical_classification,
        "broker_root_verified": broker_root_verified,
        "root_stamp_schema_version": ROOT_STAMP_SCHEMA_VERSION,
    }


def attach_canonical_provenance(payload: dict[str, Any], runtime_root: str | Path, broker_root: str | Path) -> dict[str, Any]:
    enriched = dict(payload)
    enriched.update(build_canonical_provenance(runtime_root, broker_root))
    return enriched


def parse_command_root(command_text: str) -> str:
    match = COMMAND_ROOT_RE.search(str(command_text or ""))
    if not match:
        return ""
    return _resolved_path_text(match.group(1) or match.group(2) or "")


def extract_broker_root_from_text(text: str) -> str:
    match = BROKER_ROOT_RE.search(str(text or ""))
    if not match:
        return ""
    return _resolved_path_text(match.group(1).strip())


def collect_root_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    found: dict[str, Any] = {}

    def visit(node: dict[str, Any], prefix: str = "") -> None:
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else key
            if key in ROOT_FIELD_ALIASES and not isinstance(value, (dict, list)):
                found[path] = value
            if isinstance(value, dict):
                visit(value, path)

    visit(payload)
    return found


def _candidate_views(payload: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(payload, dict):
        return []
    candidates: list[tuple[str, dict[str, Any]]] = [("top_level", payload)]
    for key in ("provenance", "runtime_provenance"):
        candidate = payload.get(key)
        if isinstance(candidate, dict):
            candidates.append((key, candidate))
    return candidates


def canonical_provenance_status(payload: dict[str, Any] | None, expected_root: str | Path) -> dict[str, Any]:
    expected_root_text = _resolved_path_text(expected_root)
    expected_normalized = normalize_windows_path(expected_root_text)
    best = {
        "present": False,
        "candidate_name": "",
        "runtime_root": "",
        "broker_root": "",
        "root_classification": "",
        "broker_root_verified": None,
        "root_stamp_schema_version": "",
        "missing_canonical_fields": list(CANONICAL_PROVENANCE_FIELDS),
        "root_stamp_found": False,
        "canonical_complete": False,
        "issues": [],
    }
    best_score = -1

    for candidate_name, candidate in _candidate_views(payload):
        present_fields = [field for field in CANONICAL_PROVENANCE_FIELDS if field in candidate]
        if not present_fields and "runtime_root" not in candidate and "broker_root" not in candidate:
            continue

        runtime_root = str(candidate.get("runtime_root", "")).strip()
        broker_root = str(candidate.get("broker_root", "")).strip()
        root_classification = str(candidate.get("root_classification", "")).strip()
        broker_root_verified = candidate.get("broker_root_verified")
        schema_version = str(candidate.get("root_stamp_schema_version", "")).strip()
        missing = [field for field in CANONICAL_PROVENANCE_FIELDS if candidate.get(field) in (None, "", [])]
        normalized_runtime = normalize_windows_path(runtime_root) if runtime_root else ""
        normalized_broker = normalize_windows_path(broker_root) if broker_root else ""
        root_stamp_found = bool(runtime_root and broker_root) and normalized_runtime == expected_normalized and normalized_broker == expected_normalized

        issues: list[str] = []
        if runtime_root and normalized_runtime != expected_normalized:
            issues.append(f"runtime_root mismatch: {runtime_root}")
        if broker_root and normalized_broker != expected_normalized:
            issues.append(f"broker_root mismatch: {broker_root}")
        if root_classification and root_classification != ACTIVE_D_ROOT:
            issues.append(f"root_classification was {root_classification}")
        if broker_root_verified not in (None, True):
            issues.append(f"broker_root_verified was {broker_root_verified}")
        if schema_version and schema_version != ROOT_STAMP_SCHEMA_VERSION:
            issues.append(f"root_stamp_schema_version was {schema_version}")

        canonical_complete = (
            not missing
            and root_stamp_found
            and root_classification == ACTIVE_D_ROOT
            and broker_root_verified is True
            and schema_version == ROOT_STAMP_SCHEMA_VERSION
        )
        score = len(present_fields)
        if canonical_complete:
            score += 100
        elif root_stamp_found:
            score += 10

        if score > best_score:
            best_score = score
            best = {
                "present": True,
                "candidate_name": candidate_name,
                "runtime_root": runtime_root,
                "broker_root": broker_root,
                "root_classification": root_classification,
                "broker_root_verified": broker_root_verified,
                "root_stamp_schema_version": schema_version,
                "missing_canonical_fields": missing,
                "root_stamp_found": root_stamp_found,
                "canonical_complete": canonical_complete,
                "issues": issues,
            }

    return best


def evaluate_root_stamp(
    *,
    expected_root: str | Path,
    command_text: str = "",
    campaign_runtime_root: str | Path = "",
    stdout_text: str = "",
    live_activation_report: dict[str, Any] | None = None,
    turn_manifest: dict[str, Any] | None = None,
    contract_executed: dict[str, Any] | None = None,
    role_model_mapping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact_statuses = {
        "live_activation_report": canonical_provenance_status(live_activation_report, expected_root),
        "turn_manifest": canonical_provenance_status(turn_manifest, expected_root),
        "contract_executed": canonical_provenance_status(contract_executed, expected_root),
        "role_model_mapping": canonical_provenance_status(role_model_mapping, expected_root),
    }

    for source_name in ("live_activation_report", "turn_manifest", "contract_executed", "role_model_mapping"):
        status = artifact_statuses[source_name]
        if status["root_stamp_found"]:
            return {
                "root_stamp_found": True,
                "runtime_root": status["runtime_root"],
                "broker_root": status["broker_root"],
                "source": source_name,
                "artifact_statuses": artifact_statuses,
            }

    command_root = parse_command_root(command_text) or _resolved_path_text(campaign_runtime_root)
    broker_root = extract_broker_root_from_text(stdout_text)
    expected_normalized = normalize_windows_path(expected_root)
    legacy_root_stamp_found = bool(command_root and broker_root) and normalize_windows_path(command_root) == expected_normalized and normalize_windows_path(broker_root) == expected_normalized

    return {
        "root_stamp_found": legacy_root_stamp_found,
        "runtime_root": command_root if legacy_root_stamp_found else command_root or _resolved_path_text(campaign_runtime_root),
        "broker_root": broker_root,
        "source": "legacy_command_and_stdout" if legacy_root_stamp_found else "",
        "artifact_statuses": artifact_statuses,
    }
