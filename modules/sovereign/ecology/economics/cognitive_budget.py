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
    estimate_token_count,
    get_paths,
    read_json,
    stamp_now,
    utc_now,
    write_json_atomic,
)


DEFAULT_POLICY = {
    "max_packet_size": 12,
    "max_retrieval_depth": 24,
    "max_token_budget": 2600,
    "max_memory_budget": 14000,
    "max_semantic_attention_budget": 1.0,
    "max_contradiction_density": 0.25,
    "max_low_confidence_retrieval_ratio": 0.3,
    "abstraction_reward_multiplier": 1.2,
    "replay_penalty_multiplier": 0.55,
    "redundancy_penalty_multiplier": 0.45,
    "safety_memory_reserve": 3,
}


def load_policy(root: str | Path | None = None) -> dict[str, Any]:
    paths = get_paths(root)
    payload = read_json(paths.configs / "cognitive_budget_policy.json", default={}) or {}
    merged = dict(DEFAULT_POLICY)
    merged.update(payload)
    merged["generated_utc"] = payload.get("generated_utc", utc_now())
    merged["policy_path"] = str(paths.configs / "cognitive_budget_policy.json")
    return merged


def estimate_memory_cost(item: dict[str, Any]) -> dict[str, Any]:
    snippet = str(item.get("snippet", "") or item.get("summary", ""))
    token_estimate = estimate_token_count(snippet)
    semantic_units = max(1, len(item.get("ontology_terms", [])) + len(item.get("contradiction_flags", [])))
    memory_units = len(snippet)
    return {
        "estimated_tokens": token_estimate,
        "estimated_characters": memory_units,
        "semantic_units": semantic_units,
    }


