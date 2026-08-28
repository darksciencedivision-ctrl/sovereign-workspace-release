# PHASE 15E `.recovery` — EVIDENCE REPORT

**Work unit:** `phase-15e.recovery` (sub-step 6 of the Phase 15E decomposition:
`.picker` → `.spawn` → `.conductor-pane` → `.objective` → `.voice` → **`.recovery`** → `.gate`)
**Date:** 2026-07-24 · **Iteration:** 56 · **Status:** PASS (sub-step)
**Tag:** none. `gate/phase-15e` is a HIGH-STAKES phase gate and closes only at `.gate`, when all
seven sub-steps have landed and the mandatory independent gate-validator confirms the phase.
**Governing directive:** `AUTONOMOUS_BUILD_DIRECTIVE.md` **§9 track 14A ("UI recovery after process
restart")**, **OP-7 §12.4 (conductor-first startup)**, OP-8 §13 (the conductor is a live interactive
pane), §11 track 15E ("restart recovery with panes reattaching"), loop protocol §3, substitution
rules §6, honesty §10.4. Load-bearing canonical invariants: **2** (every terminal is a supervised
Sovereign node — no naked sessions), **1** (operator holds final authority — the app never
self-authorizes), **3** (conductor is an interface + selection, never a vendor default), **12/27**
(immutable append-only history; everything observable), **§2.4/§10.4** (mock-first; no live call in
this unit).

---

## 1. What this sub-step delivers

15E exit criterion (§12/§13): *"restart recovery restoring the conductor-first layout … panes
reattaching."* Phase 14A's `.recovery` already reconstructed the SESSION lifecycle (which PTYs
existed + their disposition) and re-verified the governed channel. This sub-step adds the
**conductor-first LAYOUT** dimension: after a full shell-process restart the workspace comes back
with the **pinned CONDUCTOR as pane 1** and the **worker panes reattaching** — fail-closed, no naked
session auto-respawned (invariant 2), nothing admitted until the channel re-verifies. It **composes**
the existing session fold + RecoveryMachine + PaneModel and re-implements none of them (Directive §4).

- **`terminal/recovery/layout-reconstruct.js` (NEW)** — pure/deterministic, no clock/I/O/Node:
  - `buildLayoutSnapshot({panes, conductorPaneId, meta})` captures the pane structure the PaneModel +
    conductor id + an optional per-pane chrome lookup give it (order, role, mode attended/autonomous,
    model, pinned, sessionId). Fail-closed defaults: unknown mode ⇒ `autonomous`, blank model ⇒ null.
  - `reconstructLayout({snapshot, sessions, admissionOpen, selection})` folds the persisted snapshot
    together with the reconstructed session view (`terminal/recovery/reconstruct`) and the current
    admission state into the ordered conductor-first layout the shell rebuilds. Two fail-closed rules:
    **(1) conductor-first is STRUCTURAL, not data-driven** (OP-7 §12.4) — the pinned pane-1 CONDUCTOR
    is emitted **unconditionally**, even with a null/corrupt snapshot, rebuilt from the operator
    SELECTION (invariant 3), honestly `awaiting_live_conductor`, never a fabricated executing
    checkpoint; **(2) no pane reattaches to a LIVE session on boot** (invariant 2) — every worker is
    `reattach:false` / `admitted:false`; a session alive at the cut folds to `needsRelaunch:true` /
    `paneState:"awaiting_supervision"`; a pane whose session has no lifecycle record fails closed to
    relaunch; and while the channel is not re-verified (`admissionOpen:false`) even the conductor is
    `admitted:false` — no naked session during the gap.
- **`apps/desktop/recovery-store.js` (CHANGED)** — added `persistLayout(snapshot)` / `loadLayout()`,
  writing the layout snapshot to a sibling `layout.json` in the same in-repo, gitignored `.recovery/`
  dir with the **same atomic-write + fail-closed-read** machinery (refactored the shared temp-write-
  then-rename into `_writeAtomic`). A missing/corrupt snapshot ⇒ `null` ⇒ a conductor-only
  reconstruction; never a throw. The session-log persistence is untouched.
