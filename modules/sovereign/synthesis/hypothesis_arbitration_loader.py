"""Phase 20.3 — read-only loader for evidence-balanced arbitration advisory."""
from __future__ import annotations

import json
import os
from typing import Any

# Hypothesis lineage states that raise scrutiny
HIGH_SCRUTINY_STATES = {"weakened", "falsified", "deprecated"}
NEGATIVE_BALANCE_THRESHOLD = -1.0
HIGH_PRESSURE_THRESHOLD = 7.0
HIGH_CONTRADICTION_PRESSURE = 5.0


class HypothesisArbitrationLoader:
    def __init__(self, cognition_root: str | None = None) -> None:
        self._cognition_root = str(cognition_root or os.environ.get("SOVEREIGN_COGNITION_ROOT", "")).strip()
        self._hypothesis_map: dict[str, dict[str, Any]] | None = None
        self._contradiction_map: dict[str, dict[str, Any]] | None = None
        self._warnings: list[str] = []

    # -------------------------------------------------------------------------
    # Internal loaders

    def _load_hypothesis_map(self) -> dict[str, dict[str, Any]]:
        if self._hypothesis_map is not None:
            return self._hypothesis_map
        result: dict[str, dict[str, Any]] = {}
        if not self._cognition_root or not os.path.isdir(self._cognition_root):
            self._hypothesis_map = result
            return result

        # JSONL nodes (last-line-wins)
        nodes_path = os.path.join(self._cognition_root, "hypotheses", "hypothesis_nodes.jsonl")
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
                            self._warnings.append(f"malformed JSONL at hypothesis_nodes.jsonl line {line_num}")
                            continue
                        if not isinstance(node, dict):
                            continue
                        hid = str(node.get("hypothesis_id") or node.get("id") or "").strip()
                        if hid:
                            result[hid] = node
            except OSError as exc:
                self._warnings.append(f"could not read hypothesis_nodes.jsonl: {exc}")

        # Index supplement
        index_path = os.path.join(self._cognition_root, "hypotheses", "hypothesis_index.json")
        if os.path.isfile(index_path):
            try:
                with open(index_path, "r", encoding="utf-8") as fh:
                    index = json.load(fh)
                if isinstance(index, dict):
                    for hid, entry in index.items():
                        if hid not in result and isinstance(entry, dict):
                            result[str(hid)] = entry
            except (OSError, json.JSONDecodeError) as exc:
                self._warnings.append(f"could not read hypothesis_index.json: {exc}")

        self._hypothesis_map = result
        return result

    def _load_contradiction_map(self) -> dict[str, dict[str, Any]]:
        if self._contradiction_map is not None:
            return self._contradiction_map
        result: dict[str, dict[str, Any]] = {}
        if not self._cognition_root or not os.path.isdir(self._cognition_root):
            self._contradiction_map = result
            return result

        nodes_path = os.path.join(self._cognition_root, "contradictions", "contradiction_nodes.jsonl")
        if os.path.isfile(nodes_path):
            try:
                with open(nodes_path, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            node = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(node, dict):
                            continue
                        cid = str(node.get("contradiction_id") or node.get("id") or "").strip()
                        if cid:
                            result[cid] = node
            except OSError:
                pass

        self._contradiction_map = result
        return result

    # -------------------------------------------------------------------------
    # Public API

    def find_matching_hypotheses(
        self,
        claim_text: str,
        topic: str = "",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Find hypotheses relevant to claim_text using deterministic scoring."""
        hypothesis_map = self._load_hypothesis_map()
        if not hypothesis_map:
            return []

        query_tokens = set(
            (claim_text + " " + topic).lower().replace("-", " ").split()
        )
        scored = []
        for hid, node in hypothesis_map.items():
            score = 0.0
            title = str(node.get("title") or "").lower()
            statement = str(node.get("statement") or node.get("description") or "").lower()
            summary = str(node.get("summary") or "").lower()
            domain_tags = [str(t).lower() for t in (node.get("domain_tags") or [])]

            # title substring
            if title and title in claim_text.lower():
                score += 3.0
            elif title and any(tok in title for tok in query_tokens if len(tok) > 3):
                score += 1.5

            # ID substring
            hid_norm = hid.lower().replace("-", " ")
            if hid_norm in claim_text.lower():
                score += 2.0
            elif any(tok in hid_norm for tok in query_tokens if len(tok) > 4):
                score += 0.8

            # statement Jaccard
            stmt_tokens = set(statement.split())
            if stmt_tokens and query_tokens:
                jaccard = len(stmt_tokens & query_tokens) / max(len(stmt_tokens | query_tokens), 1)
                score += jaccard * 2.0

            # summary Jaccard
            sum_tokens = set(summary.split())
            if sum_tokens and query_tokens:
                jaccard = len(sum_tokens & query_tokens) / max(len(sum_tokens | query_tokens), 1)
                score += jaccard * 1.5

            # domain tag match
            for tag in domain_tags:
                if tag in query_tokens or any(tok in tag for tok in query_tokens if len(tok) > 3):
                    score += 0.5

            if score > 0.0:
                scored.append((score, hid, node))

        scored.sort(key=lambda x: (-x[0], x[1]))
        results = []
        for score, hid, node in scored[:max(1, int(limit))]:
            results.append({"hypothesis_id": hid, "node": node, "match_score": score})
        return results

    def build_advisory(
        self,
        claim_text: str,
        topic: str = "",
        limit: int = 5,
        fail_closed: bool = False,
    ) -> dict[str, Any]:
        """Build an evidence-balanced advisory for arbitration. Never decides truth."""
        matched = self.find_matching_hypotheses(claim_text=claim_text, topic=topic, limit=limit)
        contradiction_map = self._load_contradiction_map()

        scrutiny_level = "standard"
        evidence_balance_effect = "none"
        recommended_action = "proceed_standard"
        warnings: list[str] = list(self._warnings)
        matched_hypotheses: list[dict[str, Any]] = []
        linked_contradictions: list[dict[str, Any]] = []

        for m in matched:
            hid = m["hypothesis_id"]
            node = m["node"]

            # Extract fields
            evidence_balance = 0.0
            try:
                evidence_balance = float(node.get("evidence_balance") or 0.0)
            except (TypeError, ValueError):
                pass

            support_weight = 0.0
            try:
                support_weight = float(node.get("support_weight") or 0.0)
            except (TypeError, ValueError):
                pass

            opposition_weight = 0.0
            try:
                opposition_weight = float(node.get("opposition_weight") or 0.0)
            except (TypeError, ValueError):
                pass

            pressure_score = 0.0
            try:
                pressure_score = float(node.get("pressure_score") or 0.0)
            except (TypeError, ValueError):
                pass

            lineage_status = str(node.get("lineage_status") or node.get("status") or "").strip().lower()
            failure_conditions = list(node.get("failure_conditions") or [])
            linked_contradiction_ids = list(node.get("linked_contradictions") or node.get("contradiction_links") or [])

            matched_hypotheses.append({
                "hypothesis_id": hid,
                "lineage_status": lineage_status,
                "evidence_balance": evidence_balance,
                "support_weight": support_weight,
                "opposition_weight": opposition_weight,
                "pressure_score": pressure_score,
                "failure_conditions": failure_conditions,
                "linked_contradiction_ids": linked_contradiction_ids,
            })

            # Linked contradictions raise scrutiny
            for cid in linked_contradiction_ids:
                cnode = contradiction_map.get(str(cid))
                if cnode:
                    c_pressure = 0.0
                    try:
                        c_pressure = float(cnode.get("pressure_value") or cnode.get("pressure_score") or 0.0)
                    except (TypeError, ValueError):
                        pass
                    linked_contradictions.append({
                        "contradiction_id": cid,
                        "status": str(cnode.get("status", "")).strip(),
                        "pressure": c_pressure,
                    })
                    if c_pressure >= HIGH_CONTRADICTION_PRESSURE:
                        scrutiny_level = "elevated"

            # Scrutiny upgrades from hypothesis state
            if lineage_status in HIGH_SCRUTINY_STATES:
                scrutiny_level = "high"
            elif pressure_score >= HIGH_PRESSURE_THRESHOLD:
                if scrutiny_level not in ("high",):
                    scrutiny_level = "elevated"

            # Evidence balance effect
            if evidence_balance < NEGATIVE_BALANCE_THRESHOLD:
                evidence_balance_effect = "negative_balance"
                if scrutiny_level == "standard":
                    scrutiny_level = "elevated"
            elif support_weight > opposition_weight and evidence_balance > 0:
                if evidence_balance_effect == "none":
                    evidence_balance_effect = "positive_support"
            elif opposition_weight > 0:
                if evidence_balance_effect == "none":
                    evidence_balance_effect = "weak_support"

        # Derive recommended action
        if scrutiny_level == "high":
            recommended_action = "apply_elevated_scrutiny"
            if fail_closed:
                recommended_action = "fail_closed_on_weak_evidence"
        elif scrutiny_level == "elevated":
            recommended_action = "flag_for_manual_review"
        elif evidence_balance_effect == "positive_support":
            recommended_action = "proceed_with_confidence_note"

        substrate_available = bool(self._load_hypothesis_map())

        return {
            "enabled": True,
            "mode": "advisory",
            "substrate_available": substrate_available,
            "matched_hypotheses": matched_hypotheses,
            "linked_contradictions": linked_contradictions,
            "scrutiny_level": scrutiny_level,
            "evidence_balance_effect": evidence_balance_effect,
            "recommended_action": recommended_action,
            "warnings": warnings,
        }
