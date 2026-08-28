# PHASE 14A SUB-STEP EVIDENCE — Pane-Layout Policy + Geometry (`phase-14a.tiling`)
Autonomous loop iteration 17 · 2026-07-18Z · sub-step `phase-14a.tiling` · **no gate tag yet**
(the high-stakes `gate/phase-14a` closes only when ALL 14A sub-steps land, with mandatory
gate-validator confirmation; this report covers the third sub-step and carries no tag).

## Objective
Deliver the pane-layout leg of Phase 14A (directive §9 track 14A): the real **Plan §10.2**
dynamic-tiling policy + geometry — the algorithm the Phase-1 spike's
`tools/spike_compositor/lib/layout.js` only sketched. Concretely: priority classes P0..P4, the
visible-set cap (`max_visible`), the status-card rail for auto-collapsed panes, the hard rule
that operator-required (P1) panes are never auto-collapsed, near-square grid with P0/P1 double
cells, and 250 ms membership-change-only relayout debounce. Consumes
`PaneModel.tilingMembers()` (built in `.shell`). The routing/artifact inspector and UI recovery
are the remaining sub-steps (`.inspector` → `.recovery`).

## Source state
Tags through `gate/phase-13` + `build/complete` + `audit/completion-20260718`; predecessor
sub-steps `.ipc` (`7eb96e3`/`516a480`) and `.shell` (`16448bb`/`ac72171`) committed;
`next_step: phase-14a.tiling`; **no `gate/phase-14a`**. State/tags agree — reconciled at the
start of the iteration (Loop Protocol §3.1); no gate tag was or is claimed for a sub-step.
Freeze set untouched; `docs/canonical/` not modified.

## What this sub-step is NOT (honest scope)
- **Not a verified window.** Per loop directive §6, the Electron window cannot be rendered or
  observed in this headless session; it is an **operator-run metric** exactly like the Phase-1
  spike (`apps/desktop/RUN_ON_WINDOWS.md`). The layout **policy + geometry** is pure and
  headlessly tested; the renderer that paints it is operator-verified. No rendered behaviour is
  claimed as observed.
- **Not the live priority feed.** The priority machinery (P0..P4, double cells, rail collapse)
  is fully built and tested, but in the running product today only `pin` (→P0) is driven by an
  operator action; `awaiting_operator`/`background`/`idle` need a control-plane priority signal
  (approvals queue, node busy/idle state) that a later 14A sub-step / phase wires. The mechanism
  is complete; the live drivers for P1/P3/P4 are recorded as pending, NOT overclaimed as
  end-to-end I-27 coverage (spec-auditor MINOR 2, accepted).
- **Not drag-to-reorder.** §10.2's "drag to reorder overrides auto-placement until unpinned" is
  not in this sub-step's scope (priority classes / planLayout / scheduler); recorded as carried
  (spec-auditor MINOR 4).

## Files (work commit)
Product layout core (`terminal/compositor/`, headlessly tested):
- `terminal/compositor/tiling.js` (**NEW**) — pure §10.2 policy + geometry. `classify()` maps
  pinned+activity → P0..P4 (pinned overrides activity; **fail-closed** on unknown activity);
  `nearSquare(n)` = `ceil(sqrt(n)) × ceil(n/cols)`; `gridGeometry()` gives P0/P1 double
  (span-2) cells; `planLayout({maxVisible})` reserves all P0+P1 (hard rule), fills the remaining
  budget with P2, and collapses P2-overflow + all P3/P4 to `cards`; `membershipKey()` is a stable
  key derived ONLY from priority + geometry (never `attention`), so chrome flips do not reflow;
  `LayoutScheduler` is a **250 ms-debounced, membership-gated** relayout with an **injected
  timer** (deterministically testable, no wall-clock in the pure path).
- `terminal/compositor/pane-model.js` — added the `activity` field (default `"active"`),
  `setActivity()` (**fail-closed** on unknown activity/pane), and `activity` in
  `tilingMembers()`. `attention` stays a chrome-only pulse (never a priority input).

