# SOVEREIGN DISTILLERY
## Evidence-Grounded Design Plan and Engineering Report

| | |
|---|---|
| **Document** | Design Plan & Engineering Report — v1.0 |
| **Supersedes** | The hardware and library sections of all prior Distillery documents |
| **Date** | 19 August 2026 |
| **Workspace** | `D:\Sovereign Distillery` |
| **Parent** | Sovereign Research Workspace |
| **Status** | **First evidence-grounded plan.** Prior documents were specification against estimates. This one is specification against measurements. |
| **Authority** | The human operator controls objectives, scope, promotions, strategic direction, and final acceptance. This document plans and recommends. It does not decide. |
| **Classification** | Internal engineering baseline |

---

## Document control

| Version | Date | Change | Basis |
|---|---|---|---|
| v1.0 | 2026-08-19 | Initial evidence-grounded plan | D1 machine characterization + D2 library enumeration, both executed on the target machine |

**Preceding documents and their current standing**

| Document | Standing after this report |
|---|---|
| `SOVEREIGN-DISTILLERY-REPORT.md` | Findings F-1..F-8 stand except where measurement supersedes. Hardware section §IX.9 **superseded** by Part B.1. |
| Integrated Canonical Engineering Report (§1–113) | Architecture stands. Hardware §41 and roadmap §86–§101 **superseded** by Parts B and F. |
| `docs\03-INTEGRATION-REVIEW.md` | IR-1..IR-10 stand. All adopted. |
| `docs\DECISIONS-v1.md` | Stands. RD-1..RD-4 resolved in Part G.5 of this document. |

**Evidence conventions.** Every substantive claim carries a label.

| Label | Meaning |
|---|---|
| `MEASURED` | Observed on the operator's machine, this date, by a named tool |
| `DERIVED` | Computed from `MEASURED` values by a stated method |
| `ESTIMATE` | Modelled from external sources or calibrated heuristics; **not** measured here |
| `ASSUMPTION` | Taken as given, load-bearing, unverified |
| `UNVERIFIED` | Asserted somewhere; no evidence located either way |

Where a number is an `ESTIMATE`, the method and its calibration are stated. Where a conclusion is structural (robust to the estimate being wrong by a factor), that is stated too — because several conclusions here are structural even though their supporting numbers are not precise.

---

# PART A — EXECUTIVE SUMMARY

## A.1 What changed

Two instruments were run on the target machine. Both returned. The results move this project from "specification against modelled numbers" to "specification against a measured baseline" — and the baseline is materially different from what every prior document assumed.

**The library is far larger and far heavier than assumed.** 43 registry entries, **768.4 GiB** on disk, spanning 8B to 128B parameters.

**The machine is smaller than assumed.** 8151 MiB nominal VRAM, of which **5383 MiB was free** at capture — 2768 MiB was already consumed at rest. The training stack does not exist: **PyTorch is not installed.**

## A.2 The six findings that reorder the project

### EF-1 — There is no teacher smaller than the student. The premise of the ordering has no floor.

`MEASURED`. The smallest generative model in the library is **8B** (`dolphin-llama3:8b`, 4.34 GiB). The student, under any reading of the measured hardware, is **1B–3B**.

Every prior document reasoned about processing "smallest to largest," with the smallest teachers serving as cheap pipeline-validation subjects and possibly as a foundational curriculum. **That floor does not exist in this library.** Teacher #1 is already 3–8× the student's parameter count. The capability delta against the seed will be large and positive from the very first teacher — which removes the C-3 contradiction (empty early deltas) entirely, and simultaneously removes the "cheap debugging teacher" justification that F-3 used to rescue the ordering.

The ordering survives, but for a **third** reason neither prior document gave: it is now a **generation-cost ordering**. See EF-3.

### EF-2 — There is no seed candidate in the library either.

`DERIVED`. The library contains nothing between 567M (an embedding model) and 8B. **The Sovereign seed cannot be sourced from local material.** OQ-001's Phase-A bootstrap requires acquiring 1–3B base candidates from outside the current library.

This is a small, concrete, closeable gap — but it was invisible until the inventory existed, and it blocks Phase D3 as currently written.

### EF-3 — Generation, not training, is the binding constraint. The library has a feasibility frontier at roughly 12–15B.

`ESTIMATE`, structurally robust. With 5.26 GiB of usable VRAM, a teacher's corpus-generation throughput collapses once its weights exceed what fits resident. Modelled against an 8M-token targeted corpus:

| Tier | Teachers | Est. generation time | Verdict |
|---|---:|---|---|
| **T1 — VIABLE** | 5 | ≤ 4 days | Run these |
| **T2 — COSTLY** | 16 | 5–21 days | Justify each individually |
| **T3 — DEFERRED** | 12 | 22–90 days | Not on this hardware at this corpus size |
| **T4 — INFEASIBLE** | 6 | 100–170 days | Not on this hardware, full stop |

**Every prior document treated the whole library as the input queue. Measurement says 5 of 39 teachers are comfortably viable and 18 of 39 are not viable at all on this machine.** The precise day counts are estimates and will be wrong; the existence and approximate location of the frontier is structural and will not be.

### EF-4 — The training stack does not exist; the generation stack does.

`MEASURED`. `ModuleNotFoundError: No module named 'torch'`. No PyTorch, no bitsandbytes, no psutil. But Ollama is operational and serving 43 models.

This is a clean and useful split. **The Distillery can begin generating corpora today and cannot train anything today.** It also means the single most important unknown in the entire project — whether the `sm_120` / bitsandbytes 4-bit path functions on this specific card — is still unmeasured, because the software needed to measure it is absent.

### EF-5 — A significant fraction of the library is already synthetic-derived. Distilling it compounds.

`DERIVED` from model identities. `deepseek-r1:8b`, `:14b`, `:32b`, `:70b` are distillations of R1 into other bases. `dolphin3`, `dolphin-llama3` are instruction-tuned heavily on synthetic corpora.

Training Sovereign on their outputs makes Sovereign a **third-generation** synthetic artifact for that material. This is R-3 (synthetic-data collapse / diversity narrowing) arriving earlier and harder than the risk register anticipated. **It elevates the non-synthetic corpus fraction from a good practice to a requirement**, and it makes teacher-lineage a mandatory registry field.

### EF-6 — Same-base families are present. This reopens weight merging for specific groups — and creates a contamination risk.

`DERIVED`, requires confirmation. The R1 distills share base architectures with other library members (Qwen2.5-14B, Qwen3-8B, Llama-3.3-70B classes). Where confirmed, this is the **only** circumstance in which the integrated report's "compatible weight merging" pathway is legitimately available (F-2c / ADR-0002).

The same fact is a hazard: a teacher and its own base sitting in one queue means capability measurements across them are **not independent**, and a corpus built from both will be more correlated than the diversity metrics will show.

## A.3 What the operator must decide

| # | Decision | Why now |
|---|---|---|
| **DR-1** | Accept the tiered queue (T1/T2/T3/T4) as the operative teacher plan, replacing "process the whole library" | 18 of 39 teachers are not runnable here; planning around them wastes the plan |
| **DR-2** | Approve acquisition of 1–3B seed candidates from outside the library | Nothing local can serve as the seed (EF-2). Blocks D3. |
| **DR-3** | Set the corpus token budget per teacher | Every schedule number in Part D scales linearly with it |
| **DR-4** | Confirm the two-runtime split — Ollama for generation, PyTorch for training | Determines the environment remediation work in Part F.0 |
| **DR-5** | Rule on whether T3/T4 teachers are deferred-pending-compute or removed | Affects retention policy: ~470 GiB of disk is held by teachers that cannot currently be used |

## A.4 Recommended immediate sequence

1. **Install and verify the training stack** (Part F.0). Until `d1_characterize.py` reports a successful bitsandbytes 4-bit forward pass on `sm_120`, the local training plan is unproven and every downstream estimate is provisional.
2. **Measure real generation throughput** on one T1 teacher (Part F.1). Replaces the whole of Part D's estimates with measurements.
3. **Acquire and baseline 1–3B seed candidates** (Part F.3).
4. **Build the evaluation suite** (Part F.4) — still the highest-value single artifact in the project.

**Nothing in Parts C through K should be built before steps 1 and 2 return.** They are written so that work can start the moment those two measurements land.

---

# PART B — MEASURED BASELINE

## B.1 Hardware profile

Source: `tools\d1_characterize.py`, executed 2026-08-19 on `desktop-03ptabh`. Output written to `runs\hardware_profile.json`.

| Property | Value | Label |
|---|---|---|
| GPU | NVIDIA GeForce RTX 5060 Ti | `MEASURED` |
| VRAM nominal | 8151 MiB (7.96 GiB) | `MEASURED` |
| **VRAM free at capture** | **5383 MiB (5.26 GiB)** | `MEASURED` |
| **VRAM consumed at rest** | **2768 MiB (2.70 GiB)** | `DERIVED` |
| Compute capability | 12.0 → **`sm_120`** (Blackwell) | `MEASURED` |
| Driver | 610.74 | `MEASURED` |
| PyTorch | **absent** — `ModuleNotFoundError` | `MEASURED` |
| bitsandbytes | **absent** (blocked by torch) | `MEASURED` |
| psutil | absent | `MEASURED` |
| System RAM | **not captured** — psutil absent, WMI fallback did not report | gap |
| Disk free | not shown in transcript; present in JSON | gap in this report |
| VRAM probe | **not executed** — requires torch | gap |

### B.1.1 The 2.70 GiB finding

This is the most operationally significant number in the report and it appears in no prior document.

Every prior VRAM calculation used the **nominal** 8 GiB figure. The machine has **5.26 GiB actually available**. The 2.70 GiB delta is the Windows desktop compositor, driver reserve, and whatever else was resident at capture — including, quite possibly, an Ollama model still warm.

**Consequences, restated against 5.26 GiB rather than 8 GiB:**

| Configuration | Modelled requirement | Against 8 GiB | **Against 5.26 GiB** |
|---|---|---|---|
| QLoRA 7B (bs1, seq512, no ckpt) | ~8.0 GiB | Marginal | **Not possible** |
| QLoRA 3B (est.) | ~3.5–4.5 GiB | Comfortable | **Feasible, tight** |
| QLoRA 1B (est.) | ~1.5–2.5 GiB | Comfortable | **Comfortable** |
| Teacher + student co-resident | ~2× | Not possible | **Not possible** |

The validation report's F-1 concluded a 1B–3B working envelope with 7B as "an experiment to attempt and measure." **Measurement moves 7B from marginal to out**, unless the 2.70 GiB at-rest consumption can be substantially reclaimed.

