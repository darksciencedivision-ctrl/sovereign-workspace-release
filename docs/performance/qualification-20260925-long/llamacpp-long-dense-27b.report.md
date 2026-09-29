# LONG qualification report - llamacpp-long-dense-27b

- Measured: 2026-09-25T15:51:24.826Z -> 2026-09-25T16:02:04.978Z (UTC)
- Backend / model: llama.cpp / qwen3.8:27b (hybrid GPU/RAM serving planned by the supervisor)
- Hardware: NVIDIA GeForce RTX 5060 Ti (8151 MiB VRAM); Windows-11-10.0.26200-SP0
- Repetitions per rung: 1; SLOs: failure rate <= 0.2, LONG p95 <= 14400 s

## Envelope (reported, not enforced)

- Plan steps (objective only): **qualified**
- Largest map/reduce input meeting the SLOs: **~16384 tokens**
- Peak VRAM: 7330 MiB (baseline 1534); peak system RAM in use: 37013 of 65230 MiB (baseline 15976)

## End-to-end through the product

| Rung | Runs | Completed | Failure rate | p50 s | p95 s | shards max | chunks/h p50 | cold p50 s (n) | warm p50 s (n) |
|---|---|---|---|---|---|---|---|---|---|
| long_plan | 1 | 1 | 0.00 | 421.7 | 421.7 | 6 | 51.2 | 421.7 (1) | - (0) |
| long_input_16384 | 1 | 1 | 0.00 | 215.8 | 215.8 | 1 | 16.7 | - (0) | 215.8 (1) |

## Failures

- none

Cold = the model was not resident in llama.cpp when the job was submitted (its load time is inside the end-to-end time).

Rendered by `python -m sovereign_product.qualification report` from `llamacpp-long-dense-27b.results.json`.
