# SW-27 qualification - 2026-09-24

End-to-end measurements of the `ollama-production-slate` profile, taken **through the running
SOVEREIGN product** (its own `/v1` API: sessions, messages, job polling, cancellation) on the
operator's machine: NVIDIA GeForce RTX 5060 Ti (8 GB VRAM), 64 GB RAM, Windows 11, Ollama backend,
product 3.1.2 with one job worker. Each run used an isolated scratch state root.

| File | What it is |
|---|---|
| `run2-ollama-production-slate.report.md` | **Authoritative** report (after the DEEP fix below) |
| `run2-ollama-production-slate.results.json` | Raw per-job results behind it |
| `run1-ollama-production-slate.report.md` / `.results.json` | First run, which found the DEEP defect |

Both reports are rendered mechanically from the results files by
`python -m sovereign_product.qualification report`.

## Findings

1. **DEEP was broken on the shipped configuration - found by this qualification and fixed.** Run 1:
   every DEEP run failed immediately (`requested num_ctx 40960 exceeds native/configured limit
   32768 for model 'qwen2.5:14b-instruct'`). The product sent the primary model's window to every
   member of the DEEP slate. It now uses the smallest cap across the slate (16384, bounded by
   qwen3:8b's configured slot). Run 2: DEEP completed end-to-end in 360 s.
2. **Usable prompt size is ~8k tokens, not the declared 131072-token context.** The configured window
   for QUICK is 40960 tokens (qwen3:14b cap). But the product's input-capacity check bounds a
   ~13k-token prompt (about 52k characters) at 53261 tokens, so a 16k-token prompt is refused before
   generation, in both runs, deterministically (`ModelCapabilityError`, in about 0.5 s). That is a
   clean, explicit refusal, not truncation or a crash. The declared 131072 context is **not
   qualified** on this machine or configuration.
3. **QUICK is fast once warm**: p50 about 10 s (p95 about 12 s) for short prompts, 22 s for 8k-token
   prompts; two concurrent jobs completed within the SLO (they queue on the single worker).
   Mid-flight cancellation reached `cancelled` within about 1 s.
4. **Memory**: peak VRAM 7.7 of 8 GB (the GPU is effectively full; the 14B model runs partly
   offloaded); peak system RAM in use about 40 of 64 GB.

## Caveats (read before relying on the numbers)

- Small samples: 3 repetitions per ladder step, a single DEEP run, a single cancellation. The p95
  values are nearest-rank over those few samples. Re-run with `--repetitions` for tighter figures.
- Cold start: run 2's "cold" QUICK (18 s) followed an unload of models that had only just been
  resident (baseline VRAM 7.5 GB), so the files were likely still in the OS cache. Run 1's cold start
  (43 s) is closer to a first load after idle.
- `tokens` is the product's job metric, which counts input plus output. The configured
  `MAX_OUTPUT_TOKENS` (32768) was never exercised and is reported as UNQUALIFIED.
- **`llamacpp-production-slate` is UNQUALIFIED**: no llama.cpp server binary is provisioned in this
  checkout, so that profile could not be measured. Provision it and run the same command.

## Reproduce / apply

```
cd modules\sovereign
.venv\Scripts\python.exe -m sovereign_product.server --root . --port 5299 --workers 1    # product under test
.venv\Scripts\python.exe -m sovereign_product.qualification --root . run --profile ollama-production-slate --base-url http://127.0.0.1:5299 --out results.json
.venv\Scripts\python.exe -m sovereign_product.qualification --root . report --results results.json --out report.md
.venv\Scripts\python.exe -m sovereign_product.qualification --root . apply --results results.json   # install envelope in YOUR state home
```

The envelope was **not** installed into the operator's real state home. `apply` changes the live
product: it enforces the measured window and concurrency, and it lowers `CONTEXT_WINDOW` to 40960
and `MAX_OUTPUT_TOKENS` to 20480 through the downward-only overrides. Until it is applied, the
product reports this profile as `unqualified` and refuses nothing.
