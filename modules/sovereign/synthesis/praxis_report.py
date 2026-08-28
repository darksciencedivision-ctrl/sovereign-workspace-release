from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bullets(items: list[str], empty_text: str) -> str:
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    if not cleaned:
        return f"- {empty_text}"
    return "\n".join(f"- {item}" for item in cleaned[:5])


def build_praxis_report(canonical_answer: dict[str, Any], governance: dict[str, Any] | None = None) -> str:
    governance = governance or {}
    session_id = str(canonical_answer.get("session_id", "")).strip() or "unknown-session"
    topic = str(canonical_answer.get("topic", "")).strip() or "Unknown topic"
    metrics = canonical_answer.get("metrics", {}) if isinstance(canonical_answer.get("metrics"), dict) else {}
    convergence = metrics.get("structural_completeness", "?")
    confidence = metrics.get("response_elaboration", "?")
    claim = str(canonical_answer.get("claim", "")).strip() or "No claim available."
    final_synthesis = str(canonical_answer.get("final_synthesis", "")).strip() or claim
    evidence = canonical_answer.get("evidence", [])
    uncertainties = canonical_answer.get("uncertainties", [])
    mode = str(governance.get("autonomy_mode", "OBSERVE")).strip() or "OBSERVE"

    return "\n".join(
        [
            "REPORT_CHANNEL: praxis_report",
            "PRAXIS_MEMORY_ALLOWED: false",
            f"GENERATED_AT: {utc_now_iso()}",
            "",
            "# Praxis Report",
            "",
            f"Session: {session_id}",
            f"Topic: {topic}",
            f"Autonomy Mode: {mode}",
            f"Convergence: {convergence}",
            f"Confidence: {confidence}",
            "",
            "## Canonical Summary",
            final_synthesis,
            "",
            "## Claim",
            claim,
            "",
            "## Evidence",
            _bullets(list(evidence) if isinstance(evidence, list) else [], "No evidence bullets were preserved."),
            "",
            "## Remaining Uncertainty",
            _bullets(list(uncertainties) if isinstance(uncertainties, list) else [], "No uncertainties were preserved."),
            "",
            "## Memory Policy",
            "This report is non-memory by default. Promote manually only through an explicit, logged constitutional process.",
            "",
        ]
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a compact Praxis report artifact.")
    parser.add_argument("--input", required=True, help="Path to praxis_answer.json")
    parser.add_argument("--output", required=True, help="Path to praxis_report.md")
    parser.add_argument("--mode", default="OBSERVE", help="Autonomy mode label")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    canonical_answer = json.loads(input_path.read_text(encoding="utf-8"))
    content = build_praxis_report(canonical_answer, {"autonomy_mode": args.mode})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
