"""One-shot capture of the REAL `claude -p --output-format json` response shape (OP-9).

Used ONCE to reconcile `extract_reported_model` against the CLI's actual JSON (the field
that carries the executing checkpoint id), which the mock-first suite could only guess at.
Minimal prompt (smoke-scale). Prints the top-level keys and the model-bearing fields, and
writes the sanitized envelope (with the free-text `result` and volatile ids elided) to
tools/live/claude_json_shape.captured.json for use as a test fixture.

NOT part of `pytest tests/` — it spawns the real CLI.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.frontier.claude_code import ClaudeCliBackend  # noqa: E402

HERE = Path(__file__).resolve().parent
PROMPT = "Reply with exactly the two characters: ok"


def main() -> int:
    cmd = ["claude", "-p", "--output-format", "json", PROMPT]
    # §2.2 defense-in-depth: run the CLI down the SAME scrubbed-env path the adapter uses, so no
    # credential/endpoint var (ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, …) can be transmitted or
    # redirect the call away from the subscription-OAuth path — identical to `ClaudeCliBackend`.
    env = ClaudeCliBackend().build_env()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=150, check=False, env=env)
    if proc.returncode != 0:
        print(json.dumps({"returncode": proc.returncode,
                          "stderr": (proc.stderr or "")[:500],
                          "stdout": (proc.stdout or "")[:500]}, indent=2))
        return 1
    payload = json.loads(proc.stdout)
    summary = {
        "top_level_keys": sorted(payload.keys()) if isinstance(payload, dict) else None,
        "type_of_model_field": type(payload.get("model")).__name__ if isinstance(payload, dict) else None,
        "model_field": payload.get("model") if isinstance(payload, dict) else None,
        "has_modelUsage": isinstance(payload, dict) and "modelUsage" in payload,
        "modelUsage_keys": (sorted(payload.get("modelUsage", {}).keys())
                            if isinstance(payload, dict) and isinstance(payload.get("modelUsage"), dict)
                            else None),
        "is_error": payload.get("is_error") if isinstance(payload, dict) else None,
    }
    print(json.dumps(summary, indent=2, default=str))

    # sanitized envelope for a fixture: drop free text + volatile ids, keep structure/model fields
    if isinstance(payload, dict):
        sanitized = {}
        for k, v in payload.items():
            if k in ("result", "session_id", "uuid"):
                sanitized[k] = f"<elided {k}>"
            elif k in ("duration_ms", "duration_api_ms", "total_cost_usd", "num_turns"):
                sanitized[k] = 0
            else:
                sanitized[k] = v
        (HERE / "claude_json_shape.captured.json").write_text(
            json.dumps(sanitized, indent=2, default=str), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
