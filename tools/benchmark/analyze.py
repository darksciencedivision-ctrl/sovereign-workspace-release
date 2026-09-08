#!/usr/bin/env python
"""SWS-BENCH-01 analysis - paired differences, uncertainty, and the frozen decision rule.

The thresholds applied here are the ones in PROTOCOL.md, which was frozen before any run. They
are read as constants, not as arguments, so an analysis cannot quietly move them.

Reports the ONE preselected primary outcome (B_full minus A_single on task success) separately
from everything exploratory. An interval spanning zero is reported as INCONCLUSIVE, which is a
permitted result; uncertainty is never described as equivalence.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

# --- frozen in PROTOCOL.md before execution. Do not edit to fit a result. ---
BENEFIT_THRESHOLD_PTS = 10.0     # B must beat A by this much to be retained as default
REGRESSION_TOLERANCE_PTS = 5.0   # an ablation within this of B has not demonstrated its stage
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20260908
PRIMARY = ("B_full", "A_single")


def load(path: Path):
    env, runs = None, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("record_kind") == "environment":
            env = rec
        elif rec.get("record_kind") == "run":
            runs.append(rec)
    return env, runs


def task_rate(runs, condition):
    """Per-task success rate for one condition: mean of `correct` over that task's runs."""
    by_task = defaultdict(list)
    for r in runs:
        if r["condition"] != condition:
            continue
        # An errored execution is a FAILED task, not a missing one. Dropping it would silently
        # reward a condition for crashing.
        ok = bool(r["grade"]["correct"]) if r.get("grade") else False
        by_task[r["task_id"]].append(1.0 if ok else 0.0)
    return {t: statistics.mean(v) for t, v in by_task.items()}


def paired_diff(runs, a, b):
    """(mean difference in percentage points, per-task differences, shared task ids)."""
    ra, rb = task_rate(runs, a), task_rate(runs, b)
    shared = sorted(set(ra) & set(rb))
    diffs = [(ra[t] - rb[t]) * 100.0 for t in shared]
    return (statistics.mean(diffs) if diffs else 0.0), diffs, shared


def bootstrap_ci(diffs, resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED):
    """95% bootstrap CI of the mean paired difference, resampling TASKS."""
    if len(diffs) < 2:
        return (None, None)
    rng = random.Random(seed)
    n = len(diffs)
    means = []
    for _ in range(resamples):
        means.append(statistics.mean(rng.choice(diffs) for _ in range(n)))
    means.sort()
    lo = means[int(0.025 * resamples)]
    hi = means[min(resamples - 1, int(0.975 * resamples))]
    return (round(lo, 2), round(hi, 2))


def summarise(runs, condition):
    sel = [r for r in runs if r["condition"] == condition]
    if not sel:
        return None
    graded = [r for r in sel if r.get("grade")]
    errored = [r for r in sel if not r.get("grade")]
    times = [r["elapsed_s"] for r in sel if r.get("elapsed_s") is not None]
    vram = [r["peak_vram_mib"] for r in sel if r.get("peak_vram_mib") is not None]
    calls = [r["model_calls"] for r in sel if r.get("model_calls") is not None]
    return {
        "executions": len(sel),
        "errored": len(errored),
        "success_rate_pct": round(
            100.0 * sum(1 for r in graded if r["grade"]["correct"]) / len(sel), 1),
        "abstention_rate_pct": round(
            100.0 * sum(1 for r in graded if r["grade"]["abstained"]) / len(sel), 1)
        if graded else None,
        "unsupported_claims_total": sum(r["grade"]["unsupported_claims"] for r in graded),
        "citation_errors_total": sum(r["grade"]["citation_errors"] for r in graded),
        "median_seconds": round(statistics.median(times), 1) if times else None,
        "mean_seconds": round(statistics.mean(times), 1) if times else None,
        "median_model_calls": round(statistics.median(calls), 1) if calls else None,
        "peak_vram_mib_max": max(vram) if vram else None,
    }


