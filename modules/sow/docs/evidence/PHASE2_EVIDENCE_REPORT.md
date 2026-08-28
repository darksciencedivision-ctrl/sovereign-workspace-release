# PHASE 2 EVIDENCE REPORT — Node Process Manager
Autonomous loop iteration 2 · 2026-07-16/17Z · gate: `gate/phase-2`

## Objective
Node process manager per Buildout Directive §5 Phase 2 / Plan v1.0.1 §7-P2: registry
(identity, class, adapter), state machine, heartbeat, append-only event log, crash
detection/restart — proven by a fault-injected multi-node soak.

## Source state
Tags `gate/phase-0`, `gate/phase-0.1`, `gate/phase-1` present; freeze `--check` clean at
start and end of the iteration. `LOOP_STATE.json` `next_step: phase-2`.

## Files changed
- **Work commit `8c0ea84a8d602ce74dfdcfbdd40604ed5a507318`:** `control_plane/nodes/`
  (states, event_log, registry, heartbeat, process_manager, `__init__`); tests (31 unit +
  5 integration + fixture `tests/fixtures/sim_node.py`); `tools/soak/phase2_soak.py`;
  `conftest.py`; smoke/qualifying soak artifacts of the pre-remediation code.
- **Remediation commit `2dde9a727fc545db81826acb0cebea52fea7e52b`:** spec-audit fixes
  (below) + 4 new deterministic error-path tests + post-fix smoke artifacts.

## Commands run (all on this host)
`py -3.12 -m pytest tests/ -q` → **74 passed** (70 before remediation tests).
Soak smoke runs (60 s) and qualifying runs (1800 s) via `tools/soak/phase2_soak.py`.

## Tests and results
- Unit 35: state-machine legality (incl. TERMINATED fully absorbing, PAUSED
  resume-to-interrupted-only), event log (tamper/delete detection, corrupt-reopen
  refusal, seq continuation), registry (I-C1 refusal logged, duplicate refusal logged,
  heartbeat recovery, spawn grace), process-manager error paths (fake processes:
  orphan-on-failed-registration reaped; kill-failure logged + retried until dead;
  disconnect-reclaim counts unexpected → restarts; monitor never touches PAUSED).
- Integration 5 (real subprocesses): ready-via-heartbeat; crash → unexpected exit →
  incarnation 2; restart budget exhaustion; hang → DISCONNECTED → reclaim;
  terminate_all leaves nothing alive (verified via `OpenProcess`, not registry claims).

## Performance / soak measurements — QUALIFYING RUN (post-remediation code)
**`tools/soak/results/PHASE2_SOAK_20260717T061053Z.json` + `_events.jsonl`** —
Python 3.12.10, 8 real nodes, hb 250 ms, kills every 20 s, hang lane 45 s, 1801 s wall:
- **PASS 6/6 machine-checked criteria** (verdict computed, not hard-coded):
  no orphans (OS pid check, `terminate_all` leftovers `[]`); event log ordered
  (2,131 rows, contiguous seq, intact sha256 chain); complete (135 spawns = 135 exits);
  all 1,607 transitions replay legally, all 135 incarnations end TERMINATED;
  fault pressure real (89 induced kills, 127 restarts, 38 disconnect-reclaims);
  duration ≥ 1800 s.
- Identical fault totals to the superseded pre-fix run are expected: kills are
  cadence-driven (⌊1800/20⌋≈89) and the hang lane is deterministic (45 s × 38 cycles).
- Superseded runs kept for the record: `…052649Z` (pre-fix qualifying, PASS — **not**
  gate evidence because supervision code changed after audit), `…052358Z` (smoke, honest
  FAIL on fault-pressure — demonstrates criteria can fail), `…052539Z`/`…060929Z`
  (60 s smokes, PASS; not qualifying).

