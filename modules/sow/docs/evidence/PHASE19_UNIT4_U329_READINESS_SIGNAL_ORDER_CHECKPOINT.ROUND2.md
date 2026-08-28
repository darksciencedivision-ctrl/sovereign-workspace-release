# Phase 19 · Unit 19.4 — U329, round 2: the owed in-Electron leg, and the defect it took to find

**Status: CHECKPOINT — NOT CLOSED.** This document **supersedes §4 and §6** of
`PHASE19_UNIT4_U329_READINESS_SIGNAL_ORDER_CHECKPOINT.md` (which is left exactly as written — the
evidence set is append-only) and records what the second round of the two mandatory reviewers found.
Both returned findings whose repair changed the tree, so directive §18's *fix-after-validation voids
it* applies again and **round 3 of both reviewers is the next unit's first act**.

| | |
|---|---|
| Unit | `phase-19.4` (AUTONOMOUS_BUILD_DIRECTIVE.md §18, row 19.4 — U329) |
| Work commits this iteration | `8272f2c` (the owed in-Electron leg + its falsification) · `14a3ad1` (round-2 review remediation — U379) |
| Earlier work commits | `716673d` (the order, the window, the extraction) · `a6166e7` (round-1 remediation — U373) |
| Reviewers, round 2 | gate-validator (isolated git worktree) **FAIL**, 1 BLOCKING · spec-auditor (read-only, primary tree) **PROHIBITED DRIFT: NONE**, 1 BLOCKING |
| Tag | none — `gate/phase-19` is unit 19.10's, and `product/multi-frontier-v2` is never moved |
| Live provider calls | **0** |

---

## 1. What this iteration was for

The checkpoint's §6 listed three owed items. This iteration did the first two:

1. **The in-Electron leg that drives `createWorkerReadiness.run()`.** Legs A–E of the D-P16-0 check
   drove the production window and the production ordering function; the state machine around them —
   including the U373 remediation both round-1 reviewers forced — was evidenced by the headless suite
   alone. On this unit's own record that is not a small gap: the round-1 defect was invisible to
   fifteen headless tests *because their harness stubbed `writeRefusal` to null*.
2. **Round 2 of both mandatory reviewers**, foreground, sequential, in-turn.

The third (bounding the U328 gate's own read, U373's residual) is a unit, not a remainder, and is not
attempted here.

**Ordering, recorded because it deviates from the checkpoint's instruction.** The checkpoint said
round 2 runs on `a6166e7` *first*. It ran on `8272f2c` instead — the leg was built first — because
adding the owed leg after a passing round would itself have voided that round. The reviewers were
given the complete unit rather than two thirds of it.

## 2. The leg (`8272f2c`)

Legs F/G/H run the real state machine in the packaged runtime over real ConPTY panes, bound to the
production U328 write gate, write path, bounded window, launch-record store and operational-state
writer. `main.js` gains one binding — `setWorkerOperationalState` in the SHELL_SELFCHECK ctx, eight
lines with its comment, no other change to that file.

- **F** — a pane whose SCROLLBACK mentions an auth failure. The gate refuses (it reads the whole
  buffer by design). The run must report a STALL that NAMES the withheld write and must not report
  the provider state the gate's phrase would suggest. The leg also **requires** `ready === false`:
  U373's residual is measured, not described, so the receipt goes red the day the gate is bounded.
- **G** — a clean pane that answers. The gate permits, the production write path puts the prompt into
  a real ConPTY, and the bounded nonce window counts the token coming back off the real pane buffer.
- **H** — a pane whose current screen is a trust modal while its scrollback holds an auth line, so
  **only the bounded window can produce the leg's answer**. (This is what the leg became after the
  round-2 review; see §3.)

Falsifiability: `apps/desktop/test/readiness-window-selfcheck.test.js` drives the real check function
against a simulated runtime and requires each leg to go red on the defect it names.
`readiness-window-wiring.test.js` asks the question neither the module tests nor the check can — does
`main.js` hand readiness and the check the shipped objects, or lookalikes.

## 3. What round 2 found

**Both mandatory reviewers reached the same BLOCKING finding independently**, with their own probes
and their own spellings, and it was re-verified on disk before either report was acted on.