**Actionable:** re-run `d1_characterize.py --vram-probe` after closing Ollama and any GPU-accelerated applications. If free VRAM rises materially, the envelope widens. This is a five-minute test with a real payoff and it has not been done.

### B.1.2 The `sm_120` question is still open — and it is the project's largest single unknown

`sm_120` is confirmed present on the card. What is **not** confirmed is whether the training stack supports it. Blackwell consumer architecture support has been a documented friction point across the PyTorch ecosystem, with stable-channel support lagging CUDA's own support and ecosystem libraries (bitsandbytes, triton, flash-attention) lagging PyTorch in turn.

The reviewer will not assert a version matrix that cannot be verified from here. **The procedure is the answer, not a version number:** install a CUDA 12.8-or-newer PyTorch build, then let `d1_characterize.py` adjudicate. The tool already tests the two things that matter — whether `sm_120` appears in the installed build's arch list, and whether a `bitsandbytes` `Linear4bit` forward pass actually executes and produces finite output on the device.

**If that test fails, the local QLoRA path is unavailable regardless of VRAM, and the project's compute question (OQ-006) reopens immediately rather than eventually.** `ESTIMATE` of likelihood: not offered. It is cheap to measure and expensive to guess.

## B.2 Model library

Source: `tools\d2_registry.py`, executed 2026-08-19. Output written to `registry\teachers.json` / `.md`.

| Metric | Value |
|---|---|
| Registry entries | **43** |
| Generative teachers | **39** |
| Non-teachers (embedding / artifact) | **4** |
| Total on disk | **768.4 GiB** |
| Smallest generative model | 8B — `dolphin-llama3:8b`, 4.34 GiB |
| Largest | 128B — `mistral-medium-3.5`, 74.73 GiB |
| Dominant quantization | Q4_K_M (32 of 43) |
| Runtime | Ollama (all entries) |

Parameter classes present: 8B ×4 · 12B ×1 · 14–15B ×4 · ~22–24B ×5 · ~26–32B ×15 · 35–36B ×2 · ~69–70B ×3 · 109–128B ×3.

**Observation.** This is a serious library — roughly three-quarters of a terabyte, with strong coverage of the 24–32B class. It is also a library assembled for **inference and orchestration**, not for distillation onto a small student. Those are different optimization targets, and the mismatch is the source of EF-1 and EF-3.

## B.3 What the measurements invalidate

| Prior claim | Source | Status after measurement |
|---|---|---|
| "8 GB VRAM available" | All prior docs | **Wrong.** 5.26 GiB free. |
| "7B QLoRA is an experiment to attempt" | Validation F-1, ADR-0003 | **Superseded.** Not possible at 5.26 GiB. |
| "Small teachers are cheap to debug the pipeline with" | Validation F-3; Integrated §12.2 | **No longer applies.** No teacher below 8B exists. |
| "A competent seed may produce empty deltas against small teachers" | Validation C-3; Integrated §11 | **No longer applies.** Every teacher dwarfs the student. |
| "Process the local library smallest to largest" | OBJ-3, all docs | **Survives, but 18 of 39 teachers are not runnable here.** Requires tiering (Part C.5). |
| "The seed will be selected at D3" | Integrated §89; Decisions §5 | **Blocked.** No local candidate exists (EF-2). |
| Hardware envelope §IX.9 / §41 | Validation, Integrated | **Superseded** by B.1. |

## B.4 Defects in the reviewer's own tooling

Found by running it. Owned here rather than discovered later.

### TD-1 — MAJOR — The emitted ordering is wrong, and ordering is OBJ-3

`d2_registry.py` v1 sorted into two buckets: models with a `general.parameter_count` integer sorted ascending by parameters, then models without one sorted ascending by disk size. Only 12 of 43 entries carry that field; the other 31 carry only a `general.size_label` string.

The result is the run the operator saw: an ascending run from 23.6B to 127.7B, followed by a second ascending run from 0.255 GiB to 62.8 GiB. **It is not a smallest-to-largest queue and must not be used as one.** Corrected queue in Part C.

**Fix (shipped in v2):** parse `size_label` into a numeric estimate; where absent, derive parameters from file size ÷ measured bits-per-weight; cross-check declared labels against file size and reject labels that disagree by more than 50%.

### TD-2 — MAJOR — Embedding models were classified as teachers

`nomic-embed-text`, `mxbai-embed-large`, and `bge-m3` cannot generate instruction-following training data. They occupied queue positions 13–15. **Fix:** role classification field — `TEACHER` / `INFRASTRUCTURE` / `ARTIFACT` / `INELIGIBLE`.

These three are not useless — they are exactly the right instruments for corpus deduplication, semantic-diversity measurement (R-3), and retrieval-correctness validation. They move from the teacher queue into the **tooling** inventory, which is a promotion, not a demotion.

### TD-3 — MODERATE — A non-model artifact was counted as a model

Entry 16, `DavidAU/Qwen3.6-27B-Fable-Fusion-711-Unc` at **461M / F32 / 1.716 GiB**, shares its name with entry 27 at 27B / IQ2_M / 10.872 GiB. A 461M F32 file alongside a 27B model of the same name is almost certainly a projector, adapter, or shard rather than a standalone model. Classified `ARTIFACT` pending confirmation.

### TD-4 — MODERATE — Deduplication was by path, not by content

Seven pairs share identical size and quantization. Path-based dedup cannot distinguish "same blob, two tags" from "two genuinely different models that happen to be the same size."

**Confirmed-looking aliases** (same size, same quant, near-identical naming): `qwen3.6-fable-iq2:latest` ≡ `DavidAU/Qwen3.6-27B-Fable-Fusion-711-Unc` (10.872 GiB IQ2_M); `qwen3.8:27b` ≡ `Qwen3.8-27B-Uncensored:latest` (15.656 GiB Q4_K_M).

**Coincidence, not duplication — and highly informative** (see EF-6): `deepseek-r1:8b` ≈ `qwen3:8b`; `deepseek-r1:14b` ≈ `qwen2.5:14b-instruct`; `deepseek-r1:70b` ≈ `llama3.3:70b`. These are not duplicates. They are **R1 distills sitting next to their own base models.**

**Fix (shipped in v2):** deduplicate by blob content hash; record `base_family` and `derived_from` so lineage relationships are explicit rather than inferred from a size collision.

### TD-5 — MINOR — Incomplete `file_type` map

`gpt-oss:20b` and `gpt-oss:120b` reported `ftype_4`, unmapped. **Fix:** extended enum in v2, with unmapped values reported as `ftype_N` rather than silently omitted (which v1 already did correctly).

### TD-6 — MINOR — MoE handling

`laguna-xs-2.1:latest` declared `256x2.2B` (563B total) at 18.88 GiB — a 16× disagreement with the ~32.8B its file size implies. v1 sorted it to position 1 on the basis of 2.2B "active" parameters, which is wrong on both counts.

**Fix (shipped in v2):** where a declared label disagrees with the size-derived estimate by more than 50%, reject the label, use the size-derived value, and flag the entry `LABEL_INCONSISTENT` for manual review.

**Calibration note.** The size-derived method was validated against entries where both values are known: `qwen3:8b` declared 8.0B / derived 8.4B; `qwen3:32b` declared 32.0B / derived 32.6B; `deepseek-r1:70b` declared 70.0B / derived 68.7B; `qwen3.6-fable-iq2` declared 27.0B / derived 28.3B. Agreement within ~5% across three quantization formats. `laguna-xs-2.1` is the sole 16× outlier, which is why the label is rejected rather than the method.

---

# PART C — CORRECTED TEACHER REGISTRY

## C.1 Method

Ordering is ascending by parameter count, using this precedence:

1. **Declared** — GGUF `general.parameter_count`, where present.
2. **Label-parsed** — GGUF `general.size_label` (`8B`, `27B`, `256x2.2B`), parsed numerically.
3. **Size-derived** — file bytes × 8 ÷ measured bits-per-weight, where neither above is present.
4. **Consistency gate** — where (1) or (2) disagrees with (3) by more than 50%, the declared value is **rejected** and (3) is used, with the entry flagged.

Measured bits-per-weight, calibrated against the library's own known-parameter entries: `Q4_K_M` 4.95 · `Q4_0` 4.64 · `IQ2_M` 3.30 · `ftype_4` ~4.30 · `F16` 16 · `F32` 32.

## C.2 Role classification

| Role | Count | Members | Disposition |
|---|---:|---|---|
| **TEACHER** | 39 | All generative models | Enter the queue, subject to tiering |
| **INFRASTRUCTURE** | 3 | `nomic-embed-text`, `mxbai-embed-large`, `bge-m3` | **Not teachers.** Reassigned to the corpus-tooling inventory: deduplication, semantic-diversity measurement, retrieval validation |
| **ARTIFACT** | 1 | `DavidAU/Qwen3.6-27B-Fable-Fusion-711-Unc` @ 461M/F32 | Excluded pending confirmation it is a projector or shard |

## C.3 Corrected queue

Ascending by parameter count. Throughput and duration are `ESTIMATE` — see Part D for the model and its assumptions. **No tokens-per-second figure in this table has been measured on this machine.**

