# Review of the Integrated Canonical Engineering Report

| | |
|---|---|
| **Document** | Integration review v1.0 |
| **Date** | 19 August 2026 |
| **Subject** | *Sovereign Distillery — Integrated Canonical Engineering Report*, dated 19 August 2026, 113 sections |
| **Reviewer role** | Research Validator / Analyst |
| **Authority** | Operator retains objectives, scope, promotions, and acceptance. This is a review, not an approval. |
| **Prior document** | `SOVEREIGN-DISTILLERY-REPORT.md` (validation & specification report, this workspace) |
| **Basis** | Reviewed from the full text supplied in-conversation, cross-checked against the source PDF. |

---

## 0. Summary position

The integrated report is a **substantial improvement on both prior documents**. It resolves two of the three blockers, adds four things neither prior document contained, and correctly adjudicates most of the validation findings.

It also contains **two internal defects that would cause real problems in execution**, one **traceability defect** that will cause confusion within days, and **two "corrections" that correct claims the validation report did not make**.

Net movement on the blocking set:

| Blocker | Prior status | Status after integration |
|---|---|---|
| **OQ-001 — the seed** | BLOCKING | **Near-closed.** A better resolution than the validation report offered. Requires operator signature to close. |
| **OQ-002 — library inventory** | BLOCKING | **STILL BLOCKING. Unchanged.** Re-described as Phase D2; not resolved. |
| **OQ-003 — v1 acceptance** | BLOCKING | **Near-closed, but internally inconsistent as written.** See IR-2. |

**One hard blocker remains, and it is the one that 113 sections of specification cannot resolve: nobody has yet enumerated the model library.**

---

## 1. Accepted without reservation — genuine additions

These are in the integrated report and in neither prior document. Each is correct and each should be retained.

### 1.1 Seed Option C — bootstrap, then native migration (§18)

**The validation report framed OQ-001 as three mutually exclusive options. That framing was too narrow.** The integrated report identifies a fourth possibility: sequence them. Bootstrap from a permissive base to prove the pipeline; accumulate datasets, evals, capability maps, and training experience as portable assets; migrate to a native architecture later, once pipeline maturity is demonstrated.

This works because it separates two hard problems that the original framing conflated — *proving the Distillery* and *building a foundation model* — and it makes the second problem's inputs a byproduct of solving the first. The corpora, evaluation suite, and capability ledger are architecture-independent. They transfer.

**Reviewer position: this supersedes the validation report's F-4 framing.** Contradiction C-2 dissolves under it, because sovereignty becomes a trajectory with named phases rather than a binary property claimed up front.

The one thing it must not become is an indefinitely deferred Phase C. §84 (OQ-008) correctly asks when migration triggers, and correctly says the trigger is demonstrated pipeline maturity rather than enthusiasm. That question should stay open and visible, not quietly age out.

### 1.2 Distillery Knowledge Lineage (§31, §98, §109)

A second lineage recording what transfer strategies, curricula, hyperparameters, and validation methods succeeded or failed. **Neither prior document contained this and it is the most valuable single addition in the integrated report.**

The reasoning in §109 is right: the Distillery is two systems — an engine that builds models and a memory that learns how models should be built. Without the second, every teacher cycle re-derives the same lessons.

*(One scoping caveat — see IR-5.)*

### 1.3 Long-running resumability (§57, §59)

**A genuine gap in the validation report.** On an 8 GB card, generation and training runs will be long. A failure at stage 17 that forces regeneration from stage 10 is not an inconvenience; it is potentially days of lost compute. Explicit run state, checkpoint boundaries, and a resume pointer are correctly identified as architecture rather than polish.

### 1.4 Candidate state machine (§29) and Capability Ledger (§21)

Both operationalize things the validation report only asserted.

`PLANNED → INGESTED → ... → PROMOTABLE → PROMOTED → PRODUCTION`, with `QUARANTINED` and `REGRESSION_DETECTED` as first-class states, makes "training completion is not promotion" enforceable rather than aspirational.

The Capability Ledger with per-capability current / historical-best / source / trend is the concrete form of the regression band. It directly addresses R-6 (false improvement) in a way the validation report described but did not structure.

