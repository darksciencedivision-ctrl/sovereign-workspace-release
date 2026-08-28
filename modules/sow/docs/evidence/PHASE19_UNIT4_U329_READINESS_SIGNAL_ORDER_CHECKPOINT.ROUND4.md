# Phase 19 · Unit 19.4 — U329, round 4: the prompt that no longer contains its own answer

**Status: CHECKPOINT — round 4 reviewed by both mandatory reviewers, remediated twice, D-P16-0 receipt
GREEN for the first time; round 5 owed (§7).** This document **supersedes §4 and §7**
of `PHASE19_UNIT4_U329_READINESS_SIGNAL_ORDER_CHECKPOINT.ROUND3.md` (which superseded §4/§6 of ROUND2,
which superseded the original). All four are left exactly as written — the evidence set is
append-only, and where an earlier one is now known to be wrong the correction is a register row, not
an edit ([[U386]](a)).

| | |
|---|---|
| Unit | `phase-19.4` (AUTONOMOUS_BUILD_DIRECTIVE.md §18, row 19.4 — U329) |
| Work commits this iteration | `b20355e` (U392, the validator's MAJOR) · `fedbc4e` (U393, the auditor's MAJOR + MINOR-4) |
| Earlier work commits | `716673d` · `a6166e7` (round-1 remediation, U373) · `8272f2c` (the in-Electron readiness RUN leg) · `14a3ad1` (round-2 remediation, U379) · `d2e096e` (U384) · `f4beb5f` (U386(g)) · `7ca74a9` (U385 + U386(b)/(d)/(e)/(f)) |
| Reviewers, round 4 | gate-validator **FAIL** (1 MAJOR) · spec-auditor **PROHIBITED DRIFT: NONE** (0 BLOCKING, 1 MAJOR, 1 MEDIUM, 4 MINOR) — foreground, in-turn, sequential ([[U359]]) |
| Tag | none — `gate/phase-19` is unit 19.10's, and `product/multi-frontier-v2` is never moved |
| Live provider calls | **0** |

---

## 1. The standing order, and what was done

Round 3's checkpoint left an ordered list: **fix [[U385]] first**, then [[U386]](b)–(f), then **round 4
of both mandatory reviewers**, foreground, in-turn, sequential ([[U359]]). This iteration executed that
list in that order.

**Reconciliation at entry — and the correction this document owes about itself.** `git tag -l` says
the latest gate tag is `gate/phase-18e` and the latest product tag `product/multi-frontier-v2`;
`LOOP_STATE.json` said `next_step: phase-19.4.u385-then-round4`. They **agree** — 19.4 has no tag and
claims none — so no reconciliation commit was owed.

The rest of the entry state was not what the two paragraphs above it were written to describe, and
they are corrected here rather than left standing. **HEAD was `7ca74a9`, a work commit LOOP_STATE did
not know about** (`last_commit: 11a9f22`, iteration 126), beside an uncommitted register edit, two
untracked receipts, and §1–§3 of this file. A prior turn fixed [[U385]] and [[U386]](b)/(d)/(e)/(f),
committed it, took two receipts, began this document — and **died before either reviewer ran**. Under
**D-LOOP-2** everything it left is CANDIDATE material: no review was in flight, because under
`claude -p` nothing survives a turn. So this iteration re-ran every suite, every harness and the
in-Electron receipt **fresh and foreground** before reviewing anything, and its predecessor's two
receipts are committed as what they are — measurements of `7ca74a9`, taken by a turn that did not
finish. Sentences in §1–§3 written in that turn's voice ("this iteration executed that list") describe
**its** work, which this one inherited, re-measured and then took further; where one of them says
something this iteration found to be false, the correction is here and in a register row, never an
edit ([[U386]](a)).

## 2. [[U385]] — the fix, and why it is a different KIND of fix

The defect: `readinessPrompt` asked the provider to *"reply exactly `SOVEREIGN_READY_1_msnmv8y5`"* and
the run promoted the worker on the **second** occurrence of that token, on the reasoning that the
first was the pane's echo of what we typed. A ConPTY resize repaints the screen and re-emits the same
line, so the echo supplies both occurrences and the pane never says anything.

The register recorded the direction and it is the one taken: **make the expected reply a string the
prompt cannot contain.** `readinessChallenge(nodeId, turn, stamp)` now returns two fragments —
`SOVEREIGN_READY_<turn>_<stamp>` and `SOVEREIGN_TAIL_<stamp>` — and the prompt **instructs in words**
that they be written joined, with nothing between them. The reply is composed, never quoted, so:

- no echo of the prompt contains it;
- no repaint of the prompt contains it, however many times the screen redraws;
- **one occurrence is proof**, and the threshold drops to `>= 1` because the reason for `>= 2` is gone.

