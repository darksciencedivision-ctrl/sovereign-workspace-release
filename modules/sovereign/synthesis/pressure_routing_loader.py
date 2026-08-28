"""Phase 20.4 — read-only loader that computes aggregate pressure and builds routing signal."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from pressure_routing_policy import build_routing_signal

COGNITION_SUBDIRS: dict[str, tuple[str, str]] = {
    "concepts": ("concept_index.json", "pressure_score"),
    "research_threads": ("thread_index.json", "pressure_score"),
    "hypotheses": ("hypothesis_index.json", "pressure_score"),
    "contradictions": ("contradiction_index.json", "pressure_value"),
}

LOG_FILENAME = "pressure_routing_decisions.jsonl"


class PressureRoutingLoader:
    def __init__(
        self,
        cognition_root: str | None = None,
        log_dir: str | None = None,
    ) -> None:
        self._cognition_root = str(cognition_root or os.environ.get("SOVEREIGN_COGNITION_ROOT", "")).strip()
        self._log_dir = str(log_dir or "").strip()
        self._pressure_map: dict[str, float] | None = None

    def _load_pressure_map(self) -> dict[str, float]:
        if self._pressure_map is not None:
            return self._pressure_map
        result: dict[str, float] = {}
        if not self._cognition_root or not os.path.isdir(self._cognition_root):
            self._pressure_map = result
            return result
        for subdir, (index_file, pressure_key) in COGNITION_SUBDIRS.items():
            index_path = os.path.join(self._cognition_root, subdir, index_file)
            if not os.path.isfile(index_path):
                continue
            try:
                with open(index_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            for entity_id, entry in data.items():
                if not isinstance(entry, dict):
                    continue
                raw = entry.get(pressure_key)
                try:
                    p = float(raw)
                except (TypeError, ValueError):
                    continue
                existing = result.get(str(entity_id), 0.0)
                if p > existing:
                    result[str(entity_id)] = p
        self._pressure_map = result
        return result

    def _match_topic_entities(self, topic: str) -> list[tuple[str, float]]:
        """Return (entity_id, pressure) pairs that match the topic string."""
        pressure_map = self._load_pressure_map()
        if not pressure_map or not topic:
            return []
        topic_lower = topic.lower()
        matches = []
        for entity_id, pressure in pressure_map.items():
            spaced = entity_id.lower().replace("-", " ")
            raw = entity_id.lower()
            if spaced in topic_lower or raw in topic_lower:
                matches.append((entity_id, pressure))
            else:
                # token overlap check
                entity_tokens = set(spaced.split())
                topic_tokens = set(topic_lower.split())
                overlap = entity_tokens & topic_tokens
                if len(overlap) >= min(2, len(entity_tokens)):
                    matches.append((entity_id, pressure))
        return matches

    def compute_aggregate_pressure(self, topic: str) -> tuple[float, list[tuple[str, float]]]:
        """Compute aggregate pressure for a topic. Returns (aggregate, matched_entities)."""
        matched = self._match_topic_entities(topic)
        if not matched:
            return 0.0, []
        pressures = [p for _, p in matched]
        # Aggregate: weighted blend of max + mean
        max_p = max(pressures)
        mean_p = sum(pressures) / len(pressures)
        aggregate = 0.7 * max_p + 0.3 * mean_p
        return aggregate, matched

    def get_routing_signal(self, topic: str) -> dict[str, Any]:
        """Compute pressure and build routing signal for the given topic."""
        aggregate, matched = self.compute_aggregate_pressure(topic)
        signal = build_routing_signal(aggregate_pressure=aggregate, topic=topic)
        signal["matched_entities"] = [
            {"entity_id": eid, "pressure": p} for eid, p in matched
        ]
        signal["substrate_available"] = bool(self._load_pressure_map())
        return signal

    def get_routing_signal_and_log(self, topic: str, session_id: str = "", root: str = "") -> dict[str, Any]:
        """Compute routing signal and write a decision log entry."""
        signal = self.get_routing_signal(topic)
        self._write_routing_log(signal=signal, session_id=session_id, root=root)
        return signal

    def _write_routing_log(self, signal: dict[str, Any], session_id: str = "", root: str = "") -> None:
        """Write routing decision log to logs/pressure_routing_decisions.jsonl only."""
        log_dir = self._log_dir
        if not log_dir and root:
            log_dir = os.path.join(root, "logs")
        if not log_dir:
            return
        try:
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, LOG_FILENAME)
            entry = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "session_id": session_id,
                "tier": signal.get("tier"),
                "aggregate_pressure": signal.get("aggregate_pressure"),
                "topic": signal.get("topic"),
                "applied": signal.get("applied"),
                "recommended": signal.get("recommended"),
                "matched_entity_count": len(signal.get("matched_entities") or []),
            }
            line = json.dumps(entry, ensure_ascii=False) + "\n"
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass
