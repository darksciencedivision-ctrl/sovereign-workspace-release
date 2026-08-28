# Sovereign Distillery — Canonical Specification v0.1 (PROVISIONAL)

**Status:** PROVISIONAL — blocked on OQ-001 (seed decision), OQ-002 (library inventory), OQ-003 (v1 acceptance criterion)
**Authority:** The human operator owns objectives, scope, promotions, and acceptance. This specification records; it does not decide.
**Companion documents:** `00-VALIDATION-REVIEW.md` (findings this spec responds to), `02-OPEN-QUESTIONS.md` (unresolved decisions), `decisions/` (ADRs)

> **Reading note.** Sections marked **[APPROVED]** restate operator-stated objectives. Sections marked **[PROPOSED]** are reviewer proposals awaiting operator acceptance. Sections marked **[BLOCKED]** cannot be completed until a named open question is resolved. Nothing here overrides operator direction.

---

## 1. Mission [APPROVED — operator-stated]

The Sovereign Distillery is the model-forging subsystem of the Sovereign Research Workspace.

It processes the local model library in ascending size order. For each model, it treats that model as a **teacher**, extracts the capability that teacher demonstrably contributes, and uses that extracted material to train the persistent **Sovereign model** — a single evolving student lineage. Each stage produces a new immutable Sovereign checkpoint. The intended end state is a Sovereign-owned model family that can be wrapped, quantized to available hardware, and deployed as an intelligence layer inside the Sovereign system.

**Distinction from the sibling subsystems:** Sovereign, the Debate Table, and the Multi-Model App *use* models. The Distillery *produces* them.

---

## 2. Invariants

These are non-negotiable properties of the system. A change to any of them is a specification change, not an implementation detail.

| ID | Invariant | Origin | Rationale |
|---|---|---|---|
| **INV-1** | **The Sovereign checkpoint is never overwritten.** Every training run produces a new immutable candidate with a new identifier. Promotion changes a pointer, never a file. | Design conversation (ADD-2) | Rollback is the only defence against silent regression. Cheap. |
| **INV-2** | **Every training example carries provenance.** Teacher identity, teacher version/quantization, generation run, prompt source, timestamp, and license class are recorded at generation time, not reconstructed later. | Reviewer (F-6) | A cumulative lineage cannot be de-contaminated after the fact. |
| **INV-3** | **No checkpoint is promoted without passing the frozen evaluation suite**, including the regression subset covering every previously acquired capability. | Reviewer (F-7) | Without this INV-1 provides rollback ability but no rollback signal. |
| **INV-4** | **Distillation is offline and black-box by default.** Teacher generates → corpus is persisted → student trains in a separate process. Teacher and student are never required to be co-resident in VRAM. | Reviewer (F-1, F-2b) | Hardware constraint, not preference. 8 GB VRAM forecloses co-resident white-box KD. |
| **INV-5** | **The canonical master model and the quantized deployment artifacts are separate objects.** Quantization is a deployment transformation applied to a promoted master; it never defines the master. | Design conversation (ADD-5) | Prevents lossy artifacts entering the training lineage. |
| **INV-6** | **The evaluation suite is frozen before it is used and is versioned separately from the models.** Any change to the suite invalidates cross-generation comparison and must be recorded as a suite version bump. | Reviewer (F-7, R-7) | A moving ruler measures nothing. |
| **INV-7** | **Held-out evaluation data is never used for corpus generation.** | Reviewer (R-7) | Contamination inflates measured gains. |

---

## 3. Objects

### 3.1 Teacher
A model from the local library, used as a source of behaviour. Never modified. Record: name, family, architecture, parameter count, quantization, tokenizer, on-disk size, license identifier, license class (see §6), source URL, hash.

### 3.2 Sovereign checkpoint
An immutable trained student artifact. Identifier form `SOV-D<NNN>`.

Required lineage record per checkpoint:

```
SOV-D017
├── parent_checkpoint      SOV-D016
├── teacher(s)             [Model-X @ version, quant]
├── corpus_manifest_hash   sha256:...
├── training_config_hash   sha256:...
├── base_architecture      <arch>
├── parameter_count        <n>
├── precision              <fp16 | bf16 | 4bit-nf4 | ...>
├── eval_suite_version     v<N>
├── eval_results           {task: score}
├── regression_results     {prior_capability: delta}
├── capability_delta       {gained: [...], lost: [...]}
├── license_classes_used   [permissive | restricted-A | ...]
├── wall_clock_hours       <n>
└── promotion_decision     {promoted | rejected | quarantined} + operator signature
```

### 3.3 Corpus shard
A set of generated training examples from one teacher in one generation run. Carries the INV-2 provenance block. Immutable once written.

### 3.4 Evaluation suite
Versioned, frozen. Composed of (a) deterministic machine-checkable tasks, (b) a regression subset that grows as capabilities are acquired, (c) a private held-out set never used for generation. See §5.

