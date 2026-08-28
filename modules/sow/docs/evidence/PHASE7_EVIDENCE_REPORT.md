# PHASE 7 EVIDENCE REPORT — Debate Service
Autonomous loop iteration 8 · 2026-07-17Z · gate: `gate/phase-7`

## Objective
Reusable Debate Service per Buildout Directive §5 Phase 7 / Plan §19.2 (I-DS1): any
authorized node may request; ≤5 rounds, early stop, dissent preserved, per-debate token
budget + cost governor; caller authorization via the broker. Exit: §2.8 debate acceptance
tests pass, incl. non-conductor caller and budget-exhaustion cutoff. Also addresses U15
(invariant 18: no node solely judges its own work).

## Source state
Tags through `gate/phase-6`; freeze `--check` clean throughout. `next_step: phase-7`.

## Files
- **Work commit `78db24c9`:** `debate_service/{cost_governor/governor, evidence_manager/
  manager, round_manager/manager, service, __init__}.py`; `control_plane/policy.py`
  (authorize_debate); 2 test files + `tests/fixtures/mock_debater.py`.
- **Remediation commit `63cf1148`:** F1–F5 fixes + regression tests.

## Exit criteria — met, mapped to code + test
- **Reusable / any authorized node (I-DS1, not conductor-coupled):** `DebateService` holds
  no conductor reference; `policy.authorize_debate` allows worker/conductor/gate/operator,
  denies voice/unknown (deny-by-default). Test: a **worker** (non-conductor) runs a full
  debate; voice refused.
- **≤5 rounds hard cap (inv 14):** `RoundManager.run` clamps `min(max_rounds, 5)` regardless
  of request. Test: request 99 → rounds_used ≤ 5.
- **Early stop + dissent preserved (inv 15, no consensus forcing):** early stop on
  convergence; when no convergence, distinct position strings preserved **verbatim** in the
  record's `dissent`. Test: "keep"/"drop" both flow to `result.dissent`, outcome
  DISSENT_PRESERVED.
- **Cost governor (inv 17):** per-debate budget + per-caller period quota + global concurrent
  cap; **Decimal** accounting (never float); budget exhaustion → clean BUDGET_EXHAUSTED
  cutoff with partial record kept. Tests: budget 250/round 100 → 2 rounds, cost_actual 200;
  quota + cap + concurrent-bypass all covered.
- **Evidence-based (model votes are not evidence):** an assertion is SUPPORTED only if a
  citation resolves to a real MCP entry (`mcp_resolver` fails closed); convergence requires
  alignment AND ≥1 supported position. Tests: unsupported marked; all-unsupported agreement
  is NOT convergence.
- **Invariant 18 / U15:** the resolved participant set must include a node other than the
  caller, checked before any cost is charged. Test: caller-only debate refused.
- **Immutable MCP record:** debate@1.0 record (schema-validated with the node@1.0 ref store)
  published as a CANDIDATE evidence entry a gate can reference; provenance complete;
  policy-mediated (not an MCP bypass).

## Independent review (standard-stakes: validator + spec-auditor)
- **gate-validator: PASS.** Ran the suite (239→246), mapped every exit criterion to inspected
  code + self-run tests; confirmed cap/dissent/budget/inv-18/evidence/deny-by-default;
  schema conformance with the node ref store; scope/freeze clean; no Phase 8 smuggled
  (`debate_service/gate/` is an empty Phase-0 scaffold). Non-blocking notes recorded.
- **spec-auditor: FINDINGS 1 MAJOR / 4 MINOR / 4 NOTE.** Dispositions:
  - **F1 MAJOR — FIXED:** per-caller quota bypassable via concurrent debates (quota checked
    only at open against a snapshot). Fixed with reservation accounting — open reserves the
    full budget against the quota (available = quota − committed − in-flight reserved), close
    reconciles to actual spend. Pinned by a concurrent-bypass regression + slot-free +
    period-reset tests.
  - **F2 MINOR — FIXED:** malformed request now fails clean (DebateAuthorizationError) before
    any slot opens; budget tokens=0 handled. Parametrized test.
  - **F3 MINOR — FIXED:** `reset_period(caller)` added (the quota was a lifetime cap).
  - **F5 MINOR — FIXED:** removed unused import + param (ruff-clean).
  - F4 MINOR — accepted: per-debate budget clamped to quota headroom is not separately
    disclosed in the frozen debate@1.0 record; conveyed via outcome + cost_actual (schema is
    additionalProperties:false, can't add a field) → U20.
  - NOTE 6/7/8/9 — recorded: CUT_OFF init is a defensive default (unreachable, harmless);
    participants-descriptors vs actual debaters is cosmetic (real node_ids in positions);
    single-non-caller debater is inv-18-valid though degenerate; added the missing
    concurrent/slot/reset test coverage.

## Substitutions (loop directive §6)
Deterministic MockDebater participants stand in for model debaters; the Debate Service
mechanics (rounds, budget, dissent, evidence validation, cost governance, authorization)
are the real code under test.

## Deviations / carried
- ruff unavailable (pip out of scope); code typed + stdlib-first; unused-import finding fixed
  by inspection.
- Carried: U20 (new: effective-budget disclosure limited by frozen debate@1.0 shape);
  `early_stop_criteria` request field is passthrough (spec-named triggers convergence/budget
  are enforced).

## Gate verdict
**PASS.** All Phase 7 exit criteria met; §2.8 acceptance (non-conductor caller, bounds,
dissent, cost cap, invariant 18) holds; the one MAJOR (concurrent-quota bypass) fixed with
reservation accounting + regression tests before closure. U15 (no node solely judges its own
work) now enforced. 246/246 tests.

## Commits
Work `78db24c9` → remediation `63cf1148` → this evidence/register commit (tagged `gate/phase-7`).

## Next phase
`phase-8` — Gate engine: declarative gate criteria, verdicts referencing evidence/debate
records, failed artifacts cannot advance, no conductor override path. Seeded-defect artifacts
blocked at every stage boundary.