| # | Model | Params | Quant | GiB | Basis | ~tok/s | ~days/8M tok | Tier |
|---|---|---:|---|---:|---|---:|---:|---|
| 1 | `dolphin3:8b` | 8B | Q4_K_M | 4.58 | declared | 55 | 2 | **T1-VIABLE** |
| 2 | `deepseek-r1:8b` | 8B | Q4_K_M | 4.87 | declared | 53 | 2 | **T1-VIABLE** |
| 3 | `qwen3:8b` | 8B | Q4_K_M | 4.87 | declared | 53 | 2 | **T1-VIABLE** |
| 4 | `dolphin-llama3:8b` | 8B | Q4_0 | 4.34 | estimated | 55 | 2 | **T1-VIABLE** |
| 5 | `gemma4:12b` | 12B | Q4_K_M | 6.87 | declared | 26 | 4 | **T1-VIABLE** |
| 6 | `deepseek-r1:14b` | 14B | Q4_K_M | 8.37 | declared | 17 | 5 | **T2-COSTLY** |
| 7 | `qwen2.5:14b-instruct` | 14B | Q4_K_M | 8.37 | declared | 17 | 5 | **T2-COSTLY** |
| 8 | `qwen3:14b` | 14B | Q4_K_M | 8.64 | declared | 16 | 6 | **T2-COSTLY** |
| 9 | `phi4:14b` | 15B | Q4_K_M | 8.43 | declared | 17 | 5 | **T2-COSTLY** |
| 10 | `codestral:latest` | 22B | Q4_0 | 11.71 | estimated | 9 | 11 | **T2-COSTLY** |
| 11 | `magistral:latest` | 24B | Q4_K_M | 13.35 | declared | 7 | 14 | **T2-COSTLY** |
| 12 | `devstral-small-2:latest` | 24B | Q4_K_M | 14.13 | declared | 6 | 16 | **T2-COSTLY** |
| 13 | `mistral-small3.2:latest` | 24B | Q4_K_M | 14.13 | declared | 6 | 16 | **T2-COSTLY** |
| 14 | `gpt-oss:20b` | 26B | ftype_4 | 12.85 | estimated | 7 | 13 | **T2-COSTLY** |
| 15 | `gemma4:26b` | 26B | Q4_K_M | 16.75 | declared | 4 | 22 | **T3-DEFERRED** |
| 16 | `qwen3.6-fable-iq2:latest` | 27B | IQ2_M | 10.87 | declared | 10 | 9 | **T2-COSTLY** |
| 17 | `DavidAU/Qwen3.6-27B-Fable-Fusion-711-Unc` | 27B | IQ2_M | 10.87 | declared | 10 | 9 | **T2-COSTLY** |
| 18 | `qwen3.8:27b` | 27B | Q4_K_M | 15.66 | declared | 5 | 19 | **T2-COSTLY** |
| 19 | `Qwen3.8-27B-Uncensored:latest` | 27B | Q4_K_M | 15.66 | declared | 5 | 19 | **T2-COSTLY** |
| 20 | `medgemma:27b` | 27B | Q4_K_M | 16.20 | declared | 4 | 21 | **T2-COSTLY** |
| 21 | `qwen3.6:27b` | 28B | Q4_K_M | 16.22 | declared | 4 | 21 | **T2-COSTLY** |
| 22 | `glm-4.7-flash:latest` | 30B | Q4_K_M | 17.71 | declared | 4 | 25 | **T3-DEFERRED** |
| 23 | `granite4.1:30b` | 30B | Q4_K_M | 16.29 | declared | 4 | 21 | **T2-COSTLY** |
| 24 | `qwen3:30b-a3b` | 30B | Q4_K_M | 17.28 | declared | 4 | 23 | **T3-DEFERRED** |
| 25 | `qwen3-coder:30b` | 30B | Q4_K_M | 17.28 | declared | 4 | 23 | **T3-DEFERRED** |
| 26 | `gemma4:31b` | 31B | Q4_K_M | 18.50 | declared | 3 | 27 | **T3-DEFERRED** |
| 27 | `THUDM_GLM-4-32B-0414-GGUF:Q4_K_M` | 32B | Q4_K_M | 18.33 | declared | 4 | 26 | **T3-DEFERRED** |
| 28 | `deepseek-r1:32b` | 32B | Q4_K_M | 18.49 | declared | 3 | 27 | **T3-DEFERRED** |
| 29 | `GLM-4-32B-0414-GGUF:UD-Q4_K_XL` | 32B | Q4_K_M | 18.55 | declared | 3 | 27 | **T3-DEFERRED** |
| 30 | `qwen3:32b` | 32B | Q4_K_M | 18.81 | declared | 3 | 28 | **T3-DEFERRED** |
| 31 | `laguna-xs-2.1:latest` | 33B | Q4_K_M | 18.88 | estimated | 3 | 28 | **T3-DEFERRED** |
| 32 | `ornith:35b` | 35B | Q4_K_M | 19.71 | declared | 3 | 31 | **T3-DEFERRED** |
| 33 | `qwen3.6:35b` | 36B | Q4_K_M | 22.29 | declared | 2 | 39 | **T3-DEFERRED** |
| 34 | `dolphin-llama3:70b` | 69B | Q4_0 | 37.23 | estimated | 1 | 106 | **T4-INFEASIBLE** |
| 35 | `deepseek-r1:70b` | 70B | Q4_K_M | 39.60 | declared | 1 | 119 | **T4-INFEASIBLE** |
| 36 | `llama3.3:70b` | 70B | Q4_K_M | 39.60 | declared | 1 | 119 | **T4-INFEASIBLE** |
| 37 | `llama4:scout` | 109B | Q4_K_M | 62.80 | estimated | 1 | 168 | **T4-INFEASIBLE** |
| 38 | `gpt-oss:120b` | 122B | ftype_4 | 60.88 | estimated | 1 | 168 | **T4-INFEASIBLE** |
| 39 | `mistral-medium-3.5:latest` | 128B | Q4_K_M | 74.73 | declared | 1 | 168 | **T4-INFEASIBLE** |
## C.4 Structural reading of the queue

**The queue has no shallow end.** Position 1 is 8B — three to eight times the student. Every prior document's reasoning about early-queue behaviour (cheap debugging teachers, empty capability deltas, foundational curricula from weak models) assumed a floor below the student that does not exist here.

**The queue is front-loaded with the only viable work.** Positions 1–5 are the entire T1 tier. Positions 6–10 are 14–15B and cost roughly triple. Beyond position 15 the estimated cost per teacher exceeds two weeks of continuous generation.

**The queue's top third is not runnable on this machine.** Positions 34–39 (69B–128B, 37–75 GiB) are estimated at 100–170 days per corpus. That is not a scheduling problem to optimize; it is a capability the machine does not have.

## C.5 Tiering — the operative plan

| Tier | # | Est. gen. time (8M tok) | Teachers | Policy |
|---|---:|---|---|---|
| **T1 — VIABLE** | 5 | ≤ 4 days | `dolphin3:8b`, `deepseek-r1:8b`, `qwen3:8b`, `dolphin-llama3:8b`, `gemma4:12b` | **Active queue.** All pipeline proving happens here. |
| **T2 — COSTLY** | 16 | 5–21 days | 14B–30B class | **Selective.** Each requires a demonstrated capability delta *and* an explicit operator go before its generation run starts. |
| **T3 — DEFERRED** | 12 | 22–90 days | 26B–36B class | **Deferred pending compute (OQ-006).** Not removed. Not scheduled. |
| **T4 — INFEASIBLE** | 6 | 100–170 days | 69B–128B | **Not runnable on this hardware.** Reclassify only if the compute envelope changes. |

**Disk implication.** T3 and T4 together hold roughly **470 GiB** of the 768 GiB library for teachers that cannot currently be used. That is a retention-policy decision (DR-5), not a technical one — but it should be a decision rather than an accident.

## C.6 Same-base families — opportunity and hazard

`DERIVED` from model identities; **requires blob-level confirmation** before either use.

| Group | Members | Relationship |
|---|---|---|
| Qwen3-8B class | `qwen3:8b`, `deepseek-r1:8b` | R1 distill and its probable base |
| Qwen2.5-14B class | `qwen2.5:14b-instruct`, `deepseek-r1:14b` | R1 distill and its probable base |
| Llama-3.3-70B class | `llama3.3:70b`, `deepseek-r1:70b`, `dolphin-llama3:70b` | R1 distill, Dolphin finetune, probable shared base |
| Qwen3-32B class | `qwen3:32b`, `deepseek-r1:32b` | R1 distill and its probable base |
| GLM-4-32B class | `THUDM_GLM-4-32B-0414:Q4_K_M`, `GLM-4-32B-0414:UD-Q4_K_XL` | Same model, two quantizations |
| Qwen3.6-27B class | `qwen3.6:27b`, `qwen3.6-fable-iq2`, `Fable-Fusion-711` | Base and derivative finetunes |

**Opportunity.** Within a confirmed same-base group, same-architecture weight operations — adapter merging, task vectors, TIES/DARE-style merges — are technically available. This is the **only** circumstance in which the integrated report's "compatible weight merging" pathway is legitimately reachable (ADR-0002, F-2c). It is worth investigating precisely because it does not require the training stack to be as capable.

**Hazard, and it is the more urgent of the two.** Three consequences follow from same-base groups sitting in one queue:

1. **Capability measurements across the group are not independent.** A delta computed between `deepseek-r1:14b` and `qwen2.5:14b-instruct` measures the R1 distillation, not two independent teachers.
2. **Corpora drawn from both members are more correlated than diversity metrics will report**, because the diversity is measured on outputs while the correlation lives in the shared weights.
3. **Distilling an R1 distill makes Sovereign third-generation synthetic** for that material — see EF-5 and Part I, R-3.

**Required registry fields (v2):** `base_family`, `derived_from`, `generation_depth`. Without them the pipeline cannot distinguish an independent teacher from a sibling, and the differential-evaluation step will silently over-count.

---

# PART D — GENERATION FEASIBILITY

This part is the analytical core of the report. It is also the part most dependent on estimates, so its assumptions are stated in full and its measurement plan is specified.

## D.1 Why generation is the binding constraint

Prior documents treated training as the hard problem and generation as a prerequisite. The measurements invert this.

- Training happens **once per teacher**, on a 1–3B student, under QLoRA. Memory-bound but short.
- Generation happens **once per teacher at corpus scale** — millions of tokens — on models 3× to 40× the student's size, on a card that can hold 5.26 GiB.

For a T1 teacher, generation and training are of comparable cost. For a T3 teacher, generation exceeds training by one to two orders of magnitude. **The schedule is a generation schedule.**

## D.2 The throughput model

`ESTIMATE`. Method stated so it can be attacked.

```
usable VRAM       = 5.26 GiB                          [MEASURED]
resident_fraction = min(1, 0.90 × usable / model_GiB)
tok_per_sec       ≈ 55 × resident_fraction^2.1 + 1.2 × resident_fraction
                    floored at 0.55
```

**Assumptions, each of which may be wrong:**

| # | Assumption | Risk if wrong |
|---|---|---|
| A | A fully-resident Q4 model on this card generates ~55 tok/s single-stream | Scales all T1 numbers linearly |
| B | Offload penalty is super-linear (exponent 2.1) as layers spill to system RAM | Dominates T2/T3/T4; the most uncertain assumption in the report |
| C | Single-stream generation; no batching | **Conservative.** Batched generation could improve throughput several-fold — see D.5 |
| D | System RAM is sufficient to hold spilled layers | **Unverified** — RAM was not captured (B.1). If a 75 GiB model exceeds RAM, throughput is not slow, it is zero |
| E | MoE models behave like dense models of the same file size | Wrong for `gpt-oss` and `qwen3:30b-a3b`; MoE activates a fraction of weights and should generate faster than the model predicts |
| F | Corpus target of 8M tokens per teacher | Linear scalar on every duration; currently a working assumption, not a decision (DR-3) |

