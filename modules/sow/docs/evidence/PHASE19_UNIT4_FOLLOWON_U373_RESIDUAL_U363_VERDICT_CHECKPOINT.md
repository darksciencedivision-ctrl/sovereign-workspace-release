# Phase 19 — unit 19.4-followon: U373's residual, U363's verdict half, U380
## WORK-IN-PROGRESS CHECKPOINT (not a close). Round 2 of both mandatory reviewers is owed.

**Unit:** `phase-19.4-followon` (the follow-on the 19.4 close named).
**Commits:** `3b1f654` (work) → `17bfe06` (round-1 gate-validator remediation) → `6bf3ec0` (round-1
spec-audit remediation) → this evidence commit.
**Tag:** none. `gate/phase-19` belongs to unit 19.10; `product/multi-frontier-v2` is never moved.
**Register rows opened/closed here:** [[U395]] OPEN, [[U396]] CLOSED, [[U397]] OPEN.
**Closed by this unit:** [[U373]]'s residual, [[U380]], the [[U394]] items carried into it, and the
round-5 gate-validator's F4/F5 coverage gaps. [[U363]] is NARROWED, not closed.

---

## 1. Reconciliation at entry

`git tag -l` said `gate/phase-18e` and `product/multi-frontier-v2` were the newest tags;
`LOOP_STATE.json` said `phase-19.4-followon` with unit 19.4 CLOSED at iteration 128. They AGREE —
Phase 19's gate is unit 19.10's — so no reconciliation commit was owed. HEAD was `58f9ab6`, iteration
128's state-writing commit, and the tree was CLEAN: no prior turn died mid-unit and this one inherited
nobody's re-runs.

## 2. What the unit was asked to do, and what it did

The 19.4 close recorded the residual precisely: *"the U328 gate's OWN read... still calls
`buffer.snapshot()`, which is why a healthy connected worker STALLS and receipt leg F carries
`residual_u373_worker_stalls_though_connected: true`; that leg goes RED the day the gate is bounded,
and that is the signal to re-take the D-P16-0 receipt."* That is what happened.

