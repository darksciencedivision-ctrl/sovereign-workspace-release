# SWS-CORRECTIVE-01 workstream 5 — frozen evaluation protocol

**Status: FROZEN BEFORE EXECUTION.** Everything in this file — the task set, the grading rule,
the primary outcome, the benefit threshold and the regression tolerance — was written and
committed before any comparison was run. Nothing below may be changed after seeing results; a
changed threshold makes the comparison worthless, so a change means a new protocol with a new
identifier and a fresh holdout.

**Protocol ID:** `SWS-BENCH-01`

---

## 1. The question

The review did not establish (V1) that the full orchestration workflow improves task outcomes
over a simpler baseline. This protocol asks one question:

> On the workload this product actually executes, does the DEEP orchestration produce better
> outcomes than a single model call with the same evidence and the same instructions — and by
> enough to justify roughly six times the model calls?

It does not ask whether the product is good, whether local models are good, or how the product
compares to a frontier provider. A local comparison establishes nothing about frontier-provider
performance, and no paid-provider condition is executed here.

## 2. What is compared

All conditions run the **product's own code**: `sovereign_product.executors.QuickExecutor` and
`sovereign_product.semantic_deep.SemanticDeepExecutor`, driven directly with a real
`OllamaClient` and real `EvidencePacket`s. Only the HTTP service around them is absent. No
benchmark-only reimplementation of the orchestration exists; measuring a copy would measure the
copy.

| Condition | What it is | Model calls per task |
|---|---|---|
| **A — single** | `QuickExecutor`: one call to the primary reasoner with the same evidence packet and the product's own QUICK prompt | 1 |
| **B — full** | `SemanticDeepExecutor`: 3 member models, then critic, then synthesizer, then verifier, with the product's repair loop | 6+ |
| **C1 — no critic** | B with the critic stage disabled | 5+ |
| **C2 — no verifier** | B with the verifier stage disabled | 5+ |

C1 and C2 are the ablations of the two stages whose value is least established: both are extra
model calls whose output is not the answer the operator reads.

**Roster.** Exactly what `SYSTEM_MANIFEST.json MODELS` declares — the assignments the shipped
product uses. No model is substituted to make a condition look better.

## 3. The task set

30 held-out tasks in `dataset.json`, across five categories:

| Category | n | What it tests |
|---|---|---|
| `grounded_fact` | 8 | a fact that IS in the supplied evidence, answered and cited |
| `absent_fact` | 6 | a fact that is NOT in the evidence — the correct answer is an abstention |
| `contradiction` | 5 | two supplied sources disagree — the answer must report the conflict, not pick |
| `synthesis` | 6 | a conclusion that requires combining two or more supplied sources |
| `procedural` | 5 | a question about a documented procedure, answered from the supplied text |

**Substituted category, declared before results were seen.** The directive names "executable
work where supported". This product's SOVEREIGN routes emit natural-language answers over an
evidence packet; they execute nothing and have no tool access, so an executable-work category is
outside current capability. `procedural` replaces it: it is drawn from the same product workload
and is still graded by a known answer rather than by opinion.

**Held out from development.** The tasks were written against the product's real documents and
were never used to tune a prompt, a threshold, or a model choice. `dataset.json` carries a
`dataset_sha256` over its own task list; every run record repeats that hash, so a result set can
be tied to the exact tasks that produced it.

## 4. Grading

**Programmatic, on a known answer.** No model grades another model's output, and the generator
never certifies itself. Each task declares:

- `must_contain` — strings that must appear (case-insensitive) for the answer to be correct;
- `must_not_contain` — strings whose presence makes it wrong (a fabricated value, a picked side
  of a contradiction);
- `expect_abstention` — for `absent_fact`, whether the answer must decline;
- `citable` — the source IDs in the packet, used to score attribution.

Per task, per condition, per run, the harness records:

| Field | Meaning |
|---|---|
| `correct` | the known-answer verdict — the **primary outcome** |
| `abstained` | did the answer decline |
| `unsupported_claims` | clauses asserting a fact with no citation, from `quality.assess_quick_response` |
| `citation_errors` | citations naming a source not in the packet |
| `elapsed_s` | wall-clock, monotonic |
| `model_calls`, `prompt_tokens`, `completion_tokens` | from the provider's own counters; unknown stays `null` |
| `peak_vram_mib` | sampled from `nvidia-smi` every 500 ms during the task; the method and its limitations are recorded with the number |
| `error` | timeout, cancellation, or exception — recorded, never dropped |

Subjective quality is **not** scored. There is no blinded human panel available for this run, so
rather than substitute a model judge — which would let the same family of models certify its own
output — no subjective dimension is reported at all.

## 5. Execution discipline

- **3 runs per task per condition.** 30 tasks × 4 conditions × 3 runs = 360 executions.
- **Paired.** Every condition sees the identical task and the identical evidence packet.
- **Counterbalanced.** Condition order is permuted per (task, run) from a seeded shuffle, so no
  condition systematically runs on a warmer cache.
- **Cold/warm cache policy.** Ollama keeps a model resident after use. Order permutation is the
  control; the residency policy is recorded, not eliminated, and is stated as a limitation.
- **Every attempted run is reported**, including failures and timeouts. A run is never discarded
  for being inconvenient.
- **Environment is captured once per run set**: model tags with their ollama digests, quantization,
  context limits, sampling settings, the prompts, hardware, the candidate SHA, and the harness hash.

## 6. Primary outcome, threshold and tolerance — fixed in advance

**Primary outcome (preselected, single):** the paired difference in `correct` rate between
**B (full)** and **A (single)** across all 30 tasks, aggregated over 3 runs.

Everything else — per-category rates, unsupported-claim counts, time, VRAM, the C1/C2 ablations —
is **exploratory**. Exploratory results may motivate a follow-up protocol; they may not be
promoted to the headline.

**Benefit threshold.** B must beat A by **at least 10 percentage points** of absolute task
success to be retained as the default. Rationale: B costs roughly six model calls to A's one and,
on this hardware, takes several times as long. A difference smaller than that does not repay the
latency an operator waits through, and with 30 paired tasks a difference below ~10 points is not
distinguishable from noise at this sample size anyway.

**Regression tolerance.** An ablation (C1, C2) is treated as *no worse* than B if its success rate
is within **5 percentage points** of B's. A stage whose removal costs less than that has not
demonstrated its value.

**Uncertainty.** Paired differences are reported with a 95% bootstrap confidence interval over
tasks (10 000 resamples, seeded). An interval spanning zero is reported as **inconclusive**.
Inconclusive is a permitted and expected result. Uncertainty is never described as equivalence.

## 7. Decision rule — fixed in advance

Applied per component, from the numbers alone:

| Result | Decision |
|---|---|
| B − A ≥ +10 pts and the CI excludes zero | **RETAIN** the full orchestration as default |
| B − A ≤ −10 pts and the CI excludes zero | **SIMPLIFY**: make A the default |
| otherwise | **INCONCLUSIVE**: no default change. Uncertainty is a reason for a reversible default or an experimental flag, never for a claim of superiority |
| C1 (or C2) within 5 pts of B | that stage has **not demonstrated benefit** — candidate for an explicit, reversible off-by-default flag |

A change of default is implemented only where the numbers support it, is reversible, deletes no
capability, and is followed by re-running the affected correctness checks.

## 8. What this cannot establish

- Nothing about paid-provider or frontier-model performance. No such condition is run.
- Nothing about subjective answer quality: no independent human judgment was available.
- Nothing about workloads outside these five categories.
- VRAM is sampled, not integrated; a peak between samples is missed.
- Token counters come from the provider and are recorded as `null` where it does not supply them.
- 30 tasks is a small sample. Small samples produce wide intervals, and wide intervals are
  reported as wide rather than narrowed by choosing a different statistic after the fact.