### 3.5 Deployment artifact
A quantized, hardware-targeted derivative of a promoted master. `SOV-LM-Q4`, `SOV-LM-Q6`, etc. Never a parent of anything.

---

## 4. Lifecycle

For each teacher, in ascending size order:

```
 1. INGEST      register teacher; record architecture, tokenizer, license, hash
 2. GATE        license class check → permitted / restricted / rejected      [§6]
 3. CHARACTERIZE measure teacher on the frozen eval suite                     [§5]
 4. DIFFERENTIAL compare teacher scores vs current Sovereign checkpoint scores
                 → capability delta = {tasks where teacher > student by margin M}
 5. DECIDE      delta empty → SKIP this teacher, record the skip and why
                 delta non-empty → proceed
 6. CURRICULUM  build prompt set targeting only the delta capabilities
 7. GENERATE    teacher produces outputs; provenance stamped per example     [INV-2]
 8. FILTER      verification pass — reject unverifiable/incorrect outputs    [§7]
 9. MIX         new shard + replay of prior corpus + non-synthetic fraction  [§8]
10. TRAIN       QLoRA/LoRA on the current Sovereign checkpoint → candidate
11. EVALUATE    full frozen suite, including full regression subset          [INV-3]
12. ADJUDICATE  optional Debate Table adversarial pass (advisory, not a gate)
13. PROMOTE     operator decision; candidate becomes new parent, or quarantined
14. RECORD      lineage entry written; corpus manifest sealed
```

**Step 5 is load-bearing and was identified as a contradiction in review (C-3):** if the seed is competent, the smallest teachers will produce an empty delta and will be legitimately skipped. That is a correct outcome, not a failure. The value of running them first is pipeline validation at low cost (F-3), which step 5 preserves.

**Step 12 is advisory.** Debate Table output is recorded as a signal. It does not gate promotion (F-7, A-6).

---

## 5. Evaluation [PROPOSED — highest priority, precedes all training]

**Build order rule: the evaluation suite is constructed and frozen before the first teacher is processed.** Reviewer position: no training run should occur before this exists, because the result would be uninterpretable.

Composition:

| Band | Content | Scoring |
|---|---|---|
| **Deterministic** | Code that compiles/executes against unit tests; math with checkable answers; structured extraction with exact-match; instruction-following with programmatic constraint checks (format, length, forbidden tokens) | Exact / pass-rate. No model in the loop. |
| **Regression** | Every capability the lineage has previously demonstrated. Grows monotonically — items are added on promotion and never removed. | Delta vs. best prior checkpoint. Any negative delta beyond tolerance blocks promotion. |
| **Held-out** | Private. Never used for prompt generation, never shown to a teacher. | Same instruments as Deterministic. Primary anti-contamination control. |
| **Advisory** | Debate Table adversarial comparison, subjective quality, open-ended reasoning | Recorded, not gating. |

**Promotion rule [PROPOSED]:** a candidate is promotable only if (a) it improves on at least one targeted delta capability by a stated margin, and (b) it does not regress any regression-band item beyond tolerance. Both margin and tolerance are operator-set numbers, currently **UNSET** — see OQ-005.

---

## 6. License gating [PROPOSED — evidence currently weak, see F-6]

At ingestion each teacher is assigned a license class. Proposed classes:

| Class | Meaning | Corpus handling |
|---|---|---|
| `PERMISSIVE` | MIT / Apache-2.0 style; no derivative-naming or use-field restrictions | Freely mixed |
| `RESTRICTED-NAMING` | Derivative-model naming and/or attribution obligations propagate | Shard tagged; lineage flagged |
| `RESTRICTED-USE` | Field-of-use, non-commercial, or scale caps | Shard tagged; must be excludable |
| `REJECTED` | Terms incompatible with intended use | Not ingested |

**Current evidence status:** the class assignments implied by the source material (`E-11` in the review) are drawn from secondary sources and are **UNVERIFIED**. Every teacher's primary license text must be read before its class is fixed. This is tracked as MISSING-8.

**Structural requirement regardless of class assignment (INV-2):** because the lineage is cumulative, the system must be able to answer "rebuild this lineage excluding teacher X" at any time. That capability is free if provenance is recorded from example one and impossible if it is not.

---

## 7. Generation filtering [PROPOSED]

Distillation propagates teacher errors (R-2). Every generated example passes a verification gate before entering a corpus shard:

| Data type | Verification |
|---|---|
| Code | Execute against tests. Reject on failure. |
| Math / computation | Deterministic re-check. Reject on mismatch. |
| Structured output | Schema validation. Reject on parse failure. |
| Factual claims | Multi-teacher agreement threshold, or drop. Unverifiable factual generation is the weakest category and should be minimized rather than filtered. |
| Style / format | Programmatic constraint check. |

Rejection rate is a tracked metric per teacher. A teacher with a high rejection rate is itself a finding.

---

## 8. Corpus mixing [PROPOSED — mitigates R-1, R-3]