`toolSucceeded` is unchanged: composing the answer without the `get_worker_status` call behind it is
still not readiness.

**Why raising the threshold was not an option**, stated because it is the obvious cheap fix and it is
wrong: the count is of a string the prompt itself carries, so a second repaint defeats `>= 3` exactly
as the first defeated `>= 2`. The new negative control repaints **four** times for that reason — it
fails any threshold-tuned variant, not just the shipped one.

**And a guard, fail-closed:** `waitForTurn` refuses to write at all if
`challenge.prompt.includes(challenge.expected)` (`readiness_challenge_unsound` /
`decided_by: challenge_unsound`). A readiness check that cannot distinguish an echo from an answer is
worse than no check, so it does not run. Both halves are graded — see §4.

**One thing this iteration found and did not invent:** the CONDUCTOR path never had this defect.
`conductor/roundtrip-probe.js` has since 17A refused to carry its own answer — operands spelled in
words so the prompt contains no digit, redrawn per run, absence from the pane asserted before submit.
The worker readiness path was the outlier. The two now share a *principle*; they still have separate
mechanisms, and nothing here merges them.

## 3. [[U386]](b)–(f) — the carried reviewer findings this unit owned

- **(b), the one with a behaviour change ([[U390]]).** A worker that died BEFORE a readiness turn was
  `FAILED`; one that died DURING a turn was `STALLED` — one physical condition, two renderings,
  separated by our own timing, with a test pinning the second as intended. `STALLED` reads *alive and
  unresponsive*. The turn's terminal state is now derived from the stage, so a process exit renders
  `FAILED` on both paths. The older test's load-bearing assertions (`decided_by: process_exit`, the
  exit code, and **not** the modal on screen) are untouched: what changed is the word, not the
  instrument.
- **(d)** Leg A compared a Buffer byte count with a UTF-16 code-unit count and derived
  `bound_that_applied` from it. Both are now bytes; `whole_buffer_chars_utf16` is published separately.
- **(e)** `scope_note_leg_d` now says that leg D's keystroke goes through the renderer's OPERATOR
  input channel rather than the gated system path, and why that weakens no gate.
- **(f)** `main.js`'s self-check ctx comment claimed the check supplies "its own MCP session state";
  it supplies six bindings and a seeded launch record. The comment now counts what the receipt counts.
- **(c) is deliberately NOT closed here.** `requiredTurns` keyed on the vendor name `"grok_build"` is
  unit **19.6**'s row (the descriptor generalization), which is where [[U386]](c) assigned it. Closing
  it here would be this unit doing another unit's work on a name-vs-descriptor question. Note carried
  forward: leg G uses `claude_code`, so the two-turn branch remains the one readiness path never
  exercised in-Electron.

Full rows: [[U389]], [[U390]], [[U391]].

## 4. Falsification — what would have to break for any of §2–§3 to be false

Every harness below ran foreground, sequentially, nothing concurrent; every product file was restored
**byte-identical** and the hash printed by the harness itself.

