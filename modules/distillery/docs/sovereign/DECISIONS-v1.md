# Sovereign Distillery — Accepted Decisions, v1

**Date:** 19 August 2026 · **Authority:** Operator ruling, recorded verbatim in substance · **Status:** CLOSED unless marked otherwise

This is a decision ledger, not a specification. It exists so the rulings are findable. It deliberately adds no architecture.

---

## 1. Promotion gate — CLOSED

```
PROMOTION requires:
  1. Target capability gain          ≥ M
  2. Step regression   (vs Parent)   ≥ -T
  3. Historical drift  (vs Best)     ≥ -D
  4. No critical regression
  5. Valid provenance + lineage
  6. Operator promotion
```

A breach of **D** requires an explicit operator override recorded in lineage.

*Rationale (operator):* turns deliberate capability tradeoffs into governed decisions rather than accumulated erosion.

**Supersedes:** IR-1. **Amends:** integrated report §28.
**Residual items requiring one more ruling:** RD-1, RD-2, RD-3 (§6 below).

## 2. v1 acceptance — two routes — CLOSED

**Route A — Pipeline / SKIP proof.** Ingest → characterize → evaluate → compute delta → correctly SKIP → record provenance/decision → resume successfully.
= valid intermediate milestone. **≠ Distillery v1 complete.**

**Route B — Transfer proof.** Ingest → characterize → identify useful delta → generate corpus → validate corpus → train candidate → evaluate → run regression → pass T and D → promote/reject correctly → preserve lineage → produce deployment artifact → resume successfully.
= **required Distillery v1 proof.**

**Supersedes:** IR-2. **Amends:** integrated report §79, §95, §102.
**Residual item:** RD-4 (§6 below).

## 3. Identifier traceability — CLOSED

The **integrated report owns canonical numbering.** Permanent crosswalk below.

| Canonical ID | Question | Validation-report ID |
|---|---|---|
| OQ-001 | SOV-SEED | OQ-001 |
| OQ-002 | Teacher inventory | OQ-002 |
| OQ-003 | v1 acceptance | OQ-003 |
| OQ-004 | Promotion thresholds M / T *(now also D)* | OQ-005 |
| OQ-005 | Training-mix ratios | OQ-006 |
| OQ-006 | Long-term compute envelope | OQ-004 |
| OQ-007 | Distribution intent | OQ-007 |
| OQ-008 | Native architecture timing | *(new — no prior ID)* |
| OQ-009 | Workspace interface contracts | OQ-009 *(paths are its prerequisite)* |
| **OQ-010** | **Smallest-to-largest: curriculum or risk ordering?** | OQ-008 |

**OQ-010 — RESOLVED.** Retained as operator requirement; justified as engineering risk ordering (integrated §12.2). Curriculum superiority retained as **HYP-1**, to be tested, not assumed.

**Supersedes:** IR-3.

## 4. Hardware-envelope history — CORRECTED

Canonical history, per operator ruling:

> The validation report and integrated specification **agree** that the current hardware envelope is provisional, conservative, and subject to empirical measurement. INV-11 / INV-12 supersede the earlier wording by stating the policy more precisely: scale does not increase automatically, but may increase when capacity evidence and approved compute permit it.

**REJ-5 is retained** as a standing invariant against future scope distortion — **not** as a rejection of any validation-report finding.

**Interim planning constraint (binding until D1 completes):** all v1 planning assumes the **conservative end** of the estimated compute envelope. Higher configurations are hypotheses to test, not available capacity.

**Supersedes:** IR-4, IR-10. **Amends:** integrated report §41, §72, §113.

## 5. Scoping and ownership — CLOSED

| Item | Ruling | Supersedes |
|---|---|---|
| **Knowledge Lineage v1** | An **experiment database**, not a learned oracle. Records attempt, teacher/student pair, architecture, curriculum, dataset, hyperparameters, hardware, runtime, VRAM/RAM, result, gains, regressions, failures, remediation, quantization effects. | IR-5 |
| **Transfer Strategy Selector** | Deterministic / rule-based initially. | IR-5 |
| **HYP-6** | Gated. Tested only after enough comparable experiments accumulate. | IR-5 |
| **Ownership** | Distillery owns `distillery_memory\`. Sovereign may consume / synchronize. Preserves INV-14 standalone operation. | IR-7 |
| **Seed selection** | D3 selects **2–3 candidates**; D4 baselines all; **D4.1 selects canonical SOV-SEED**; D5+ proceeds. | IR-6 |
| **Teacher Disposition State** | `PENDING · ELIGIBLE · SKIPPED_NO_DELTA · DISTILLING · PROMOTED · REJECTED · QUARANTINED_TECHNICAL · QUARANTINED_DATA · QUARANTINED_LICENSE · DEFERRED_COMPUTE · SUPERSEDED` | IR-9 *(operator extension)* |
| **Stop / escalation budgets** | `retry_budget_per_stage · retry_budget_per_teacher · maximum_remediation_cycles · consecutive_skip_threshold · consecutive_rejection_threshold · stall_timeout · operator_escalation_required` | IR-9 *(operator extension)* |
| **Evidence labeling** | Carried forward into the baseline. | IR-8 |

## 6. Residual items — OPEN, small

Four second-order gaps in the rules just adopted. Each is a one-paragraph fix. Listed for ruling, not elaborated.

| ID | Gap | Why it matters |
|---|---|---|
| **RD-1** | After a **D**-breach override, historical best is unchanged, so every later candidate also breaches **D** and needs its own override. | **D** degenerates from a gate into a permanent alarm. Fix: an override re-baselines a recorded **governed floor** for that capability; **D** is then measured against the governed floor, with historical best retained for reporting. |
| **RD-2** | Promotion condition 1 requires target-capability **gain ≥ M**. A **remediation** candidate (§29 `REMEDIATION`) exists to *restore* a capability, not to gain one — so it is unpromotable under the rule as written. | The remediation state has no legal exit. Fix: a remediation route that passes on **restoration toward historical best** in place of condition 1. |
| **RD-3** | Condition 4, "no critical regression," has no definition of *critical*. | Not machine-checkable. Fix: a per-capability criticality tag in the Capability Ledger (e.g. `CRITICAL / STANDARD / EXPERIMENTAL`). |
| **RD-4** | Route B contains both "promote/reject correctly" **and** "produce deployment artifact." A correctly-**rejected** candidate cannot produce an artifact. | Same conjunction defect as IR-2, at smaller scale. Fix: Route B requires a **promoted** candidate; a correct rejection is a distinct outcome that proves the training and evaluation machinery but does not close v1. |

## 7. Project state — operator classification, recorded

| Dimension | State |
|---|---|
| Architecture | Substantially defined |
| Validation | Strong conceptual review completed |
| Canonical specification | Not yet frozen |
| Implementation | Pre-build |
| **Primary hard blocker** | **Model library inventory (OQ-002)** |
| **Primary empirical blocker** | **Measured hardware / toolchain profile (D1)** |
| Primary unresolved strategic decision | Final SOV-SEED selection after candidate baselining (OQ-001 → D4.1) |
| Primary scientific risk | Cumulative capability retention |
| Primary implementation proof | Route B end-to-end transfer |

**Standing directive:** architecture expansion is closed. Further prose requires a stated reason.
