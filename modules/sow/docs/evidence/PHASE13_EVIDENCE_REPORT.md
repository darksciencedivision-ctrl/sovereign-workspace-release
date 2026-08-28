# PHASE 13 EVIDENCE REPORT — Evaluation & Hardening (final build phase)
Autonomous loop iteration 14 · 2026-07-17Z · gate: `gate/phase-13`

## Objective
Evaluation & hardening per Buildout Directive §5 Phase 13 / Plan §7-P13, §12.4: a comparative
harness across four configurations on the reference project; cost-to-accepted-output
instrumentation; kill-matrix recovery tests; hardening backlog triaged. Report losses honestly;
model-quality conclusions limited to mock/local backends and must say so.

## Source state
Tags through `gate/phase-12`; freeze `--check` clean throughout. `next_step: phase-13`.

## Files
- **Work commit `b579f90a`:** `tools/evaluation/harness.py`;
  `tests/evaluation/test_comparative_eval.py`; `tests/recovery/test_kill_matrix.py`;
  `docs/evidence/PHASE13_EVAL_REPORT.json`.
- **Remediation (R1/R2):** real Debate Service wired into C4; `docs/HARDENING_BACKLOG.md`;
  this report.

## Exit criteria — met, mapped to code + test
- **4-config comparative harness:** C0 single-pass / C2 conductor+raw / C3 Sovereign no-debate /
  C4 Sovereign+debate all run end-to-end and are distinct. The Sovereign configs exercise the
  REAL governance path (MCP publish CANDIDATE + provenance → GateEngine.evaluate over 6 stage
  criteria → transition to ACCEPTED); `accepted` increments only on a real PASS verdict. **C4
  now runs the REAL Debate Service** (a `debate@1.0` record is produced; `debate_id` in the
  report), not a synthetic surcharge (R1 closed).
- **Cost-to-accepted-output instrumentation:** real tokens (tiktoken cl100k_base), control_ops,
  wallclock, accepted count, cost_to_accepted per config. Measured curve (deterministic fields):
  C0 = 45 tok/accepted (0 ops); C2 = 47 (2 ops); C3 = 47 (8 ops); C4 = 247 (14 ops, real debate).
  The honest reading: governance + debate is a real cost the operator pays for provenance,
  gating, and adversarial review — the baselines are cheaper because they do less and lack those
  capabilities.
- **HONEST LIMITATION (the phase's make-or-break criterion):** stated prominently in the harness
  docstring, as a top-level `honest_limitation` field in the report JSON, and enforced by a test:
  all backends are deterministic MOCKS → the harness measures ORCHESTRATION cost + capabilities,
  **NOT model reasoning quality**; **no config is claimed to reason better**; a real model-quality
  comparison needs live/local models (deferred, Track E).
- **Kill-matrix recovery:** real faults at three layers — node crash → detected + restarted (event
  log intact); MCP disconnect → fail-closed (McpDisconnected) + on-disk store reopens intact;
  conductor loss → successor reconstructs with zero loss.
- **Hardening backlog triaged (R2 closed):** `docs/HARDENING_BACKLOG.md` triages every carried
  item (U1–U24 + deferred-live) into DEFERRED-HARDWARE / DEFERRED-LIVE / DEFERRED-P-LATER /
  ACCEPTED with severity; highest-priority live-deployment item identified (U10 OS-level
  same-user isolation).

## Independent review (standard-stakes: validator)
- **gate-validator: PASS_WITH_RESERVATIONS.** Ran the suite (330) + eval/recovery tests (none
  skipped); reproduced the deterministic cost metrics; confirmed the Sovereign configs use the
  real governance code (not faked), the honesty statement is prominent and truthful (no config
  credited with better reasoning), and recovery faults are real. Reservations → dispositions:
  - **R1 (debate leg simulated) → FIXED:** C4 now invokes the real DebateService (debate_id in
    the report; test asserts it).
  - **R2 (hardening backlog artifact missing) → FIXED:** `docs/HARDENING_BACKLOG.md` added;
    this evidence report added.

## Substitutions (loop directive §6)
All backends are deterministic MOCKS — stated as the harness's central limitation. The harness
measures orchestration cost + capabilities, not model quality; a live/local model comparison is
Track E (deferred). The governance/debate/recovery machinery under measurement is real code.

## Deviations / carried
- ruff unavailable (pip out of scope); code typed + stdlib-first (recorded in the backlog).
- All carried unresolved items triaged in `docs/HARDENING_BACKLOG.md`.

## Gate verdict
**PASS.** The comparative harness runs all four configs on the real governance path (C4 with the
real Debate Service); cost-to-accepted-output is instrumented with a real tokenizer and the cost
curve is honest; the mock-backend limitation is stated prominently and no model-quality claim is
made; kill-matrix recovery is tested at three layers with real faults; the hardening backlog is
triaged. Both validator reservations closed before the gate. 330/330 tests.

## Commits
Work `b579f90a` → remediation (real debate + backlog) → this evidence/register commit (tagged
`gate/phase-13`).

## Next
`finalize` — FINAL_BUILD_REPORT.md at repo root + tag `build/complete` + set loop state COMPLETE
(the one moment the operator is addressed).
