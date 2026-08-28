# GROUNDED DISTILLERY — Unified Design v1.1 — DRAFT

| | |
|---|---|
| **Amends** | the frozen v1.0 specification (private, 2026-08-19), which remains the frozen reference until this draft passes joint review |
| **Thesis** | `docs/THESIS.md` (v1.1). Lawson's validators and gate formalism; the operator's data and teacher. Real usage anchors the distribution; validated synthesis provides the volume; a variance-calibrated, **paired-per-item** banded gate provides the only honest version of "always an upgrade" — delivered into the one slot where an upgrade is both winnable and worth money: the bottom rung of the fleet's delegation ladder. |
| **Date** | 2026-08-19 |
| **Status** | **DRAFT — proposed v1.0 → v1.1 bump, pre-run.** v1.0's amendment rule requires a version bump plus run evidence; no runs exist yet. Justification for a pre-run bump: (a) the trainer card changed (6 GB consumer-card assumption → 32 GB gfx906-class card, verified training-capable), which invalidates §5 of v1.0 as written; (b) an external adversarial review (Claude, 2026-08-19) found defects in claims the frozen text already makes (gate statistics, teacher-of-record, shadow semantics) that are cheaper to fix on paper than at run 3. Freeze requires joint sign-off per the §10 treaty. Changes after freeze revert to the evidence rule. |

Operational branch for the operators' production agentic workload. Sovereign Distillery continues separately as the research architecture; §10 defines the shared-infrastructure contract. §13 is the full v1.0 → v1.1 changelog for review.

---

## 1. Principles

1. **Data comes from real work; volume comes from synthesis seeded by real work.** A curriculum is only legitimate when its topics are sampled from measured usage and measured weaknesses — never from a self-authored capability taxonomy. Measured usage includes the operator's written incident record (§3, CH-W).
2. **One validator codebase, two jobs.** The same deterministic checks (code-vs-tests, sandbox exit codes, schema validation, exact-answer checks) filter training data at curation time and score candidates at eval time. Write once, trust twice.
3. **"Always an upgrade" is a deployment property.** Training runs will regress sometimes. The guarantee is: nothing regressive gets promoted, promotion margins sit above the measured noise floor *with pairing doing the statistical work repetition cannot*, a human makes the final call, and rollback is a router flip.
4. **Every sample carries lineage.** Channel, `harness`, `teacher_of_record`, generation depth, seed trace, validator results, client tags. Any model must be rebuildable *excluding any source*.
5. **One synthesis teacher.** Qwen3.8-27B until a second wins an eval-based case. No queues, no zoos. *Amended:* this governs **CH2/CH3/CH-W generation only**. CH1 gold's teacher-of-record is whatever model served the session — for this fleet, substantially frontier models accessed through the gateway — recorded per sample. The corpus is multi-teacher by construction; the synthesis channel is not. D-9 source admission must be decided before any affected trace enters curation or training; it does **not** block privacy-minimized G0 telemetry collection.
6. **Measure before plan.** Throughput, training envelope, corpus-size-vs-delta, and the card calendar are estimates until run 1, then they are measurements and the estimates are deleted.
7. **Train verbs, retrieve nouns.** *(new)* Weights carry behaviors: tool fluency, multi-step control, recovery patterns, escalation judgment. Volatile declarative facts (addresses, container IDs, service states, paths) belong to the live retrieval/memory layers the deployed system already consults. Curation prefers samples that demonstrate looking facts up over samples that assert facts which rot.
8. **Gate the bundle.** *(new)* The artifact under test is model + system prompt + tool schemas + retrieval/memory configuration, versioned as one unit. That is what the router flips; nothing else is "the deployed system."
9. **The student ships into the ladder's bottom rung.** *(new)* The incumbent it must beat is the current local-tier model, not a frontier model. Every promotion measurably increases the share of fleet work done at zero marginal cost — and the student is trained to escalate correctly when a task exceeds it.

## 2. Architecture

