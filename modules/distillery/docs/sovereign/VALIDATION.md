# Sovereign Distillery — Complete Validation & Specification Report

| | |
|---|---|
| **Document** | Consolidated report v1.0 |
| **Date** | 19 August 2026 |
| **Workspace** | `D:\Sovereign Distillery` |
| **Subject** | The Sovereign Distillery — proposed fourth subsystem of the Sovereign Research Workspace |
| **Author role** | Research Validator / Analyst / Reviewer |
| **Authority** | **The human operator owns objectives, scope, promotions, strategic direction, and final acceptance.** This report verifies, challenges, and proposes. It does not decide, and it does not approve. |
| **Status** | Review complete. Specification **provisional**, blocked on three operator decisions. No pipeline code exists. |

---

## Evidence conventions used throughout

Every substantive claim in this report carries one of the following labels. Claims without a label are structural or definitional.

| Label | Meaning |
|---|---|
| `FACT` | Verified against a cited source, or directly observed on the operator's machine |
| `ASSUMPTION` | Taken as given, not verified, and load-bearing |
| `INTERPRETATION` | The reviewer's reading of intent or implication |
| `SPECULATION` | Plausible but unsupported; must not be treated as established |
| `UNVERIFIED` | Asserted in source material; no evidence located either for or against |

Confidence in secondary sources is stated explicitly. Where a number is modelled rather than measured, the report says so every time it is used.

---

# Executive Summary

## What was asked

The operator directed that a fourth subsystem — the **Sovereign Distillery** — be added to the Sovereign Research Workspace, alongside Sovereign, the Debate Table, and the Multi-Model App. Its stated purpose: process the local model library from smallest to largest, treating each model as a source, extract what is useful from it, and use that material to train a persistent Sovereign model that improves with each stage, ultimately producing a Sovereign-owned LLM that can be wrapped, quantized, and deployed as the native intelligence layer of the Sovereign system.

## What was found

**The core concept is sound and buildable.** A provenance-aware pipeline that uses a local model library as teachers to train and iteratively improve a persistent student lineage is a real, well-established engineering pattern. Nothing about the fundamental idea is fictional.

**Three things block it, and two things in the elaborated design are not achievable.**

### Blocking

| ID | Blocker | Effect |
|---|---|---|
| **OQ-001** | `SOV-SEED` is undefined | Determines whether this is a fine-tuning pipeline or a from-scratch model research programme. These share almost no engineering. Nothing downstream can be finalized. |
| **OQ-002** | The local model library has not been enumerated | Device bridge refused access to `.ollama` and `.lmstudio`. The entire *input* to the system is unknown. |
| **OQ-003** | No v1 acceptance criterion exists | The project has no terminal state and will drift indefinitely. |

### Not achievable as stated

| Finding | Claim in source material | Status |
|---|---|---|
| **F-1** | Architecture growth `3B → 7B → 14B → 32B` | Not executable on an 8 GB card. 14B QLoRA ≈ 14 GB; 32B ≈ 28 GB (modelled). A 32B model does not fit for *inference* either, which contradicts the operator's own sizing requirement. |
| **F-2c** | "Clone" / "cannibalize" weights across model families | No established method exists. All working weight-merge techniques (soups, TIES, DARE, task arithmetic, SLERP) require the same architecture *and* the same tokenizer, usually the same base checkpoint. |

### Unsupported but not refuted

| Finding | Claim | Status |
|---|---|---|
| **F-3** | Smallest-to-largest ordering produces a better model (a learning curriculum) | `SPECULATION`. No evidence located. The ordering has a *different*, solid justification — it is correct risk-ordering for pipeline debugging — and survives on that basis. |
| **F-8** | Sovereign will eventually run primarily on models it produced | Unfalsifiable as stated. Reframed into measurable per-role targets. |

## The single most valuable action available

**Build the frozen evaluation suite before the first training run.** The design contains a `PASS?` promotion gate with no definition of pass. Without a measurement instrument, "differential evaluation" — the intellectual core of the whole Distillery concept — cannot be implemented, regression cannot be detected, and every claim about the Sovereign model's improvement is unfalsifiable. Immutable lineage gives the *ability* to roll back but supplies no *signal* for when to.

## The single most urgent action available

**One measured QLoRA run on the actual GPU with the actual toolchain.** Every hardware number in this report is a modelled estimate from a secondary source, not a measurement of this machine. Blackwell `sm_120` kernel availability (bitsandbytes, triton, flash-attention) is an unknown that could invalidate the entire local-training plan, and it is cheap to test.

---

# Part I — Provenance of the Material Under Review

## I.1 What was reviewed

Three sources, of differing authority:

| # | Source | Authority |
|---|---|---|
| 1 | The operator's own statement of the Distillery concept | **Authoritative.** Objectives, scope, and method as stated here are preserved. |
| 2 | The operator's clarifying restatement ("the Distillery will exist to take the local models from smallest to largest to create its own LLM...") | **Authoritative.** Supersedes ambiguity in (1). |
| 3 | A prior design conversation with another model, elaborating (1) and (2) | **Not authoritative.** Contains valuable engineering but also silently adds objectives the operator did not state. Treated as a proposal to be reviewed, not a specification to be implemented. |

## I.2 Why source 3 is separated out

The prior design conversation returned a definition presented as canonical:

> *"Sovereign Distillery is the model-forging subsystem of the Sovereign Research Workspace. It progressively processes the local model library from smallest to largest, using each model as a teacher and capability source..."*

Most of that definition faithfully restates the operator. But embedded within it are six objectives the operator never stated, one of which is not executable on the available hardware. Presenting added scope inside a paragraph labelled as the operator's own concept is the mechanism by which projects acquire commitments nobody agreed to. **Part II separates them.**

## I.3 What was NOT reviewed

- No sibling repository (Sovereign, Debate Table, Multi-Model App) was read. The operator has offered paths; they have not yet been supplied. `MISSING-4`
- No model in the local library was identified, profiled, or licensed-audited. Bridge access was refused. `MISSING-1`
- No benchmark was run on the operator's GPU. `MISSING-5`, `MISSING-7`
- No code exists to review.

**Nothing in this report is a measurement of the operator's system.**

---

# Part II — Objectives and Scope

## II.1 Operator-stated objectives — APPROVED and preserved

These are authoritative. They are restated, not reinterpreted.

| ID | Objective |
|---|---|
| **OBJ-1** | Produce a Sovereign-owned LLM lineage |
| **OBJ-2** | Use the local model library as teachers / capability sources |
| **OBJ-3** | Process teachers in ascending size order (smallest to largest) |
| **OBJ-4** | Each teacher improves the persistent Sovereign checkpoint |
| **OBJ-5** | The final model is wrappable and deployable inside the Sovereign system |
| **OBJ-6** | Quantize and size-target the model to fit available hardware |
| **OBJ-7** | Build the Distillery using the existing Sovereign subsystems |

## II.2 Objectives added by the design conversation — REQUIRE EXPLICIT DECISION

