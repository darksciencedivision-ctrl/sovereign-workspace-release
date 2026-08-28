from __future__ import annotations

"""Deterministic gate-status supersession resolution.

A gate may accumulate multiple historical status records. The current status is
the record that no other trusted record supersedes. Resolution uses only the
explicit ``supersedes`` edges declared by the records themselves; filename
ordering and timestamp comparison are never used to pick a winner. Timestamps
are validated but play no role in resolution. Any ambiguity fails closed.
"""

import hashlib
from pathlib import Path
from typing import Iterable, Mapping

from distillery.common import ContractError, utc_now
from datetime import UTC, datetime, timedelta

REQUIRED_FIELDS = {"record_id", "gate", "status", "recorded_at", "supersedes"}
_HEX = set("0123456789abcdef")


def _require_hex64(value: object, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in _HEX for character in value.lower()):
        raise ContractError(f"{field} must be a SHA-256 hex digest")
    return value.lower()


def _validate_timestamp(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError("recorded_at is required")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("recorded_at must be a parseable timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ContractError("recorded_at must be timezone-aware UTC")


def content_sha256(content: str | bytes) -> str:
    raw = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(raw).hexdigest()


def parse_gate_status_record(raw: Mapping) -> dict:
    missing = REQUIRED_FIELDS - raw.keys()
    if missing:
        raise ContractError(f"gate status record missing fields: {sorted(missing)}")
    for field in ("record_id", "gate", "status"):
        if not isinstance(raw[field], str) or not raw[field].strip():
            raise ContractError(f"{field} must be a non-empty string")
    _validate_timestamp(raw["recorded_at"])
    supersedes = raw["supersedes"]
    if not isinstance(supersedes, list):
        raise ContractError("supersedes must be a list")
    normalized_edges = []
    for edge in supersedes:
        if not isinstance(edge, dict):
            raise ContractError("each supersedes entry must be an object")
        target = edge.get("record_id")
        if not isinstance(target, str) or not target.strip():
            raise ContractError("supersedes entries require a non-empty record_id")
        digest = _require_hex64(edge.get("record_sha256"), f"supersedes[{target}].record_sha256")
        normalized_edges.append({**{key: edge[key] for key in ("path", "claim") if isinstance(edge.get(key), str) and edge[key]}, "record_id": target, "record_sha256": digest})
    return {
        "record_id": raw["record_id"],
        "gate": raw["gate"],
        "status": raw["status"],
        "recorded_at": raw["recorded_at"],
        "decision_authority": raw.get("decision_authority"),
        "evidence_refs": list(raw.get("evidence_refs") or []),
        "supersedes": normalized_edges,
    }


def parse_gate_status_file(path: str | Path) -> dict:
    import json

    return parse_gate_status_record(json.loads(Path(path).read_text(encoding="utf-8")))


def resolve_current(
    records: Iterable[Mapping],
    *,
    contents: Mapping[str, str | bytes] | None = None,
    trusted_record_ids: set[str] | None = None,
) -> dict:
    parsed = [parse_gate_status_record(record) for record in records]
    by_id: dict[str, dict] = {}
    for record in parsed:
        if record["record_id"] in by_id:
            raise ContractError(f"duplicate gate status record id: {record['record_id']}")
        by_id[record["record_id"]] = record

    edges: dict[str, set[str]] = {record_id: set() for record_id in by_id}
    for record in parsed:
        for edge in record["supersedes"]:
            target = edge["record_id"]
            if target == record["record_id"]:
                raise ContractError(f"record cannot supersede itself: {target}")
            if target not in by_id:
                raise ContractError(f"dangling supersedes edge: {record['record_id']} -> {target}")
            edges[target].add(record["record_id"])
            if contents is not None and target in contents:
                observed = content_sha256(contents[target])
                if observed != edge["record_sha256"]:
                    raise ContractError(
                        f"superseded record content hash mismatch for {target}: expected {edge['record_sha256']}, observed {observed}"
                    )

    visited: dict[str, int] = {}

    def visit(node: str) -> None:
        state = visited.get(node, 0)
        if state == 1:
            raise ContractError(f"cycle detected in supersedes graph at {node}")
        if state == 2:
            return
        visited[node] = 1
        for successor in edges[node]:
            visit(successor)
        visited[node] = 2

    for node in sorted(by_id):
        visit(node)

    effective = sorted(record_id for record_id in by_id if not edges[record_id])
    if trusted_record_ids is not None:
        rogue = [record_id for record_id in effective if record_id not in trusted_record_ids]
        if rogue:
            raise ContractError(f"effective gate status records outside the trust anchor set: {rogue}")
    grouped: dict[str, list[str]] = {}
    for record_id in effective:
        grouped.setdefault(by_id[record_id]["gate"], []).append(record_id)
    winners: dict[str, dict] = {}
    for gate, ids in grouped.items():
        if len(ids) != 1:
            raise ContractError(f"gate {gate} has {len(ids)} unresolved current-status records: {sorted(ids)}; refusing to guess")
        winner = by_id[ids[0]]
        winners[gate] = winner
    if not winners:
        raise ContractError("no effective gate status records remain")
    return {
        "resolved_at": utc_now(),
        "gates": {
            gate: {
                "status": winner["status"],
                "record_id": winner["record_id"],
                "recorded_at": winner["recorded_at"],
                "decision_authority": winner["decision_authority"],
                "evidence_refs": winner["evidence_refs"],
            }
            for gate, winner in winners.items()
        },
    }
