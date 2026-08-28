# PHASE 16C EVIDENCE REPORT — Live conductor in pane 1 (sub-stepped)
Autonomous loop iteration 60 · 2026-07-24Z · gate: `gate/phase-16c` **NOT yet tagged**
(large phase, decomposed into sub-steps; the gate closes only when ALL sub-steps land)

## Objective (directive §15 / OP-10 track 16C)
End `awaiting_live_conductor`: on launch, pane 1 spawns the REAL interactive `claude` (fable-5
selection / recorded fallback) through the gated conductor spawn path, attached to Sovereign MCP;
**badge sources selection over IPC (closes U65)**; conductor dispatch of live workers per OP-9
(closes U58 as far as evidence allows). **Binding lesson D-P16-0 (per-track):** every shell/UI
change is exercised by an automated check that runs INSIDE the packaged Electron runtime on this
host and writes a machine-readable receipt.

## Decomposition (directive §3.2 — one named sub-step per iteration for large phases)
16C is large and the live-spawn slice is delicate (a real `claude` CLI spawned under the operator's
subscription, D-LOOP-1 teardown-critical, concurrency-capped). Sub-step order:

1. **`.selection` — DONE (this report).** READ-ONLY: pane-1's CONDUCTOR badge + Resume→Select
   succession are SOURCED from the Python authority instead of a hand-maintained literal. Closes
   **U65**. No live process; badge still honestly reads `awaiting_live_conductor`.
2. `.spawn` — pending: on-launch governed spawn of the real interactive `claude` conductor node
   through `conductor_pane_spawn.spawn_conductor_pane`; ends `awaiting_live_conductor`. D-LOOP-1
   teardown of the live CLI within the unit is CRITICAL.
3. `.dispatch` — pending: conductor dispatch of live workers over MCP (closes U58 as evidence allows).

The high-stakes framing note: 16C is **not** a directive-flagged high-stakes gate (only 16A / 16F
are). The `gate/phase-16c` tag + a final gate-validator close land when `.spawn` + `.dispatch` are in;
**no per-sub-step gate tag** (same convention as the 14A sub-steps).

## Source state
Tags through `gate/phase-16b` (+ `product/live`). `LOOP_STATE.next_step = phase-16c`,
`last_commit = 1fa97cd`; HEAD `dca861c` (iteration-59 loop commit). State consistent with tags —
**no reconciliation commit needed**. Frozen canonical 4-hash set intact
(6D3FD03B / 8C9B7240 / 668089B5 / CC414372). `mcp_server/` untouched by this diff.

Note: this unit finalizes an interrupted prior turn's uncommitted `.selection` work. Per the
PRINT-MODE contract (D-LOOP-2), the prior turn's receipt/suites were treated as DEAD and **every**
suite + the in-Electron self-check + both subagent reviews were re-run FRESH, FOREGROUND, this turn.

## What `.selection` delivers (closes U65)
**The defect (U65):** `apps/desktop/main.js` rendered pane-1's CONDUCTOR model badge + succession
from local literals (`CONDUCTOR_SELECTION_RECORD` / `CONDUCTOR_SUCCESSION_AFFORDANCE`) that MUST
mirror `control_plane/conductor/selection.OPERATOR_SELECTED_CONDUCTOR` — a copy the operator's
authority could silently disagree with (drift risk; invariant 3).

**The fix:** the shell now SOURCES the badge + succession from the ONE Python authority and renders
them VERBATIM — the two can no longer drift. This mirrors the already-gated 16B picker read-source
pattern (`enumerate_pane_picker --emit-picker` → `picker/source.js`): a single Python authority
produces the record set; the shell renders exactly what it produced and can never fabricate.

- **READ path (done).** `apps/desktop/conductor/source.js` bounded-spawns
  `py -3.12 tools/live/emit_conductor_selection.py --emit-conductor-selection` (the same `py -3.12`
  the shell already uses for the gateway + the 16B picker), STRICT-parses the
  `conductor_selection_feed@1.0` JSON, and hands it to the renderer. **No frontier model call, no
  credential, no network** (§2.2/§2.4) — the emitter imports two records via their canonical modules
  and prints them.
