# Phase 19 · Unit 19.4 — U329, round 3: two clean reviewers, and the red receipt that outranked them

**Status: CHECKPOINT — NOT CLOSED.** This document **supersedes §4 and §6** of
`PHASE19_UNIT4_U329_READINESS_SIGNAL_ORDER_CHECKPOINT.ROUND2.md` (which itself superseded §4/§6 of the
original checkpoint). All three are left exactly as written — the evidence set is append-only, and
where an earlier one is now known to be wrong the correction is a register row, not an edit
([[U386]](a)).

| | |
|---|---|
| Unit | `phase-19.4` (AUTONOMOUS_BUILD_DIRECTIVE.md §18, row 19.4 — U329) |
| Work commits this iteration | `d2e096e` (U384 — the disclosure repair) · `f4beb5f` (U386(g) — the wiring header's false grading claim) |
| Earlier work commits | `716673d` · `a6166e7` (round-1 remediation, U373) · `8272f2c` (the in-Electron readiness RUN leg) · `14a3ad1` (round-2 remediation, U379) |
| Reviewers, round 3 | gate-validator (isolated worktree) **PASS**, 0 BLOCKING/MAJOR/MEDIUM, 3 MINOR · spec-auditor (read-only, primary tree) **PROHIBITED DRIFT: NONE**, 0 BLOCKING, 2 MAJOR, 2 MEDIUM, 3 MINOR |
| Tag | none — `gate/phase-19` is unit 19.10's, and `product/multi-frontier-v2` is never moved |
| Live provider calls | **0** |

---

## 1. What this iteration was for, and what it found

The standing order from round 2 was a single act: **round 3 of both mandatory reviewers**, foreground,
in-turn, sequential (the validator writes mutations into a tree the auditor reads — [[U359]]), on
`8272f2c` + `14a3ad1` + the round-2 report. It ran exactly that, and then followed where it led.

Round 3 is the first round in which **no reviewer found a BLOCKING defect**. It is also the round in
which the unit failed, for a reason no reviewer raised: **the D-P16-0 receipt, taken on the repaired
tree, came back RED.** The reviewers read the code and the record; the runtime answered a question
neither of them asked, and its answer is [[U385]].

## 2. The reviewers

**gate-validator — PASS.** Worked in an isolated worktree, re-ran both suites and all four mutation
harnesses itself, and re-ran the two experiments round 2 left as open questions: it spliced R16/R17/R18
individually and confirmed each reddens exactly the one test naming its defect, and it re-ran the
leg-H experiment that round 2 had used to demonstrate the leg could not fail — this time splicing R12
reddened **both** leg F and leg H, so the round-2 rebuild is real. It verified the U379 repair on disk
(`worker-readiness.js:318` is the first statement of every withheld-write poll; `:485` re-reads before
any structured failure) and traced the process signal to production (`picker/worker-spawn.js:550`). It
reported the primary tree clean and stated explicitly that **no repair was required for closure**.

Its three MINOR items are recorded as [[U386]](a), [[U386]](g) and — the one it shares with the
auditor — the seeded-record disclosure, closed here as part of [[U384]].

**spec-auditor — PROHIBITED DRIFT: NONE.** Confirmed independently: the U328 gate is not weakened,
narrowed or bypassed by the bounded-window path; nothing spawns outside the supervised path; no file
under `mcp_server/` was touched, so invariant 7 is untouched by this unit; no record this code emits
can still contradict itself (the U379 class); registers append-only; canonical set frozen; no tag
created or moved; `live_exchanges: 0`.

Its two MAJORs were **verified on disk before being acted on**, and both were real — §3.

## 3. What was repaired, and why it had to be (`d2e096e`, `f4beb5f`)

**The disclosure repair had reached the scope note and stopped there.** Round 2 recorded "three false
disclosure sentences" as fixed. The receipt's headline `finding` still ended *"so those two bindings
are simulated and everything else is the shipped object"* while six bindings and a seeded launch
record were the check's own — the same undercount, one field away from its own correction, in the field
a reader reads first. And `seeded_launch_record` published seven constant fields while `driveReadiness`
seeded eleven: `nodeId`, and a `chrome` whose `provider` and `model_slug` become the `provider` and
`model` of **every structured failure legs F/G/H produce**. The complete object was computed, returned,
and read by nothing; the test pinned the seven-key list as correct, which is why round 2 passed over it.

Both are now structural rather than editorial. `CHECK_OWNED_BINDINGS` is the single list; the headline
sentence is **generated from it** and states its count, so the sentence cannot disagree with the note
again without the list itself being wrong. The per-pane seeded record is published **by the function
that seeds it**, so a future leg cannot add a field the receipt does not disclose. Full row: [[U384]].

Falsification, which is the only reason to believe any of it: both new tests were shown to go red on
the exact defect they name — the old sentence spliced back in reddens the headline test; suppressing
the per-pane publication reddens the seeded-record test — with the file restored **BYTE-IDENTICAL**
(SHA-256 `51A3F2B4…DA0F8`) after each splice.

`f4beb5f` corrects a source comment that claimed a mutation grading it does not have ([[U386]](g)).

**This alone means round 3 does not close the unit**: the repairs changed the tree, and directive §18's
*fix-after-validation voids it* applies. It is not, however, the more serious finding.

## 4. [[U385]] — the receipt that only a real run could redden

With the repairs committed, the D-P16-0 check was re-run in the packaged Electron runtime on a clean
tracked product tree. **Seven of eight legs green; leg G red**, and it stayed red on a second run.

Leg G is the unit's **positive** control: a clean pane is written to and the run reaches READY on an
answer this runtime measured. What the receipt recorded was a run that reached `READY`
(`ready: true`, `readiness_responses: 1`, one prompt delivered) **on a pane that had not answered** —
`answer_marks_on_the_real_pane: 0`.

The mechanism was then captured in the pane's own bytes, with a temporary diagnostic (not committed;
file restored byte-identical afterwards, and the resulting receipt self-discloses
`tracked_product_tree_clean: false`):

