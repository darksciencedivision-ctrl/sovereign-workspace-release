from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluation.preference_learning.comparison_schema import ensure_dir, utc_now_iso

MODULE_ROOT = Path(__file__).resolve().parent
LEDGER_PATH = MODULE_ROOT / "logs" / "memory_write_ledger.jsonl"


def build_memory_write_record(
    *,
    artifact_id: str,
    session_id: str,
    topic: str,
    memory_decision: str,
    selection_confidence: float,
    source_hash: str,
    write_status: str,
    reason: str,
    praxis_collection: str = "praxis_memory",
) -> dict[str, Any]:
    return {
        "timestamp": utc_now_iso(),
        "artifact_id": artifact_id,
        "session_id": session_id,
        "topic": topic,
        "memory_decision": memory_decision,
        "selection_confidence": round(float(selection_confidence), 4),
        "source_hash": source_hash,
        "praxis_collection": praxis_collection,
        "write_status": write_status,
        "reason": reason,
    }


def append_memory_write_record(record: dict[str, Any], ledger_path: Path | None = None) -> Path:
    resolved = ledger_path or LEDGER_PATH
    ensure_dir(resolved.parent)
    with resolved.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return resolved


def load_memory_write_ledger(ledger_path: Path | None = None) -> list[dict[str, Any]]:
    resolved = ledger_path or LEDGER_PATH
    if not resolved.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in resolved.read_text(encoding="utf-8-sig").splitlines():
        raw = line.strip()
        if not raw:
            continue
        rows.append(json.loads(raw))
    return rows
