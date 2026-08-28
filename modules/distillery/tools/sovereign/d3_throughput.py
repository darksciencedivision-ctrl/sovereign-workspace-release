#!/usr/bin/env python3
"""
Sovereign Distillery — Phase F.1: Generation Throughput Measurement

Replaces the ESTIMATED tier boundaries in the design plan (Part D) with measured
tokens/sec. Needs only Ollama — no PyTorch, no training stack. Can run today.

Measures, per model:
  * single-stream generation tok/s
  * BATCHED aggregate tok/s at increasing concurrency
  * time-to-first-token (load + prefill cost)

Batched throughput is the highest-leverage number in the plan. Corpus generation
is throughput-bound and latency-irrelevant, so if concurrency yields 3-4x
aggregate, the feasibility frontier moves up a whole tier.

Usage:
    python tools\\d3_throughput.py --models qwen3:8b qwen3:14b qwen3:32b
    python tools\\d3_throughput.py --models qwen3:8b --concurrency 1 2 4 8
    python tools\\d3_throughput.py --models qwen3:8b --max-tokens 512 --repeats 3

Writes: runs/generation_throughput.json
"""
import argparse, json, statistics, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HOST = "http://127.0.0.1:11434"

# Fixed benchmark set spanning the output shapes the Distillery will actually
# generate. Kept short so prefill does not dominate the measurement.
PROMPTS = [
    ("short_answer", "In one sentence, what is the difference between latency and throughput?"),
    ("long_form",    "Explain how gradient checkpointing reduces memory during training. Be thorough."),
    ("code",         "Write a Python function that merges two sorted lists in O(n). Include docstring and three tests."),
    ("structured",   "Return ONLY valid JSON: an object with keys 'name','version','deps' (array of 3 strings)."),
    ("reasoning",    "A train leaves at 14:05 travelling 80 km/h. Another leaves the same station at 14:35 at 120 km/h. When does the second catch the first? Show your steps."),
]


def _post(path, payload, timeout=1800):
    req = urllib.request.Request(HOST + path,
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def check_ollama():
    try:
        with urllib.request.urlopen(HOST + "/api/tags", timeout=10) as r:
            return [m["name"] for m in json.loads(r.read().decode()).get("models", [])]
    except Exception as e:
        print(f"  Cannot reach Ollama at {HOST}: {type(e).__name__}: {e}")
        print("  Start Ollama and retry.")
        sys.exit(1)


def generate(model, prompt, max_tokens, seed=41):
    """One generation. Returns Ollama's own nanosecond counters."""
    t0 = time.perf_counter()
    r = _post("/api/generate", {
        "model": model, "prompt": prompt, "stream": False,
        "options": {"num_predict": max_tokens, "temperature": 0.7,
                    "top_p": 0.95, "seed": seed},
    })
    wall = time.perf_counter() - t0
    ev, evd = r.get("eval_count", 0), r.get("eval_duration", 0)
    pv, pvd = r.get("prompt_eval_count", 0), r.get("prompt_eval_duration", 0)
    return {
        "wall_s": wall,
        "eval_tokens": ev,
        "eval_tok_per_s": (ev / (evd / 1e9)) if evd else None,   # pure generation
        "prompt_tokens": pv,
        "prefill_tok_per_s": (pv / (pvd / 1e9)) if pvd else None,
        "load_s": r.get("load_duration", 0) / 1e9,
        "ttft_s": (r.get("load_duration", 0) + pvd) / 1e9,
        "total_tok_per_s": (ev / wall) if wall else None,        # incl. overheads
    }


def warm(model):
    try:
        generate(model, "ok", 1)
    except Exception:
        pass


def bench_single(model, max_tokens, repeats):
    runs = []
    for label, p in PROMPTS:
        for i in range(repeats):
            try:
                m = generate(model, p, max_tokens, seed=41 + i)
                m["prompt_class"] = label
                runs.append(m)
            except Exception as e:
                runs.append({"prompt_class": label, "error": f"{type(e).__name__}: {e}"})
    ok = [r for r in runs if "error" not in r and r.get("eval_tok_per_s")]
    if not ok:
        return {"runs": runs, "error": "all single-stream runs failed"}
    ev = [r["eval_tok_per_s"] for r in ok]
    return {
        "runs": runs,
        "n": len(ok),
        "eval_tok_per_s_median": round(statistics.median(ev), 2),
        "eval_tok_per_s_mean": round(statistics.mean(ev), 2),
        "eval_tok_per_s_stdev": round(statistics.stdev(ev), 2) if len(ev) > 1 else 0.0,
        "ttft_s_median": round(statistics.median([r["ttft_s"] for r in ok]), 3),
        "load_s_max": round(max(r["load_s"] for r in ok), 2),
    }


def bench_concurrent(model, max_tokens, n):
    """Aggregate throughput at concurrency n. This is the number that matters."""
    prompts = [PROMPTS[i % len(PROMPTS)][1] for i in range(n)]
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n) as ex:
        res = list(ex.map(lambda pr: generate(model, pr[1], max_tokens, seed=41 + pr[0]),
                          list(enumerate(prompts))))
    wall = time.perf_counter() - t0
    toks = sum(r.get("eval_tokens", 0) for r in res)
    return {
        "concurrency": n,
        "wall_s": round(wall, 2),
        "total_eval_tokens": toks,
        "aggregate_tok_per_s": round(toks / wall, 2) if wall else None,
        "per_stream_tok_per_s": round(toks / wall / n, 2) if wall and n else None,
    }