| ID | Added objective | Reviewer position | Basis |
|---|---|---|---|
| **ADD-1** | Capacity-threshold architecture growth (3B → 7B → 14B → 32B) | **Reject for v1** | F-1, C-1, C-5 — not executable |
| **ADD-2** | Immutable checkpoint lineage; never overwrite | **Accept** | Low cost, high value, cannot be retrofitted |
| **ADD-3** | Differential evaluation ("what does this teacher have that I lack?") | **Accept in principle — currently undefined** | F-7 — requires an instrument that does not exist |
| **ADD-4** | License-compatibility gating at ingestion | **Accept** | F-6 — but current evidence is secondary-source only |
| **ADD-5** | Quantized deployment family separate from canonical master | **Accept** | Cheap and structurally correct |
| **ADD-6** | Sovereign eventually replaces external-model dependency | **Reject as stated** | F-8 — unbounded and unfalsifiable |

**Finding F-5 — Silent scope drift.** The operator stated a pipeline. The design conversation returned a pipeline *plus* a capability-mapping subsystem, a license-compliance subsystem, an adversarial evaluation subsystem, a deployment-artifact family, a lineage/provenance database, and an architecture-growth ladder — none flagged as additions. Several are genuine improvements. One is unexecutable. All six require deliberate acceptance or rejection rather than inheritance.

## II.3 Scope

### In scope (reviewer's reading — requires operator confirmation)

- Ingestion and characterization of local models as teachers
- Corpus construction from teacher behaviour
- Training a persistent Sovereign student checkpoint
- Evaluation, regression detection, and promotion decisions
- Checkpoint lineage and provenance
- Quantization for deployment

### Out of scope (asserted by reviewer — requires operator confirmation)

| Excluded | Reason |
|---|---|
| Pretraining a language model from random initialization at useful scale | Compute requirement exceeds a single 8 GB consumer GPU by orders of magnitude — F-4 |
| Cross-architecture weight transplantation between model families | No established method — F-2c |
| Architecture scale-up beyond the local training ceiling | F-1 |
| Serving / inference infrastructure | Belongs to Sovereign, not the Distillery |

### Scope boundary currently undefined — `UNVERIFIED`

Where the Distillery ends and Sovereign / the Debate Table / the Multi-Model App begin. The design conversation assigns roles but no interface, data contract, or invocation path has been inspected. **Every integration statement in the current material is an `ASSUMPTION`.**

---

# Part III — Evidence Base

## III.1 Directly observed on the operator's machine

| ID | Observation | Method |
|---|---|---|
| **E-1** | `D:\Sovereign Distillery` existed and was empty at review start | `device_list_dir`, recursive |
| **E-2** | Host is Windows x64 (`win32`), device `desktop-03ptabh`, Node 24.18.1, Electron 42.9.2 | `get_device_info` |
| **E-3** | Home directory contains `.ollama`, `.lmstudio`, `.gemini`, `.codex`, `.grok`, `.aider`, `.ccp`, `.dsh`, `deepseek-harness`, `ollama-fable-import`, `repos`, `praxis`, `skills-matrix`, `RRR_DUAL_CYCLE`, `URI`, `broker`, `audit`, `data` | `get_device_info` — **names only**, contents not readable |
| **E-4** | Folder-access grant for `.ollama` and `.lmstudio` was **refused by the device bridge** | `device_request_folder_access` |

**E-4 is the most consequential gap in this report.** The local model library is the entire input to the proposed system, and it has not been enumerated. Every statement about teacher ordering, license exposure, tokenizer diversity, same-family merge opportunities, disk footprint, and schedule is downstream of an inventory that does not exist.

`INTERPRETATION` — E-3 is nonetheless informative. The presence of `.ollama`, `.lmstudio`, `deepseek-harness`, and `ollama-fable-import` is consistent with a substantial multi-runtime local library. It does not establish its contents.

## III.2 External evidence

| ID | Claim | Source | Type | Confidence |
|---|---|---|---|---|
| **E-5** | RTX 5060 Ti ships in 8 GB and 16 GB variants; GDDR7 on a 128-bit bus | Multiple hardware review outlets, mutually consistent | Secondary | **High** |
| **E-6** | QLoRA on 7B/8B (4-bit NF4, rank 64, batch 1, seq 512, AdamW, **no** gradient checkpointing) ≈ **8 GB VRAM** | Spheron, *GPU VRAM Requirements to Fine-Tune LLMs in 2026* | Secondary, **modelled** | Medium |
| **E-7** | QLoRA 14B ≈ 14 GB; QLoRA 32B ≈ 28 GB; full fine-tune of 7B ≈ 88 GB | Same | Secondary, **modelled** | Medium |
| **E-8** | Gradient checkpointing reduces **activation** memory by 40–60%; does **not** reduce weight, gradient, or optimizer-state memory | Same | Secondary | Medium |
| **E-9** | Cross-tokenizer KD is an active research area (ULD, DSKD, MultiLevelOT, ALM, X-Token). The ALM authors restricted experiments to **2.4B–3.3B** parameter models, report "persistent performance degradation" in byte-level transfer, report inconsistent best-variant selection across scenarios, and self-assess as suitable for "specialized applications rather than general production deployment" | arXiv 2503.20083v2, *Cross-Tokenizer Distillation via Approximate Likelihood Matching* | **Primary** | **High** |
| **E-10** | ALM+SFT distilling a math-specialized Llama 8B into Gemma 2B reached **49.0%** average vs. the teacher's **74.6%** | Same paper | **Primary** | **High** |
| **E-11** | DeepSeek / Phi / GLM commonly MIT; Qwen3 / Mistral / Gemma-4-era commonly Apache-2.0; Llama 4 under Meta Community License with a >700M MAU cap; Gemma 3 under custom non-OSI Gemma Terms of Use with reserved remote-restriction rights | `awesome-open-weight-models` (GitHub) and licensing blog aggregation | Secondary | **LOW — must be verified against primary license text per model actually present** |

## III.3 Verification debt

| Item | Why it matters | How to close it |
|---|---|---|
| E-6 / E-7 / E-8 are modelled, not measured | The entire hardware envelope rests on them | One measured QLoRA run on this GPU |
| E-11 is secondary-source | License classification gates corpus admission | Read primary license text for each model in the library |
| Blackwell `sm_120` toolchain support | Nothing runs at all if kernels are unavailable | Attempt a run; record driver / CUDA / PyTorch / bitsandbytes versions |
| Library inventory (blocked by E-4) | Teacher ordering, licensing, schedule | Operator connects the folder or supplies `ollama list` output |

---

# Part IV — Assumptions Surfaced

These are assumptions the source material made **without stating them as assumptions**. Surfacing them is the point; several are load-bearing and at least two are false.

| ID | Hidden assumption | Load-bearing | Status |
|---|---|---|---|
| **A-1** | A Sovereign seed model exists or can be obtained | **Critical** | Undefined — F-4, OQ-001 |
| **A-2** | Distilling a teacher transfers capability the student did not have | **Critical** | Only true when the teacher is *stronger on that capability*. Unstated precondition. If the seed exceeds the teacher, distillation is a net regression. |
| **A-3** | Capability transfer is cumulative across teachers | **Critical** | Contradicted by catastrophic-forgetting behaviour unless the prior corpus is replayed — R-1 |
| **A-4** | The Sovereign model can eventually be trained at 14B / 32B scale | **Critical** | **False** on the stated hardware — F-1 |
| **A-5** | Weights, adapters, or layers can be transferred between different model families | High | **No established method** — F-2c |
| **A-6** | Debate Table output constitutes a valid promotion signal | High | LLM-as-judge is a biased estimator (position, verbosity, self-preference bias). Valid as an additional signal; unsound as the sole gate — F-7 |
| **A-7** | Local teachers can generate a training corpus in acceptable wall-clock time on an 8 GB card | High | Unquantified — MISSING-5, R-9 |
| **A-8** | Teacher outputs are correct enough to train on | High | Untested. Distillation propagates teacher errors — R-2 |
| **A-9** | The three sibling subsystems expose usable programmatic interfaces | High | Unverified — repositories not inspected |
| **A-10** | Disk capacity suffices for teacher weights + corpora + full immutable checkpoint lineage | Medium | Unquantified — MISSING-6, R-10 |

