"""Conductor succession + persistence (Plan §19.1, §9.11; I-CS1, invariant 28).

The conductor is an interface; its runtime selection is replaceable with zero project loss.
This serializes the conductor's full operating state to MCP as an immutable snapshot with an
integrity hash, and reconstructs it into a freshly-selected conductor after loss. Because the
project intelligence lives in MCP (not the model session), a killed conductor is a routine
hot swap: Resume → Select model → reconstruct.

Cadence (U11): snapshot on every major event PLUS a bounded interval (default 5 min).
Staleness checklist on reconstruct: integrity, directive-version match, snapshot age,
memory-head resolvability, node-registry presence, unresolved-conflict scan — any mismatch is
reported before the new conductor assigns work.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

from control_plane.conductor.selection import (
    CONDUCTOR_RECORD_KEYS,
    ConductorSelectionError,
    succession_selection,
)

_SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "schemas" / "checkpoint.schema.json").read_text(encoding="utf-8"))

DEFAULT_INTERVAL_S = 300  # 5 min (U11 default, tunable)


@dataclass
class ConductorState:
    """The full operating state a successor must reconstruct — the whole point is ZERO loss."""
    tasks: list[dict[str, Any]] = field(default_factory=list)          # task-graph snapshot
    nodes: list[dict[str, Any]] = field(default_factory=list)          # node registry
    open_debates: list[str] = field(default_factory=list)
    pending_gates: list[str] = field(default_factory=list)
    memory_heads: dict[str, str] = field(default_factory=dict)         # logical key -> version ref
    routing: dict[str, Any] = field(default_factory=dict)
    outstanding_issues: list[str] = field(default_factory=list)
    directive_version: str = "v2.4"
    task_graph_version: int = 0                                        # monotonic; §19.1 version match
    current_conductor: dict[str, Any] = field(default_factory=dict)    # {model, reason, since}


@dataclass(frozen=True)
class StalenessReport:
    ok: bool
    checks: dict[str, Any]

    def reasons(self) -> list[str]:
        return [k for k, v in self.checks.items() if v is False]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _integrity(state: ConductorState) -> str:
    return "sha256:" + hashlib.sha256(_state_json(state)).hexdigest()


def _state_json(state: ConductorState) -> bytes:
    return json.dumps(asdict(state), sort_keys=True).encode("utf-8")


class SuccessionManager:
    def __init__(self, mcp_client: Any) -> None:
        self._mcp = mcp_client

    def serialize(self, state: ConductorState, *, trigger: str = "major_event") -> dict[str, Any]:
        """Publish an immutable succession snapshot to MCP (kind=succession_state, CANDIDATE —
        the conductor's own checkpoint, not a promoted work product). Returns the record."""
        integrity = _integrity(state)
        # the checkpoint's conductor field conforms to checkpoint@1.0's current_conductor def
        # (additionalProperties:false); node_id lives in the state, not the checkpoint conductor.
        # The key set is read from the ONE schema-derived source (Phase 15D `.selection`) rather
        # than restated here, so a schema change cannot leave a stale copy behind.
        conductor_meta = {k: v for k, v in state.current_conductor.items()
                          if k in CONDUCTOR_RECORD_KEYS}
        checkpoint = {
            "checkpoint_id": "s-" + secrets.token_hex(8), "kind": "succession_snapshot",
            "ts": _now_iso(), "trigger": trigger,
            "debates": state.open_debates, "gates": state.pending_gates,
            "memory_heads": state.memory_heads, "outstanding_issues": state.outstanding_issues,
            "directive_version": state.directive_version, "conductor": conductor_meta,
            "integrity": integrity, "schema": "checkpoint@1.0",
        }
        jsonschema.validate(checkpoint, _SCHEMA)
        doc = {"state": asdict(state), "checkpoint": checkpoint}
        content = json.dumps(doc, sort_keys=True).encode("utf-8")
        prov = {"author_node": self._conductor_node(state), "task_id": None, "ts": _now_iso(),
                "directive_version": state.directive_version, "confidence": "high"}
        pub = self._mcp.call("publish", kind="succession_state", tier="shared_project",
                             content_b64=base64.b64encode(content).decode("ascii"),
                             provenance=prov, status="CANDIDATE")
        # note: the full state lives in doc["state"] (integrity-hashed); the checkpoint's
        # tasks/nodes/routing version-refs are the snapshot entry itself
        return {"entry_id": pub["entry_id"], "checkpoint": checkpoint, "integrity": integrity}

    def _conductor_node(self, state: ConductorState) -> str:
        # the publishing node id; falls back to a stable conductor id
        return state.current_conductor.get("node_id", "conductor")

    def latest(self) -> dict[str, Any] | None:
        # read_status returns entries in durable insertion order (ORDER BY inserted_ts), so the
        # LAST succession_state entry is the newest — skew-immune, unlike a wall-clock ts sort
        entries = [e for e in self._mcp.call("read_status", status="CANDIDATE")
                   if e.get("kind") == "succession_state"]
        if not entries:
            return None
        newest = entries[-1]
        raw = self._mcp.call("get_content", entry_id=newest["entry_id"])
        doc = json.loads(base64.b64decode(raw["content_b64"]))
        return {"entry_id": newest["entry_id"], "doc": doc}

    def reconstruct(self, *, expected_directive_version: str, new_selection: dict[str, Any],
                    expected_task_graph_version: int | None = None, max_age_s: float | None = None,
                    now: datetime | None = None) -> tuple[ConductorState, StalenessReport]:
        latest = self.latest()
        if latest is None:
            raise LookupError("no succession snapshot to reconstruct from")
        doc = latest["doc"]
        state_dict, checkpoint = doc["state"], doc["checkpoint"]
        known = {f.name for f in fields(ConductorState)}
        state = ConductorState(**{k: v for k, v in state_dict.items() if k in known})  # tolerate schema drift

        now = now or datetime.now(timezone.utc)
        recomputed = _integrity(state)
        age_s = (now - datetime.fromisoformat(checkpoint["ts"])).total_seconds()
        # memory heads must resolve AND still be current: a version advance on a tracked head
        # (in-place, same entry_id) is post-snapshot work the entry-id diff alone would miss (R2)
        heads_ok = all(self._head_current(ref) for ref in state.memory_heads.values())
        conflicts = self._open_conflicts()  # -1 on error => fail closed (flagged as conflicts)
        # §19.1 "snapshot age vs event-log tail": detect ACCEPTED work that happened AFTER the
        # snapshot (the real project-loss window), not just wall-clock age
        newer_ids = self._accepted_after(state.memory_heads)
        checks: dict[str, Any] = {
            "integrity_ok": recomputed == checkpoint["integrity"],
            # directive read from the integrity-covered STATE, not the unprotected checkpoint copy
            "directive_version_match": state.directive_version == expected_directive_version,
            "task_graph_version_match": (expected_task_graph_version is None)
                                        or (state.task_graph_version == expected_task_graph_version),
            "event_tail_current": len(newer_ids) == 0,
            "memory_heads_current": heads_ok,
            "node_registry_present": bool(state.nodes),
            "no_unresolved_conflicts": conflicts == 0,
            "snapshot_age_s": round(age_s, 3),
            "age_within_limit": (max_age_s is None) or (age_s <= max_age_s),
            "newer_accepted_entries": sorted(newer_ids),
        }
        # every §19.1 checklist item is BLOCKING (any mismatch => reconciliation before assignment)
        ok = bool(checks["integrity_ok"] and checks["directive_version_match"]
                  and checks["task_graph_version_match"] and checks["event_tail_current"]
                  and checks["memory_heads_current"] and checks["node_registry_present"]
                  and checks["no_unresolved_conflicts"] and checks["age_within_limit"])
        # The successor adopts the SAME project state; only the conductor selection changes. The
        # selection record is built through the ONE validated constructor (Phase 15D `.selection`),
        # so a malformed successor selection is refused here instead of reaching a checkpoint.
        # Non-schema keys the caller carries (e.g. node_id) are preserved alongside it.
        if "model" not in new_selection:
            # raised as the selection module's own error type, not a bare KeyError, so a caller
            # catching ConductorSelectionError cannot miss this fail-closed refusal
            raise ConductorSelectionError("new_selection must name the successor `model`")
        # `reason` and `since` are OWNED by this path (a reconstruct IS a succession, stamped with
        # the reconstruct clock). Silently discarding a caller's values would let an explicit
        # operator re-selection be recorded as a system recovery — refuse instead.
        owned = {k for k in ("reason", "since") if k in new_selection}
        if owned:
            raise ConductorSelectionError(
                f"succession owns {sorted(owned)} — a reconstruct is always reason='succession' "
                "stamped with the reconstruct clock; pass only the successor's selection fields")
        extra = {k: v for k, v in new_selection.items() if k not in CONDUCTOR_RECORD_KEYS}
        schema_keys = {k: v for k, v in new_selection.items()
                       if k in CONDUCTOR_RECORD_KEYS and k != "model"}
        successor = succession_selection(new_selection["model"], since=_now_iso(), **schema_keys)
        state.current_conductor = {**extra, **successor.as_current_conductor()}
        return state, StalenessReport(ok=ok, checks=checks)

    @staticmethod
    def perform_handoff(governor: Any, subscription_ref: str, predecessor_node: str,
                        successor_node: str) -> list[str]:
        """I-X3 succession ordering owned by the succession code: RELEASE the predecessor's
        one-per-subscription terminal BEFORE the successor ACQUIRES it. Returns the order."""
        governor.release(subscription_ref, predecessor_node)
        governor.acquire(subscription_ref, successor_node)
        return ["release", "acquire"]

    def _accepted_after(self, memory_heads: dict[str, str]) -> set[str]:
        """ACCEPTED entry ids present now but NOT captured in the snapshot's heads => post-snapshot work."""
        snapshot_ids = {ref.split("@", 1)[0] for ref in memory_heads.values()}
        try:
            current = {e["entry_id"] for e in self._mcp.call("read_status", status="ACCEPTED")}
        except Exception:
            return {"<event-log-read-failed>"}  # fail closed: cannot confirm currency
        return current - snapshot_ids

    def _head_current(self, ref: str) -> bool:
        """True iff the snapshot's head ref is still the CURRENT head — i.e. it both resolves
        and its version has not advanced since the snapshot (R2). Fail closed on error."""
        try:
            entry_id = ref.split("@", 1)[0]
            entry = self._mcp.call("get_head", entry_id=entry_id)
            if entry is None:
                return False
            current_ref = f"{entry_id}@{entry['version']}"
            return current_ref == ref
        except Exception:
            return False

    def _open_conflicts(self) -> int:
        try:
            return len(self._mcp.call("list_conflicts"))
        except Exception:
            return -1  # unknown => fail closed (treat as conflicts present)


def should_snapshot(*, last_snapshot_ts: float | None, now_ts: float, had_major_event: bool,
                    interval_s: float = DEFAULT_INTERVAL_S) -> bool:
    """Cadence policy (U11): snapshot on a major event OR when the bounded interval elapsed."""
    if had_major_event:
        return True
    if last_snapshot_ts is None:
        return True
    return (now_ts - last_snapshot_ts) >= interval_s