def project(tps, corpus_tokens):
    if not tps:
        return None
    d = corpus_tokens / tps / 86400
    if   d <= 4:  t = "T1-VIABLE"
    elif d <= 21: t = "T2-COSTLY"
    elif d <= 90: t = "T3-DEFERRED"
    else:         t = "T4-INFEASIBLE"
    return {"days": round(d, 2), "tier": t}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--concurrency", nargs="+", type=int, default=[1, 2, 4, 8])
    ap.add_argument("--max-tokens", type=int, default=384)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--corpus-tokens", type=int, default=2_000_000)
    ap.add_argument("--no-concurrent", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    available = check_ollama()
    print("=" * 82)
    print("SOVEREIGN DISTILLERY — F.1 GENERATION THROUGHPUT")
    print("=" * 82)
    print(f"  Ollama reachable. {len(available)} models served.")
    print(f"  Corpus projection basis: {a.corpus_tokens:,} tokens per teacher")
    print("-" * 82)

    out = {
        "schema": "sovereign-distillery/generation_throughput/v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "config": vars(a), "models": {},
    }

    for m in a.models:
        if m not in available:
            print(f"  [skip] {m} not served by Ollama")
            out["models"][m] = {"error": "not available"}
            continue
        print(f"\n  {m}")
        print("  " + "-" * 78)
        warm(m)
        single = bench_single(m, a.max_tokens, a.repeats)
        rec = {"single_stream": single, "concurrent": []}
        if "error" in single:
            print(f"    ERROR: {single['error']}")
            out["models"][m] = rec
            continue
        base = single["eval_tok_per_s_median"]
        pj = project(base, a.corpus_tokens)
        print(f"    single-stream   {base:>8.1f} tok/s  "
              f"(sd {single['eval_tok_per_s_stdev']:.1f}, ttft {single['ttft_s_median']:.2f}s, "
              f"load {single['load_s_max']:.1f}s)")
        print(f"    projected       {pj['days']:>8.2f} days for {a.corpus_tokens:,} tokens  -> {pj['tier']}")
        rec["single_projection"] = pj

        if not a.no_concurrent:
            best = base
            for n in a.concurrency:
                if n == 1:
                    continue
                try:
                    c = bench_concurrent(m, a.max_tokens, n)
                except Exception as e:
                    print(f"    concurrency {n:<2}    FAILED: {type(e).__name__}: {e}")
                    continue
                rec["concurrent"].append(c)
                agg = c["aggregate_tok_per_s"] or 0
                best = max(best, agg)
                print(f"    concurrency {n:<2}  {agg:>8.1f} tok/s aggregate  "
                      f"({agg/base:.2f}x single)")
            bp = project(best, a.corpus_tokens)
            rec["best_tok_per_s"] = best
            rec["best_projection"] = bp
            if best > base:
                print(f"    BEST            {best:>8.1f} tok/s -> {bp['days']:.2f} days -> {bp['tier']}"
                      + ("   *** TIER IMPROVED ***" if bp["tier"] != pj["tier"] else ""))
        out["models"][m] = rec

    dest = Path(a.out) if a.out else Path(__file__).resolve().parent.parent / "runs" / "generation_throughput.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("\n" + "-" * 82)
    print(f"  Written: {dest}")
    print("  Feed these numbers back into d2_registry.py to reissue the tiered queue.")
    print("=" * 82)


if __name__ == "__main__":
    main()
