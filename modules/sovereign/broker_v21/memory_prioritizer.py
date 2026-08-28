from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

THIS_FILE = Path(__file__).resolve()
ROOT_CANDIDATE = THIS_FILE.parents[1]
if str(ROOT_CANDIDATE) not in sys.path:
    sys.path.insert(0, str(ROOT_CANDIDATE))

from ecology.abstraction_graphs.abstraction_builder import build_abstractions
from ecology.arbitration.retrieval_arbitrator import arbitrate_results
from ecology.ecology_core import (
    append_jsonl,
    get_paths,
    read_json,
    read_jsonl,
    utc_now,
    write_json_atomic,
)
from ecology.economics.cognitive_budget import apply_cognitive_budget
from ecology.ontology.ontology_stabilizer import build_semantic_physics
from ecology.retrieval.semantic_router import route_semantic_query
from ecology.telemetry.memory_packet_explainer import generate_memory_packet_report


def _contract_constraints(paths) -> list[str]:
    contract = read_json(paths.library / "index" / "runtime_contract.json", default={}) or {}
    if not isinstance(contract, dict):
        return []
    ordered_keys = [
        "fail_closed",
        "deletion_enabled",
        "DELETE_DISABLED",
        "no_uri_authority_expansion",
        "no_auto_promotion",
        "no_direct_sandbox_writes",
        "no_raw_archive_runtime_retrieval",
        "library_is_semantic_governance_layer",
    ]
    return [f"{key}={contract.get(key)}" for key in ordered_keys if key in contract]


def build_memory_packet(
    topic: str,
    *,
    root: str | Path | None = None,
    max_items: int = 12,
    output_path: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    paths = get_paths(root)

    build_abstractions(root=paths.root)
    build_semantic_physics(root=paths.root)

    routed = route_semantic_query(topic, root=paths.root, max_results=max_items * 3)
    arbitration = arbitrate_results(routed["query_id"], routed["retrieved_items"], root=paths.root)
    budgeted = apply_cognitive_budget(
        arbitration["selected_items"],
        root=paths.root,
        query_id=routed["query_id"],
    )

    selected_items: list[dict[str, Any]] = []
    for rank, item in enumerate(budgeted["selected_items"], start=1):
        selected_items.append(
            {
                "rank": rank,
                "item_id": item.get("item_id"),
                "path": item.get("path"),
                "tier": item.get("tier"),
                "source_type": item.get("source_type"),
                "confidence": round(float(item.get("final_confidence", item.get("score", 0.0)) or 0.0), 4),
                "ontology_relationship": item.get("ontology_terms", []),
                "truth_weight": item.get("truth_weight", 0.0),
                "contradiction_flags": item.get("contradiction_flags", []),
                "memory_cost_estimate": item.get("memory_cost_estimate", {}),
                "why_selected": "; ".join(item.get("selection_reasons", [])) or "selected_by_ranked_relevance",
                "summary": item.get("summary", ""),
                "snippet": item.get("snippet", ""),
                "score_breakdown": item.get("score_breakdown", {}),
                "arbitration_breakdown": item.get("arbitration_breakdown", {}),
            }
        )

    suppressed_results = []
    for group in (
        routed.get("suppressed_results", []),
        arbitration.get("suppressed_items", []),
        budgeted.get("suppressed_items", []),
    ):
        for item in group:
            suppressed_results.append(
                {
                    "item_id": item.get("item_id"),
                    "path": item.get("path"),
                    "reason": item.get("reason", "suppressed"),
                    "confidence": item.get("final_confidence", item.get("confidence")),
                    "why_suppressed": item.get("why_suppressed") or item.get("reason", "suppressed"),
                }
            )

    contradictions = []
    for item in selected_items:
        contradictions.extend(item.get("contradiction_flags", []))

    operator_decision_rows = []
    for path in sorted((paths.library / "memory" / "operator_decisions").glob("*")):
        if path.suffix.lower() == ".json":
            payload = read_json(path, default={}) or {}
            operator_decision_rows.append({"path": str(path), "summary": payload.get("decision") or payload.get("approval_status")})
        elif path.suffix.lower() == ".jsonl":
            rows = read_jsonl(path)
            operator_decision_rows.extend(
                {
                    "path": str(path),
                    "summary": row.get("decision"),
                    "decision_id": row.get("decision_id"),
                }
                for row in rows[:10]
            )

    packet = {
        "query_id": routed["query_id"],
        "topic": topic,
        "retrieved_artifacts": selected_items,
        "selected_items": selected_items,
        "canonical_constraints": _contract_constraints(paths),
        "known_contradictions": contradictions,
        "relevant_prior_decisions": operator_decision_rows[:20],
        "ontology_terms": routed.get("ontology_terms", []),
        "truth_weights": routed.get("truth_weights", []),
        "ranking_explanations": routed.get("ranking_explanations", []),
        "retrieval_strategy": routed.get("retrieval_strategy"),
        "retrieval_reasoning": routed.get("retrieval_reasoning"),
        "suppressed_results": suppressed_results,
        "suppressed_items": suppressed_results,
        "contradictions": contradictions,
        "attention_budget": budgeted.get("budget", {}),
        "budget_explanation": budgeted.get("budget", {}).get("budget_explanation", ""),
        "packet_status": budgeted.get("budget", {}).get("status", "PASS"),
        "packet_compression": {
            "original_candidate_count": len(routed.get("retrieved_items", [])),
            "selected_count": len(selected_items),
            "suppressed_count": len(suppressed_results),
            "compression_ratio": round(
                len(selected_items) / max(1, len(routed.get("retrieved_items", []))),
                4,
            ),
        },
        "arbitration": {
            "report_path": arbitration.get("report_path"),
            "selected_count": len(arbitration.get("selected_items", [])),
            "suppressed_count": len(arbitration.get("suppressed_items", [])),
            "unresolved_contradictions": arbitration.get("report", {}).get("unresolved_contradictions", []),
        },
        "created_utc": utc_now(),
    }

    report_info = generate_memory_packet_report(packet, root=paths.root)
    packet["explainability_report_path"] = report_info["report_path"]
    ecology_packet_path = paths.memory_packets / f"memory_packet_{routed['query_id']}.json"
    write_json_atomic(ecology_packet_path, packet)
    write_json_atomic(paths.memory_packets / "latest_memory_packet.json", packet)

    append_jsonl(
        paths.telemetry / "retrieval_metrics.jsonl",
        {
            "event_type": "memory_prioritizer",
            "query_id": routed["query_id"],
            "created_utc": utc_now(),
            "selected_count": len(selected_items),
            "suppressed_count": len(suppressed_results),
            "packet_compression_ratio": packet["packet_compression"]["compression_ratio"],
            "redundancy_reduction": round(
                len([item for item in suppressed_results if item.get("reason") == "redundant_retrieval"])
                / max(1, len(suppressed_results)),
                4,
            ),
            "status": packet["packet_status"],
            "budget_warning": packet["packet_status"] == "WARN",
        },
    )

    final_output_path = Path(output_path) if output_path else paths.root / "broker_v21" / "inbox" / "memory_context_packet.json"
    if not dry_run:
        write_json_atomic(final_output_path, packet)
    return {
        "packet": packet,
        "ecology_packet_path": str(ecology_packet_path),
        "broker_output_path": str(final_output_path),
        "report_path": report_info["report_path"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an explainable ecological memory packet.")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--root", default=None)
    parser.add_argument("--max-items", type=int, default=12)
    parser.add_argument("--out", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    build_memory_packet(
        args.topic,
        root=args.root,
        max_items=args.max_items,
        output_path=args.out,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
