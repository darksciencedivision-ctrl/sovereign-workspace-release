from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

THIS_FILE = Path(__file__).resolve()
ROOT_CANDIDATE = THIS_FILE.parents[2]
if str(ROOT_CANDIDATE) not in sys.path:
    sys.path.insert(0, str(ROOT_CANDIDATE))

from ecology.ecology_core import (
    append_jsonl,
    get_paths,
    normalize_identifier,
    read_json,
    unique_preserve_order,
    utc_now,
    write_json_atomic,
)


DIMENSION_WEIGHTS = {
    "truth_weight": 0.24,
    "ontology_alignment": 0.16,
    "operator_confirmation": 0.16,
    "recency": 0.1,
    "abstraction_relevance": 0.12,
    "runtime_relevance": 0.1,
    "retrieval_cost": 0.06,
    "contradiction_risk": -0.14,
}


def _dimension_breakdown(item: dict[str, Any]) -> dict[str, float]:
    truth_weight = float(item.get("truth_weight", 0.0) or 0.0)
    ontology_alignment = min(1.0, len(item.get("ontology_terms", [])) / 4.0)
    operator_confirmation = 1.0 if item.get("operator_confirmed") else 0.0
    recency = float(item.get("recency_score", 0.0) or 0.0)
    abstraction_relevance = 1.0 if item.get("source_type") in {"abstraction", "compressed_summary"} else 0.3
    runtime_relevance = 1.0 if int(item.get("tier", 99)) <= 1 else 0.5 if int(item.get("tier", 99)) == 2 else 0.2
    retrieval_cost = float(item.get("memory_cost_estimate", {}).get("estimated_tokens", 40))
    retrieval_cost_score = max(0.1, 1.0 - min(1.0, retrieval_cost / 1200.0))
    contradiction_risk = min(1.0, len(item.get("contradiction_flags", [])) / 2.0)
    return {
        "truth_weight": truth_weight,
        "ontology_alignment": round(ontology_alignment, 4),
        "operator_confirmation": operator_confirmation,
        "recency": recency,
        "abstraction_relevance": abstraction_relevance,
        "runtime_relevance": runtime_relevance,
        "retrieval_cost": round(retrieval_cost_score, 4),
        "contradiction_risk": round(contradiction_risk, 4),
    }


def _arbitration_score(item: dict[str, Any]) -> tuple[float, dict[str, float]]:
    breakdown = _dimension_breakdown(item)
    score = 0.0
    for key, value in breakdown.items():
        score += DIMENSION_WEIGHTS[key] * value
    return round(score, 4), breakdown


def _conflict_key(item: dict[str, Any]) -> str:
    if item.get("ontology_terms"):
        return normalize_identifier(str(item["ontology_terms"][0]))
    if item.get("path"):
        return normalize_identifier(Path(str(item["path"])).stem)
    return normalize_identifier(str(item.get("item_id", "candidate")))


def arbitrate_results(
    query_id: str,
    items: list[dict[str, Any]],
    *,
    root: str | Path | None = None,
    minimum_confidence: float = 0.32,
) -> dict[str, Any]:
    paths = get_paths(root)
    selected: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    best_by_conflict: dict[str, float] = {}
    decision_rows: list[dict[str, Any]] = []

    for raw_item in items:
        item = dict(raw_item)
        arbitration_score, breakdown = _arbitration_score(item)
        confidence = max(float(item.get("score", 0.0) or 0.0), arbitration_score)
        item["arbitration_score"] = arbitration_score
        item["arbitration_breakdown"] = breakdown
        item["final_confidence"] = round(confidence, 4)

        conflict_key = _conflict_key(item)
        contradiction_flags = item.get("contradiction_flags", [])
        is_canonical = bool(item.get("canonical"))
        is_operator_confirmed = bool(item.get("operator_confirmed"))
        reject_reason = None

        if confidence < minimum_confidence and not (is_canonical or is_operator_confirmed):
            reject_reason = "low_confidence_retrieval"
        elif contradiction_flags and not (is_canonical or is_operator_confirmed):
            reject_reason = "unresolved_contradiction_risk"
        elif conflict_key in best_by_conflict and arbitration_score < best_by_conflict[conflict_key]:
            reject_reason = "lower_ranked_conflict"

        if reject_reason is not None:
            suppressed.append(
                {
                    "item_id": item.get("item_id"),
                    "path": item.get("path"),
                    "reason": reject_reason,
                    "final_confidence": confidence,
                    "contradiction_flags": contradiction_flags,
                }
            )
            decision_rows.append(
                {
                    "item_id": item.get("item_id"),
                    "decision": "SUPPRESS",
                    "reason": reject_reason,
                    "arbitration_score": arbitration_score,
                    "created_utc": utc_now(),
                }
            )
            continue

        best_by_conflict[conflict_key] = max(arbitration_score, best_by_conflict.get(conflict_key, arbitration_score))
        selected.append(item)
        decision_rows.append(
            {
                "item_id": item.get("item_id"),
                "decision": "SELECT",
                "reason": "selected_by_arbitration",
                "arbitration_score": arbitration_score,
                "created_utc": utc_now(),
            }
        )

    selected.sort(key=lambda row: (float(row.get("arbitration_score", 0.0)), float(row.get("score", 0.0))), reverse=True)
    unresolved_contradictions = unique_preserve_order(
        [flag for item in selected for flag in item.get("contradiction_flags", [])]
    )

    report = {
        "query_id": query_id,
        "created_utc": utc_now(),
        "arbitration_dimensions": DIMENSION_WEIGHTS,
        "selected_count": len(selected),
        "suppressed_count": len(suppressed),
        "unresolved_contradictions": unresolved_contradictions,
        "decisions": decision_rows,
        "selected_items": [
            {
                "item_id": item.get("item_id"),
                "path": item.get("path"),
                "arbitration_score": item.get("arbitration_score"),
                "final_confidence": item.get("final_confidence"),
                "arbitration_breakdown": item.get("arbitration_breakdown"),
            }
            for item in selected
        ],
        "suppressed_results": suppressed,
    }
    report_path = paths.arbitration / f"retrieval_arbitration_{query_id}.json"
    write_json_atomic(report_path, report)
    append_jsonl(
        paths.telemetry / "retrieval_metrics.jsonl",
        {
            "event_type": "retrieval_arbitration",
            "query_id": query_id,
            "created_utc": utc_now(),
            "selected_count": len(selected),
            "suppressed_count": len(suppressed),
            "unresolved_contradictions": len(unresolved_contradictions),
        },
    )
    return {
        "selected_items": selected,
        "suppressed_items": suppressed,
        "report": report,
        "report_path": str(report_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Arbitrate ecological retrieval candidates.")
    parser.add_argument("--items", required=True, help="Input JSON file containing retrieval items.")
    parser.add_argument("--out", required=True, help="Output JSON file path.")
    parser.add_argument("--query-id", required=True)
    parser.add_argument("--root", default=None)
    args = parser.parse_args()

    payload = read_json(Path(args.items), default=[])
    if not isinstance(payload, list):
        raise SystemExit("items JSON must contain a list")
    result = arbitrate_results(args.query_id, payload, root=args.root)
    write_json_atomic(Path(args.out), result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