---

# Part V — Contradictions

Five internal contradictions were identified in the source material. Each is a place where two stated commitments cannot both hold.

### C-1 — The hardware contradicts the growth plan

The design specifies `SOV-3B-v4 → SOV-7B-v1 → SOV-14B-v1 → ...` on capacity threshold. E-6/E-7 put 14B QLoRA at ~14 GB and 32B at ~28 GB against an **8 GB** card. These cannot both be true. The growth ladder is not currently a plan; it is an aspiration presented in the grammar of a plan.

### C-2 — "Sovereign-owned model" contradicts "start from a seed"

The material asserts simultaneously that (a) the Sovereign model is Sovereign's own, independent of the external library, and (b) the process begins from a `SOV-SEED` and proceeds by fine-tuning. Under (b) the Sovereign model is a **derivative of whatever the seed is**, inheriting its architecture, tokenizer, license, and any naming or acceptable-use obligations. Sovereignty in the *ownership* sense is not achieved by fine-tuning another party's base model. This is the most consequential contradiction in the material and it is unresolved.

### C-3 — "Smallest to largest" contradicts "only useful deltas get promoted"

If the differential-evaluation rule holds — train only on what the teacher does *better* than the current checkpoint — then a competent seed produces an **empty delta** against the smallest teachers. By the design's own logic, the earliest and cheapest stages of the pipeline would do nothing. Either the seed is very weak (which reintroduces C-2 and F-4), or the smallest-to-largest ordering yields no capability benefit at its start.

*This contradiction is resolvable and the resolution is in F-3 — but it must be resolved deliberately, not ignored.*

### C-4 — "Clone / cannibalize" contradicts the mechanism actually described

The operator's language describes weight-level appropriation. The mechanism described in the same material is behavioural distillation via generated training data. These are different operations with different feasibility. The material treats them as one term.

### C-5 — Parameter growth contradicts the deployment constraint

OBJ-6 requires the final model to fit the operator's hardware. Growth to 14B/32B moves *away* from that constraint. A 32B model at Q4 is roughly 18–20 GB of weights and does not fit 8 GB of VRAM even for inference, let alone training.

---

# Part VI — Risk Register

| ID | Risk | Severity | Likelihood | Mitigation direction |
|---|---|---|---|---|
| **R-1** | **Catastrophic forgetting.** Sequential fine-tuning on teacher *N* degrades capabilities acquired from teachers 1..*N*−1 | High | High | Cumulative replay corpus; interleaved mixed-teacher mixes; frozen regression suite. The source design *names* this risk but does not solve it. |
| **R-2** | **Teacher-error amplification.** Small teachers hallucinate; distillation trains the student to reproduce those hallucinations *confidently* | High | High | Verification filter before corpus admission — execution tests for code, deterministic re-check for math, multi-teacher agreement for factual claims. Not present in the source design. |
| **R-3** | **Synthetic-data mode collapse.** Repeated training on model-generated text narrows the output distribution across generations | High | Medium-High | Hold a fixed non-synthetic fraction in every training mix; track output diversity as a first-class metric. Not present in the source design. |
| **R-4** | **Student ceiling.** A small student cannot absorb the full capability of a much larger teacher. E-10 shows 49.0% vs. 74.6% under a published method | High | **Certain** | This is a bound to design around, not a bug to fix. Set per-capability target bars; never "match the teacher." |
| **R-5** | **License contamination of the lineage.** Because the lineage is cumulative, one restrictively-licensed teacher taints every downstream checkpoint, irreversibly | High | Medium | Per-example provenance at generation time; license partitioning; ability to rebuild a lineage excluding any named teacher. **Free now, impossible later.** |
| **R-6** | **Promotion gate is decorative.** Immutable lineage provides rollback *ability* but no rollback *signal* | High | High | Build the frozen evaluation suite before the first training run. Non-negotiable. |
| **R-7** | **Evaluation contamination.** Teacher-generated corpora may contain benchmark items, inflating measured gains | Medium | Medium | Decontamination pass; a private held-out set never used for generation. |
| **R-8** | **Toolchain risk on Blackwell (`sm_120`).** Quantization and attention kernels have historically lagged new architectures | Medium | **Unknown** | Must be measured, not assumed. First action is a run, not a document. |
| **R-9** | **Wall-clock infeasibility.** Corpus generation on an 8 GB card is throughput-bound; a multi-teacher curriculum could consume weeks-to-months of GPU time | Medium-High | Unknown | Measure tokens/sec on one teacher before committing to a curriculum size. |
| **R-10** | **Disk exhaustion.** Teacher weights + per-teacher corpora + immutable lineage grows without bound | Medium | Medium | Retention policy defined at design time, not after the first full disk. |
| **R-11** | **Scope drift into a permanent research project.** The design is broad enough that no state counts as "done" | Medium | High | Define v1 acceptance as a single measurable claim, not a capability aspiration — OQ-003. |

---

# Part VII — Findings in Full

## F-1 — CRITICAL — The stated hardware cannot execute the stated plan beyond roughly 3B parameters

**Evidence:** E-5, E-6, E-7, E-8.

**Analysis.** An 8 GB card running Windows loses VRAM to the desktop compositor — the WDDM reserve, typically several hundred MB to ~1.5 GB depending on display configuration (`ASSUMPTION`; not measured here). Against E-6's ~8 GB figure for 7B QLoRA at batch 1, sequence 512, rank 64, **without** gradient checkpointing, a 7B student sits **at or past the margin** before any teacher is resident and before any sequence length useful for reasoning-style training data.

**Conclusions, by confidence:**

- `FACT`-grounded: **14B and 32B training are not possible on this card.** C-1 is a hard contradiction, not a tuning problem.
- High-confidence `INTERPRETATION`: the realistic local training ceiling is a **1B–3B student under QLoRA with gradient checkpointing and short-to-moderate sequence length**. A 7B student may be reachable with aggressive settings and should be treated as an experiment to measure, not a dependency to plan around.
- `FACT`: online / logit-level distillation requires teacher **and** student resident simultaneously, roughly doubling peak memory. On 8 GB this effectively forecloses white-box KD for any non-trivial teacher.

**Therefore:** the only broadly viable local mechanism is **offline, black-box, sequence-level distillation** — teacher generates, corpus is persisted, student trains in a separate process. This is a hardware constraint, not a design preference, and it is recorded as invariant **INV-4**.

**Operator decision required (OQ-004).** Either accept a ≤3B Sovereign model as the v1 target, or decide that training bursts to rented GPU compute — which is a materially different project with different cost, data-egress, and licensing analysis. The reviewer does not choose.

---

## F-2 — CRITICAL — "Distill / clone / cannibalize" conflates three mechanisms with three different feasibilities

The source material uses these terms interchangeably. They are not interchangeable, and the difference determines what can be built.

### (a) White-box / logit-level KD — student matches the teacher's output distribution