## Independent review
- **gate-validator (isolated context): PASS_WITH_RESERVATIONS.** Ran the suite itself;
  wrote its own event-log replay (0 illegal transitions, 0 resurrections, spawns=exits,
  log wall-span 1800.2 s, tamper probe detected); confirmed criteria computed and
  falsifiable; scope + freeze clean; 30-invariant drift check clean.
  Reservations → dispositions:
  R1 evidence report with pinned qualifying run + substitution + D-LANG-01 closure →
  this document + register rows. R2 duration floor lives in invocation config → floor
  restated here: qualifying run measured 1801.3 s ≥ 1800 s. R3 30-min soak ≠ 24 h-class
  defects (leaks/handles) → acknowledged; long-horizon behavior falls to Phase 13
  hardening. R4 I-C1 is flag-checking until real node auth (Phase 3/3A) → acknowledged,
  see also audit F12. R5 ruff not installed; pip not within permitted network use →
  style bar unverified by machine; code typed + stdlib-only.
- **spec-auditor (isolated context): 2 MAJOR / 7 MINOR / 6 NOTE, no BLOCKER.**
  Dispositions (remediation commit `2dde9a72`):
  **F1 MAJOR fixed** — spawn() reaps the OS process when registration fails after Popen
  (+ fake-process test). **F2 MAJOR fixed** — kill failures append `kill_failed` events;
  poll() retries DISCONNECTED reclaim until exit observed (+ test).
  F3 fixed (backoff outside lock); F4 partially fixed (grace clocks pruned; monitor
  TOCTOU accepted as self-healing, noted); F5a fixed (utf-8/replace decoding);
  F5b/F5c accepted for phase scope (reader-thread teardown noise; dead KeyError guard);
  F6 fixed (reclaim-restart pinned by test); F7 fixed (PAUSED-skip pinned by test);
  F8 fixed (docstring records tail-truncation detection limit; compensating control =
  spawn/exit pairing); F9 fixed (duplicate refusals logged); F10 accepted (vacuous
  attribute test; real property carried by tamper tests); F11 accepted (pid-reuse
  caveat, fails safe); F12 accepted + recorded (I-C1 honor-system until 3/3A);
  F13 accepted (seed ≠ reproducibility; nothing claims otherwise); F14 fixed
  (record_exit validates the transition); F15 register note added (transition graph is
  implementation-defined beyond the frozen enum — recorded, not silent).

## Substitutions (loop directive §6 — explicitly recorded)
1. **24 h fleet run → 1800 s accelerated soak** (authorized by AUTONOMOUS_BUILD_DIRECTIVE
   §5 phase-2 row): time-compressed heartbeats (250 ms), induced kills every 20 s, hang
   lane for the DISCONNECTED path, 8 real simulated nodes. **No 24 h-equivalence is
   claimed**; long-horizon defects (leaks, handle growth) are out of this run's reach.
2. Heartbeat transport = child stdout lines — a Phase 2 supervision channel only; makes
   no claim about the Phase 3A MCP transport.
3. Simulated nodes (`tests/fixtures/sim_node.py`) stand in for real adapter nodes; the
   governance path under test (registry/state machine/log/supervision) is the real code.

## Deviations
- ruff unavailable (pip outside permitted network use) — recorded above (R5).
- Pre-fix qualifying soak superseded after spec-audit remediation; re-run on shipped code.

## Unresolved issues (carried)
- Monitor TOCTOU can spuriously reclaim a freshly-beating node (self-healing, burns one
  restart-budget unit) — accepted at this phase, revisit if soak flakiness appears.
- Reader-thread teardown may drop late `node_output` events after log close (F5b) —
  cosmetic at this phase.
- I-C1 enforcement is caller-flag-checking until Phase 3/3A node auth (R4/F12).

## Gate verdict
**PASS.** All §5 Phase 2 criteria met on machine evidence from the shipped code;
both MAJOR audit findings fixed with pinning tests before gate closure.
**D-LANG-01 CLOSED: Python 3.12 (3.12.10 on host), decided_by: operator-delegation
(ruling 2026-07-16)** — recorded in the decision register with this gate.

## Commits
Work `8c0ea84a` → remediation `2dde9a72` → this evidence/register commit (tagged
`gate/phase-2`).

## Next phase
`phase-3` — Sovereign node runtime (directive/role/permission loaders, supervisor
containment scaffold, local gate, structured-output validation, workspace binding).
