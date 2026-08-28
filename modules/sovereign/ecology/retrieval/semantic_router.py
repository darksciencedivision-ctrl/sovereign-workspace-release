from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

THIS_FILE = Path(__file__).resolve()
ROOT_CANDIDATE = THIS_FILE.parents[2]
if str(ROOT_CANDIDATE) not in sys.path:
    sys.path.insert(0, str(ROOT_CANDIDATE))

from ecology.ecology_core import (
    append_jsonl,
    build_query_id,
    get_paths,
    normalize_identifier,
    read_json,
    read_jsonl,
    read_path_text,
    recency_score,
    relative_to_root,
    summarize_text,
    tokenize,
    unique_preserve_order,
    utc_now,
    write_json_atomic,
)


TIER_LABELS = {
    0: "runtime_contracts_and_safety",
    1: "operator_decisions_and_canonical_runtime",
    2: "compressed_summaries_and_semantic_consolidations",
    3: "ontology_truth_and_abstraction_graphs",
    4: "research_and_replay_only_references",
}

TIER_PRIORS = {
    0: 1.0,
    1: 0.92,
    2: 0.78,
    3: 0.62,
    4: 0.38,
}


def _load_truth_rows(paths) -> list[dict[str, Any]]:
    rows = read_jsonl(paths.library / "index" / "truth_weight_registry.jsonl")
    return [row for row in rows if isinstance(row, dict)]


def _load_contradictions(paths) -> list[dict[str, Any]]:
    rows = read_jsonl(paths.library / "index" / "contradiction_registry.jsonl")
    return [row for row in rows if isinstance(row, dict)]


def _ontology_concepts(paths) -> list[dict[str, Any]]:
    graph = read_json(paths.library / "index" / "ontology_graph.json", default={}) or {}
    concepts = graph.get("concepts", [])
    return [concept for concept in concepts if isinstance(concept, dict)]


