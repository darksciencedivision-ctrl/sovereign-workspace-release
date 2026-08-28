# PHASE 14A SUB-STEP EVIDENCE — UI Recovery After Restart (`phase-14a.recovery`)
Autonomous loop iteration 19 · 2026-07-18Z · sub-step `phase-14a.recovery` · **final 14A sub-step**
(this is the last of the five 14A sub-steps; on landing it the high-stakes `gate/phase-14a` closes
with mandatory gate-validator — see `PHASE14A_EVIDENCE_REPORT.md`).

## Objective
Deliver the recovery leg of Phase 14A (directive §9 track 14A: **"UI recovery after process
restart"**): the shell must survive a control-plane / gateway / process restart — fail closed in
the gap (no naked sessions), tear sessions down on channel loss, re-admit ONLY on a re-verified
channel, and reconstruct pane/session state — with the whole lifecycle observable (invariant 27).

## Source state
Tags through `gate/phase-13` + `build/complete` + `audit/completion-20260718`; 14A sub-steps `.ipc`
(`7eb96e3`/`516a480`), `.shell` (`16448bb`/`ac72171`), `.tiling` (`58dade9`/`186d1e9`), `.inspector`
(`9830768`/`415c64e`) committed; `next_step: phase-14a.recovery`; **no `gate/phase-14a`** at the
start. State/tags agree — reconciled per Loop Protocol §3.1. Freeze set untouched; `docs/canonical/`
not modified.

## Design — recovery as an explicit, pure state machine (the crux)
Before this sub-step, supervision was a single latched boolean inside `IpcSupervisor`. Recovery
requires an observable, testable lifecycle, so it is lifted into a pure machine and a pure fold:

- **`terminal/recovery/recovery-machine.js` (NEW) — `RecoveryMachine`.** Deterministic, fail-closed,
  holds no clock and no socket (fed one probe outcome at a time). States: `INIT` (never supervised),
  `SUPERVISED` (admission OPEN), `DEGRADED` (loss edge — sessions torn down, admission SHUT),
  `RECOVERING` (still down, re-probing, admission SHUT). `admissionOpen === (state==="SUPERVISED")`
  is the SINGLE gate admission consults. A monotonic **`epoch`** bumps on every (re)establish so the
  UI/inspector can tell a freshly re-established channel from the original. Every transition is
  appended to an immutable, copy-on-read history with the injected timestamp, and mirrored to
  `onTransition`. The loss edge (`SUPERVISED→DEGRADED`) is the ONLY one flagged `teardown`.
- **`terminal/recovery/reconstruct.js` (NEW) — `reconstructSessions` / `interruptedSessions`.** Pure
  fold of the append-only `SessionRegistry` event log (invariant 12) → last-known session state.
  **Load-bearing rule:** a session still alive (`SPAWNING`/`RUNNING`) at the cut is marked
  `interrupted` / `needsRelaunch:true` and **`recoverable` is hardcoded `false`** — fail-closed,
  invariant 2, a naked session is NEVER auto-respawned; the operator relaunches it through supervised
  admission. Terminal states (EXITED/KILLED/REFUSED) reconstruct as history only.

## Wiring
- **`apps/desktop/supervisor.js` (CHANGED).** `IpcSupervisor` now DRIVES the `RecoveryMachine`: each
  `_probe()` feeds the machine `ready`; the machine owns the lost/restored edges and fires
  `onSupervisionLost` (→ `manager.killAll()`, existing) and the **new `onSupervisionRestored`** (the
  false→true edge, re-admits + re-pushes the UI). `ready`/`admit()` read `machine.admissionOpen`;
  `supervisionState()` exposes the lifecycle. Backward compatible — the 4 pre-existing supervisor
  tests pass unchanged.
- **`apps/desktop/recovery-store.js` (NEW).** Durable persistence of the event log (fs injected) so a
  full SHELL PROCESS restart can fold it. Reads fail closed to `[]` on missing/corrupt; writes are
  **atomic** (temp file + rename) so a mid-write crash can never leave a truncated log that hides an
  interrupted session (invariant 27). In-repo path under `apps/desktop/.recovery/` (gitignored).
- **`apps/desktop/main.js` (CHANGED).** Wires `onSupervisionRestored → pushState + emitLayoutNow`;
  persists the event log on every lifecycle event; at boot folds the persisted log and **reports**
  interrupted sessions (`shell:recovery` + log) — NEVER auto-spawns; adds `recovery:
  supervisor.supervisionState()` to `shell:state`.
- **`apps/desktop/preload.js` + `renderer/{renderer.js,index.html}` (CHANGED).** A `DEGRADED` /
  `RECOVERING` banner + supervision card driven by `shell:state.recovery`; a one-shot interrupted-
  session notice ("relaunch under supervision — no naked re-spawn") from `shell:recovery`. All
  model-derived strings pass through `esc()`; CSP `script-src 'self'`; renderer stays sandboxed.
- **`control_plane/ipc/gateway.py` + `run_gateway.py` (CHANGED).** `IpcCredentialStore.install`
  binds a caller-supplied `(token,key)→identity` (no authorization added — I-M2 intact); `run_gateway`
  honors `IPC_FIXED_TOKEN`/`IPC_FIXED_KEY` **only** behind the explicit opt-in `IPC_ALLOW_FIXED_CRED=1`
  (fail-closed: the recovery-model shim can never activate silently in a real deployment — absent the
  opt-in a fresh random credential is always minted). This models a control plane whose credential
  store survives a restart, so the reconnecting shell re-verifies against the same per-node HMAC key.

## Exit criteria (directive §9 "UI recovery after process restart") — met, mapped to code + test
- **Re-establish the governed channel after a restart:** proven LIVE — `apps/desktop/test/
  recovery-live.test.js` starts a real `py -3.12` gateway (SUPERVISED), **kills** it (DEGRADED),
  **restarts** it on the same port+credential (RECOVERING → SUPERVISED restored, epoch 2) and re-admits
  a session — all via the real Node `IpcClient`. Not a mock, not skipped when `py -3.12` is present.
- **Fail closed in the gap (no naked sessions):** `admissionOpen` is true ONLY in `SUPERVISED`
  (`recovery-machine.js`); `admit()` reads it (`supervisor.js`); asserted live (admission shut after
  the kill) + in the pure machine.
- **Tear sessions down on loss:** loss edge flags `teardown`, `onSupervisionLost → killAll`; the live
  test asserts the running session's PTY is killed in the gap.
- **Re-admit ONLY on a re-verified channel:** `restored` fires on `DEGRADED/RECOVERING→SUPERVISED`
  driven by a real `op:"health"` `ok===true` probe — not optimistically; re-admission works only then.
- **Reconstruct pane/session state:** `reconstruct.js` folds the append-only log; round-trip test
  proves cross-restart reconstruction through serialization; interrupted sessions surfaced for
  supervised relaunch, never respawned.
- **Observable (invariant 27):** lifecycle pushed to the renderer (banner + card), transitions logged.

## Independent review
- **gate-validator: PASS_WITH_RESERVATIONS** (isolated context; all commands re-run). Adversarially
  verified every load-bearing claim: no admission path while down; session cannot survive the loss
  edge (live `fakePty.killed===true`); `recoverable` structurally unreachable as true; restore only on
  a real re-verify; the live test is genuinely load-bearing (real processes, counterfactuals fail);
  `install()` adds no authorization; renderer sandboxed; no GUI-substitution overclaim. Observed **130
  JS pass / 0 skipped** (live ran), **366 pytest** (the +2 gateway tests; see below now 367 with the
  opt-in test), 4 backward-compat supervisor tests pass, all `node --check` clean. Reservations, all
  pre-existing/documented: **R1** U9 re-verify with a real console TUI in a pane is a listed 14A
  criterion, deferred (needs OpenCode/14C + a live window; tracked HARDENING_BACKLOG U9,
  UNRESOLVED_ISSUE_REGISTER) — precludes a clean PASS, hence PASS_WITH_RESERVATIONS; **R2** OS-level
  pid→JobObject containment not wired from the Node shell (U25/U26, disclosed in `supervisor.js`);
  **R3** GUI is operator-run substituted, not observed (directive §6); **R4** count drift (366 vs the
  brief's 364 — the two ADDED gateway tests; benign).
- **spec-auditor: CLEAN with 2 MINOR (both FIXED this iteration).** All six load-bearing invariants
  hold: I-2 (no auto-respawn — `recoverable` hardcoded false, launch only via `SessionManager.spawn`
  admission), I-16/fail-closed (single admission gate; teardown on loss; re-admit only on re-verify;
  corrupt log → []), I-12 (append-only, copy-on-read, `structuredClone`), I-27 (lifecycle pushed +
  logged), I-7/I-M2 (`install` adds no authz; grep confirms no role checks in the gateway), I-20
  (loopback; fixed-cred still HMAC-verified). §2.2 judged honest (fixed creds are ephemeral loopback
  test credentials, never real secrets, never off-loopback). Determinism confirmed. **MINOR-1** (non-
  atomic persist could hide an interrupted-session report) → **FIXED**: temp-write + atomic rename,
  new test. **MINOR-2** (env-credential path in product code) → **FIXED**: gated behind explicit
  `IPC_ALLOW_FIXED_CRED=1` opt-in, new fail-closed test proving the fixed cred is ignored without it.
  No drift / certainty-inflation; disclosed limitations understate rather than overstate.

## Substitutions (loop directive §6)
- **GUI verification deferred, not faked.** The Electron window / recovery banner is an operator-run
  metric (`apps/desktop/RUN_ON_WINDOWS.md`). The governance-bearing recovery logic — state machine,
  reconstruction, supervision/admission, credential re-verification — is pure and headlessly tested,
  including a **live gateway restart** proven through the real Node `IpcClient` (the strongest
  available substitution). No rendered behaviour is claimed as observed.
- **Credential-store persistence modeled, honestly.** A real persistent credential store would
  survive a restart; here `IPC_ALLOW_FIXED_CRED`-gated install models that so the reconnection path is
  testable, still fully HMAC-verified and loopback-only. Recorded, not presented as a shipped store.

## Deviations / carried
- **ruff unavailable** (pip out of scope, §2.7); JS `node --check` clean + `node --test`.
- **Carried:** U9 real-TUI re-verify (R1, needs 14C/live window); U25 IPC→MCP per-node credential
  broker + U26 OS pid→JobObject containment from the Node shell (R2); durable-log rotation/retention
  (the store keeps a single latest snapshot — sufficient for reconstruction, not an audit archive).

## Test totals
- JS: **131 passed / 0 failed / 0 skipped** (`node --test terminal/test/*.test.js
  apps/desktop/test/*.test.js`) — new: recovery-machine 12, reconstruct 8, recovery-store 5, live
  recovery 1 (real gateway restart, ran not skipped).
- Python: **367 passed** (`py -3.12 -m pytest tests/ -q`) — new: 3 in `test_ipc_gateway.py`
  (install persists a fixed credential; restart re-issues the same credential; fixed cred ignored
  without the opt-in).

## Sub-step verdict
**PASS (sub-step).** UI recovery after control-plane/process restart: a pure, fail-closed recovery
state machine (admission open only when supervised; teardown on loss; re-admit only on a re-verified
channel; monotonic epoch; append-only history), pure session reconstruction that never auto-respawns
a naked session (invariant 2), durable atomic-persisted event log, and an observable recovery banner
— proven end-to-end by a LIVE gateway kill+restart through the real IPC client. gate-validator
PASS_WITH_RESERVATIONS, spec-auditor CLEAN (both MINOR fixed + pinned). This is the final 14A
sub-step; `gate/phase-14a` closes this iteration (see `PHASE14A_EVIDENCE_REPORT.md`).
