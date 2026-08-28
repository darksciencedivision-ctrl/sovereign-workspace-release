# PHASE 1 EVIDENCE REPORT — Terminal compositor spike
**Date:** 2026-07-16 · **Builder:** Claude (Fable 5) in Cowork · **Status: GATE OPEN —
rig delivered; ConPTY measurements require the operator's Windows run; exit = operator
ratifies D-UI-01.** Format per Buildout Directive §6.

## Objective
Deliver the Phase 1 throwaway spike rig (`tools/spike_compositor/`, Electron + xterm.js +
node-pty) able to demonstrate every Plan §16 requirement and machine-evaluate every kill
criterion, within the environment constraint that ConPTY cannot execute in the build
sandbox (register E2).

## Source state
Phase 0 gate passed (self-check 7/7; tag `gate/phase-0`, commit `cc0bceb…`); operator
freeze signature still outstanding — surfaced, not blocking spike tooling (spike is
explicitly throwaway tooling, not product UI, per Plan §16 prohibitions).

## Approach discipline
Plan-before-code per Directive §2.6: `SPIKE_PLAN.md` written first (architecture, probes,
kill-criteria mapping, test plan), then code.

## Files created
`SPIKE_PLAN.md`; `package.json` (pinned: electron ^31, node-pty ^1.0, @xterm/xterm ^5.5,
@xterm/addon-fit ^0.10); `main.js` (PTY ownership, session registry, latency + wrong-pane
probe, resize-correctness scan, metrics sampler, kill-criteria evaluator, report writer);
`preload.js`; `renderer/index.html` + `renderer/renderer.js` (6–8 xterm panes, guided
checklist buttons, layout/resize/latency storms, detach/reattach);
`scenarios/tui.js` (alt-screen resize-aware TUI, self-reports dims — U9 probe);
`scenarios/streamer.js` (rate-controlled SEQ stream — output-loss probe);
`lib/` (stats, seq-check, ring-buffer, layout, session-registry — pure logic);
`test/` (5 files, 21 tests, zero dependencies); `RUN_ON_WINDOWS.md` (operator runbook).

## Commands run & results (sandbox-verifiable subset)
- `node --check` on all 15 JS files → clean.
- `node --test test/*.test.js` → **21/21 pass** (percentile math incl. censored samples;
  seq gaps/dupes/restarts incl. chunk-boundary and CRLF; byte-exact ring-buffer replay +
  overflow; near-square grid n=1..12 + pinned double-cell + membership-key stability;
  registry legal-transitions/detach-reattach-immutability/no-orphan teardown).
- `npm install --dry-run --ignore-scripts` → full dependency tree resolves from the
  public registry (no installs performed in sandbox; Electron/ConPTY are Windows-host
  concerns).

## Performance measurements
**None claimed.** Every ConPTY-dependent number (p95 input latency, output loss at
1 MB/s, RAM/CPU at 6 and 8 panes, resize/TUI behavior, orphan check) must come from the
operator's Windows run — the rig writes `results/SPIKE_REPORT_<ts>.{json,md}` with the
kill-criteria table filled and any unmeasured criterion explicitly marked UNMEASURED.
No sandbox result is represented as a ConPTY result.

## Deviations
None from Plan §16 scope. Two honest limitations recorded in RUN_ON_WINDOWS.md: ConPTY
host processes sit outside Electron's metrics API (identical across framework candidates;
comparison unaffected); renderer latency is data-arrival, not pixel-flip (main-path p95
is the gate metric).

## Unresolved issues
U9/U12 get their answers from the operator run. Kill-criterion trigger ⇒ Tauri +
portable-pty rerun before any ratification (rig's verdict line says this itself).

## Gate verdict
**OPEN.** Deliverable complete and verified to the extent the sandbox permits. Exit
requires: (1) operator runs the guided checklist on Windows; (2) report reviewed;
(3) operator ratifies or rejects D-UI-01. Also outstanding from Phase 0: freeze-manifest
signature.

## Commit
This report + rig committed as Phase 1 work (no `gate/phase-1` tag until the operator
ratifies). Hash recorded in the decision register's gate table.

## Next phase
On D-UI-01 ratification → Phase 2 (node process manager). On kill-criteria trigger →
Tauri rerun of the identical rig, then comparative evidence to the operator.

---
## ERRATA (appended 2026-07-16, after independent gate-validator review)

- **E-1 (validator F2):** the commit hash first recorded in the decision register
  (`b2c6fd535aa3`) was the pre-amend hash and is not reachable in history; the actual
  Phase 1 delivery commit is `e60fac8d06df`. Cause: amending the commit to embed its own
  hash — the Phase 0 two-commit convention exists to prevent exactly this and is binding
  from now on. Corrected by dated register row.
- **E-2 (validator F4):** rig gaps closed — explicit **minimize** control added to the
  pane bar (Plan §16 verbatim list); automated kill-criteria row added for **"instability
  at 6 terminals"** (unexpected tui/streamer exits or nonzero-code exits; operator-typed
  `exit` in shells excluded); README current-phase line corrected. 21/21 logic tests
  still green; all files `node --check` clean.

---

## AUTORUN GATE CLOSURE (appended 2026-07-16 local / 2026-07-17Z, autonomous loop iteration 1)

**Objective:** run the Phase 1 spike unattended on the Windows host per AUTONOMOUS_BUILD_DIRECTIVE
`phase-1-autorun`; close the gate + D-UI-01 by operator-delegation (OP-1/OP-3) on recorded evidence.