**What is structural despite all of the above:** throughput falls sharply once a model exceeds resident capacity; the library spans 4.3 GiB to 74.7 GiB against 5.26 GiB of VRAM; therefore a frontier exists and it sits close to the resident boundary. Assumptions A, B, and F can each be wrong by a factor of two or three without changing the tier structure — they would move the boundaries between tiers, not eliminate them.

**Assumption D is the exception.** If system RAM is inadequate, T3 and T4 are not slow — they are impossible, and the report is too optimistic rather than too pessimistic. This is why capturing system RAM is a Part F.0 task rather than a nicety.

## D.3 Corpus budget sensitivity

Duration scales linearly with the token budget. Illustrative, at three budgets:

| Teacher | 2M tokens | 8M tokens | 20M tokens |
|---|---:|---:|---:|
| `qwen3:8b` (T1) | ~10 hrs | **~1.7 days** | ~4.4 days |
| `gemma4:12b` (T1) | ~21 hrs | **~3.6 days** | ~8.9 days |
| `qwen3:14b` (T2) | ~1.4 days | **~5.7 days** | ~14 days |
| `mistral-small3.2` (T2) | ~3.9 days | **~15.6 days** | ~39 days |
| `qwen3:32b` (T3) | ~7 days | **~27.8 days** | ~70 days |
| `llama3.3:70b` (T4) | ~30 days | **~119 days** | ~298 days |

**Reviewer recommendation for DR-3:** begin at **2M tokens per teacher** for the T1 tier. It is enough to demonstrate measurable capability transfer on a 1–3B student, it keeps the first full cycle inside a working week, and it converts the Part D estimates into measurements at low cost. Scale up only once a measured relationship exists between corpus size and capability delta — which is itself worth knowing and which nothing in the project currently measures.

## D.4 Consequences for the roadmap

1. **T1 is the entire near-term program.** Five teachers, roughly 11 days of generation at 8M tokens or under 3 days at 2M. Everything — pipeline proof, Route A, Route B, promotion, quantization, resumability — is demonstrated inside T1.
2. **T2 becomes per-teacher business cases.** Two weeks of continuous generation is a real commitment. Each T2 teacher should require a demonstrated delta and an explicit go.
3. **T3/T4 become the concrete content of OQ-006.** The compute question is no longer abstract: it is "18 teachers holding ~470 GiB that this machine cannot use."
4. **The `mistral-medium-3.5` case is instructive.** 127.7B, 74.73 GiB, ~168 days estimated. It is the strongest model in the library and the least reachable. That gap is the entire argument for OQ-006, stated in one row.

## D.5 What must be measured to replace this part

Part D should have the shortest life of any section in this document.

| Measurement | Method | Replaces |
|---|---|---|
| Resident throughput | `ollama run qwen3:8b --verbose` on a fixed prompt set; record eval tok/s | Assumption A |
| Offload throughput | Same on `qwen3:14b` and `qwen3:32b` | Assumption B — the report's weakest point |
| Batched throughput | Concurrent requests to the Ollama API; measure aggregate tok/s | Assumption C; may materially improve every tier |
| System RAM & swap behaviour | `d1_characterize.py` after `pip install psutil`; observe during a T3 load | Assumption D — the one that could invalidate rather than shift |
| MoE behaviour | Throughput on `qwen3:30b-a3b` vs dense `qwen3:32b` at similar file size | Assumption E |

**Assumption C deserves particular attention.** Corpus generation is embarrassingly parallel and entirely throughput-bound — latency is irrelevant. If batched generation yields 3–4× aggregate throughput, the frontier moves up a full tier and much of T2 becomes viable. This is the single highest-leverage measurement in the plan and it costs an afternoon.

---

# PART E — REVISED ARCHITECTURE

Deltas against the integrated canonical architecture. The architecture is not re-derived; §1–§113 of the integrated report stand except where measurement forces a change.

## E.1 Student sizing

| Parameter | Value | Basis |
|---|---|---|
| v1 student size | **1B–3B** | 5.26 GiB usable VRAM (B.1) |
| Method | QLoRA 4-bit NF4, gradient checkpointing **on** | Memory envelope |
| Sequence length | Start 1024; raise only if measurement permits | Activation memory is the tunable term |
| Precision | bf16 compute if `sm_120` supports it; fp16 fallback | To be measured by D1 |
| 7B student | **Removed from v1** | Not possible at 5.26 GiB |

**Recommendation.** Select **two** seed candidates — one ~1B and one ~3B. The 1B trains fast enough to iterate the pipeline in hours; the 3B is the realistic v1 product. Running both through D4 baselining costs little and de-risks the choice, which is exactly the D3→D4.1 structure already accepted in `DECISIONS-v1.md` §5.

## E.2 Two-runtime split — now mandatory

| Function | Runtime | Rationale |
|---|---|---|
| **Teacher generation** | **Ollama** | Already installed, already serving all 43 models, handles GPU/CPU layer offload natively. Reaching these teachers through PyTorch would mean re-acquiring 768 GiB in a different format for no benefit. |
| **Student training** | **PyTorch + PEFT + bitsandbytes** | Only path to QLoRA |
| **Student inference / eval** | Either | Ollama after GGUF conversion; PyTorch pre-conversion |
| **Deployment artifacts** | **Ollama / llama.cpp** | Matches the harness the rest of the workspace already uses |

This was implicit in INV-4 (offline black-box distillation). Measurement makes it explicit and non-optional: teacher and student **cannot** be co-resident at 5.26 GiB, and the two runtimes never need to be loaded simultaneously.

**Architectural consequence.** The Distillery's generation stage talks to the Ollama HTTP API, not to a Python model object. That is a cleaner boundary than prior documents implied, and it means **corpus generation can begin before PyTorch is fixed** — which, given B.1, is the difference between starting this week and starting after the toolchain is resolved.

## E.3 Corpus tooling from the INFRASTRUCTURE models

The three embedding models, reclassified out of the teacher queue, become the corpus quality instruments:

| Model | Use | Addresses |
|---|---|---|
| `bge-m3` (567M, multilingual, long-context) | Primary embedding for near-duplicate detection and semantic-diversity scoring | R-3 |
| `nomic-embed-text` (0.255 GiB) | Fast first-pass dedup at scale | R-3 |
| `mxbai-embed-large` (0.624 GiB) | Independent second opinion on diversity; retrieval-correctness checks | R-3, R-7 |

**This closes a real gap.** The integrated report §38 requires diversity measurement to resist synthetic-data collapse but names no instrument. These are the instruments, they are already on disk, they are small enough to run alongside anything, and they cost nothing to adopt.

## E.4 Where EF-5 forces a change

The library is substantially synthetic-derived (R1 distills, Dolphin finetunes). Two changes follow, neither optional:

1. **`generation_depth` becomes a mandatory registry and corpus field.** A base model is depth 0; a distill of it is depth 1; Sovereign trained on that distill's output is depth 2. The field must propagate into corpus provenance so that mixing can be controlled by depth, not just by teacher identity.
2. **The non-synthetic corpus fraction moves from recommended to required, with a floor.** The integrated report §38 leaves the ratio as an empirical parameter. Given that the *teachers themselves* are synthetic-trained, a floor should be set before the first run rather than tuned after collapse is observed. The floor value is an operator decision (OQ-005 canonical numbering); the existence of a floor should not be.

---

# PART F — DESIGN PLAN

Phases replace the integrated report's D0–D15 where measurement has changed them. Each phase states entry criteria, work, exit criteria, artifacts, and the risk it retires.

**Legend:** `[BLOCKED]` cannot start · `[READY]` can start now · `[GATED]` needs an operator decision

---

## F.0 — Environment remediation `[READY]`

**Retires:** EF-4, R-8. **Duration estimate:** hours to one day, depending on how the `sm_120` question resolves.

**Entry:** none. This is the critical path.

**Work**

1. Install `psutil`; re-run `d1_characterize.py` to capture system RAM and disk. *(Assumption D in Part D depends on this.)*
2. Create an isolated Python environment for training — venv or conda. Do not install into system Python; the training stack will need to be rebuilt more than once.
3. Install PyTorch from a **CUDA 12.8-or-newer** wheel index. Blackwell consumer support has lagged across the ecosystem; the correct index and version must be confirmed against the current PyTorch installation matrix rather than taken from any document, including this one.
4. Install `transformers`, `peft`, `accelerate`, `datasets`, `trl`, `bitsandbytes`.
5. **Re-run `d1_characterize.py`.** The gate is not "PyTorch imports." The gate is: `sm_120` present in the build's arch list **and** `bitsandbytes` `Linear4bit` forward pass returns finite output on the device.
6. Close Ollama and all GPU applications; run `d1_characterize.py --vram-probe`. Record how much of the 2.70 GiB at-rest consumption is reclaimable.

**Exit criteria**

- [ ] `hardware_profile.json` shows `cuda_available: true`
- [ ] `arch_supported_by_this_torch_build: true` for `sm_120`
- [ ] `bitsandbytes.linear4bit_forward: true` and `output_finite: true`
- [ ] System RAM and free disk captured
- [ ] `vram_probe` recorded with GPU applications closed

**Failure path.** If step 5 cannot be satisfied after reasonable effort, **stop and escalate**. Do not work around it with CPU training or by deferring. A non-functional 4-bit path means OQ-006 (compute envelope) is live now, and the plan below changes shape rather than slipping.

**Artifacts:** `runs\hardware_profile.json`, `runs\ENVIRONMENT.md` (exact versions, reproducible install commands)

---

## F.1 — Generation throughput measurement `[READY]`

**Retires:** the whole of Part D's estimates. **Duration:** one day. **Runs in parallel with F.0** — needs only Ollama.

**Work**

1. Fixed benchmark prompt set — 20 prompts spanning short-answer, long-form, code, and structured output.
2. Measure single-stream tok/s via `ollama run --verbose` on: `qwen3:8b` (resident), `qwen3:14b` (boundary), `qwen3:32b` (offloaded).
3. Measure **batched** aggregate throughput via concurrent Ollama API requests at 1 / 2 / 4 / 8 concurrency. *(Highest-leverage measurement in the plan — see D.5.)*
4. Measure MoE behaviour: `qwen3:30b-a3b` vs dense `qwen3:32b`.
5. Observe RAM and swap during the 32B run.
6. Recompute the tier boundaries from measured values.

**Exit criteria**

