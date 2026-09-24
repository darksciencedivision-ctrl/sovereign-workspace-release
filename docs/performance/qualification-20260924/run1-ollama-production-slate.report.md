# Qualification report - ollama-production-slate

- Measured: 2026-09-24T14:50:13.919Z -> 2026-09-24T14:54:37.231Z (UTC)
- Backend / primary model: ollama / qwen3:14b
- Hardware: NVIDIA GeForce RTX 5060 Ti (8151 MiB VRAM); Windows-11-10.0.26200-SP0
- Product: 3.1.2 (workers 1); repetitions per step: 3
- SLOs: failure rate <= 0.2, QUICK p95 <= 300 s, DEEP p95 <= 3600 s, cancel p95 <= 30 s

## Envelope (enforced)

- Qualified context window (the num_ctx measured): **40960 tokens**
- Largest prompt meeting the SLOs through the product: **~8192 tokens**
- Qualified concurrent jobs: **2**
- Qualified workflows: QUICK=yes, DEEP=NO, cancellation=yes
- Largest task observed (input + output, the product's job metric): 8307 tokens (a configured MAX_OUTPUT_TOKENS above this is reported UNQUALIFIED)
- Peak VRAM: 7523 MiB (baseline 1872); peak system RAM in use: 41632 of 65230 MiB

## End-to-end latency through the product

| Scenario | Runs | Completed | Failure rate | p50 s | p95 s | max s | task tokens/s p50 | max task tokens |
|---|---|---|---|---|---|---|---|---|
| context_2048 | 3 | 3 | 0.00 | 8.8 | 8.9 | 8.9 | 250.88 | 2216 |
| context_8192 | 3 | 3 | 0.00 | 22.9 | 23.0 | 23.0 | 362.89 | 8307 |
| context_16384 | 3 | 0 | 1.00 | - | - | - | - | - |
| context_32768 | 0 | 0 | - | - | - | - | - | - |
| concurrency_1 | 3 | 3 | 0.00 | 11.0 | 15.0 | 15.0 | 27.99 | 329 |
| concurrency_2 | 2 | 2 | 0.00 | 15.0 | 23.9 | 23.9 | 12.85 | 341 |
| quick_cold | 1 | 1 | 0.00 | 43.3 | 43.3 | 43.3 | 6.79 | 294 |
| quick_warm | 3 | 3 | 0.00 | 13.5 | 13.9 | 13.9 | 24.06 | 332 |
| deep | 1 | 0 | 1.00 | - | - | - | - | - |

## Cancellation

- 1 of 1 mid-flight cancellations reached `cancelled`; cancel-to-terminal p50 1.1 s, p95 1.1 s

## Failures

- context (16384): failed after 0.6 s - ModelCapabilityError: input bound (53261) plus safety allowance (512) leaves no generation capacity inside effective context 40960 for model 'qwen3:14b'
- context (16384): failed after 0.6 s - ModelCapabilityError: input bound (53261) plus safety allowance (512) leaves no generation capacity inside effective context 40960 for model 'qwen3:14b'
- context (16384): failed after 0.6 s - ModelCapabilityError: input bound (53261) plus safety allowance (512) leaves no generation capacity inside effective context 40960 for model 'qwen3:14b'
- deep (): failed after 21.2 s - member_2 capability resolution failed: ModelCapabilityError: requested num_ctx 40960 exceeds native/configured limit 32768 for model 'qwen2.5:14b-instruct'; declared 131072 is not supported and is not

Rendered by `python -m sovereign_product.qualification report` from `run1-ollama-production-slate.results.json`.