- **FAIL-CLOSED (invariant 3 / invariant 20 spirit).** A timeout / non-zero exit / non-JSON /
  malformed feed yields the UNKNOWN feed (`selection.model: null`), which the pure
  `terminal/compositor/conductor-pane.conductorBadge` renders **"(unknown selection)"** and whose
  succession renders unavailable. The shell shows an honest "unknown" rather than a fabricated
  "fable-5" it could not source — strictly more honest than the prior literal, which always claimed
  fable-5 even if Python disagreed. The startup feed is sourced BEFORE the window paints and is
  bounded, so it can never wedge launch.
- **PRE-LAUNCH honesty.** `executing.model` None, `verified` False, `is_fallback` False — nothing
  has executed; the badge shows the SELECTION label only. The live checkpoint is recorded only when a
  live reply reports one (the later `.spawn`/`.dispatch` work). The pane stays a governed placeholder
  (`sessionId: null`, `nodeState: "awaiting_live_conductor"`) — **no naked session** (invariant 2).

### Substitution recorded (directive §6, honest)
The directive phrasing for 16C says "badge sources selection over IPC." The delivered read path is a
**bounded `py -3.12` subprocess emitter**, not the WebSocket IPC channel — identical to the
already-gated 16B picker read-source. The conductor selection is a pure operator record (not live
node state), so a one-shot emitter is the faithful, honest read path; the WebSocket IPC channel is
reserved for live node/session feeds. Recorded here and in the register (U65 resolution) as a
substitution, never presented as the WS-IPC path.

## The change (files)
**Work commit (this unit):**
- `tools/live/emit_conductor_selection.py` (NEW) — the ONE authoritative feed: imports
  `OPERATOR_SELECTED_CONDUCTOR` / `bind_conductor_selection` (`control_plane/conductor/selection.py`)
  + `conductor_succession_affordance` (`node_runtime/supervisor/conductor_pane_spawn.py`), emits
  `conductor_selection_feed@1.0`. `--emit-conductor-selection` prints ONLY the feed JSON (one line);
  any other invocation is a fail-closed usage error (exit 2).
- `apps/desktop/conductor/source.js` (NEW) — bounded spawn + STRICT parse (rejects timeout /
  non-zero exit / non-JSON / malformed); DISPLAY wrapper `fetchConductorSelectionFeed` NEVER throws
  → fails closed to `unknownSelectionFeed()`; injectable `spawn` for deterministic tests.
- `apps/desktop/selfcheck/conductor-selfcheck.js` (NEW) — in-Electron D-P16-0 check; writes the
  receipt.
- `apps/desktop/main.js` — sources the feed at startup (before paint); badge / pane title / paneMeta
  / recovery selection now derive from the feed; `conductorState()` surfaces `selectionSourced` +
  `selectionSource` so the self-check can prove the badge is sourced, not a literal; the old literals
  are removed.
- `apps/desktop/renderer/renderer.js` — read-only self-check hooks (`conductorState`,
  `conductorBadgeText`) gated behind `?selfcheck=1` (grant no authority).
- `apps/desktop/selfcheck/run.js` — adds the `conductor` selector (`node selfcheck/run.js conductor`).
- `apps/desktop/test/conductor-source.test.js` (NEW) — 14 tests: fake-spawn fail-closed matrix +
  the fail-closed badge render + a LIVE `py -3.12` emitter integration asserting the operator
  selection (fable-5) and pre-launch honesty.
- `tests/unit/test_emit_conductor_selection.py` (NEW) — 7 tests: schema pin, **anti-drift** (feed ==
  operator authority verbatim), pre-launch honesty, succession authority, JSON round-trip,
  emit-only-JSON, fail-closed usage error.

## Self-check + tests (ALL FRESH, FOREGROUND — D-LOOP-2)
- **In-Electron D-P16-0 self-check:** `node selfcheck/run.js conductor` → **exit 0**, clean teardown
  (`gateway process exited`; no orphan PTY/gateway, D-LOOP-1). Fresh receipt
  `docs/evidence/receipts/PHASE16C_SELFCHECK.json`: `ok:true`, `feed_ok:true`,
  `selection_sourced:true`, `main_badge_model == feed_selection_model == "fable-5"`,
  `rendered_model_matches_feed:true`, `succession_available:true`,
  `badge_text: "CONDUCTOR · fable-5 (unverified) · awaiting_live_conductor"`,
  Electron 31.7.7 / Node 20.18.0 / win32-x64. Load-bearing: had the wiring reverted to a literal,
  `conductorFeed().ok` and `conductorState().selectionSourced` would be false and the check would FAIL.