- [ ] Measured tok/s at three model sizes, single-stream and batched
- [ ] Tier boundaries recomputed; Part C.5 reissued from measurement
- [ ] Corpus budget (DR-3) set from measured throughput rather than estimate

**Artifacts:** `runs\generation_throughput.json`, reissued `registry\teachers.md`

---

## F.2 — Registry v2 and license audit `[READY]` / `[GATED]`

**Retires:** TD-1..TD-6, EF-6 hazard, R-5.

**Work**

1. Run `d2_registry.py` v2 — corrected ordering, role classification, blob-hash dedup, `base_family` / `derived_from` / `generation_depth` fields.
2. Confirm the seven candidate duplicate pairs by blob hash; collapse true aliases.
3. Confirm the `ARTIFACT` classification of the 461M F32 entry.
4. **License audit** `[GATED]` — read the **primary** license text for each of the 39 teachers and assign `license_class`. This is manual and it is the gate on any teacher reaching `ELIGIBLE`.
5. Resolve OQ-007 (distribution intent) first — it determines whether the audit is hygiene or a hard gate.

**Exit criteria**

- [ ] Registry v2 emitted; ordering verified against Part C.3
- [ ] Duplicates confirmed or refuted by hash
- [ ] Every T1 teacher carries a `license_class` from primary text
- [ ] `base_family` populated for all same-base groups in C.6

**Note.** The audit can be **scoped to T1 first** — 5 models — so it does not block the pipeline behind 39 license reviews. T2 teachers are audited before their individual go decisions.

---

## F.3 — Seed acquisition and candidate selection `[GATED — DR-2]`

**Retires:** EF-2, OQ-001 Phase A.

**Entry:** F.0 complete (need a working training stack to baseline candidates meaningfully).

**Work**

1. **Acquire 1–3B base candidates from outside the library.** Nothing local qualifies (EF-2). Selection criteria, in priority order:
   - **Permissive license** — this is the seed; its terms propagate to the entire lineage (C-2, R-5). A restrictive seed contaminates everything downstream, permanently.
   - **Trainable at 5.26 GiB** under QLoRA with headroom
   - **Tokenizer and architecture with a credible migration path** toward the Phase-C native architecture (OQ-008)
   - **Long-context capable** enough not to cap the student below the teachers' useful output length
2. Shortlist **2–3**, do not freeze one (accepted at `DECISIONS-v1.md` §5).
3. Verify each loads and trains a trivial LoRA step on this machine.

**Exit criteria**

- [ ] 2–3 candidates acquired, licenses verified from primary text
- [ ] Each demonstrably trainable on this GPU
- [ ] Selection deferred to F.4.1

---

## F.4 — Evaluation suite `[BLOCKED on F.0]`

**Retires:** R-6, F-7. **Still the highest-value artifact in the project.**

**Entry:** F.0 complete.

**Work**

1. **Capability taxonomy** — start narrow. Five to seven capabilities the T1 teachers plausibly differ on: general reasoning, mathematics, programming, structured output, instruction adherence, summarization, tool selection. Extensible, per integrated §20.
2. **Band A — Deterministic.** Machine-checkable only: code executed against unit tests; math with exact answers; schema-validated structured extraction; programmatic constraint checks for instruction-following. No model in the loop.
3. **Band B — Regression.** Empty at v1; grows monotonically on promotion. Build the *mechanism* now; it has no content until the first promotion.
4. **Band C — Held-out.** Private, access-controlled, **never** used for prompt generation or curriculum construction (INV-7). Reserve at least 20% of authored items here.
5. **Band D — Advisory.** Debate Table hooks. Recorded, never gating.
6. **Variance establishment.** Run every candidate seed **and every T1 teacher** through Bands A and C **at least 5 times**. Compute per-capability run-to-run standard deviation.
7. **Set M, T, and D from measured variance** (OQ-004 canonical). Thresholds below the noise floor produce a gate that is either always or never passed. This step is why F.4 must precede any training.
8. **Freeze as `eval_suite_v1`.** Version it. Any change is a version bump that invalidates cross-generation comparison (INV-6).

**Exit criteria**

- [ ] Suite runs unattended against any Ollama or PyTorch model
- [ ] Baseline scores for 2–3 seed candidates and all 5 T1 teachers
- [ ] Per-capability variance measured
- [ ] M, T, D set from variance and recorded
- [ ] Suite frozen and versioned

**Artifacts:** `evals\suite_v1\`, `evals\baselines\`, `evals\variance_report.md`

### F.4.1 — Seed selection `[GATED — operator]`

Select canonical `SOV-SEED` from the F.3 shortlist using F.4 baselines. Record as an ADR with the rejected candidates and the reason. **Operator decision.**

---

## F.5 — Provenance, lineage, and run-state skeleton `[READY]`

**Retires:** R-5, R-10, IR-7. **The phase that cannot be retrofitted.**

**Work**

1. Implement the schemas in Part G: corpus shard, provenance record, lineage record, capability ledger, run state.
2. Implement and **test** the exclusion query — *"rebuild this lineage excluding teacher X"* — against synthetic data, before any real corpus exists.
3. Implement resumability: checkpoint boundaries, resume pointer, run-state persistence (integrated §57, §59).
4. Retention policy (R-10): what is kept forever, what is cold-stored, what is disposable. **768 GiB of teachers is already on disk before a single corpus exists.**
5. `distillery_memory\` — the Knowledge Lineage as a **structured experiment database**, owned by the Distillery, per `DECISIONS-v1.md` §5.

**Exit criteria**

- [ ] Exclusion query verified on synthetic data
- [ ] A run interrupted mid-stage resumes without repeating completed stages
- [ ] Retention policy written with numbers in it
- [ ] Every schema in Part G implemented and round-trip tested

---

## F.6 — Dataset factory `[BLOCKED on F.1, F.2, F.5]`

**Retires:** R-2, R-3, R-7.

**Work**

1. Curriculum builder — prompt sets targeting specific capability deltas.
2. Generation driver against the **Ollama API**, with provenance stamped per example at creation (INV-2), batched per F.1's findings.
3. **Validation gate** per data type (integrated §35): code executed against tests; math deterministically re-checked; structured output schema-validated; format constraints programmatically checked; factual claims requiring multi-teacher agreement or being dropped.
4. **Deduplication and diversity scoring** using the E.3 embedding models.
5. Decontamination against the held-out band (INV-7, R-7).
6. Immutable shard sealing with content hash and manifest.
7. **Rejection-rate tracking per teacher** — itself a finding (integrated §39).

**Exit criteria**

- [ ] One T1 teacher produces a sealed, validated, provenance-complete shard
- [ ] Rejection rate reported per teacher
- [ ] Diversity score computed and recorded
- [ ] Decontamination verified against the held-out set

---

## F.7 — Training prototype `[BLOCKED on F.0, F.4.1, F.6]`

**Retires:** the remaining hardware unknowns.

**Work**

1. QLoRA fine-tune `SOV-SEED` on one shard → `SOV-D001-CANDIDATE`.
2. Record measured peak VRAM, wall clock, throughput, loss curve into `distillery_memory\`.
3. Verify reproducibility — same config and seed, same result.
4. Emit lineage record.

**Exit criteria**

- [ ] A candidate checkpoint exists, reproducibly
- [ ] Measured training envelope recorded — **this finally replaces every VRAM estimate in the project**
- [ ] Lineage record complete and valid

---

## F.8 — Evaluation, regression, and promotion `[BLOCKED on F.7]`

**Work**

1. Run candidate through Bands A, B, C.
2. Compute capability deltas vs. parent and vs. teacher.
3. Apply the promotion gate of Part G.5 — margin **M**, step tolerance **T**, drift floor **D**, criticality check.
4. Update the Capability Ledger.
5. Present the evidence package to the operator. **Promotion is a human decision** (INV-15).
6. On promotion: add regression items for newly demonstrated capabilities (integrated §25).

**Exit criteria**

- [ ] Candidate is evidence-backed `PROMOTABLE` or `REJECTED`
- [ ] Ledger updated; regression band grown if promoted
- [ ] Operator decision recorded in lineage

---

## F.9 — Route B closure `[BLOCKED on F.8]`

Complete the Route B chain end to end on one T1 teacher, including deployment-artifact production and a demonstrated mid-run interruption and resume. **This closes Distillery v1.** Acceptance in Part K.

---

## F.10 — T1 sequence `[BLOCKED on F.9]`

Process the remaining four T1 teachers. Watch: capability gains, regression deltas, rejection rates, diversity scores, wall clock, disk growth. Every run writes to `distillery_memory\`.

**This is the first point at which the smallest-to-largest hypothesis (HYP-1) becomes testable** — five teachers is a small but non-zero sample.

---

## F.11 — T2 selective processing `[GATED — per teacher]`

Each T2 teacher requires a demonstrated capability delta **and** an explicit operator go before its generation run starts. At 5–21 days of continuous generation each, these are commitments, not queue items.

---

## F.12 — Compute envelope decision `[GATED — OQ-006]`

Bring T3/T4 to the operator with measured numbers rather than estimates: 18 teachers, ~470 GiB, measured throughput, measured value of the deltas obtained from T1/T2. **Decide, do not drift.**

---

## F.13 — Continual-learning optimization

Replay ratios, non-synthetic floor, adapter strategies, curriculum sizing. Tests HYP-3. Requires several completed cycles.

## F.14 — Workspace integration `[BLOCKED on OQ-009]`

Sovereign, Multi-Model App, Debate Table. **Still blocked — no repository has been inspected.** Distillery must remain standalone (INV-14).

## F.15 — Native architecture research `[Phase C]`

OQ-008. Triggered by demonstrated pipeline maturity, not by enthusiasm.

---

## F.16 — Critical path

```
F.0 environment ──┬─→ F.4 evaluation ──→ F.4.1 seed selection ──┐
                  │                                             │
F.1 throughput ───┼─→ F.2 registry v2 ──┐                       │
                  │                     │                       │
F.3 seed acquire ─┘                     ├─→ F.6 dataset ──→ F.7 train ──→ F.8 eval ──→ F.9 v1
                                        │