```
agent & CLI harnesses ─────────► LLM gateway (per-harness key = channel tag)
 (coding · chat · assistant)          │──OTel──► trace store
 existing trace hooks joined ────────►│           labels · scores · join keys
      │ trajectory export: /harness-adapters normalizers → ShareGPT
      ▼
 CH1 GOLD ◄──seeds── CH2 SILVER   CH3 TARGETED   CH-W WIKI    CH-M CONSOL
 real traces,        synthetic    gap-repair     incident-    memory→weights
 all harnesses       (Qwen 27B)   curriculum     seeded       (memory layer)
 depth 1             depth 2      depth 2        depth 2      depth 2
      │                 │             │              │             │
      └──────────┬──────┴─────────────┴──────────────┴─────────────┘
                 ▼                                          ▲
        CURATION CORE                                       │
        normalize · trace-fit · validators · outcome        │
        filters · volatile-fact screen · dedup/diversity    │
        decontam · PII scrub → immutable hashed shards      │
        (client-homogeneous)                                │
                 ▼                                          │
        TRAIN — PEFT/TRL fp16 LoRA from base,               │
        32 GB gfx906 trainer, exclusive card window         │
                 ▼                                          │
        MERGE + QUANT + BUNDLE — GGUF + prompt/tools/       │
        retrieval config = the artifact                     │
                 ▼                                          │
        GATE — Bands A/B/C/D, paired per-item stats ────────┘ (failures feed CH3)
                 ▼ human promote
        Gateway routing — shadow (plan-diff only) → promote → (rollback = flip back)
```

## 3. Data channels

| Ch | Source | Label / filter | Depth | Share of mix |
|---|---|---|---|---|
| **CH1 GOLD** | Real sessions from **every gateway-transiting harness** (agent/CLI harnesses via per-harness gateway keys; assistant harnesses joined via their existing trace hooks) | `/success` `/fail` explicit; implicit (clean tool exits, no retry/edit, not abandoned); `teacher_of_record` + `harness` recorded per sample | 1 | Anchor — uncapped |
| **CH1-E ESCALATION** *(new sub-stream)* | Joins of cheap-tier-fail → higher-tier-success on the same task, mined across ladder tiers | Join heuristic + precision audit (E8) | 1 | Small; feeds escalation training + Band C items |
| **CH2 SILVER** | Curriculum variations seeded from CH1 task types; synthesis-teacher rollouts via headless batch (parallel workers, checkpointing) in the card calendar's synthesis windows | Deterministic validation where verifiable; judge only for residuals | 2 | `TUNE` — start ≤40%, earns its cap in §9 step 6 or gets cut |
| **CH3 TARGETED** | Curriculum aimed at *measured* gate/regression failures of the current student | Same as CH2 | 2 | Small; exists only once Band B has content |
| **CH-W WIKI** *(new)* | Documented incidents from the operator's knowledge base (incident log, fix pages): failure→resolution arcs converted to sandboxed repair scenarios; `seed_ref` = knowledge-base page path | Outcome-labeled by reality; deterministic validation in sandbox | 2 | Small; activates after validators exist (§9 step 2) |
| **CH-M CONSOLIDATION** *(new)* | Stable behaviors and durable knowledge with high recall frequency whose recalls precede successful outcomes; volatile facts remain retrieval-only | Recall-count + outcome join; volatile-fact screen; admission criteria D-13 | 2 | Very small, slow cadence (quarterly with suite bumps) |
| **REPLAY** | Off-the-shelf general instruct mix (forgetting guard) | **Decontaminated against the Band C floor battery** — public instruct mixes are notoriously benchmark-contaminated | — | 15–30% of every run |

**Labeling spec (CH1).** Three states: marked-good, marked-bad, unlabeled. End-of-session one-keypress prompt so compliance doesn't decay. Retries and edits are *candidate* implicit negatives → DPO pairs (rejected = superseded turn, chosen = accepted final) — admitted to any preference experiment only after the pair-mining precision audit (E4-pre) passes. Turn-level cleanup after session selection: mask turns with nonzero tool exits and superseded turns; deliberately **keep** error→recovery arcs; drop abandoned dead ends. Silver-tier implicit positives sampled in so the mundane distribution stays represented. **Operator label audit** *(new)*: monthly, re-check a sample of ~10 marked-good sessions against the turn-mask output for silent human steering; log precision as calibration data alongside the judge's.

**Instrumentation hardening** *(new, load-bearing)*: labeling hooks and exporters live **outside harness packages** (wrapper scripts / hook files), with checksum guards — package-manager updates have already been observed to clobber in-package patches silently. Gold-accrual rate, label compliance %, and per-channel rejection rate are dashboard panels with alerts; a no-labels-in-48h condition pages. G0 is worthless if it dies silently.

