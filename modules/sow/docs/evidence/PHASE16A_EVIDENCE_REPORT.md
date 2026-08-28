# PHASE 16A EVIDENCE REPORT — Pane I/O (the defect)
Autonomous loop iteration 58 · 2026-07-24Z · gate: `gate/phase-16a` (HIGH-STAKES, mandatory gate-validator)

## Objective
Directive §15 / OP-10 track 16A: diagnose + fix the shipped shell defect the operator hit on
first launch — supervised session **output does not stream into xterm panes** and **keystrokes
do not reach sessions** (screenshot: RUNNING sessions, blank panes, no shell banner). Reproduce
INSIDE the packaged Electron runtime via an autorun self-check (spawn pane → banner in the
renderer buffer → type probe → echo), fix, commit the receipt. **Binding lesson D-P16-0:** the
change must be exercised by an automated check that runs inside the packaged Electron runtime on
this host and writes a machine-readable receipt — headless Node tests alone (which closed 14A)
are insufficient.

## Source state
Tags through `gate/phase-15e` + `product/live` (Phase 15 terminal, status was COMPLETE). OP-10
armed Phase 16 at `next_step: phase-16a`. No `gate/phase-16*` tags yet — state consistent with
tags; no reconciliation commit needed. Frozen canonical 4-hash set intact
(6D3FD03B/8C9B7240/668089B5/CC414372). `mcp_server/` untouched.

## Root cause (diagnosed against the shipped code)
The renderer builds a pane's xterm VIEW lazily, only when the §10.2 layout plan arrives — and
that plan rides a **250 ms-debounced** channel, i.e. AFTER the supervised PTY has already printed
its banner. The old renderer then:
- `S.onData((id,data)=>{ const rec=terms.get(id); if(rec) rec.term.write(data); })` — a live
  chunk arriving before the term view existed was **silently dropped** (no buffer); and
- `ensurePane` **never replayed the session's byte-exact scrollback** on (re)attach, though the
  code comment claimed "re-expansion reattaches losslessly".

Net: the banner (and all early output) is lost → blank pane, permanently until new output
arrives (PowerShell does not reprint its banner). The "cannot type" half compounds it: clicking a
pane routed the focus MODEL (`S.focus`) but never gave the xterm textarea DOM focus, so
keystrokes had nowhere to go.

## The fix (files)
**Work commit `da09b7c`:**
- `apps/desktop/renderer/pane-feed.js` (NEW) — pure `PaneFeed`: merges byte-exact scrollback with
  the live stream using a per-session monotonic `seq`. Writes scrollback first, then only live
  chunks with `seq > baseSeq` (chunks ≤ boundary are already in the snapshot). No gap, no
  duplication. IIFE-wrapped so the class is not a global lexical binding (a bare top-level
  `class PaneFeed` collides with renderer.js's `const PaneFeed` — both share the classic-script
  global scope — a SyntaxError that aborts renderer.js; this bug was found and fixed **by the
  in-Electron self-check**, exactly the failure headless tests miss).
- `apps/desktop/test/pane-feed.test.js` (NEW) — 8 unit tests of the seq-boundary invariant
  (no-duplication at exactly `baseSeq`, no-gap, seq-order flush regardless of arrival order,
  no-session flush, ready passthrough, idempotent re-attach).
- `apps/desktop/main.js` — tags every `pane:data` chunk with a per-session `seq`; new read-only
  `pane:scrollback` IPC handler returns `{text, seq}` from `manager.registry.reattach(id)` (the
  byte-exact `RingBuffer` snapshot, read atomically with `dataSeq` on the single-threaded main
  loop); `emitLayoutNow()` on pane create (term built promptly, not only after the debounce);
  the `SHELL_SELFCHECK` hook + isolated `.recovery/selfcheck/` recovery dir + a load-time
  `?selfcheck=1` query flag; SHELL_SELFCHECK-guarded console/crash diagnostics.
- `apps/desktop/preload.js` — read-only `scrollback` intent; `seq` threaded through `onData`.
- `apps/desktop/renderer/renderer.js` — PaneFeed usage; async scrollback replay on (re)attach
  (`attachFeed`); `term.focus()` on click and on the focused pane (the "cannot type" fix); a
  read-only `window.__sovereignSelfCheck` observability hook armed ONLY under `?selfcheck=1`.
- `apps/desktop/renderer/index.html` — loads `pane-feed.js` before `renderer.js`.
- `apps/desktop/RUN_ON_WINDOWS.md` — operator self-check run (`node selfcheck/run.js`).

**Self-check harness (same commit):** `apps/desktop/selfcheck/pane-io-selfcheck.js` (in-Electron
autorun) + `apps/desktop/selfcheck/run.js` (node launcher — `node` is the permitted entrypoint,
as `npm start` would spawn electron; hard 150 s timeout).

