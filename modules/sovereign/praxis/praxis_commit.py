# praxis_commit.py - guarded PRAXIS write-back with memory gate enforcement

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from system_manifest import load_system_manifest, model_name, runtime_value
try:
    from .memory_contract import MEMORY_ELIGIBLE, MEMORY_REJECTED, MEMORY_REVIEW_REQUIRED
    from .memory_gate import evaluate_memory_gate
    from .memory_write_ledger import append_memory_write_record, build_memory_write_record
except ImportError:
    from memory_contract import MEMORY_ELIGIBLE, MEMORY_REJECTED, MEMORY_REVIEW_REQUIRED
    from memory_gate import evaluate_memory_gate
    from memory_write_ledger import append_memory_write_record, build_memory_write_record

PRAXIS_DIR = os.path.dirname(os.path.abspath(__file__))
COMMIT_JSON = os.path.join(PRAXIS_DIR, "commit.json")
DONE_TXT = os.path.join(PRAXIS_DIR, "commit_done.txt")
DB_DIR = os.path.join(PRAXIS_DIR, "db")
CLAIM_MEMORY_DIR = os.path.join(PRAXIS_DIR, "claim_memory")

_MANIFEST = load_system_manifest(ROOT_DIR)
OLLAMA_URL = str(runtime_value("OLLAMA_BASE_URL", _MANIFEST)).strip()
EMBED_MODEL = model_name("EMBEDDING_MODEL", _MANIFEST)
CANONICAL_COLLECTION = "praxis_memory"
CLAIM_COLLECTION = "praxis_claim_memory"

CHUNK_SIZE = 1800
CHUNK_OVER = 180
CANONICAL_TYPES = {"synthesis", "ledger"}
ANALYTICAL_TYPES = {"arbitration_claim", "contested_claim", "unresolved_conflict"}
ALLOWED_TYPES = CANONICAL_TYPES | ANALYTICAL_TYPES
BLOCKED_TYPES = {"sovereign_voice", "voice", "praxis_report", "report"}
GATE_INPUT_FIELDS = (
    "selection_confidence",
    "validation_status",
    "provenance",
    "source_hash",
    "selection_status",
    "unresolved_contradiction",
    "semantic_duplicate_suspected",
    "cosmetic_duplicate",
    "failed_validation",
)


def write_done(message: str) -> None:
    with open(DONE_TXT, "w", encoding="utf-8") as handle:
        handle.write(message)


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as handle:
        handle.write(serialized)
        tmp_name = handle.name
    Path(tmp_name).replace(path)


def embed(text: str) -> list[float]:
    payload = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        body = json.loads(response.read().decode("utf-8"))
    if "embedding" not in body:
        raise ValueError(f"No embedding key in response: {body}")
    return [float(item) for item in body["embedding"]]


def chunk_text(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        candidate = (current + "\n\n" + paragraph).strip() if current else paragraph
        if len(candidate) <= CHUNK_SIZE:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) > CHUNK_SIZE:
            start = 0
            while start < len(paragraph):
                end = start + CHUNK_SIZE
                chunks.append(paragraph[start:end])
                start = end - CHUNK_OVER
            current = ""
        else:
            current = paragraph
    if current:
        chunks.append(current)
    return chunks if chunks else [text[:CHUNK_SIZE]]