**CH2 rules.** Seeds are task *types* and parameter perturbations drawn from CH1, never invented categories. Every sample records `seed_trace_id`. Synthetic never seeds from synthetic. Vision traces: filter out unless the student is VL (§5). Synthesis quant per D-11 (E10 decides whether the fast low-bit teacher quant is admissible for generation).

## 4. Curation core

Pipeline order per sample:

0. **Normalize** *(new)* — per-harness, per-teacher trajectory converters render traces into the student's chat/tool-call template. Versioned, tested code in `/harness-adapters/`; a silent format drift here poisons everything downstream.
0.5. **Trace-fit** *(new)* — sessions exceeding the measured max training sequence length pass through the versioned fitting policy: tool-output truncation rules, turn windowing, long-session splitting. The policy is a curation artifact recorded in lineage — it changes what behavior is learnable and E1's result is uninterpretable without knowing which policy produced the corpus.
1. **Deterministic** — code executes against tests, commands exit clean in sandbox, tool calls schema-validate, exact answers re-checked. No model in the loop.
2. **Outcome labels** — CH1 gold/silver states.
3. **LLM judge** — residual non-verifiable cases only. Judge-vs-outcome disagreements are logged as judge-calibration data, not resolved in the judge's favor. *(new)* Residual judging fans out to **multiple local judge families with agreement filtering** on the idle local inference fleet — judge diversity is a bias control that costs watts, not dollars.
4. **Volatile-fact screen** *(new)* — samples asserting volatile infrastructure facts (IPs, CT IDs, live states) are down-weighted or rewritten toward lookup behavior; samples demonstrating retrieval consultation are preferred (Principle 7).

Then: embedding dedup + semantic diversity scoring (existing Postgres/pgvector infra), decontamination against Band C (embedding similarity + n-gram overlap) **and of the REPLAY mix against the floor battery**, PII/client scrub, and sealing into **immutable content-hashed, client-homogeneous shards** — one client's data never shares a shard with another's, so exclusion never over-purges — with manifest: channel, `harness`, `teacher_of_record` (id + version + quant), `generation_depth`, seed refs, labels, validator results, client tags.

**Rejection rate per channel is a first-class metric** — dashboarded, alerted. A spike in CH2 rejections means the curriculum or the teacher drifted; that's a finding, not noise.

## 5. Training loop

| Parameter | Value |
|---|---|
| Trainer | **Dedicated training container — 32 GB gfx906 GPU (Vega 20 / MI50 family)**, `/dev/kfd` + `/dev/dri` passthrough, unprivileged |
| Stack | **Pinned:** torch 2.7.0 + rocm6.3 wheels (last branch shipping gfx906 kernels; runtime bundled, no system ROCm), `TORCH_BLAS_PREFER_HIPBLASLT=0`, `HSA_OVERRIDE_GFX_VERSION=9.0.6`. No flash-attention, no torch.compile, no bf16 — fp16 only. Upgrades are assumed breaking until smoke-tested; the pin is policy, not neglect. |
| Method | **HF PEFT + TRL fp16 LoRA, from base every run**, cumulative dataset. Never adapter-on-adapter. Verified working on this card with zero forks; ceiling ~9B at 32 GB. QLoRA via the community gfx906 stack (source-built bitsandbytes + triton-gfx906 + compile paths disabled) is an **experiment, not a dependency** — demonstrated elsewhere up to 31B-4bit on identical silicon, but every layer is unsupported. At 32 GB a 4–9B student does not need it. |
| Student | Qwen-lineage — 4B and 8B both carried as candidates (`MEASURE`, now a fair fight); same family as the synthesis teacher for template/tokenizer continuity. **G1 gate: architecture smoke test** — short forward/backward on each candidate on the pinned stack before any corpus exists. The teacher's generation is a GDN-hybrid family and this silicon has already crashed on GDN kernels under a newer ROCm; if the small siblings inherit the hybrid and it doesn't train, the fallback family is D-10 and we want to know at G1, not run 1. |
| Sequence length | `MEASURE` on-card. Without flash-attention, activations — not weights — are the binding constraint; the measured max drives the §4 trace-fitting policy. Escape hatch for long-sequence experiments: a fully supported 16 GB CUDA card (official Unsloth/bnb/flash-attention path) trades capacity for support when the gfx906 stack is the obstacle. |
| **Card calendar** *(new, normative)* | The synthesis teacher's serving stack and the trainer share the same physical GPU. **Training runs are scheduled exclusive windows**: drain/evict the serving layer first (a preflight eviction hook already exists), verify free VRAM, train, restore serving. CH2/CH-W synthesis batches fill the complement. A **tokens/day synthesis budget** line lives in the experiment DB from day 0 — at the teacher's measured decode rate, a thousand long trajectories is on the order of a week of card time, and the budget, not the A/B, may be what actually caps silver. |
| Loss | Masked, assistant tokens only |
| Thinking tokens | `TUNE` once, record as config axis: include CoT vs strip. Evaluate both on run 2, freeze the winner (E5). |
| Trigger | Volume: 300–1000 new curated turns (`TUNE`, D-3), never wall-clock |
| Reproducibility | Once: same config + seed → same result, to validate the rig |
| Artifact under test | **The bundle**: merged + quantized GGUF **plus** system prompt, tool schemas, and retrieval/memory config, versioned together. Gate what you deploy — all of it. |

