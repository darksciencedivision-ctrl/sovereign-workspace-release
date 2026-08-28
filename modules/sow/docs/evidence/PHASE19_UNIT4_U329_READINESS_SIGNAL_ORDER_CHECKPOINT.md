# Phase 19 · Unit 19.4 — U329: exit codes first, a bounded window, and the negative control

**Status: CHECKPOINT — NOT CLOSED.** Round 1 of the two mandatory reviewers ran in the foreground
this iteration and returned findings whose repair changed the tree; directive §18's
*fix-after-validation voids it* therefore applies, and **round 2 of both reviewers is the next unit's
first act**, exactly as 19.2's round 5 and 19.3's round 2 were.

| | |
|---|---|
| Unit | `phase-19.4` (AUTONOMOUS_BUILD_DIRECTIVE.md §18, row 19.4 — U329) |
| Work commits | `716673d` (the order, the window, the extraction) · `a6166e7` (round-1 review remediation — U373) |
| Reviewers | gate-validator (isolated git worktree) **FAIL**, 1 BLOCKING · spec-auditor (read-only, primary tree) **PROHIBITED DRIFT: NONE**, 1 BLOCKING |
| Tag | none — `gate/phase-19` is unit 19.10's, and `product/multi-frontier-v2` is never moved |
| Live provider calls | **0** |

---

## 1. What the unit was asked for, and what it did

The directive's row is quoted in full in the register's [[U378]] disposition. Five requirements:
exit codes and structured signals before any screen text; a window bounded by
`RingBuffer.sliceFrom()` rather than `buffer.snapshot()`; `runWorkerReadiness` reordered so the MCP
check is not short-circuited; an exit path for every classified state; and the negative control that
did not exist — *a healthy, connected, exit-0 worker whose transcript merely mentions "usage limit"
or "not signed in" stays READY*.

