# LONG qualification report - llamacpp-long-moe-30b-a3b

- Measured: 2026-09-25T16:02:06.673Z -> 2026-09-25T17:15:45.569Z (UTC)
- Backend / model: llama.cpp / qwen3:30b-a3b (hybrid GPU/RAM serving planned by the supervisor)
- Hardware: NVIDIA GeForce RTX 5060 Ti (8151 MiB VRAM); Windows-11-10.0.26200-SP0
- Repetitions per rung: 1; SLOs: failure rate <= 0.2, LONG p95 <= 14400 s

## Envelope (reported, not enforced)

- Plan steps (objective only): **qualified**
- Largest map/reduce input meeting the SLOs: **~65536 tokens**
- Peak VRAM: 7088 MiB (baseline 7076); peak system RAM in use: 35776 of 65230 MiB (baseline 35776)

## End-to-end through the product

| Rung | Runs | Completed | Failure rate | p50 s | p95 s | shards max | chunks/h p50 | cold p50 s (n) | warm p50 s (n) |
|---|---|---|---|---|---|---|---|---|---|
| long_plan | 1 | 1 | 0.00 | 727.4 | 727.4 | 8 | 39.6 | 727.4 (1) | - (0) |
| long_input_32768 | 1 | 1 | 0.00 | 1495.3 | 1495.3 | 4 | 9.6 | - (0) | 1495.3 (1) |
| long_input_65536 | 1 | 1 | 0.00 | 2192.2 | 2192.2 | 6 | 9.9 | - (0) | 2192.2 (1) |

## Failures

- none

Cold = the model was not resident in llama.cpp when the job was submitted (its load time is inside the end-to-end time).

Rendered by `python -m sovereign_product.qualification report` from `llamacpp-long-moe-30b-a3b.results.json`.
