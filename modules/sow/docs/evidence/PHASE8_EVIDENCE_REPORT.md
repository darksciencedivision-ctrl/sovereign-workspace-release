# PHASE 8 EVIDENCE REPORT — Gate Engine
Autonomous loop iteration 9 · 2026-07-17Z · gate: `gate/phase-8`

## Objective
Gate engine per Buildout Directive §5 Phase 8 / Plan §7-P8, §9.3: declarative gate
definitions; verdicts referencing evidence/debate records; failed artifacts cannot advance;
reasons traceable end-to-end. Exit: seeded-defect artifacts blocked at every stage boundary;
no bypass path including for the conductor. Also close the memory-layer half of invariant 18
(a gate may not promote/canonize an entry it authored).

## Source state
Tags through `gate/phase-7`; freeze `--check` clean throughout. `next_step: phase-8`.

## Files
- **Work commit `feecf157`:** `control_plane/gates/{criteria,engine,__init__}.py`;
  `control_plane/policy.py` (authorize_transition inv-18); 2 test files + edits to 2
  pre-existing tests (gate→operator for self-authoring shortcuts).
- **Remediation commit `10f11796`:** F1–F7 fixes + regression tests + publish-path inv-18.

## Exit criteria — met, mapped to code + test
- **Declarative gate definitions:** criteria stated before evaluation; unknown criterion,
  empty criteria, unknown kind all fail closed. Kinds local|stage|plan|acceptance.
- **Verdicts reference evidence/debate:** gate@1.0 record carries evidence + debate_ref;
  verdict = FAIL if any CRITICAL fails, else PASS_WITH_RESERVATIONS if any ADVISORY fails,
  else PASS — deterministic, no model output, no float. A dissent-preserved debate lowers to
  PASS_WITH_RESERVATIONS (not silent PASS); a converged debate passes clean.
- **Failed artifacts cannot advance; seeded defects blocked at every boundary:** each seeded
  defect (no artifact, claim without evidence, unresolved critical, placeholder marker, hash
  mismatch, size mismatch) → FAIL; FAIL → GATED_FAIL → BLOCKED with dependents BLOCKED.
- **No bypass including the conductor — structural:** the task state machine has no
  GATED_FAIL→DONE edge for ANY caller; `apply_to_task` advances ONLY on explicit
  PASS/PASS_WITH_RESERVATIONS and fails closed on FAIL/null/malformed; it re-validates the
  record and rejects a record naming a different task. Conductor cannot override.
- **Reasons traceable:** per-criterion reasons + gate_id + task_id + decided_by=gate_engine
  in the record.
- **Invariant 18 (memory half):** a gate may not promote an entry it authored (transition
  path) NOR publish its own work product directly into a promoted state (publish path);
  operator (human final authority) exempt. A gate's own decision verdict (kind=decision, e.g.
  a plan-gate) remains its authoritative output.

## Independent review (standard-stakes: validator + spec-auditor)
- **gate-validator: PASS.** Verified declarative/fail-closed, verdict determinism, seeded
  defects → FAIL → BLOCKED (+dependents), no-override as a genuine state-machine property
  (no force method exists), reasons traceable, inv-18 transition half + operator exemption,
  schema conformance, scope/freeze clean, no Phase 9 smuggled; confirmed the 3 gate→operator
  test edits are legitimate (operator is the exempt authority), not a masked break.
- **spec-auditor: FINDINGS 3 MAJOR / 2 MINOR / 3 NOTE.** Dispositions (all fixed pre-gate):
  - **F1 MAJOR — FIXED:** `apply_to_task` was fail-OPEN (any non-"FAIL" → DONE, no
    re-validation). Now advances only on explicit PASS/PWR; FAIL/null/malformed fail closed;
    record re-validated + task_id checked. Tests pin malformed-verdict + wrong-task.
  - **F2 MAJOR — FIXED:** inv-18 was evadable via publish (gate publishing own finding at
    ACCEPTED). authorize_publish now denies a gate self-publishing a work product
    (finding/evidence/artifact_ref) into a promoted state; scoped so a gate's own decision
    verdict still flows. Test pins the finding-kind block.
  - **F3 MAJOR — FIXED:** `_plan_acyclic` now does real DFS cycle detection (t1↔t2 cycle
    FAILs); was referential-integrity only. Test pins a real cycle.
  - **F4 MINOR — FIXED:** placeholder check uses word-boundary regex + expanded markers
    (no 'mastodon'→'todo' false positive; catches XXX/WIP/HACK/stub/placeholder).
  - **F5 MINOR — FIXED:** apply_to_task rejects a record whose task_id ≠ target.
  - **F6 NOTE — FIXED:** docstrings corrected (state machine is absolute for all callers; no
    operator-force path implemented this phase → U21).
  - **F7 NOTE — FIXED:** artifact size_bytes cross-checked against content length.
  - F8 NOTE — addressed: added cycle / malformed-verdict / hash&size-mismatch / publish-path
    tests.

## Substitutions (loop directive §6)
None material — the gate engine is deterministic control-plane logic; criteria operate on a
GateContext assembled from real artifacts/structured output/debate records.

## Deviations / carried
- ruff unavailable (pip out of scope); code typed + stdlib-first.
- Carried: U21 (new: operator state-force override path referenced in the plan is not
  implemented this phase — the task state machine is currently absolute; recovery from a FAIL
  is redo-and-repass); U15 fully closed (both debate and memory halves of invariant 18).

## Gate verdict
**PASS.** All Phase 8 exit criteria met; seeded-defect artifacts blocked at every boundary;
no-bypass is a genuine state-machine property; the three MAJOR review findings (fail-open
apply, publish-path inv-18 evasion, non-detecting cycle check) all fixed with pinning tests
before closure. 273/273 tests.

## Commits
Work `feecf157` → remediation `10f11796` → this evidence/register commit (tagged `gate/phase-8`).

## Next phase
`phase-9` — Scoped context compiler (control_plane/routing/): role+task+need-to-know context
assembly from MCP; no default full-transcript forwarding; measured token reduction vs a naive
baseline on a reference project.