- **`apps/desktop/main.js` (CHANGED, operator-run wiring, §6)** — imports the fold; adds
  `conductorSelection()` (the operator selection in the fold's {model,verified,isFallback} shape),
  `paneMeta(id)` (per-pane chrome; today only the conductor carries governed chrome — worker panes
  predate the node-launcher, owed — so they snapshot honestly as role `worker` / model null),
  `persistLayoutSnapshot()` (best-effort, called at every structural change: pane create/destroy/pin,
  conductor create, session lifecycle), and `reconstructConductorFirstLayout()` (boot fold). On boot
  it folds + logs + sends `shell:recovery` with the reconstructed layout **before** `supervisor.start()`,
  so the surfaced admission is fail-closed SHUT until the channel verifies.
- **`apps/desktop/renderer/renderer.js` + `preload.js` (CHANGED)** — the recovery banner surfaces the
  reconstructed conductor-first layout honestly ("✓ conductor-first layout restored — CONDUCTOR pane 1
  pinned, N worker pane(s), admission OPEN/SHUT") plus the panes needing SUPERVISED relaunch (HTML-
  escaped ids). Backward-compatible with the prior `{interrupted}` payload.

### Scope discipline (kept honest, NOT faked)
This sub-step delivers the layout-recovery fold + its persistence + the boot wiring. The rendered
window / reattaching panes are an operator-run surface (directive §6, the Phase-1 substitution
pattern), exactly like every GUI in this build; the LOGIC is what is headless-tested. The actual
pane-1 CONDUCTOR placement is (re)built by `createConductorPane()` on `did-finish-load`; interrupted
worker panes are surfaced for the operator to relaunch under supervision — never auto-respawned.

---

## 2. Substitution (directive §6) — what is proven headlessly vs operator-run

- **Proven headlessly (governance-bearing):** the full deterministic fold — conductor-first is always
  a pinned pane-1 CONDUCTOR even with no snapshot; the operator SELECTION label (never a fabricated
  checkpoint); interrupted-vs-ended-vs-absent worker disposition; `reattach:false`/`admitted:false`
  for every worker; nothing admitted during the gap; atomic + fail-closed persistence round-trips
  across a simulated restart — all pure/deterministic, no Electron, no live socket, no `claude`
  process (§2.4/§10.4).
- **Operator-run metric (like every GUI in this build):** the rendered window, the panes visibly
  reattaching, and the on-screen recovery banner. The DATA path (snapshot persist/load + fold) is
  headless-tested (`terminal/test/layout-reconstruct.test.js`, `apps/desktop/test/recovery-store.test.js`);
  the painting is operator-verified.

**No live model call was made in this work unit.**

---

## 3. Self-check — every exit criterion with real command output

| Exit criterion (§9 track 14A / OP-7 §12.4 / §11 track 15E) | Evidence |
|---|---|
| Restart **restores the conductor-first layout** (pinned CONDUCTOR pane 1) — structural, not data-driven | `layout-reconstruct.test.js`: "reconstructLayout ALWAYS yields a pinned pane-1 CONDUCTOR, even with no snapshot"; "a full round-trip proves conductor-first layout recovery across a restart" |
| CONDUCTOR badge shows the operator **SELECTION**, never a fabricated checkpoint (inv 3) | "reconstructLayout shows the SELECTION label, never a fabricated checkpoint" (null selection ⇒ `(unknown selection)`, `verified:false`); `nodeState` always `awaiting_live_conductor` |
| **Panes reattaching** — a worker alive at the cut needs SUPERVISED relaunch, never auto-attached (inv 2) | "a worker whose session was still alive at the cut needs supervised relaunch, never auto-attached" (`reattach:false`, `admitted:false`, `paneState:"awaiting_supervision"`) |
| A cleanly-ended worker reconstructs as history | "a cleanly EXITED worker reconstructs as ended history, not needing relaunch" |
| Unknown-fate session ⇒ **fail closed to relaunch** | "a pane whose session has NO lifecycle record has an unknown fate ⇒ fail-closed to relaunch" |
| **No naked session during the gap** — nothing admitted until the channel re-verifies | "while the channel is NOT re-verified, NOTHING is admitted"; conductor `admitted` tracks the channel and is asserted true only when `admissionOpen` (else false) |
| Fail-closed persistence (missing/corrupt ⇒ conductor-only, atomic, sibling file) | `recovery-store.test.js`: "the layout snapshot is stored in a sibling layout.json"; "persistLayout then loadLayout round-trips…"; "loadLayout on a missing or corrupt snapshot fails closed to null" |
| Read-only fold; append-only history not mutated (inv 12) | "reconstructLayout is deterministic and does not mutate its inputs" |
| Supervision DENIED on channel loss, re-admit only on a re-verified channel | unchanged, via the already-gated `RecoveryMachine`/`IpcSupervisor` (`supervisor.js`); the boot fold reads `supervisor.ready` |

**Test totals (real output):**
- JS: `node --test "terminal/test/*.test.js"` → **155 passed** (+11 over the 144 `.voice` baseline;
  new file `terminal/test/layout-reconstruct.test.js` = 11). `node --test "apps/desktop/test/*.test.js"`
  → **38 passed** (+3 over 35; the 3 new layout-snapshot cases in `recovery-store.test.js`).
- Python: `py -3.12 -m pytest tests/ -q` → **1011 passed** (unchanged — no Python changed this step).
- Shell files (`main.js`, `preload.js`, `renderer/renderer.js`, `recovery-store.js`, and the new
  `layout-reconstruct.js`) pass `node --check`.

**Mutation-intent check (invariant 2):** the no-naked-re-spawn rule is load-bearing — see the
gate-validator's load-bearing probe in §5 (forcing `reattach`/`admitted` true makes exactly 3 tests
fail; a still-alive worker would then come back auto-attached).

