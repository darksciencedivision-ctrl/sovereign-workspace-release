# Sovereign Distillery — Open Questions Register v0.1

Decisions the operator must make. The reviewer states options and consequences; the reviewer does not choose.

**Legend:** BLOCKING = downstream work cannot proceed correctly without this.

---

## OQ-001 — What is `SOV-SEED`? — **BLOCKING**

*Related: F-4, C-2, A-1, MISSING-2*

Every diagram in the source material begins at a seed model. None defines it. The three options are not variations of one project; they are three different projects.

| Option | Executable on stated hardware? | "Sovereign-owned"? | Consequence |
|---|---|---|---|
| **(i)** Random init, pretrain from scratch at useful scale | **No** — off by orders of magnitude | Yes | Project as scoped is not executable |
| **(ii)** Fine-tune an existing open-weight base | **Yes** | No — derivative; inherits arch, tokenizer, license | Fastest path to a working system; sovereignty is operational, not legal |
| **(iii)** Pretrain a deliberately tiny model (~100M–500M) from scratch, then distil into it | **Yes** (marginal) | Yes | Genuinely own the lineage; model will be far weaker than the library for a long time |

**Consequence of not deciding:** the specification cannot be finalized. Tooling, licensing posture, schedule, and acceptance criteria all branch here.

**Reviewer note:** (ii) and (iii) are both defensible. They are not combinable. If the answer is (ii), the honest framing is "Sovereign controls and shapes its model," not "Sovereign owns its model from nothing" — and that framing should be corrected in project documentation now rather than discovered later.

---

## OQ-002 — What is actually in the local model library? — **BLOCKING**

*Related: MISSING-1, E-4*

Bridge access to `.ollama` and `.lmstudio` was refused by the device. The library composition is unknown, so the following are all currently unanswerable:

- The teacher ordering (the entire smallest-to-largest premise)
- License exposure (§6 of the spec)
- Whether any same-family teachers exist (which would make weight-merging viable — F-2c)
- Tokenizer diversity (which determines whether white-box KD is ever an option)
- Disk footprint and generation schedule

**Needed from operator:** either connect the model directory via the desktop folder picker, or paste the output of `ollama list` and the LM Studio model directory listing.

---

## OQ-003 — What is the v1 acceptance criterion? — **BLOCKING**

*Related: R-11, §12 of spec*

Without a falsifiable terminal condition the project has no completion state and will drift indefinitely.

Reviewer's proposed shape (operator to accept, amend, or replace): one named capability, measured on the frozen deterministic suite, where the promoted checkpoint meets a stated numeric threshold with no regression beyond tolerance and with reproducible provenance.

---

## OQ-004 — Is training compute limited to the local 8 GB GPU?

*Related: F-1, C-1, ADD-1*

| Answer | Consequence |
|---|---|
| **Local only** | Student capped at ~1B–3B. Architecture growth ladder is deleted permanently, not deferred. Model is small, specialized, and honest about it. |
| **Rented compute available for training bursts** | 7B–14B becomes reachable. Changes cost model, changes data-egress/licensing posture, and means the local card is a generation and inference device rather than a training device. |

This decision determines whether §9 of the spec is a permanent ceiling or a temporary one.

---

## OQ-005 — Promotion margin and regression tolerance

*Related: INV-3, §5 of spec*

Two numbers, both currently UNSET:

- **Improvement margin M** — how much better on a targeted capability counts as a real gain rather than noise?
- **Regression tolerance T** — how much degradation on a previously-held capability is acceptable, if any?

Reviewer note: these should be set with reference to measured run-to-run variance on the eval suite, which requires the suite to exist first. Setting them by intuition produces a gate that either never passes or always passes.

---

## OQ-006 — Corpus mixing ratios

*Related: R-1, R-3, §8 of spec*

New-teacher shard : replay of prior corpus : non-synthetic human data — ratios UNSET.

Sub-question with a real tension behind it: does the operator intend **strictly single-teacher training mixes** (matching the literal "one at a time" directive), or **cumulative mixes** with replay? The former is more faithful to the stated design; the latter is the standard mitigation for catastrophic forgetting. The reviewer recommends cumulative, but this is an operator call because it touches the stated method.

---

## OQ-007 — Is the Sovereign model intended for distribution?

*Related: R-5, F-6, MISSING-9*

Internal-use-only and eventual-release have very different licensing exposure. If release is ever plausible, the license partitioning in §6 changes from good hygiene to a hard gate — and some teachers may need to be excluded from the lineage entirely before any training occurs.

---

## OQ-008 — Does the "smallest to largest" ordering stand as a learning curriculum, or as pipeline-risk ordering?

*Related: F-3, C-3*

The reviewer found no evidence supporting it as a learning curriculum, and a clear justification for it as risk ordering (cheap teachers first = cheap place to debug the pipeline). Both preserve the operator's stated sequence. The difference is what claim the project makes about *why*.

If the operator wishes to retain the curriculum hypothesis, the reviewer recommends recording it as an explicit, testable hypothesis rather than as settled design rationale — it can be tested later by comparing a sequentially-trained lineage against a single mixed-corpus baseline.

---

## OQ-009 — Where are the Sovereign, Debate Table, and Multi-Model App repositories?

*Related: MISSING-4, A-9, §10 of spec*

The operator indicated these exist on disk and offered paths. Until they are inspected, every integration statement in the specification remains an assumption and §10 cannot be completed.

---

## Resolved

*(none yet)*