def make_doc_id(session_id: str, entry_type: str, chunk_index: int, ordinal: int) -> str:
    raw = f"{session_id}::{entry_type}::{ordinal}::{chunk_index}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[key] = value
        else:
            clean[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return clean


def normalize_entry_content(entry: dict[str, Any]) -> str:
    content = entry.get("content", entry.get("text", ""))
    return str(content).strip()


def validate_entry(entry: dict[str, Any], index: int) -> tuple[str, str, str, dict[str, Any]]:
    entry_type = str(entry.get("type", "")).strip().lower()
    if entry_type in BLOCKED_TYPES:
        raise ValueError(f"entries[{index}] type '{entry_type}' is explicitly excluded from Praxis memory")
    if entry_type not in ALLOWED_TYPES:
        raise ValueError(f"entries[{index}] unknown type '{entry_type}'")

    default_channel = "canonical" if entry_type == "synthesis" else "ledger" if entry_type == "ledger" else "analytical"
    channel = str(entry.get("channel", default_channel)).strip().lower()
    if entry_type == "synthesis" and channel != "canonical":
        raise ValueError(f"entries[{index}] synthesis channel must be canonical, got '{channel}'")
    if entry_type in ANALYTICAL_TYPES and channel == "canonical":
        raise ValueError(f"entries[{index}] analytical claim memory cannot use canonical channel")
    if entry.get("memory_allowed") in (False, "false", "False", 0):
        raise ValueError(f"entries[{index}] is explicitly marked non-memory and cannot be committed")

    content = normalize_entry_content(entry)
    if not content:
        raise ValueError(f"entries[{index}] content is empty")
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    return entry_type, channel, content, metadata


def append_claim_sidecar(session_id: str, topic: str, entry_type: str, content: str, metadata: dict[str, Any], timestamp: str) -> None:
    sidecar_path = Path(CLAIM_MEMORY_DIR) / f"{session_id}.json"
    payload = {"session_id": session_id, "topic": topic, "entries": []}
    if sidecar_path.exists():
        try:
            existing = json.loads(sidecar_path.read_text(encoding="utf-8-sig"))
            if isinstance(existing, dict):
                payload.update(existing)
        except (OSError, json.JSONDecodeError):
            pass
    payload.setdefault("entries", [])
    payload["entries"].append(
        {
            "type": entry_type,
            "content": content,
            "metadata": metadata,
            "timestamp": timestamp,
        }
    )
    atomic_write_json(sidecar_path, payload)


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def write_done_with_metadata(*, ok: bool, memory_decision: str, write_status: str, reason: str, input_hash: str) -> None:
    prefix = "OK" if ok else "ERROR"
    write_done(
        f"{prefix}: {reason}\n"
        f"MEMORY_DECISION={memory_decision}\n"
        f"WRITE_STATUS={write_status}\n"
        f"INPUT_HASH={input_hash}\n"
    )


def build_memory_input(payload: dict[str, Any], input_hash: str) -> dict[str, Any]:
    memory_gate_payload = payload.get("memory_gate") if isinstance(payload.get("memory_gate"), dict) else {}
    requested_gate_fields: dict[str, Any] = {}
    for field in GATE_INPUT_FIELDS:
        if field == "provenance":
            continue
        if field in memory_gate_payload:
            requested_gate_fields[field] = memory_gate_payload.get(field)
        elif field in payload:
            requested_gate_fields[field] = payload.get(field)

    provenance = memory_gate_payload.get("provenance") if isinstance(memory_gate_payload.get("provenance"), dict) else {}
    if not provenance:
        provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    provenance = dict(provenance)
    for field in ("candidate_file", "selection_ledger_path"):
        if field in memory_gate_payload and field not in provenance:
            provenance[field] = memory_gate_payload.get(field)
        elif field in payload and field not in provenance:
            provenance[field] = payload.get(field)
    if provenance:
        requested_gate_fields["provenance"] = provenance

    return {
        "artifact_id": str(payload.get("artifact_id") or payload.get("session_id") or "").strip(),
        "selection_id": str(payload.get("selection_id") or "").strip(),
        "session_id": str(payload.get("session_id") or "").strip(),
        "topic": str(payload.get("topic") or "").strip(),
        "entries": payload.get("entries"),
        "selected_output": payload.get("selected_output") or "",
        "selection_confidence": requested_gate_fields.get("selection_confidence"),
        "validation_status": requested_gate_fields.get("validation_status"),
        "provenance": requested_gate_fields.get("provenance", {}),
        "source_hash": requested_gate_fields.get("source_hash"),
        "selection_status": requested_gate_fields.get("selection_status"),
        "unresolved_contradiction": requested_gate_fields.get("unresolved_contradiction"),
        "semantic_duplicate_suspected": requested_gate_fields.get("semantic_duplicate_suspected"),
        "cosmetic_duplicate": requested_gate_fields.get("cosmetic_duplicate"),
        "failed_validation": requested_gate_fields.get("failed_validation"),
        "payload_requested_memory_decision": str(payload.get("memory_decision") or "").strip(),
        "payload_requested_trusted_internal": coerce_bool(payload.get("trusted_internal")),
        "payload_gate_fields": requested_gate_fields,
        "input_hash": input_hash,
    }


def authorization_result_from_write_status(write_status: str) -> str:
    if write_status == "written":
        return "authorized"
    if write_status == "review":
        return "review_required"
    return "rejected"


def build_memory_attempt_audit_fields(
    *,
    memory_input: dict[str, Any],
    gate_result: dict[str, Any] | None,
    gate_memory_decision: str,
    payload_requested_memory_decision: str,
    write_status: str,
) -> dict[str, Any]:
    gate_payload = gate_result if isinstance(gate_result, dict) else {}
    verified_gate_inputs = gate_payload.get("verified_gate_inputs") if isinstance(gate_payload.get("verified_gate_inputs"), dict) else {}
    requested_provenance = memory_input.get("provenance") if isinstance(memory_input.get("provenance"), dict) else {}
    return {
        "payload_requested_memory_decision": payload_requested_memory_decision or None,
        "gate_memory_decision": gate_memory_decision,
        "payload_requested_trusted_internal": coerce_bool(memory_input.get("payload_requested_trusted_internal")),
        "verified_gate_inputs": verified_gate_inputs,
        "unverified_payload_fields": gate_payload.get("unverified_payload_fields", []),
        "authorization_basis": gate_payload.get(
            "authorization_basis",
            "trusted ledger fields and candidate_file-derived content binding",
        ),
        "authorization_result": authorization_result_from_write_status(write_status),
        "verification_status": gate_payload.get("verification_status", "unverified"),
        "verification_errors": gate_payload.get("verification_errors", []),
        "requested_candidate_file": gate_payload.get("requested_candidate_file") or requested_provenance.get("candidate_file") or "",
        "verified_candidate_file": gate_payload.get("verified_candidate_file", ""),
        "requested_selection_ledger_path": gate_payload.get("requested_selection_ledger_path")
        or requested_provenance.get("selection_ledger_path")
        or "",
        "verified_selection_ledger_path": gate_payload.get("verified_selection_ledger_path", ""),
        "trusted_root_policy": gate_payload.get("trusted_root_policy", {}),
        "trusted_ledger_row_id": gate_payload.get("trusted_ledger_row_id", ""),
        "missing_trusted_fields": gate_payload.get("missing_trusted_fields", []),
        "requested_entries_hash": gate_payload.get("requested_entries_hash", ""),
        "verified_candidate_file_hash": gate_payload.get("verified_candidate_file_hash", ""),
        "authorized_source_hash": gate_payload.get("authorized_source_hash", ""),
        "authorized_entries_hash": gate_payload.get("authorized_entries_hash", ""),
        "committed_content_hash": gate_payload.get("committed_content_hash", ""),
        "content_binding_method": gate_payload.get("content_binding_method", "fail_closed"),
        "content_binding_result": gate_payload.get("content_binding_result", "unavailable_or_untrusted"),
        "payload_entries_used_for_write": gate_payload.get("payload_entries_used_for_write", False),
        "entries_derived_from_verified_candidate": gate_payload.get("entries_derived_from_verified_candidate", False),
    }


def log_memory_attempt(
    *,
    memory_input: dict[str, Any],
    gate_result: dict[str, Any] | None,
    gate_memory_decision: str,
    payload_requested_memory_decision: str,
    write_status: str,
    reason: str,
    praxis_collection: str,
) -> None:
    audit_fields = build_memory_attempt_audit_fields(
        memory_input=memory_input,
        gate_result=gate_result,
        gate_memory_decision=gate_memory_decision,
        payload_requested_memory_decision=payload_requested_memory_decision,
        write_status=write_status,
    )
    verified_gate_inputs = audit_fields["verified_gate_inputs"] if isinstance(audit_fields.get("verified_gate_inputs"), dict) else {}
    record = build_memory_write_record(
        artifact_id=str(memory_input.get("artifact_id") or ""),
        session_id=str(memory_input.get("session_id") or ""),
        topic=str(memory_input.get("topic") or ""),
        memory_decision=gate_memory_decision,
        selection_confidence=float(verified_gate_inputs.get("selection_confidence", 0.0) or 0.0),
        source_hash=str(verified_gate_inputs.get("source_hash") or memory_input.get("input_hash") or ""),
        praxis_collection=praxis_collection,
        write_status=write_status,
        reason=reason,
    )
    record.update(audit_fields)
    append_memory_write_record(record)


def main() -> None:
    if not os.path.isfile(COMMIT_JSON):
        write_done("ERROR: commit.json not found")
        sys.exit(1)

    try:
        payload = json.loads(Path(COMMIT_JSON).read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        write_done(f"ERROR: commit.json JSON parse error: {exc}")
        sys.exit(2)

    input_hash = payload_hash(payload)
    memory_input = build_memory_input(payload, input_hash)
    session_id = str(payload.get("session_id") or "").strip()
    topic = str(payload.get("topic") or "").strip()
    artifact_id = str(memory_input.get("artifact_id") or session_id or "").strip()
    payload_requested_memory_decision = str(memory_input.get("payload_requested_memory_decision") or "").strip()
    gate_result = evaluate_memory_gate(memory_input)
    gate_memory_decision = str(gate_result.get("memory_decision") or MEMORY_REJECTED)
    gate_reason = str(gate_result.get("reason") or "")
    authorized_entries = gate_result.get("authorized_entries") if isinstance(gate_result.get("authorized_entries"), list) else []

    if not session_id or not topic:
        reason = "commit.json must include non-empty session_id and topic."
        log_memory_attempt(
            memory_input=memory_input,
            gate_result=gate_result,
            gate_memory_decision=gate_memory_decision,
            payload_requested_memory_decision=payload_requested_memory_decision,
            write_status="rejected",
            reason=reason,
            praxis_collection=CANONICAL_COLLECTION,
        )
        write_done_with_metadata(
            ok=False,
            memory_decision=gate_memory_decision,
            write_status="rejected",
            reason=reason,
            input_hash=input_hash,
        )
        sys.exit(2)

    if not os.path.isdir(DB_DIR):
        reason = f"ChromaDB dir not found: {DB_DIR}"
        log_memory_attempt(
            memory_input=memory_input,
            gate_result=gate_result,
            gate_memory_decision=gate_memory_decision,
            payload_requested_memory_decision=payload_requested_memory_decision,
            write_status="rejected",
            reason=reason,
            praxis_collection=CANONICAL_COLLECTION,
        )
        write_done_with_metadata(
            ok=False,
            memory_decision=gate_memory_decision,
            write_status="rejected",
            reason=reason,
            input_hash=input_hash,
        )
        sys.exit(2)

    if gate_memory_decision != MEMORY_ELIGIBLE:
        write_status = "review" if gate_memory_decision == MEMORY_REVIEW_REQUIRED else "rejected"
        log_memory_attempt(
            memory_input=memory_input,
            gate_result=gate_result,
            gate_memory_decision=gate_memory_decision,
            payload_requested_memory_decision=payload_requested_memory_decision,
            write_status=write_status,
            reason=gate_reason,
            praxis_collection=CANONICAL_COLLECTION,
        )
        write_done_with_metadata(
            ok=False,
            memory_decision=gate_memory_decision,
            write_status=write_status,
            reason=gate_reason,
            input_hash=input_hash,
        )
        sys.exit(2)

    if not authorized_entries:
        reason = gate_reason or "memory gate did not provide verified candidate-derived entries"
        log_memory_attempt(
            memory_input=memory_input,
            gate_result=gate_result,
            gate_memory_decision=MEMORY_REJECTED,
            payload_requested_memory_decision=payload_requested_memory_decision,
            write_status="rejected",
            reason=reason,
            praxis_collection=CANONICAL_COLLECTION,
        )
        write_done_with_metadata(
            ok=False,
            memory_decision=MEMORY_REJECTED,
            write_status="rejected",
            reason=reason,
            input_hash=input_hash,
        )
        sys.exit(2)

    try:
        import chromadb
    except ImportError:
        reason = "chromadb not importable - is it installed?"
        log_memory_attempt(
            memory_input=memory_input,
            gate_result=gate_result,
            gate_memory_decision=gate_memory_decision,
            payload_requested_memory_decision=payload_requested_memory_decision,
            write_status="rejected",
            reason=reason,
            praxis_collection=CANONICAL_COLLECTION,
        )
        write_done_with_metadata(
            ok=False,
            memory_decision=gate_memory_decision,
            write_status="rejected",
            reason=reason,
            input_hash=input_hash,
        )
        sys.exit(2)

    client = chromadb.PersistentClient(path=DB_DIR)
    canonical_collection = client.get_or_create_collection(name=CANONICAL_COLLECTION, metadata={"hnsw:space": "cosine"})
    claim_collection = client.get_or_create_collection(name=CLAIM_COLLECTION, metadata={"hnsw:space": "cosine"})
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    total_chunks = 0
    praxis_collection_used = CANONICAL_COLLECTION
    audit_fields = build_memory_attempt_audit_fields(
        memory_input=memory_input,
        gate_result=gate_result,
        gate_memory_decision=gate_memory_decision,
        payload_requested_memory_decision=payload_requested_memory_decision,
        write_status="written",
    )
    try:
        for index, entry in enumerate(authorized_entries):
            if not isinstance(entry, dict):
                raise ValueError(f"entries[{index}] is not a dict")
            entry_type, channel, content, extra_metadata = validate_entry(entry, index)
            collection = canonical_collection if entry_type in CANONICAL_TYPES else claim_collection
            praxis_collection_used = CANONICAL_COLLECTION if entry_type in CANONICAL_TYPES else CLAIM_COLLECTION
            for chunk_index, chunk in enumerate(chunk_text(content)):
                doc_id = make_doc_id(session_id, entry_type, chunk_index, index)
                vector = embed(chunk)
                metadata = sanitize_metadata(
                    {
                        "source": f"session:{session_id}",
                        "doc_id": doc_id,
                        "chunk_index": chunk_index,
                        "session_id": session_id,
                        "topic": topic,
                        "type": entry_type,
                        "channel": channel,
                        "timestamp": timestamp,
                        "input_hash": input_hash,
                        **extra_metadata,
                        "memory_decision": gate_memory_decision,
                        **audit_fields,
                    }
                )
                collection.upsert(ids=[doc_id], embeddings=[vector], documents=[chunk], metadatas=[metadata])
                total_chunks += 1
            if entry_type in ANALYTICAL_TYPES:
                append_claim_sidecar(session_id, topic, entry_type, content, sanitize_metadata(extra_metadata), timestamp)
    except Exception as exc:
        reason = f"Commit failed: {exc}"
        log_memory_attempt(
            memory_input=memory_input,
            gate_result=gate_result,
            gate_memory_decision=gate_memory_decision,
            payload_requested_memory_decision=payload_requested_memory_decision,
            write_status="rejected",
            reason=reason,
            praxis_collection=praxis_collection_used,
        )
        write_done_with_metadata(
            ok=False,
            memory_decision=gate_memory_decision,
            write_status="rejected",
            reason=reason,
            input_hash=input_hash,
        )
        sys.exit(3)

    success_reason = gate_reason or "memory-eligible PRAXIS commit completed"
    log_memory_attempt(
        memory_input=memory_input,
        gate_result=gate_result,
        gate_memory_decision=gate_memory_decision,
        payload_requested_memory_decision=payload_requested_memory_decision,
        write_status="written",
        reason=success_reason,
        praxis_collection=praxis_collection_used,
    )
    write_done_with_metadata(
        ok=True,
        memory_decision=gate_memory_decision,
        write_status="written",
        reason=success_reason,
        input_hash=input_hash,
    )
    print(f"[praxis_commit] committed {total_chunks} chunk(s) for session {session_id}", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
