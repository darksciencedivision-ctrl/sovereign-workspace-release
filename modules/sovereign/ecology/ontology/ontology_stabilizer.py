from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

THIS_FILE = Path(__file__).resolve()
ROOT_CANDIDATE = THIS_FILE.parents[2]
if str(ROOT_CANDIDATE) not in sys.path:
    sys.path.insert(0, str(ROOT_CANDIDATE))

from ecology.ecology_core import append_jsonl, get_paths, read_json, read_jsonl, utc_now, write_json_atomic


def build_semantic_physics(*, root: str | Path | None = None) -> dict[str, Any]:
    paths = get_paths(root)
    ontology = read_json(paths.library / "index" / "ontology_graph.json", default={}) or {}
    concepts = [concept for concept in ontology.get("concepts", []) if isinstance(concept, dict)]
    decisions_dir = paths.library / "memory" / "operator_decisions"
    drift_rows: list[dict[str, Any]] = []
    for file_path in sorted(decisions_dir.glob("*.jsonl")):
        drift_rows.extend(row for row in read_jsonl(file_path) if isinstance(row, dict))

    allowed_aliases: dict[str, list[str]] = {}
    deprecated_aliases: dict[str, list[str]] = {}
    canonical_concepts: list[dict[str, Any]] = []
    inheritance_relationships: list[dict[str, Any]] = []
    contradiction_relationships: list[dict[str, Any]] = []
    drift_findings: list[dict[str, Any]] = []
    stability_scores: dict[str, float] = {}
    seen_alias_targets: dict[str, str] = {}

    for concept in concepts:
        concept_id = str(concept.get("concept_id", "UNKNOWN_CONCEPT"))
        aliases = [str(alias) for alias in concept.get("aliases", [])]
        confidence = float(concept.get("confidence", 0.0) or 0.0)
        contradiction_count = len(concept.get("contradictions", []))
        stability = round(max(0.2, min(1.0, 0.55 + (0.25 * confidence) - (0.1 * contradiction_count))), 4)
        stability_scores[concept_id] = stability
        allowed_aliases[concept_id] = aliases

        for alias in aliases:
            key = alias.lower()
            if key in seen_alias_targets and seen_alias_targets[key] != concept_id:
                drift_findings.append(
                    {
                        "finding": "alias_collision",
                        "alias": alias,
                        "first_concept_id": seen_alias_targets[key],
                        "second_concept_id": concept_id,
                        "severity": "WARN",
                    }
                )
            else:
                seen_alias_targets[key] = concept_id

        for decision in drift_rows:
            term = str(decision.get("term", "")).strip()
            if not term:
                continue
            lowered = term.lower()
            canonical_terms = [str(concept.get("canonical_name", "")).lower(), *[alias.lower() for alias in aliases]]
            if lowered not in canonical_terms:
                continue
            if decision.get("decision") == "mark_legacy":
                deprecated_aliases.setdefault(concept_id, []).append(term)
            if decision.get("decision") in {"mark_legacy", "approve_exception"}:
                drift_findings.append(
                    {
                        "finding": "drift_classification",
                        "concept_id": concept_id,
                        "term": term,
                        "decision_id": decision.get("decision_id"),
                        "classification": decision.get("decision"),
                        "severity": "WARN" if decision.get("decision") == "mark_legacy" else "INFO",
                    }
                )

        canonical_concepts.append(
            {
                "concept_id": concept_id,
                "canonical_name": concept.get("canonical_name"),
                "definition": concept.get("definition"),
                "status": concept.get("status", "canonical"),
                "allowed_aliases": aliases,
                "stability_score": stability,
            }
        )

        if concept_id in {"CONCEPT_RUNTIME_FAIL_CLOSED", "CONCEPT_DELETION_DISABLED"}:
            inheritance_relationships.append(
                {
                    "parent": "CONCEPT_LIBRARY_SEMANTIC_GOVERNANCE",
                    "child": concept_id,
                    "relationship": "runtime_invariant",
                }
            )
        if concept_id.startswith("CONCEPT_TAX_"):
            inheritance_relationships.append(
                {
                    "parent": "CONCEPT_TAX_AGI",
                    "child": concept_id,
                    "relationship": "taxonomy_alignment",
                }
            )

        for contradiction in concept.get("contradictions", []):
            contradiction_relationships.append(
                {
                    "concept_id": concept_id,
                    "contradiction": contradiction,
                }
            )

    payload = {
        "schema_version": "18.4",
        "generated_utc": utc_now(),
        "canonical_concepts": canonical_concepts,
        "inheritance_relationships": inheritance_relationships,
        "allowed_aliases": allowed_aliases,
        "deprecated_aliases": {
            key: sorted(set(values), key=str.lower) for key, values in deprecated_aliases.items()
        },
        "contradiction_relationships": contradiction_relationships,
        "stability_scores": stability_scores,
        "drift_findings": drift_findings,
        "suggested_canonical_merges": [
            {
                "alias": finding["alias"],
                "preferred_concept_id": finding["first_concept_id"],
                "conflicting_concept_id": finding["second_concept_id"],
            }
            for finding in drift_findings
            if finding.get("finding") == "alias_collision"
        ],
        "status": "WARN" if drift_findings else "PASS",
        "notes": "Suggestion-only semantic physics view. No automatic rewriting is performed.",
    }
    write_json_atomic(paths.ontology / "semantic_physics.json", payload)
    append_jsonl(
        paths.ontology / "ontology_drift_telemetry.jsonl",
        {
            "event_type": "ontology_drift",
            "generated_utc": utc_now(),
            "concept_count": len(canonical_concepts),
            "drift_finding_count": len(drift_findings),
            "suggested_merge_count": len(payload["suggested_canonical_merges"]),
            "status": payload["status"],
        },
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the ecological semantic physics view.")
    parser.add_argument("--root", default=None)
    args = parser.parse_args()
    build_semantic_physics(root=args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
