from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

THIS_FILE = Path(__file__).resolve()
ROOT_CANDIDATE = THIS_FILE.parents[2]
if str(ROOT_CANDIDATE) not in sys.path:
    sys.path.insert(0, str(ROOT_CANDIDATE))

from ecology.ecology_core import get_paths, read_json, read_jsonl, safe_read_text, tokenize, utc_now, write_json_atomic


def _summary_files(paths) -> list[Path]:
    summaries_dir = paths.library / "memory" / "compressed" / "batch_001"
    return sorted(summaries_dir.glob("*.summary.md"))


def build_abstractions(*, root: str | Path | None = None) -> dict[str, Any]:
    paths = get_paths(root)
    contract = read_json(paths.library / "index" / "runtime_contract.json", default={}) or {}
    compression = read_json(
        paths.library / "memory" / "operator_decisions" / "compression_batch_001_approval_20260514T003317Z.json",
        default={},
    ) or {}
    semantic_confirmation = read_json(
        paths.library / "memory" / "operator_decisions" / "semantic_drift_operator_confirmation_20260514T003317Z.json",
        default={},
    ) or {}
    semantic_decisions = read_jsonl(
        paths.library / "memory" / "operator_decisions" / "semantic_drift_operator_decisions_20260513T234318Z.jsonl"
    )
    contradictions = read_jsonl(paths.library / "index" / "contradiction_registry.jsonl")
    summary_files = _summary_files(paths)

    repeated_failures: dict[str, int] = {}
    for summary_path in summary_files:
        text = safe_read_text(summary_path).lower()
        if "warning:" in text:
            warning_lines = [line.strip() for line in text.splitlines() if line.strip().startswith("- warning:") or "warning:" in line]
            for line in warning_lines:
                repeated_failures[line] = repeated_failures.get(line, 0) + 1

    abstractions: list[dict[str, Any]] = []
    abstractions.append(
        {
            "abstraction_id": "ABS_RUNTIME_SAFETY_INVARIANTS",
            "concept": "Runtime safety invariants outrank ecological recall breadth.",
            "derived_from": ["CONCEPT_RUNTIME_FAIL_CLOSED", "CONCEPT_DELETION_DISABLED"],
            "evidence": [
                str(paths.library / "index" / "runtime_contract.json"),
                str(paths.root / "CORE_RUNTIME_INDEX.md"),
            ],
            "confidence": 0.96 if contract.get("fail_closed") and not contract.get("deletion_enabled") else 0.72,
            "stability": 0.94,
            "contradictions": [],
            "operator_confirmed": True,
            "created_utc": utc_now(),
        }
    )
    abstractions.append(
        {
            "abstraction_id": "ABS_COMPRESSION_PRESERVES_SOURCE_MEMORY",
            "concept": "Compression is source-preserving and operator-gated rather than destructive.",
            "derived_from": ["CONCEPT_LIBRARY_SEMANTIC_GOVERNANCE"],
            "evidence": [str(paths.library / "memory" / "operator_decisions" / "compression_batch_001_approval_20260514T003317Z.json")]
            + [str(path) for path in summary_files[:3]],
            "confidence": 0.93 if compression.get("approval_status") == "APPROVED" else 0.64,
            "stability": 0.9,
            "contradictions": [],
            "operator_confirmed": bool(compression.get("approval_required")),
            "created_utc": utc_now(),
        }
    )
    abstractions.append(
        {
            "abstraction_id": "ABS_SEMANTIC_DRIFT_REQUIRES_OPERATOR_CLASSIFICATION",
            "concept": "Semantic drift is classified and stabilized through operator review, not autonomous rewriting.",
            "derived_from": ["CONCEPT_LIBRARY_SEMANTIC_GOVERNANCE", "CONCEPT_TAX_AGI"],
            "evidence": [
                str(paths.library / "memory" / "operator_decisions" / "semantic_drift_operator_confirmation_20260514T003317Z.json"),
                str(paths.library / "memory" / "operator_decisions" / "semantic_drift_operator_decisions_20260513T234318Z.jsonl"),
            ],
            "confidence": 0.91 if semantic_confirmation.get("auto_rewrite_allowed") is False else 0.55,
            "stability": 0.88,
            "contradictions": [],
            "operator_confirmed": True,
            "created_utc": utc_now(),
        }
    )

    recurring_warnings = [message for message, count in repeated_failures.items() if count >= 1]
    if recurring_warnings:
        abstractions.append(
            {
                "abstraction_id": "ABS_RECURRING_FAILURES_REQUIRE_EXPLICIT_UNCERTAINTY_TRACKING",
                "concept": "Recurring failure signatures should be consolidated into explicit uncertainty and contradiction traces.",
                "derived_from": ["ABS_SEMANTIC_DRIFT_REQUIRES_OPERATOR_CLASSIFICATION"],
                "evidence": [str(path) for path in summary_files if "warning:" in safe_read_text(path).lower()],
                "confidence": 0.76,
                "stability": 0.7,
                "contradictions": recurring_warnings[:5],
                "operator_confirmed": False,
                "created_utc": utc_now(),
            }
        )

    graph = {
        "schema_version": "18.4",
        "generated_utc": utc_now(),
        "abstraction_count": len(abstractions),
        "source_summary_count": len(summary_files),
        "operator_decision_count": len(semantic_decisions),
        "contradiction_count": len(contradictions),
        "abstractions": abstractions,
        "status": "WARN" if contradictions else "PASS",
    }
    write_json_atomic(paths.abstraction_graphs / "abstraction_graph.json", graph)

    nodes = []
    edges = []
    for abstraction in abstractions:
        nodes.append({"id": abstraction["abstraction_id"], "label": abstraction["concept"], "type": "abstraction"})
        for parent in abstraction["derived_from"]:
            edges.append({"parent": parent, "child": abstraction["abstraction_id"], "relationship": "derived_from"})
    inheritance = {
        "schema_version": "18.4",
        "generated_utc": utc_now(),
        "nodes": nodes,
        "edges": edges,
        "status": "PASS",
    }
    write_json_atomic(paths.abstraction_graphs / "concept_inheritance_graph.json", inheritance)
    return graph


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ecological abstraction graphs.")
    parser.add_argument("--root", default=None)
    args = parser.parse_args()
    build_abstractions(root=args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