- **Python:** `py -3.12 -m pytest tests/ -q` → **1022 passed** (was 1015 at 16B; +7 emitter tests).
- **Node apps/desktop:** `node --test` → **71 passed** (was 57; +14 conductor-source).
- **Node terminal:** `node --test` → **155 passed** (unchanged).
- Total **1248 green**.

## Independent review (mandatory; run in isolated contexts, foreground)
- **gate-validator — PASS.** Independently RE-RAN `node selfcheck/run.js conductor` (deleted the
  committed receipt first → freshly-written passing receipt, provably its own run), reproduced the
  7 + 14 targeted tests, confirmed: the old literals are GONE and the fail-closed "(unknown
  selection)" path is load-bearing; anti-drift (feed == authority verbatim); pre-launch honesty
  (executing None / verified False); no naked session; canonical 4-hash set intact (hashed itself);
  `mcp_server/` untouched. One non-blocking reservation: `git` was permission-gated in its sandbox,
  compensated by direct hashing + mtime scan (a tooling limitation, not a work defect).
- **spec-auditor — CLEAN** (no invariant violation, no prohibited drift; traced I-1/2/3/7/20,
  determinism, no float, no credential, §2.2/§2.4, D-LOOP-1). 2 NITs:
  **NIT-1** (docstring overstated purity vs. the transitive import graph) — **FIXED** this unit
  (reworded to "the executed path makes no model call…"; cites [[U71]]).
  **NIT-2** (defense-in-depth: relocate the pure succession-affordance builder to a leaf module free
  of adapter imports) — recorded as **U71**, accepted non-blocking (import-time purity is verified
  today; the fail-closed guarantee holds now).

## Invariants honored
I-1 (shell self-authorizes nothing — the read source performs no protected action) · I-2 (no naked
session — governed placeholder pane) · I-3 (conductor is a runtime SELECTION label; executing stays
unverified; no fabricated model) · I-7 (`mcp_server/` untouched; no authorization logic added) ·
I-20 (fail-closed / absent-reported-as-absent) · I-27/28 (the orchestra is visible; succession
control sourced, not a literal). Prohibitions §2.2/§2.4 intact (no credential, no live frontier
session in this read path).