def _query_concepts(query_tokens: list[str], concepts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for concept in concepts:
        corpus = " ".join(
            [
                str(concept.get("canonical_name", "")),
                str(concept.get("definition", "")),
                " ".join(str(alias) for alias in concept.get("aliases", [])),
            ]
        ).lower()
        if any(token in corpus for token in query_tokens):
            matches.append(concept)
    return matches


def _candidate(
    *,
    paths,
    path: Path,
    tier: int,
    source_type: str,
    summary: str,
    text: str,
    canonical: bool = False,
    operator_confirmed: bool = False,
    replay_only: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(metadata or {})
    rel_path = relative_to_root(path, paths.root)
    item_id = metadata.get("item_id") or f"{normalize_identifier(source_type)}::{normalize_identifier(path.stem)}"
    snippet = summarize_text(text, limit=340)
    candidate = {
        "item_id": item_id,
        "path": str(path),
        "relative_path": rel_path,
        "tier": tier,
        "tier_label": TIER_LABELS[tier],
        "source_type": source_type,
        "summary": summary,
        "snippet": snippet,
        "canonical": canonical,
        "operator_confirmed": operator_confirmed,
        "replay_only": replay_only,
        "safety_critical": tier == 0,
        "metadata": metadata,
        "recency_score": recency_score(path=path, timestamp_text=metadata.get("timestamp_utc")),
    }
    return candidate


def _safe_source_candidates(paths, query_tokens: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    raw_archive_blocked = 0

    tier0_sources = [
        (paths.library / "index" / "runtime_contract.json", "runtime contract", "runtime_contract", True),
        (paths.library / "config" / "runtime_mode.json", "runtime mode safety state", "runtime_mode", True),
        (paths.library / "config" / "authority_policy.json", "authority policy", "authority_policy", True),
        (paths.root / "security" / "path_authority_policy.json", "path authority policy", "path_policy", True),
    ]
    for path, summary, source_type, canonical in tier0_sources:
        if not path.exists():
            continue
        candidates.append(
            _candidate(
                paths=paths,
                path=path,
                tier=0,
                source_type=source_type,
                summary=summary,
                text=read_path_text(path),
                canonical=canonical,
            )
        )

    tier1_sources = [
        (paths.root / "CORE_RUNTIME_INDEX.md", "canonical runtime index", "canonical_runtime_state", True, True),
        (paths.root / "runtime_profile.json", "runtime profile", "runtime_profile", True, False),
    ]
    for path, summary, source_type, canonical, operator_confirmed in tier1_sources:
        if not path.exists():
            continue
        candidates.append(
            _candidate(
                paths=paths,
                path=path,
                tier=1,
                source_type=source_type,
                summary=summary,
                text=read_path_text(path),
                canonical=canonical,
                operator_confirmed=operator_confirmed,
            )
        )

    decisions_dir = paths.library / "memory" / "operator_decisions"
    for path in sorted(decisions_dir.glob("*")):
        if path.is_file() and path.suffix.lower() in {".json", ".jsonl"}:
            candidates.append(
                _candidate(
                    paths=paths,
                    path=path,
                    tier=1,
                    source_type="operator_decision",
                    summary=f"operator decision record: {path.name}",
                    text=read_path_text(path),
                    operator_confirmed=True,
                )
            )

    summaries_dir = paths.library / "memory" / "compressed" / "batch_001"
    for path in sorted(summaries_dir.glob("*.summary.md")):
        candidates.append(
            _candidate(
                paths=paths,
                path=path,
                tier=2,
                source_type="compressed_summary",
                summary=f"compressed summary: {path.stem}",
                text=read_path_text(path),
                operator_confirmed=True,
            )
        )

    tier3_sources = [
        (paths.library / "index" / "ontology_graph.json", "ontology graph", "ontology_graph"),
        (paths.library / "index" / "truth_weight_registry.jsonl", "truth-weight registry", "truth_registry"),
        (paths.abstraction_graphs / "abstraction_graph.json", "abstraction graph", "abstraction"),
        (paths.abstraction_graphs / "concept_inheritance_graph.json", "concept inheritance graph", "abstraction"),
    ]
    for path, summary, source_type in tier3_sources:
        if not path.exists():
            continue
        candidates.append(
            _candidate(
                paths=paths,
                path=path,
                tier=3,
                source_type=source_type,
                summary=summary,
                text=read_path_text(path),
                canonical=source_type in {"ontology_graph", "truth_registry"},
            )
        )

    evidence_dir = paths.root / "research" / "evidence_index"
    evidence_files = sorted(evidence_dir.glob("EVIDENCE_INDEX_*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for path in evidence_files[:3]:
        candidates.append(
            _candidate(
                paths=paths,
                path=path,
                tier=4,
                source_type="research_evidence",
                summary=f"research evidence index: {path.name}",
                text=read_path_text(path),
                replay_only=True,
            )
        )

    artifact_rows = read_jsonl(paths.library / "index" / "artifact_registry.jsonl")
    matched_artifacts = 0
    for row in artifact_rows:
        if not isinstance(row, dict):
            continue
        path_text = str(row.get("path", ""))
        if "\\archive\\" in path_text.lower():
            raw_archive_blocked += 1
            continue
        haystack = " ".join(
            [
                path_text.lower(),
                str(row.get("subsystem", "")).lower(),
                str(row.get("artifact_type", "")).lower(),
                str(row.get("canonical_status", "")).lower(),
            ]
        )
        if query_tokens and not any(token in haystack for token in query_tokens):
            continue
        canonical_status = str(row.get("canonical_status", "unknown")).lower()
        tier = 1 if canonical_status == "canonical" else 4 if canonical_status == "research_evidence" else 3
        candidates.append(
            {
                "item_id": row.get("artifact_id"),
                "path": path_text,
                "relative_path": path_text,
                "tier": tier,
                "tier_label": TIER_LABELS[tier],
                "source_type": "artifact_registry",
                "summary": f"{row.get('artifact_type', 'artifact')} in subsystem {row.get('subsystem', 'unknown')}",
                "snippet": summarize_text(haystack, limit=240),
                "canonical": canonical_status == "canonical",
                "operator_confirmed": False,
                "replay_only": bool(row.get("replay_required")),
                "safety_critical": False,
                "metadata": row,
                "recency_score": recency_score(timestamp_text=row.get("modified_utc")),
            }
        )
        matched_artifacts += 1
        if matched_artifacts >= 18:
            break

    if raw_archive_blocked:
        suppressed.append(
            {
                "item_id": "aggregate::raw_archive_blocked",
                "path": "archive",
                "reason": "raw_archive_blocked",
                "suppressed_count": raw_archive_blocked,
                "why_suppressed": "Raw archive retrieval is blocked from live ecological routing.",
            }
        )

    return candidates, suppressed


def route_semantic_query(
    query: str,
    *,
    root: str | Path | None = None,
    max_results: int = 12,
) -> dict[str, Any]:
    started = time.perf_counter()
    paths = get_paths(root)
    query_id = build_query_id(query)
    query_tokens = tokenize(query)
    concepts = _ontology_concepts(paths)
    matched_query_concepts = _query_concepts(query_tokens, concepts)
    truth_rows = _load_truth_rows(paths)
    contradictions = _load_contradictions(paths)
    candidates, suppressed_results = _safe_source_candidates(paths, query_tokens)
    ranking_rows: list[dict[str, Any]] = []

    for candidate in candidates:
        haystack = " ".join(
            [
                str(candidate.get("summary", "")).lower(),
                str(candidate.get("snippet", "")).lower(),
                str(candidate.get("path", "")).lower(),
            ]
        )
        matched_terms = [token for token in query_tokens if token in haystack]
        ontology_terms = []
        for concept in matched_query_concepts:
            aliases = [str(alias).lower() for alias in concept.get("aliases", [])]
            concept_name = str(concept.get("canonical_name", "")).lower()
            concept_terms = [concept_name, *aliases]
            if any(term and term in haystack for term in concept_terms):
                ontology_terms.append(concept.get("canonical_name"))
        truth_matches = []
        truth_weight = 0.0
        for row in truth_rows:
            claim_text = str(row.get("claim", "")).lower()
            evidence_paths = [str(path).lower() for path in row.get("evidence_artifacts", []) if isinstance(path, str)]
            if any(token in claim_text for token in matched_terms) or str(candidate.get("path", "")).lower() in evidence_paths:
                truth_matches.append(row.get("claim_id"))
                truth_weight = max(truth_weight, float(row.get("truth_weight", 0.0) or 0.0))

        contradiction_flags = []
        for row in contradictions:
            values = " ".join(str(value).lower() for value in row.values())
            if str(candidate.get("path", "")).lower() in values or any(token in values for token in matched_terms):
                contradiction_flags.append(row.get("contradiction_id") or row.get("claim_id") or "unresolved_contradiction")

        query_relevance = len(matched_terms) / max(1, len(query_tokens)) if query_tokens else 0.5
        ontology_relevance = len(ontology_terms) / max(1, len(matched_query_concepts)) if matched_query_concepts else 0.0
        canonical_bonus = 0.12 if candidate.get("canonical") else 0.0
        operator_bonus = 0.12 if candidate.get("operator_confirmed") else 0.0
        summary_bonus = 0.08 if candidate.get("source_type") == "compressed_summary" else 0.0
        replay_penalty = 0.18 if candidate.get("replay_only") else 0.0
        contradiction_penalty = min(0.25, 0.15 * len(contradiction_flags))
        tier_prior = TIER_PRIORS[int(candidate.get("tier", 4))]
        recency = float(candidate.get("recency_score", 0.0) or 0.0)

        score = (
            (0.42 * query_relevance)
            + (0.18 * tier_prior)
            + (0.14 * ontology_relevance)
            + (0.14 * truth_weight)
            + (0.12 * recency)
            + canonical_bonus
            + operator_bonus
            + summary_bonus
            - replay_penalty
            - contradiction_penalty
        )
        reasons = []
        if int(candidate.get("tier", 4)) == 0:
            reasons.append("safety tier priority")
        if candidate.get("canonical"):
            reasons.append("canonical memory")
        if candidate.get("operator_confirmed"):
            reasons.append("operator-confirmed memory")
        if candidate.get("source_type") == "compressed_summary":
            reasons.append("compressed summary coverage")
        if ontology_terms:
            reasons.append("ontology match: " + ", ".join(ontology_terms[:3]))
        if truth_weight:
            reasons.append(f"truth weight {truth_weight:.2f}")
        if contradiction_flags:
            reasons.append("contradiction surfaced")
        if not reasons:
            reasons.append("fallback semantic coverage")

        row = dict(candidate)
        row["matched_terms"] = matched_terms
        row["ontology_terms"] = ontology_terms
        row["truth_weight"] = round(truth_weight, 4)
        row["truth_match_ids"] = truth_matches
        row["contradiction_flags"] = contradiction_flags
        row["score"] = round(score, 4)
        row["score_breakdown"] = {
            "query_relevance": round(query_relevance, 4),
            "tier_prior": round(tier_prior, 4),
            "ontology_relevance": round(ontology_relevance, 4),
            "truth_weight": round(truth_weight, 4),
            "recency": round(recency, 4),
            "canonical_bonus": round(canonical_bonus, 4),
            "operator_bonus": round(operator_bonus, 4),
            "summary_bonus": round(summary_bonus, 4),
            "replay_penalty": round(replay_penalty, 4),
            "contradiction_penalty": round(contradiction_penalty, 4),
        }
        row["selection_reasons"] = reasons
        ranking_rows.append(row)

    ranking_rows.sort(key=lambda item: (float(item.get("score", 0.0)), -int(item.get("tier", 4))), reverse=True)
    retrieved_items = ranking_rows[:max_results]
    ranking_explanations = [
        {
            "rank": index,
            "item_id": item.get("item_id"),
            "path": item.get("path"),
            "score": item.get("score"),
            "reasons": item.get("selection_reasons", []),
            "score_breakdown": item.get("score_breakdown", {}),
        }
        for index, item in enumerate(retrieved_items, start=1)
    ]
    truth_weights = [
        {
            "item_id": item.get("item_id"),
            "truth_weight": item.get("truth_weight"),
            "claim_ids": item.get("truth_match_ids", []),
        }
        for item in retrieved_items
        if item.get("truth_match_ids")
    ]
    contradiction_values = unique_preserve_order(
        [flag for item in retrieved_items for flag in item.get("contradiction_flags", [])]
    )

    payload = {
        "query_id": query_id,
        "query": query,
        "retrieved_items": retrieved_items,
        "ranking_explanations": ranking_explanations,
        "ontology_terms": unique_preserve_order(
            [term for item in retrieved_items for term in item.get("ontology_terms", [])]
        ),
        "truth_weights": truth_weights,
        "contradictions": contradiction_values,
        "suppressed_results": suppressed_results,
        "retrieval_strategy": (
            "tiered_semantic_router:candidate_sources=tier0-4,"
            "weights=canonical+operator+ontology+truth+recency,"
            "raw_archive=blocked,contradictions=surfaced"
        ),
        "retrieval_reasoning": (
            "Canonical safety memory and operator-confirmed documents were favored first, "
            "compressed summaries were used for semantic continuity, and replay-only evidence "
            "was penalized unless it matched the query strongly."
        ),
        "created_utc": utc_now(),
    }
    route_path = paths.retrieval / f"semantic_route_{query_id}.json"
    write_json_atomic(route_path, payload)
    append_jsonl(
        paths.telemetry / "retrieval_metrics.jsonl",
        {
            "event_type": "semantic_router",
            "query_id": query_id,
            "created_utc": utc_now(),
            "retrieval_latency_ms": int((time.perf_counter() - started) * 1000),
            "retrieval_depth": len(ranking_rows),
            "ontology_hit_rate": round(
                len([item for item in retrieved_items if item.get("ontology_terms")]) / max(1, len(retrieved_items)), 4
            ),
            "abstraction_hit_rate": round(
                len([item for item in retrieved_items if item.get("source_type") == "abstraction"]) / max(1, len(retrieved_items)),
                4,
            ),
            "contradiction_density": round(len(contradiction_values) / max(1, len(retrieved_items)), 4),
            "suppression_rate": round(len(suppressed_results) / max(1, len(candidates) + len(suppressed_results)), 4),
            "semantic_relevance": round(
                sum(float(item.get("score", 0.0)) for item in retrieved_items) / max(1, len(retrieved_items)),
                4,
            ),
            "retrieval_failures": 0,
            "unresolved_contradictions": len(contradiction_values),
        },
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Route an ecological semantic retrieval query.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--root", default=None)
    parser.add_argument("--max-results", type=int, default=12)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    payload = route_semantic_query(args.query, root=args.root, max_results=args.max_results)
    if args.out:
        write_json_atomic(Path(args.out), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