def by_category(runs, condition):
    out = defaultdict(lambda: [0, 0])
    for r in runs:
        if r["condition"] != condition:
            continue
        out[r["category"]][1] += 1
        if r.get("grade") and r["grade"]["correct"]:
            out[r["category"]][0] += 1
    return {k: round(100.0 * v[0] / v[1], 1) for k, v in sorted(out.items())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", default=str(HERE / "results" / "runs.jsonl"))
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    env, runs = load(Path(args.results))
    if not runs:
        print("no run records found")
        return 1

    conditions = sorted({r["condition"] for r in runs})
    partial = any(r.get("partial") for r in runs) or (env or {}).get("partial")

    print("=" * 78)
    print("SWS-BENCH-01 analysis")
    print("=" * 78)
    if env:
        print(f"candidate       {env.get('candidate_sha')}")
        print(f"dataset_sha256  {env.get('dataset_sha256')}")
        print(f"protocol_sha256 {env.get('protocol_sha256')}")
        print(f"harness_sha256  {env.get('harness_sha256')}")
        print(f"gpu             {(env.get('hardware') or {}).get('gpu')}")
    tasks = sorted({r["task_id"] for r in runs})
    per_cell = {c: len([r for r in runs if r["condition"] == c]) for c in conditions}
    print(f"tasks           {len(tasks)}")
    print(f"executions      {len(runs)}  {per_cell}")
    if partial:
        print()
        print("  *** PRELIMINARY *** This run set does not satisfy SWS-BENCH-01 in full.")
        print("      Its coverage is stated above and in the report; the decision below is")
        print("      correspondingly provisional and MUST NOT be reported as the protocol's.")

    print()
    print("-" * 78)
    print("Per-condition summary (all exploratory except the primary outcome below)")
    print("-" * 78)
    rows = {}
    for c in conditions:
        s = summarise(runs, c)
        rows[c] = s
        print(f"\n{c}")
        for k, v in s.items():
            print(f"    {k:<28} {v}")
        print(f"    {'by category (%)':<28} {by_category(runs, c)}")

    print()
    print("=" * 78)
    print("PRIMARY OUTCOME (preselected, single): B_full minus A_single, task success")
    print("=" * 78)
    decision = "NOT EVALUABLE"
    primary = None
    if PRIMARY[0] in conditions and PRIMARY[1] in conditions:
        mean, diffs, shared = paired_diff(runs, PRIMARY[0], PRIMARY[1])
        lo, hi = bootstrap_ci(diffs)
        primary = {"mean_pts": round(mean, 2), "ci95": [lo, hi], "paired_tasks": len(shared)}
        print(f"  paired tasks            {len(shared)}")
        print(f"  mean difference         {mean:+.1f} percentage points")
        print(f"  95% bootstrap CI        [{lo}, {hi}]  ({BOOTSTRAP_RESAMPLES} resamples, "
              f"seed {BOOTSTRAP_SEED})")
        print(f"  benefit threshold       +{BENEFIT_THRESHOLD_PTS} pts (frozen before the run)")

        excludes_zero = lo is not None and (lo > 0 or hi < 0)
        if mean >= BENEFIT_THRESHOLD_PTS and excludes_zero:
            decision = "RETAIN the full orchestration as default"
        elif mean <= -BENEFIT_THRESHOLD_PTS and excludes_zero:
            decision = "SIMPLIFY: make the single-model workflow the default"
        else:
            decision = "INCONCLUSIVE: no default change"
        print(f"\n  DECISION: {decision}")
        if not excludes_zero:
            print("  The interval spans zero. That is uncertainty, not equivalence: this run")
            print("  does not show the orchestration helping, and does not show it not helping.")
    else:
        print("  both conditions were not run; the primary outcome cannot be computed")

    print()
    print("-" * 78)
    print("EXPLORATORY: ablations against B_full")
    print("-" * 78)
    ablations = {}
    for ab in ("C1_no_critic", "C2_no_verifier"):
        if ab not in conditions or "B_full" not in conditions:
            print(f"  {ab:<16} not run")
            continue
        mean, diffs, shared = paired_diff(runs, ab, "B_full")
        lo, hi = bootstrap_ci(diffs)
        within = abs(mean) <= REGRESSION_TOLERANCE_PTS
        verdict = ("stage has NOT demonstrated benefit" if within
                   else ("stage helps" if mean < 0 else "stage HURTS"))
        ablations[ab] = {"mean_pts": round(mean, 2), "ci95": [lo, hi], "verdict": verdict}
        print(f"  {ab:<16} {mean:+.1f} pts vs B_full   CI [{lo}, {hi}]   -> {verdict}")
        print(f"  {'':<16} (tolerance +/-{REGRESSION_TOLERANCE_PTS} pts, frozen before the run)")

    print()
    print("-" * 78)
    print("Cost")
    print("-" * 78)
    for c in conditions:
        s = rows[c]
        print(f"  {c:<16} median {s['median_seconds']}s   "
              f"median calls {s['median_model_calls']}   "
              f"peak VRAM {s['peak_vram_mib_max']} MiB")
    print("\n  VRAM is a 500 ms sample of whole-device usage, not an integral and not this")
    print("  process's share; a peak between samples is missed.")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps({
            "protocol": "SWS-BENCH-01",
            "preliminary": bool(partial),
            "environment": env,
            "conditions": rows,
            "by_category": {c: by_category(runs, c) for c in conditions},
            "primary_outcome": primary,
            "primary_decision": decision,
            "ablations": ablations,
            "thresholds": {
                "benefit_pts": BENEFIT_THRESHOLD_PTS,
                "regression_tolerance_pts": REGRESSION_TOLERANCE_PTS,
            },
        }, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