## Owed / deferred (honest)
- **U71** (NEW) — relocate the pure `conductor_succession_affordance` builder to a leaf module free
  of adapter imports (defense-in-depth for the emitter's fail-closed purity). Non-blocking.
- **U65** — RESOLVED by this sub-step (badge no longer drifts).
- The live conductor spawn (ends `awaiting_live_conductor`) is the `.spawn` sub-step; live-worker
  dispatch (U58) is `.dispatch`. `gate/phase-16c` + the final gate-validator close land then.

## Two-commit convention
Work commit → this evidence + receipt + register-update commit (carries the work hash). **No gate tag
this unit** (sub-step). `LOOP_STATE` updated (`next_step` stays `phase-16c`; sub-step `.selection`
recorded DONE, next `.spawn`) and committed separately.

---

# 16C `.spawn` — governed-born conductor pane 1 (append; loop iteration 61 · 2026-07-24Z)

## What `.spawn` delivers
Until now pane 1's `node_state` was a hardcoded string in `apps/desktop/main.js`
(`nodeState: conductorPaneId ? "awaiting_live_conductor" : "unstarted"`) — the conductor-first pane
was a pure JS placeholder that never touched the governed spawn path. `.spawn` ends that: on launch
the shell SOURCES pane 1's governed spawn from the Python authority
`node_runtime/supervisor/conductor_pane_spawn.spawn_conductor_pane`, so pane 1 is **GOVERNED-BORN**
through the full live-gate chain — `ProfileLoader.assert_startup` (roster + `LIVE_OPERATION_AUTHORIZED`)
→ `LiveAuthorization.assert_provider_live(claude_code)` → R8 §6 operator-terms (OP-9, recorded) →
`claude` CLI presence → the I-X3 `SubscriptionGovernor` (acquire) — exactly as a live worker pane. The
node_state the shell renders is now **what the governed path produced**, not a literal.

- **READ path.** `apps/desktop/conductor/spawn-source.js` bounded-spawns
  `py -3.12 tools/live/emit_conductor_spawn.py --emit-conductor-spawn` (the same `py -3.12` the shell
  uses for the gateway, the 16B picker, and the 16C `.selection` badge), STRICT-parses the
  `conductor_spawn_feed@1.0` JSON, hands it to main. Sourced BEFORE the window paints; bounded, so it
  can never wedge launch.
- **The emitter runs the REAL governed spawn** with **NO launcher** ⇒ the interactive `claude` ConPTY
  drive is DEFERRED to the operator-run shell (`spawn_conductor_pane`'s documented deferred branch):
  **no live model call is made here** (§2.2/§2.4), `node_state` is the honest `awaiting_live_conductor`
  (gates passed, argv `["claude","--model","fable-5"]` + credential-scrubbed env built, I-X3 counted),
  and the badge shows the SELECTION label with executing **unverified** (invariant 3). The mock-first
  "ready" branch (a launcher injected ⇒ `node_state: ready`) is proven by the unit tests.
- **D-LOOP-1 (CRITICAL).** The governed spawn ACQUIRES one I-X3 terminal; the emitter tears it down
  (`ConductorPaneSession.teardown()`) in a `finally` **before emitting**, and records the release
  (`torn_down:true`, `governor_released:true` — the real `active_count(...) == 0`). With no launcher
  nothing is launched, so no live `claude` process is ever started — teardown only releases the
  counted terminal. Verified: no orphan `claude`/`electron`/`py` after every run (gate-validator §7).
- **FAIL-CLOSED (invariant 3 / invariant 20 spirit).** A timeout / non-zero exit / non-JSON / malformed
  feed yields the UNAVAILABLE feed (`spawned:false`, `node_state:"unstarted"`, chrome null) — pane 1 is
  an honest un-governed-live placeholder, **never a fabricated governed birth**. A governed REFUSAL
  Python emits (no config / provider not live / terms unconfirmed / `claude` absent / naked identity /
  I-X3 full) is a well-formed `spawned:false, refused:true, reason` feed surfaced as-is. The pane stays
  a governed placeholder (`sessionId: null`) — **no naked session** (invariant 2).

### Substitution recorded (directive §6, honest)
Same substitution posture as `.selection`: the directive says pane 1 "spawns the REAL interactive
`claude`". The delivered path runs the **governed spawn gate chain** (a real, non-vacuous live-gate
pass on this host — config authorizes + `claude` detected) and builds the interactive launch spec, but
the actual interactive ConPTY drive is the **operator-run surface** (directive §6) like every GUI in
this build. So `.spawn` makes pane 1 **governed-born** and honestly `awaiting_live_conductor`; it does
**not** by itself flip the running product into a live conductor conversation — that live drive + the
native-MCP attach (`mcp_client` is passed for parity only, not read) + live-worker dispatch (U58) are
`.dispatch` / operator-run, and `gate/phase-16c` + the final gate-validator close land then. Recorded
here, never presented as a live running conductor.

## The change (files) — `.spawn`
**Work commit (this unit):**
- `tools/live/emit_conductor_spawn.py` (NEW) — runs `spawn_conductor_pane` through the full live-gate
  chain (defaults resolve the REAL repo `load_live_authorization()` + cloud `ProfileLoader` + a fresh
  `SubscriptionGovernor`), tears the terminal down in a `finally` before emitting `conductor_spawn_feed@1.0`;
  fail-closed refusal feed on any governed refusal (never a fabricated spawn). `--emit-conductor-spawn`
  prints ONLY the feed JSON; any other invocation is a fail-closed usage error (exit 2).
- `apps/desktop/conductor/spawn-source.js` (NEW) — bounded spawn + STRICT parse; DISPLAY wrapper
  `sourceConductorSpawnFeed` NEVER throws → fails closed to `unavailableSpawnFeed()`; injectable `spawn`.
- `apps/desktop/selfcheck/conductor-spawn-selfcheck.js` (NEW) — in-Electron D-P16-0 check; writes the
  receipt `docs/evidence/receipts/PHASE16C_SPAWN_SELFCHECK.json`.
- `apps/desktop/main.js` — sources the governed spawn feed at startup (before paint);
  `conductorState().nodeState` now derives from the feed (`conductorSpawnNodeState`); surfaces
  `spawnGoverned` / `spawnSourced` / `spawnRefused` / `spawnTornDown` / `spawnSource` / `subscription`
  so the self-check can prove node_state is sourced, not a literal; `SHELL_SELFCHECK=conductor-spawn`
  dispatch + `conductorSpawnFeed` in the self-check ctx.
- `apps/desktop/selfcheck/run.js` — adds the `conductor-spawn` selector (`node selfcheck/run.js conductor-spawn`).
- `apps/desktop/test/conductor-spawn-source.test.js` (NEW) — 15 tests: fake-spawn fail-closed matrix
  (non-zero exit, non-JSON, malformed spawn/refusal, drifted schema, timeout, launch error, child
  error) + governed-spawn + governed-refusal parse + a LIVE `py -3.12` emitter integration asserting
  the governed deferred spawn is torn down.
- `tests/unit/test_emit_conductor_spawn.py` (NEW) — 12 tests: schema pin, governed deferred spawn
  (awaiting + torn-down + governor released), interactive-never-headless argv, subscription view,
  mock-first "ready" branch + session close, fail-closed refusals (denied auth / unconfirmed terms /
  absent CLI — no terminal leaked), recorded fallback, emit-only-JSON, JSON round-trip, usage error.

## Self-check + tests (ALL FRESH, FOREGROUND — D-LOOP-2)
- **In-Electron D-P16-0 self-check:** `node selfcheck/run.js conductor-spawn` → **exit 0**, clean
  teardown (`gateway process exited`; no orphan PTY/gateway, D-LOOP-1). Fresh receipt
  `docs/evidence/receipts/PHASE16C_SPAWN_SELFCHECK.json`: `ok:true`, `feed_ok:true`, `spawned:true`,
  `node_state:"awaiting_live_conductor"`, `interactive:true`, `argv:["claude","--model","fable-5"]`,
  `no_headless_flags:true`, `env_credential_scrubbed:true`, `torn_down:true`, `governor_released:true`,
  `spawn_governed:true`, `state_node_state == feed node_state`, `rendered_carries_node_state:true`,
  `badge_text: "CONDUCTOR · fable-5 (unverified) · awaiting_live_conductor"`,
  Electron 31.7.7 / Node 20.18.0 / win32-x64. Load-bearing: reverting to a hardcoded node_state ⇒
  `conductorSpawnFeed().ok`/`conductorState().spawnGoverned` false ⇒ the check FAILS
  (gate-validator empirically falsified this with a broken interpreter).
- **Python:** `py -3.12 -m pytest tests/ -q` → **1034 passed** (was 1022 at `.selection`; +12 emitter tests).
- **Node apps/desktop:** `node --test` → **86 passed** (was 71; +15 conductor-spawn-source).
- **Node terminal:** `node --test` → **155 passed** (unchanged).
- Total **1275 green**.

## Independent review (mandatory; isolated contexts, foreground)
- **gate-validator — PASS.** Independently re-ran the real emitter (one JSON line, all governed fields),
  DELETED then RE-RAN `node selfcheck/run.js conductor-spawn` → fresh passing receipt (timestamp
  provably its own run, not hand-written), reproduced the 12 + 15 targeted tests, **empirically
  falsified** the load-bearing claim (broken interpreter ⇒ unavailable feed ⇒ self-check rejects),
  recomputed the canonical 4-hash set intact, confirmed `mcp_server/` untouched and no orphan
  processes. 3 non-blocking reservations, all recorded honestly: **R1** — "governed-born" ≠ "live
  conductor running": `.spawn` does not end `awaiting_live_conductor` in the running product and MCP
  is not yet attached (parity only) — owed to `.dispatch`/gate close (the claim states this deferral
  explicitly, no overclaim); **R2** — `operator_terms_confirmed=True` rides recorded OP-9; **R3** —
  the feed is a string-pinned shell contract (same precedent as 16B/`.selection`), not a `schemas/@1.0`
  envelope.
- **spec-auditor — CLEAN** (no invariant violation, no prohibited drift; traced I-1/2/3/7/20/29/I-SC1,
  determinism, no float, no credential, §2.2/§2.4, D-LOOP-1). 3 NITs:
  **NIT-1** (operator_terms default is a literal — matches the ecosystem `live_flow`/15D pattern, and
  the config gate dominates) — accepted, OP-9 is the documented anchor.
  **NIT-2** (`test_denied_live_auth_...` had loose `and`/`or` precedence) — **FIXED** this unit
  (parenthesized).
  **NIT-3** (a hypothetical "would be OP-9" TTS note in the decision register collides in name with the
  recorded live-terms OP-9; the code cites the correct recorded one) — docs-hygiene observation,
  recorded as **U72**, non-blocking.

## Invariants honored — `.spawn`
I-1 (shell self-authorizes nothing — `operator_terms_confirmed` rides recorded OP-9, not a loop
decision; the config gate dominates) · I-2/29 (no naked session — governed placeholder pane, no `claude`
launched; supervised admission unchanged) · I-3 (conductor is a runtime SELECTION label; executing
unverified; fail-closed to un-governed-live, never a fabricated spawn) · I-7 (`mcp_server/` untouched;
no authorization logic added) · I-20 (fail-closed / absent-reported-as-absent) · I-SC1 (the gate keys
on the provider CAPABILITY, never the conductor label). Prohibitions §2.2 (credential-scrubbed env,
no credential read/stored/transmitted) / §2.4 (no live frontier call in this unit) intact. D-LOOP-1
(teardown-before-emit; no orphan) proven on real command output.

## Owed / deferred (honest) — `.spawn`
- **U72** (NEW) — decision-register hygiene: disambiguate the hypothetical-TTS "OP-9" mention from the
  recorded live-terms OP-9. Docs-only, non-blocking.
- The live interactive conductor drive that actually ends `awaiting_live_conductor` in the running
  product, the native-MCP attach, and live-worker dispatch (**U58**) are the `.dispatch` sub-step /
  operator-run surface. `gate/phase-16c` + the final gate-validator close land when `.dispatch` is in.

## Two-commit convention — `.spawn`
Work commit **9334270** → this evidence-append + receipt + register-update commit (carries the work
hash). **No gate tag this unit** (sub-step). `LOOP_STATE` updated (`next_step` stays `phase-16c`;
`.spawn` recorded DONE, next `.dispatch`) and committed separately.

---

# 16C `.dispatch` — govern-born conductor DISPATCH wired into the shell (append; loop iteration 62 · 2026-07-24Z) — **CLOSES `gate/phase-16c`**

## What `.dispatch` delivers (closes U58 as far as evidence allows)
`.dispatch` is the FINAL 16C sub-step; on it landing, **`gate/phase-16c` closes** (all sub-steps in:
`.selection` closed U65 · `.spawn` govern-born pane 1 · `.dispatch` wires conductor dispatch). It
implements the track-16C clause *"conductor dispatch of live workers per OP-9 (closes U58 as far as
evidence allows — honest receipts)."*

