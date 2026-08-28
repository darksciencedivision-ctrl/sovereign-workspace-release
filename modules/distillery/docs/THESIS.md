# Grounded Distillery
## Deployment-Gated Specialization of Small Language Models from Real Agentic Workloads

**Thesis v1.1 — GitHub Shipping Candidate**

| Field | Value |
|---|---|
| **Project** | Grounded Distillery |
| **Version** | v1.1 |
| **Authors** | Samuel Lawson ([@darksciencedivision-ctrl](https://github.com/darksciencedivision-ctrl)) · [ryguy-pixel](https://github.com/ryguy-pixel) |
| **Status** | GitHub shipping candidate; canonical branch integration complete, with PR #1 open pending treaty-owner review |
| **Canonical joint repository** | `ryguy-pixel/Sovereign-Distillery` |
| **Canonical integration branch** | `integration/grounded-rc3` |
| **Canonical integration commit** | `c3594cfc6284b7b5008bb131434436d5a3a77c9a` |
| **Canonical baseline** | `f1904399ffc8cc357b2d413127b406fedf44b903` |
| **Preserved RC3 provenance** | `a332e68823ab426310c5d37f3c0bfed5c52cc1f0` |
| **Relationship** | Operational specialization branch sharing infrastructure with Sovereign Distillery |
| **Promotion authority** | Human operator only |
| **Default posture** | Fail closed |

---

# 1. Abstract

Grounded Distillery is a locally operated model-development and deployment-gating system for progressively specializing a small language model on one measured agentic workload. It makes a bounded deployment claim: **a candidate is promoted only when the current evaluation contract measures non-regression against its incumbent and a human approves the evidence.** This is not proof of universal or permanent superiority. Source evidence may originate from external providers and is admitted under an explicit source policy. Training runs may regress; the system's job is to catch that and refuse to ship them.

Its central premise is simple:

> **The best data available to a workload specialist is the workload itself.**

Grounded Distillery harvests real trajectories from production agent harnesses, records explicit and implicit outcomes, admits only source-authorized training examples, normalizes and validates them through a shared curation core, and uses them to retrain a small student from base weights on a cumulative corpus. Bounded synthetic channels may expand or repair that corpus, but synthetic data earns its place empirically rather than by assumption.

Candidates are not promoted because training completed, because loss decreased, or because an evaluator liked the prose. A candidate must first demonstrate model-level improvement under controlled serving conditions, then pass a deployment-bundle gate against the incumbent using frozen deterministic, regression, held-out, and advisory evaluation bands. Comparisons are paired per item, uncertainty is reported, and promotion margins are governed by explicit policy thresholds: **M** for minimum useful gain, **T** for maximum tolerated regression versus the immediate incumbent, and **D** for maximum tolerated regression versus historical best.

The deployed unit is the complete serving bundle: model, quantization, system prompt, tool schemas, retrieval configuration, memory configuration, and serving configuration. Promotion is human-authorized, router-based, rollback-capable, and fail closed.

Grounded Distillery does not attempt to replace frontier models. Its student is designed to occupy the bottom rung of an existing delegation ladder: complete an increasing share of routine work locally, recognize when a task exceeds its capability, and escalate accurately.

Grounded Distillery is not a replacement for Sovereign Distillery. The two projects share validators, provenance, immutable shards, exclusion/rebuild machinery, evaluation semantics, experiment records, promotion evidence, and rollback infrastructure. Their objectives remain separate. Grounded specializes against one measured workload. Sovereign researches persistent capability accumulation across a heterogeneous teacher ecosystem and a long-horizon Sovereign model lineage.

---

# 2. Thesis

A small locally trained language model is unlikely to win by competing with frontier laboratories on general capability.

It can win by exploiting a distribution the laboratories do not possess:

- the operator's exact tools;
- recurring task structures;
- workflow conventions;
- failure patterns;
- recovery patterns;
- escalation decisions;
- infrastructure interactions;
- verified incident history;
- successful production trajectories.

This changes the problem.

The goal is not:

> build the strongest small model in the abstract.

The goal is:

> build a model that becomes progressively better at a measured real workload, without allowing regression below explicit deployment floors.

The value of Grounded Distillery therefore comes from four sources:

1. **Distribution match** — the training data is drawn from actual work.
2. **Outcome grounding** — real task success outranks judge preference wherever success can be observed.
3. **Deployment gating** — regression is caught before production.
4. **Compounding operational data** — every real workload interaction can improve the future training set without requiring a separate curriculum-writing project.

---

# 3. Design Principles

## 3.1 Real work defines the curriculum

Curriculum topics come from measured usage, measured failures, and real operational history.

They are not authored from a free-form capability taxonomy and then assumed to matter.

Grounded therefore prioritizes:

```text
real workload
    ↓
measured task types
    ↓
validated training examples
```

over:

```text
invented capability list
    ↓
synthetic curriculum
    ↓
hope
```

The stronger claim that usage-grounded curricula outperform authored curricula is falsifiable and must be tested.

## 3.2 One validator codebase, two jobs

The same deterministic validators are reused for corpus admission and candidate evaluation.

Examples include:

- code versus tests;
- sandbox command exit status;
- exact-answer validation;
- JSON/schema validation;
- structured-output validation;
- tool-call schema validation;
- deterministic file transformations.

A correctness check should not mean one thing during curation and something subtly different during evaluation.

## 3.3 Deployment non-regression, not training perfection

Grounded makes no claim that every training run improves.

Training may regress.

The deployment guarantee is narrower and stronger:

> **No candidate is promoted unless it satisfies the frozen gate's superiority and noninferiority requirements on the measured workload and general-capability floor.**

This guarantee applies only to what the evaluation contract measures.

Grounded does not claim omniscience over unmeasured behavior.

## 3.4 Every sample has lineage

Every admitted example records enough provenance to reconstruct where it came from and why it was allowed to train.

Canonical sample lineage includes:

```text
sample_id
source_trace_id
content_hash
channel
harness
provider
teacher_of_record
teacher_revision
teacher_quantization
source_admission_class
generation_depth
seed_trace_ids[]
derived_from[]
validator_results[]
labels
client_tag
trace_fit_version
normalizer_version
created_at
```

Lineage is immutable after shard sealing.

## 3.5 One synthesis teacher, multi-teacher provenance

Grounded uses one designated synthesis teacher for CH2/CH3/CH-W generation until evidence justifies another.

This is a policy simplification, not a claim that all real data comes from one model.

CH1 gold records the actual `teacher_of_record` for each production trace.

Therefore:

```text
synthesis policy = one designated teacher
corpus provenance = potentially many teachers
```

## 3.6 Instrument first; admit later

Telemetry collection and training permission are separate.

A trace may be observed and measured before it is authorized for training.

Every source is classified:

```text
ELIGIBLE
INTERNAL_ONLY
REJECTED
UNKNOWN
```

Default behavior is fail closed.

```text
UNKNOWN
    ↓
may be observed
may contribute operational statistics
may NOT train
may NOT seed synthetic training data
```

`REJECTED` behaves likewise.

`INTERNAL_ONLY` may train only inside an explicitly authorized internal lineage.

This distinction allows G0 instrumentation to begin immediately while source decisions proceed independently.

## 3.7 Train verbs; retrieve nouns

Weights should primarily learn:

- tool fluency;
- procedural control;
- multi-step execution;
- recovery behavior;
- escalation judgment;
- stable conventions;
- durable abstractions.

Volatile declarative state belongs in retrieval or memory:

- current IP addresses;
- active container IDs;
- temporary paths;
- current service state;
- mutable topology;
- changing resource assignments.

The preferred learned behavior is to retrieve the current fact correctly, not memorize today's fact permanently.

## 3.8 Gate the model scientifically and the bundle operationally

Scientific attribution and production promotion are different questions.

### Controlled model-effect evaluation

Used for experiments such as E1, E2, E5, and E6.

Hold constant:

```text
system prompt
tool schemas
retrieval configuration
memory configuration
sandbox
serving policy
evaluation suite
```

Vary only the declared model/training intervention.

Question:

> Did the training intervention cause measurable model improvement?

### Deployment-bundle evaluation

Used before production promotion.

Evaluate the exact bundle:

```text
model
quantization
system prompt
tool schemas
retrieval config
memory config
serving config
```

Question:

> Is the exact system we are about to deploy better and non-regressive according to policy?

A model may pass a scientific experiment and still fail deployment.

A bundle may outperform operationally without proving that the model weights caused the improvement.

Grounded records the distinction.

## 3.9 The student occupies the bottom rung

The student is not intended to replace the strongest available frontier model.

It competes for the lowest-cost tier of the delegation ladder:

```text
Grounded local student
        ↓ if needed
larger/cheap tier
        ↓
mid-tier frontier
        ↓
top-tier frontier
```

Success means:

- more routine work completed locally;
- lower marginal inference cost;
- correct tool use;
- reliable recovery;
- calibrated escalation;
- fewer unnecessary frontier calls.

A small model that knows when to punt can be more valuable than one that attempts everything.

---

# 4. Architecture

```text
production agent & CLI harnesses
              │
              ▼
          LLM gateway
      ┌───────┴────────┐
      │                │
 local providers   approved remote providers
      │                │
      └───────┬────────┘
              │
       OTel / trace hooks
              │
              ▼
       LOCAL TRACE STORE
              │
              ▼
    SOURCE-ADMISSION CLASS
              │
      ┌───────┴─────────┐
      │                 │
OBSERVED ONLY      TRAINING-ELIGIBLE
                        │
                        ▼
                   CH1 GOLD
             ┌──────────┼──────────┐
             │          │          │
             ▼          ▼          ▼
          CH1-E       CH-W       CH-M
        escalation   incidents   skills
             │
             └──────┬──┴──────────┘
                    │
                    ▼
             CH2 / CH3 SYNTHESIS
                    │
                    ▼
               CURATION CORE
     normalize · trace-fit · validate
     outcome filter · volatile-fact screen
     dedup · diversity · decontamination
     PII/client scrub · source enforcement
                    │
                    ▼
       IMMUTABLE CLIENT-HOMOGENEOUS SHARDS
                    │
                    ▼
           FP16 LoRA FROM BASE
                    │
                    ▼
             candidate model
                    │
        ┌───────────┴────────────┐
        ▼                        ▼
CONTROLLED MODEL-EFFECT       ASSEMBLE
      EVALUATION              BUNDLE
        │                        │
        └──────────────┬─────────┘
                       ▼
               DEPLOYMENT GATE
                       │
                human promotion
                       │
               plan-diff shadow
                       │
                       ▼
                 router promote
                       │
                       ▼
                   local tier
```

---

# 5. Data Channels

| Channel | Source | Depth | Purpose |
|---|---|---:|---|
| **CH1 GOLD** | Real eligible production sessions | 1 | Workload anchor |
| **CH1-E ESCALATION** | Lower-tier failure → higher-tier success joins | 1 | Learn when to escalate |
| **CH2 SILVER** | Variations seeded from eligible CH1 task types | 2 | Controlled amplification |
| **CH3 TARGETED** | Synthetic repair curricula from measured failures | 2 | Gap repair |
| **CH-W INCIDENT** | Real incident/fix records converted to validated scenarios | 2 | Operational repair behavior |
| **CH-M SKILL** | Stable procedures/abstractions nominated by repeated memory use | 2 | Durable skill consolidation |
| **REPLAY** | General instruction corpus | n/a | Forgetting guard |

---

# 6. CH1 GOLD

CH1 is the anchor and contains real work from instrumented harnesses.

Possible outcome states:

```text
marked_good
marked_bad
unlabeled
```

Explicit signals:

```text
/success
/fail
```

Implicit signals may include clean tool exits, successful completion, absence of correction, retry, edit, supersession, and abandonment.

Each session records:

```text
harness
teacher_of_record
provider
model/revision where recoverable
source_admission_class
client_tag
join identifiers
```

Sensitive payloads do not enter Git evidence.

---

# 7. Source Admission

Source admission is a first-class control.

Every source begins:

```text
UNKNOWN
```

Allowed transitions:

```text
UNKNOWN → ELIGIBLE
UNKNOWN → INTERNAL_ONLY
UNKNOWN → REJECTED

INTERNAL_ONLY → ELIGIBLE
INTERNAL_ONLY → REJECTED

ELIGIBLE → INTERNAL_ONLY
ELIGIBLE → REJECTED
```

Each transition records:

```text
provider
model_id
revision
previous_class
new_class
evidence_ref
effective_time
decision_authority
notes
```

A later policy change does not rewrite historical lineage.

If an already-used source becomes disallowed:

1. stop future admission;
2. identify affected ancestry;
3. run transitive exclusion;
4. rebuild where required;
5. re-gate;
6. record remediation.

Current implementation status is intentionally conservative: known candidate sources remain `UNKNOWN` until exact provider/model/revision and output-use authority are established.

---

# 8. CH1-E Escalation

Grounded can mine same-task transitions where a cheaper tier fails or escalates and a higher tier succeeds.

Candidate structure:

```text
task
  ↓
low-tier attempt
  ↓
failure / escalation
  ↓
higher-tier completion
```

Because joins can be noisy, E8 measures pair precision, escalation precision, escalation recall, unnecessary escalation rate, and catastrophic non-escalation rate.

Escalation training activates only if the mined signal proves sufficiently clean.

---

# 9. CH2 SILVER

CH2 expands workload volume through synthetic variations.

Rules:

- seeds come only from eligible CH1 task types;
- synthetic never seeds synthetic;
- `derived_from` is mandatory;
- generation depth is capped;
- synthesis teacher, revision, and quantization are recorded;
- deterministic validation is preferred;
- model judging is residual;
- opening corpus share is bounded;
- CH2 must demonstrate incremental value in E2.

If silver does not outperform gold-only training, it loses its steady-state allocation.

---

# 10. CH3 TARGETED

CH3 exists only after real evaluation failures identify gaps worth repairing.

```text
measured failure
    ↓
targeted curriculum
    ↓
validated synthetic shard
    ↓
next training cycle
```

CH3 is evidence-driven repair, not speculative curriculum generation.

---

# 11. CH-W Incident Channel

Real operational incident records can become training seeds where they capture genuine failure → diagnosis → repair → verification histories.

Examples include service restoration, configuration repair, failed automation diagnosis, deployment recovery, and toolchain repair.

A written incident page alone is not sufficient.

The converted scenario must retain a source reference and pass the relevant validator.

---

# 12. CH-M Skill Consolidation

CH-M does not memorize frequently recalled volatile facts.

It uses repeated memory dependence to nominate stable behaviors that may belong in weights.

Eligible examples:

- durable operating procedures;
- stable conventions;
- transferable diagnostics;
- general decision rules;
- repeatable recovery patterns.

Ineligible by default:

- active IP addresses;
- temporary identifiers;
- live service state;
- mutable paths;
- current machine topology.

Admission requires repeated relevance, outcome association, stability, transferability, and non-volatility.

---

# 13. REPLAY

A general instruction mix protects against catastrophic forgetting.

Opening planning range:

```text
15–30%
```

The value is tunable.

REPLAY is decontaminated against the general-capability floor.

---

# 14. Curation

The curation sequence is:

```text
0. source admission
1. normalize
2. trace-fit
3. deterministic validation
4. outcome filtering
5. residual judge
6. volatile-fact screen
7. deduplication
8. diversity checks
9. eval decontamination
10. PII/client scrub
11. provenance finalization
12. immutable shard seal
```

---

# 15. Immutable Shards and Provenance

Shards are immutable, content hashed, client homogeneous, and provenance complete.

A canonical shard hash covers the manifest and sample hashes.

Mutation creates a new shard/version.

No sealed shard is edited in place.

---

# 16. Transitive Exclusion

Exclusion is a graph operation.

For source `X`:

```text
EXCLUDE(X)
=
X ∪ descendants(X)
```

The rebuild manifest records:

```text
request_id
excluded_roots[]
excluded_nodes[]
excluded_shards[]
retained_shards[]
dangling_edge_count
source_snapshot
created_at
```

PASS requires:

```text
dangling_edge_count == 0
```

Exclusion is idempotent against the same immutable lineage snapshot.

---

# 17. E7 Client Purge Acceptance

The synthetic acceptance graph contains at minimum:

```text
X_root
 ├─ X_child_1
 │    └─ X_grandchild
 └─ X_child_2

Y_root
 └─ Y_child
```

Purging X must prove:

1. X roots removed;
2. direct descendants removed;
3. indirect descendants removed;
4. all X-containing shards removed;
5. no dangling ancestry remains;
6. unaffected Y lineage remains;
7. manifest hashes verify;
8. repeated purge is idempotent.

Current implementation status: synthetic E7 infrastructure has passed; production-client use remains gated separately.

---

# 18. Model Purge Is Not Data-Store Deletion

The rebuild path removes a source from future corpus manifests, retrained ancestry, and subsequently deployed model lineage.

It does not automatically delete raw trace-store rows, exports, archived private shards, or backups.

Those stores require separate retention/deletion policy.

---

# 19. Training Environment

The current training target is a 32 GB gfx906-class GPU in the Vega 20 / MI50 family.

The verified default path is:

```text
torch 2.7
ROCm 6.3
fp16
HF PEFT
TRL
LoRA
```

Operational constraints include:

```text
TORCH_BLAS_PREFER_HIPBLASLT=0
HSA_OVERRIDE_GFX_VERSION=9.0.6
```

The software stack is pinned deliberately because this silicon sits outside the comfortable center of current framework support.

QLoRA on this hardware remains experimental rather than a required dependency.

---

# 20. Student Size

The working candidate range is a planning envelope, not a permanent architecture ceiling.

Grounded currently carries:

```text
4B
vs
8B
```

as the meaningful comparison.

Selection is based on capability, stable sequence length, peak VRAM, throughput, retraining wall clock, and headroom.

"Larger" is not the objective. "Fits" is not the acceptance criterion.

---

# 21. Trainer-Card Lock

Teacher serving and student training may share the same physical GPU.

Before every training run:

```text
1. acquire exclusive card lock
2. drain/evict synthesis serving
3. verify GPU identity
4. verify free VRAM
5. verify no conflicting compute process
6. capture pre-run hardware snapshot
7. train
8. capture post-run hardware snapshot
9. release lock
10. restore serving
```

No lock, no training.

---

# 22. Evaluation Bands

| Band | Content | Role |
|---|---|---|
| **A — Deterministic** | Reproducible validators and exact checks | Hard |
| **B — Regression** | Historical promoted wins | Hard |
| **C — Held-out** | Frozen workload and general floor | Hard where verifiable |
| **D — Advisory** | Judges, style, plan diffs | Advisory |

Band D never overrides a failed hard gate.

---

# 23. Band B Retirement

Band B begins empty.

Each promotion adds representative items for capabilities that earned promotion.

On entry:

```text
remove exact item from training pools
remove exact item from seed pools
block near-duplicates
```

If the workload later retires that capability, the item may leave the active evaluation suite.

Retirement does not make the exact benchmark artifact trainable again.

---

# 24. Band C

Band C is frozen per suite version.

It is divided into:

## Hermetic
Deterministically reproducible and hard-gating.

## Live infrastructure
Dependent on mutable production state and proxy-scored until a hermetic validator exists.

## General-capability floor
Compact general tests plus a generative instruction-following probe.

---

# 25. Statistical Contract

Two uncertainty sources matter.

## Run/decoding variance

Repeated executions characterize stochastic variation.

Opening requirement remains at least five runs per condition where stochasticity exists.

## Item-sampling variance

Rerunning the same small evaluation set does not create new independent workload examples.

Comparisons are paired per item.

Binary outcomes use an appropriate paired binary test.

Scalar outcomes use paired bootstrap/resampling.

Evidence packages report confidence intervals, not bare deltas.

---

# 26. M / T / D

The margins are policy values.

```text
M = minimum useful gain
T = maximum acceptable regression vs immediate incumbent
D = maximum acceptable regression vs historical best
```

The v1.1 default decision contract is:

```text
LCB(Δtarget) >= M
LCB(Δparent) >= -T
LCB(Δbest)   >= -D
```

Default confidence level:

```text
95%
```

M/T/D must be declared before comparative results are inspected.

Power analysis determines whether the evaluation suite can resolve those margins.

It does not choose them.

---

# 27. Historical Best

Historical best is a promotion-time aggregate, not the highest lucky single run.

Minimum record:

```text
capability
checkpoint
suite_version
n_runs
mean
dispersion
confidence metadata
promotion time
```

D compares against that governed historical reference.

---

# 28. Evaluation Suite Versioning

The suite is versioned:

```text
eval_suite_vN
```

Any content change bumps N.

Fresh workload items enter an advisory annex first.

At deliberate suite bumps, annex items may join the frozen core, obsolete workload elements may retire, and historical references may be re-baselined with rationale.

Anti-ratchet must not become anti-adaptation.

---

# 29. Controlled Model-Effect Experiments

For E1/E2/E5/E6 hold constant:

```text
system prompt
tool schemas
retrieval configuration
memory configuration
sandbox
serving policy
eval suite
```

Only the declared intervention changes.

Any unavoidable confound is recorded.

A confounded result may be operationally interesting, but it cannot prove that training caused the gain.

---

# 30. Deployment Bundle

The production artifact is not a bare model file.

Canonical bundle manifest:

```text
bundle_id
model_artifact_hash
quantization
system_prompt_hash
tool_schema_hashes[]
retrieval_config_hash
memory_config_hash
serving_config_hash
created_at
```

The bundle hash is computed over the canonical manifest.

A gate rejects bare model artifacts, missing prompt/config hashes, mutable unversioned retrieval config, and untracked companion files.

---

# 31. Shadow Deployment

Shadow mode is plan-diff only.

It may compare proposed first action, intended tool sequence, escalation choice, and final non-executed answer where appropriate.

It must not execute mutating production tools.

---

# 32. Promotion and Rollback

Promotion is a human decision.

Required sequence:

```text
candidate bundle immutable
        ↓
hard-gate evidence finalized
        ↓
human PROMOTE
        ↓
prior bundle verified
        ↓
atomic router switch
        ↓
health/readiness check
```

If health fails:

```text
router → prior bundle
status = ROLLED_BACK
```

Before first production promotion, staging must prove promote, route verification, rollback, and prior-bundle restoration.

A verified prior bundle is the required rollback target. No rollback target means no promotion.

---

# 33. Shared Grounded / Sovereign Infrastructure

Grounded and Sovereign jointly maintain one canonical implementation of:

- deterministic validators;
- source-admission schema;
- immutable shard schema;
- provenance fields;
- dependency graph;
- transitive exclusion/rebuild;
- Bands A–D;
- paired statistical tooling;
- power-analysis tooling;
- M/T/D semantics;
- historical-best records;
- controlled model-effect evaluation;
- experiment-record schema;
- exact deployment-bundle gating and evidence;
- human-governed promotion;
- rollback metadata;
- trainer-card locking.

Grounded-specific modules remain focused on:

- workload telemetry;
- Grounded curation policy;
- harness adapters;
- Grounded CLI/policy.

Shared infrastructure should exist once.

---

# 34. Relationship to Sovereign Distillery

Grounded Distillery and Sovereign Distillery are sibling projects with different research questions.

## Grounded Distillery

> How can a small model become progressively better at one measured operational workload without deployment regression below governed floors?

Primary methods:

- real traces;
- outcome grounding;
- one synthesis teacher;
- workload specialization;
- local-tier deployment;
- escalation training;
- from-base retraining;
- deployment gating.

## Sovereign Distillery

> How can a persistent model lineage acquire and accumulate useful capability from a heterogeneous teacher ecosystem under a measured compute envelope?

Primary methods may include:

- multiple teachers;
- capability-delta analysis;
- behavioral distillation;
- synthetic capability curricula;
- compatible adapter or parameter-transfer experiments;
- persistent Sovereign model lineage;
- future architecture/scale research;
- native Sovereign trajectory, including eventual native Sovereign architecture.

Evidence flows between Grounded and Sovereign as evidence only. It does not automatically become policy for either project.

One workload proving that one synthesis teacher is enough does not invalidate heterogeneous teacher research.

One 4B/8B student result does not impose a permanent Sovereign scale ceiling.

---

# 35. Research Questions

### RQ1 — Workload specialization
Can outcome-filtered real workload traces produce measurable gains above the instruct/base model?

### RQ2 — Synthetic amplification
Does bounded workload-seeded synthetic data add incremental value above gold-only training?

### RQ3 — Curriculum grounding
Does usage-seeded synthetic curriculum outperform authored taxonomy curriculum at equal volume?

### RQ4 — Judge calibration
How often do model judges disagree with deterministic or observed outcomes?

### RQ5 — Preference mining
Are retry/edit-derived preference pairs precise enough to support DPO?

### RQ6 — Student scale
Does the 4B or 8B candidate provide the better operational tradeoff under the actual trainer?

### RQ7 — Purgeability
Can a source and all descendants be provably removed from a rebuild lineage?

### RQ8 — Escalation
Can the student learn to escalate with better precision/recall than the stock incumbent?

### RQ9 — Retrieval counterfactual
Are apparent training gains merely benefits already obtainable from live retrieval?

### RQ10 — Synthesis quantization
Does a cheaper low-bit synthesis teacher materially degrade accepted training data?

---

# 36. Evidence Plan

| Experiment | Question |
|---|---|
| **E1** | Does GOLD SFT improve the student above the frozen threshold? |
| **E2** | Does GOLD+SILVER improve over GOLD-only? |
| **E2b** | Does usage-seeded SILVER beat authored-taxonomy SILVER? |
| **E3** | How often do judges disagree with observed outcomes? |
| **E4-pre** | Are mined preference pairs sufficiently precise? |
| **E4** | Does DPO add value beyond SFT? |
| **E5** | Include or strip reasoning tokens? |
| **E6** | 4B vs 8B operating envelope and capability? |
| **E7** | Does transitive client exclusion/rebuild work? |
| **E8** | Are escalation joins precise and useful? |
| **E9** | Is apparent training gain actually retrieval gain? |
| **E10** | Does cheaper synthesis quantization degrade validated data? |

---

# 37. Falsification Commitments

The thesis must be allowed to fail.

- If E1 shows no gain above uncertainty at realistic corpus volume, Grounded may be premature for the workload.
- If E2 shows no incremental value, CH2 loses steady-state allocation.
- If E2b shows authored curricula perform equivalently or better, the strong usage-grounding claim is rejected.
- If E4-pre fails, DPO does not activate from those mined pairs.
- If E8 joins are mostly noise, automatic escalation supervision loses its premise.
- If E9 shows retrieval accounts for the supposed model improvement, that gain is not attributed to the weights.
- If E7 cannot guarantee descendant closure, purgeability claims do not ship.
- If shadow/advisory evidence repeatedly contradicts hard-gate decisions, the evaluation contract itself must be investigated.

**Teacher-of-record and source admission.** *(stated plainly in v1.1 because v1.0 did not.)* Gold traces are produced by whatever model served the session, which for this fleet includes external providers accessed through the gateway. Training a locally deployed student on provider outputs may conflict with provider terms or policy. A thesis that sells provable data governance does not get to leave its own inputs' authority unexamined. D-9 is therefore an explicit, per-provider/model/revision admission decision. Privacy-minimized G0 telemetry can be collected while classification proceeds; `UNKNOWN` fails closed before curation or training. This document takes no position on admission without primary evidence and operator authority.

Results are findings, not embarrassments to edit out of the thesis.

---

# 38. Failure-Mode Register

| Failure mode | Primary control |
|---|---|
| Recursive synthetic collapse | Depth cap, real seeding, replay, diversity |
| Teacher-error amplification | Outcomes, deterministic validators, masking |
| Judge bias | Residual-only judging, disagreement logging |
| Label decay | Explicit marks + implicit outcomes + monitoring |
| Selection bias | Sample mundane implicit positives |
| Operator steering contamination | Periodic label audit |
| Eval contamination | Frozen pools + decontamination |
| Band B contamination | Permanent exact-item exclusion |
| Replay contamination | Decontaminate against floor |
| Gate on noise | Pairing + confidence intervals |
| Underpowered evaluation | G2 power analysis |
| Ratchet decay | Historical-best D |
| Anti-adaptation ratchet | Deliberate retirement |
| Catastrophic forgetting | REPLAY + general floor |
| Quantization drift | Gate the deployed quant |
| Bundle confounding | Controlled model-effect evaluation |
| Client-data leakage | Scrub + provenance + exclusion |
| Volatile-fact staleness | Train verbs, retrieve nouns |
| Instrumentation clobber | External hooks + checksum guards |
| DPO mislabeling | E4-pre |
| Shadow side effects | No mutating execution path |
| Source-license contamination | Fail-closed source admission |
| Capacity scope creep | Grounded/Sovereign treaty |
| Retraining cadence collapse | Cost curve + future curation |

---

# 39. Build Phases

## G0 — Instrument

Required acceptance cases:

- **G0-A:** real success session with stable joins and `/success`.
- **G0-B:** real failure session with `/fail`.
- **G0-C:** failure → recovery → success with maskable failure and retained recovery arc.
- **G0-D:** trace from an `UNKNOWN` source is collected but rejected from training and synthetic seeding.

Also required:

- implicit positive signals;
- implicit negative signals;
- accrual dashboard;
- label-compliance dashboard;
- rejection metrics;
- no-trace/no-label alert;
- instrumentation checksum guard.

Current state: **PASS**. Live G0-A/B/C/D acceptance passes using privacy-minimized evidence. Implicit-signal coverage, accrual and label-compliance dashboards, rejection metrics, no-trace/no-label alerts, and instrumentation checksum guards also pass. This establishes HG-0; it does not authorize training, promotion, or deployment.

## G1 — Data Integrity and Training Readiness

Implement and prove source-admission enforcement, normalizers, trace fitting, CH1 miner, volatile-fact screen, immutable shard sealing, transitive exclusion, E7, 4B/8B architecture smoke, and E4-pre.

Current state: software foundation substantially implemented. HG-3 architecture smoke and HG-4 human pair audit remain blockers.

## G2 — Evaluation Freeze

Build and freeze Bands A–D, hermetic/live Band C partition, general floor, paired statistics, historical-best store, M/T/D, item-count power analysis, and `eval_suite_v1`.

## G3 — Student Micro-Runs

Measure 4B and 8B candidates on the real trainer.

## G4 — GOLD-Only Run

```text
source-admission snapshot
    ↓
eligible GOLD + REPLAY manifest
    ↓
freeze dataset hash
    ↓
train from base
    ↓
controlled model-effect evaluation
    ↓
E9 retrieval counterfactual
    ↓
merge/quantize
    ↓
assemble exact bundle
    ↓
deployment-bundle gate
    ↓
human decision
```

## G5 — GOLD + SILVER A/B

Controlled comparison:

```text
GOLD ONLY
vs
GOLD + SILVER
```

If silver does not demonstrate incremental benefit, disable it in steady state.

## G6 — Steady State

Features activate only when their prerequisites pass.

---

# 40. Hard Gates

| Gate | Meaning |
|---|---|
| **HG-0** | Real telemetry acceptance |
| **HG-1** | Source admission |
| **HG-2** | Transitive exclusion / E7 |
| **HG-3** | Exact student architecture smoke |
| **HG-4** | Preference-pair audit |
| **HG-5** | Frozen evaluation contract |
| **HG-6** | Valid controlled model-effect result |
| **HG-7** | Exact deployment-bundle pass |
| **HG-8** | Explicit human promotion |

No hard gate is replaced with a warning.

---

# 41. Current Evidence State

The current canonical integration milestone establishes software foundations, not production completion.

## Canonical repository integration

```text
repository: ryguy-pixel/Sovereign-Distillery
branch: integration/grounded-rc3
commit: c3594cfc6284b7b5008bb131434436d5a3a77c9a
baseline: f1904399ffc8cc357b2d413127b406fedf44b903
```

The RC3 implementation lineage is preserved:

```text
a332e68823ab426310c5d37f3c0bfed5c52cc1f0
```

## Implemented software evidence

Current reported integration results:

- original RC3 suite: **23/23 passed**;
- integrated suite: **27/27 passed**;
- shared validators/admission/schema/exclusion/gate/evidence/promotion/card-locking centralized;
- Grounded-only telemetry/curation/CLI/adapters remain separate;
- live G0-A/B/C/D, dashboards, alerts, rejection metrics, and checksum guards: **PASS**;
- all current D-9 source candidates remain `UNKNOWN` and fail closed for training and synthetic seeding;
- PR #1 is open against `main` and remains unmerged pending owner review;
- no model weights, private corpus, or secrets staged;
- no G2–G6 execution performed;
- no production promotion or deployment performed;
- no repository-wide license decision has been made.

## Hard-gate state

| Gate | Current state |
|---|---|
| HG-0 | **PASS** |
| HG-1 | **software PASS; real source decisions pending** |
| HG-2 | **PASS on synthetic E7 acceptance** |
| HG-3 | **BLOCKED** |
| HG-4 | **BLOCKED** |
| HG-5 | **NOT REACHED** |
| HG-6 | **NOT REACHED** |
| HG-7 | **NOT REACHED** |
| HG-8 | **NOT REACHED** |

This thesis must not describe Grounded as production-proven while those states remain.

---

# 42. Security and Privacy Boundary

Grounded's model-development pipeline keeps on operator-controlled infrastructure:

- trace persistence;
- curation;
- corpus construction;
- training;
- evaluation;
- provenance;
- exclusion/rebuild;
- model artifacts;
- promotion records;
- Grounded deployment.

Production traces may originate from local or approved remote teachers.

The accurate claim is:

> Grounded does not export its private training corpus, model-development artifacts, or locally trained candidate to an external training service.

A stricter `LOCAL_ONLY` deployment profile may be used where no remote inference is permitted.

---

# 43. Repository Boundary

The Git repository may contain:

```text
README.md
docs/
schema/
validators/
source_admission/
curation/
exclusion/
gate/
train/
ops/
grounded/
tests/
runs/metadata-only-evidence
```

It must not contain raw production prompts, raw production outputs, private client traces, private corpora, model weights, GGUF artifacts, model caches, virtual environments, credentials, secrets, or private database dumps.

---

# 44. Governance

Human authority is explicit.

Automation may collect, validate, train, evaluate, assemble evidence, recommend, and prepare a candidate.

Automation may not silently classify ambiguous sources as eligible, redefine M/T/D, mutate frozen evaluation suites, change project scope, promote itself, or deploy without authorization.

Promotion requires an explicit human decision.

---

# 45. Commercial Interpretation

Appropriate claims after evidence exists may include:

- workload-specialized local inference;
- outcome-grounded model improvement;
- gated non-regressive deployment on the measured workload;
- source-level provenance;
- transitive model-lineage exclusion;
- local model-development workflow;
- rollback-capable deployment.

Do not claim universal non-regression, universal deletion of every copy of client data, legal eligibility of every teacher output, frontier-equivalent general intelligence, or guaranteed improvement from every training cycle.

---

# 46. Relationship to the Larger Workspace

Grounded is one operational branch of a larger model-development and orchestration workspace.

Its deeper contribution is a hardened shared laboratory for:

- provenance;
- source eligibility;
- immutable datasets;
- transitive exclusion;
- controlled training experiments;
- regression tracking;
- historical-best governance;
- exact serving-bundle evaluation;
- promotion evidence;
- rollback.

Those capabilities strengthen Sovereign Distillery without shrinking Sovereign's broader objective.

---

# 47. What Grounded Explicitly Does Not Do

Grounded v1.1 does not:

- replace Sovereign Distillery;
- eliminate heterogeneous teacher research from Sovereign;
- define a permanent Sovereign model-size ceiling;
- require every teacher to contribute;
- claim one synthesis teacher is universally optimal;
- fine-tune teacher-scale models merely because 32 GB VRAM makes some experiments possible;
- auto-promote;
- use judges as primary truth;
- allow synthetic depth to grow without governance;
- train on unknown sources;
- execute mutating shadow actions;
- silently recycle held-out evaluation items into training.

---

# 48. Immediate Next Milestone

After PR #1 reconciliation and owner review:

```text
PRESERVE HG-0 PASS
       +
CONTINUE FAIL-CLOSED SOURCE RESEARCH
       ↓
HG-3 real 4B/8B architecture smoke
       ↓
HG-4 E4-pre audit
       ↓
G2 evaluation freeze
```

G2–G6 remain intentionally blocked until their prerequisites are satisfied.

---

# 49. Conclusion

Grounded Distillery is not a claim that a small local model can become universally superior to frontier systems.

It is a disciplined attempt to exploit a narrower and more defensible advantage:

> **the operator owns a workload distribution that no general model provider possesses in full.**

Grounded turns that workload into a measured training signal.

It observes real trajectories, separates collection from training authority, admits data fail closed, preserves provenance, validates deterministic outcomes, excludes sources transitively, retrains from a governed base, measures causal model effects under controlled conditions, evaluates the exact serving bundle before deployment, protects historical capability through M/T/D, and leaves final promotion under human authority.

Its intended product is not merely a fine-tuned model.

Its intended product is a **repeatable improvement system**:

```text
REAL WORK
   ↓
MEASURE
   ↓
CURATE
   ↓
TRAIN
   ↓
CONTROLLED EVALUATION
   ↓
DEPLOYMENT GATE
   ↓
PROMOTE OR REJECT
   ↓
MORE REAL WORK
```

The loop is valuable only if it remains falsifiable.

If gold does not help, that is evidence.

If silver does not help, remove it.

If retrieval explains the gain, do not credit the weights.

If escalation supervision is noisy, do not train it.

If source eligibility is unknown, do not admit it.

If a candidate regresses, do not promote it.

If the evaluation suite cannot resolve the desired policy margins, enlarge the suite or admit that the effect cannot yet be established.

That is the operating philosophy of Grounded Distillery v1.1:

> **Instrument honestly. Admit fail closed. Preserve lineage. Exclude transitively. Train from evidence. Measure causally. Gate what actually ships. Promote deliberately. Roll back safely. Let experiments decide what survives.**

---

# 50. References

- Hinton, G., Vinyals, O., Dean, J. (2015). *Distilling the Knowledge in a Neural Network.*
- Hu, E. et al. (2021). *LoRA: Low-Rank Adaptation of Large Language Models.*
- Lewis, P. et al. (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.*
- Rafailov, R. et al. (2023). *Direct Preference Optimization: Your Language Model is Secretly a Reward Model.*
- Shumailov, I. et al. (2024). *AI models collapse when trained on recursively generated data.*
- Zelikman, E. et al. (2022). *STaR: Self-Taught Reasoner — Bootstrapping Reasoning With Reasoning.*
- Zheng, L. et al. (2023). *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.*
- Zhou, J. et al. (2023). *Instruction-Following Evaluation for Large Language Models (IFEval).*

---

## Release Note

This v1.1 thesis incorporates:

- the Grounded/Sovereign infrastructure treaty;
- RC3 fail-closed builder hardening;
- source-admission separation from telemetry;
- transitive exclusion;
- controlled model-effect evaluation;
- exact deployment-bundle gating;
- variance-aware historical best;
- Band B retirement semantics;
- stable-skill CH-M semantics;
- gfx906 trainer constraints;
- canonical joint-repository integration;
- current live G0 and hard-gate evidence state.

Future substantive thesis changes after freeze require a version bump and run evidence.
