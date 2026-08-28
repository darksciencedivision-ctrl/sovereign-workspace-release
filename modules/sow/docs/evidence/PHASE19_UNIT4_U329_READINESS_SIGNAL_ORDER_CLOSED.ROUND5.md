# Phase 19 · Unit 19.4 — U329, round 5: the round that changed nothing

**Status: CLOSED.** Round 5 ran both mandatory reviewers, foreground, in-turn, sequential ([[U359]]),
over `fedbc4e` — the tree the unit's first green D-P16-0 receipt was taken on — and **neither
returned a finding whose repair moves the product tree.** That was the one condition ROUND3 §7 and
ROUND4 §7 left standing, and it is the only way a unit whose last four rounds each ended in a repair
could ever close.

This document **supersedes §7 of `PHASE19_UNIT4_U329_READINESS_SIGNAL_ORDER_CHECKPOINT.ROUND4.md`**
(which superseded §4/§7 of ROUND3, which superseded §4/§6 of ROUND2, which superseded the original).
All five files are left exactly as written — the evidence set is append-only, and where an earlier
one is now known to be wrong, the correction is a register row and a paragraph here, never an edit
([[U386]](a), [[U394]]).

| | |
|---|---|
| Unit | `phase-19.4` (AUTONOMOUS_BUILD_DIRECTIVE.md §18, row 19.4 — U329) |
| Work commits this iteration | **none — no product file changed, which is the point** |
| Bookkeeping commits | register + this report · `LOOP_STATE.json` |
| Tree reviewed | `fedbc4e`; working tree at HEAD `7b464dd` byte-identical in every product path |
| Reviewers, round 5 | gate-validator **PASS** · spec-auditor **PROHIBITED DRIFT: NONE** — both foreground, in-turn, sequential ([[U359]]) |
| Tag | **none** — `gate/phase-19` is unit 19.10's, `product/multi-frontier-v2` is never moved |
| Live provider calls | **0** (0 for the whole unit) |
| Register | [[U394]], append-only: 140 insertions, 0 deletions |

---

## 1. Reconciliation at entry

`git tag -l` says the newest gate tag is `gate/phase-18e` and the newest product tag
`product/multi-frontier-v2`; `LOOP_STATE.json` said `next_step: phase-19.4.round5`. They **agree** —
unit 19.4 has no tag and claims none — so **no reconciliation commit was owed**.

HEAD was `7b464dd`, the state-writing commit of iteration 127, and `git status --porcelain` was
**empty**. So no prior turn died mid-unit and this one inherited nobody's re-runs. Under **D-LOOP-2**
that matters concretely: nothing from iteration 127 was "in flight" — reviews do not survive a turn —
so round 5 is a genuine first look at `fedbc4e` by both reviewers, not a continuation.

## 2. What round 5 was, and why the tree not moving is the result

The unit's exit condition, set at round 3 and restated at round 4: **a round in which both mandatory
reviewers return with nothing whose repair changes the tree, taken on the tree the receipt describes.**
Rounds 1–4 each failed it the same way — a reviewer found something real, it was repaired, and
*fix-after-validation* voided the round that found it. Round 4 ended with a green receipt at `fedbc4e`
that **no reviewer had seen**, because the two repairs that produced `fedbc4e` came after both passes.

Round 5 closed that gap and nothing else. **No code was written this round.** The receipt was not
re-run, and none was owed: `git diff --stat fedbc4e HEAD -- apps terminal tools node_runtime adapters
voice_bridge control_plane mcp_server schemas docs/canonical` is **empty**, so
`round4-final_223425Z` describes exactly these bytes. Re-running it would have produced a second
measurement of the same commit, not a new fact.

## 3. The correction this document owes about ROUND4

ROUND4 §6 and [[U393]]'s closing paragraph state: *"across FIVE in-Electron runs the pane's echo of
our own prompt counted 2, 3, 2, 3, 3 while the answer count stayed 1 EVERY TIME."* Measured from the
receipts on disk this round, that is wrong in its count and its provenance. There are **six** runs
carrying `prompt_echo_occurrences_on_the_real_pane`:

| receipt | commit | echo | answers |
|---|---|---|---|
| `round4_201556Z` | `7ca74a9` | 2 | 1 |
| `round4-rerun_201625Z` | `7ca74a9` | 3 | 1 |
| `round4-fresh_212513Z` | `7ca74a9` | 2 | 1 |
| `validator-r4_214956Z` | `7ca74a9` | 3 | 1 |
| `round4-remediated_221142Z` | `b20355e` | 3 | 1 |
| `round4-final_223425Z` | `fedbc4e` | 3 | 1 |

The true sequence is **2, 3, 2, 3, 3, 3**, and the first two belong to the **predecessor turn that
died** — ROUND4 §1 says so itself. So **four** runs were that iteration's, not five, and the quoted
sequence omitted the final run while silently merging two turns.

The substantive claim survives intact and is in fact stronger: **the echo count is nondeterministic
between 2 and 3 across six runs while the answer count never once moved off 1.** Under the pre-[[U385]]
rule ("the second occurrence is the answer") every one of those six runs would have promoted a silent
pane. It is the provenance that was wrong — and provenance is precisely what this unit keeps getting
caught on ([[U384]], [[U386]](g), [[U393]], now this). ROUND4 is not edited; [[U394]] carries the
correction.

## 4. Verdicts

**gate-validator: PASS.** 0 BLOCKING, 1 MAJOR, 4 MEDIUM, 3 MINOR — none requiring a product change.
It wrote **12 mutations of its own** rather than trusting the harnesses, spliced each by hand and
restored every file byte-identically; 5 caught, 7 survived. It independently replicated R22/R23 and
confirmed each reddens exactly the test that names its defect — ROUND4 §4's most specific claim,
re-derived rather than believed. The seven survivors are coverage gaps over correct, fail-closed
shipped code: two `main.js` bindings and one cross-run call site that only a byte-hash tripwire
guards (**F1/F2 → 19.9**, by [[U338]]'s own words), two unasserted lines in `worker-readiness.js`
(**F4/F5 → follow-on unit**), and one self-check leg predicate (**F3 = [[U382]]**, already open).

**spec-auditor: PROHIBITED DRIFT NONE.** 0 BLOCKING, 0 MAJOR, 2 MEDIUM, 5 MINOR. Invariants 1, 2, 7,
16, 27 and I-SC1 re-verified against the bytes; the untouchable set confirmed undisturbed; the
register confirmed pure-append with [[U389]]'s superseded absolute left standing and retracted by new
rows. Its two MEDIUMs and five MINORs are prose and provenance defects — **every one re-verified on
disk by the builder before being recorded**, none taken on the reviewer's word.

**Neither reviewer's findings require a code change**, and both said so explicitly when asked the
closing question directly.

## 5. What is deliberately NOT repaired, and why

Three auditor findings live under `apps/desktop/**`, inside the receipt's `product_paths`:
`worker-readiness.test.js:429` still carries the absolute [[U393]] retracted (MEDIUM-1); the
differential-repaint comment at `worker-readiness.js:279-281` says 39 characters where the separator
measures **41** (MINOR-2); and the receipt's generated disclosure says "each pane's launch record is
SEEDED" where `panes[] = [A, B, G, H]` and `seeded_launch_record.per_pane = {F, G, H}` (MINOR-4). A
fourth, MINOR-5, is a short note trail in `tools/mutation/`.

This unit's habit has been to repair prose **in the bytes** — [[U384]], [[U386]](g) and [[U393]] were
all fixed that way. Here it would be the wrong call, and the reason is worth stating so no reader
mistakes restraint for oversight: repairing any of the three flips `tracked_product_tree_clean`, voids
`round4-final_223425Z` — the first green D-P16-0 receipt this unit has produced — and buys a **sixth**
review round for sentences that change no behaviour, no test result and no verdict. The rule that
closes a unit is *no finding whose repair changes the tree*; changing the tree for cosmetics after
that condition is met is the fix-after-validation trap chosen on purpose. All four are carried to the
follow-on unit, which already owns `worker-readiness.js` ([[U373]] residual) and
`readiness-window-selfcheck.js` ([[U380]]).

## 6. Criterion C5, stated without rounding up

Directive row 19.4 requires *"a healthy, connected, exit-0 worker whose transcript merely mentions
'usage limit' or 'not signed in' stays READY."* Graded honestly: **MET at module level, NOT MET
end-to-end.** The test exists and passes (`worker-readiness.test.js:272-286`, plus two further forms).
Through the production [[U328]] write gate the same worker does **not** stay READY — the gate reads
`buffer.snapshot()`, withholds the write, and readiness reports `STALLED` / `write_gate_withheld`.
`worker-readiness.test.js:588-617` pins that as the current truth, and receipt leg F carries
`residual_u373_worker_stalls_though_connected: true`, so **the receipt goes red the day the gate is
bounded**. The repair belongs to [[U373]]/[[U363]]/[[U380]] and unit 19.3's gate. Nobody reading this
closure can infer the criterion is wholly met.

Likewise recorded rather than claimed: the structured signal this unit elevates above screen text is
itself known-unreliable until 19.7 — `sovereign-control-server.js:62-66` reports `connected` for any
`_lastSeen` with no staleness window ([[U335]]). It fails **closed** for promotion (`toolSucceeded`
requires a real `get_worker_status` call), so it degrades diagnosis, never promotes a silent worker.

## 7. Measurements, foreground, on the closing tree

| Suite / harness | Builder | gate-validator (independent) |
|---|---|---|
| `apps/desktop` — `npm test` | **930 pass / 0 fail / 0 skipped** | 930 / 0 / 0 |
| `terminal` — `node --test test/*.test.js` | **216 / 0** | 216 / 0 |
| `test:falsify:readiness` | **23/23 CAUGHT** | 23/23 |
| `test:falsify:panewrite` | **25/25 CAUGHT** | 25/25 |
| `test:falsify` (pane-input) | **ALL CAUGHT** | ALL |
| `test:falsify:orchestration` | **5/5 CAUGHT** | 5/5 |

Every mutated file restored **BYTE-IDENTICAL** by SHA-256 (`worker-readiness.js` `B526A830…D2E4E3C`,
`main.js` `7184DD8D…23B1A06`, `pane-writer.js` `15511BB8…1C0CB85`), and `git status --porcelain` was
empty after all four harnesses. `SHA-256(main.js)` also **matches** both harness pins, which is what
resolved the auditor's MINOR-5 to its benign branch: the pins are current, the harnesses genuinely
ran, and ROUND4 §4/§5's counts stand.

Python suites not run, and the reason is not that they are slow: **no commit in this unit touches a
`.py` file** — unit 19.10 owns that run ([[U339]]).

**D-LOOP-1:** no pane, no session, no child process beyond the test runners was created this round;
nothing was left running; `live_exchanges` is **0** for the entire unit. **D-LOOP-2:** both reviewers
ran in-turn and synchronously; nothing was backgrounded or awaited across a turn boundary.

## 8. Disposition

**Unit 19.4 is CLOSED.** [[U329]] is closed with graded falsification.

- **CLOSED:** [[U329]], [[U373]] (primary), [[U379]], [[U384]], [[U385]], [[U386]](b)/(d)/(e)/(f)/(g),
  [[U392]], [[U393]]
- **→ 19.6:** [[U386]](c), [[U393]] MINOR-1 — the vendor-name branches at `provider-readiness.js:32/:37/:41`
  and `pane-writer.js:237`, so the descriptor generalization does not stop at `requiredTurns` (I-SC1)
- **→ 19.7:** [[U335]] / F7
- **→ 19.9:** [[U382]], F1, F2 — the `main.js` binding coverage, with [[U338]]'s extraction
- **→ follow-on unit:** [[U373]] residual, [[U363]] verdict half, [[U380]], and [[U394]]'s MEDIUM-1,
  MINOR-2, MINOR-4, MINOR-5, F4, F5
- **Operator's:** [[U387]] (stale worktree at `D:/multi model terminal app/gv-19.4`, outside the repo
  root — §2.5 forbids this loop deleting it)

**No tag applied.** `gate/phase-19` belongs to unit 19.10 and closes the whole phase;
`product/multi-frontier-v2` is never moved.

**The lesson of the unit, in one line:** four times running, the pure function had the order right and
the caller did not ([[U373]], [[U379]], the round-2 blocking finding, [[U392]]) — a signal read once
and then trusted for a whole deadline. The fifth round found no fifth instance, and that is the
evidence, not the absence of it.
