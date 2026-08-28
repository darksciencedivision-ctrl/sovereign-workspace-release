from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from distillery.common import ContractError, sha256_value
from source_admission import (
    AdmissionClass,
    assert_admitted,
    assert_snapshot_matches_registry,
    lineage_id,
)

SCRUB_POLICY_VERSION = "1.0"
RETENTION_DURABLE_PROCEDURE = "DURABLE_PROCEDURE"
RETENTION_EPHEMERAL_TRACE = "EPHEMERAL_TRACE"

SECRET_CATEGORIES = ("API_KEY", "CREDENTIAL")
REQUIRED_SCAN_CATEGORIES = ("API_KEY", "CREDENTIAL", "EMAIL", "HOSTNAME", "LOCAL_PATH")

_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("API_KEY", re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|xoxb-[A-Za-z0-9-]{10,})\b")),
    ("CREDENTIAL", re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?token|access[_-]?key)[\"']?\s*[:=]\s*[^\s\"',;]{6,}")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("HOSTNAME", re.compile(r"\b[A-Za-z0-9][A-Za-z0-9-]*\.(?:local|internal|lan|corp)\b", re.IGNORECASE)),
    ("LOCAL_PATH", re.compile(r"(?:[A-Za-z]:\\(?:Users|home)\\[^\\/:\s]+|/(?:home|Users)/[^/:\s]+)")),
)


@dataclass(frozen=True)
class ScrubFinding:
    category: str
    token_hash: str


def scan_text(text: str, *, categories: Iterable[str] = REQUIRED_SCAN_CATEGORIES) -> list:
    if not isinstance(text, str):
        raise ContractError("scrub scan requires string content")
    wanted = set(categories)
    unknown = wanted - set(REQUIRED_SCAN_CATEGORIES)
    if unknown:
        raise ContractError(f"unknown scrub categories requested: {sorted(unknown)}")
    findings = []
    for category, pattern in _PATTERNS:
        if category not in wanted:
            continue
        for match in pattern.finditer(text):
            findings.append(ScrubFinding(category, sha256_value(match.group(0))[:12]))
    return sorted(findings, key=lambda finding: (finding.category, finding.token_hash))


def redact_text(text: str) -> tuple:
    if not isinstance(text, str):
        raise ContractError("scrub redaction requires string content")
    findings = scan_text(text)
    redacted = text
    for category, pattern in _PATTERNS:
        def replace(match: re.Match, category: str = category) -> str:
            return "[REDACTED:" + category + ":" + sha256_value(match.group(0))[:12] + "]"
        redacted = pattern.sub(replace, redacted)
    return redacted, findings


def verify_snapshot_integrity(snapshot: dict) -> None:
    """Fail closed when an admission snapshot blob is forged or internally inconsistent."""
    if not isinstance(snapshot, dict) or not snapshot.get("snapshot_hash"):
        raise ContractError("admission snapshot missing snapshot_hash")
    body = {key: value for key, value in snapshot.items() if key != "snapshot_hash"}
    if snapshot["snapshot_hash"] != sha256_value(body):
        raise ContractError("admission snapshot hash mismatch: forged or corrupt snapshot body")
    state = snapshot.get("admission_state_hash")
    if not isinstance(state, str) or not state:
        raise ContractError("admission snapshot missing admission_state_hash")
    events = snapshot.get("events")
    if not isinstance(events, list):
        raise ContractError("admission snapshot missing event history")


