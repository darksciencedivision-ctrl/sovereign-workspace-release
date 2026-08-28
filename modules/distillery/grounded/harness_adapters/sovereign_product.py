from __future__ import annotations

import hashlib
import json
from pathlib import Path

from distillery.common import ContractError, sha256_value
from grounded.telemetry import TraceStore


def source_session_key(source_session_id: str) -> str:
    if not source_session_id:
        raise ContractError("source session identity is required")
    return "sovereign:" + sha256_value(source_session_id)[:32]


def _provider(record: dict) -> str:
    telemetry = record.get("telemetry") or {}
    return telemetry.get("provider") or ("ollama" if telemetry.get("reported_model") else "UNKNOWN")


def _revision(record: dict) -> str:
    revision = record.get("model_provenance_after") or record.get("model_provenance_before") or "UNKNOWN"
    return revision if isinstance(revision, str) else sha256_value(revision)


def _ensure_session(store: TraceStore, session_id: str, *, harness: str, provider: str, model_id: str, revision: str) -> None:
    if not store.has(session_id):
        store.start(session_id, harness=harness, provider=provider, model_id=model_id or "UNKNOWN", revision=revision)


def import_turn_record(path: str | Path, store: TraceStore) -> dict:
    """Import privacy-minimized metadata from Sovereign product turn evidence."""
    source = Path(path)
    record = json.loads(source.read_text(encoding="utf-8"))
    required = {"session_id", "turn", "model", "status", "prompt_sha256", "output_sha256"}
    missing = required - record.keys()
    if missing:
        raise ContractError(f"Sovereign turn evidence missing: {sorted(missing)}")
    provider = _provider(record)
    revision = _revision(record)
    turn_id = str(record["turn"])
    # A source turn is one immutable import unit. Keeping the turn in the
    # telemetry session identity makes replay idempotence explicit and avoids
    # reopening a source session whose outcome is already final.
    source_file_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    session_id = "sovereign:" + sha256_value({"source_session": record["session_id"], "turn": turn_id, "source_file_hash": source_file_hash})[:32]
    expected_outcome = "success" if record["status"] == "completed" else "fail"
    if store.has(session_id):
        existing = store.get(session_id)
        expected = (provider, record["model"], revision, turn_id, record["output_sha256"], expected_outcome)
        observed = (existing["provider"], existing["model_id"], existing["revision"], existing["turns"][0]["turn_id"], existing["turns"][0]["content_hash"], existing["outcome"])
        if observed != expected:
            raise ContractError("existing Sovereign turn import conflicts with immutable source metadata")
        return {"session_id": session_id, "turn_id": turn_id, "provider": provider, "model_id": record["model"], "revision": revision, "outcome": expected_outcome, "content_copied": False, "duplicate_ignored": True}
    store.start(session_id, harness="sovereign_product.semantic_deep", provider=provider, model_id=record["model"], revision=revision)
    store.turn(session_id, turn_id, content_hash=record["output_sha256"], tool_status="passed" if record["status"] == "completed" else "failed", measured={"latency_seconds": record.get("latency_seconds"), "prompt_hash": record["prompt_sha256"], "record_hash": record.get("record_sha256"), "source_file_hash": source_file_hash, "source_status": record["status"]})
    if expected_outcome == "success":
        store.success(session_id)
    else:
        store.fail(session_id)
    return {"session_id": session_id, "turn_id": turn_id, "provider": provider, "model_id": record["model"], "revision": revision, "outcome": store.get(session_id)["outcome"], "content_copied": False, "duplicate_ignored": False}


def import_session_turns(paths: list[str | Path], store: TraceStore, *, recovery: bool = False, superseded: bool = False) -> dict:
    """Join real semantic-deep turn records without persisting raw content."""
    if not paths:
        raise ContractError("at least one Sovereign turn record is required")
    records = []
    for item in paths:
        source = Path(item)
        record = json.loads(source.read_text(encoding="utf-8"))
        required = {"session_id", "turn", "model", "status", "prompt_sha256", "output_sha256"}
        missing = required - record.keys()
        if missing:
            raise ContractError(f"Sovereign turn evidence missing: {sorted(missing)}")
        records.append((source, record))
    source_ids = {record["session_id"] for _, record in records}
    if len(source_ids) != 1:
        raise ContractError("turn records do not share a stable source session")
    session_id = source_session_key(next(iter(source_ids)))
    first = records[0][1]
    _ensure_session(store, session_id, harness="sovereign_product.semantic_deep", provider=_provider(first), model_id=first["model"], revision=_revision(first))
    imported = duplicate_count = 0
    for source, record in sorted(records, key=lambda pair: (str(pair[1].get("execution_id", "")), int(pair[1]["turn"]))):
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        turn_id = sha256_value({"execution": record.get("execution_id") or source.parent.parent.name, "turn": record["turn"]})[:24]
        if store.has_turn(session_id, turn_id):
            duplicate_count += 1
            continue
        status = str(record["status"])
        telemetry = record.get("telemetry") or {}
        store.turn(
            session_id,
            turn_id,
            content_hash=record["output_sha256"],
            tool_status="passed" if status == "completed" else "failed",
            recovery=recovery,
            superseded=superseded or status != "completed",
            measured={"latency_seconds": record.get("latency_seconds"), "prompt_hash": record["prompt_sha256"], "record_hash": record.get("record_sha256"), "source_file_hash": source_hash, "source_status": status, "failure_type": telemetry.get("failure_type"), "role": record.get("role")},
            harness="sovereign_product.semantic_deep",
            provider=_provider(record),
            model_id=record["model"],
            revision=_revision(record),
        )
        imported += 1
    return {"session_id": session_id, "turns_imported": imported, "duplicates_ignored": duplicate_count, "content_copied": False}


def import_result_record(path: str | Path, store: TraceStore, *, recovery: bool = False, superseded: bool | None = None) -> dict:
    """Import a QUICK/DEEP result as one content-free, joinable turn."""
    source = Path(path)
    record = json.loads(source.read_text(encoding="utf-8"))
    required = {"session_id", "status", "route"}
    missing = required - record.keys()
    if missing:
        raise ContractError(f"Sovereign result evidence missing: {sorted(missing)}")
    status = str(record["status"])
    passed = status in {"accepted", "completed"} or record.get("accepted") is True
    provider = _provider(record)
    model_id = record.get("model") or "UNKNOWN"
    revision = _revision(record)
    session_id = source_session_key(record["session_id"])
    harness = f"sovereign_product.{record['route']}"
    _ensure_session(store, session_id, harness=harness, provider=provider, model_id=model_id, revision=revision)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    turn_id = sha256_value({"source_file_hash": source_hash, "route": record["route"]})[:24]
    if store.has_turn(session_id, turn_id):
        return {"session_id": session_id, "turn_id": turn_id, "duplicate_ignored": True, "content_copied": False, "source_status": status}
    telemetry = record.get("telemetry") or {}
    store.turn(
        session_id,
        turn_id,
        content_hash=sha256_value(record.get("answer")),
        tool_status="passed" if passed else "failed",
        recovery=recovery,
        superseded=(not passed) if superseded is None else superseded,
        measured={"latency_seconds": record.get("latency_seconds"), "prompt_hash": telemetry.get("prompt_sha256"), "source_file_hash": source_hash, "source_status": status, "failure_type": telemetry.get("failure_type") or record.get("reason"), "route": record["route"]},
        harness=harness,
        provider=provider,
        model_id=model_id,
        revision=revision,
    )
    return {"session_id": session_id, "turn_id": turn_id, "duplicate_ignored": False, "content_copied": False, "source_status": status}
