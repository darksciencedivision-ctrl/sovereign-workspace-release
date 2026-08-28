# PHASE 16F `.assembled` — EVIDENCE REPORT

**Work unit:** `phase-16f.assembled` (sub-step 1 of the Phase 16F decomposition, **`.assembled` → `.close`**)
**Date:** 2026-07-25 · **Iteration:** 69 · **Status:** PASS (sub-step)
**Tag:** none. `gate/phase-16f` + `product/usable` close **only** when the final `.close` sub-step lands
with the **mandatory** independent `gate-validator` confirmation (16F **is** a directive-flagged
high-stakes gate — §15) and the FINAL report addendum. Same whole-track-gate convention as
14A/15E/16C/16D/16E: no per-sub-step gate tag.
**Governing directive:** `AUTONOMOUS_BUILD_DIRECTIVE.md` **§15 track 16F** (*"Assembled run in the
operator's shell: type to the live conductor, watch it spawn/drive picker-selected workers in panes,
approval exercised, restart recovery — receipts + FINAL report addendum + `product/usable`. High-stakes
gate."*), **§13 (OP-8 — the conductor is a live conversational pane)**, loop protocol §3, substitution
§6, **D-P16-0 binding** (every shell/UI change exercised by an in-Electron autorun self-check writing a
machine-readable receipt), honesty §10.4. Load-bearing invariants: **1** (operator holds final
authority — the app never self-authorizes), **2** (no naked session — every pane is supervised-admitted),
**16** (explicit gates, no override), **18** (no node judges its own work — the gate verdict is the gate
node's), **3/24** (fail-closed; a substituted/mock surface is always visibly named, never overclaimed).

---

## 1. Decomposition — `.assembled` → `.close` (directive §3.2)

Phase 16F is the **final, high-stakes** validation track and the Phase-16 terminal state
(FINAL report addendum + `product/usable`). It is decomposed into two reviewable sub-steps to keep each
unit test-first and to avoid the over-reach that stalled 16d.recovery, while honoring the mandatory
gate-validator requirement at the close:

- **`.assembled` (this unit):** build the assembled operator-visible in-Electron self-check, run it on
  this host, prove every leg composes in ONE shell session, run the spec-auditor, write this evidence,
  two-commit — **no gate tag**.
- **`.close` (next unit):** re-run the assembled self-check FRESH (foreground), obtain the **mandatory**
  independent `gate-validator` confirmation on the whole track, write the FINAL report addendum, tag
  `gate/phase-16f` + `product/usable`, set the Phase-16 terminal state.

## 2. What this sub-step delivers — the assembled run composes in one session

Phase 16A–16E each proved one surface in-Electron and each honestly marked the **assembled** proof
"owed to 16F" (16E: `deliverConductorChat` → *"conductor session not admitted (owed 16F)"*; 16D
recovery: *"the live governed worker SPAWN … owed 16F/U70"*; 16D approvals: *"the shared long-lived
queue … owed 16F"*). This sub-step closes the **composition** gap: one packaged Electron process drives
the whole operator-visible run and writes one receipt.

| File | Change |
|---|---|
| **`apps/desktop/selfcheck/assembled-selfcheck.js`** (NEW) | The assembled in-Electron self-check. Six legs, each measured (no fabricated pass), fail-closed (any unproven leg throws ⇒ `ok:false`). Writes `docs/evidence/receipts/PHASE16F_ASSEMBLED_SELFCHECK.json`. |
| **`apps/desktop/main.js`** | 3 wiring edits: `require` of `runAssembledSelfCheck`; the `SHELL_SELFCHECK` kind dispatch gains `"assembled"`; the runner branch calls `runAssembledSelfCheck(ctx)`. No behavior change to any production path. |
| **`apps/desktop/selfcheck/run.js`** | 2 wiring edits: the one-command doc line + the arg dispatch gain `assembled`. |

### The six composed legs (all against the REAL renderer + REAL ConPTY + REAL Python governed feeds)

1. **Conductor governed-born** — supervision READY (governed spawn path, invariant 2), `conductorState()`
   reports `spawnGoverned:true`, pane-1, honest `awaiting_live_conductor`.
2. **Type to the conductor (closes the 16E-owed WRITE)** — admit a **supervised** interactive ConPTY
   session (a stand-in for the operator-run live `claude` backend, §6), deliver a CHAT through the
   **production** `deliverConductorChat` path (the same fn typing + voice-IN use), assert `written:true`
   (no longer *"owed 16F"*) **and** the transcript **echoes** into the rendered xterm buffer — a real PTY
   round-trip. `live_backend_operator_run:true` and the OWED live backend are recorded; **no live model
   answered**.
3. **Spawn/drive picker-selected workers** — record a governed **picker** selection targeting a worker
   pane (badge previews `Opus 4.8`), and read the governed **dispatch** feed sourced from the Python flow:
   routing **BY DESCRIPTOR** (invariant 4), `2` artifacts gate-**ACCEPTED** (verdict `PASS` — the gate
   node's verdict, invariant 18), legs **mock-honest** (conductor=mock, workers=mock), the live worker
   leg **OWED (U58)**, loopback MCP **torn_down** (D-LOOP-1).
4. **Approval exercised** — source the approval drawer through the same preload bridge the renderer uses
   (`source:"emitter"`, 3 governed rows), then **route** an operator decide to the governed authority:
   approving a **clarification** is **GOVERNED-REFUSED** (invariant 16, no override) and `selfAuthorized:false`
   (the shell forwarded; Python decided — invariant 1).
5. **Restart recovery** — the persisted layout snapshot carries the worker's model chrome; the production
   restart fold reconstructs the **conductor-first** layout (pinned P0, `awaiting_live_conductor`) + the
   worker chrome, **not** re-attached (invariant 2); a simulated fresh renderer (badges dropped) repaints
   the worker badge from the reconstructed snapshot after `shell:recovery`.

## 3. Self-check every exit criterion (real command output, this host, foreground)

**In-Electron assembled self-check** (`node selfcheck/run.js assembled`, packaged Electron 31.7.7 /
node 20.18.0 / win32-x64):

```
[selfcheck:assembled] conductor input delivered + echoed into admitted session pane-2
[selfcheck:assembled] governed dispatch: 2 accepted by descriptor, legs mock-honest, U58 owed
[selfcheck:assembled] approval drawer sourced (3 rows); governed decide routed + refused (invariant 16)
[selfcheck:assembled] restart recovery: conductor-first + worker chrome repainted from reconstructed snapshot
[selfcheck:assembled] PASS → docs/evidence/receipts/PHASE16F_ASSEMBLED_SELFCHECK.json
shell exited code=0
```

Receipt `PHASE16F_ASSEMBLED_SELFCHECK.json` — `ok:true`, every leg true:
`legs.{supervision_ready, conductor_governed_born, conductor_input_delivered, workers_dispatched,
picker_worker_selected, approval_exercised, restart_recovered}` all `true`;
`conductor_input.written:true` / `.echoed:true`; `dispatch.by_descriptor:true` / `.accepted_count:2` /
`.acceptance_verdict:"PASS"` / `.legs_mock_honest:true` / `.live_workers_owed:true` / `.torn_down:true`;
`approval.sourced_from_emitter:true` / `.decide_governed_refused:true` / `.self_authorized_false:true`;
`recovery.*` all `true`. **OWED (honest):** live conductor backend (§6 operator-run), live workers
(U58), live worker spawn (U70).

**Test suites (foreground, this host):**
- `apps/desktop/test/*.test.js` (`node --test`) → **158 passed / 0 failed**.
- `terminal/test/*.test.js` (`node --test`) → **173 passed / 0 failed**.
- `py -3.12 -m pytest tests/ -q` → **1109 passed / 0 failed** (207.41 s).

## 4. Independent review — spec-auditor (this sub-step)

`spec-auditor` (isolated context) on the new self-check + the 5 wiring edits + the sources it consumes:
**VERDICT CLEAN** — no invariant violation, no prohibited drift, no dishonesty. Confirmed: no live
frontier call; no mock surface overclaimed as real (leg 2 names its stand-in and records
`live_backend_operator_run:true` + OWED legs; leg 3 requires `legs_mock_honest` **and** `live_workers_owed`
so it cannot pass while pretending workers were live); invariant 1 (approvals `self_authorized_false`,
conductor input is a forwarded CHAT); invariant 2 (both spawns via `createPaneWithSession`/supervised
admission, gated on `isSupervised`); invariant 16 (clarification approve is governed-refused); fail-closed
(`receipt.ok = every leg`). One **MINOR robustness** note: the per-leg `waitFor` ceilings can, on a
pathologically slow host, sum above the launcher's 150 s `HARD_TIMEOUT_MS`, yielding a **false FAIL**
(exit 124) — fail-closed, never a fabricated PASS. Observed wall-clock this host: **~4 s** (18:03:18 →
18:03:22), far under budget; recorded as an honest limitation, no change required for this sub-step. The
**mandatory** high-stakes `gate-validator` runs at `.close`.

## 5. Substitutions & OWED (directive §6 / §10.4 — honest)

- **Live interactive `claude` conductor backend** — **operator-run (§6)**. The loop never starts a live
  frontier session (§2.4 remains except the OP-6/OP-9 lift, which the loop does not exercise autonomously
  here). Leg 2 proves the shell's conductor-input **delivery + echo** path against a supervised stand-in
  ConPTY; the receipt records `live_backend_operator_run:true` and the OWED backend. Never presented as a
  live model answer.
- **Live worker CLI legs / governed worker spawn** — **OWED (U58 / U70)**. The dispatch ran mock-first
  (honest legs); the picker selection is recorded (badge + chrome survive restart); the live governed
  spawn from a selection is the operator-run surface.
- **Timeout robustness (MINOR)** — recorded above; fail-closed.

## 6. Invariants honored

1 (no self-authorization: approvals `selfAuthorized:false`, conductor input is a forwarded CHAT verdict) ·
2 (no naked session: every pane supervised-admitted, gated on `isSupervised`) · 3/24 (fail-closed; the
mock/stand-in surfaces are visibly named, never overclaimed) · 4 (dispatch routing BY DESCRIPTOR) ·
16 (explicit gate, no override — clarification approve refused) · 18 (the acceptance verdict is the gate
node's `PASS`, not the synthesizer's) · 27 (byte-exact scrollback: the echo is read from the real xterm
buffer) · D-LOOP-1 (every spawned PTY/gateway/loopback-MCP torn down within the unit).

## 7. Two-commit convention (this sub-step)

- Work commit: `apps/desktop/selfcheck/assembled-selfcheck.js` (NEW) + `main.js`/`run.js` wiring.
- Evidence commit: this report + `docs/evidence/receipts/PHASE16F_ASSEMBLED_SELFCHECK.json`, carrying the
  work-commit hash. **No gate tag** — deferred to `.close`.

*End of `phase-16f.assembled` evidence report.*