---

## 4. Invariant / prohibition check

- **Inv 2 (no naked/auto-attached sessions)** — every worker in the fold is `reattach:false` /
  `admitted:false`, unconditionally; interrupted and unknown-fate sessions surface for supervised
  relaunch only; the boot payload spawns nothing (it reconstructs + logs + sends a banner). ✔
- **Inv 1 (operator holds final authority; app never self-authorizes)** — recovery only reconstructs
  and surfaces; it admits/spawns nothing by itself; the interrupted panes wait for the operator to
  relaunch them through the supervised admission path. ✔
- **Inv 3 (conductor is interface + selection, never a vendor default)** — the recovered CONDUCTOR
  badge is derived from the operator SELECTION label, honestly `awaiting_live_conductor`, `verified`
  only when the record says a live reply reported the checkpoint; never a hard-coded runtime default. ✔
- **Inv 12/27 (append-only, observable)** — the session log + the layout snapshot are read, never
  mutated (determinism/non-mutation asserted); `_writeAtomic` preserves the last-good file across a
  crash; recovery is logged + bannered. ✔
- **OP-7 §12.4 (conductor-first is structural)** — `_conductorEntry` is emitted unconditionally in
  `reconstructLayout`, always `ordinal:1, pinned:true`; proven with a null snapshot. ✔
- **§2.4/§10.4 / §6** — mock-first: no `claude`/live call; the fold is pure (no `subprocess`/`socket`/
  `urllib`); the window/panes are operator-run, recorded, never overclaimed. ✔
- **Directive §4** — the module composes `reconstruct` + `RecoveryMachine`/`IpcSupervisor` + PaneModel;
  re-implements no lifecycle, no supervision, no authority. ✔
- Frozen canonical set untouched: `docs/canonical/` unmodified (git status clean); the four pinned
  canonical hashes intact (`6D3FD03B`, `8C9B7240`, `668089B5`, `CC414372`);
  `config/live_operation.json` remains gitignored/untracked. `gate/phase-15e` tag ABSENT.

## 5. Reviews (fresh this iteration, foreground per D-LOOP-2 PRINT-MODE FACT)

