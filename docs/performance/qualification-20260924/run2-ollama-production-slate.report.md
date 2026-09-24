# Qualification report - ollama-production-slate

- Measured: 2026-09-24T14:56:38.171Z -> 2026-09-24T15:06:18.519Z (UTC)
- Backend / primary model: ollama / qwen3:14b
- Hardware: NVIDIA GeForce RTX 5060 Ti (8151 MiB VRAM); Windows-11-10.0.26200-SP0
- Product: 3.1.2 (workers 1); repetitions per step: 3
- SLOs: failure rate <= 0.2, QUICK p95 <= 300 s, DEEP p95 <= 3600 s, cancel p95 <= 30 s

## Envelope (enforced)

- Qualified context window (the num_ctx measured): **40960 tokens**
- Largest prompt meeting the SLOs through the product: **~8192 tokens**
- Qualified concurrent jobs: **2**
- Qualified workflows: QUICK=yes, DEEP=yes, cancellation=yes
- Largest task observed (input + output, the product's job metric): 8307 tokens (a configured MAX_OUTPUT_TOKENS above this is reported UNQUALIFIED)
- Peak VRAM: 7661 MiB (baseline 7495); peak system RAM in use: 40069 of 65230 MiB

## End-to-end latency through the product

| Scenario | Runs | Completed | Failure rate | p50 s | p95 s | max s | task tokens/s p50 | max task tokens |
|---|---|---|---|---|---|---|---|---|
| context_2048 | 3 | 3 | 0.00 | 8.8 | 8.9 | 8.9 | 251.11 | 2215 |
| context_8192 | 3 | 3 | 0.00 | 22.3 | 22.7 | 22.7 | 372.29 | 8307 |
| context_16384 | 3 | 0 | 1.00 | - | - | - | - | - |
| context_32768 | 0 | 0 | - | - | - | - | - | - |
| concurrency_1 | 3 | 3 | 0.00 | 15.5 | 16.6 | 16.6 | 22.07 | 345 |
| concurrency_2 | 2 | 2 | 0.00 | 11.9 | 21.8 | 21.8 | 14.13 | 320 |
| quick_cold | 1 | 1 | 0.00 | 18.2 | 18.2 | 18.2 | 16.51 | 301 |
| quick_warm | 3 | 3 | 0.00 | 10.4 | 11.9 | 11.9 | 29.98 | 314 |
| deep | 1 | 1 | 0.00 | 360.1 | 360.1 | 360.1 | 23.06 | 8306 |

## Cancellation

- 1 of 1 mid-flight cancellations reached `cancelled`; cancel-to-terminal p50 1.0 s, p95 1.0 s

## Failures

- context (16384): failed after 0.6 s - ModelCapabilityError: input bound (53261) plus safety allowance (512) leaves no generation capacity inside effective context 40960 for model 'qwen3:14b'
- context (16384): failed after 0.5 s - ModelCapabilityError: input bound (53261) plus safety allowance (512) leaves no generation capacity inside effective context 40960 for model 'qwen3:14b'
- context (16384): failed after 0.5 s - ModelCapabilityError: input bound (53261) plus safety allowance (512) leaves no generation capacity inside effective context 40960 for model 'qwen3:14b'

Rendered by `python -m sovereign_product.qualification report` from `run2-ollama-production-slate.results.json`.