Mix policy (channel ratios, replay fraction) is versioned config recorded in every run's lineage.

## 6. The gate

Existing Tier 0/1/2 harness restructured into the band model:

| Band | Content | Maps to | Gating |
|---|---|---|---|
| **A — Deterministic** | Parse/schema gate + deterministic replay checks. *Same code as curation validators.* | Tier 0 | Hard gate |
| **B — Regression** | Starts empty. Every promotion adds items for the capabilities that earned it. **On entry, an item is removed from all training and seed pools permanently.** Candidate must not regress on any past win beyond tolerance **T**. | new | Hard gate |
| **C — Held-out** | Frozen private set of real sessions — never trained on, never used as seeds, decontaminated — **partitioned by verifiability class at carve time**: `hermetic` (deterministically scorable in sandbox: code-vs-tests, file transforms, exact answers) vs `live-infra` (touched mutable cluster state; scorable only by proxy: schema-valid tool sequences, teacher-forced match, judge). Plus the general floor battery: lm-eval subset **+ a generative instruction-following probe (IFEval-style)** — forgetting shows in format compliance before multiple-choice accuracy moves. | Tiers 1–2 | **Hard gate = hermetic subset + floor battery.** Live-infra items are scored, reported with their class, and never silently promoted to hard-gate status. Every live-infra item is also a standing entry in the validator backlog: make it hermetic, then it gates. |
| **D — Advisory** | Judge comparisons, style/verbosity drift, shadow plan-diffs. | new | Advisory |

**Statistics** *(rewritten — the load-bearing v1.1 correction)*. Two noise sources:

1. *Decoding variance* — handled as in v1.0: incumbent and candidate through Bands A–C **≥5 times each**.
2. *Item-sampling variance* — **dominates at this operator's item counts and does not yield to reruns.** Handled by design: all comparisons are **paired per item** (McNemar on pass/fail, paired bootstrap on scalars); the evidence package reports **confidence intervals, never bare deltas**; a **power analysis at G2** against the actual Band C size sets the minimum detectable effect.