**The gap (U58):** the live `.flow` (15D) proved a live CONDUCTOR but the WORKERS were the
deterministic `LocalWorkerAdapter` (`legs.workers="mock"`, honest). The govern-born conductor pane
(`.spawn`) could be born but its DISPATCH of workers over MCP (OP-8 §13.4) was not surfaced in the
shell.

**The change:** the shell now SOURCES the govern-born conductor's governed DISPATCH from Python and
renders it on pane-1 chrome. `tools/live/emit_conductor_dispatch.py --emit-conductor-dispatch` runs
ONE governed dispatch through the REAL `control_plane/orchestration/live_flow.py` loop — the
conductor decomposes an objective → the Scheduler assigns each task **BY DESCRIPTOR** (invariant 4)
→ workers publish CANDIDATE over a real loopback MCP server → the REAL gate engine decides → the
conductor synthesizes the ACCEPTED set into an `acceptance_packet@1.0` — and folds the trace into a
stable `conductor_dispatch_feed@1.0` contract (`control_plane/orchestration/conductor_dispatch.py`).
`apps/desktop/conductor/dispatch-source.js` invokes that emitter as a bounded `py -3.12` one-shot
(the same read-source pattern as the 16B picker + 16C `.selection`/`.spawn`), parses fail-closed, and
`main.js` renders one dispatch line via the pure `terminal/compositor/conductor-dispatch.js`.

