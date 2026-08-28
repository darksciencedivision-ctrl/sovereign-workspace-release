from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from distillery.common import ContractError


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_instrumentation_baseline(component: str, baseline: dict) -> None:
    required = {"runtime_repo_path", "runtime_commit_sha", "runtime_dirty", "dirty_file_list", "file_path", "sha256", "captured_at", "capture_authority"}
    missing = required - baseline.keys()
    dirty_files = baseline.get("dirty_file_list")
    if missing:
        raise ContractError(f"checksum baseline provenance incomplete for {component}: missing={sorted(missing)}")
    if type(baseline["runtime_dirty"]) is not bool or not isinstance(dirty_files, list) or not all(isinstance(path, str) and path for path in dirty_files):
        raise ContractError(f"checksum baseline dirty-state provenance invalid for {component}")
    if len(dirty_files) != len(set(dirty_files)) or bool(dirty_files) != baseline["runtime_dirty"]:
        raise ContractError(f"checksum baseline dirty_file_list is not an exact dirty-state record for {component}")
    for field in ("runtime_repo_path", "file_path", "capture_authority"):
        if not isinstance(baseline[field], str) or not baseline[field].strip():
            raise ContractError(f"checksum baseline {field} is required for {component}")
    commit = baseline["runtime_commit_sha"]
    digest = baseline["sha256"]
    if not isinstance(commit, str) or len(commit) not in {40, 64} or any(character not in "0123456789abcdef" for character in commit.lower()):
        raise ContractError(f"checksum baseline runtime_commit_sha is invalid for {component}")
    if not isinstance(digest, str) or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest.lower()):
        raise ContractError(f"checksum baseline sha256 is invalid for {component}")
    try:
        captured = datetime.fromisoformat(baseline["captured_at"].replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ContractError(f"checksum baseline captured_at is invalid for {component}") from exc
    if captured.tzinfo is None or captured.utcoffset() != timedelta(0):
        raise ContractError(f"checksum baseline captured_at must be timezone-aware UTC for {component}")
    captured.astimezone(UTC)


def verify_instrumentation_checksums(expected: dict[str, str | dict], component_paths: dict[str, str | Path]) -> dict:
    if set(expected) != set(component_paths) or not expected:
        raise ContractError("checksum guard requires exact expected component coverage")
    components = {}
    for component in sorted(expected):
        baseline = expected[component]
        if isinstance(baseline, dict):
            validate_instrumentation_baseline(component, baseline)
            expected_hash = baseline["sha256"]
        else:
            expected_hash = baseline
        observed = file_sha256(component_paths[component])
        passed = observed == expected_hash.lower()
        components[component] = {
            "expected_sha256": expected_hash.lower(),
            "observed_sha256": observed,
            "passed": passed,
            "change_classification": "MATCH" if passed else "TAMPER_OR_UNREVIEWED_CHANGE",
            "baseline_provenance": baseline if isinstance(baseline, dict) else None,
        }
    return {
        "passed": all(row["passed"] for row in components.values()),
        "components": components,
        "update_policy": "Only an explicitly authorized recapture may create EXPECTED_BASELINE_UPDATE; an observed mismatch is TAMPER_OR_UNREVIEWED_CHANGE.",
    }