Thresholds sit at or above what the power analysis says is detectable: **M** = minimum useful gain vs. incumbent (a tie doesn't ship); **T** = max regression vs. immediate incumbent, per item class; **D** = max regression vs. **historical best** (anti-ratchet), referenced to variance-aware aggregates, never single-run maxima. **The v1 gate is declared big-effects-only**: at an early Band C of tens of items, only large effects are real; the gate says so in the evidence package rather than laundering noise through fine-grained thresholds. Granularity tightens as the annex grows the frozen core at version bumps.

**Suite versioning and retirement.** `eval_suite_vN`, frozen; any change bumps N and invalidates cross-version comparison. Annex → core promotion at bumps (D-4). *(new)* **Retirement rule:** at each bump, items and historical-best references whose workload element has been decommissioned are dropped or re-baselined, rationale logged. Retired evaluation content is permanently marked no-recycle and cannot return to mining, training, or seed pools. The anti-ratchet floor defends capabilities; it must not defend ghosts — this cluster retires infrastructure monthly, and a floor referenced to a dead service blocks legitimate adaptation forever.

**Promotion.** Evidence package auto-assembled (per-band deltas **with CIs**, variance, verifiability-class breakdown, lineage, mix policy, controlled model effect, bundle config version) → one-keypress human decision. A paired model-only control holds prompt, tools, retrieval, and memory constant; the deployed-bundle comparison then measures the complete change. Neither substitutes for the other. On promote: gateway route flip of the bundle, Band B grows (and its items leave the pools), old bundle retained. Rollback is the same flip backwards.

## 7. Provenance spine

- `generation_depth` mandatory on every sample. Real trace = 1, synthesized-from-trace = 2. **Depth cap: nothing ≥3 trains without an explicit decision.** Student outputs never silently re-enter the corpus.
- `harness` and `teacher_of_record` *(new)* mandatory on CH1; `teacher_of_record` includes model id, version, and quant for synthetic channels.
- **Exclusion query** — "rebuild this lineage excluding source X" — computes the transitive closure over `derived_from`, is idempotent, and is tested on synthetic shards *before* the first real corpus exists. Cannot be retrofitted.
- **Client purge path.** Client-homogeneous shards + exclusion query + retrain from base + re-gate. **Acceptance test (E7), passed before any production client data is admitted:** seed synthetic TEST_CLIENT_X and a source Y derived transitively from X across shards; the system must enumerate every affected shard, emit the exact rebuild manifest excluding them, and assert the excluded content hashes and all descendants appear nowhere in the manifest.
- **Retention boundary** *(new, honest)*: the purge path removes a source from the *model*. Trace-store rows, exports, shard archives, and backup history are separate stores governed by retention policy, stated as such in any client engagement. Also operational: any new host provisioned for this pipeline must be explicitly enrolled in backup and monitoring scope — a training host that silently isn't backed up and a client store that silently *is* backed up forever are both failures.
- **Experiment DB** in the existing Postgres: every run's config, dataset hashes, trace-fitting policy version, measured peak VRAM, wall clock, card-calendar window, synthesis tokens/day, gate results with CIs, promotion decision. After run 1, corpus-size-vs-delta is a measurement (`MEASURE`) and it prices every future generation decision.

## 8. Deployment

Candidate bundle serves in **shadow** behind the gateway first — **plan-diff only: the shadow path is structurally incapable of tool execution** (a shadow agent that acts doubles every side effect on live infrastructure). Mirrored requests produce first-action/plan diffs against the incumbent, feeding Band D; that is weaker evidence than full rollouts and is labeled as such. Promotion is a gateway route flip into the **local tier of the delegation ladder** — the slot whose incumbent the gate actually beat. llama.cpp serves the GGUF on whatever fleet node the VRAM budget assigns (a separate fully supported CUDA card is the natural serving home, keeping the trainer free for the next cycle). Every promoted bundle and its predecessor stay in the model store.

## 9. Build order

1. **Instrument now — all harnesses.** `/success`, `/fail`, implicit signals → trace-store scores; gateway OTel consolidation; harnesses that already ship turn traces via existing hooks are joined, not rebuilt. Hooks outside packages, checksum-guarded; accrual/compliance/rejection dashboards + alerting live. Privacy-minimized telemetry accrues from day 0. D-9 classification runs in parallel and gates source admission to curation/training, not collection.
2. Source-admission registry + validators + shard schema + **transitive exclusion query** (tested on synthetic shards) + per-harness normalizers + **student-arch smoke test on the pinned stack** + **E4-pre pair audit**. CH-W may start generating once validators exist.
3. Carve Band C's frozen core from existing trace-store history **with verifiability classing**; those sessions are excluded from all future mining; decontamination pipeline live (including REPLAY-vs-floor-battery).
4. Variance-calibrate (≥5×) **and run the item-count power analysis**; set M/T/D under the big-effects-only posture.
5. **Run 1 — gold only (E1, interpreted against E9's retrieval counterfactual).** Card calendar, training envelope, throughput, and synthesis budget become measurements.
6. **Run 2 — gold + silver A/B (E2 + E10 quant rider).** Silver earns its cap or gets cut. Evidence, not vibes.
7. CH3 online once Band B has content; CH1-E escalation training once E8's mining audit passes; CH-M on its slow cadence (D-13). Steady state: volume-triggered cycles.

## 10. Relationship to Sovereign Distillery

Agreed fork, 2026-08-19. Grounded is the production workload-specialization branch; Sovereign continues as the model-development research architecture. They share infrastructure with each other and objectives with nobody.

**Shared (common library, jointly maintained):** deterministic validators, immutable hashed shard schema, source-admission state machine, provenance fields (`generation_depth`, `base_family`, `derived_from`, `harness`, `teacher_of_record`, client tags), transitive exclusion/rebuild query, Bands A–D, M/T/D semantics, **paired-comparison statistics, historical-best ratchet, controlled model-effect comparison, and power-analysis tooling**, variance calibration, experiment DB schema, immutable evidence bundles, human-governed promotion, router rollback.

**Per-project policy:** teacher count, curriculum source, student objective, corpus admission rules.

**Capacity clause** *(new)*: the 32 GB trainer makes teacher-scale fine-tuning physically possible on this rack. It remains out of Grounded's scope by treaty — teacher modification and multi-teacher capability work are Sovereign's lane. Grounded spends capacity on sequence length and cycle speed, never on model ambition.

Evidence flows between projects as evidence only.

## 11. Explicitly rejected

| From | Rejected | Why |
|---|---|---|
| Sovereign | Multi-teacher synthesis queue, size ordering | One strong synthesis teacher beats a zoo; a second enters only by winning an eval case. (Gold's multi-teacher reality is provenance, not policy.) |
| Sovereign | Generalist objective | The student is a workload specialist. Generality is a floor constraint (Band C battery), not a goal. |
| Sovereign | Free-authored capability taxonomy | Curriculum topics come from measured usage, measured failures, and the operator's documented incidents only. |
| Trace pipeline v1 | Session-only labels, time-based cadence | Fixed in §3, §5. |
| Trace pipeline v1 | Judge as primary filter | Demoted to residual cases; calibrated against outcomes; diversified across local judge families. |
| Both | Unbounded synthetic fraction | Capped, depth-tagged, and required to prove its delta in run 2. |
| v1.1 review | Frontier tier as the deployment slot | Unbeatable incumbent = a gate that never fires. The student ships into the local tier (Principle 9). |
| v1.1 review | Parametric memorization of volatile infra facts | Stale by promotion time, unpurgeable after; the deployed system has retrieval — use it (Principle 7). |
| v1.1 review | Shadow-with-execution | Double side effects on live infrastructure. Plan-diff only. |
| v1.1 review | Unpaired aggregate gate statistics | Item-sampling variance at this N makes unpaired deltas noise theater (C13). |
| v1.1 review | Training on Band B items | Regression band decays into an easy quiz. Entry removes from pools. |
| v1.1 review | Teacher fine-tuning under this project | Capacity scope creep; Sovereign's lane by treaty (§10). |
| v1.1 review | Unsloth QLoRA as the default method | Unsupported everywhere on gfx906; community stack is fragile; 32 GB makes 4-bit unnecessary for a ≤9B student. fp16 LoRA on PEFT/TRL is verified and boring. Boring wins. |

## 12. Open decisions

| # | Decision | Default |
|---|---|---|
| D-1 | CH2 cap after run-2 A/B | ≤40% opening value |
| D-2 | Depth policy | Hard cap at 2; ≥3 requires explicit sign-off |
| D-3 | Retrain trigger threshold | 500 curated turns |
| D-4 | Suite version cadence | Bump only on deliberate content change; annex promotion quarterly; retirement rule applied at every bump |
| D-5 | Thinking-token policy | Decide on run-2 evidence (E5) |
| D-6 | Student size (4B vs 8B) | Micro-run measurements on the 32 GB card (E6); sequence length, not fit, is the axis |
| D-7 | Per-client adapters vs single student | Single student + purge path for v1; per-client adapters if a client demands hard isolation |
| D-8 | Cumulative-dataset growth policy | Record wall-clock curve from run 1; adopt curation/subsampling once a full run exceeds ~24 h (`TUNE`) — expected to bind within the first several runs, not "eventually" |
| D-9 *(new)* | **CH1 source-admission policy for frontier-teacher traces** | Must be decided in writing before affected evidence enters curation or training. Privacy-minimized telemetry collection proceeds while provider/model/revision classification remains `UNKNOWN`; fail-closed admission prevents use. Options: (a) admit specified sources for internal use with risk documented; (b) restrict admission to approved local-teacher sessions. No default — this is the operators' call. |
| D-10 *(new)* | Student family fallback if the Qwen-lineage smoke test fails on gfx906 | Older dense Qwen generation (keeps tokenizer, loses recency) over a foreign family (loses continuity); decided by the G1 smoke test |
| D-11 *(new)* | Synthesis teacher quant (full-quality q8 vs ~2× faster low-bit) | Decided by E10; default = fast quant if E10 shows no validated-sample quality loss, because the synthesis budget is the binding constraint |
| D-12 *(new)* | Retirement-rule criteria | Item retires when its workload element is decommissioned or unexercised for 2 suite versions; historical-best re-baselines rather than deletes where the capability generalizes |
| D-13 *(new)* | CH-M consolidation admission | Recall-frequency threshold + outcome-validated recalls only; quarterly cadence aligned with suite bumps; always depth-2 provenance |

## 13. Changelog v1.0-frozen → v1.1-draft

**Corrections (fixes to claims v1.0 already made):**
1. Gate statistics: paired per-item comparison, CIs mandatory, G2 power analysis, big-effects-only opening posture. v1.0 calibrated only rerun noise; item-sampling variance dominates at this N. (§6)
2. Principle 5 scoped to synthesis: CH1's teacher-of-record is per-sample provenance and is substantially frontier models; new field `teacher_of_record`; harvest/licensing policy forced to a written decision (D-9). (§1, §3, §7)
3. Shadow semantics: plan-diff only, execution structurally excluded. (§8)
4. Band C partitioned by verifiability class; hard gate = hermetic subset + floor battery; live-infra items honestly proxy-graded and queued for validator conversion. (§6)
5. Band B entry removes items from training/seed pools. (§6)
6. Retirement rule at suite bumps — anti-ratchet must not become anti-adaptation. (§6, D-12)
7. Purge/retention boundary stated honestly; E7 extended to assert hash absence; shard sealing made client-homogeneous. (§4, §7)
8. REPLAY mix decontaminated against the floor battery; floor battery gains a generative instruction-following probe. (§3, §6)
9. DPO pair mining gated behind a precision audit (E4-pre). (§3)
10. Trace-fitting policy and per-harness/teacher template normalization added as versioned curation steps. (§4)

**Environment updates (trainer card change):**
11. §5 rewritten for the 32 GB gfx906-class trainer: pinned torch 2.7+rocm6.3 stack, fp16 PEFT/TRL LoRA as default, QLoRA demoted to experiment, no-FA sequence-length reality, G1 architecture smoke test, a fully supported 16 GB CUDA card named as escape hatch and serving home.
12. Card calendar made normative: teacher and trainer share one GPU; exclusive training windows; synthesis tokens/day budget in the experiment DB; synthesis quant decision (D-11, E10).

**Additions (new scope, from review + operator infrastructure):**
13. Deployment-slot doctrine: student ships into the delegation ladder's local tier; beatable incumbent (Principle 9, C10).
14. Escalation sub-stream CH1-E + E8: punt-calibration as a trained capability (C12).
15. Multi-harness harvest: every gateway-transiting harness via per-harness keys + assistant harnesses via existing trace hooks; `harness` provenance field. (§2, §3)
16. CH-W wiki-incident channel and CH-M memory-consolidation channel. (§3)
17. Train verbs, retrieve nouns (Principle 7, C11) + volatile-fact screen + retrieval counterfactual experiment (E9); bundle as the unit of gating and promotion (Principle 8).
18. Instrumentation hardening: out-of-package hooks, checksum guards, accrual/compliance/rejection dashboards with alarms. (§3)
19. Judge diversity across local model families for residual grading. (§4)
20. Capacity clause in the treaty; new rejected-items rows; D-9..D-13.

**Unchanged and reaffirmed:** channel philosophy and depth caps, validator reuse, outcome-over-judge precedence, from-base retraining, human-governed promotion, router-flip rollback, evidence-flow treaty, G-phase sequencing, the falsification commitments.
