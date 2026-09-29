# LONG-route qualification - 2026-09-25

End-to-end measurements of the two sharded-inference profiles, taken **through the running
SOVEREIGN product** (its own `/v1` API) with the SW-27 harness (`qualification run`). The machine:
NVIDIA GeForce RTX 5060 Ti (8 GB VRAM), 64 GB RAM, Windows 11, llama.cpp b11160. Models were served
by the llama.cpp supervisor with the memory planner's GPU/RAM split, against an isolated scratch
state root. The operator's real state home was not touched, and nothing was installed: LONG
envelopes are reported, never enforced.

| File | What it is |
|---|---|
| `llamacpp-long-dense-27b.report.md` / `.results.json` | qwen3.8:27b, 13 of 65 layers on the GPU, 131072 context |
| `llamacpp-long-moe-30b-a3b.report.md` / `.results.json` | qwen3:30b-a3b (Qwen3-30B-A3B-Thinking-2507), experts of 42 of 48 layers in RAM, 32768 context, thinking on with 6144 reasoning tokens |

The reports are rendered mechanically from the results files by
`python -m sovereign_product.qualification report`.

## Results

Every rung completed, with no failed jobs. There was one repetition per rung.

| Profile | Rung | End-to-end | Shards | Chunks/h | Load |
|---|---|---|---|---|---|
| dense 27B | plan steps | 422 s | 6 | 51.2 | cold (model load 48 s inside) |
| dense 27B | map/reduce ~16k tokens | 216 s | 1 | - | warm |
| MoE 30B-A3B | plan steps | 727 s | 8 | 39.6 | cold (swap from the 27B, load 55 s inside) |
| MoE 30B-A3B | map/reduce ~32k tokens | 1495 s | 4 | 9.6 | warm |
| MoE 30B-A3B | map/reduce ~65k tokens | 2192 s | 6 | 9.9 | warm |

## Findings

1. **Both LONG modes qualify on both models on this machine.**
   - Plan steps are qualified for both models.
   - Map/reduce is qualified up to the largest rung measured: ~16k tokens on the 27B, and ~65k
     tokens on the MoE. The 65k input is twice the MoE's 32k window, so it was split into 5 map
     chunks plus a reduce.
2. **The MoE's map/reduce speed depends on the input.**
   - On these synthetic, highly repetitive notes, each map took about 5-6 minutes, and 2 of the 9
     map chunks needed a fresh retry.
   - On real prose earlier the same day (145 KB of Distillery DESIGN + VALIDATION, see the PR), the same
     model mapped 3 chunks of ~19k tokens and reduced them in 601 s, with every call accepted on the
     first try.
   - The thinking model reasons far longer over near-identical records. Treat these rungs as a
     conservative bound.
3. **Model loads are cheap compared with the work.** Loads took 48 s (27B) and 55 s (MoE).
   `models_max=1` means switching models costs one load. See the open policy question in the PR.
4. **Memory.**
   - The 27B profile peaked about 5.8 GB of VRAM and about 21 GB of system RAM above its baseline;
     the planner estimated 6.1 GiB and 18.3 GiB.
   - The MoE profile's peaks are **not meaningful here**. The resource sampler is system-wide, and
     its baseline was taken while the 27B was still resident, before the swap. The MoE's own peak
     was measured separately on 2026-09-25 at 6.87 GB of VRAM; the planner estimated 6.01 GiB.

## Correction applied to the results

The harness decides cold vs warm from `/v1/self-state`'s `loaded_models`. That list omitted the
router's `aliases`, so it named models only by router id (e.g. `qwen3-30b-a3b-hybrid-32k`), and
every run was recorded `cold=True`.

This bug was found by this qualification and fixed in `introspection.py` in the same commit, with a
failure-injection test.

The `cold` flags in both results files were corrected from the router's own log. It shows exactly
two model loads: the first job of each profile. Each corrected run keeps the harness's original
value as `cold_recorded`, carries `cold_source`, and the document lists the correction under
`corrections`. The reports were rendered after the correction.