**Source state:** tags `gate/phase-0`, `gate/phase-0.1`; freeze `--check` clean before and after
(only append-only registers differ). Work commit for the retrofit: **b09c96f81a87d3cc911874c151ba83822362c1ad**.

**Files changed (work commit):** `main.js` (autorun IPC, automated criteria 8/9, scenario host fix,
resize-criterion null-collapse fix), `renderer/renderer.js` (named scenario functions + autorun driver),
`scenarios/tui.js` (mode-con authoritative size), `RUN_ON_WINDOWS.md` (autorun instructions),
new `lib/lifecycle-check.js`, `lib/orphan-scan.js`, their tests, three `test/manual_*.js` U9 diagnostics,
`package-lock.json`.

**Commands run:** `npm install` (registry only; Electron postinstall failed silently on this host —
binary extracted manually from the intact npm cache zip, recorded as environment note E4);
`npm test` → **31/31 pass**; smoke autoruns (`SPIKE_AUTORUN=1 SPIKE_AUTORUN_WAIT_S=5`) exposing three
rig defects (see work-commit message); full evidence run `SPIKE_AUTORUN=1` (60 s windows).

**Evidence run (this host, Win 11 10.0.26200, 20 cores/64 GB, Electron 31.7.7, scenario host node.exe):**
`docs/evidence/PHASE1_SPIKE_REPORT_20260717T022713Z.json` (copy of
`tools/spike_compositor/results/SPIKE_REPORT_2026-07-17T02-27-13-485Z.json`):
- **All 9 kill criteria measured; none triggered. Verdict: "NO KILL CRITERIA TRIGGERED".**
- p95 input latency (main echo path) **1.88 ms** (n=190, 0 timeouts; threshold 50 ms).
- Streamer integrity: **1,459,864 SEQ lines, 0 gaps** (~0.85 MB/s effective vs ~1 MB/s nominal —
  timer granularity/backpressure; `restarts:16` are ConPTY re-wrap re-emissions during pane
  resizes, ~166 replayed lines, no loss — forward gaps would count as loss and are 0).
- Resize: 29/56 raw checks ok; per-episode analysis (validator-verified): **29/29 resize requests
  converged to exact requested dims** (non-ok entries are expected transitional redraws).
- Layout storm ×20 (maximize/restore/detach/reattach): `allAlive:true, newGaps:0`.
- RAM (Electron processes): peak 470 MB @6 panes, **587 MB @8 panes** (budget 2048 MB, builder
  default standing in for the plan's operator-set budget under OP-3 delegation).
- Cross-pane input hits: 0. Unexpected session deaths: 0.
- Lifecycle (automated): `{ok:true, checked:8}` — every session has spawn + terminal event.
- ConPTY containment (automated, fail-closed on scan error): 0 alive PTY pids, 0 orphan
  conhost/OpenConsole after teardown.

**Independent confirmation (gate-validator subagent, isolated context): PASS_WITH_RESERVATIONS.**
Validator re-ran `npm test` (31/31), verified verdict logic is computed (all three branches exercised
in the results history), performed anti-overfit review (thresholds unchanged; new automated criteria
have fail-path tests; falsifiability shown by the recorded KILL/INCOMPLETE runs), confirmed scope
clean + freeze intact, and **reproduced the result with its own autorun**
(`docs/evidence/PHASE1_SPIKE_REPORT_VALIDATOR_RERUN_20260717T023356Z.json`: 0 triggered, p95 1.13 ms,
gaps 0, 16/16 episodes converged).

**Validator reservations (owned; dispositions):**
1. Renderer paint latency n=0 is dead instrumentation (`probeWatch.marker` never assigned) —
   recorded as known limitation; end-to-end latency inferred (1.88 ms + ≤2 frame budgets ≪ 50 ms).
   Not fixed in-rig: throwaway code, main-path latency is the gate criterion.
2. Machine resize criterion is weak ("never matched") — mitigated by the per-episode analysis above.
3. U9 stays **OPEN-qualified**: ConPTY resize + Node-child staleness characterized
   (`test/manual_*.js` diagnostics); a real console-subsystem TUI (e.g. OpenCode) not yet exercised —
   re-verify at P6/P10 when the real coding TUI runs in a pane.
4. Autorun exercises maximize/detach/reattach/terminate but not minimize/pin (view-level only).
5. 8-pane window is 60 s — adequate for envelope, thin for slow-growth detection; long-run memory
   behavior falls to Phase 2 soak + Phase 13 hardening.
6. Effective streamer rate ~0.85 MB/s recorded (above).
7. ANSI rendering correctness beyond TUI-SIZE parsing not machine-asserted.
8. node-pty `AttachConsole failed` stderr noise at teardown in validator rerun (exit 0, scan clean).
9. Register follow-ups — closed with this commit (D-UI-01 row, U9/U12 updates, gate row).

**Substitutions (loop directive §6):** operator interactive run → autorun on the same host
(same code paths as the manual buttons); operator-judgment criteria 8/9 → automated equivalents
with fail-path tests; spec-auditor subagent → covered by the gate-validator's measurement-validity
+ anti-overfit inspection for this phase (throwaway rig, no product code; spec-auditor resumes at
Phase 2+ product code).

**Deviations:** Electron postinstall failure (E4, environment not product); D-UI-01 closed by
delegation instead of interactive ratification (OP-1/OP-3).

**Gate verdict: PASS.** Exit criteria all met on machine evidence; kill criteria all false;
**D-UI-01 = Electron + xterm.js + node-pty (ConPTY), decided_by: operator-delegation
(ruling 2026-07-16)**; Tauri remains the named fallback if later phases surface a disqualifier.

**Next phase:** phase-2 (node process manager).