```
… Readiness check only. … reply exactly SOVEREIGN_READY_1_msnmv8y5. …    ← the pane echoes our prompt
ESC[8;7;65t ESC[H  SOVEREIGN_U329_PANE_READY ESC[K                        ← a RESIZE, then a REPAINT
… Readiness check only. … reply exactly SOVEREIGN_READY_1_msnmv8y5. …    ← the SAME line, re-emitted
```

Token occurrences in the whole buffer: **2**. `SOVEREIGN_U329_ANSWER` occurrences: **0**.

`worker-readiness.js:373` promotes on `toolSucceeded && echoes >= 2`, reasoning that "one occurrence is
the pane's echo of the prompt; the second is the provider's answer". On a real ConPTY a resize repaints
the screen, and the echo alone supplies both occurrences. **This is U329's own subject matter turned on
the positive control**: the unit exists because screen text was consulted ahead of stronger signals, and
here a screen-*derived* count is trusted as though it were the provider speaking.

Bounded honestly: in **production** `operationCount` is the real count of `get_worker_status` MCP tool
calls, and a repaint cannot fabricate a tool call, so production promotion still requires a genuine
structured signal — this degrades a defence-in-depth confirmation rather than promoting a silent worker
on its own. In the **self-check** `operationCount` is simulated (disclosed: it counts prompt delivery),
so leg G rests entirely on the echo count. **The leg is working; the verdict it graded is what is wrong.**

Two things had to be established before this could be written down as a defect rather than a symptom:

1. **It is not the U384 repair.** An A/B control restored the pre-repair file and ran the check again:
   it failed identically (`ab-pre-repair_193555Z`).
2. **It is not a flake.** Reproduced 3/3. But it is timing-dependent in the other direction, and that
   is the uncomfortable part: `round2_184046Z` and `close_174627Z` recorded
   `answer_marks_on_the_real_pane: 2` on identical code. **Round 2's green was the resize landing
   early, not evidence.** A green contingent on when a repaint arrives is exactly the kind this unit
   may not accept, and it went unnoticed because the leg passed.

The fix is the next unit's first act and needs its own review round. Its direction is recorded in
[[U385]]: make the expected answer a string the prompt itself cannot contain, so no echo or repaint of
the instruction can satisfy it. Raising the threshold is not a fix — a second repaint defeats `>= 3`
exactly as the first defeated `>= 2`.

## 5. Exit-criterion self-check (real command output, all foreground, this iteration)