**(a) The gate reads a screen, not a transcript ([[U373]]'s residual, CLOSED).**
`apps/desktop/control/pane-writer.js` no longer reads `buffer.snapshot()`. `paneScreenFromWindow`
takes the shell's bounded window object and maps `answerable !== true` — no session, no buffer, a
trimmed region, a window that throws — to UNREADABLE, which refuses. `apps/desktop/main.js` passes
**`readinessWindow` itself**, the same object the readiness state machine classifies through: not a
second reader built from the same parts, because two readers drift and the drift is exactly what put
a 256 KB scrape behind a gate whose sibling was reading a screen.

The consequence is the negative control the directive asked for, END TO END rather than at module
level: a healthy, connected, exit-0 worker whose transcript merely MENTIONS "not signed in" now gets
its readiness prompt DELIVERED and reaches READY. The assertion that used to require `ready === false`
("U373 residual: the audited pin survives as an honest STALL") is inverted, and the helper that
claimed to use the production binding while hand-rolling `{readable: true, text: buffer.snapshot()}`
now builds the real one — a "production" helper that reimplements the binding grades the double.

**(b) The verdict half ([[U363]], NARROWED).** Bounding a gate LOOSENS it, so the verdict was widened
in the same unit rather than left for later. `apps/desktop/control/modal-affordance.js` is new and
holds the affordance families `voice/pane-state.js` has enforced on the OPERATOR's own voice since
17C — MOVED, not rewritten (the round-1 spec-auditor could not diff, and said so; the validator
differential-fuzzed old against new `paneAcceptsTypedText` over 800 000 generated screens and found
**0 differences**). Of the ten realistic permission screens the 19.3 gate-validator walked through
this gate, **seven now refuse where one did**. The three that survive — a codex `(y = yes, a = always,
n = no)` approval, an elevation password prompt, a bare numbered menu — are ASSERTED in the suite as
the recorded residual, because inventing vendor wording is how a gate comes to look stronger than it
is. The positive-evidence half (`paneAcceptsTypedText`'s shape) is NOT adopted: its input markers are
`claude`-shaped and would mute every pane whose vendor chrome this shell has never seen.

**(c) [[U380]], CLOSED.** The window's line bound keeps the last N NON-BLANK lines. A repainting
provider's blank lines no longer spend the bound on nothing.

**(d) Carried [[U394]] items, all four done:** the retracted absolute at `worker-readiness.test.js`,
the separator count corrected to a MEASURED 41 (`" written immediately before the fragment "`), the
receipt disclosure, and the `pane_input_bypass_mutations.js` note trail.

**(e) F4/F5, the round-5 validator's unasserted properties:** the nonce window's mark floor is now
asserted (`U394/V4`) and graded (**R25**); the turn-level challenge freshness is asserted (`U394/V8`).

## 3. Round 1 — gate-validator: PASS WITH RESERVATIONS, and what it cost

Run in the foreground, in-turn, over `3b1f654`. Every measurement it was given re-derived: 939/0/0
desktop, 216/0 terminal, all four harnesses CAUGHT with byte-identical restores, and its own
in-Electron run of the receipt reproduced leg for leg. It re-derived the 41-character count itself and
re-verified freeze integrity (`8E604CA3…`, unchanged; no `docs/canonical/` file touched).

**Its two MAJORs were repaired in the tree** (`17bfe06`), because both are about what the gate can SEE
and that is this unit's whole subject:

- **MAJOR-2, and it is the important one.** `TAIL_LINES = 24` made the window SMALLER than the pane it
  judges: `main.js` spawns at `rows: spec.rows || 30` and the renderer fits larger, so a full-screen
  repaint drawing a live trust modal near the top left that modal OUTSIDE the only window allowed to
  see it — writable, where the whole-buffer read refused. Not a stale modal; a live one, in the same
  frame. `TAIL_LINES` is **80** now, and both module headers stop saying "the pane's CURRENT screen"
  where the code delivers the last N non-blank lines of it. The residual for a taller pane is
  **[[U395]]**, with a row-aware bound as its fix.
- **MAJOR-1: five of its eight own mutations survived all 939 tests.** Four are graded now —
  **R26** (screen order: deleting `lastLines`'s `.reverse()` turns a refusal into a write, because the
  numbered-menu pattern requires "1. Yes" before "2. No"), **P20** (the gate's window narrowed below
  the one it is supposed to share), **P21** (the affordance judged on the last 200 characters),
  **P22** (the refusal reporting a state that is not what happened) — and each has a behavioural
  assertion beside it. The fifth is an equivalent mutant and is recorded as such. **[[U396]]**.
- **MEDIUM-1** (the carried [[U394]] MINOR-4) is fixed: the receipt's generated headline said "each
  pane's launch record is SEEDED" while panes are A/B/G/H/I and `per_pane` is F/G/H/I.

## 4. Round 1 — spec-auditor: PROHIBITED DRIFT NONE

Run in the foreground, in-turn, over `17bfe06`. 0 BLOCKING, 2 MAJOR, 6 MEDIUM, 7 MINOR. It confirmed:
invariant 1's net effect is not an unadmitted weakening (every keystroke path still gated — pre-body,
submit key, the Codex second Enter); invariant 27 and fail-closed hold on every path ("I cannot see"
never renders as "nothing is wrong"); nothing was added under `mcp_server/` (invariant 7); the voice
path's rule is intact and only its `require` changed (invariants 25/26); the untouchable set is
undisturbed and the registers were not edited in place.

**Every finding was repaired in the bytes** (`6bf3ec0`), because all of them are prose or instruments
and that is the class this unit has spent five rounds fixing in its own comments:

- **MAJOR-1:** the self-check that GENERATES the receipt still said the write gate reads the whole
  buffer "deliberately" — false at HEAD, inside the instrument whose receipt says the opposite.
- **MAJOR-2:** this harness had told itself, in the future tense, that when the window became bounded
  the un-mutated `echoIsWhole`-always-false direction would become a verdict needing a mutation. **The
  trigger fired in this unit and the note did not notice.** It needs a fixture where the modal leaves
  the window DURING the settle wait, which this unit did not build: recorded as **[[U397]]** with an
  owner, in the present tense.
- **MEDIUM-13, the one behaviour change:** `affordance.text` is PROVIDER-CONTROLLED and travels into
  the refusal reason, the shell log, the conductor's operator-visible chrome and structured failures —
  and the two-line menu pattern matches ACROSS a newline. It is collapsed to one line before it goes
  anywhere.
- **MEDIUM-5:** the [[U380]] fixture stopped clearing its own bound when `TAIL_LINES` went 24 → 80 —
  it passed with R24 spliced in, graded only by its second assertion. The blank count is tied to
  `TAIL_LINES` now, so it cannot silently stop building its scenario again. The [[U367]] class, inside
  the test written to prevent it.
- Record corrections: the window is "the last 80 non-blank lines OF THE LAST 16 KB", spent on the RAW
  stream; the cost paragraph stops pricing 256 KB snapshots; the marker lists' provenance separates
  what was observed on this host's panes from what was written out; the scope note and receipt
  headline say F/G/H/I and admit the denylist; the withheld-write rule keeps its rule and drops its
  retired reason.

## 5. Measurements on the closing tree (`6bf3ec0`), foreground

| Instrument | Result |
|---|---|
| desktop suite | **942 pass / 0 fail / 0 skipped** |
| terminal suite | **216 / 0** |
| `system_pane_write_mutations.js` | **ALL 30 CAUGHT**, every file restored BYTE-IDENTICAL |
| `readiness_signal_mutations.js` | **ALL 26 CAUGHT**, restored BYTE-IDENTICAL |
| `pane_input_bypass_mutations.js` | **ALL CAUGHT**, `main.js` restored BYTE-IDENTICAL |
| `orchestration_mutations.js` | **5/5 CAUGHT**, every file restored byte-identically |
| D-P16-0 in-Electron receipt | `PHASE19_4_READINESS_WINDOW_SELFCHECK_phase-19.4-followon.audit-final_20260811T012905Z.json` — **ok: true, 9/9 legs**, `source.commit 6bf3ec0`, `tracked_product_tree_clean: true`, `live_exchanges: 0` |

**The receipt's two new legs are the unit's own falsification.** Leg **F** inverted: the gate PERMITS
(`gate_refusal_state: null`) while the whole-buffer read of the SAME live pane still says
`AUTH_REQUIRED`, both prompts are delivered and the run reaches READY — the healthy worker that
stalled for two units. Leg **I** is [[U363]]'s half on a real ConPTY: `classifier_verdict: null` and
`gate_refusal_terminal_state: PANE_AWAITING_OPERATOR_DECISION`, `prompts_delivered: 0` — the gate
refusing a screen the provider-state classifier says nothing about. Leg **H** now turns on BOTH
instruments being bounded (`buried_auth_state_reported: false`) rather than on their disagreement.

**Python suites not run, and the reason is not that they are slow:** no commit in this unit touches a
`.py` file. 19.10 owns that run ([[U339]]).

**D-LOOP-1:** four in-Electron runs this unit, every pane killed inside its run (5 sessions killed per
run, `sessions_killed_in_unit` recorded), `tasklist` reports ZERO surviving `electron.exe`, no stale
`.mutation.lock`. **No live provider call, no credential, `live_exchanges: 0` for the whole unit.**
**D-LOOP-2:** both reviewers ran foreground and synchronously, in-turn; nothing was backgrounded
across a turn boundary.

## 6. Why this is a CHECKPOINT and not a close

**Fix-after-validation voids it.** The gate-validator saw `3b1f654`; the spec-auditor saw `17bfe06`;
the tree is `6bf3ec0`. No reviewer has seen the tree the green receipt describes. That is precisely
the reason unit 19.4 did not close at round 4, and the directive's prescribed split for a unit that
will not fit its reviews in one turn is a WIP checkpoint with the remainder recorded — which is what
this is.

**What remains, exactly:** round 2 of BOTH mandatory reviewers over `6bf3ec0` (or over whatever tree
their own remediations produce), foreground and in-turn, as the next unit's FIRST act. The receipt
above describes `6bf3ec0` and does not need re-taking unless the tree moves.

**Carried, unchanged, to later units:** [[U395]] (the row-aware bound) and [[U397]] (the settle-wait
mutation and its fixture); [[U363]]'s positive-evidence half; [[U386]](c) + [[U393]] MINOR-1 → 19.6;
[[U335]]/F7 → 19.7; [[U382]] + F1/F2 → 19.9; [[U339]] and the phase gate → 19.10. [[U387]] is the
operator's.
