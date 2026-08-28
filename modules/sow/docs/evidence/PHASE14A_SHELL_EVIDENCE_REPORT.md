# PHASE 14A SUB-STEP EVIDENCE — Product Shell + Terminal Canvas (`phase-14a.shell`)
Autonomous loop iteration 16 · 2026-07-18Z · sub-step `phase-14a.shell` · **no gate tag yet**
(the high-stakes `gate/phase-14a` closes only when ALL 14A sub-steps land, with mandatory
gate-validator confirmation; this report covers the second sub-step and carries no tag).

## Objective
Deliver the product desktop-shell leg of Phase 14A (directive §9 track 14A): the real
Electron/xterm.js/node-pty workspace scaffold in `apps/desktop/` + `terminal/` — terminal
canvas, pane create/destroy + maximize/restore/minimize/pin, status cards, ConPTY sessions
**supervised by the real Node Runtime (no naked sessions)**, and a Node IPC client mirroring
`control_plane/ipc/client.py` — riding the authenticated IPC (D-IPC-01) the prior sub-step
built. The tiling GEOMETRY (Plan §10.2), the routing/artifact inspector, and UI recovery are
the remaining sub-steps (`.tiling` → `.inspector` → `.recovery`).

## Source state
Tags through `gate/phase-13` + `build/complete` + `audit/completion-20260718`; `next_step:
phase-14a.shell`; **no `gate/phase-14a`**. State/tags agree (reconciled: prior sub-step
`.ipc` is committed at `7eb96e3`/`516a480`, loop-state at `f4fa4ae`; no gate tag was or is
claimed). Freeze set untouched; `docs/canonical/` not modified.

## What this sub-step is NOT (honest scope)
- **Not the throwaway spike.** `tools/spike_compositor` stays a throwaway rig (Plan §16). This
  is product code that reuses the spike's *proven* patterns (session survival, ring-buffer
  scrollback, near-square layout) but adds the governance the spike deliberately omitted
  (node binding, supervised admission, the signed IPC contract).
- **Not a verified window.** Per loop directive §6, the Electron window cannot be rendered or
  observed in this headless build session; it is an **operator-run metric** exactly like the
  Phase-1 spike (`apps/desktop/RUN_ON_WINDOWS.md`). Every governance-bearing layer beneath it
  is covered by headless tests. No rendered behaviour is claimed as observed.
- **Not the tiling geometry.** Pane geometry (Plan §10.2 near-square grid + pinned
  double-cells) is the sibling `.tiling` sub-step; the renderer here uses a placeholder
  auto-fit grid and the model exposes `tilingMembers()` for `.tiling` to consume.

## Files (work commit)
Product terminal core (`terminal/`, headlessly tested):
- `terminal/session/ring-buffer.js` — bounded scrollback, byte-exact replay on reattach.
- `terminal/session/session-registry.js` — session lifecycle state machine
  (SPAWNING→RUNNING→EXITED|KILLED, and SPAWNING→REFUSED for denied admission), node binding
  required (no naked session), **append-only immutable event log** (deep-cloned detail).
- `terminal/conpty/session-manager.js` — PTY↔registry↔supervisor wiring; **REFUSES + kills any
  session the supervisor does not admit, and any session with no node binding** (fail-closed);
  injected `ptyFactory` (node-pty in production, fake in tests).