F.5 provenance ─────────────────────────┘
```

**F.0, F.1, F.2, and F.5 can all start now.** F.1 and F.2 need only Ollama; F.5 is pure schema and code with no model dependency. F.0 is the critical path because F.4 and everything after it depend on it.

**Estimated elapsed time to F.9 (Route B closure), assuming F.0 resolves without a toolchain crisis and a 2M-token corpus budget:** three to five weeks, dominated by F.4 (evaluation suite construction) rather than by compute. `ESTIMATE`, moderate confidence, and it collapses entirely if `sm_120` support proves unavailable.

---

# PART G — SPECIFICATIONS

Concrete schemas. These are implementable as written.

## G.1 Teacher registry v2

```jsonc
{
  "model_id": "T001",
  "display_name": "qwen3:8b",
  "source_runtime": "ollama",
  "path": "…/blobs/sha256-…",
  "content_hash": "sha256:…",          // dedup key — NOT the path (TD-4)

  "role": "TEACHER",                    // TEACHER | INFRASTRUCTURE | ARTIFACT | INELIGIBLE
  "role_rationale": "",

  "architecture": "qwen3",
  "parameter_count": 8190735360,
  "parameter_basis": "declared",        // declared | label_parsed | size_derived
  "label_consistent": true,             // false ⇒ declared value rejected (TD-6)
  "is_moe": false,
  "active_parameter_count": null,
  "quantization": "Q4_K_M",
  "tokenizer": "gpt2",
  "context_length": 32768,
  "disk_size_bytes": 5225578496,

  // EF-5 / EF-6 — mandatory, not optional
  "base_family": "qwen3-8b",
  "derived_from": null,                 // e.g. "qwen3:8b" for deepseek-r1:8b
  "generation_depth": 0,                // 0 = base; 1 = distill of a base; …

  // Never inferred from family name (F-6)
  "license_identifier": "apache-2.0",
  "license_source": "primary_text",     // primary_text | gguf_declared | UNKNOWN
  "license_class": "PERMISSIVE",
  "license_verified_by": "operator",
  "license_verified_at": "2026-08-…",

  // Part C/D
  "tier": "T1-VIABLE",
  "measured_tok_per_sec": null,         // null until F.1
  "estimated_tok_per_sec": 53.0,
  "queue_position": 3,

  "disposition": "PENDING",             // integrated §—Teacher Disposition State
  "disposition_history": []
}
```

**Disposition values** (operator extension, `DECISIONS-v1.md` §5): `PENDING · ELIGIBLE · SKIPPED_NO_DELTA · DISTILLING · PROMOTED · REJECTED · QUARANTINED_TECHNICAL · QUARANTINED_DATA · QUARANTINED_LICENSE · DEFERRED_COMPUTE · SUPERSEDED`

**Rule:** no teacher reaches `ELIGIBLE` while `license_source != "primary_text"`.

## G.2 Corpus example provenance

Stamped at generation. Never reconstructed (INV-2).

```jsonc
{
  "example_id": "uuid",
  "corpus_shard_id": "SHARD-T003-R001",
  "content_hash": "sha256:…",

  "teacher_id": "T003",
  "teacher_content_hash": "sha256:…",
  "teacher_quantization": "Q4_K_M",
  "teacher_license_class": "PERMISSIVE",
  "teacher_generation_depth": 0,
  "example_generation_depth": 1,        // teacher depth + 1 (EF-5)

  "generation_run_id": "RUN-…",
  "curriculum_id": "CUR-math-001",
  "capability_target": "mathematics",
  "prompt_id": "P-000412",
  "prompt_source": "authored",          // authored | template | seeded — never held-out (INV-7)
  "prompt": "…",
  "response": "…",
  "generation_parameters": { "temperature": 0.7, "top_p": 0.95, "seed": 41, "max_tokens": 2048 },

  "validation_method": "deterministic_math_check",
  "validation_result": "PASS",
  "quality_score": 0.94,
  "dedup_cluster_id": "C-0912",
  "embedding_model": "bge-m3",
  "decontamination_checked_against": "eval_suite_v1/heldout",

  "created_at": "2026-…"
}
```

## G.3 Capability ledger

Extends integrated §21 with the three fields RD-1 and RD-3 require.

```jsonc
{
  "capability": "tool_use",
  "criticality": "CRITICAL",            // CRITICAL | STANDARD | EXPERIMENTAL   (RD-3)
  "current_score": 95,
  "historical_best": 96,
  "historical_best_checkpoint": "SOV-D009",
  "governed_floor": 96,                 // (RD-1) moves ONLY by recorded operator override
  "governed_floor_set_by": "initial",
  "governed_floor_rationale": null,
  "measurement_variance": 1.8,          // from F.4 step 6
  "source_teacher": "T009",
  "trend": "REGRESSION",
  "regression_items": ["REG-tooluse-001", "REG-tooluse-002"]
}
```

## G.4 Lineage record

Per integrated §14, plus the fields the gate needs.

```jsonc
{
  "checkpoint_id": "SOV-D017",
  "parent_checkpoint": "SOV-D016",
  "teacher_models": ["T012"],
  "corpus_manifest_hash": "sha256:…",
  "corpus_mix": { "new_teacher": 0.45, "replay": 0.35, "non_synthetic": 0.20 },
  "training_config_hash": "sha256:…",
  "architecture": "…", "parameter_count": 3085938688,
  "precision": "4bit-nf4", "tokenizer": "…",
  "eval_suite_version": "v1",
  "pre_scores": {}, "post_scores": {}, "regression_results": {},
  "capabilities_gained": [], "capabilities_lost": [],
  "licenses_in_lineage": ["PERMISSIVE"],
  "max_generation_depth_in_corpus": 2,
  "hardware_profile_hash": "sha256:…",
  "wall_clock_hours": 6.4,
  "gate_result": { "M": true, "T": true, "D": false, "criticality": true },
  "override": {
    "applied": true,
    "capability": "tool_use",
    "old_governed_floor": 96,
    "new_governed_floor": 93,
    "rationale": "Deliberate trade for +14 mathematics.",
    "operator": "sam",
    "at": "2026-…"
  },
  "promotion_decision": "PROMOTED",
  "operator_acceptance": { "operator": "sam", "at": "2026-…" }
}
```

## G.5 Promotion gate — with RD-1 through RD-4 resolved

```python
def evaluate_gate(candidate, parent, ledger, cfg, route):
    """
    cfg.M  required improvement margin on a target capability
    cfg.T  max permitted regression vs PARENT            (step tolerance)
    cfg.D  max permitted regression vs GOVERNED FLOOR    (drift floor)

    All three MUST exceed the measured run-to-run variance for the
    capability in question, or the gate is not discriminating (F.4 step 7).
    """
    r = {"M": False, "T": True, "D": True,
         "criticality": True, "breaches": [], "requires_override": False}

    # ---- Condition 1 — purpose of the run ---------------------------------
    # RD-2: a REMEDIATION candidate exists to RESTORE, not to gain. It passes
    # on movement back toward the governed floor, not on a new capability gain.
    if route == "REMEDIATION":
        tgt = candidate.remediation_target
        recovered = candidate.score(tgt) - parent.score(tgt)
        gap_before = ledger[tgt].governed_floor - parent.score(tgt)
        r["M"] = recovered > 0 and recovered >= min(cfg.M, gap_before * 0.5)
    else:
        r["M"] = any(candidate.score(c) - parent.score(c) >= cfg.M
                     for c in candidate.target_capabilities)

    # ---- Conditions 2, 3, 4 — protection ----------------------------------
    for cap in ledger:
        s = candidate.score(cap)

        # Step regression vs immediate parent
        if s - parent.score(cap) < -cfg.T:
            r["T"] = False
            r["breaches"].append((cap, "T", parent.score(cap) - s))

        # RD-1: drift measured against the GOVERNED FLOOR, not historical best.
        # Historical best is retained for reporting but does not gate, or the
        # first accepted trade turns D into a permanent alarm.
        if s - ledger[cap].governed_floor < -cfg.D:
            r["D"] = False
            r["requires_override"] = True
            r["breaches"].append((cap, "D", ledger[cap].governed_floor - s))

        # RD-3: "critical" is now a declared property, so this is checkable.
        if ledger[cap].criticality == "CRITICAL":
            if s - parent.score(cap) < -max(cfg.T * 0.5, ledger[cap].measurement_variance):
                r["criticality"] = False
                r["breaches"].append((cap, "CRITICAL", parent.score(cap) - s))

    r["promotable"] = (r["M"] and r["T"] and r["D"] and r["criticality"]
                       and candidate.lineage_valid and candidate.provenance_complete)
    return r


def apply_override(result, ledger, capability, rationale, operator):
    """
    RD-1. An override does two things, and the second is the point:
      1. permits this promotion despite the D breach
      2. RE-BASELINES the governed floor, so D keeps discriminating afterwards
    Historical best is NOT modified — it remains the honest high-water mark.
    """
    old = ledger[capability].governed_floor
    ledger[capability].governed_floor = result.candidate_score(capability)
    ledger[capability].governed_floor_set_by = operator
    ledger[capability].governed_floor_rationale = rationale
    return {"applied": True, "capability": capability,
            "old_governed_floor": old,
            "new_governed_floor": ledger[capability].governed_floor,
            "rationale": rationale, "operator": operator}