Wiring (operator-run GUI surface; parse-checked, not headlessly executable — electron/xterm are
operator-host installs):
- `apps/desktop/main.js` — computes the §10.2 plan in the **Node main process** (where the
  tested module lives) and pushes it over a dedicated **debounced `shell:layout` channel** via
  `LayoutScheduler`; `shell:state` stays the chrome/content channel (realizing §10.2
  "restyle without reflow"). New `pane:activity` intent → `panes.setActivity`. `MAX_VISIBLE=6`
  (the policy API is tunable; the shell pins the §10.2 default — a live operator control is
  deferred, spec-auditor MINOR 1).
- `apps/desktop/preload.js` — bridges the `pane:activity` intent (renderer→main) and the
  `onLayout` stream (main→renderer). No widening of renderer authority.
- `apps/desktop/renderer/{renderer.js,index.html}` — thin view: reflows the grid + P0/P1 spans
  ONLY on `shell:layout`, restyles chrome on `shell:state`, and renders the collapsed panes as a
  right-hand **status-card rail**. Terminal output is written to xterm only, never routed back as
  a command (TB-2/I-29).
- Tests (`node --test`): `terminal/test/tiling.test.js` (**NEW**, 25) + updated
  `terminal/test/pane-model.test.js`.

## Exit criteria for the sub-step (Plan §10.2) — met, mapped to code + test
- **Near-square grid `ceil(sqrt(n)) × ceil(n/cols)`:** `nearSquare()`; tested n=1..12 fit +
  near-square, plus `nearSquare(6)={3,2}`, `nearSquare(8)={3,3}`.
- **Priority classes P0..P4** from pinned+activity; **pinned overrides activity**; **fail-closed
  on unknown activity:** `classify()` + `setActivity()`; tested incl. `pinned+idle → P0` and the
  unknown-activity throw.
- **Visible set = P0..P2 up to `max_visible` (default 6, tunable); P3/P4 + P2 overflow →
  status cards:** `planLayout()`; tested 9×P2 @6 → 6 tiled / 3 cards; P3/P4 always carded;
  `maxVisible:2` tunable; `DEFAULT_MAX_VISIBLE===6`.
- **HARD RULE — P1 (awaiting-operator) can NEVER be auto-collapsed**, even when P1 alone exceeds
  `max_visible`: `tiled = [...p0, ...p1, ...p2Visible]` (budget gates only P2). Tested: 8×P1 @6
  → 8 tiled / 0 cards; and P0-reservation squeezes P2 out first while no P0/P1 ever enters the
  rail. **Validated load-bearing** — a naive `slice(0, maxVisible)` would collapse 2 P1 (the
  validator reproduced this).
- **P0/P1 double cells:** `gridGeometry()` span-2 for P0/P1 when `n>1 && cols≥2`; single pane
  never doubles. Tested.
- **Recompute debounced 250 ms on membership change ONLY:** `membershipKey()` ignores
  `attention` (tested: attention flip → key stable; pin/activity/reorder → key changes);
  `LayoutScheduler.update()` returns `false` and schedules nothing on chrome-only change,
  coalesces rapid membership changes into one relayout with the latest state, and cancels on
  `dispose()`. The **literal 250 ms default** is asserted (and an override honored) via a fake
  timer that captures the scheduled delay (added to close validator R1).
- **Deterministic / fail-closed / no model output:** pure functions, no I/O/clock/randomness in
  the layout path; time injected into the scheduler; `maxVisible` rejects `0/-1/2.5/"6"/true/NaN`
  and treats `null`/absent as the default.

## Independent review
- **gate-validator: PASS** (isolated context, real commands reproduced). Verified every §10.2
  criterion above with its own probes, and specifically confirmed the P1-never-collapsed rule is
  **load-bearing** (8×P1@6 → 8 tiled; naive slice would break it), `membershipKey` stability
  under `attention` vs change under priority, and `maxVisible` fail-closed validation. Observed:
  `tiling.test.js` 24→(now 25) pass, `pane-model.test.js` 12 pass, `terminal/test/*` 58 pass,
  `apps/desktop/test/*` 15 pass, `pytest` 364 pass; GUI files `node --check` clean. Reservations
  (non-blocking): **R1** no literal-250 assertion → **now FIXED** (test added, asserts 250 &
  override); **R2** (informational) double cells can push grid `rows` past `nearSquare`'s row
  count — an honest consequence of span-2 slotting, not a spec violation.
