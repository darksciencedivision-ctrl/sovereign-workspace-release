# LONG-route qualification r2 - 2026-09-27

MoE profile `llamacpp-long-moe-30b-a3b`, re-measured through the running product on `feature/sharded-inference` after the closeout fixes. Isolated scratch state. The operator's real state home was not touched. r1 in `docs/performance/qualification-20260925-long/` was not edited.

The report is rendered mechanically from the results file by `python -m sovereign_product.qualification report`.

## What changed since r1

- `9a8ecc6` aggregation: reduce adds disjoint per-part counts and names a missing part.
- `9e0caf2` splitting: a cut-off map is split, not retried unchanged.
- `3e0a2de` isolation: maps do not share a ledger.
- D1 (`ed82343`): the per-part appendix is one checkpoint-summary line per completed map, or omitted when the answer already names every map.

## Files

| File | What it is |
|---|---|
| `llamacpp-long-moe-30b-a3b.report.md` / `.results.json` | qwen3:30b-a3b (Qwen3-30B-A3B-Thinking-2507), experts of 42 of 48 layers in RAM, 32768 context, thinking on with 6144 reasoning tokens |

## Results

Every rung completed. One repetition. No failures. The MoE was already resident (the prose check on the same stack had loaded it), so every rung is warm. r1's plan rung was cold.

| Rung | End-to-end | Shards | Chunks/h | Load |
|---|---|---|---|---|
| plan steps | 511.8 s | 6 | 42.2 | warm |
| map/reduce ~32k tokens | 1058.7 s | 4 | 13.6 | warm |
| map/reduce ~65k tokens | 2613.8 s | 8 | 11.0 | warm |

## 65k count

Job `job_8cbed56a19214a3aad6272c9a401cef4`. The product answer's count of notes reporting 16 warnings is 115. The sum of the per-map checkpoint summaries is 31+25+27+12+13+1+6 = 115. Truth is 124. The gap is the model's per-part counting, not cross-map leakage: every map ledger was empty. One split (`map-0004` into `map-0004a` / `map-0004b` / `map-0004c`), 9 model calls, 0 failures. The answer's appendix is capped (one summary line per completed map).

## Memory

Peak VRAM 6609 MiB, baseline 6601 MiB. The baseline was taken with the MoE already resident, so the delta is not a cold-load measurement. Peak system RAM in use 39473 of 65230 MiB, baseline 37751. The sampler is system-wide.