*(One defect in the ledger design — see IR-1. It is important.)*

---

## 2. Adjudication of the three corrections to the validation report

### 2.1 §71 — "Own LLM" as acceptance criterion — **CORRECTION ACCEPTED**

The integrated report separates **strategic objective** ("produce Sovereign-developed model artifacts capable of operation inside the Sovereign ecosystem") from **release acceptance** (measurable capability thresholds, regression limits, deployment, lineage, provenance, hardware requirements).

**This is a better resolution than the validation report's.** F-8 rejected ADD-6 as unfalsifiable, which was correct about its use as an acceptance criterion and overreaching as a verdict on the objective itself. A strategic direction does not need to be a benchmark to be legitimate; it needs to not be *mistaken* for one.

**The validation report's F-8 is superseded. The reframe in §71 is the correct form.**

### 2.2 §72 and §113 — "permanent 1B–3B ceiling" — **CORRECTION REJECTED AS MISATTRIBUTED**

REJ-5 rejects: *"Today's local GPU permanently caps the final Sovereign architecture."*

**The validation report did not make that claim.** Specifically:

| Where | What the validation report actually said |
|---|---|
| §IX.9 | "**Working envelope [PROPOSED, pending measurement]**" |
| ADR-0003 | Contains an explicit **"Revisit condition"**: "Resolve OQ-004. If training can burst to rented GPU compute, this ADR is superseded and the growth ladder returns." |
| ADR-0003 | "**Evidence quality caveat** — the VRAM figures above are modelled estimates from a secondary source, not measurements on this GPU." |
| Part XIII | Lists, as explicit falsifiers: rented compute approved → "ADR-0003 superseded"; measured VRAM differs → "the entire IX.9 envelope is recalculated" |
| Part XII, Phase 0 | Made measuring the machine the **first** action precisely so the estimate could be replaced |

§113's characterization — that the validation report "attempted to convert current hardware into a permanent model ceiling" — is not an accurate reading of the source document.

**This matters for one reason only, and it is not pride.** The integrated report is now the canonical baseline. If it records the review history inaccurately, then in six months someone reconstructing *why* the envelope was set will find a rejected claim that was never made, and will not find the actual reasoning — which was "this is an estimate, measure it, here is exactly what would change it."

**The substantive position is not in dispute. Both documents say: provisional, pending measurement, revisable on evidence.** Recommend §72 and §113 be revised to record agreement rather than correction, and REJ-5 be retained as a standing project principle (which is useful) rather than as a rejection of a prior finding (which is inaccurate).

### 2.3 §73 — architecture growth ladder — **AGREEMENT, not correction**

The fixed `3B → 7B → 14B → 32B` ladder is removed; evidence-driven growth is retained. **This is what ADR-0003 said** ("removed from v1 scope... pending OQ-004", with a revisit condition). The integrated report's INV-11 / INV-12 pair — *scale does not increase automatically; scale may increase when capacity evidence and compute permit* — is a cleaner formulation than the validation report's and should be adopted.

Recorded as agreement reached, not as a correction applied.

---

## 3. New findings against the integrated report

### IR-1 — MAJOR — Per-step regression tolerance does not bound cumulative capability drift

*Relates to: §21, §28, §36, §60, §80, §108*

The integrated report names cumulative capability retention as **the principal engineering finding** (§108): *"the most important scientific metric over the lifetime of the project is NET RETAINED CAPABILITY."* Correct. But the mechanism specified to protect it cannot deliver it.

The promotion rule (§28) requires "regression within accepted limits" — a per-promotion tolerance `T` (OQ-004 in the integrated numbering). **A per-step bound does not bound the sum.**

Worked example. Suppose `T` = "no capability may regress more than 2 points in a single promotion." Consider twenty promotions, each losing 2 points on Tool Use while gaining elsewhere:

```
SOV-D001   Tool Use  96   ← historical best
SOV-D002   Tool Use  94   promoted, -2, within T
SOV-D003   Tool Use  92   promoted, -2, within T
...
SOV-D021   Tool Use  56   promoted, -2, within T
```