| Criterion (directive row 19.4) | Verdict | Evidence |
|---|---|---|
| Exit codes + structured signals before screen text | **MET** | R1/R2/R3 + R16/R17/R18 CAUGHT (re-run this iteration, and re-run independently by the validator, which spliced R16–R18 one at a time and named the single test each reddens); receipt leg `exit_code_and_structured_signals_first`, `screen_reads_while_answerable_by_stronger_signals: 0` |
| Window bounded by `sliceFrom()`, never `snapshot()` | **MET** for classification | R4–R7 CAUGHT; receipt leg `buried_overlay_is_not_current_state` green in all three runs — bounded verdict `null` where the whole-buffer read says `AUTH_REQUIRED` on the same live pane. The one unbounded read in the call graph is the U328 gate, deliberate and owned by [[U373]] |
| `runWorkerReadiness` reordered | **MET** | R2 CAUGHT; validator confirmed no ordering remains in `main.js` (`:2337-2356` is binding only) and that a connected worker with a modal on screen reaches READY with `classificationReads === 0` |
| Every classified state has an exit path | **MET** | R8 CAUGHT; within-run, withheld-write and process-death exits each pinned by a test; validator confirmed nothing caches a verdict across runs |
| Negative control: healthy connected worker stays READY | **MET at module level** (three forms, R12–R15 CAUGHT); **NOT MET end-to-end**, measured not described — receipt leg F carries `residual_u373_worker_stalls_though_connected: true` and goes red the day the gate is bounded ([[U373]]) | validator graded this MET-WITH-LIMIT and recorded the shortfall in plain words; the register says the same |
| **The unit's own D-P16-0 receipt is green** | **NOT MET** — leg G red, [[U385]] | `round3_193358Z`, `round3-rerun_193502Z` |

Measured on the final tree, sequentially, nothing concurrent:

- `apps/desktop` — `node --test test/*.test.js` → **923 pass / 0 fail** (921 at `14a3ad1` + 2 at
  `d2e096e`). Per [[U376]] this is a measurement **of this host**; the validator's fresh worktree
  measured 1 failure in `conductor-source.test.js`, which it traced to that same untracked-host-state
  cause and re-ran alone in the primary tree to 14/14 pass.
- `terminal` — **216 pass / 0 fail**
- `readiness_signal_mutations.js` → **18/18 CAUGHT**, restore BYTE-IDENTICAL ·
  `system_pane_write_mutations.js` → **25/25 CAUGHT**, all three files BYTE-IDENTICAL ·
  `pane_input_bypass_mutations.js` → ALL CAUGHT · `orchestration_mutations.js` → **5/5**
- Four in-Electron runs this iteration, every one with all four panes killed in-unit (D-LOOP-1),
  `live_exchanges: 0`, and no surviving Electron process (`tasklist` reports none; the launcher's own
  inventory reports `remaining=-`).

**The Python suite was not run, and the reason is not "it is slow":** no commit in this unit touches a
`.py` file. Unit 19.10 owns the full-suite run, the 600 s diagnosis and `pytest.ini` ([[U339]]).

## 6. The receipts this iteration produced, and what each one is

Four, none of them a pass, all committed as what they are:

| Receipt | Tree | What it is |
|---|---|---|
| `round3_193358Z` | `d2e096e`, clean | The unit's D-P16-0 attempt on the repaired tree. **RED**, leg G |
| `round3-rerun_193502Z` | `d2e096e`, clean | The same, again — establishing [[U385]] is not a flake |
| `ab-pre-repair_193555Z` | `d2e096e` with the pre-repair self-check restored; `tracked_product_tree_clean: false`, self-disclosed | The A/B control proving [[U385]] predates the U384 repair |
| `diag_193721Z` | same, plus an **uncommitted** temporary diagnostic; `tracked_product_tree_clean: false` | The raw pane buffer that names the mechanism. **Produced by code that is not in the tree** — it is diagnostic evidence, not a measurement of the shipped check. Its shell hung on exit and was hard-killed by the launcher; no process survived |

The last two are worth stating twice: **neither was taken on the shipped tree**, both say so in their
own `source` block, and neither may be read as evidence about the product.

## 7. What is owed before 19.4 can close

1. **[[U385]] first** — the false READY. It is in row 19.4's own subject matter and the unit cannot
   close over a red positive control.
2. **[[U386]](b)–(f)** — the carried reviewer findings this unit owns: the FAILED/STALLED divergence
   for a death before vs during a turn, the bytes-vs-characters comparison in leg A, leg D's use of the
   operator input channel, and `main.js`'s stale comment.
3. **Then round 4 of BOTH mandatory reviewers**, foreground, in-turn, sequential, over `d2e096e` +
   `f4beb5f` + the U385 fix + this report. The unit closes only when a round returns with nothing whose
   repair changes the tree **and** the D-P16-0 receipt is green.
4. Then the follow-on unit for [[U373]]'s residual — bounding the U328 gate's read — where [[U363]]'s
   verdict half and [[U380]] become affordable.

[[U387]] (a stale worktree outside the repo root, which prohibition §2.5 forbids this loop from
deleting) is recorded for the operator, not carried as work.