**SUBSTITUTION (directive §6, recorded) + honesty (inv 3 / §6 / §10.4):** the governed dispatch is
run **MOCK-first** — the mock conductor handle + `LocalWorkerAdapter` workers, so `legs.conductor=mock`
and `legs.workers=mock` and **NO live model call is made** (§2.2/§2.4). This proves the dispatch
MACHINERY end-to-end and wires it into the operator's shell; it does NOT manufacture a live-worker
result. `live_flow.build_acceptance_packet` / `_assert_legs_honest` make a `live`/`attempted` WORKER
leg **UNREPRESENTABLE** without its own evidence record, so **U58 cannot be faked closed by
construction**. The feed carries an explicit `live_workers_owed{owed:true, issue:"U58"}`; the rendered
line ends `· live workers OWED (U58)`. What remains OWED (unchanged): actual LIVE worker CANDIDATE
publication (Anthropic/Codex/Ollama) — the operator-run assembled run (**gate 16F**).

**Invariants surfaced on the feed:** invariant 4 (`by_descriptor` — true only when EVERY assignment
cites the descriptor); invariant 1 (`operator_disposition:"pending"` — gate promotion is NOT operator
acceptance; the rendered count says **gate-accepted**, never bare "accepted"); invariant 18 (the
acceptance verdict is the GATE node's; `synthesized_by` named separately, so the synthesizer never
judges its own work). **D-LOOP-1:** `run_governed_dispatch` tears the loopback MCP server + flow down
in a `finally` before returning (`torn_down:true`); the emitter uses an OS tempdir (never the repo,
§2.5); no live process, no orphan.