The readiness state machine left `main.js` for `apps/desktop/control/worker-readiness.js`, where it
can be required and driven (U338's shape, applied where this unit was already working). The order is
one pure function, `orderedProviderSignal`; the window is `createScreenWindow`, whose reads are the
pane's tail and whose unanswerable case is carried as `answerable: false` rather than widened.

## 2. The round-1 finding, which is the reason this is a checkpoint

**Both mandatory reviewers found the same defect independently**, each with its own probe and its own
spellings, and it was re-verified on disk before either report was acted on (a reviewer's finding is
evidence, not a verdict — 19.3's lesson).

`waitForTurn`'s first act was `io.writeRefusal(paneId)`. That binding is the U328 write gate, and the
gate reads `buffer.snapshot()` — the whole 256 KB scrollback — because a modal it fails to see is a
modal the loop might answer. The module returned that refusal as `{stage: "provider_setup"}`, and
`run()` made it the node's terminal state, labelled `decided_by: "screen_text_bounded_window"`: an
instrument that had read nothing. So **the audited pin survived the reorder built to remove it** — a
healthy, connected worker whose transcript merely MENTIONED an auth failure was reported
`AUTH_REQUIRED`, across runs. The unit test named for that scenario passed because the harness
stubbed `writeRefusal` to null.

The second finding of the same class: the in-turn wait classified the unfloored tail on every poll,
so a worker taking longer than two polls to answer — every real CLI — could be classified by a
mention twenty lines up its transcript.

### What `a6166e7` fixes

- The gate's answer means only *we may not type here yet*. A refusal is **waited on**; one that
  clears lets the SAME turn go on to write; one that never clears is `readiness_prompt_withheld` /
  `decided_by: "write_gate_withheld"`, carrying the gate's own words. No provider verdict is read off
  a scrollback, and no `decided_by` names an instrument that did not read.
- While a write is withheld, the **bounded** window still gets its vote on what is actually wrong.
- The in-turn classification window is floored at the turn's own mark: what the provider draws in
  answer to our prompt lands after it, and a mention before it is transcript, not answer. `notBefore`
  narrows and cannot widen (mutation R14).
- Three observability repairs the reviewers named: the injected logger was dead; the
  `mcp_readiness_timeout` failure dropped the unanswerable-window reason its sibling path keeps; the
  receipt's `finding` claimed a readiness run it does not drive, and a comment claimed the product
  path no longer calls `snapshot()` — which `pane-writer.js` does.

### What it does NOT fix — stated here, asserted in the test, and open in the register as U373

While the GATE's own read is unbounded, that healthy worker's prompt is **undeliverable**, so it
stalls. The pin is honest, not gone. **OP-13.1's stated rationale for sequencing this unit ahead of
Path A — "U329 can pin a healthy worker as permanently blocked" — is therefore only partly
discharged.** Bounding the U328 gate's window is [[U363]]'s other half; it loosens an invariant-1
gate closed at a high-stakes review, interacts with the U360/U364 own-echo machinery, and needs its
own falsification and its own in-Electron receipt. It is a unit, not a remainder — rushing it into a
review remediation is exactly what [[U371]] was reverted for.

`worker-readiness.test.js` asserts `ready === false` **with the reason in the assertion message**, so
a green suite cannot be mistaken for a passing end-to-end negative control, and the test goes red the
moment the gate reads a bounded window.

## 3. Exit-criterion self-check (real command output, all foreground, this iteration)

| Criterion (directive row 19.4) | Verdict | Evidence |
|---|---|---|
| Exit codes + structured signals before screen text | **MET** in the readiness path | `orderedProviderSignal`; R1/R2/R3 CAUGHT; receipt leg `exit_code_and_structured_signals_first` — `screen_reads_while_answerable_by_stronger_signals: 0` |
| Window bounded by `sliceFrom()`, never `snapshot()` | **MET** for classification | R4/R5/R6/R7 CAUGHT; receipt leg `buried_overlay_is_not_current_state` — bounded verdict `null` where the whole-buffer read says `AUTH_REQUIRED` on the same live pane |
| `runWorkerReadiness` reordered | **MET** | R2 CAUGHT; `the MCP connection is consulted even when the screen would classify` |
| Every classified state has an exit path | **MET across polls and runs**; a withheld write now has one too | R8 CAUGHT; `the overlay clears mid-run and the SAME run continues`; `U373 EXIT PATH` |
| Negative control: healthy connected worker stays READY | **MET at module level, in two timing forms; NOT MET end-to-end** | two negative-control tests + delayed-answer form (R13/R14 CAUGHT); the production-write-gate test records the residual as U373 |
| Also owned: U371 | **CLOSED** (`716673d`), with a test debt recorded in U375(c) | `intervalMs` parses rather than coerces |

Measured on the final tree `a6166e7`, sequentially, nothing concurrent:

- `apps/desktop` — `node --test test/*.test.js` → **907 pass / 0 fail** (64 s)
- `terminal` — `node --test test/*.test.js` → **216 pass / 0 fail**
- `tools/mutation/readiness_signal_mutations.js` → **15/15 CAUGHT**, restore BYTE-IDENTICAL
- `tools/mutation/system_pane_write_mutations.js` → **25/25 CAUGHT**, all three files restored BYTE-IDENTICAL (M4/M6 re-anchored to the new gate loop and re-read against the new bytes)
- `tools/mutation/pane_input_bypass_mutations.js` → ALL CAUGHT · `orchestration_mutations.js` → **5/5**
- D-P16-0 receipt, in the packaged Electron runtime, on `a6166e7` with a clean tracked product tree:
  `docs/evidence/receipts/PHASE19_4_READINESS_WINDOW_SELFCHECK_phase-19.4.round1_20260810T172223Z.json`
  — `ok: true` on all five legs, `live_exchanges: 0`, both panes killed in-unit (D-LOOP-1), no
  surviving Electron process.

**The Python suite was not run, and the reason is not "it is slow":** no commit in this unit touches
a `.py` file (`git show --stat 716673d a6166e7`). Unit 19.10 owns the full-suite run, the 600 s
diagnosis and `pytest.ini` (U339).

## 4. Receipts, and which of them are measurements

Four `PHASE19_4_READINESS_WINDOW_SELFCHECK` receipts are committed with this unit. They are not four
measurements and must not be read as such:

- `..._phase-19.4_20260810T135311Z` and `..._135343Z` — taken by the **prior turn that died before
  any review**, at commit `d11c276`, with `tracked_product_tree_clean: false` and the then-new files
  listed as unexpected untracked. Honest about themselves, **pre-commit**, and evidence of nothing
  except that the check ran.
- `..._phase-19.4_20260810T140454Z` — that turn's post-commit run at `716673d`, clean tree.
- `..._phase-19.4.close_20260810T161427Z` — this iteration's fresh re-run at `716673d`, clean tree.
  Its legs are byte-identical to the previous one; it is a **re-run**, taken because D-LOOP-2 makes a
  dead turn's receipts CANDIDATE material, not a new fact.
- `..._phase-19.4.round1_20260810T172223Z` — the only receipt taken on the remediated tree
  (`a6166e7`). **This is the unit's D-P16-0 receipt.**

What the receipt evidences and what it does not, in its own `finding` field after this unit corrected
it: the production **window instance** and the production **ordering function**, exercised against
real ConPTY panes. `createWorkerReadiness.run()` is **not** driven inside Electron by this check, so
the state machine around those two parts — including the U373 remediation — is evidenced by the
headless suite only. An in-Electron leg that drives the readiness run through the production write
gate is **owed** and is named in §6. The panes are `powershell.exe` printing text this check chose,
so no real provider screen is evidenced (U362 unchanged), and the byte bound has never been
triggered in-Electron (`bounded_window_bytes == whole_buffer_bytes`, disclosed by the leg itself).

## 5. Register rows written this unit

Append-only, 156 insertions / 0 deletions, in one commit: **U372** (a byte/line window is not a
terminal emulator), **U373** (the unfinished half of U329 — the gate's unbounded read), **U374** (four
adjacent mutations the validator demonstrated surviving all 901 tests, plus an unpinned `decided_by`),
**U375** (three defects this unit relocated — U337's literal booleans, the `grok_build` `requiredTurns`
name pin that no unit owned, U371's source-string grading — and the eight-constant scope note),
**U376** (the desktop suite is not hermetic, so "907 pass" is a measurement of this host),
**U377** (CLOSED — the harness wrapper that dropped its options argument and graded every mutation
against an already-red target), **U378** (the dispositions for U329 and U371, since rows above are
never edited in place).

Nothing in `docs/canonical/` or `schemas/` was touched; `config/live_operation.json` is untracked and
untouched; no tag was created or moved.

## 6. What is owed before 19.4 can close

1. **Round 2 of BOTH mandatory reviewers, foreground and in-turn, on `a6166e7` + this report** — the
   remediation post-dates round 1. 19.4 closes only when a round returns with nothing whose repair
   changes the tree. Run them **sequentially**, not concurrently: the validator writes mutations into
   a tree the auditor reads (U359, and 19.2's round 3 caught a widening sitting in the tree
   mid-review).
2. **An in-Electron leg that drives `createWorkerReadiness.run()`** through the production write-gate
   binding, so the U373 remediation has a D-P16-0 receipt of its own rather than headless tests plus a
   window receipt.
3. Then the follow-on unit for **U373's residual** — bounding the U328 gate's read — which is where
   U363's verdict half also becomes affordable.

Everything else this round found is recorded in the register with an owner, not silently carried.