- Requires a shared tokenizer, or a cross-tokenizer method.
- Cross-tokenizer KD is **real research, not fiction**: ULD, DSKD, MultiLevelOT, ALM, X-Token all exist.
- But per E-9 the ALM authors explicitly limit their claims to 2.4B–3.3B models, report inconsistent best-variant selection across scenarios, report persistent degradation in transfer, and self-assess the method as suited to "specialized applications rather than general production deployment."
- Memory cost makes it impractical on 8 GB regardless (F-1).

**Verdict: research track. Not the v1 mechanism.**

### (b) Black-box / sequence-level KD — teacher generates outputs; student is supervised-fine-tuned on them

- Tokenizer-agnostic, architecture-agnostic, family-agnostic.
- Decouples generation from training, so it fits an 8 GB card.
- Well-established; this is the mechanism behind most well-known distilled small models.

**Verdict: this is the Distillery. Everything else is optional.**

### (c) Weight-level transfer — merging, task vectors, layer transplantation, adapter grafting

- Every established method — model soups, TIES, DARE, task arithmetic, SLERP — requires **the same architecture and the same tokenizer**, typically the same base checkpoint.
- Transplanting weights across model families is not a supported operation. `FACT` — the reviewer located no established method. *(Note: this is an absence-of-evidence claim, appropriately weaker than a positive proof of impossibility.)*

**Verdict: applicable only among same-family teachers, if the library contains any — which OQ-002 would reveal. Out of scope cross-family.**

### Finding

The operator's word "cannibalize" maps cleanly onto **(b)**, and onto (b) alone. This is not a downgrade of the concept. It is a translation of it into the mechanism that actually performs the described function. But the specification must say so explicitly, or the project will repeatedly attempt (c) and repeatedly fail without understanding why.

---

## F-3 — MAJOR — The smallest-to-largest ordering is asserted, not evidenced

**Claim under review:** *"The smaller teachers establish foundational behaviors and cheaper capability acquisition first... By the time it reaches the biggest teachers, it is no longer an infant trying to imitate them wholesale."*

**Status: `SPECULATION`.** This is a curriculum-learning analogy applied to distillation. The reviewer found no evidence that sequential smallest→largest distillation outperforms either (i) distilling directly from the strongest available teacher, or (ii) training on a single interleaved corpus drawn from all teachers.

**Counter-considerations with support:**

1. In black-box KD, student capability is bounded above by the teacher's *outputs*. Training a 3B student on a 1B teacher's outputs installs a **1B-quality ceiling** on the capabilities that data covers. If the seed is already at 3B quality, this is a net regression, not a gain (A-2).
2. Strictly sequential fine-tuning is the configuration **most** vulnerable to catastrophic forgetting (R-1). Interleaved mixed-corpus training is the standard mitigation — and is strictly *less* compatible with a one-teacher-at-a-time ordering.
3. C-3: honouring the differential-evaluation rule makes the early stages no-ops.

**However — the ordering has a justification the source material did not give, and it is a good one.**

Smallest-to-largest is correct **risk ordering**. Small teachers are cheap to load and cheap to generate from. Running them first proves the plumbing — ingestion, generation, filtering, provenance, training, evaluation, promotion, lineage — at the lowest possible cost, before any expensive teacher is touched. That is sound engineering practice and it preserves the operator's stated sequence exactly.

**Recommendation.** Retain smallest-to-largest as an **operational ordering for pipeline validation** — well-justified. Drop the claim that it produces a better *model* — not justified. If the operator wishes to retain the curriculum hypothesis, record it as an explicit, testable hypothesis (comparable later against a single-mixed-corpus baseline) rather than as settled design rationale. **The operator's directive survives intact; only the stated reason for it changes.**

---

## F-4 — CRITICAL / BLOCKING — `SOV-SEED` is undefined and the entire architecture rests on it

Every diagram in the source material begins at `SOV-SEED` or `SOV-0`. None says what it is. There are exactly three possibilities, and they are not variations of one project.

| Option | Executable on 8 GB? | Genuinely "Sovereign-owned"? | Consequence |
|---|---|---|---|
| **(i) Random initialization — pretrain from scratch at useful scale** | **No.** Pretraining a usable LLM requires compute several orders of magnitude beyond a single consumer GPU. `FACT` | Yes | If this is the intent, the project as scoped is **not executable**, and that must be said now rather than discovered in six months. |
| **(ii) Fine-tune an existing open-weight base model** | **Yes** | **No** — the Sovereign model is a derivative, inheriting architecture, tokenizer, license, naming and AUP obligations | Fastest path to a working system. Sovereignty is *operational* (you control the training, data, and lineage), not *legal* (you do not own the base). Directly triggers C-2. |
| **(iii) Pretrain a deliberately tiny model (~100M–500M) from scratch on a curated corpus, then distil into it** | **Yes**, marginally | **Yes** | Genuinely own the lineage end to end. The resulting model will be far weaker than the existing library and would not replace it for a long time, if ever. Legitimate as a research lineage; not as a near-term production intelligence layer. |

**This decision determines whether the Sovereign Distillery is (ii) "a fine-tuning pipeline with unusually good governance" or (iii) "a from-scratch model research programme." They share almost no engineering — different tooling, different licensing posture, different schedule, different acceptance criteria, different definition of success.**

The reviewer does not choose. The operator must. **This is the blocker.**

`INTERPRETATION` — the operator's language ("its own LLM", "our own Sovereign model", "Sovereign-owned") reads as pointing toward (iii). The operator's constraints (single 8 GB GPU, local library as the material) point toward (ii). That tension is real and it is exactly what OQ-001 asks the operator to resolve.

---

## F-5 — MAJOR — Silent scope drift between operator directive and design conversation

Covered in Part II.2. The operator stated a pipeline; the design conversation returned a pipeline plus six additional subsystems and objectives, presented as a single canonical definition without flagging which parts were added.

Several additions are genuine improvements and should be accepted. One is unexecutable. The point of the finding is not that the additions are bad — it is that **added scope arriving inside a paragraph labelled as the operator's own concept is how projects acquire commitments nobody agreed to.** Part II.2 exists so each addition can be accepted or rejected deliberately.

---

## F-6 — MAJOR — Licensing analysis is currently secondary-source and cannot be relied upon

E-11 is drawn from blog aggregation. It is directionally plausible and matches the reviewer's prior understanding, but it is `UNVERIFIED`, and license terms differ between versions *within the same family* — Gemma 2, Gemma 3, and Gemma 4 terms are not identical; Qwen 2.5 and Qwen 3 differ. Blanket family-level statements are unsafe.

**The structurally important point is independent of which licenses actually apply.** Because the Sovereign lineage is *cumulative and sequential*, a single restrictively-licensed teacher contaminates every downstream checkpoint, and there is no way to remove it after the fact without retraining from a point before its introduction. The mitigation is cheap now and impossible later:

- Per-example provenance recorded **at generation time** (which teacher, which version, which prompt, which run, which license class).
- Corpus partitioned by license class.
- The ability to answer "rebuild this lineage excluding teacher X" at any point.

**Recommendation.** Build provenance in from the first generated example regardless of what the license audit concludes. Resolve OQ-007 (internal-only vs. eventual distribution) early — it changes the severity of R-5 by an order of magnitude, and if distribution is ever plausible, some teachers may need to be excluded from the lineage *before* any training occurs rather than after.

---

## F-7 — MAJOR — There is no evaluation definition, so the promotion gate does not exist

The source design shows a `PASS?` decision node. Nothing in the material defines what pass means. Three consequences follow, and they compound:

1. **Rollback without a signal.** The immutable-lineage invariant (ADD-2 / INV-1) provides the ability to roll back but no signal for when to. Preserving `SOV-D016` is worthless if nothing detects that `SOV-D017` regressed.
2. **Differential evaluation is unimplementable.** "What capability does this teacher possess that the current Sovereign checkpoint demonstrably lacks?" is the intellectual core of the Distillery — the thing that distinguishes it from naive sequential fine-tuning. It requires a per-capability measurement of *both* teacher and student on a *common* instrument. That instrument does not exist and is not specified anywhere in the material.
3. **Debate Table cannot be the gate.** LLM-as-judge carries known position, verbosity, and self-preference biases. It is a useful *additional* signal and an unsound *sole* gate (A-6).

**Recommendation — the reviewer regards this as the single highest-value action available in the entire project.**

Build a frozen evaluation suite **before** the first training run. Composition in Part IX.5. It must contain deterministic, machine-checkable tasks — code that executes against tests, math with checkable answers, structured extraction with exact-match scoring, instruction-following with programmatic constraint checks — plus a private held-out set never used for corpus generation.

Without this, every subsequent claim about the Sovereign model's improvement is unfalsifiable, and the project will produce a lineage of checkpoints whose quality nobody can establish, compare, or defend.

---

## F-8 — MODERATE — "Sovereign runs primarily on models Sovereign produced" is an unfalsifiable objective

Under F-1's training ceiling and R-4's capability bound, a Sovereign student distilled from a heterogeneous local library on an 8 GB card will not be competitive with the models currently performing orchestration work in the Sovereign system. Adopting ADD-6 as a project objective installs a **permanent failure condition** — a goal that can never be marked achieved.

**Reframe that is achievable and measurable.** Sovereign-produced models take over **specific, bounded in-system roles** where a small specialized model can meet a stated numeric bar:

- Routing / intent classification
- Memory compaction and summarization
- Structured extraction and schema-filling
- Query rewriting and expansion
- First-pass triage before escalating to a larger model

Each role gets an explicit acceptance threshold. *"Sovereign now runs its own router at 94% agreement with the reference model at one-twentieth the latency"* is a real, verifiable, defensible achievement. *"Sovereign has its own LLM"* is not measurable and therefore not achievable.

This is a reframe, not a rejection. The long-term direction the operator described survives; only the success criterion changes from unbounded to bounded.

---

# Part VIII — Missing Information

Ordered by how much it blocks.

| ID | Missing | Blocks | Why it matters |
|---|---|---|---|
| **MISSING-1** | **Local model library inventory** — names, parameter counts, quantizations, tokenizers, architectures, licenses, on-disk sizes | Everything | Bridge access refused (E-4). Teacher ordering, license exposure, same-family merge opportunities, and schedule all depend on it. |
| **MISSING-2** | **Seed decision** — what is `SOV-SEED`? | Everything | F-4. The blocking decision. |
| **MISSING-3** | **v1 acceptance criteria** — what measurable result means the Distillery worked? | Promotion gate, project completion | Without it the project has no terminal state (R-11). |
| **MISSING-4** | **Sibling repository interfaces** — Sovereign, Debate Table, Multi-Model App | All integration design | Operator offered paths; not yet supplied. |
| **MISSING-5** | **Measured generation throughput** on the actual GPU for a representative teacher | Curriculum sizing, schedule realism | Determines whether the plan takes days or months (R-9). |
| **MISSING-6** | **Disk budget and system RAM** | Retention policy, CPU-offload viability | System RAM determines whether offloaded training is an option at all. |
| **MISSING-7** | **Verified toolchain status** — driver, CUDA version, PyTorch build, bitsandbytes / Unsloth support for `sm_120` | The first training run | R-8. Nothing runs if kernels are unavailable. |
| **MISSING-8** | **Primary license texts** for each model actually present | Legal exposure, redistribution rights | E-11 is secondary-source only. |
| **MISSING-9** | **Intended distribution** — internal use only, or eventual release? | Whether R-5 is a nuisance or a hard blocker | Licensing analysis differs completely between these. |

---

# Part IX — Provisional Specification

**Status: PROVISIONAL.** Blocked on OQ-001, OQ-002, OQ-003. Sections marked **[APPROVED]** restate operator-stated objectives; **[PROPOSED]** are reviewer proposals awaiting acceptance; **[BLOCKED]** cannot be completed until a named open question resolves.

## IX.1 Mission [APPROVED — operator-stated]

The Sovereign Distillery is the **model-forging** subsystem of the Sovereign Research Workspace.

It processes the local model library in ascending size order. For each model, it treats that model as a **teacher**, extracts the capability that teacher demonstrably contributes, and uses the extracted material to train the persistent **Sovereign model** — a single evolving student lineage. Each stage produces a new immutable Sovereign checkpoint. The intended end state is a Sovereign-owned model family that can be wrapped, quantized to available hardware, and deployed as an intelligence layer inside the Sovereign system.

**The distinction that defines the subsystem:** Sovereign, the Debate Table, and the Multi-Model App **use** models. The Distillery **produces** them.

## IX.2 Invariants

Non-negotiable properties. A change to any of these is a specification change requiring operator approval, not an implementation detail.

| ID | Invariant | Origin | Rationale |
|---|---|---|---|
| **INV-1** | **The Sovereign checkpoint is never overwritten.** Every training run produces a new immutable candidate with a new identifier. Promotion changes a pointer, never a file. | ADD-2 | Rollback is the only defence against silent regression, and it is cheap. |
| **INV-2** | **Every training example carries provenance** — teacher identity, teacher version and quantization, generation run, prompt source, timestamp, license class — recorded at generation time, never reconstructed. | Reviewer (F-6) | A cumulative lineage cannot be decontaminated after the fact. |
| **INV-3** | **No checkpoint is promoted without passing the frozen evaluation suite**, including the regression subset covering every previously acquired capability. | Reviewer (F-7) | Without this, INV-1 provides rollback ability but no rollback signal. |
| **INV-4** | **Distillation is offline and black-box by default.** Teacher generates → corpus persisted → student trains separately. Teacher and student are never required to be co-resident in VRAM. | Reviewer (F-1, F-2b) | Hardware constraint, not preference. |
| **INV-5** | **Canonical master and quantized deployment artifacts are separate objects.** Quantization is a deployment transformation applied to a promoted master; it never defines the master and a quantized artifact is never a parent. | ADD-5 | Prevents lossy artifacts entering the training lineage. |
| **INV-6** | **The evaluation suite is frozen before use and versioned separately from the models.** Any change to the suite invalidates cross-generation comparison and requires a version bump. | Reviewer (F-7, R-7) | A moving ruler measures nothing. |
| **INV-7** | **Held-out evaluation data is never used for corpus generation.** | Reviewer (R-7) | Contamination inflates measured gains. |

## IX.3 Objects

### Teacher
A model from the local library, used as a source of behaviour. **Never modified.** Record: name, family, architecture, parameter count, quantization, tokenizer, on-disk size, license identifier, license class, source URL, content hash.

### Sovereign checkpoint
An immutable trained student artifact. Identifier form `SOV-D<NNN>`. Required lineage record:

```
SOV-D017
├── parent_checkpoint      SOV-D016
├── teacher(s)             [Model-X @ version, quantization]
├── corpus_manifest_hash   sha256:...
├── training_config_hash   sha256:...
├── base_architecture      <arch>
├── parameter_count        <n>
├── precision              <fp16 | bf16 | 4bit-nf4 | ...>
├── eval_suite_version     v<N>
├── eval_results           {task: score}
├── regression_results     {prior_capability: delta}
├── capability_delta       {gained: [...], lost: [...]}
├── license_classes_used   [permissive | restricted-naming | restricted-use]
├── wall_clock_hours       <n>
└── promotion_decision     {promoted | rejected | quarantined} + operator signature
```

### Corpus shard
Generated training examples from one teacher in one generation run. Carries the INV-2 provenance block. **Immutable once written.**

### Evaluation suite
Versioned and frozen. Deterministic band, regression band, private held-out set, advisory band. See IX.5.

### Deployment artifact
A quantized, hardware-targeted derivative of a promoted master — `SOV-LM-Q4`, `SOV-LM-Q6`, `SOV-LM-CODE`. **Never a parent of anything.**

## IX.4 Lifecycle

For each teacher, in ascending size order:

```
 1. INGEST        register teacher; record architecture, tokenizer, license, hash
 2. GATE          license class check → permitted / restricted / rejected
 3. CHARACTERIZE  measure teacher on the frozen eval suite
 4. DIFFERENTIAL  compare teacher scores vs. current Sovereign checkpoint scores
                  → capability delta = {tasks where teacher exceeds student by margin M}
 5. DECIDE        delta empty  → SKIP this teacher; record the skip and its reason
                  delta present → proceed
 6. CURRICULUM    build a prompt set targeting only the delta capabilities
 7. GENERATE      teacher produces outputs; provenance stamped per example  [INV-2]
 8. FILTER        verification pass; reject unverifiable or incorrect outputs
 9. MIX           new shard + replay of prior corpus + non-synthetic fraction
10. TRAIN         QLoRA/LoRA on the current Sovereign checkpoint → candidate
11. EVALUATE      full frozen suite, including the complete regression subset  [INV-3]
12. ADJUDICATE    optional Debate Table adversarial pass — ADVISORY, not a gate
13. PROMOTE       operator decision; candidate becomes new parent, or is quarantined
14. RECORD        lineage entry written; corpus manifest sealed
```

**Step 5 is load-bearing.** If the seed is competent, the smallest teachers will produce an empty delta and will be legitimately skipped. **That is a correct outcome, not a failure.** The value of running them first is pipeline validation at minimum cost (F-3), which step 5 preserves.

**Step 12 is advisory.** Debate Table output is recorded as signal. It does not gate promotion (F-7, A-6).

**Step 13 requires the operator.** Promotion is an acceptance decision and acceptance belongs to the operator.

## IX.5 Evaluation [PROPOSED — precedes all training]

**Build-order rule: the evaluation suite is constructed and frozen before the first teacher is processed.** No training run should occur before it exists, because the result would be uninterpretable.

| Band | Content | Scoring |
|---|---|---|
| **Deterministic** | Code that compiles and executes against unit tests; math with checkable answers; structured extraction with exact-match; instruction-following with programmatic constraint checks (format, length, forbidden tokens, schema conformance) | Exact / pass-rate. **No model in the loop.** |
| **Regression** | Every capability the lineage has previously demonstrated. Grows monotonically — items added on promotion, never removed. | Delta vs. best prior checkpoint. Any negative delta beyond tolerance **blocks promotion**. |
| **Held-out** | Private. Never used for prompt generation, never shown to a teacher. | Same instruments as Deterministic. Primary anti-contamination control. |
| **Advisory** | Debate Table adversarial comparison; subjective quality; open-ended reasoning | Recorded. **Not gating.** |

**Promotion rule [PROPOSED].** A candidate is promotable only if (a) it improves at least one targeted delta capability by margin **M**, and (b) it does not regress any regression-band item beyond tolerance **T**. Both M and T are operator-set numbers, currently **UNSET** — OQ-005.

**Companion requirement.** Establish run-to-run variance on the suite *before* setting M and T. Thresholds set below the noise floor produce a gate that either always passes or never passes.

## IX.6 License gating [PROPOSED — evidence currently weak, see F-6]

| Class | Meaning | Corpus handling |
|---|---|---|
| `PERMISSIVE` | MIT / Apache-2.0 style; no derivative-naming or field-of-use restrictions | Freely mixed |
| `RESTRICTED-NAMING` | Derivative-model naming and/or attribution obligations propagate | Shard tagged; lineage flagged |
| `RESTRICTED-USE` | Field-of-use, non-commercial, or user-scale caps | Shard tagged; must remain excludable |
| `REJECTED` | Terms incompatible with intended use | Not ingested |

**Current evidence status:** class assignments implied by E-11 are `UNVERIFIED`. Every teacher's **primary license text** must be read before its class is fixed (MISSING-8).

**Structural requirement regardless of class assignment (INV-2):** the system must be able to answer *"rebuild this lineage excluding teacher X"* at any time. That capability is free if provenance is recorded from example one, and impossible if it is not.

## IX.7 Generation filtering [PROPOSED — mitigates R-2]

| Data type | Verification |
|---|---|
| Code | Execute against tests. Reject on failure. |
| Math / computation | Deterministic re-check. Reject on mismatch. |
| Structured output | Schema validation. Reject on parse failure. |
| Factual claims | Multi-teacher agreement threshold, or drop. Unverifiable factual generation is the weakest category and should be **minimized rather than filtered**. |
| Style / format | Programmatic constraint check. |

**Rejection rate is a tracked metric per teacher.** A teacher with a high rejection rate is itself a finding worth recording.

## IX.8 Corpus mixing [PROPOSED — mitigates R-1, R-3]

Each training mix contains:

- The new teacher's filtered shard (the targeted delta)
- **Replay** — a sampled fraction of all previously accepted shards
- A **non-synthetic fraction** — human-authored data, resisting model-collapse and diversity narrowing across generations

Ratios are **UNSET** (OQ-006).

**Acknowledged tension with the operator directive.** Replay mixing is in mild tension with the strict "one teacher at a time" framing. The reviewer's position: the **ordering** is preserved — teachers are still introduced smallest-to-largest, one at a time — while the **training mix** is cumulative. If the operator intends strictly single-teacher mixes, R-1 becomes near-certain and should be accepted knowingly rather than by default.

## IX.9 Hardware envelope [BLOCKED on measurement]

**Stated hardware:** NVIDIA RTX 5060 Ti, 8 GB VRAM, Blackwell (`sm_120`).

Modelled constraints — **secondary-source estimates, not measured on this machine**:

| Operation | Estimate | Verdict on 8 GB |
|---|---|---|
| QLoRA 7B (4-bit NF4, r=64, bs=1, seq=512, no grad-ckpt) | ~8 GB | At or over margin |
| QLoRA 14B | ~14 GB | Not possible |
| QLoRA 32B | ~28 GB | Not possible |
| Full fine-tune 7B | ~88 GB | Not possible |
| Co-resident teacher + student (white-box KD) | ~2× student | Not possible for non-trivial teachers |

**Working envelope [PROPOSED, pending measurement]:** student **1B–3B**, QLoRA 4-bit, gradient checkpointing enabled, short-to-moderate sequence length. A 7B student is an experiment to attempt and measure, not a plan to depend on.

**Architecture growth (3B → 7B → 14B → 32B) is REMOVED from v1 scope** per F-1, C-1, C-5 — pending OQ-004.