## The change (files) — `.dispatch`
- **NEW** `control_plane/orchestration/conductor_dispatch.py` — pure `fold_dispatch_feed(trace)` +
  `run_governed_dispatch(...)` (owns the loopback MCP server lifecycle, D-LOOP-1 teardown) +
  fail-closed `build_conductor_dispatch_feed(...)` + `undispatched_feed(...)`.
- **NEW** `tools/live/emit_conductor_dispatch.py` — `--emit-conductor-dispatch` prints ONE
  `conductor_dispatch_feed@1.0` JSON line (mock-first governed dispatch in a self-cleaning tempdir).
- **NEW** `apps/desktop/conductor/dispatch-source.js` — bounded read-source, fail-closed to the
  unavailable feed (schema-pinned well-formed check; injectable `spawn` for tests).
- **NEW** `terminal/compositor/conductor-dispatch.js` — pure dispatch summary line (legs verbatim,
  OWED U58 always surfaced; never dresses a mock dispatch as live).
- **NEW** `apps/desktop/selfcheck/conductor-dispatch-selfcheck.js` + `run.js`/`main.js`
  `conductor-dispatch` selector — the in-Electron D-P16-0 self-check.
- **NEW tests** `tests/unit/test_emit_conductor_dispatch.py` (9), `apps/desktop/test/
  conductor-dispatch-source.test.js` (15, incl. 1 live emitter), `terminal/test/
  conductor-dispatch.test.js` (5).
- **WIRING** `apps/desktop/main.js` (source dispatch after window; `conductorState().dispatch/
  dispatchRan/…`; ctx `conductorDispatchFeed`), `apps/desktop/renderer/renderer.js` (`.cdispatch`
  span + `applyConductorChrome` + `conductorDispatchText` self-check hook), `apps/desktop/renderer/
  index.html` (`.cdispatch` style).

## Self-check + tests (ALL FRESH, FOREGROUND — D-LOOP-2)
- **In-Electron D-P16-0 self-check:** `node selfcheck/run.js conductor-dispatch` → **exit 0**, clean
  teardown (`gateway process exited`; no orphan PTY/gateway, D-LOOP-1). Fresh receipt
  `docs/evidence/receipts/PHASE16C_DISPATCH_SELFCHECK.json`: `ok:true`, `feed_ok:true`,
  `dispatched:true`, `by_descriptor:true`, `accepted_count:2`, `acceptance_verdict:"PASS"`,
  `legs:{conductor:"mock",workers:"mock"}`, `legs_mock_honest:true`, `operator_disposition:"pending"`,
  `live_workers_owed:true`, `torn_down:true`, `dispatch_ran:true`,
  `dispatch_text == state_text` = `"DISPATCH · 2 worker(s) by descriptor · 2 gate-accepted · 1 queued ·
  legs mock/mock · live workers OWED (U58)"`, `rendered_carries_owed:true`,
  Electron 31.7.7 / Node 20.18.0 / win32-x64. Load-bearing: reverting to a literal ⇒
  `conductorDispatchFeed().ok`/`conductorState().dispatchRan` false ⇒ the check FAILS (gate-validator
  empirically falsified this by moving the emitter aside → self-check exit 1, `ok:false`).
- **Python:** `py -3.12 -m pytest tests/ -q` → **1043 passed** (was 1034 at `.spawn`; +9 dispatch tests).
- **Node apps/desktop:** `node --test` → **101 passed** (was 86; +15 conductor-dispatch-source).
- **Node terminal:** `node --test` → **160 passed** (was 155; +5 conductor-dispatch compositor).
- Total **1304 green**. All numbers re-taken FRESH after the two spec-auditor NIT fixes.