**Every single promotion is legal. The capability is destroyed.** This is precisely the failure mode §108 identifies — "not accumulating intelligence, merely rotating specialties" — and the promotion rule as written permits it, one legal step at a time.

The integrated report's own example makes this visible without flagging it. §21's ledger shows:

| Capability | Current | Historical Best | Trend |
|---|---:|---:|---|
| Tool Use | 95 | 96 | Regression |

A promoted checkpoint sitting below historical best. Correct behaviour under the rule as written — and the first step of the sequence above.

**Required fix — a second gate.** Promotion must be tested against **two** thresholds, not one:

1. **Step tolerance `T`** — maximum regression versus the immediate parent. *(Already specified.)*
2. **Drift floor `D`** — maximum regression versus **historical best** for that capability, across the whole lineage. *(Missing.)*

A candidate that passes `T` but breaches `D` is not promotable without an explicit, recorded operator override — the override being the point at which a human decides a capability is genuinely being traded away rather than eroded by accident.

The Capability Ledger already stores `Historical Best`, so the data needed is present. Only the gate is absent.

**This is the most consequential finding in this review.** It is a small specification change that protects the metric the integrated report itself names as most important.

### IR-2 — MAJOR — The v1 acceptance criteria are internally inconsistent on the SKIP path

*Relates to: §79, §95, §102*

Three passages disagree about whether a SKIP satisfies v1.

| § | Statement |
|---|---|
| §79 (OQ-003) | v1 requires "**demonstrates statistically or deterministically meaningful improvement on at least one target capability**" |
| §95 (Phase D9) | "Even a SKIP or REJECT can count as pipeline success if the decision is evidence-backed" |
| §102 | Criterion 6: "A useful delta is identified **OR a valid SKIP is produced**" — but criteria 7–13 (corpus generated, training completes, candidate evaluated, regression measured, promotion decided, lineage preserved, artifact runs) all presuppose that training occurred. And §102 states: "**If all fourteen are satisfied**, the Distillery exists as a functioning system." |

**A SKIP satisfies criterion 6 and makes criteria 7, 8, 9, 10, 11 and 13 unsatisfiable.** As a conjunction of fourteen items, the list cannot be satisfied via the SKIP path it explicitly permits.

This is not pedantry. It determines whether the project can declare v1 complete after processing a teacher that legitimately contributed nothing — which, per contradiction C-3 in the validation report and §11 here, is a *likely* outcome for the smallest teachers under a competent bootstrap seed.

**Required fix — two acceptance routes, stated separately:**

- **Route A — Pipeline proof (SKIP path).** Criteria 1–6 plus lineage record plus resumability. Proves ingestion, characterization, differential evaluation, the skip decision, and recording. Demonstrates the *decision* machinery.
- **Route B — Transfer proof (train path).** All fourteen. Proves the *training* machinery.

**Recommend v1 require Route B**, with Route A recorded as a valid and informative intermediate milestone. Reason: Route A does not exercise generation, filtering, training, evaluation, regression, promotion, or quantization — which is most of the system. A Distillery that can only decide to skip has not been proven.

### IR-3 — MAJOR (traceability) — Identifier namespaces collide between the two documents

Both documents now live in `D:\Sovereign Distillery`. Their `OQ-` identifiers refer to **different questions**.

| ID | Validation report | Integrated report | Status |
|---|---|---|---|
| OQ-001 | Seed | Seed | ✅ Match |
| OQ-002 | Library inventory | Teacher inventory | ✅ Match |
| OQ-003 | v1 acceptance | v1 acceptance | ✅ Match |
| **OQ-004** | **Compute envelope (local vs. rented)** | **Promotion thresholds M / T** | ❌ **Collision** |
| **OQ-005** | **Promotion margin M / tolerance T** | **Training-mix ratios** | ❌ **Collision** |
| **OQ-006** | **Corpus mixing ratios** | **Long-term compute envelope** | ❌ **Collision** |
| OQ-007 | Distribution intent | Distribution intent | ✅ Match |
| **OQ-008** | **Smallest-to-largest: curriculum or risk ordering?** | **Native architecture timing** | ❌ **Collision + question dropped** |
| OQ-009 | Repository paths | Workspace interface contracts | ⚠️ Compatible — paths are a prerequisite of contracts |