| Harness | Result |
|---|---|
| `readiness_signal_mutations.js` | **23/23 CAUGHT** (R19–R21 grade §2–§3; **R22–R23 are new, and are the round-4 MAJOR's graders**) |
| `system_pane_write_mutations.js` | **25/25 CAUGHT**, all three files byte-identical |
| `pane_input_bypass_mutations.js` | **ALL CAUGHT** |
| `orchestration_mutations.js` | **5/5 CAUGHT**, every file restored byte-identically |

**R22 and R23 exist because the gate-validator's round-4 probe found the falsification missing, not
weak.** It spliced two mutations into the *call site* — the challenge stamp frozen, and frozen with
the turn dropped, which makes **every readiness challenge in the process byte-identical** — and ran
the entire desktop suite against each. **Both survived, 928/928 green.** Neither shape existed in the
harness. The defect that hid behind that gap is [[U392]]: "one occurrence is the provider speaking" is
true of the prompt just typed and **false of an earlier run's answer**, which is still in the ring and
still on the visible screen, and which a repaint re-emits *after* the new run's mark. [[U385]] one
level up, defeated only by the accident that `io.now()` had moved.

The repair makes non-repetition structural (`challengeStamp` appends a process-incremented sequence to
the clock reading), and both new mutations were verified to redden **named** tests, spliced one at a
time by hand:

- **R22** (stamp frozen) → reddens `U385 round 4: an EARLIER run's answer, repainted into this run's
  window, is not this run's answer` — **and only that test**, `fail 1`.
- **R23** (sequence deleted, clock kept) → reddens `U385 round 4: the same instant, twice, still
  yields two different challenges`, `fail 2`.

**R23's second effect is recorded because it corrects this document's own first draft.** R23 also
reddens the behavioural test on this host — a readiness run returns when its pane answers rather than
when its deadline expires, so both runs fell inside one millisecond. That is **this host's timing, not
a property**, and it would go green on a slower one. The same-instant test is the grader that holds at
any speed, and both code comments were corrected to say what was measured rather than what was assumed.

## 5. Exit-criterion self-check (real command output, all foreground, this iteration)

| Criterion (directive row 19.4) | Verdict | Evidence |
|---|---|---|
| Exit codes + structured signals before screen text | **MET** | R1/R2/R3 + R16/R17/R18 CAUGHT; receipt leg `exit_code_and_structured_signals_first` green with `screen_reads_while_answerable_by_stronger_signals: 0` |
| Window bounded by `sliceFrom()`, never `snapshot()` | **MET** for classification | R4–R7 + R13/R14 CAUGHT; leg `buried_overlay_is_not_current_state` green — bounded verdict `null` where the whole-buffer read says `AUTH_REQUIRED` **on the same live pane**. The one unbounded read in the call graph is the U328 gate, deliberate and owned by [[U373]] |
| `runWorkerReadiness` reordered | **MET** | R2 CAUGHT; both reviewers re-confirmed no ordering remains in `main.js` |
| Every classified state has an exit path | **MET** | R8 CAUGHT; within-run, withheld-write and process-death exits each pinned; the auditor re-verified nothing caches a verdict across runs |
| Negative control: healthy connected worker stays READY | **MET at module level** (three forms, R12–R15 CAUGHT); **NOT MET end-to-end** — measured, not described: leg F carries `residual_u373_worker_stalls_though_connected: true` and reddens the day the gate's own read is bounded ([[U373]]) | unchanged from round 3; both reviewers re-graded it MET-WITH-LIMIT and neither asked for it to be softened |
| **The unit's own D-P16-0 receipt is green** | **MET** — the first round in which it is | `round4-final_223425Z`, commit `fedbc4e`, `tracked_product_tree_clean: true`, all **eight** legs `ok`, `live_exchanges: 0` |
| **Both mandatory reviewers return with nothing whose repair changes the tree** | **NOT MET** — each returned a MAJOR whose repair changed it | §6; this is why the unit checkpoints instead of closing |

Measured on the final tree (`fedbc4e`), sequentially:

- `apps/desktop` — `node --test test/*.test.js` → **930 pass / 0 fail** (928 at `7ca74a9` + 2 at `b20355e`)
- `terminal` — `node --test test/*.test.js` → **216 pass / 0 fail**
- the four harnesses as tabled in §4
- **five in-Electron runs this iteration** (three by this builder, one by the gate-validator, one after
  each remediation), every one with all four panes killed in-unit (**D-LOOP-1**), `live_exchanges: 0`,
  and no surviving `electron.exe` — `tasklist` reports **0**, and the launcher's own inventory reports
  `remaining=-` on every run

**The Python suite was not run, and the reason is not "it is slow":** no commit in this unit touches a
`.py` file. Unit 19.10 owns the full-suite run, the 600 s diagnosis and `pytest.ini` ([[U339]]).

**The strongest single measurement this round produced** is not a test. Across five in-Electron runs
the pane's echo of our own prompt was counted **2, 3, 2, 3, 3** while the answer count stayed **1**
every time. The repaint that produced round 3's false READY is still happening on this host, run to
run, in a quantity nobody controls — and it no longer counts as an answer. Under the pre-U385 rule,
**every one of those five runs would have promoted a silent pane.**

## 6. The reviewers

Both ran **foreground, in-turn, and SEQUENTIAL** ([[U359]]: the validator writes mutations into the
working tree and the auditor reads that tree; 19.2's round 3 caught a validator's widening *sitting in
the tree* while the auditor read it). The validator ran first, on `7ca74a9`; the auditor ran after its
MAJOR was repaired, on `b20355e`.

**gate-validator — FAIL, 1 MAJOR + 1 MEDIUM + 4 MINOR.** It independently reproduced the suites
(928/0, 216/0), the harness (21/21, byte-identical restores), and took **its own** in-Electron receipt
(`validator-r4_214956Z`, green). It wrote 12 of its own mutations — 9 caught, **2 survived**, one
no-op control — and the two survivors are [[U392]], repaired at `b20355e` and graded by R22/R23. Its
answer to the question this unit actually turns on is worth quoting as a measurement: leg G's echo
count was **3** in its run against **2** in the builder's — "the repaint count is nondeterministic
run-to-run while the answer count is pinned at 1".

**spec-auditor — PROHIBITED DRIFT: NONE**, 0 BLOCKING, 1 MAJOR, 1 MEDIUM, 4 MINOR, and its own
explicit answer: *"Does anything I found require a code-behaviour change before this unit closes?
No."* Every finding was a claim-vs-evidence mismatch. It re-verified that the U328 gate is not
weakened, bypassed or widened (invariant 1 / D-P18-13), that the self-check's panes are supervised
(invariant 2), that no structured failure can contradict itself (invariants 16/27), and that nothing
under `mcp_server/` was touched (invariant 7). It also recorded its own verification limit up front —
no shell, so git-level facts were checked only as far as file contents permit.

Its **MAJOR-1 was repaired in the tree rather than footnoted**, because this is the third time this
unit has been told the same thing ([[U384]], [[U386]](g)) and the first two were repaired in the bytes:
`worker-readiness.js` asserted an **absolute** — "no echo and no repaint of the prompt can contain the
joined string" — that [[U392]]'s own register row had already retracted. `plainScreen` **deletes**
CSI/OSC sequences without substitution where it replaces C0 controls with a space, so a *differential*
repaint re-emitting `head`, cursor addressing and `tail` while skipping the 39 instruction characters
between them would normalize to the joined string. Never observed here; defended in production not by
the screen at all but by `toolSucceeded`, a real `get_worker_status` count no repaint can fabricate.
Four comments now say exactly that.

Its **MINOR-4 was U384's finding again at lower amplitude, and also repaired**: the receipt's headline
sentence is *generated* from `CHECK_OWNED_BINDINGS.length` precisely so it cannot go stale by hand —
and the list collapsed `now/sleep/log` into one entry, so a sentence whose entire purpose is to count
what it counts said **six** where **eight** bindings are the check's. One entry per binding now; the
test pins 8 **and** refuses any entry containing a `/`; and `operationCount` discloses the simulation
it is (a tool call counted on prompt *delivery*), so a reader of the receipt alone can now separate leg
G's measured half from its simulated half.

**Two findings corrected [[U392]]'s row before it was ever committed**, and both are recorded as
corrections rather than quietly reworded: the same-millisecond collision is **not** reachable on one
pane in production (a 500 ms paste settle separates the turns), and readiness re-runs on the
conductor's duplicate-worker branch rather than "any pane that is not READY". **MINOR-1** — three
further vendor-name branches in the same call graph (`provider-readiness.js:32/:37/:41`,
`pane-writer.js:237`) — is carried to **19.6**, so that unit's descriptor generalization does not stop
at the one branch [[U386]](c) named. **MINOR-2** (the counter is neither injected nor factory-scoped)
is recorded and deliberately **not** fixed: it fails closed, and scoping it after a review round would
be a behaviour change smuggled into a remediation.

Full rows: [[U392]], [[U393]].

## 7. Disposition

**Status: CHECKPOINT — unit 19.4 does NOT close on round 4.** It is checkpointed a fourth time, and the
reason is the closure condition itself, not a defect left standing.

ROUND3 §7 requires a round in which **both** mandatory reviewers return with nothing whose repair
changes the tree, **and** the D-P16-0 receipt is green. This round:

- the receipt half is **MET for the first time** — `round4-final_223425Z`, green, eight legs, on the
  committed tree it describes;
- the reviewer half is **NOT MET** — each reviewer returned a MAJOR, both were repaired, and
  **fix-after-validation voids the round that found them**. The validator reviewed `7ca74a9`; the
  auditor reviewed `b20355e`; the tree is now `fedbc4e`. **No reviewer has yet seen the tree the green
  receipt was taken on.** The auditor said so itself, unprompted, and ranked it above its own findings.

**Owed, and it is the next unit's first act: ROUND 5 of both mandatory reviewers, foreground, in-turn,
sequential, over `b20355e` + `fedbc4e` + this report.** Nothing else is owed by this unit — [[U385]],
[[U386]](b)/(d)/(e)/(f), [[U392]] and [[U393]] are closed with graded falsification, and the receipt is
green.

What this iteration deliberately did **not** do, so no reader infers it: it did not run round 5 itself.
Two full reviewer passes and two remediations had already run in this turn, and a third pass over a
tree this turn had just changed would have been a review of work its own author finished minutes
earlier. The split the directive prescribes (**D-LOOP-2**) is a WIP checkpoint with the remainder
recorded, which is what this is.

Carried forward unchanged, none of it this unit's: [[U373]]'s residual (the U328 gate's own unbounded
read — the follow-on unit, with [[U363]]'s verdict half and [[U380]]); [[U386]](c) and [[U393]]'s
MINOR-1 (name-vs-descriptor) to **19.6**; [[U387]] (a stale worktree outside the repo root, which
prohibition §2.5 forbids this loop from deleting) recorded for the operator, not carried as work.