`waitForTurn`'s withheld-write loop — the loop `a6166e7` added to fix U373 — never refreshed the
launch record. It classified with the record the TURN began with, for the whole response deadline,
while the answer loop twenty lines below refreshes on every poll. So **a worker that died while the
gate withheld its prompt was decided by its screen**: the directive row's first clause, inverted
inside the remediation written for its second. And the structured failure asserted
`process_state: "running"`, `exit_code: null` for a process that had exited — on the path that *did*
observe the exit, beside `decided_by: "process_exit"` and a real exit code. Mutation R1 does not catch
it: R1 mutates the pure function's guard, not the caller that feeds it stale state.

`14a3ad1` fixes it the way the sibling loop already worked (read the record first, return the exit by
its code), re-reads the process fields before any failure is written, and gives a refused delivery its
own label — `write_not_delivered` rather than a `readiness_deadline` that had not elapsed. **R16/R17/R18**
grade all three. Full row: [[U379]], CLOSED.

The other findings acted on:

- **Leg H could not fail on the defect it names** (validator MAJOR-1 / auditor MAJOR-2, demonstrated:
  the validator spliced R12 back in — leg F reddened, leg H stayed green). Pane H's scrollback and
  current screen were the same trust line, so the gate and the window agreed by construction. Rebuilt
  so they disagree, and the leg now requires the disagreement.
- **Three false disclosure sentences.** "Every binding is the shell's own except the two named
  SIMULATED" undercounted itself — `operationState` (which feeds `last_successful_mcp_operation` in
  every structured failure these legs produce), both deadlines and `now`/`sleep`/`log` are the
  check's too. "What is seeded is stated in the receipt" was not true until it was. Leg C's header
  named pane A where the code reads pane B. The receipt now enumerates every check-owned binding and
  carries `seeded_launch_record` verbatim.
- **`lastLines` said "non-empty lines" and filters nothing.** The comment is made true; the behaviour
  question — blank-line padding can evict a live modal from the bound — is carried as [[U380]] rather
  than changed inside a review remediation, which is what [[U371]] was reverted for.
- **The header misquoted its own binding source.** `frontier_provider_recon.py:44-49` says "only on a
  NONZERO exit"; the header had "only when neither answers", presented as the quote. The quote is
  exact now and the extension to still-running processes is labelled as this module's.
- **Two sentences that read as global and were true only of this module**: the "connected worker's
  screen is never classified" summary (false inside a turn for a worker that has not yet answered),
  and "the gate's answer is now used for exactly what it is evidence of" — which is false of
  `main.js`'s conductor readiness path, where the same whole-buffer refusal still becomes the
  conductor's operational state. Recorded as [[U381]](a); that call site is outside this row and is
  now named rather than left to be inferred.

Record-only corrections from both reports — U375's stale line citations, U374's falsified G5 clause,
`8272f2c`'s "all four harnesses re-pinned" (three pin `main.js`), the checkpoint's "four receipts"
(five) — are [[U381]](b)–(e). Two accuracy notes left OPEN with an owner are U381(f). The
self-check's absence from every mutation harness's pin set is [[U382]].

**Verdicts in full:** gate-validator **FAIL** (1 BLOCKING, 1 MAJOR, 2 MEDIUM, 5 MINOR); spec-auditor
**PROHIBITED DRIFT: NONE** (1 BLOCKING, 3 MAJOR, 8 MEDIUM, 5 MINOR). The auditor confirmed
independently that the U328 gate is not weakened, that no authorization logic moved into
`mcp_server/`, and that every byte still passes `paneWriter.writePrompt`.

## 4. Exit-criterion self-check (real command output, all foreground, this iteration)

| Criterion (directive row 19.4) | Verdict | Evidence |
|---|---|---|
| Exit codes + structured signals before screen text | **MET** — and it was NOT met at round 2's start | R1/R2/R3 + **R16/R17** CAUGHT; receipt leg `exit_code_and_structured_signals_first` (`screen_reads_while_answerable_by_stronger_signals: 0`); three U379 tests |
| Window bounded by `sliceFrom()`, never `snapshot()` | **MET** for classification | R4–R7 CAUGHT; receipt leg `buried_overlay_is_not_current_state` — bounded verdict `null` where the whole-buffer read says `AUTH_REQUIRED` on the same live pane |
| `runWorkerReadiness` reordered | **MET** | R2 CAUGHT; `the MCP connection is consulted even when the screen would classify` |
| Every classified state has an exit path | **MET across polls and runs**; a withheld write and a dead process each have one now | R8 CAUGHT; `the overlay clears mid-run and the SAME run continues`; `U373 EXIT PATH`; U379's exit-code path |
| Negative control: healthy connected worker stays READY | **MET at module level, in two timing forms; NOT MET end-to-end**, and the in-Electron leg measures the gap rather than describing it | two negative-control tests + delayed-answer form (R13/R14 CAUGHT); receipt leg `withheld_write_is_not_a_provider_verdict` with `residual_u373_worker_stalls_though_connected: true` |