def admit_example(
    example: dict,
    admission_snapshot: dict,
    *,
    client_scope: str,
    admission_registry,
    internal_use_authorized: bool = False,
    mutable_environment_fact: bool = False,
) -> dict:
    """Admit one training example into the normative corpus under the scrub policy.

    Fail closed when: source UNKNOWN/REJECTED/revoked, the snapshot is forged or
    stale relative to the supplied registry (freshness enforcement is structural:
    offline replay must rebuild an AdmissionRegistry from snapshot events), the
    scrub scan is bypassable nowhere, a prohibited secret survives redaction,
    provenance cannot bind the content, client scope is violated, or deletion
    lineage cannot be established.
    """
    if not isinstance(example, dict):
        raise ContractError("corpus example must be a mapping")
    content = example.get("content")
    if not isinstance(content, str):
        raise ContractError("corpus example requires string content to scrub")

    verify_snapshot_integrity(admission_snapshot)
    if admission_registry is not None:
        assert_snapshot_matches_registry(admission_snapshot, admission_registry)

    provider = example.get("provider")
    teacher = example.get("teacher_of_record")
    revision = example.get("source_revision")
    if not all(isinstance(value, str) and value for value in (provider, teacher, revision)):
        raise ContractError("corpus provenance requires provider, teacher_of_record, and source_revision")
    key_index = {
        (row["provider"], row["teacher_or_model_id"], row["revision"]): row["use_class"]
        for row in admission_snapshot.get("sources", [])
    }
    use_class = key_index.get((provider, teacher, revision), AdmissionClass.UNKNOWN.value)
    assert_admitted(use_class, internal_use_authorized=internal_use_authorized)

    if not client_scope or not isinstance(client_scope, str):
        raise ContractError("client scope declaration is required for corpus admission")
    if example.get("client_tag") != client_scope:
        raise ContractError("example client tag outside declared corpus scope")

    source_lineage_id = lineage_id(provider, teacher, revision)
    texts = [content]
    turns = example.get("turns")
    if isinstance(turns, list):
        texts.extend(str(turn) for turn in turns)
    scan_results = []
    redacted_content = None
    for text in texts:
        redacted, findings = redact_text(text)
        if redacted_content is None:
            redacted_content = redacted
        scan_results.extend({"category": finding.category, "token_hash": finding.token_hash} for finding in findings)
    surviving = scan_text(redacted_content, categories=SECRET_CATEGORIES)
    if surviving:
        raise ContractError("prohibited secret survived scrubbing: " + surviving[0].category)

    supplied_hash = example.get("content_hash")
    if supplied_hash is not None and supplied_hash != sha256_value(content):
        raise ContractError("corpus input integrity failure: content_hash does not bind raw content")
    created_at = example.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        raise ContractError("corpus admission requires created_at provenance timestamp")

    record = {
        "scrub_policy_version": SCRUB_POLICY_VERSION,
        "example_id": example.get("sample_id") or "example-" + sha256_value(redacted_content)[:12],
        "channel": example.get("channel"),
        "client_scope": client_scope,
        "retention": RETENTION_EPHEMERAL_TRACE if mutable_environment_fact else RETENTION_DURABLE_PROCEDURE,
        "retrieval_only": bool(mutable_environment_fact),
        "source_lineage": {
            "lineage_id": source_lineage_id,
            "provider": provider,
            "teacher_or_model_id": teacher,
            "revision": revision,
            "use_class": use_class,
            "admission_snapshot_hash": admission_snapshot["snapshot_hash"],
            "admission_state_hash": admission_snapshot["admission_state_hash"],
        },
        "deletion_lineage_ids": [source_lineage_id, "CLIENT:" + client_scope],
        "redactions_applied": len(scan_results),
        "scan_findings": scan_results,
        "redacted_content_hash": sha256_value(redacted_content),
        "raw_content_hash": sha256_value(content),
        "created_at": example.get("created_at"),
    }
    record["record_hash"] = sha256_value({key: value for key, value in record.items() if key != "record_hash"})
    return record


def verify_corpus_admission_record(record: dict) -> None:
    """Re-validate a persisted corpus-admission record fail-closed."""
    if not isinstance(record, dict):
        raise ContractError("corpus admission record must be a mapping")
    required = {
        "scrub_policy_version",
        "example_id",
        "client_scope",
        "retention",
        "source_lineage",
        "deletion_lineage_ids",
        "scan_findings",
        "redacted_content_hash",
        "record_hash",
    }
    missing = required - record.keys()
    if missing:
        raise ContractError("corpus admission record missing fields: " + str(sorted(missing)))
    lineage = record["source_lineage"]
    if not isinstance(lineage, dict) or not lineage.get("use_class"):
        raise ContractError("corpus admission record lacks source lineage provenance")
    assert_admitted(lineage["use_class"])
    if record["deletion_lineage_ids"] and lineage.get("lineage_id") not in record["deletion_lineage_ids"]:
        raise ContractError("corpus deletion lineage does not include source lineage id")
    body = {key: value for key, value in record.items() if key != "record_hash"}
    if record["record_hash"] != sha256_value(body):
        raise ContractError("corpus admission record hash mismatch: tampered record")


__all__ = [
    "SCRUB_POLICY_VERSION",
    "RETENTION_DURABLE_PROCEDURE",
    "RETENTION_EPHEMERAL_TRACE",
    "SECRET_CATEGORIES",
    "REQUIRED_SCAN_CATEGORIES",
    "ScrubFinding",
    "scan_text",
    "redact_text",
    "verify_snapshot_integrity",
    "admit_example",
    "verify_corpus_admission_record",
]