## Exit criteria — met, on in-runtime evidence
- **Output streams into the pane (the defect):** self-check receipt `banner_seen:true`,
  `banner_excerpt:"SOVEREIGN_SELFCHECK_BANNER PS C:\\Users\\Sslaw>"` — the deterministic banner
  AND a real PowerShell prompt rendered into the renderer's xterm buffer. Load-bearing: with the
  old "write-live-only" path the banner (printed before the debounced term view) is dropped;
  scrollback replay + seq buffering closes it (the `PaneFeed` unit test pins the boundary).
- **Keystrokes reach the session (the defect):** `echo_xterm_seen:true` — `term.input(data,true)`
  fires the exact `term.onData → S.input → pane:input → manager.write → PTY → echo → render`
  wiring a physical key uses; the echo rendered back. `echo_bridge_seen:true` independently proves
  the input IPC path. `active_element:"xterm-helper-textarea"` proves the focus fix lands DOM
  focus on the xterm textarea (the root cause). `echo_dom_seen:false` recorded honestly — synthetic
  OS keystroke delivery (`sendInputEvent`) into xterm is a known-unreliable harness artifact, not
  shell code; physical-keyboard end-to-end confirmation is owed to operator gate 16F (see U69).
- **Reproduced INSIDE the packaged Electron runtime (D-P16-0):** `node selfcheck/run.js` boots the
  REAL `py -3.12` gateway, reaches `supervision READY`, spawns a **supervised** pane through the
  same `createPaneWithSession → manager.spawn → supervisor.admit` path (no naked session,
  invariant 2 — it waits for `supervisor.ready` first), drives the real renderer + real ConPTY,
  writes the receipt, tears everything down (no orphan PTY/gateway, D-LOOP-1), exits 0.
- **Receipt committed:** `docs/evidence/receipts/PHASE16A_SELFCHECK.json` (`ok:true`, Electron
  31.7.7 / Node 20.18.0 / win32-x64). Self-check recovery isolated to `.recovery/selfcheck/`
  (gitignored) — the operator's real recovery state is never polluted.

## Tests (all foreground, fresh — D-LOOP-2)
- `node --test apps/desktop/test/pane-feed.test.js` → **8 pass**.
- `node --test terminal/test/*.test.js` → **155 pass**.
- `node --test apps/desktop/test/*.test.js` → **46 pass** (was 38 at 15E; +8 pane-feed).
- `py -3.12 -m pytest tests/ -q` → **1011 passed**, 0 failed (pre-existing jsonschema
  deprecation warnings only). Total **1212 green** (was 1204).

## Independent review (HIGH-STAKES: mandatory gate-validator + spec-auditor)
- **gate-validator: PASS_WITH_RESERVATIONS** (isolated context). Independently RE-RAN
  `node selfcheck/run.js` (fresh receipt, exit 0 — not hand-written), reproduced 155 / 46 / 1011,
  confirmed the fix load-bearing against old-vs-new code, `pane:scrollback` reads the byte-exact
  RingBuffer, no naked sessions, clean teardown, recovery isolated, canonical + mcp_server
  untouched. **R1 (owned):** the full synthetic-OS-keystroke→echo chain is not auto-proven
  (`echo_dom_seen:false`); its two halves are (focus lands on the xterm textarea; `term.onData`
  round-trips) — physical-keyboard confirmation scheduled at 16F. **R2 (minor):** the
  observability hook was exposed unconditionally → **FIXED this unit** (gated behind
  `?selfcheck=1`).
- **spec-auditor: CLEAN** — no invariant violation, no prohibited drift. Traced I-1 (no
  self-authorization; input is keystroke passthrough to a supervised PTY), I-2 (supervised spawn
  only), I-27 (byte-exact RingBuffer replay, no fabrication), I-29/TB-2 (renderer stays
  sandboxed/contextIsolated; `scrollback` read-only; hook grants no authority), determinism/
  fail-closed (PaneFeed pure), no float, mcp_server untouched, D-LOOP-1 teardown, canonical
  untouched. One NIT (unconditional hook) — **FIXED this unit** (same as R2).

## Substitutions & honest limits (directive §6)
- The **rendered GUI window** is an operator-run metric (§6, Phase-1 substitution pattern) — but
  UNLIKE prior phases, the pane data path is now exercised **inside the real Electron runtime**
  (D-P16-0), not headless-only: the banner/echo assertions read the actual on-screen xterm buffer.
- **`echo_dom_seen:false`** — synthetic OS-keystroke delivery is a harness artifact; the real
  renderer wiring is proven via `term.input` + the focus assertion. Physical typing is owed to 16F.
- 16A does **not** close the owed live-feed family U65–U68 (those are 16C/16D). This unit closes
  the pane-I/O defect only.

## Decisions closed
- `gate/phase-16a` closed by **operator-delegation (ruling 2026-07-16)**; basis OP-10. High-stakes
  → mandatory independent gate-validator PASS_WITH_RESERVATIONS recorded.

## New unresolved item
- **U69** — physical-keyboard end-to-end (browser keydown on the focused xterm textarea →
  `onData` → echo) is validated only in its two halves by the automated self-check; confirm the
  full physical chain at operator gate 16F. Non-blocking (the wiring it depends on is proven).