## IX.10 Integration with the Sovereign Workspace [BLOCKED — repositories not inspected]

| Subsystem | Assigned role | Status |
|---|---|---|
| **Multi-Model App** | Extraction and experimentation surface — drives teacher generation, coordinates multiple models | `ASSUMPTION` — interface unknown |
| **Debate Table** | Adversarial comparison of candidate vs. parent vs. teacher; **advisory** signal only | `ASSUMPTION` — interface unknown |
| **Sovereign** | Orchestration, provenance store, long-running workflow state, experiment memory | `ASSUMPTION` — interface unknown |
| **Distillery** | Owns the IX.4 lifecycle end to end | Defined here |

No integration contract may be written into the specification until the three repositories are inspected (MISSING-4).

**Design constraint asserted now, to prevent later coupling:** the Distillery must be **operable standalone**. If the Debate Table is unavailable, step 12 is skipped and promotion still functions on the deterministic suite. A model-production pipeline that cannot run without three other applications is a fragility, not an integration.

## IX.11 Directory layout [PROPOSED]

```
D:\Sovereign Distillery\
├── docs\          specifications, reviews, decisions, evidence
├── registry\      teacher registry, license classifications
├── evals\         frozen suites, versioned; held-out set access-controlled
├── curricula\     prompt sets per capability
├── corpora\       immutable shards + manifests + provenance
├── runs\          training run configs, logs, metrics
├── checkpoints\   immutable Sovereign lineage
├── lineage\       lineage records, promotion decisions
├── deploy\        quantized artifacts (never parents)
└── tools\         pipeline code
```