**OQ-004, OQ-005, and OQ-006 have been rotated onto each other.** Any future reference to "OQ-005" is now ambiguous, and the ambiguity is invisible — both documents look internally consistent.

Additionally, the validation report's **OQ-008** (does smallest-to-largest stand as learning curriculum or as risk ordering?) has been **dropped from the register while actually being answered**. §12.3 resolves it correctly — retained as operator requirement, justified as engineering risk ordering, curriculum superiority demoted to **HYP-1** and marked for testing rather than installed as doctrine. That is exactly the right disposition. It is just no longer tracked as a resolved question, so the resolution is unfindable from the register.

**Recommended fix — adopt the integrated report's numbering as canonical** (it is the newer baseline; renumbering it would be worse) **and publish this crosswalk in the workspace** so validation-report references stay resolvable. Then add one entry:

> **OQ-010 — RESOLVED.** *Does smallest-to-largest function as a learning curriculum or as engineering risk ordering?* Resolved §12.2/§12.3: retained as operator requirement and justified as risk ordering. Curriculum superiority recorded as **HYP-1**, to be tested, not assumed.

Cheap now. Genuinely confusing in three months.

### IR-4 — MODERATE — Two of three corrections address claims not present in the source

Covered in §2.2 above. §72 and §113 misstate the validation report's position on the hardware envelope. REJ-5 rejects a claim that document did not make.

**Effect:** the project's record of *why* the working envelope was set is now inaccurate. The reasoning that actually applies — modelled estimate, explicit revisit condition, measurement scheduled as Phase 0 / D1 — is not preserved anywhere in the canonical baseline.

**Fix:** revise §72 and §113 to record agreement; retain REJ-5 as a standing principle, not as a correction.

### IR-5 — MODERATE — The Distillery Learning Engine is scoped as policy learning; the available sample size supports a lab notebook

*Relates to: §31, §32, §98, HYP-6*

The concept is right and the addition is valuable (§1.2 above). The **scoping** over-claims.

§98 proposes that historical runs "recommend transfer strategies, hyperparameters, curriculum structures, validation methods." Consider the data that will actually exist:

- Teacher queue: plausibly 10–30 models `ASSUMPTION` — the inventory is still unknown (OQ-002)
- Runs per teacher: roughly one, at least initially
- Teachers: heterogeneous in family, size, tokenizer, and specialization
- Repeated trials under matched conditions: approximately none

**That is n ≈ 20 non-repeated, non-matched, high-variance observations across a large configuration space.** No inference procedure recovers a hyperparameter policy from that. Any apparent pattern will be indistinguishable from noise, and — the real hazard — a system that *presents* such patterns as recommendations will be trusted more than the evidence supports.

**Distinguish two things the integrated report currently merges:**

| Component | Basis | Status |
|---|---|---|
| **§32 Transfer Strategy Selector** | Hand-written rules from architecture and capability type (same base → adapter; different arch → behavioral; code → execution validation) | **Sound.** Deterministic dispatch from known properties. Not learned, does not need to be. Build it. |
| **§98 hyperparameter / strategy recommendation from run history** | Statistical inference over run outcomes | **Over-claimed at this sample size.** |

**Recommended rescope:** the Distillery Knowledge Lineage is a **structured, queryable experiment record** — an engineering lab notebook with a schema. It answers *"what did we try, what happened, what did it cost."* That is genuinely valuable, it is achievable at n ≈ 20, and it is the necessary precondition for learned policy later.

Retain **HYP-6** ("the Distillery can learn transfer-strategy policies") as a long-horizon hypothesis, explicitly gated on accumulating enough matched trials to test it. Do not build a recommender against it yet.

### IR-6 — MODERATE — Phase D2 is blocked by a tooling constraint the roadmap does not acknowledge

*Relates to: §44, §88*

§44 correctly identifies teacher inventory as a blocker and §88 correctly schedules Phase D2 to resolve it. **Neither records that the blockage is currently a tooling/access failure, not merely unperformed work.**

Recorded evidence: a folder-access grant for `.ollama` and `.lmstudio` was **refused by the device bridge** during the validation review. The inventory has not been deferred by choice — the first attempt to obtain it failed.

