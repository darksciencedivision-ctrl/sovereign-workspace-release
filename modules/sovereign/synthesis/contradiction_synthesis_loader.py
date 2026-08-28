"""Phase 20.2 — read-only loader for contradiction-aware synthesis context."""
from __future__ import annotations

import json
import os
from typing import Any

ACTIVE_STATUSES = {"open", "pressured", "under_review"}
DEFAULT_LIMIT = 5
DEFAULT_MIN_PRESSURE = 0.0
TOPIC_RELEVANCE_BOOST = 2.0

SYNTHESIS_INSTRUCTION = (
    "These active contradictions represent known epistemic pressure points. "
    "They inform synthesis but do not decide truth. "
    "Consider them as areas requiring careful epistemic scrutiny."
)


class ContradictionSynthesisLoader:
    def __init__(self, cognition_root: str | None = None) -> None:
        self._cognition_root = str(cognition_root or os.environ.get("SOVEREIGN_COGNITION_ROOT", "")).strip()
        self._contradiction_map: dict[str, dict[str, Any]] | None = None
        self._warnings: list[str] = []

    def load_contradiction_map(self) -> dict[str, dict[str, Any]]:
        """Load contradiction nodes, last-line-wins per ID from JSONL + index."""
        if self._contradiction_map is not None:
            return self._contradiction_map
        result: dict[str, dict[str, Any]] = {}
        self._warnings = []
        if not self._cognition_root or not os.path.isdir(self._cognition_root):
            self._contradiction_map = result
            return result

        # Load from JSONL (last-line-wins per ID)
        nodes_path = os.path.join(self._cognition_root, "contradictions", "contradiction_nodes.jsonl")
        if os.path.isfile(nodes_path):
            try:
                with open(nodes_path, "r", encoding="utf-8") as fh:
                    for line_num, line in enumerate(fh, 1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            node = json.loads(line)
                        except json.JSONDecodeError:
                            self._warnings.append(f"malformed JSONL at contradiction_nodes.jsonl line {line_num}")
                            continue
                        if not isinstance(node, dict):
                            continue
                        cid = str(node.get("contradiction_id") or node.get("id") or "").strip()
                        if cid:
                            result[cid] = node
            except OSError as exc:
                self._warnings.append(f"could not read contradiction_nodes.jsonl: {exc}")

        # Supplement with index (fills in any entries not in JSONL)
        index_path = os.path.join(self._cognition_root, "contradictions", "contradiction_index.json")
        if os.path.isfile(index_path):
            try:
                with open(index_path, "r", encoding="utf-8") as fh:
                    index = json.load(fh)
                if isinstance(index, dict):
                    for cid, entry in index.items():
                        if cid not in result and isinstance(entry, dict):
                            result[str(cid)] = entry
            except (OSError, json.JSONDecodeError) as exc:
                self._warnings.append(f"could not read contradiction_index.json: {exc}")

        self._contradiction_map = result
        return result

    def select_relevant_contradictions(
        self,
        topic: str = "",
        limit: int = DEFAULT_LIMIT,
        min_pressure: float = DEFAULT_MIN_PRESSURE,
    ) -> list[dict[str, Any]]:
        """Filter active contradictions by status and pressure, rank by pressure + topic boost."""
        contradiction_map = self.load_contradiction_map()
        candidates = []
        topic_tokens = set(topic.lower().replace("-", " ").split()) if topic else set()

        for cid, node in contradiction_map.items():
            status = str(node.get("status", "")).strip().lower()
            if status not in ACTIVE_STATUSES:
                continue
            pressure = 0.0
            try:
                pressure = float(node.get("pressure_value") or node.get("pressure_score") or 0.0)
            except (TypeError, ValueError):
                pass
            if pressure < min_pressure:
                continue

            # Topic relevance boost
            relevance_boost = 0.0
            if topic_tokens:
                node_text = " ".join(filter(None, [
                    str(node.get("contradiction_id", cid)).lower().replace("-", " "),
                    str(node.get("description", "")).lower(),
                    str(node.get("statement", "")).lower(),
                    " ".join(str(t).lower() for t in (node.get("linked_concepts") or [])),
                ])).split()
                node_tokens = set(node_text)
                overlap = topic_tokens & node_tokens
                if overlap:
                    relevance_boost = TOPIC_RELEVANCE_BOOST * (len(overlap) / max(len(topic_tokens), 1))

            candidates.append({
                "contradiction_id": cid,
                "node": node,
                "pressure": pressure,
                "relevance_boost": relevance_boost,
                "rank_score": pressure + relevance_boost,
            })

        candidates.sort(key=lambda c: (-c["rank_score"], c["contradiction_id"]))
        return candidates[:max(1, int(limit))]

    def build_contradiction_digest(
        self,
        topic: str = "",
        limit: int = DEFAULT_LIMIT,
        min_pressure: float = DEFAULT_MIN_PRESSURE,
    ) -> dict[str, Any]:
        """Build a structured digest of relevant contradictions."""
        selected = self.select_relevant_contradictions(topic=topic, limit=limit, min_pressure=min_pressure)
        items = []
        for c in selected:
            node = c["node"]
            items.append({
                "contradiction_id": c["contradiction_id"],
                "status": str(node.get("status", "")).strip(),
                "pressure": c["pressure"],
                "description": str(node.get("description") or node.get("statement") or "").strip(),
                "linked_concepts": list(node.get("linked_concepts") or []),
                "severity": str(node.get("severity", "")).strip(),
            })
        return {
            "count": len(items),
            "highest_pressure": max((c["pressure"] for c in selected), default=0.0),
            "topic": topic,
            "items": items,
            "warnings": list(self._warnings),
            "substrate_available": bool(self._contradiction_map),
        }

    def format_contradiction_context_for_prompt(
        self,
        topic: str = "",
        limit: int = DEFAULT_LIMIT,
        min_pressure: float = DEFAULT_MIN_PRESSURE,
    ) -> str:
        """Format contradiction context as a compact string for injection into king synthesis prompt."""
        digest = self.build_contradiction_digest(topic=topic, limit=limit, min_pressure=min_pressure)
        if not digest["items"]:
            return ""
        lines = ["--- ACTIVE CONTRADICTIONS / EPISTEMIC PRESSURE ---"]
        for item in digest["items"]:
            pressure_str = f"{item['pressure']:.2f}"
            desc = item["description"] or item["contradiction_id"]
            lines.append(f"[{item['status'].upper()} p={pressure_str}] {item['contradiction_id']}: {desc}")
        lines.append("")
        lines.append(SYNTHESIS_INSTRUCTION)
        return "\n".join(lines)
