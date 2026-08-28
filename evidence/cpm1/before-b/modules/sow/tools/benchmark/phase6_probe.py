"""Phase 6 light roster probe (loop-scoped stand-in for Track E; NOT the full benchmark).

Times ONE small generation per offline-default model class (reasoning + coder) against the
detected local Ollama daemon and records latency + output length. This is minimal real
evidence that the offline roster's local backends run on this host; the FULL Track E/R10
campaign (multi-task suites, tool-call reliability, long-context, VRAM sizing across the
24B+ scale path) is a GPU-heavy effort deferred beyond the autonomous loop's compute budget.

Run: py -3.12 tools/benchmark/phase6_probe.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters import detect  # noqa: E402
from adapters.base.backend import OllamaBackend  # noqa: E402

PROMPTS = {
    "reasoning": ("qwen2.5:7b-instruct", "qwen2.5:14b-instruct", "llama3.1:8b"),
    "coding": ("qwen2.5-coder:7b", "qwen2.5-coder:32b", "deepseek-coder-v2:latest"),
}
PROMPT_TEXT = {
    "reasoning": "In one sentence, define idempotence in distributed systems.",
    "coding": "Write a one-line Python function is_even(n) that returns True if n is even.",
}


def main() -> int:
    if not detect.ollama_available():
        print(json.dumps({"skipped": "ollama daemon not detected"}))
        return 0
    models = detect.ollama_models()
    results = []
    for capability, candidates in PROMPTS.items():
        model = detect.pick_model(models, candidates)
        if not model:
            results.append({"capability": capability, "model": None, "note": "no candidate present"})
            continue
        backend = OllamaBackend(model)
        t0 = time.monotonic()
        out = backend.generate(PROMPT_TEXT[capability], max_tokens=96)
        dt = time.monotonic() - t0
        results.append({"capability": capability, "model": model, "latency_s": round(dt, 2),
                        "output_chars": len(out), "output_head": out.strip()[:120]})
        print(f"[probe] {capability}: {model} -> {dt:.2f}s, {len(out)} chars", flush=True)
    report = {"probe": "phase6-light@1.0", "generated": datetime.now(timezone.utc).isoformat(),
              "host_models_count": len(models), "opencode_detected": detect.opencode_available(),
              "results": results,
              "note": "light roster probe; full Track E/R10 benchmark deferred (GPU-heavy, out of loop budget)"}
    out_dir = ROOT / "docs" / "evidence"
    out_path = out_dir / "PHASE6_ROSTER_PROBE.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"[probe] wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
