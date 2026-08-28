# PHASE 5 EVIDENCE REPORT — Conductor Prototype (conductor + two workers)
Autonomous loop iteration 6 · 2026-07-17Z · gate: `gate/phase-5`

## Objective
Conductor prototype per Buildout Directive §5 Phase 5 / Plan §7-P5, §3.4 F1: conductor
loads conductor files via MCP before any assignment; launches/assigns 2 workers via
Sovereign+MCP; routes 1 artifact; capability-based assignment through the Scheduler; all
transfers logged. Exit: end-to-end trace shows zero manual transcript routing; every hop has
provenance; plan gate + acceptance packet produced. Backend = mock (live providers prohibited).

## Source state
Tags through `gate/phase-4`; freeze `--check` clean throughout. `next_step: phase-5`.

## Files
- **Work commit `6573b8d1`:** `control_plane/tasks/graph.py`; `scheduler/{capability_registry/
  registry, resolver/resolver, scheduler}.py`; `adapters/local/{worker,__init__}.py`;
  `control_plane/orchestration/conductor_prototype.py`; 2 test files.
- **Remediation commit `a861a990`:** failure-path + review fixes.

## Exit criteria — met, mapped to code + test
- **Conductor loads files before any assignment:** `ConductorAdapter.start()` loads the 12
  files from MCP (Phase 4); the prototype calls `start()` + `run_cycle` before any `add_task`
  or `schedule_ready`. Structurally enforced (fails closed until all files loaded).
- **2 workers assigned via Sovereign+MCP, by capability:** the Scheduler resolves each READY
  task's `capability_req` to a node **by descriptor** (`CapabilityResolver`), never by model
  name (I-SC1); both workers assigned, distinct, by load-ranking. Tests: resolver picks by
  capability (incapable node registered first, so an order-based stub fails); 2 assignments.
- **1 artifact routed CANDIDATE→gate→ACCEPTED:** worker publishes CANDIDATE (reads scoped
  context from an MCP entry ref, runs the node-local gate first); the worker **cannot
  self-promote** (policy denies); the gate node promotes to ACCEPTED. Tests: rogue-worker
  ACCEPT refused; findings reach ACCEPTED.
- **Failed artifact cannot advance (invariant 16):** local-gate FAIL or stage-gate REJECT →
  task GATED_FAIL/BLOCKED; dependents stay BLOCKED. **Now exercised end-to-end** (real
  worker→gate REJECT→dependent BLOCKED) + an F3 regression (a 'TODO' objective trips the
  local gate without crashing).
- **Zero manual transcript routing:** every worker reads context from an MCP entry ref (no
  transcript parameter exists); every result leaves via an MCP publish. Test asserts the
  worker logged an `m-` context ref AND the published bytes contain the MCP-sourced objective.
- **Every hop has provenance:** accepted findings carry `provenance.task_id` + author + the
  promoting gate as `reviewers` + `gate_result`. Tested.
- **Plan gate + acceptance packet produced:** plan gate is a gate-published ACCEPTED decision;
  acceptance packet is a conductor-published CANDIDATE decision (conductor proposes, operator
  accepts — invariant 1). Both asserted.
- **§12.2 broker-mediation leg (U16, deferred from P4):** re-checked — every worker action
  (get_content/publish/transition) transits control_plane.policy; no bypass. Closed.

## Independent review (standard-stakes: validator + spec-auditor)
- **gate-validator: PASS_WITH_RESERVATIONS.** Confirmed capability-by-descriptor (not order),
  worker-cannot-self-promote at the authority, zero-transcript structural, provenance, plan
  gate + packet, broker-mediation leg, scope/freeze clean, no invariant drift. Reservation R2:
  the invariant-16 failure path was only unit-tested → **fixed** (end-to-end test added).
- **spec-auditor: FINDINGS 3 MAJOR / 3 MINOR / 3 NOTE**, all in the failure-path dimension;
  invariant posture otherwise CLEAN (I-SC1, I-7, I-10/M6, I-16, I-18, no premature Phase 6).
  Dispositions:
  - **F3 MAJOR — FIXED:** reachable KeyError crash — an objective containing a placeholder
    marker ('TODO'/'TBD'/'FIXME') fails the worker's local gate, `execute()` returned no
    `entry_id`, and `run()` did `result["entry_id"]`. Orchestrator now handles the not-published
    branch → GATED_FAIL/BLOCKED; docstring claim now matches code. Regression test added.
  - **F2 MAJOR — FIXED:** invariant-16 failure path now tested end-to-end (real gate REJECT →
    dependent BLOCKED).
  - **F1 MAJOR — FIXED:** resolver-by-capability test registers the incapable node first
    (order-based stub now fails it).
  - **F4 MINOR — FIXED:** resolver tie-break is a stable `node_id` key, not registration order.
  - **F5 MINOR — FIXED:** conductor `read_accepted()`/`publish_acceptance_packet()` public
    methods; orchestrator no longer reaches into adapter privates (policy was never bypassed).
  - **F7 NOTE — FIXED:** `TaskGraph.get()` takes the lock. **F8 NOTE — addressed:** zero-transcript
    test now asserts the published bytes contain the MCP-sourced objective.
  - **F6 MINOR / F9 NOTE — recorded:** locality only `local_only` is a real constraint
    (`any`/`frontier_ok` both permit — correct; documented); `benchmark_score` is a flagged
    Phase-6 (Track E/R10) placeholder. → U18.

## Substitutions (loop directive §6)
Mock reasoning/worker backends stand in for real models (no provider network use); the
governed orchestration path (MCP context routing, capability scheduling, task-graph state,
gate promotion, provenance) is real code.

## Deviations / carried
- ruff unavailable (pip out of scope); code typed + stdlib-first.
- Carried: U18 (benchmark ranking is a placeholder until Phase 6 Track E; locality semantics
  note); U16 closed; U15 (approver≠author) still → P7/P8.

## Gate verdict
**PASS.** All Phase 5 exit criteria met on machine evidence from the remediated code; the
one reachable crash (F3) and the untested failure path (F2) both fixed with pinning tests
before closure; capability scheduling is genuinely descriptor-driven (I-SC1); zero manual
transcript routing is structural. 212/212 tests.

## Commits
Work `6573b8d1` → remediation `a861a990` → this evidence/register commit (tagged `gate/phase-5`).

## Next phase
`phase-6` — multi-model & local adapters: ≥3 backends behind capability descriptors
(mock-frontier claude_code-shaped, OpenCode+local-coder if detected else mock-coder, ≥1 local
reasoning); selection demonstrably by descriptor not name. Live-subscription + R8 ToS work is
out of scope by prohibition (recorded as deferred-live), not a failure.