Only `docs\` currently exists. The rest awaits specification acceptance.

## IX.12 v1 acceptance criterion [BLOCKED — OQ-003]

**Currently undefined.** Without it the project has no terminal state (R-11).

Reviewer's proposed *shape*, for operator consideration only:

> *One named capability, measured on the frozen deterministic suite, where the promoted Sovereign checkpoint scores at or above a stated threshold, with no regression-band item degraded beyond tolerance, and with full provenance from teacher to checkpoint reproducible from the lineage record.*

That is falsifiable. *"Sovereign has its own LLM"* is not.

---

# Part X — Decision Records

Four ADRs were written. All are **PROPOSED**, none accepted.

| ADR | Decision | Depends on | Reversible? |
|---|---|---|---|
| **ADR-0001** | Immutable checkpoint lineage; provenance recorded at generation time | — | **No.** Provenance is free to add now and impossible to reconstruct later. |
| **ADR-0002** | Offline black-box distillation as the primary mechanism; white-box KD as a research track; cross-family weight transfer out of scope | F-1, F-2 | Yes, if hardware changes |
| **ADR-0003** | Architecture growth removed from v1 scope; working envelope 1B–3B | OQ-004 | Yes — superseded if rented compute is approved |
| **ADR-0004** | The evaluation suite is built and frozen before the first training run | — | Technically yes; practically no — retrofitting evaluation after a lineage exists invalidates all prior comparisons |

**Two of these cannot be deferred without permanent cost:** ADR-0001 (provenance) and ADR-0004 (evaluation-first). Both are cheap now. Neither can be added later without discarding work.

---

# Part XI — Open Questions Requiring the Operator

| ID | Question | Blocking? |
|---|---|---|
| **OQ-001** | What is `SOV-SEED` — random init, an existing open-weight base, or a deliberately tiny from-scratch model? | **YES** |
| **OQ-002** | What is actually in the local model library? | **YES** |
| **OQ-003** | What is the v1 acceptance criterion? | **YES** |
| **OQ-004** | Is training compute limited to the local 8 GB GPU, or can it burst to rented compute? | Determines whether ADR-0003 is permanent |
| **OQ-005** | Promotion margin **M** and regression tolerance **T** | Blocks the promotion gate |
| **OQ-006** | Corpus mixing ratios; and — strictly single-teacher mixes, or cumulative with replay? | Touches the stated method |
| **OQ-007** | Is the Sovereign model intended for distribution, or internal use only? | Changes R-5 severity by an order of magnitude |
| **OQ-008** | Does smallest-to-largest stand as a learning curriculum, or as pipeline-risk ordering? | Determines what claim the project makes |
| **OQ-009** | Where are the Sovereign, Debate Table, and Multi-Model App repositories? | Blocks all integration design |

---

# Part XII — Recommended Sequence of Work

`PROPOSED` — the reviewer's recommended ordering. The operator sets priority.

Each phase states what it **de-risks**, so the ordering can be argued with rather than merely accepted.

### Phase 0 — Instrument the machine *(before any design work continues)*

**De-risks:** R-8, F-1, MISSING-5, MISSING-7 — converts the entire hardware envelope from modelled estimate to measurement.

- Record driver, CUDA, PyTorch, bitsandbytes / Unsloth versions
- Run one minimal QLoRA fine-tune on the smallest available model
- Measure peak VRAM, tokens/sec training, tokens/sec generation
- Record system RAM and free disk

**Exit criterion:** a one-page measured-capability sheet for this specific machine. **If this phase fails — if `sm_120` kernels are unavailable — the entire local-training plan is invalid and must be reconsidered before anything else is built.**

*This phase is deliberately first. Every number in this report is currently an estimate.*

### Phase 1 — Resolve the seed *(OQ-001)*

**De-risks:** F-4, C-2 — determines which project this is.

Operator decision. No engineering.

**Exit criterion:** a written, dated decision recorded as ADR-0005, with its consequences for licensing and acceptance criteria spelled out.

### Phase 2 — Inventory and license audit *(OQ-002, MISSING-8)*

**De-risks:** MISSING-1, R-5, F-6.

- Enumerate the library: name, params, quant, tokenizer, architecture, size on disk
- Read **primary** license text per model; assign license class
- Identify any same-family groups (the only case where weight merging is viable — F-2c)
- Produce the ordered teacher list

**Exit criterion:** `registry/teachers.json` with a license class per entry, and an explicit ordered teacher queue.

### Phase 3 — Build and freeze the evaluation suite *(ADR-0004)*

**De-risks:** R-6, F-7, R-7 — the highest-value phase in the project.

- Deterministic band with machine-checkable scoring
- Private held-out set, access-controlled, never used for generation
- Establish run-to-run variance
- Set M and T from measured variance, not intuition *(OQ-005)*
- Freeze; version as `v1`

**Exit criterion:** a suite that can score any model, plus a baseline measurement of the seed and of every teacher in the queue. **That baseline is also the differential-evaluation table — it is what makes step 4 of the lifecycle implementable.**

### Phase 4 — Provenance and lineage skeleton *(ADR-0001)*

**De-risks:** R-5, R-10 — and this is the phase that cannot be retrofitted.

- Corpus shard format with the INV-2 provenance block
- Lineage record schema
- Retention policy *(R-10)*
- "Rebuild excluding teacher X" implemented and tested against synthetic data

**Exit criterion:** the exclusion query works on test data. Not on real data — on test data, before any real data exists.

### Phase 5 — End-to-end on the smallest teacher

**De-risks:** everything procedural, at minimum cost — the real justification for smallest-to-largest *(F-3)*.

Run the full IX.4 lifecycle once, on the cheapest teacher available. **The goal is not a better model. The goal is a proven pipeline.**

A legitimate and informative outcome here is **SKIP at step 5** — an empty capability delta. If that happens, the pipeline worked correctly and C-3 has been confirmed empirically.

**Exit criterion:** a complete lineage record exists, whatever the promotion decision was.

### Phase 6 — Iterate the teacher queue

Ascending size. Per teacher: differential → curriculum → generate → filter → mix → train → evaluate → adjudicate → operator promotion decision → record.

**Watch metrics:** regression-band deltas *(R-1)*, filter rejection rate per teacher *(R-2)*, output diversity *(R-3)*, wall-clock per stage *(R-9)*, disk consumption *(R-10)*.

### Phase 7 — Quantize and deploy *(INV-5)*

Only from a promoted master. Deployment artifacts are terminal — never parents.

**Exit criterion:** a hardware-targeted artifact that runs inside the Sovereign harness, measured against the same frozen suite as its master, with the quantization loss recorded.

---

# Part XIII — What Would Change This Report

Stated explicitly so the analysis can be falsified rather than merely believed.

| If this turns out to be true | These findings change |
|---|---|
| The GPU is the **16 GB** 5060 Ti variant, not 8 GB | F-1 relaxes substantially; 7B becomes comfortable; ADR-0003 is revised though 14B/32B still remain out of reach |
| Rented training compute is approved *(OQ-004)* | ADR-0003 superseded; the growth ladder returns with new cost and licensing analysis |
| Measured QLoRA VRAM on this machine differs materially from E-6/E-7 | The entire IX.9 envelope is recalculated; E-6/E-7 are downgraded and replaced with measurements |
| The library contains a **same-family** teacher set | F-2c partially reopens — weight merging becomes viable *within* that family |
| The library contains a strong same-tokenizer teacher/student pair | White-box KD moves from research track toward a viable option, memory permitting |
| The seed is decided as option (iii) — tiny from-scratch | F-8's reframe becomes less necessary; expectations reset far lower; the timeline extends substantially; C-2 dissolves |
| The seed is decided as option (ii) — fine-tune an existing base | C-2 is resolved by accepting derivative status; F-6 licensing becomes materially more urgent; "Sovereign-owned" must be restated as operational rather than legal sovereignty |
| Primary license texts contradict E-11 | IX.6 class assignments change; some teachers may become `REJECTED` before ingestion |
| Sibling repositories expose usable interfaces | IX.10 moves from `ASSUMPTION` to specification; integration contracts can be written |
| `sm_120` kernels are unavailable for the required quantization path | **Phase 0 fails and the entire local-training plan requires reconsideration** |

---

# Appendix A — Terminology Register *(continuity)*

Preserved for project continuity. Terminology should remain stable across sessions and across models working on this project.

| Term | Definition as used in this project |
|---|---|
| **Sovereign Research Workspace** | The parent environment containing Sovereign, the Debate Table, the Multi-Model App, and the Distillery |
| **Sovereign Distillery** | The model-forging subsystem. Produces models; does not use them operationally. |
| **Teacher** | A model from the local library used as a source of behaviour. Never modified. |
| **Student / Sovereign model** | The single persistent evolving checkpoint lineage the Distillery trains |
| **`SOV-SEED`** | The initial Sovereign checkpoint. **Currently undefined — OQ-001.** |
| **`SOV-D<NNN>`** | An immutable Sovereign checkpoint in the development lineage |
| **`SOV-LM-<QUANT>`** | A quantized deployment artifact. Terminal; never a parent. |
| **Capability delta** | The set of tasks on which a teacher measurably exceeds the current Sovereign checkpoint by margin M |
| **Differential evaluation** | Lifecycle step 4 — measuring teacher against student on a common instrument to compute the capability delta |
| **Promotion** | The operator decision to make a candidate checkpoint the new parent of the lineage |
| **Quarantine** | A candidate that failed evaluation; retained with its lineage record, never a parent |
| **Corpus shard** | Immutable generated examples from one teacher in one generation run, carrying provenance |
| **Replay** | Sampled inclusion of prior corpus shards in a new training mix, mitigating catastrophic forgetting |
| **License class** | `PERMISSIVE` / `RESTRICTED-NAMING` / `RESTRICTED-USE` / `REJECTED` — assigned at ingestion |
| **Operational sovereignty** | Control over training, data, lineage, and deployment |
| **Legal sovereignty** | Ownership of the base model weights and freedom from inherited license terms. **The two are not the same — C-2.** |

# Appendix B — Sources

| Source | Used for | Type |
|---|---|---|
| arXiv 2503.20083v2 — *Cross-Tokenizer Distillation via Approximate Likelihood Matching* — https://arxiv.org/html/2503.20083v2 | E-9, E-10 — cross-tokenizer KD maturity and measured student/teacher gap | **Primary** |
| Spheron — *GPU VRAM Requirements to Fine-Tune LLMs in 2026* — https://www.spheron.network/blog/gpu-vram-requirements-fine-tune-llm-2026/ | E-6, E-7, E-8 — modelled VRAM by method and model size | Secondary |
| `awesome-open-weight-models` (GitHub) — https://github.com/phlx0/awesome-open-weight-models | E-11 — license landscape | Secondary, **low confidence** |
| TechSpot — *RTX 5060 Ti 8GB vs 16GB* — https://www.techspot.com/review/3004-nvidia-rtx-5060-ti-pcie-benchmark/ | E-5 — card variants and memory configuration | Secondary |
| Operator statements (this session and prior) | OBJ-1 … OBJ-7 | **Authoritative** |
| Prior design conversation with another model | ADD-1 … ADD-6, and the material under review | **Not authoritative** |

# Appendix C — Document Inventory

Written to `D:\Sovereign Distillery`:

| Path | Contents |
|---|---|
| `README.md` | Entry point, blocking decisions, findings summary |
| `docs\00-VALIDATION-REVIEW.md` | Full structured review — objectives, scope, evidence, assumptions, contradictions, risks, gaps, findings |
| `docs\01-CANONICAL-SPEC.md` | Provisional specification |
| `docs\02-OPEN-QUESTIONS.md` | OQ-001 … OQ-009 with consequences |
| `docs\decisions\ADR-0001-immutable-lineage.md` | Immutable lineage and provenance |
| `docs\decisions\ADR-0002-distillation-mechanism.md` | Offline black-box distillation as primary mechanism |
| `docs\decisions\ADR-0003-architecture-growth-deferred.md` | Growth removed from v1 scope |
| `docs\decisions\ADR-0004-evaluation-precedes-training.md` | Evaluation-first build order |
| `docs\evidence\EVIDENCE-LOG.md` | Every external claim, source, confidence, and verification debt |
| `SOVEREIGN-DISTILLERY-REPORT.md` | **This document** — consolidated and self-contained |

---

## Closing position

The Sovereign Distillery is a real, buildable subsystem. The concept survives technical review. What does not survive is a specific set of claims that were stated with more confidence than the evidence supports: that the model can grow to 32B on this hardware, that weights can be cloned across model families, that ascending teacher order produces a better model, and that a locally-distilled small model will displace the frontier models currently doing the orchestration.

Removing those four claims does not diminish the project. It converts it from an aspiration into a plan with a measurable terminal state.

**Three decisions block progress: OQ-001 (the seed), OQ-002 (the library inventory), OQ-003 (the acceptance criterion). Two actions cannot be deferred without permanent cost: provenance recording and the frozen evaluation suite. One action should precede all further design: a measured run on the actual GPU.**

*This report is a review. It is not an approval, and it is not a decision. Acceptance belongs to the operator.*