def apply_cognitive_budget(
    items: list[dict[str, Any]],
    *,
    root: str | Path | None = None,
    query_id: str | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paths = get_paths(root)
    active_policy = dict(load_policy(root))
    if policy:
        active_policy.update(policy)

    max_packet_size = int(active_policy["max_packet_size"])
    max_retrieval_depth = int(active_policy["max_retrieval_depth"])
    max_token_budget = int(active_policy["max_token_budget"])
    max_memory_budget = int(active_policy["max_memory_budget"])
    max_contradiction_density = float(active_policy["max_contradiction_density"])
    max_low_conf_ratio = float(active_policy["max_low_confidence_retrieval_ratio"])
    redundancy_penalty_multiplier = float(active_policy["redundancy_penalty_multiplier"])

    selected: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    token_budget_used = 0
    memory_budget_used = 0
    contradiction_count = 0
    low_confidence_count = 0
    warning_reason_counts: dict[str, int] = {}
    seen_fingerprints: set[str] = set()
    packets_examined = 0

    for raw_item in items[:max_retrieval_depth]:
        packets_examined += 1
        item = dict(raw_item)
        cost = estimate_memory_cost(item)
        item["memory_cost_estimate"] = cost
        contradiction_flags = item.get("contradiction_flags", [])
        confidence = float(item.get("final_confidence", item.get("score", 0.0)) or 0.0)
        fingerprint = item.get("fingerprint") or item.get("path") or item.get("item_id")
        is_redundant = fingerprint in seen_fingerprints
        is_safety = bool(item.get("safety_critical")) or int(item.get("tier", 99)) == 0

        would_exceed_packet = len(selected) >= max_packet_size
        would_exceed_tokens = token_budget_used + int(cost["estimated_tokens"]) > max_token_budget
        would_exceed_memory = memory_budget_used + int(cost["estimated_characters"]) > max_memory_budget
        next_contradiction_density = (
            (contradiction_count + (1 if contradiction_flags else 0)) / max(1, len(selected) + 1)
        )
        next_low_conf_ratio = (
            (low_confidence_count + (1 if confidence < 0.5 else 0)) / max(1, len(selected) + 1)
        )

        suppress_reason = None
        if is_redundant and not is_safety:
            suppress_reason = "redundant_retrieval"
            item["score"] = round(float(item.get("score", 0.0)) * redundancy_penalty_multiplier, 4)
        elif would_exceed_packet and not is_safety:
            suppress_reason = "packet_size_limit"
        elif would_exceed_tokens and not is_safety:
            suppress_reason = "token_budget_limit"
        elif would_exceed_memory and not is_safety:
            suppress_reason = "memory_budget_limit"
        elif next_contradiction_density > max_contradiction_density and not is_safety:
            suppress_reason = "contradiction_density_limit"
        elif next_low_conf_ratio > max_low_conf_ratio and not is_safety:
            suppress_reason = "low_confidence_ratio_limit"

        if suppress_reason is not None:
            warning_reason_counts[suppress_reason] = warning_reason_counts.get(suppress_reason, 0) + 1
            suppressed.append(
                {
                    "item_id": item.get("item_id"),
                    "path": item.get("path"),
                    "reason": suppress_reason,
                    "confidence": confidence,
                    "memory_cost_estimate": cost,
                }
            )
            continue

        selected.append(item)
        seen_fingerprints.add(str(fingerprint))
        token_budget_used += int(cost["estimated_tokens"])
        memory_budget_used += int(cost["estimated_characters"])
        contradiction_count += 1 if contradiction_flags else 0
        low_confidence_count += 1 if confidence < 0.5 else 0

    budget_warning_count = sum(warning_reason_counts.values())
    budget_status = "WARN" if budget_warning_count else "PASS"
    budget = {
        "policy": active_policy,
        "selected_count": len(selected),
        "suppressed_count": len(suppressed),
        "retrieval_depth_examined": packets_examined,
        "token_budget_used": token_budget_used,
        "memory_budget_used": memory_budget_used,
        "contradiction_density": round(contradiction_count / max(1, len(selected)), 4),
        "low_confidence_ratio": round(low_confidence_count / max(1, len(selected)), 4),
        "status": budget_status,
        "budget_warning_count": budget_warning_count,
        "warning_reasons": warning_reason_counts,
        "explainability_note": "Budget enforcement preserved safety-critical memory and emitted explicit suppression reasons.",
        "budget_explanation": "Budget enforcement preserved safety-critical memory and emitted explicit suppression reasons.",
        "created_utc": utc_now(),
    }

    telemetry_event = {
        "event_type": "cognitive_budget",
        "query_id": query_id or f"budget_{stamp_now()}",
        "created_utc": utc_now(),
        "selected_count": len(selected),
        "suppressed_count": len(suppressed),
        "retrieval_depth_examined": packets_examined,
        "token_budget_used": token_budget_used,
        "memory_budget_used": memory_budget_used,
        "contradiction_density": budget["contradiction_density"],
        "low_confidence_ratio": budget["low_confidence_ratio"],
        "suppression_rate": round(len(suppressed) / max(1, packets_examined), 4),
        "status": budget_status,
        "budget_warning": budget_warning_count > 0,
        "budget_warning_count": budget_warning_count,
        "warning_reasons": warning_reason_counts,
    }
    append_jsonl(paths.telemetry / "retrieval_metrics.jsonl", telemetry_event)
    write_json_atomic(paths.economics / "latest_cognitive_budget.json", budget)

    return {
        "selected_items": selected,
        "suppressed_items": suppressed,
        "budget": budget,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply the ecological cognitive budget policy.")
    parser.add_argument("--root", default=None)
    parser.add_argument("--items", required=True, help="Path to a JSON file containing ranked retrieval items.")
    parser.add_argument("--out", required=True, help="Path to a JSON file for budgeted results.")
    args = parser.parse_args()

    items_path = Path(args.items)
    items = read_json(items_path, default=[])
    if not isinstance(items, list):
        raise SystemExit("items JSON must contain a list")

    payload = apply_cognitive_budget(items, root=args.root)
    write_json_atomic(Path(args.out), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