Measured on the final tree `14a3ad1`, sequentially, nothing concurrent:

- `apps/desktop` — `node --test test/*.test.js` → **921 pass / 0 fail** (907 at `a6166e7` + 11 at
  `8272f2c` + 3 at `14a3ad1`). Per [[U376]] this is a measurement **of this host**: the suite reads
  untracked host state, which is why the gate-validator's worktree measured 918 tests with **1
  failure** at `8272f2c` where this host measured 918 pass — the failing test is
  `conductor-source.test.js`, untouched by this unit, and the validator traced it to exactly that
  cause.
- `terminal` — **216 pass / 0 fail**
- `tools/mutation/readiness_signal_mutations.js` → **18/18 CAUGHT**, restore BYTE-IDENTICAL
- `tools/mutation/system_pane_write_mutations.js` → **25/25 CAUGHT**, all three files restored
  BYTE-IDENTICAL · `pane_input_bypass_mutations.js` → ALL CAUGHT · `orchestration_mutations.js` → 5/5
- D-P16-0 receipt, in the packaged Electron runtime, on `14a3ad1` with a clean tracked product tree:
  `docs/evidence/receipts/PHASE19_4_READINESS_WINDOW_SELFCHECK_phase-19.4.round2_20260810T184046Z.json`
  — `ok: true` on all **eight** legs, `live_exchanges: 0`, four panes killed in-unit (D-LOOP-1), no
  surviving Electron process (`remaining=-` from the launcher's own process inventory).

**The Python suite was not run, and the reason is not "it is slow":** no commit in this unit touches a
`.py` file. Unit 19.10 owns the full-suite run, the 600 s diagnosis and `pytest.ini` ([[U339]]).

## 5. Receipts, and which of them is the unit's

Seven `PHASE19_4_READINESS_WINDOW_SELFCHECK` receipts now exist. They are not seven measurements:
`135311Z` and `135343Z` are pre-commit runs by the turn that died before any review; `140454Z` and
`close_161427Z` are the same check at `716673d` (the second a re-run, because D-LOOP-2 makes a dead
turn's receipts CANDIDATE material); `round1_172223Z` is the round-1 remediated tree `a6166e7`;
`close_174627Z` is this iteration's run of the NEW legs at `8272f2c` — the tree the reviewers read,
and the one whose leg H they showed could not fail.
**`round2_184046Z` is this unit's D-P16-0 receipt** — the only one taken on a tree whose
check drives the readiness RUN, and the only one whose leg H can fail on the defect it names.

What it evidences and what it does not, in its own words: the production window, ordering function
and state machine, exercised against real ConPTY panes running `powershell.exe` printing text the
check chose — so no real provider screen is evidenced ([[U362]] unchanged), the classifier's coverage
is not evidenced ([[U363]]), and the byte bound has still never triggered in-Electron
(`bound_that_applied: "line_only"`, disclosed by the leg itself). The Sovereign MCP session state, the
tool-call count, `operationState`, both deadlines and `now`/`sleep`/`log` are the CHECK's, and the
pane's launch record is seeded; all of it is enumerated in `scope_note_readiness_run` and
`seeded_launch_record`.

## 6. What is owed before 19.4 can close

1. **Round 3 of BOTH mandatory reviewers, foreground and in-turn, sequential** (the validator writes
   mutations into a tree the auditor reads — [[U359]]), on `8272f2c` + `14a3ad1` + this report. The
   unit closes only when a round returns with nothing whose repair changes the tree.
2. Then the follow-on unit for **[[U373]]'s residual** — bounding the U328 gate's read — which is where
   [[U363]]'s verdict half and [[U380]] also become affordable.

Everything else this round found is in the register with an owner ([[U379]]–[[U383]]), not silently
carried.