**Practical consequence:** Phase D2 cannot begin until either (a) the model directories are connected via the desktop folder picker, or (b) the inventory is supplied by other means — `ollama list`, the LM Studio model directory listing, or a manual enumeration.

**Fix:** record the access constraint in §44 and add the unblocking step as D2's entry criterion, so the roadmap does not present D2 as ready-to-start when it is not.

**Secondary ordering note — D3 before D4.** Seed selection (D3) is scheduled before the evaluation system (D4). This works for the criteria §89 actually names — license, architecture, local trainability, tokenizer, context, migration potential — none of which need the eval suite. But it means the seed is frozen before any capability measurement of candidate seeds exists, and a poor choice surfaces only at D4 baselining.

Low-cost mitigation: shortlist 2–3 candidate seeds at D3 rather than freezing one, and let D4's baselining select among them. Cost is small; it removes a rework path.

### IR-7 — MINOR — Ownership of the Distillery Knowledge Lineage is ambiguous against the standalone requirement

§50 requires the Distillery to run standalone with optional sibling integration. §51 assigns "experiment memory" and "Distillery post-mortem analysis" to Sovereign. §31 places the Distillery Knowledge Lineage inside the Distillery. §58 gives it a directory, `distillery_memory\`.

If the knowledge lineage lives in Sovereign, INV-14 is violated. If it lives in the Distillery, §51's assignment needs narrowing.

**Recommended resolution:** the knowledge lineage is **owned by the Distillery** (`distillery_memory\`, per §58) and **optionally synchronized** to Sovereign for research and cross-subsystem reasoning. Sovereign consumes it; it does not own it. One sentence in §51 closes this.

### IR-8 — MINOR (process) — Evidence-labeling discipline regressed

The validation report labeled every substantive claim `FACT` / `ASSUMPTION` / `INTERPRETATION` / `SPECULATION` / `UNVERIFIED`, with source confidence stated. The integrated report uses labels only in §107.

Unlabeled confidence assertions now sit in the canonical baseline. Example, §112: *"Confidence: High that a practical v1 behavioral-distillation pipeline can be built from existing methods."* The reviewer **agrees** with that assessment — but its basis is not stated, and a reader cannot distinguish it from the surrounding design prose.

Given that this document is the baseline future work will inherit, and given the project's stated standard of traceability over confidence, recommend the labeling convention be carried forward. The cost is a few words per claim.

### IR-9 — MINOR — No stop, escalation, or stall policy

§29 includes `REMEDIATION` as a state. Neither document specifies:

- What happens when remediation fails repeatedly on the same teacher — retry limit? quarantine the teacher? proceed to the next?
- What constitutes a stalled lineage — N consecutive SKIPs? N consecutive rejections?
- When a run is abandoned rather than resumed

Without a stop policy, a failing teacher can absorb unbounded effort, and R-11 (scope drift) re-enters through an operational door rather than a strategic one.

**Suggested minimum:** a retry limit per teacher, a rule that a teacher exceeding it is quarantined with its failure recorded in the knowledge lineage, and a defined consecutive-SKIP count that triggers operator review of the queue rather than silent continuation.

### IR-10 — MODERATE — Removing the ceiling without restating the binding planning assumption invites optimism drift

*Relates to: §40, §41, §72*

The reviewer **agrees** that no permanent architectural ceiling should be asserted, and §41's list of possible future compute paths is legitimate.

The risk is in what the section does not say. §41 records: high confidence that local hardware constrains training scale; the exact ceiling not yet established; permanence not accepted. All true. But it leaves no **binding planning assumption for the interval before D1 completes**.

Until the machine is measured, the only safe basis for v1 planning is the **conservative** end of the envelope. A reader of §40–§41 could reasonably begin seed selection (D3) on the assumption that 7B is available. If D1 then shows 7B is not trainable — or that `sm_120` quantization kernels are unavailable at all (R-8, still unmeasured) — that work is discarded.

**Suggested one-line addition to §41:**

> **Interim planning constraint.** Until Phase D1 produces a measured hardware profile, all v1 planning assumes the conservative end of the estimated envelope. Configurations above that are treated as hypotheses to be tested at D1, not as available capacity.

This costs nothing if D1 comes back favourable and prevents rework if it does not.

---

## 4. Status carried forward unchanged

| Item | Status |
|---|---|
| **Library inventory (OQ-002)** | **Still blocking.** Access refused; not yet obtained by any route. |
| **Primary license audit** | Still outstanding. §45 adds a classification schema; the underlying evidence is still secondary-source. Classes cannot be assigned until primary license texts are read. |
| **Sibling repository interfaces** | Still uninspected. §51–§53 remain assumptions, correctly labeled as such in §51. Paths have been offered but not supplied. |
| **Measured hardware profile** | Still absent. Every VRAM figure in both documents remains a modelled estimate. |
| **`sm_120` toolchain viability** | Still unmeasured. R-8 / §67. If quantization kernels are unavailable for this GPU architecture, the local-training plan requires reconsideration regardless of everything else in either document. |

---

## 5. Recommended actions

Ordered by cost-to-benefit, cheapest first.

| # | Action | Cost | Addresses |
|---|---|---|---|
| 1 | Add the **drift floor `D`** as a second promotion gate alongside step tolerance `T` | One paragraph | **IR-1** — protects the metric §108 names as most important |
| 2 | Split v1 acceptance into **Route A (SKIP proof)** and **Route B (transfer proof)**; require B | One section | **IR-2** — removes an unsatisfiable conjunction |
| 3 | Publish the **OQ crosswalk**; adopt integrated numbering; add OQ-010 as RESOLVED → HYP-1 | One table | **IR-3** — preserves traceability |
| 4 | Revise §72 / §113 to record agreement; retain REJ-5 as a standing principle | Two edits | **IR-4** — accurate review history |
| 5 | Rescope §98 to a structured experiment record; keep §32's rule-based selector; gate HYP-6 | One section | **IR-5** — avoids over-claiming at n ≈ 20 |
| 6 | Add the **interim planning constraint** to §41 | One line | **IR-10** — prevents rework before D1 |
| 7 | Record the **access constraint** as D2's entry criterion; shortlist rather than freeze the seed at D3 | Two edits | **IR-6** |
| 8 | Assign knowledge-lineage ownership to the Distillery in §51 | One sentence | **IR-7** |
| 9 | Add a **stop / escalation / stall policy** | One section | **IR-9** |
| 10 | Carry the **evidence-labeling convention** into the baseline | Ongoing | **IR-8** |
| 11 | **Obtain the model library inventory** — connect the folder, or supply `ollama list` | Minutes, operator | **OQ-002 — the remaining hard blocker** |
| 12 | **Run Phase D1** — measure the machine before further design | Hours | R-8, and every VRAM figure in both documents |

Items 1–10 are edits to the integrated report. Items 11 and 12 are the only ones that produce new information, and item 11 is the only one that requires the operator specifically.

---

## 6. Reviewer's closing position

The integrated report does what an integration should: it takes an operator concept and an adversarial review, keeps what survived, restores what the review over-corrected, rejects what neither had evidence for, and adds four things neither contained.

Its treatment of the seed problem is better than the validation report's. Its INV-11 / INV-12 formulation of growth policy is better than the validation report's. Its separation of strategic objective from release acceptance is better than the validation report's. Those are conceded without qualification.

Two defects should be fixed before the document is treated as canonical, because both would surface as real failures rather than as documentation problems:

- **IR-1** — the promotion rule cannot protect cumulative capability retention, which the document itself names as the project's most important metric. Twenty individually legal promotions can destroy a capability. The ledger already stores the data needed; only the gate is missing.
- **IR-2** — the v1 acceptance criteria cannot be satisfied via the SKIP path they explicitly permit.

And one blocker is unchanged by 113 sections of specification: **the model library has still not been enumerated.** Every teacher-ordering, licensing, scheduling, and same-family-merge question in both documents is downstream of an inventory that does not exist and that one folder-picker click or one `ollama list` would produce.

The specification is now ahead of the evidence. The next useful work is measurement, not more architecture.

---

*This is a review. It is not an approval. Acceptance belongs to the operator.*