- **spec-auditor: CLEAN** — no MAJOR, no invariant drift. Confirmed load-bearing: determinism
  (I-16/§4 — fixed priority table, no model/clock/random in the layout path); §10.2 hard rule
  faithfully implemented (operator authority I-1 preserved; pinned→P0 uncollapsible); I-1 not
  self-authorized (gateway spawn is role `shell`, `pane:activity` only sets a display hint);
  TB-2/I-29 (renderer sandboxed `sandbox:true`, CSP `script-src 'self'`, output never routed as
  command); fail-closed on unknown activity/maxVisible; I-27 collapsed panes surfaced as cards.
  4 MINOR (all accepted/recorded, none blocking): (1) "operator-tunable" was aspirational at the
  shell → comment softened to say the policy API is tunable while the shell pins the default;
  (2) `activity` not yet driven live beyond pin → recorded above, I-27 not overclaimed
  end-to-end; (3) maximize hides a P1 pane (operator-initiated, not an auto-collapse; the
  always-visible approval-queue drawer is §10.3 / a later sub-step); (4) drag-to-reorder not
  implemented (out of scope) — carried.

## Substitutions (loop directive §6)
- **GUI verification deferred, not faked.** The Electron window is an operator-run metric
  (`apps/desktop/RUN_ON_WINDOWS.md`) exactly like the Phase-1 spike. The layout **policy +
  geometry** — the governance-bearing part — is pure and fully headlessly tested (25 tiling
  tests); the renderer that paints the plan is operator-verified. No rendered behaviour is
  claimed as observed.

## Deviations / carried
- **ruff unavailable** (pip out of scope, §2.7); JS has no repo linter — code is `node --check`
  clean and exercised by `node --test`.
- **Carried (§10.2 completeness, later sub-steps):** live P1/P3/P4 priority feed from the
  control plane (approvals + node busy/idle); an operator control to retune `max_visible` live;
  drag-to-reorder override; the always-visible approval-queue drawer that surfaces awaiting-
  operator items even under maximize (§10.3).
- **U25/U26** unchanged (IPC→MCP per-node credential broker; OS-level pid→JobObject containment
  from the shell) — not touched by this sub-step.

## Test totals
- JS: **74 passed / 0 failed** (`node --test terminal/test/*.test.js apps/desktop/test/*.test.js`)
  — terminal 59 (incl. 25 tiling), apps/desktop 15 (which drive real `py -3.12` gateway
  subprocesses, not skipped).
- Python: **364 passed** (`py -3.12 -m pytest tests/ -q`) — unchanged; this sub-step touches no
  Python.

## Sub-step verdict
**PASS (sub-step)** — gate-validator PASS, spec-auditor CLEAN (both reproduced with real
commands in isolated contexts; the sole reservation R1 is fixed this iteration). A pure,
deterministic Plan §10.2 tiling policy + geometry — priority classes P0..P4, `max_visible` cap,
status-card rail, P1-never-auto-collapsed hard rule (proven load-bearing), P0/P1 double cells,
and a 250 ms membership-gated relayout debounce — consuming the real `PaneModel.tilingMembers()`
and wired into the Node main process over a debounced `shell:layout` channel. `gate/phase-14a`
is **NOT** tagged — the high-stakes gate (mandatory gate-validator) awaits `.inspector` and
`.recovery`.

## Commits
Work `58dade9` → this evidence/register commit (carries the work hash) → loop-state commit.
**No gate tag** (sub-step; `gate/phase-14a` awaits `.inspector`, `.recovery`).

## Next
`phase-14a.inspector` — the routing/artifact inspector (Plan §10.3): per-task view of context
routed, artifacts published (hash, status, provenance), and the gate chain, consuming MCP state
over the D-IPC-01 channel. Then `.recovery`; `gate/phase-14a` closes when all land.