## Independent review (mandatory; isolated contexts, foreground)
- **gate-validator — PASS_WITH_RESERVATIONS.** Independently re-ran the real emitter (one JSON line,
  all governed fields); DELETED then RE-RAN `node selfcheck/run.js conductor-dispatch` → fresh passing
  receipt (timestamp provably its own run); **empirically falsified** the load-bearing claim (emitter
  moved aside ⇒ feed unavailable ⇒ self-check exit 1 `ok:false`), restored byte-identical (9/9 tests
  green); confirmed NO live `claude`/`codex` spawn in the dispatch path and that `_assert_legs_honest`
  makes a live worker leg unrepresentable (**U58 honestly OWED, not overclaimed**); reproduced
  1043/101/160 + targeted 9/15/5; canonical 4-hash set intact; `mcp_server/` untouched; no orphan
  processes. Reservations (both non-blocking, itemized): **R1** — a pre-existing `pane:resize` null
  TypeError at `main.js:451` on the sessionless conductor placeholder (out of `.dispatch` scope, NOT
  introduced here → recorded **U73**); **R2** — `git diff` is permission-denied in the validator's
  isolated context, so `mcp_server/`-untouched was verified by file-mtime + code inspection rather than
  a git-empty-diff (high confidence).
- **spec-auditor — CLEAN** (no invariant violation, no prohibited drift; traced I-1/3/4/5/7/10/11/16/18/20,
  §2.2/§2.4/§2.5, determinism, no float, no credential, mock-first, D-LOOP-1). 2 NITs, both **FIXED**
  this unit: **NIT-1** — `run_governed_dispatch` closed the `op` `McpClient` only on the happy path (a
  `connect()`/`publish` failure would leak an in-process socket; not a D-LOOP-1 violation since the
  server IS stopped) → now closed in the `finally` on every path. **NIT-2** — the rendered line said
  bare "accepted" (gate-accepted count) → now "**gate-accepted**", removing any chance an operator
  reads it as operator acceptance (invariant 1). Both re-verified: `pytest tests/unit/
  test_emit_conductor_dispatch.py` 9 green, `terminal … conductor-dispatch.test.js` 5 green, and the
  in-Electron self-check re-run fresh → `ok:true` with the "gate-accepted" text.

## Invariants honored — `.dispatch`
I-1 (shell self-authorizes nothing — the feed surfaces `operator_disposition:pending`, gate promotion
≠ operator acceptance; rendered "gate-accepted") · I-3 (conductor is a runtime SELECTION; the mock
dispatch is NEVER dressed as live — legs stated verbatim; fail-closed to "dispatch unavailable", never
a fabricated dispatch) · I-4 (routing BY DESCRIPTOR — `by_descriptor` true only if EVERY assignment
cites the descriptor) · I-5 (project state in MCP; the conductor can be swapped losslessly — unchanged)
· I-7 (`mcp_server/` untouched; no authorization logic added) · I-10/11 (workers publish CANDIDATE
with provenance — unchanged) · I-16 (failed artifacts can't advance — the flow's real gate engine) ·
I-18 (the acceptance verdict is the GATE node's; `synthesized_by` named separately — no self-judging)
· I-20 (fail-closed everywhere). Prohibitions §2.2 (no credential read/store/transmit) / §2.4 (no live
frontier call — mock-first) / §2.5 (writes only to an OS tempdir + the receipt under
`docs/evidence/receipts/`) intact. D-LOOP-1 (server+flow torn down before emit; no orphan) proven on
real command output + the receipt.

## Owed / deferred (honest) — `.dispatch`
- **U58** (NARROWED, still OPEN) — the governed dispatch MACHINERY is now wired + proven mock-first in
  the shell; the actual LIVE worker CANDIDATE publication with its own evidence record is OWED to the
  operator-run assembled run (**16F**). `_assert_legs_honest` keeps a live worker leg unrepresentable
  until that evidence lands.
- **U73** (NEW) — pre-existing `pane:resize` null-`manager` TypeError on the sessionless conductor
  placeholder (`main.js:451`); transient, non-fatal, self-check still PASSES; owed a fail-closed guard
  (16A-adjacent / 16F). Non-blocking.

## Two-commit convention — `.dispatch` (gate close)
Work commit → this evidence-append + receipt + register commit (carries the work hash) → tag
`gate/phase-16c`. `LOOP_STATE` updated (`.dispatch` DONE; 16C CLOSED; `next_step = phase-16d`) and
committed separately. **`gate/phase-16c` is the gate tag for the whole 16C track** (`.selection` +
`.spawn` + `.dispatch`), same convention as the 14A/15E sub-steps.
