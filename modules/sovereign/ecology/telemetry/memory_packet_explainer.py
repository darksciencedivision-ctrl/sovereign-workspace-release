from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

THIS_FILE = Path(__file__).resolve()
ROOT_CANDIDATE = THIS_FILE.parents[2]
if str(ROOT_CANDIDATE) not in sys.path:
    sys.path.insert(0, str(ROOT_CANDIDATE))

from ecology.ecology_core import get_paths, read_json, utc_now, write_text_atomic


def generate_memory_packet_report(packet: dict[str, Any], *, root: str | Path | None = None) -> dict[str, Any]:
    paths = get_paths(root)
    query_id = str(packet.get("query_id", "memory_packet"))
    report_path = paths.telemetry / "memory_packet_reports" / f"memory_packet_report_{query_id}.md"
    selected_items = packet.get("selected_items") or packet.get("retrieved_items") or []
    suppressed_items = packet.get("suppressed_results", [])
    contradictions = packet.get("contradictions", [])
    budget = packet.get("attention_budget", {})
    arbitration = packet.get("arbitration", {})

    lines = [
        "# Ecological Memory Packet Report",
        f"**Generated UTC:** {utc_now()}",
        f"**Query ID:** {query_id}",
        f"**Topic:** {packet.get('topic', packet.get('query', ''))}",
        "",
        "## Retrieval Strategy",
        "",
        f"- {packet.get('retrieval_strategy', 'not_recorded')}",
        f"- {packet.get('retrieval_reasoning', 'no reasoning recorded')}",
        "",
        "## Selected Memory",
        "",
    ]
    if selected_items:
        for item in selected_items:
            lines.extend(
                [
                    f"### Rank {item.get('rank', '?')} — {item.get('item_id', 'unknown_item')}",
                    f"- Path: `{item.get('path', '')}`",
                    f"- Confidence: `{item.get('confidence', item.get('final_confidence', item.get('score', 0.0)))}`",
                    f"- Why selected: {item.get('why_selected', '; '.join(item.get('selection_reasons', [])) or 'not recorded')}",
                    f"- Ontology relationship: `{', '.join(item.get('ontology_relationship', item.get('ontology_terms', [])) or [])}`",
                    f"- Contradiction flags: `{', '.join(item.get('contradiction_flags', [])) or 'none'}`",
                    f"- Memory cost estimate: `{item.get('memory_cost_estimate', {})}`",
                    "",
                ]
            )
    else:
        lines.append("- No selected items recorded.")
        lines.append("")

    lines.extend(["## Suppressed Memory", ""])
    if suppressed_items:
        for item in suppressed_items:
            lines.append(
                f"- `{item.get('item_id', 'unknown_item')}` suppressed because `{item.get('reason', 'unspecified')}`"
            )
    else:
        lines.append("- No suppressed items recorded.")

    lines.extend(
        [
            "",
            "## Contradictions",
            "",
            f"- Count: `{len(contradictions)}`",
            f"- Values: `{', '.join(str(item) for item in contradictions) if contradictions else 'none'}`",
            "",
            "## Budget Allocation",
            "",
            f"- Selected count: `{budget.get('selected_count', 0)}`",
            f"- Suppressed count: `{budget.get('suppressed_count', 0)}`",
            f"- Token budget used: `{budget.get('token_budget_used', 0)}`",
            f"- Memory budget used: `{budget.get('memory_budget_used', 0)}`",
            f"- Contradiction density: `{budget.get('contradiction_density', 0)}`",
            f"- Low-confidence ratio: `{budget.get('low_confidence_ratio', 0)}`",
            "",
            "## Arbitration",
            "",
            f"- Report path: `{arbitration.get('report_path', packet.get('arbitration_report_path', 'not_recorded'))}`",
            f"- Suppressed by arbitration: `{arbitration.get('suppressed_count', len(arbitration.get('suppressed_results', [])))}`",
            "",
            "## Explainability Status",
            "",
            "- Every selection and suppression above is directly inspectable.",
            "- Contradictions remain surfaced rather than silently resolved.",
            "- Budget limits are described explicitly rather than silently truncating memory.",
        ]
    )
    write_text_atomic(report_path, "\n".join(lines))
    return {"report_path": str(report_path), "generated_utc": utc_now()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a human-readable ecological memory packet report.")
    parser.add_argument("--packet", required=True)
    parser.add_argument("--root", default=None)
    args = parser.parse_args()

    packet = read_json(Path(args.packet), default={}) or {}
    if not isinstance(packet, dict):
        raise SystemExit("packet JSON must contain an object")
    generate_memory_packet_report(packet, root=args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