- **spec-auditor (substantive new code): CLEAN** — no invariant violation, no prohibited drift.
  Traced inv **2** (workers hard-coded `reattach:false`/`admitted:false`, unconditionally; the
  renderer banner never instantiates an xterm or attaches a pane; the boot fold spawns nothing), inv
  **1** (recovery reconstructs/surfaces only; boot fold reads `admissionOpen:false` because
  `supervisor.start()` runs later — correct fail-closed ordering), inv **3** (badge from the operator
  selection, `awaiting_live_conductor`, no fabricated checkpoint; the recorded `fable-5` is the
  operator SELECTION label, cleanly separated from the null/unverified executing state), inv **12/27**
  (read-never-write; `_writeAtomic` last-good survival), OP-7 §12.4 (conductor emitted unconditionally,
  proven by the no-snapshot test), and fail-closed persistence. No TTS/voice-out, no credential
  handling, no `mcp_server/` authorization, no float, no invented governance, no overclaiming (comments
  correctly present the window as operator-run). **Three NITs, all non-blocking:** (1) the conductor's
  `admitted` reflects the channel while workers are always false — internally consistent and
  documented; **addressed this iteration** by adding an explicit `conductor.admitted===true` assertion
  under an open channel (pins the intent). (2) `buildLayoutSnapshot` computes a worker `ordinal` that
  `reconstructLayout` recomputes — harmless self-describing metadata in the persisted snapshot,
  **accepted**. (3) `loadLayout`'s `typeof === "object"` guard also admits an array — downstream
  degrades safely to a conductor-only layout (non-Array `panes` ⇒ `[]`), defense-in-depth, **accepted**.
- **gate-validator (sub-step, isolated): PASS.** Independently reproduced the counts in its own
  context (`155` terminal JS / `38` apps/desktop, zero failures; `node --check` clean on all changed
  JS; confirmed the new file contributes exactly 11 tests). **Load-bearing mutation probe (invariant
  2):** backed up `layout-reconstruct.js`, forced the worker `reattach`/`admitted` to `true`, re-ran →
  3 tests fail; restored the file **byte-identical (SHA-256 `26f6355c…a2f9320` re-verified)**, deleted
  the backup, re-ran to green. Confirmed conductor-first is structural (unconditional pinned pane-1
  even with a null snapshot; selection label, `awaiting_live_conductor`), nothing admitted during the
  gap (boot `shell:recovery` emitted before `supervisor.start()`), fail-closed persistence (null on
  missing/corrupt, atomic temp+rename to a sibling `layout.json`, session log untouched, `.recovery/`
  gitignored), and no prohibited drift (`docs/canonical/` + `mcp_server/` untouched; no
  credential/TTS/float; `config/live_operation.json` untracked; `gate/phase-15e` ABSENT). No test
  process bound a port. Two owned, non-blocking reservations: Python not re-run (zero `.py` files
  changed this step — confirmed by `git status`); untracked `apps/desktop/package-lock.json` predates
  this sub-step and is correctly NOT swept into the gate commit.

## 6. Owed / deferred (honest limits)

- The rendered window + visibly-reattaching panes + the on-screen recovery banner are an operator-run
  surface: the DATA path (snapshot persist/load + fold) is headless-tested; the painting is
  operator-verified (the Phase-1 substitution pattern).
- **Per-pane worker chrome for the snapshot** (which model/role a worker pane runs, attended vs
  autonomous) is only populated for the conductor today; worker panes predate the node-launcher UI, so
  they snapshot honestly as role `worker` / model null. When the live node-launcher feeds per-pane
  model/role, `paneMeta` sources it — the fold already carries the fields.
- U58 (live flow workers), U63/U64, U65 (conductor selection literals), U66 (approval-queue feed), U67
  (live STT→bridge→conductor-write), and OP-8 voice-OUT/TTS (owed-by-operator-decision) remain open;
  the layout snapshot's per-pane model/role is populated the same way the picker/spawn feeds land.
- Next sub-step `.gate`: with all seven 15E sub-steps landed, `gate/phase-15e` closes with the
  MANDATORY independent gate-validator (high-stakes), then FINAL_LIVE_REPORT.md + `product/live`.

**Work commit:** `66fe2bf` · **Evidence/register commit:** this commit (carries the work hash).
