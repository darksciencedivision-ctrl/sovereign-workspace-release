# LONG qualification report - llamacpp-long-moe-30b-a3b

- Measured: 2026-09-28T02:11:29.441Z -> 2026-09-28T03:21:17.814Z (UTC)
- Backend / model: llama.cpp / qwen3:30b-a3b (hybrid GPU/RAM serving planned by the supervisor)
- Hardware: NVIDIA GeForce RTX 5060 Ti (8151 MiB VRAM); Windows-11-10.0.26200-SP0
- Repetitions per rung: 1; SLOs: failure rate <= 0.2, LONG p95 <= 14400 s

## Envelope (reported, not enforced)

- Plan steps (objective only): **qualified**
- Largest map/reduce input meeting the SLOs: **~65536 tokens**
- Peak VRAM: 6609 MiB (baseline 6601); peak system RAM in use: 39473 of 65230 MiB (baseline 37751)

## End-to-end through the product

| Rung | Runs | Completed | Failure rate | p50 s | p95 s | shards max | chunks/h p50 | cold p50 s (n) | warm p50 s (n) |
|---|---|---|---|---|---|---|---|---|---|
| long_plan | 1 | 1 | 0.00 | 511.8 | 511.8 | 6 | 42.2 | - (0) | 511.8 (1) |
| long_input_32768 | 1 | 1 | 0.00 | 1058.7 | 1058.7 | 4 | 13.6 | - (0) | 1058.7 (1) |
| long_input_65536 | 1 | 1 | 0.00 | 2613.8 | 2613.8 | 8 | 11.0 | - (0) | 2613.8 (1) |

## Failures

- none

Cold = the model was not resident in llama.cpp when the job was submitted (its load time is inside the end-to-end time).

Rendered by `python -m sovereign_product.qualification report` from `llamacpp-long-moe-30b-a3b.results.json`.
