# Phase 16D — Status-bar + approvals live feeds — EVIDENCE REPORT

**Directive:** §15 track 16D (register OP-10). **Loop mode:** autonomous
(AUTONOMOUS_BUILD_DIRECTIVE.md). **Decided by:** operator-delegation (ruling 2026-07-16);
basis OP-10. **Gate class:** 16D is NOT a directive-flagged high-stakes gate (only 16A/16F
are); the whole-track `gate/phase-16d` tag + a final gate-validator close only when all three
sub-steps land — same convention as the 14A / 15E / 16C sub-steps.

Phase 16D is a large phase with three independently-self-checked deliverables, so it is
DECOMPOSED (directive §3.2, one named sub-step per iteration):

| Sub-step | Content | Status |
|---|---|---|
| **`.statusbar`** | governor n/2 real count into the status bar (fixes the operator's "concurrency count unavailable") | **DONE** |
| **`.approvals`** | approval-queue drawer fed over read-only IPC (closes U66) | **DONE** |
| **`.recovery`** | recovery snapshot carries worker-pane chrome (closes U68) | **DONE (this section closes the track)** |

All three sub-steps have landed, so `gate/phase-16d` is applied on the `.recovery` evidence
commit (see the whole-track close section at the end).

---

## Sub-step `.statusbar` — DONE

### Exit criterion (directive §15 track 16D, first bullet)
> Governor n/2 real count into the status bar (fixes "concurrency count unavailable").

**Operator finding (OP-10):** the shipped shell's status bar showed
`⚠ concurrency count unavailable (fail-closed)`.

### Root cause
The always-visible status bar reads the subscription-concurrency n/allowance count over the
`subscription_status` IPC op (built + tested at 15A: `apps/desktop/statusbar/source.js`,
`apps/desktop/test/statusbar-source.test.js`, proven against a REAL seeded `SubscriptionGovernor`).
But the gateway the running shell actually spawns is the diagnostic `EchoControlSurface`
(`control_plane/ipc/run_gateway.py`, no `--mcp-port`), which does **not** expose that op — so the
read fails and the bar degrades, honestly but uselessly, to the em-dash unknown. The IPC read path
is correct; it had no governor-backed surface to talk to in the shipped shell.

### Fix (the same §6 substitution pattern the 16B picker + 16C conductor feeds use)
`statusbar:fetch` now SOURCES the count from the REAL `SubscriptionGovernor` via a **bounded
one-shot `py -3.12` read-source** — NOT the WS-IPC channel:

- **`tools/live/emit_subscription_status.py`** `--emit-subscription-status` builds a real
  `SubscriptionGovernor`, registers one subscription per authorized provider at the authorized
  allowance read from the enforced `LiveAuthorization` (`config/live_operation.json`, OP-6 scope),
  and prints its `status()` as ONE JSON line (`subscription_status_feed@1.0`).
- **`apps/desktop/statusbar/governor-source.js`** invokes it (injectable `spawn` for tests), parses
  the one line, and folds `feed.status` through the SAME pure view model
  (`terminal/statusbar/statusbar-model`) the tested IPC path uses.
- **`apps/desktop/main.js`** `statusbar:fetch` → `fetchStatusBarModelFromGovernor({cwd})`. The dead
  dedicated IPC status channel (`statusClient`) and its now-unused imports were removed; the IPC
  surface (`SubscriptionStatusControlSurface`) + `statusbar/source.js` + its test are RETAINED as the
  documented design endpoint for a live governor-backed gateway at 16F.

**Why the emitter, not the IPC surface, this unit (§6 substitution — recorded):** swapping the
shell's gateway surface to `SubscriptionStatusControlSurface` would DISPLACE the `EchoControlSurface`
the supervisor's `health` / `session_event` liveness path already rides — a first-launch regression
class D-P16-0 explicitly warns against. The isolated, proven read-source touches zero existing
wiring. Identical rationale to the 16B picker and 16C `.selection`/`.spawn`/`.dispatch` feeds.

### Honesty (invariant 3; §6; §10.4)
- `allowance` is the operator-authorized OP-6 ceiling read from the enforced `LiveAuthorization`
  (governor-capped at 2; a config may narrow, never widen). Two independent OP-6 caps hold
  (`LiveAuthorization._validate_terminals`, `SubscriptionGovernor.MAX_ALLOWANCE`).
- `in_use` is the governor's `active` count. The governor is built FRESH per emit and is not wired to
  a live-session tracker, so `in_use` is structurally **0** in this build — a truthful, honest zero
  (the shell drives no live frontier session: mock-first §2.4, live drive operator-run/16F). It only
  ever UNDERstates concurrency (fail-safe — never mints capacity or authority).
- **Fail-closed:** a DENIED authorization (no config, a fresh clone) or a malformed config ⇒
  `status:null` ⇒ the JS fold renders the em-dash `—/2` unknown with the reason attached, **never a
  fabricated 0/2**.
- **Owed to 16F, recorded:** DYNAMIC per-session tracking (`in_use` rising/falling against a shared,
  long-lived governor as the shell drives live spawns) — carried in the feed as
  `live_session_tracking.owed:true, issue:"16F"`, in the self-check receipt, and here.
- **No live model call, no credential, no network** (§2.2/§2.4): the emitter only reads the
  `LiveAuthorization` gate + builds an in-memory governor (guarded by
  `test_no_credential_no_network_pure_record`).

### Self-check (D-P16-0 binding, per-track) — REAL runtime evidence
`apps/desktop/selfcheck/statusbar-selfcheck.js` (`node selfcheck/run.js statusbar`) drives the REAL
renderer inside the packaged Electron runtime: reads the status-bar model through the same preload
bridge the renderer uses (`window.sovereign.statusBar()`), asserts it was SOURCED from the emitter
(`source:"emitter"` — the load-bearing proof, not a literal), `readable:true`, both live providers
rendered as real n/allowance, no fabricated count, and the RENDERED `#statusbar` DOM shows the chips
with NO "concurrency count unavailable" warn. Receipt:
`docs/evidence/receipts/PHASE16D_STATUSBAR_SELFCHECK.json` — `ok:true`, Electron 31.7.7 / Node
20.18.0 / win32-x64; rendered excerpt: `subscriptions … claude 0/2 … codex 0/2`.

**Load-bearing (empirically falsified by the gate-validator):** with a broken interpreter the real
`fetchStatusBarModelFromGovernor` path yields `readable:false` (fail-closed unknown); with the real
one it yields `readable:true` claude 0/2 · codex 0/2 — the exact delta the fix supplies. A reverted
wiring (IPC-only against the echo gateway) would yield `readable:false` in the running shell ⇒ the
self-check FAILS.

### Tests — ALL FRESH FOREGROUND (D-LOOP-2)
| Suite | Count | Δ |
|---|---|---|
| `py -3.12 -m pytest tests/ -q` | **1055 passed** | +12 (`test_emit_subscription_status.py`) |
| apps/desktop `node --test test/*.test.js` | **115 passed** | +14 (`statusbar-governor-source.test.js`) |
| terminal `node --test "terminal/**/*.test.js"` | **160 passed** | 0 |
| **Total** | **1330** | +26 (was 1304) |

### Independent confirmation
- **gate-validator (isolated): PASS** — independently re-ran the emitter (one JSON line, all fields),
  the Python + JS suites (1055 / 115 / 160), DELETED + regenerated the self-check receipt
  (`ok:true`, provably its own run), empirically FALSIFIED the load-bearing claim (broken interpreter
  ⇒ readable:false), confirmed no live model call / no credential / fail-closed honesty, D-LOOP-1
  clean teardown (no orphan), frozen canonical 4-hash set intact
  (6D3FD03B/8C9B7240/668089B5/CC414372), `mcp_server/` untouched. **No reservations.** Noted the
  pre-existing `pane:resize` U73 TypeError is out of `.statusbar` scope (not in this unit's diff).
- **spec-auditor: CLEAN** — no invariant violation / no prohibited drift (traced I-1/3/7/19-22/I-X3,
  §2.2/§2.4, determinism, no float, D-LOOP-1, §6 substitution recorded). 2 documentation-only NITs —
  renderer status-bar comment credited the old test path (→ **FIXED**, now cites
  `statusbar-governor-source.test.js` + the self-check); emitter `in_use` docstring lead clause read
  stronger than the fresh-per-emit mechanism (→ **FIXED**, tightened). No code change from either NIT;
  counts above re-taken and the self-check receipt regenerated after the fixes.

### Substitutions (directive §6, explicitly listed)
1. **Bounded `py -3.12` read-source emitter instead of the authenticated `SubscriptionStatusControlSurface`
   over WS-IPC.** Rationale: displacing the shell's echo gateway would break the supervisor
   liveness path (D-P16-0 regression risk). The IPC surface remains the design endpoint for a
   governor-backed gateway at 16F. Identical to the gated 16B/16C precedents.
2. **Rendered status bar is an operator-run surface** (like the window itself) — the DATA path is
   proven headlessly + in-Electron; the pixel is operator-verified via the self-check receipt.

### Frozen-canonical / MCP / prohibitions
Frozen canonical 4-hash set intact (6D3FD03B/8C9B7240/668089B5/CC414372); `docs/canonical/` not
modified; `mcp_server/` untouched (invariant 7 — no authorization logic added). No push, no
credentials, no network beyond the local emitter subprocess, nothing outside the repo root.
`config/live_operation.json` (gitignored) + `apps/desktop/package-lock.json` (untracked) deliberately
NOT swept.

### What remains owed
- Dynamic per-session n/2 tracking against a shared governor as the shell drives live spawns →
  **16F** (recorded `live_session_tracking.owed`).
- The two remaining 16D sub-steps: `.approvals` (U66) and `.recovery` (U68).
- Pre-existing **U73** (`pane:resize` null-manager TypeError against the sessionless conductor
  placeholder) — out of scope, non-blocking.

### Two-commit convention
- Work commit: emitter + governor-source + main.js/renderer.js rewire + self-check + tests + run.js.
- Evidence commit (this report + register rows + receipt) carries the work hash. No gate tag
  (sub-step).

---

## Sub-step `.approvals` — DONE (closes U66 read + governed-resolve authority)

### Exit criterion (directive §15 track 16D, second bullet)
"approval-queue drawer fed over the read-only IPC (closes U66)". Phase 15E shipped the pure render
model (`terminal/compositor/approval-drawer.js`) and the drawer chrome, but `main.js`'s
`approvalSnapshot()` returned a **hardcoded EMPTY drawer** — the live in-process
`ApprovalQueue.drawer_model()` was never delivered (U66). `.approvals` sources the REAL governed
drawer and routes the operator's Approve/Reject back to the governed authority.

### Fix (the same §6 read-source substitution the 16B/16C/`.statusbar` feeds use)
- **New `control_plane/orchestration/approval_feed.py`** builds a REAL `ApprovalQueue` populated by the
  REAL governed producers — a PLAN item via `LiveGovernedFlow.begin(objective)` + the REAL gate engine
  (`approvable` DERIVED from the `gate@1.0` verdict, invariant 16), a PROTECTED_ACTION and a
  CLARIFICATION via the REAL `CommandBroker` (`mirror_broker_outcome`) — folds `drawer_model()` into
  `approval_drawer_feed@1.0`, and (`route_governed_decision`) rebuilds the SAME deterministic queue to
  resolve a decision through `ApprovalQueue.resolve` (operator-only inv 1; no approve of a
  non-approvable item, inv 16 — no override).
- **Emitters** `tools/live/emit_approval_drawer.py --emit-approval-drawer` and
  `emit_approval_decision.py --emit-approval-decision --item <id> --decision <approve|reject>` print
  ONE JSON line; MOCK-first (no live model call), D-LOOP-1 teardown before emit (`torn_down:true`),
  OS-tempdir only (§2.5).
- **`apps/desktop/approvals/drawer-source.js`** (`sourceApprovalDrawerFeed` + `routeApprovalDecision`)
  is the bounded fail-closed glue; `main.js` `approvals:fetch` now async-sources the real drawer
  (`fetchApprovalDrawerModel`→`buildApprovalDrawer`, `source:"emitter"`) and `approvals:decide` routes
  to the governed authority (`selfAuthorized:false` — the shell forwards, Python decides). The
  hardcoded `approvalSnapshot()` is REMOVED. Startup does a bounded background refresh (never blocks
  first paint); a fault renders the honest empty drawer.

### Honesty (invariant 3; §6; §10.4)
The drawer is REAL but the queue is rebuilt FRESH per emit (not the shared long-lived queue a live
conductor holds). So the decide path proves the resolve AUTHORITY (inv 1/16 enforced in code), but the
downstream SIDE-EFFECT (`apply_protected_decision`/`ObjectiveIntake.approve`) and cross-fetch
PERSISTENCE ride the live conductor's queue and are OWED to **16F** (`live_queue_owed`/`live_effect_owed`
on every feed). The operator log says "RESOLVED (effect owed 16F)", never "applied". The operator
identity is PRESUMED from local shell context (authenticated per-node binding owed to 16F); the
authority re-checks the role regardless (a non-operator is refused — inv 1, defense-in-depth, tested).
No fabricated pending item or resolution on any path.

### Self-check (D-P16-0 binding, per-track) — REAL runtime evidence
`node selfcheck/run.js approvals` drives the REAL renderer inside packaged Electron (31.7.7 / Node
20.18.0 / win32-x64), exit 0, `docs/evidence/receipts/PHASE16D_APPROVALS_SELFCHECK.json` `ok:true`:
`model_sourced_from_emitter:true` (load-bearing — NOT the old empty literal), the three governed kinds
present, `clarification_not_approvable:true`, rendered rows + badge painted, and a governed decide
(approve the clarification) → `decide_governed_refused:true` + `decide_self_authorized_false:true`
(invariant 16 in-runtime). Empirically falsified by the gate-validator (moved the emitter aside ⇒
`ok:false`/exit 1 ⇒ restored byte-identical ⇒ pass).

### Tests — ALL FRESH FOREGROUND (D-LOOP-2)
- `tests/unit/test_approval_feed.py` **+14** (governed 3-kind queue; determinism; drawer fold +
  fail-closed; decide reject→resolved / approve-clarification→inv16 refused / unknown→refused /
  non-operator→inv1 refused; both CLI contracts) → **py-3.12 1069** (was 1055).
- `apps/desktop/test/approvals-drawer-source.test.js` **+19** (fake-spawn parse/timeout/fail-closed
  matrix for both drawer + decision routes; bad-decision never routed; 2 LIVE emitter tests) →
  **apps/desktop 134** (was 115). **terminal 160** unchanged. **Total 1363 green** (was 1330).

### Independent confirmation
- **gate-validator (isolated): PASS_WITH_RESERVATIONS** — independently re-ran both emitters, the
  suites (14 / 19 / 134 / 1069), DELETED+moved the drawer emitter aside to EMPIRICALLY FALSIFY the
  load-bearing self-check (⇒ ok:false/exit 1) then restored byte-identical, confirmed no live call /
  no orphan processes / D-LOOP-1 / the 4 canonical hashes intact / `mcp_server/` untouched. Reservations
  = the honest 16F-owed scope (side-effect + persistence) + the §6 read-source substitution + a sandbox
  `git`-gated changeset-enumeration limitation (worked around via hashes/mtimes) — no FAIL.
- **spec-auditor: CLEAN** — no invariant violation, no prohibited drift (traced inv 1/3/7/16, §2.2/§2.4,
  §6/§10.4, D-LOOP-1, determinism, no TTS). 3 honesty NITs: (1) "APPLIED" log overstated → **FIXED**
  ("RESOLVED (effect owed 16F)"); (2) presumed-operator identity surfaced less loudly → **FIXED**
  (explicit docstring note, owed to 16F); (3) `torn_down:true` is a literal set after teardown in the
  `finally` — structurally accurate, accepted (sibling `.dispatch`/`.statusbar` precedent).

### Substitutions (directive §6, explicitly listed)
1. **Bounded `py -3.12` read-source emitter instead of an authenticated IPC surface** — swapping the
   shell's echo gateway would break the supervisor liveness path (D-P16-0 regression risk). Identical
   to `.statusbar`/16B/16C.
2. **Fresh-per-emit `ApprovalQueue`** (not a shared long-lived queue) — the decide AUTHORITY is real;
   persistence + downstream side-effects are the operator-run 16F assembled run.
3. **Rendered drawer is an operator-run surface** — the DATA path is proven headlessly + in-Electron;
   the pixel is operator-verified via the self-check receipt.

### Frozen-canonical / MCP / prohibitions
Frozen canonical 4-hash set intact (6D3FD03B/8C9B7240/668089B5/CC414372); `docs/canonical/` not
modified; `mcp_server/` untouched (invariant 7 — the approval authority is `control_plane/orchestration/`,
not MCP). No push, no credentials, no network beyond the local emitter subprocess, nothing outside the
repo root. `config/live_operation.json` (gitignored) + `apps/desktop/package-lock.json` (untracked)
deliberately NOT swept.

### What remains owed
- The shared long-lived queue where a resolve PERSISTS and its downstream side-effect FIRES
  (broker execute / `ObjectiveIntake.approve`) + authenticated per-node operator identity → **16F**
  (`live_queue_owed`/`live_effect_owed`).
- The last 16D sub-step: `.recovery` (recovery snapshot carries worker-pane chrome, U68).
- Pre-existing **U73** (`pane:resize` null-manager TypeError) — out of scope, non-blocking.

### Two-commit convention (`.approvals`)
- Work commit: `approval_feed.py` + two emitters + `drawer-source.js` + `main.js`/`run.js` rewire +
  self-check + tests.
- Evidence commit (this section + register rows + receipt) carries the work hash. NO gate tag
  (sub-step; `gate/phase-16d` closes only when `.recovery` also lands).

---

## Sub-step `.recovery` — DONE (closes U68); this section closes `gate/phase-16d`

### Exit criterion (AUTONOMOUS_BUILD_DIRECTIVE.md §15 track 16D, third bullet)
> "recovery snapshot carries worker-pane chrome (closes U68)".

I.e. after a full shell-process restart, a restored WORKER pane must repaint its EXACT model
badge from the persisted/reconstructed chrome instead of coming back blank — WITHOUT
auto-attaching or admitting a live session (invariant 2) and WITHOUT fabricating a model when a
pane has no recorded selection (invariant 3).

### Root cause (U68, opened at `phase-15e.recovery`)
Conductor-first LAYOUT recovery (`terminal/recovery/layout-reconstruct.js` — `buildLayoutSnapshot`
/ `reconstructLayout`, wired in `apps/desktop/main.js`) already rebuilt the pinned CONDUCTOR pane 1
and the worker-pane order/disposition across a restart, fail-closed. But the per-pane worker fields
came from `paneMeta(id)`, which carried governed chrome ONLY for the conductor pane — so a worker
pane snapshotted honestly as role `worker` / model `null` and came back with a BLANK badge after a
restart (never a fabricated model — but the operator's selected model badge was lost).

### Fix (record/read half — the live governed worker SPAWN stays owed to 16F/U70)
- **`terminal/recovery/layout-reconstruct.js`** gains `_chromeSnapshot(c)` — a DETERMINISTIC field
  WHITELIST (provider / adapter / locality / model_label / model_slug / model_verified / role /
  mode / node_state / governed / subscription{allowance,in_use} / residency). It NEVER blind-copies
  the caller's object (a stray field cannot survive a round-trip), fail-closes `mode` to
  `autonomous` and `governed` to `false`, and returns `null` for absent/non-object chrome.
  `buildLayoutSnapshot` captures `_chromeSnapshot(m.chrome)` per pane; `reconstructLayout`
  RE-sanitizes the disk-loaded value through the same whitelist, so a corrupt snapshot degrades to
  `null` rather than propagating garbage into the rebuilt badge.
- **`apps/desktop/main.js`** adds a `paneChrome` Map keyed by `paneId`. `spawnFromSelection` — the
  governed picker intent — RECORDS the selection's chrome preview server-side when it targets a LIVE
  pane and persists the layout snapshot so the badge is captured into the LAST GOOD layout for the
  next boot; `paneMeta(id)` returns that chrome (conductor branch still read first — a stray entry
  can never overwrite the CONDUCTOR badge); `pane:close` deletes the entry. A new `sendRecovery()`
  helper reconstructs + pushes the conductor-first layout over the SAME `shell:recovery` channel
  boot uses (no test-only shortcut). NO live worker is spawned here (still owed to 16F/U70).
- **`apps/desktop/renderer/renderer.js`** `onRecovery` restores each worker pane's model badge from
  the reconstructed `chrome` (a RECORDED selection restored — `node_state` stays
  awaiting-governed-spawn; the fold kept `reattach:false`, so no live node is claimed).

### Honesty (invariant 3; invariant 2; §6; §10.4)
- A pane with no recorded selection ⇒ `chrome:null` / `model:null` — never a fabricated model
  (invariant 3). `governed` is captured `false` (a RECORDED selection is not a live governed node);
  a corrupt snapshot fails closed to `null`.
- Carrying chrome NEVER auto-attaches or admits a live session: `reconstructLayout` unconditionally
  sets `reattach:false` / `admitted:false` on every recovered worker, independent of chrome
  (invariant 2 — no naked re-spawn on boot; nothing admitted until the control channel re-verifies).
- **Owed to 16F/U70, recorded:** the live governed worker SPAWN from a selection (the pane going
  from a recorded badge to an actually-running governed `claude`/`codex`/Ollama node). This sub-step
  proves the RECORD/READ half — the selected badge survives a restart. No live model call, no
  credential, no network (§2.2/§2.4); the only process spawned by the self-check is the supervised
  target pane through the gated admission path (invariant 2).

### Self-check (D-P16-0 binding, per-track) — REAL runtime evidence
`apps/desktop/selfcheck/recovery-selfcheck.js` (`node selfcheck/run.js recovery`) drives the REAL
renderer + REAL picker + REAL `RecoveryStore` inside the packaged Electron runtime: reaches
supervision READY (no naked session, invariant 2), spawns a supervised worker pane and records a
governed picker selection targeting it, then proves (3) the persisted `layout.json` off disk carries
the worker chrome (`snapshot_carries_chrome`, honestly `governed:false`), (4) the production restart
FOLD carries the chrome AND the recovered worker is still `reattach:false`/`admitted:false`, and (5)
the VISIBLE, load-bearing half — drop the in-memory picker badges so the badge goes blank
(`resetBadges` ⇒ `badge_cleared_on_reset`), then push `shell:recovery` through the production path
(`sendRecovery`) and assert the renderer REBUILDS the exact badge from the reconstructed chrome
(`badge_restored_from_recovery`). Recovery state isolated to `.recovery/selfcheck/`. Receipt:
`docs/evidence/receipts/PHASE16D_RECOVERY_SELFCHECK.json` — `ok:true`, all 10 checks true, Electron
31.7.7 / Node 20.18.0 / win32-x64; rendered badge `Opus 4.8 (unverified) · reasoning · 0/2 ·
selected` before reset → blank after reset → repainted after recovery.

**Load-bearing (empirically falsified by the gate-validator):** the validator injected
`return null` at the top of `_chromeSnapshot`, re-ran, and the self-check FAILED (`ok:false`, exit 1,
"the persisted snapshot did NOT carry the worker's model chrome (U68 not closed)"); it then restored
the file byte-identical (sha re-verified). A reverted U68 wiring cannot pass.

### Tests — ALL FRESH FOREGROUND (D-LOOP-2)
| Suite | Count | Δ |
|---|---|---|
| `py -3.12 -m pytest tests/ -q` | **1069 passed** | 0 (`.recovery` is JS-only) |
| apps/desktop `node --test test/*.test.js` | **135 passed** | +1 (`recovery-store.test.js` disk chrome round-trip) |
| terminal `node --test test/*.test.js` | **164 passed** | +4 (`layout-reconstruct.test.js`: capture whitelist / honest null / fold carry / corrupt→null) |
| **Total** | **1368** | +5 (was 1363) |

### Independent confirmation
- **gate-validator (isolated): PASS_WITH_RESERVATIONS** — independently re-ran the JS suites
  (164 / 135), DELETED + regenerated the self-check receipt (`ok:true`, exit 0, provably its own run
  by mtime), EMPIRICALLY FALSIFIED the load-bearing claim (injected `return null` ⇒ `ok:false`/exit 1)
  then restored byte-identical (sha + `git diff --numstat` re-verified), confirmed no live call / no
  credential / no orphan process / clean D-LOOP-1 teardown / recovery-state isolation to
  `.recovery/selfcheck/`, frozen canonical 4-hash set intact (6D3FD03B/8C9B7240/668089B5/CC414372),
  `mcp_server/` untouched. Reservations: **R1** the gate-close bookkeeping (U68 close, report flip,
  tag) must land in this commit — DONE here; **R2** cite the exit criterion at
  `AUTONOMOUS_BUILD_DIRECTIVE.md §15` (the Buildout Directive CC414372 defines only phases 0–13) —
  honored above; **R3** the pre-existing `pane:resize` **U73** TypeError logs during the self-check
  (out of `.recovery` scope, non-blocking, no receipt check affected).
- **spec-auditor: CLEAN** — no invariant violation / no prohibited drift (traced invariant 2/3/7,
  determinism, no float, no credential/network, §2.2/§2.4, §6/§10.4, no TTS, D-LOOP-1). 3 NITs, all
  "no action required", ACCEPTED-with-record: (1) `model_verified` is mirrored faithfully from record
  time, not re-verified at reconstruct time — provenance-faithful and paired with honest
  `governed:false` / `node_state:"selected_awaiting_governed_spawn"`, so it never asserts a live
  executing checkpoint; (2) `_chromeSnapshot` has no hard floor forcing `governed:false` — it relies
  on the sole upstream producer `chromePreview` (hard-sets `governed:false`) + the tests/self-check
  that pin `governed===false`; defense-in-depth only, no reachable path today; (3) `paneChrome` is
  deleted on `pane:close` but not on supervision-loss/`killAll` — consistent by design (a recorded
  selection is meant to survive a channel drop and repaint) and `paneMeta` reads the conductor branch
  first, so no stray entry can overwrite the CONDUCTOR badge. No code change taken (would invalidate
  the fresh independent gate-validation; all three are guarded, unreachable, or by-design).

### Substitutions (directive §6, explicitly listed)
1. **Record/read half only** — the live governed worker SPAWN from a selection is owed to
   operator-run **16F/U70**. This sub-step proves the RECORDED selection + its badge survive a
   restart, which is exactly the U68 criterion.
2. **Rendered recovery is an operator-run surface** (like the window itself) — the DATA path is
   proven headlessly (`layout-reconstruct.test.js`, `recovery-store.test.js`) + in-Electron
   (self-check); the pixel is operator-verified via the receipt.

### Frozen-canonical / MCP / prohibitions
Frozen canonical 4-hash set intact (6D3FD03B/8C9B7240/668089B5/CC414372); `docs/canonical/` not
modified; `mcp_server/` untouched (invariant 7 — no authorization logic added; the recovery fold is
pure `terminal/` + shell wiring). No push, no credentials, no network, nothing outside the repo root.
`config/live_operation.json` (gitignored) + `apps/desktop/package-lock.json` (untracked) deliberately
NOT swept.

### Provenance note (D-LOOP-2 recurrence recovery)
The `.recovery` code was produced as UNCOMMITTED CANDIDATE material by an interrupted prior turn
(2026-07-24 incident record) that ended waiting for a monitor notification that cannot arrive under
`claude -p`. Per the binding recovery-provenance rule, that turn's receipt was treated as DEAD: this
turn re-ran EVERY touched suite + the in-Electron self-check FRESH IN THE FOREGROUND, regenerated the
receipt from the current code, and re-ran BOTH subagent reviews fresh before adopting the material.

### Two-commit convention (`.recovery` — closes the track)
- Work commit: `layout-reconstruct.js` (+ `_chromeSnapshot`) + `main.js`/`renderer.js` rewire +
  `recovery-selfcheck.js` + `run.js` selector + the three touched test files.
- Evidence commit (this section + register rows + receipt) carries the work hash, then tag
  `gate/phase-16d`.

---

## Whole-track close — `gate/phase-16d`

All three 16D sub-steps have landed with their own in-Electron self-check receipts (D-P16-0):

| Sub-step | Closes | Work | Evidence | Receipt |
|---|---|---|---|---|
| `.statusbar` | governor n/2 into the status bar | 0676b21 | 5f682b9 | `PHASE16D_STATUSBAR_SELFCHECK.json` |
| `.approvals` | U66 (approval drawer read + governed decide) | 2be353f | 8566804 | `PHASE16D_APPROVALS_SELFCHECK.json` |
| `.recovery` | U68 (worker-pane chrome across restart) | *(this commit)* | *(this commit)* | `PHASE16D_RECOVERY_SELFCHECK.json` |

`gate/phase-16d` is applied on the `.recovery` evidence commit. 16D is NOT a directive-flagged
high-stakes gate (only 16A/16F are), but independent gate-validator confirmation was obtained for
the closing sub-step (PASS_WITH_RESERVATIONS, all reservations resolved or recorded). What Phase 16D
leaves OWED to the operator-run assembled validation at **16F**: dynamic per-session governor n/2
tracking; the shared long-lived approval queue where a resolve PERSISTS + its downstream side-effect
FIRES + authenticated per-node operator identity; and the live governed worker SPAWN from a picker
selection (U70). Pre-existing **U73** (`pane:resize` null-manager TypeError against the sessionless
placeholder) remains out of scope, non-blocking.