```

**Design note on RD-1.** Historical best and governed floor are deliberately separate. Historical best is a fact and never moves down — it is what the ledger reports so erosion stays visible. The governed floor is a *decision* and moves only when a human records why. Cumulative drift is therefore always visible in the gap between them, while the gate keeps discriminating. Without this split, `D` fires forever after the first legitimate trade, and a gate that always fires is a gate that gets disabled.

## G.6 Run state — resumability

Per integrated §57 / §59.

```jsonc
{
  "run_id": "RUN-T003-001",
  "teacher_id": "T003",
  "parent_checkpoint": "SOV-D000",
  "candidate_checkpoint": null,
  "route": "B",
  "current_stage": "GENERATE",
  "stage_status": "RUNNING",
  "last_successful_boundary": "CURRICULUM",
  "stage_artifacts": { "CURRICULUM": "curricula/CUR-math-001.json" },
  "generation_progress": { "target_tokens": 2000000, "generated_tokens": 743122,
                           "last_prompt_id": "P-000412", "shard_partial": "…" },
  "retry_counts": { "GENERATE": 1 },
  "budgets": {                          // integrated §—stop policy
    "retry_budget_per_stage": 3,
    "retry_budget_per_teacher": 8,
    "maximum_remediation_cycles": 2,
    "consecutive_skip_threshold": 3,
    "consecutive_rejection_threshold": 2,
    "stall_timeout_hours": 48
  },
  "operator_escalation_required": false,
  "resume_pointer": { "stage": "GENERATE", "offset": 743122 }
}
```

**Checkpoint boundaries** (resume without repeating): after ingestion · after each generation batch · after each validation batch · at shard sealing · at each training checkpoint interval · after each evaluation band · after quantization · at artifact packaging.

---

# PART H — OPERATIONS

## H.1 Directory layout

```
D:\Sovereign Distillery\
├── docs\                    specifications, reviews, decisions
├── tools\                   pipeline code
├── registry\                teachers.json, license audit
├── evals\
│   ├── suite_v1\            frozen, versioned
│   ├── heldout\             ACCESS-CONTROLLED — never used for generation (INV-7)
│   ├── baselines\
│   └── variance_report.md
├── curricula\
├── corpora\
│   ├── shards\              immutable, sealed
│   └── manifests\
├── runs\                    run state, logs, hardware & throughput profiles
├── checkpoints\
│   ├── seeds\  promoted\  candidates\  quarantine\
├── lineage\
├── deploy\                  quantized artifacts — never parents (INV-5)
├── experiments\
└── distillery_memory\       Knowledge Lineage — Distillery-owned (IR-7)
```

## H.2 Storage budget

| Item | Size | Note |
|---|---:|---|
| Teacher weights (existing) | **768.4 GiB** | `MEASURED`. Of which ~470 GiB is T3/T4 — unusable on current hardware (DR-5) |
| Corpora, T1 @ 2M tokens ×5 | ~2–5 GiB | Text plus provenance |
| Corpora, T1 @ 8M tokens ×5 | ~8–20 GiB | |
| Checkpoints — LoRA adapters | ~0.1–0.5 GiB each | Cheap; keep all |
| Checkpoints — merged 3B fp16 | ~6 GiB each | Expensive; keep promoted only |
| Deployment artifacts | ~2 GiB each | Regenerable from a promoted master |
| Eval suite + baselines | < 1 GiB | |

**Retention policy — recommendation, requires operator ruling**

| Class | Policy |
|---|---|
| LoRA adapters, all candidates | Keep indefinitely. Small, and they *are* the lineage. |
| Merged weights, promoted only | Keep. Merged weights of rejected candidates: delete after 30 days; the adapter plus config reproduces them. |
| Corpus shards | Keep indefinitely. Immutable, and the exclusion query (F.5) depends on them. |
| Deployment artifacts | Regenerable. Keep only the current release per target. |
| T3/T4 teacher weights | **DR-5.** ~470 GiB. Cold-store or retain. |

## H.3 Runbooks required before F.9

`RB-01` Environment rebuild from `ENVIRONMENT.md` · `RB-02` Generation run start / monitor / resume · `RB-03` Interrupted-run recovery · `RB-04` Candidate evaluation and evidence package · `RB-05` Promotion or rejection with lineage recording · `RB-06` Governed-floor override procedure · `RB-07` Rebuild-lineage-excluding-teacher · `RB-08` Quantization and artifact release

## H.4 Failure modes

| Mode | Detection | Response |
|---|---|---|
| Generation stalls | No token progress within `stall_timeout_hours` | Kill, resume from `resume_pointer`, increment retry |
| Teacher exhausts retry budget | `retry_counts` vs budgets | `QUARANTINED_TECHNICAL`; record in `distillery_memory`; advance queue |
| High rejection rate from filter | Per-teacher rejection rate | Finding in its own right (integrated §39). Investigate before training on the shard. |
| Regression detected post-promotion | Regression band on a later candidate | Bisect the lineage; parent checkpoints are intact (INV-1) |
| License problem discovered late | Audit or external notice | `RB-07` — rebuild excluding the teacher. **Only works if F.5 was done first.** |
| Disk exhaustion | Free-space monitor | Retention policy; cold-store T3/T4 |
| `sm_120` regression after an update | `d1_characterize.py` in CI | Pin versions in `ENVIRONMENT.md`; never update the training stack mid-lineage |

---

# PART I — RISK REGISTER

Severities revised against measurement. Changes from the prior register are marked.

| ID | Risk | Sev | Likelihood | Change | Mitigation | Phase |
|---|---|---|---|---|---|---|
| **R-8** | `sm_120` / bitsandbytes toolchain unavailable for this GPU | **CRITICAL** | **Unknown** | **↑↑ from Medium.** Now the single largest unknown. PyTorch absent, so it has never been tested. If it fails, local training is impossible and OQ-006 becomes immediate. | F.0 gate; escalate on failure | F.0 |
| **R-9** | Wall-clock infeasibility of generation | **HIGH** | **HIGH** | **↑ from Medium-High, and now quantified.** 18 of 39 teachers estimated at 22–170 days each. | Tiering (C.5); measured throughput; batching; corpus budget | F.1, D.3 |
| **R-3** | Synthetic-data collapse / diversity narrowing | **HIGH** | **HIGH** | **↑ from Medium-High.** EF-5: the teachers are themselves synthetic-derived. Sovereign becomes 3rd-generation for that material. | `generation_depth` tracking; non-synthetic floor; embedding-based diversity scoring (E.3) | F.5, F.6 |
| **R-4** | Student capacity ceiling | **HIGH** | **CERTAIN** | **↑ context.** Every teacher is 3–40× the student; nothing below 8B exists (EF-1). | Targeted per-capability transfer; per-capability bars; never "match the teacher" | F.4, F.8 |
| **R-1** | Catastrophic forgetting | HIGH | HIGH | — | Replay mixing; regression band; **governed floor `D`** (G.5) | F.5, F.8 |
| **R-2** | Teacher-error amplification | HIGH | HIGH | — | Deterministic validation gate (F.6); per-teacher rejection rate | F.6 |
| **R-5** | License contamination of the lineage | HIGH | Medium | — | Per-example provenance; primary-text audit; exclusion query tested before real data | F.2, F.5 |
| **R-10** | Storage exhaustion | **HIGH** | **Medium-High** | **↑ from Medium, quantified.** 768 GiB consumed before a single corpus exists. | Retention policy with numbers; DR-5 on the ~470 GiB of T3/T4 | H.2 |
| **R-6** | False improvement / promotion gate ineffective | HIGH | Medium | ↓ from High likelihood — the gate is now specified with M/T/D and criticality | Variance-derived thresholds (F.4 step 7) | F.4, F.8 |
| **R-7** | Evaluation contamination | Medium | Medium | — | Held-out band never used for generation; decontamination pass | F.4, F.6 |
| **R-11** | Scope drift | Medium | **Low** | **↓ from High.** Route A/B acceptance and tiering give the project a terminal state. | Part K | — |
| **R-12** | **Seed licence propagates to the entire lineage** | **HIGH** | Medium | **NEW.** The seed's terms bind every downstream checkpoint permanently (C-2, EF-2). A restrictive seed cannot be corrected later. | Permissive-first selection criteria (F.3); primary-text verification before use | F.3 |
| **R-13** | **Same-base teachers produce correlated, non-independent measurements** | Medium | **HIGH** | **NEW (EF-6).** Six same-base groups identified. Deltas across a group measure the distillation, not two teachers. | `base_family` / `derived_from` fields; treat groups as one source for diversity accounting | F.2 |
| **R-14** | **System RAM insufficient for offloaded teachers** | **HIGH** | **Unknown** | **NEW.** RAM was not captured. A 75 GiB model that exceeds RAM does not run slowly — it does not run. | Capture RAM in F.0; observe during a T3 load in F.1 | F.0, F.1 |
| **R-15** | **Reclaimable VRAM never measured** | Low | High | **NEW.** 2.70 GiB consumed at rest; `--vram-probe` never executed (torch absent). Could widen or confirm the envelope. | Re-run with GPU apps closed | F.0 |

---

# PART J — DECISIONS AND OPEN ITEMS

## J.1 Decisions requested now

| ID | Decision | Recommendation | Consequence of deferring |
|---|---|---|---|
| **DR-1** | Adopt tiering (T1/T2/T3/T4) as the operative queue | **Adopt.** | Planning continues around 18 teachers this machine cannot run |
| **DR-2** | Approve acquiring 1–3B seed candidates from outside the library | **Approve.** Nothing local qualifies. | F.3 and everything after it stay blocked |
| **DR-3** | Corpus token budget per teacher | **2M for T1**, revisit after F.1 measures throughput | Every schedule number is unanchored |
| **DR-4** | Confirm two-runtime split (Ollama generate / PyTorch train) | **Confirm.** | F.0 scope is undefined |
| **DR-5** | T3/T4 — deferred-pending-compute, or removed | **Defer, cold-store.** | ~470 GiB held with no policy |
| **DR-6** | Non-synthetic corpus floor — set a value | Set one before the first run; tune later | EF-5 makes R-3 near-certain without it |

## J.2 Open questions — status

Canonical numbering per `DECISIONS-v1.md` §3.

| ID | Question | Status |
|---|---|---|
| **OQ-001** | SOV-SEED | **Phase A resolved** (bootstrap from permissive base). **Candidate selection newly blocked** by EF-2 — nothing local. → F.3, F.4.1 |
| **OQ-002** | Teacher inventory | **CLOSED.** 43 entries, 39 teachers, 768.4 GiB. Corrected ordering in C.3. *The hard blocker of every prior document is retired.* |
| **OQ-003** | v1 acceptance | **CLOSED.** Route A / Route B, RD-4 applied. Part K. |
| **OQ-004** | Promotion thresholds M / T / **D** | Open — **derive from measured variance**, F.4 step 7 |
| **OQ-005** | Training-mix ratios | Open — floor required before first run (DR-6) |
| **OQ-006** | Long-term compute envelope | **Sharpened.** Now concrete: 18 teachers, ~470 GiB, measured infeasibility. → F.12 |
| **OQ-007** | Distribution intent | Open — **gates the license audit's severity**. Answer before F.2 step 4. |
| **OQ-008** | Native architecture timing | Open — Phase C |
| **OQ-009** | Workspace interface contracts | **Open. Unchanged. No repository has been inspected.** Paths still not supplied. |
| **OQ-010** | Smallest-to-largest rationale | **RESOLVED** → HYP-1. Now justified as **generation-cost ordering** (EF-3), which is stronger than the risk-ordering argument it replaces. |

## J.3 Residual defects — status

| ID | Item | Status |
|---|---|---|
| RD-1 | Governed floor vs. historical best | **Resolved** — G.3, G.5 |
| RD-2 | Remediation route | **Resolved** — G.5 |
| RD-3 | "Critical" definition | **Resolved** — criticality tag, G.3, G.5 |
| RD-4 | Route B reject/artifact conflict | **Resolved** — Part K |
| TD-1..TD-6 | Reviewer's tooling defects | Corrected queue in C.3; v2 tooling shipped |

## J.4 Hypotheses

| ID | Hypothesis | First testable at |
|---|---|---|
| HYP-1 | Smallest-to-largest improves final quality | F.10 — five T1 teachers |
| HYP-2 | Differential targeted distillation beats wholesale imitation | F.11 |
| HYP-3 | Cumulative replay preserves prior capability | F.13 |
| HYP-4 | Bootstrap lineage transfers to a native architecture | Phase C |
| HYP-5 | Specialized models beat one general model per role | Post-v1 |
| HYP-6 | Distillery history predicts better strategies | **Gated** — needs matched trials; n≈5 at F.10 is far short |

---

# PART K — ACCEPTANCE CRITERIA

Per operator ruling, RD-4 applied.

## Route A — Pipeline / decision proof

1. Teacher ingested and registered with content hash and verified `license_class`
2. Teacher characterized on frozen `eval_suite_v1`
3. Current Sovereign checkpoint characterized on the same suite
4. Capability delta computed and recorded
5. A **correct** disposition reached — `SKIPPED_NO_DELTA` or `ELIGIBLE` — with the evidence recorded
6. Provenance and lineage record written and valid
7. Run interrupted mid-stage and resumed without repeating completed stages

**= valid intermediate milestone. ≠ Distillery v1 complete.**

## Route B — Transfer proof — **required for v1**

1. Teacher ingested, registered, license-verified
2. Teacher characterized
3. Useful capability delta identified against the current checkpoint
4. Curriculum constructed targeting **only** the delta
5. Corpus generated with per-example provenance at creation
6. Corpus validated; rejection rate recorded; diversity scored; decontaminated against held-out
7. Corpus mixed per policy — new / replay / non-synthetic — and sealed immutably
8. Candidate trained reproducibly; measured envelope recorded
9. Candidate evaluated on Bands A, B, C
10. Regression measured across the full regression band
11. **Gate passes M, T, D, and criticality** (G.5)
12. **Candidate PROMOTED** by operator decision — *(RD-4: promotion required. A correct rejection proves the training and evaluation machinery but does not close v1.)*
13. Lineage record complete, valid, and reproducible
14. Deployment artifact produced and running under the Sovereign harness
15. Run interrupted and resumed successfully at least once

**All fifteen ⇒ Distillery v1 exists as a functioning system.**

## Definition of success at scale

Unchanged from the integrated report §103, and still the right formulation:

> This teacher possessed capability X. Sovereign previously lacked or underperformed X. The Distillery extracted valid training signal. The new checkpoint measurably improved X. Prior capabilities remained within `T` of the parent and within `D` of the governed floor. The whole process is reproducible and attributable.

---

# APPENDIX A — Measured library, as reported

43 entries · 768.4 GiB · captured 2026-08-19 by `tools\d2_registry.py`. **Queue positions in this table are the v1 tool's output and are known to be wrong (TD-1); the corrected order is Part C.3.**

| v1 pos | Model | Label | Quant | GiB |
|---:|---|---:|---|---:|
| 1 | magistral:latest | 23.6B | Q4_K_M | 13.349 |
| 2 | devstral-small-2:latest | 24B | Q4_K_M | 14.135 |
| 3 | mistral-small3.2:latest | 24B | Q4_K_M | 14.135 |
| 4 | gemma4:26b | 25.8B | Q4_K_M | 16.752 |
| 5 | medgemma:27b | 27.4B | Q4_K_M | 16.202 |
| 6 | qwen3.6:27b | 27.8B | Q4_K_M | 16.224 |
| 7 | glm-4.7-flash:latest | 29.9B | Q4_K_M | 17.713 |
| 8 | qwen3:30b-a3b | 30.5B | Q4_K_M | 17.282 |
| 9 | qwen3-coder:30b | 30.5B | Q4_K_M | 17.282 |
| 10 | gemma4:31b | 31.3B | Q4_K_M | 18.504 |
| 11 | qwen3.6:35b | 36B | Q4_K_M | 22.294 |
| 12 | mistral-medium-3.5:latest | 127.7B | Q4_K_M | 74.731 |
| 13 | nomic-embed-text:latest | ? | F16 | 0.255 |
| 14 | mxbai-embed-large:latest | ? | F16 | 0.624 |
| 15 | bge-m3:latest | 567M | F16 | 1.078 |
| 16 | DavidAU/Qwen3.6-27B-Fable-Fusion-711-Unc | 461M | F32 | 1.716 |
| 17 | dolphin-llama3:8b | ? | Q4_0 | 4.341 |
| 18 | dolphin3:8b | 8B | Q4_K_M | 4.583 |
| 19 | deepseek-r1:8b | 8B | Q4_K_M | 4.867 |
| 20 | qwen3:8b | 8B | Q4_K_M | 4.867 |
| 21 | gemma4:12b | 12B | Q4_K_M | 6.874 |
| 22 | deepseek-r1:14b | 14B | Q4_K_M | 8.371 |
| 23 | qwen2.5:14b-instruct | 14B | Q4_K_M | 8.371 |
| 24 | phi4:14b | 15B | Q4_K_M | 8.431 |
| 25 | qwen3:14b | 14B | Q4_K_M | 8.639 |
| 26 | qwen3.6-fable-iq2:latest | 27B | IQ2_M | 10.872 |
| 27 | DavidAU/Qwen3.6-27B-Fable-Fusion-711-Unc | 27B | IQ2_M | 10.872 |
| 28 | codestral:latest | ? | Q4_0 | 11.706 |
| 29 | gpt-oss:20b | ? | ftype_4 | 12.846 |
| 30 | qwen3.8:27b | 27B | Q4_K_M | 15.656 |
| 31 | Qwen3.8-27B-Uncensored:latest | 27B | Q4_K_M | 15.656 |
| 32 | granite4.1:30b | 30B | Q4_K_M | 16.289 |
| 33 | THUDM_GLM-4-32B-0414-GGUF:Q4_K_M | 32B | Q4_K_M | 18.328 |
| 34 | deepseek-r1:32b | 32B | Q4_K_M | 18.488 |
| 35 | GLM-4-32B-0414-GGUF:UD-Q4_K_XL | 32B | Q4_K_M | 18.551 |
| 36 | qwen3:32b | 32B | Q4_K_M | 18.814 |
| 37 | laguna-xs-2.1:latest | 256x2.2B | Q4_K_M | 18.882 |
| 38 | ornith:35b | 35B | Q4_K_M | 19.713 |
| 39 | dolphin-llama3:70b | ? | Q4_0 | 37.225 |
| 40 | deepseek-r1:70b | 70B | Q4_K_M | 39.600 |
| 41 | llama3.3:70b | 70B | Q4_K_M | 39.600 |
| 42 | gpt-oss:120b | ? | ftype_4 | 60.880 |
| 43 | llama4:scout | ? | Q4_K_M | 62.805 |

# APPENDIX B — Evidence log

| ID | Claim | Source | Label |
|---|---|---|---|
| M-1 | RTX 5060 Ti, 8151 MiB nominal, 5383 MiB free, cc 12.0, driver 610.74 | `d1_characterize.py`, operator's machine | `MEASURED` |
| M-2 | PyTorch, bitsandbytes, psutil absent | same | `MEASURED` |
| M-3 | 43 registry entries, 768.4 GiB, 8B–128B | `d2_registry.py`, operator's machine | `MEASURED` |
| M-4 | Smallest generative model 8B / 4.34 GiB | derived from M-3 | `DERIVED` |
| M-5 | 2768 MiB consumed at rest | 8151 − 5383 | `DERIVED` |
| M-6 | Bits-per-weight calibration within ~5% across Q4_K_M, Q4_0, IQ2_M | cross-check of declared vs size-derived on 4 known entries | `DERIVED` |
| E-6/E-7 | QLoRA VRAM by model size | Spheron (secondary, modelled) | `ESTIMATE` |
| E-9/E-10 | Cross-tokenizer KD maturity; 49.0% vs 74.6% distillation gap | arXiv 2503.20083v2 | `FACT` (primary) |
| E-12 | `sm_120` stable-channel PyTorch support has lagged CUDA's own support; ecosystem libraries lag further | pytorch/pytorch#164342 and PyTorch forum threads — **dated relative to Aug 2026** | `ESTIMATE`, low confidence. **Resolved empirically by F.0, not by citation.** |
| D-1 | Throughput model and tier boundaries | Part D.2, calibrated heuristic | `ESTIMATE` — replaced by F.1 |

# APPENDIX C — Terminology added by this report

| Term | Definition |
|---|---|
| **Tier (T1–T4)** | Teacher classification by estimated corpus-generation feasibility on the measured hardware |
| **Generation feasibility frontier** | The model size above which corpus generation ceases to be schedulable on this machine — measured proxy: resident VRAM capacity |
| **Governed floor** | Per-capability regression floor that moves only by recorded operator override. Distinct from historical best, which never moves down (RD-1) |
| **Generation depth** | Distance in synthetic-derivation hops from a non-synthetic base. Base = 0; distill of a base = 1; Sovereign trained on that distill = 2 (EF-5) |
| **Base family** | Group of models sharing a base checkpoint. Enables same-family merging; forbids treating members as independent teachers (EF-6) |
| **Role** | `TEACHER` / `INFRASTRUCTURE` / `ARTIFACT` / `INELIGIBLE` — registry classification preceding tiering (TD-2) |
| **Two-runtime split** | Ollama for teacher generation, PyTorch for student training. Mandatory at 5.26 GiB (E.2) |

---

## Closing position

The two measurements did what measurements do: they retired the project's oldest blocker and replaced it with sharper, smaller, more tractable ones.

**OQ-002 is closed.** The library is enumerated — 43 entries, 39 teachers, 768.4 GiB. Every prior document in this workspace was written around a blank where that inventory should have been.

**What the inventory reveals is harder than what it replaced.** The library was assembled for inference and orchestration. It is being asked to serve as distillation source material for a small student on a small card. Those are different optimization targets, and the mismatch produces EF-1 through EF-3: there is no teacher below the student, no seed candidate at all, and roughly half the library cannot be run at corpus scale on this machine.

None of that is a reason to change the architecture. The integrated design absorbs all of it. **It is a reason to change the plan** — from "process the library smallest to largest" to "process five viable teachers, prove Route B, and make the compute question a decision rather than a discovery."

**The largest remaining unknown is no longer conceptual.** It is whether `bitsandbytes` executes a 4-bit forward pass on `sm_120` on this specific card. That question has never been asked, because the software needed to ask it is not installed. It is a one-day task and everything downstream depends on the answer.

*This is a plan and a report. It is not an approval. Acceptance belongs to the operator.*
