# Sovereign Distillery — Evidence Log v0.1

Every external claim used in the review and specification, with its source and confidence. Claims not listed here are not evidenced.

## Directly observed (this workspace / this device)

| ID | Observation | Method | Date |
|---|---|---|---|
| E-1 | `D:\Sovereign Distillery` existed and was empty | `device_list_dir` recursive | 2026-08-19 |
| E-2 | Host: Windows x64, device `desktop-03ptabh`, Node 24.18.1, Electron 42.9.2 | `get_device_info` | 2026-08-19 |
| E-3 | Home directory contains `.ollama`, `.lmstudio`, `.gemini`, `.codex`, `.grok`, `.aider`, `deepseek-harness`, `ollama-fable-import`, `repos`, `praxis`, `skills-matrix`, `RRR_DUAL_CYCLE`, `URI`, `broker`, `audit`, `data` | `get_device_info` (names only — contents not readable) | 2026-08-19 |
| E-4 | Folder-access grant for `.ollama` and `.lmstudio` was **refused** by the device bridge | `device_request_folder_access` | 2026-08-19 |

**E-4 is the most consequential gap.** The local model library — the entire input to this system — has not been enumerated.

## External sources

| ID | Claim | Source | Type | Confidence |
|---|---|---|---|---|
| E-5 | RTX 5060 Ti ships in 8 GB and 16 GB variants; GDDR7, 128-bit bus | Multiple hardware review outlets, mutually consistent | Secondary | High |
| E-6 | QLoRA 7B/8B (4-bit NF4, r=64, batch 1, seq 512, AdamW, no gradient checkpointing) ≈ **8 GB VRAM** | Spheron, "GPU VRAM Requirements to Fine-Tune LLMs in 2026" | Secondary, modelled | Medium |
| E-7 | QLoRA 14B ≈ 14 GB; QLoRA 32B ≈ 28 GB; full fine-tune 7B ≈ 88 GB | Same | Secondary, modelled | Medium |
| E-8 | Gradient checkpointing cuts activation memory 40–60%; does not reduce weight/gradient/optimizer memory | Same | Secondary | Medium |
| E-9 | Cross-tokenizer KD is active research (ULD, DSKD, MultiLevelOT, ALM, X-Token). ALM experiments restricted to 2.4B–3.3B; authors report persistent degradation in byte-level transfer and inconsistent best-variant selection; self-assessed as "promising but incomplete maturity" for production | arXiv 2503.20083v2, *Cross-Tokenizer Distillation via Approximate Likelihood Matching* | **Primary** | High |
| E-10 | ALM+SFT distilling math-specialized Llama 8B → Gemma 2B reached 49.0% average vs teacher 74.6% | Same paper | **Primary** | High |
| E-11 | DeepSeek/Phi/GLM commonly MIT; Qwen3/Mistral/Gemma-4-era commonly Apache-2.0; Llama 4 under Meta Community License with >700M MAU cap; Gemma 3 under custom non-OSI Gemma Terms | `awesome-open-weight-models` (GitHub) and licensing blog aggregation | Secondary | **Low — must be verified against primary license text per model** |

## Claims deliberately NOT made

- No benchmark was run on the operator's GPU.
- No model in the local library was profiled, or even identified.
- No sibling repository (Sovereign, Debate Table, Multi-Model App) was read.
- No statement here is a measurement of this system.

## Verification debt

| Item | Why it matters | How to close |
|---|---|---|
| E-6/E-7/E-8 are modelled, not measured | The entire hardware envelope (§9 of spec) rests on them | One measured QLoRA run on this GPU |
| E-11 is secondary-source | License classification gates corpus admission | Read primary license text for each model in the library |
| Toolchain support for Blackwell sm_120 | Nothing runs if kernels are unavailable | Attempt the run; record driver/CUDA/PyTorch/bitsandbytes versions |
| Library inventory (E-4 blocked) | Teacher ordering, licensing, schedule all depend on it | Operator connects folder, or supplies `ollama list` output |