Strictly sequential training on a single new teacher is the configuration most vulnerable to catastrophic forgetting. Each training mix therefore contains:

- The new teacher's filtered shard (the targeted delta)
- **Replay** — a sampled fraction of all previously accepted shards
- A **non-synthetic fraction** — human-authored data, to resist model-collapse / diversity narrowing across generations

Ratios are **UNSET** and are operator/experiment decisions — see OQ-006.

**Note on tension with the operator directive:** replay mixing is in mild tension with the strict "one teacher at a time" framing. The reviewer's position is that the *ordering* is preserved (teachers are still introduced smallest-to-largest, one at a time) while the *training mix* is cumulative. If the operator intends strictly single-teacher training mixes, R-1 becomes near-certain and should be accepted knowingly.

---

## 9. Hardware envelope [BLOCKED on measurement — see F-1, MISSING-5/7]

**Stated hardware:** NVIDIA RTX 5060 Ti, 8 GB VRAM (Blackwell, sm_120).

Modelled constraints (secondary-source estimates, **not measured on this machine**):

| Operation | Estimate | Verdict on 8 GB |
|---|---|---|
| QLoRA 7B (4-bit NF4, r=64, bs=1, seq=512, no grad-ckpt) | ~8 GB | At/over margin |
| QLoRA 14B | ~14 GB | Not possible |
| QLoRA 32B | ~28 GB | Not possible |
| Full fine-tune 7B | ~88 GB | Not possible |
| Co-resident teacher + student (white-box KD) | ~2× student | Not possible for non-trivial teachers |

**Working envelope [PROPOSED, pending measurement]:** student size **1B–3B**, QLoRA 4-bit, gradient checkpointing on, short-to-moderate sequence length. A 7B student is an experiment to attempt and measure, not a plan to depend on.

**Architecture growth (3B → 7B → 14B → 32B) is REMOVED from v1 scope** per F-1/C-1/C-5, pending an operator decision on whether training bursts to rented compute (OQ-004).

**Required first action:** a measured hello-world QLoRA run on this GPU with this toolchain, to convert the above estimates into measurements and to establish whether the sm_120 toolchain (driver, CUDA, PyTorch, bitsandbytes/Unsloth kernels) is functional. Until that run exists, every number in this section is an estimate.

---

## 10. Integration with the Sovereign Workspace [BLOCKED — repos not inspected]

The design conversation assigned these roles. **All are currently ASSUMPTIONS** (A-9); no sibling repository has been read.

| Subsystem | Assigned role | Status |
|---|---|---|
| **Multi-Model App** | Extraction and experimentation surface — drives teacher generation, coordinates multiple models | `ASSUMPTION` — interface unknown |
| **Debate Table** | Adversarial comparison of candidate vs. parent vs. teacher; advisory signal only (§4 step 12) | `ASSUMPTION` — interface unknown |
| **Sovereign** | Orchestration, provenance store, long-running workflow state, experiment memory | `ASSUMPTION` — interface unknown |
| **Distillery** | Owns the lifecycle in §4 end to end | Defined here |

No integration contract may be written into this specification until the three repositories are inspected. Tracked as MISSING-4.

**Design constraint asserted now to protect against later coupling:** the Distillery must be operable standalone. If the Debate Table is unavailable, step 12 is skipped and promotion still functions on the deterministic suite. A model-production pipeline that cannot run without three other applications is a fragility, not an integration.

---

## 11. Directory layout [PROPOSED]

```
D:\Sovereign Distillery\
├── docs\                    specifications, reviews, decisions, evidence
├── registry\                teacher registry, license classifications
├── evals\                   frozen suites, versioned; held-out set access-controlled
├── curricula\               prompt sets per capability
├── corpora\                 immutable shards + manifests + provenance
├── runs\                    training run configs, logs, metrics
├── checkpoints\             immutable Sovereign lineage
├── lineage\                 lineage records, promotion decisions
├── deploy\                  quantized artifacts (never parents)
└── tools\                   pipeline code
```

Not yet created — creation awaits acceptance of this specification.

---

## 12. v1 acceptance criterion [BLOCKED — OQ-003]

**Currently undefined.** Without it the project has no terminal state (R-11).

Reviewer's proposed shape, for operator consideration only: *"One named capability, measured on the frozen deterministic suite, where the promoted Sovereign checkpoint scores at or above a stated threshold, with no regression-band item degraded beyond tolerance, with full provenance from teacher to checkpoint reproducible from the lineage record."*

That is a falsifiable claim. "Sovereign has its own LLM" is not.

---

## 13. Change control

This specification is versioned. Changes to §2 (Invariants), §1 (Mission), or §12 (Acceptance) require explicit operator approval and a dated entry below.

| Version | Date | Change | Approved by |
|---|---|---|---|
| v0.1 | 2026-08-19 | Initial provisional draft, blocked on OQ-001/002/003 | *pending operator review* |
