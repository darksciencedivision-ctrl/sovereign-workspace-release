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
    return "\n".join(f"- {item}" for item in cleaned[:6])


def build_sovereign_voice(canonical_answer: dict[str, Any], governance: dict[str, Any] | None = None) -> str:
    governance = governance or {}
    session_id = str(canonical_answer.get("session_id", "")).strip() or "unknown-session"
    topic = str(canonical_answer.get("topic", "")).strip() or "Unknown topic"
    claim = str(canonical_answer.get("claim", "")).strip() or "No canonical claim was available."
    final_synthesis = str(canonical_answer.get("final_synthesis", "")).strip() or claim
    uncertainties = canonical_answer.get("uncertainties", [])
    counters = canonical_answer.get("counterarguments", [])
    mode = str(governance.get("autonomy_mode", "OBSERVE")).strip() or "OBSERVE"

    return "\n".join(
        [
            "NON_CANONICAL_CHANNEL: sovereign_voice",
            "PRAXIS_MEMORY_ALLOWED: false",
            "CONTROL_PLANE_ALLOWED: false",
            f"GENERATED_AT: {utc_now_iso()}",
            "",
            "# Sovereign Voice",
            "",
            f"Session: {session_id}",
            f"Autonomy Mode: {mode}",
            f"Topic: {topic}",
            "",
            "This channel is interpretive and non-canonical. It must never be committed to Praxis memory or treated as state.",
            "",
            "## Reading",
            final_synthesis,
            "",
            "## What The Canonical Answer Suggests",
            claim,
            "",
            "## Tension Signals",
            _bullets(list(counters) if isinstance(counters, list) else [], "No counterarguments were preserved in the canonical answer."),
            "",
            "## Open Questions",
            _bullets(list(uncertainties) if isinstance(uncertainties, list) else [], "No open questions were preserved in the canonical answer."),
            "",
            "## Boundary Condition",
            "Treat this voice as optional interpretation layered on top of the canonical Praxis Answer.",
            "",
        ]
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a non-canonical Sovereign Voice markdown artifact.")
    parser.add_argument("--input", required=True, help="Path to praxis_answer.json")
    parser.add_argument("--output", required=True, help="Path to sovereign_voice.md")
    parser.add_argument("--mode", default="OBSERVE", help="Autonomy mode label")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    canonical_answer = json.loads(input_path.read_text(encoding="utf-8"))
    content = build_sovereign_voice(canonical_answer, {"autonomy_mode": args.mode})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