- `terminal/compositor/pane-model.js` — deterministic pane/window state: create/destroy,
  maximize/restore/minimize/pin, and single always-valid focus (input routing — "input to the
  wrong pane" was a Phase-1 kill criterion). Geometry-free.

Desktop shell (`apps/desktop/`, operator-run window + headlessly-tested IPC/supervision):
- `apps/desktop/ipc/envelope.js` + `ipc/client.js` — Node mirror of `control_plane/ipc/
  {envelope,client}.py`: signed `envelope@1.0`, constant-time integrity verify, fail-closed
  (`IpcDisconnected`/`IpcIntegrityError`); loopback enforced in the transport itself.
- `apps/desktop/supervisor.js` — `IpcSupervisor`: admission gated on holding a verified,
  authenticated control-plane channel (a `health` heartbeat); tears every session down on
  channel loss (fail-closed).
- `apps/desktop/main.js` — Electron main: resolves/spawns the real Python gateway, connects the
  client, builds the `SessionManager` (node-pty) + `PaneModel`, routes renderer intents; kills
  all PTYs on quit (no orphans). Renderer sandboxed (`contextIsolation`, `nodeIntegration:false`,
  `sandbox:true`).
- `apps/desktop/preload.js` — contextBridge exposing intents only (TB-2: the renderer has no
  Node access; model output is never routed back as a command).
- `apps/desktop/renderer/{index.html,renderer.js}` — xterm.js canvas, per-pane controls,
  status cards (supervision/sessions/focus), minimized tray. Thin view over pushed state.
- `apps/desktop/package.json` (deps: electron, @xterm/xterm, @xterm/addon-fit, node-pty) +
  `RUN_ON_WINDOWS.md` (one-command operator run + what to confirm visually).
- Control-plane fix: `control_plane/ipc/gateway.py` — `EchoControlSurface` now answers
  `op:"health"`, making `health` a universal liveness op every surface satisfies.
- Tests (`node --test`): `terminal/test/{ring-buffer,session-registry,session-manager,
  pane-model}.test.js` (32) + `apps/desktop/test/{envelope,ipc-client,supervisor}.test.js` (15).

## Exit criteria for the sub-step — met, mapped to code + test
- **Product Electron/xterm/node-pty scaffold in `apps/desktop` + `terminal/`:** all files
  present; `node --check` parses every main-process/renderer file; window deferred as an
  operator metric (RUN_ON_WINDOWS.md), not overclaimed.
- **Pane create/destroy + maximize/restore/minimize/pin + focus routing:** `pane-model.js` +
  10 tests — a new pane takes focus; destroying the focused pane deterministically re-focuses
  the previously focused survivor; focus never rests on a minimized pane; maximize shows only
  the maximized pane; snapshots are copies (no external mutation).
- **ConPTY sessions supervised by the real Node Runtime — no naked sessions:**
  `session-manager.js` refuses a session with no node binding, and on a non-`supervised:true`
  verdict (or a throwing supervisor) **kills the PTY and marks it REFUSED** (session-manager
  tests, proven load-bearing by the validator's mutation pass). `session-registry.js`
  independently refuses `register` without `nodeId` (a second fail-closed layer).
- **Admission is a real, live gate (not a fake):** `supervisor.test.js` wires the REAL
  `IpcSupervisor` to the REAL `run_gateway` (default echo surface — the exact config main.js
  spawns): the `health` heartbeat reaches READY → `admit()` returns `supervised:true` → a
  `SessionManager` spawns a RUNNING session; killing the gateway flips ready→false, fires
  `onSupervisionLost` (teardown), and `admit()` returns `supervised:false`.
- **Node IPC client mirrors `client.py` (D-IPC-01 contract):** `ipc-client.test.js` spawns a
  genuinely separate `py -3.12 -m control_plane.ipc.run_gateway`; a Node-signed `envelope@1.0`
  is accepted and the gateway's signed reply verifies under the same per-node key
  (cross-language byte-identity). Fail-closed negatives: bad credential, wrong integrity key,
  and spoofed `from_node` each drop the connection (`IpcDisconnected`).
- **Deterministic + observable:** lifecycle/admission logic is deterministic and injected-clock;
  the shell surfaces supervision/session/focus state (invariant 27).

## Blocking defect found in review, then FIXED this iteration (§3.4)
The first gate-validator pass returned **FAIL** (corroborated by spec-auditor MAJOR F1): the
supervisor probed `op:"health"`, but the gateway `main.js` spawns by default
(`EchoControlSurface`) only answered `op:"ping"`, so admission latched permanently DENIED —
**no terminal could ever spawn in the documented one-command run** (fail-closed, so safe, but
the headline deliverable was unreachable and untested end-to-end). Fixed by making `health` a
universal liveness op (`EchoControlSurface` now answers it) and adding `supervisor.test.js`,
which drives the REAL supervisor↔gateway path — the exact integration the suite previously did
not cover. Re-validated below.

## Independent review
- **gate-validator: FAIL → PASS_WITH_RESERVATIONS on re-run (both passes reproduced with real
  commands, isolated context).** First pass: **FAIL** — the readiness/op mismatch above plus no
  headless supervisor↔gateway coverage. After the fix, the validator independently reproduced:
  `echo health -> {ok: True, ...}` (was `ok: False, unsupported op`); the 4 new `supervisor.test.js`
  tests executing (not skipped); 47 JS / 364 Python green; and a **load-bearing mutation proof**
  — deleting only the echo `health` branch makes the READY path fail, and it restored
  `gateway.py` byte-identical afterward. Reservations (non-blocking): R1 GUI unobserved by design
  (now reachable-to-READY, not guaranteed-DENIED); R2 OS containment deferred (U26); R3 integrity
  covers `payload` only (carried from `.ipc`).
- **spec-auditor: 1 MAJOR + 4 MINOR, all addressed.** MAJOR F1 (unreachable READY) → FIXED
  (universal `health` + live test). MINOR: F2 (shell self-minted `operator` role) → FIXED
  (bootstrap role is now `shell`); F3 (canonicalization byte-identity overclaim for floats/
  astral keys) → claim softened to what the round-trip test proves, with the fail-closed edge
  documented; F4 (append-only log leaked mutable nested `detail`) → FIXED (deep-clone on
  append); F5 (client did not self-enforce loopback) → FIXED (non-loopback host refused in the
  transport). Confirmations (CLEAN): invariant 2 mechanically enforced; I-7/I-M2 (no authz in
  the transport); TB-2/29 (renderer sandboxed, output never parsed as command); constant-time
  compare; invariants 12/13 (append-only, illegal transitions raise). Explicit `sandbox:true`
  added per the auditor nit.

## Substitutions (loop directive §6)
- **GUI verification deferred, not faked.** The Electron window is an operator-run metric
  (`apps/desktop/RUN_ON_WINDOWS.md`) exactly like the Phase-1 spike. All governance-bearing
  logic under it is headlessly tested (47 JS tests). No rendered behaviour is claimed as
  observed; the one-command run and the visual checklist are for the operator's host run.

## Deviations / carried
- **ruff unavailable** (pip out of scope, §2.7); JS has no repo linter — code is `node --check`
  clean and exercised by `node --test`.
- **U26 (new):** OS-level containment — assigning the PTY pid to the Node Runtime's Windows Job
  Object (`node_runtime/supervisor/containment.py`) — is NOT yet wired from the Node shell
  process; it needs the IPC surface to carry a write op, which is blocked on the U25 per-node
  credential broker. Today the shell enforces the GOVERNANCE gate (authenticated channel
  required for admission, lifecycle reported, kill-all on supervision loss); kernel-level
  kill-on-close containment remains the Node Runtime's (exercised in Phase 3/10). Recorded, not
  hidden (`apps/desktop/supervisor.js`).

## Test totals
- JS: **47 passed / 0 failed** (`node --test terminal/test/*.test.js apps/desktop/test/*.test.js`);
  the 15 apps/desktop tests drive real `py -3.12` gateway subprocesses (not skipped).
- Python: **364 passed** (`py -3.12 -m pytest tests/ -q`) — the `gateway.py` health addition
  broke nothing.

## Sub-step verdict
**PASS (sub-step)** — gate-validator PASS_WITH_RESERVATIONS on re-run (recorded above). Product shell
scaffold with supervised, no-naked-session ConPTY lifecycle, deterministic pane/window state
with safe input routing, and a cross-language-proven Node IPC client on the D-IPC-01 channel;
the blocking readiness defect found in review is fixed and now covered by a live
supervisor↔gateway test. `gate/phase-14a` is **NOT** tagged — the high-stakes gate (mandatory
gate-validator) awaits `.tiling`, `.inspector`, and `.recovery`.

## Commits
Work `16448bb` → this evidence/register commit (carries the work hash) → loop-state commit.
**No gate tag** (sub-step; `gate/phase-14a` awaits `.tiling`, `.inspector`, `.recovery`).

## Next
`phase-14a.tiling` — the Plan §10.2 near-square tiling geometry (pinned/attention double-cells)
as headless JS logic tests consuming `PaneModel.tilingMembers()`, mirroring the spike's
`layout.test.js`. Then `.inspector`, `.recovery`; `gate/phase-14a` closes when all land.
