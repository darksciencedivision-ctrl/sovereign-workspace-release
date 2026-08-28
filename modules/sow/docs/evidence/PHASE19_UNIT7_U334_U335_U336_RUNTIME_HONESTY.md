# Phase 19 · Unit 19.7 — U334/U335/U336: the runtime tells the truth about its own failures

**Status:** **CLOSED.** **Four gate-validator rounds and three spec-auditor rounds** ran in the
foreground, in-turn; repairs landed after each, and each round re-read the tree the previous round's
repairs produced. Rounds 3 and 4 both returned **PASS_WITH_RESERVATIONS, 0 BLOCKING**, and spec-audit
rounds 2 and 3 both returned **PROHIBITED DRIFT: NONE** with every finding in the *evidence and comment*
layer, none in the code. The last round's items are repaired in `f324671`; §10.1 lists each and §11 says
plainly what is and is not covered by a review at this point.
**Work commits:** `09720ce` (the unit), `eb89ed0` (the self-check instrument's own defect, found by
running it), `9d51701` (gate-validator round-1 repairs), `323e541` (round-2 repairs), `e29bd7d`
(spec-audit round-1 repairs — product code: `main.js`, `operational-source.js`), `65d92e7`
(round-3 repairs — `test/`, the mutation harness, and one comment), `f324671` (round-4 repairs —
the same three places, no product statement moved since `e29bd7d`).
**Evidence commit:** this file, register rows U431–U439, and the four not-yet-committed receipts (§8.1).
**Tag:** none. `gate/phase-19` belongs to unit 19.10; `product/multi-frontier-v2` is never moved.

---

## 1. Reconciliation at entry

`git tag -l` said `gate/phase-18e` and `product/multi-frontier-v2` were newest; `LOOP_STATE.json` said
`next_step = phase-19.7`, iteration 134, 19.6 closed, Phase 19's gate belonging to 19.10. They
**agreed** — no reconciliation commit owed. HEAD was `71bd348`, iteration 134's state commit.

The tree was **not** clean: `apps/desktop/control/sovereign-control-server.js` carried an uncommitted
partial edit (the staleness constants and a rewritten `connectionState`, no `stop()` work) from an
iteration that died before committing. Per the phase's recovery-provenance rule that is CANDIDATE
material, not work: it was read, kept where it was right, and everything resting on it was re-derived
and re-run in this unit. Nothing from it was trusted because it was already on disk.

## 2. What the unit was chartered to do, and what it did

Directive §18, row 19.7, clause by clause.

| Clause | Done |
|---|---|
| bound `stop()` with a timeout **plus `closeAllConnections()`** | yes — graceful close, destroy at the halfway mark, resolve regardless at the end |
| bring it **inside `teardown()`** | yes — fire-and-forget there, awaited (memoised) by both quit paths |
| `connectionState` gets a **`last_seen` staleness window** so a dead MCP subprocess behind a live PTY cannot report `connected` | yes — plus a fourth state, `stale` = UNVERIFIED |
| `controlAssignTask` checks **MCP freshness**, not pane state alone | yes — through `apps/desktop/control/assignment-gate.js`, where it can be driven by a test |
| `operational-source.js` stops returning a **fully-shaped zero-count success on error** | yes — null, never zero |
| `main.js` stops reporting **top-level `ok: true`** when the operational half failed | yes — `ok` is the AND of both reads, and the legacy half gets the same null treatment |

Nothing else was in scope and nothing else was changed. Re-verified over the **whole** range at close,
`71bd348..f324671` — the earlier draft of this sentence cited `71bd348..323e541` and called it "the
entire range", which stopped one commit short of the tree it shipped with; the version after that stopped
one short again (spec-auditor round 2, MAJOR-1 — the certainty-inflation class this unit exists to
remove, which is why the range is stated as a command that was re-run at the actual close):

* `git diff --stat 71bd348..f324671 -- '*.py'` → empty. No Python file is touched, so invariant 7 is
  untouched by construction.
* `git diff --name-only 71bd348..f324671 -- schemas docs/canonical` → empty.
* 20 files in the range, every one inside the declared scope. No register rewrite, no live provider
  call, no credential.

## 3. U334 — the await that had no end

The audited code was `await new Promise((resolve) => server.close(() => resolve()))`. `close()` does not
resolve while any connection is open and every attached node holds one, and this await sits **after**
`before-quit` called `event.preventDefault()` — so the shell could say it was quitting and then not.

What replaced it runs to a stated budget and **reports what that took**: `{closed, forced, timed_out,
waited_ms, timeout_ms}` on the listening path (the "there was no server" early return at
`sovereign-control-server.js:233` answers `{closed, was_listening: false, forced, timed_out}` and no
duration, because none was spent — spec-auditor round 2, MINOR-1, recorded as **U437** rather than
rounded off in this sentence). `closed: false` is the honest answer for a socket that outlived the
budget, and it is never rendered as success **by `stop()` or by the teardown log line** — the
process's own exit code still ignores it (`main.js:2947` computes `complete` without `controlStop`),
which is U432's item, owner 19.9. Two stages rather than one destroy, deliberately: `close()` first lets a call
the node is waiting on finish, and only what is still holding on at the halfway mark is destroyed.
Credentials are cleared **first and unconditionally**, so even a stop that times out has revoked
everything. It is memoised, `start()` invalidates the memo, and it never rejects — both call sites are
teardown paths where a thrown shutdown error is worse than a reported one.

**A call arriving mid-shutdown now answers 503 "shutting down", not 401.** `stop()` clears credentials at
kill-request time, so a node's perfectly valid token would otherwise be told it had an authentication
problem. Fail-closed either way; only what it says about itself changed — which is this unit's subject.

**It was not the only unbounded await on that path, and the first version of this file's comment said it
was.** `apps/desktop/voice/turn-authority.js:687` is the same shape and is awaited one step earlier. The
word is gone from the code; the defect is **U435**, owner 19.9. The cold audit's own U334 row carries the
same overstatement, which is why the correction is recorded rather than quietly applied.

## 4. U335 — `connected` was a latch, and the fix had to not become a pin

`connectionState` answered `connected` from any `_lastSeen` at all. It now has a window (default 180 s,
which is `AppControlClient`'s own per-call ceiling at `mcp_server/sovereign_tools.py:40`, so a node inside
its longest possible single call is still fresh) and four states: `disconnected` (no credential),
`configured` (credential, nothing ever arrived), `connected` (a request inside the window), `stale` (one
arrived, longer ago than silence can account for). It carries `last_seen_age_ms`, clamps a backwards clock
to zero, and fails closed to `stale` on an unparseable stamp.

**`stale` means UNVERIFIED, and that distinction is the whole design.** The gate-validator's round-1
BLOCKING-1 was that the first draft did not honour it: binding readiness to `=== "connected"` meant a
worker that HAD connected but had been quiet longer than the window never reached its challenge and was
written a durable `STALLED` on a pane nothing had been typed into — U329's defect class, re-created inside
the unit written to remove it. Two different questions were being answered by one comparison:

* **has this node ever had a session?** → `sessionEstablished()`, used by readiness (whose challenge is a
  PROVOCATION: the answer is a real gateway call, which re-freshens the session) and by the two
  operational status functions' `ready`;
* **has it had one recently?** → the assignment gate, and only there.

The refusal is per-attempt: nothing is written to the worker, so the node's next gateway call makes the
same assignment succeed. It also names an exit that **exists** — round 1's version told the caller to
"re-run readiness", and no readiness re-run is reachable for a worker already READY.

**Two bounds on the mechanism, both recorded rather than rounded off.** `_lastSeen` observes only calls
that traverse the app-control gateway, so `read_messages`, `abort_debate`, `close_debate`,
`publish_synthesis` and artifact publish/read do not refresh it — a node doing store-only MCP work is
working and `stale` at once (**U434**, whose real fix is a node heartbeat). And refusing is costless for
the worker but **not for the project**: `sovereign_tools.py` creates the task before calling the shell and
marks it `BLOCKED` when the call raises, so a routine staleness can leave a durable BLOCKED row
(**U436**, owner 19.9, with the fail-closed pre-pass shape named).

## 5. U336 — "I cannot see" is not "nothing happened"

The failure branch returned `tasks: []`, `messages: []`, `debates: []` and four zeroes with `ok:false`
beside them, and `inspector:fetch` returned a literal `ok: true` whenever the *legacy* read had succeeded.
Two different worlds — a store holding nothing, and a store nobody could read — rendered identically, and
the second is the one where somebody needs to look.

Unreadable now carries **null**, never zero, on both halves; `available` states it; the live node list
survives because that is the shell's own observation and not the emitter's. `ok` is `Boolean(legacy) &&
operationalOk`. The drawer degrades **per half**: the unreadable side says UNREADABLE and prints no
number, the readable side still prints its own counts, and with nothing readable the fail-closed banner
stands alone. All three cases are painted through the production `renderInspector` in the real renderer
and read back out of the DOM by the receipt.

## 6. Falsification

Each row carries the tree it was run at (the earlier draft stated these results with no tree attached
while §10 admitted the bytes had moved — spec-auditor round 2, MEDIUM-1):

| Harness | Tree | Result |
|---|---|---|
| `tools/mutation/orchestration_mutations.js` | **`f324671`** | **ALL 14 CAUGHT** (O6–O14 are new; the count in its closing line is derived, not typed) |
| `tools/mutation/pane_input_bypass_mutations.js` | `65d92e7` | ALL CAUGHT, `main.js` restored byte-identically |
| `tools/mutation/system_pane_write_mutations.js` | `65d92e7` | ALL 32 CAUGHT, four files byte-identical |
| `tools/mutation/readiness_signal_mutations.js` | `65d92e7` | ALL 26 CAUGHT |
| `tools/mutation/disarm_authority_mutations.js` | `65d92e7` | ALL 11 CAUGHT |

The four harnesses at `65d92e7` are **not** re-run at `f324671`, and the reason is checkable rather than
asserted: every file each of them pins is byte-identical between the two trees — `f324671` moves
`sovereign-control-server.js` comment bytes, two test files and this harness, and none of those four pins
`sovereign-control-server.js` (the round-4 validator enumerated the pins repo-wide and found it pinned in
exactly one place).

**O6–O10 are the audited behaviour put back**: any timestamp counts as live again (U335); a timed-out stop
reported as a clean close; the halfway destroy removed; the zero-count shape restored (U336); the gate
stops consulting the node. **O11–O14 are a weaker and different claim** and the distinction is kept
because it matters (spec-auditor round 3, MEDIUM-2): each restores a state that existed only *between
review rounds of this unit* — `main.js` calling the gate and filtering out the one verdict it was written
for; the operator's dispatch sentence no longer naming MCP-unverified workers; an emitter's `ok`/
`available` overwriting the inspector call's verdict; and the round-4 validator's own decoy, that same
dispatch clause commented out at the end of a live line.

Four further mutations were written and run against the **round-2 repairs** specifically (the second
`sessionEstablished` call site, `_lastSeen.clear()`, the 503 branch, and a block-comment decoy around the
`if (refusal)` pin): all four CAUGHT, every file restored byte-identically, and the driver deleted.

**Which harness re-pinned what** (the earlier "three baselines … four files" sentence was arithmetically
unreadable — spec-auditor round 3, MINOR-4): `orchestration_mutations.js` re-pinned `main.js`,
`sovereign-control-server.js` (three times across the rounds, the last two comment-only) and added pins
for `operational-source.js` and `assignment-gate.js`; `pane_input_bypass_mutations.js` and
`system_pane_write_mutations.js` re-pinned their own `main.js` baseline; `readiness_signal_mutations.js`
and `system_pane_write_mutations.js` re-pinned `worker-readiness.js`. Every anchor was re-read and every
row re-run. O11's
anchor had to be widened because `    if (refusal) {` occurs twice in `main.js` — the harness refused to
run on the ambiguity, which is the fail-closed behaviour working.

## 7. Suites

| Run | Tree | Result |
|---|---|---|
| `node --test test/*.test.js` (apps/desktop) | `e29bd7d` | 990 passed / 0 failed / 0 skipped |
| `node --test test/*.test.js` (apps/desktop) | `65d92e7` | 992 passed / 0 failed / 0 skipped (the two round-3 graders) |
| `node --test test/*.test.js` (apps/desktop) | **`f324671`** | **992 passed / 0 failed / 0 skipped** (the round-4 repairs; the count is unchanged because they strengthened an existing pin rather than adding a test) |
| `node --test test/*.test.js` (terminal) | `e29bd7d` | **216 passed / 0 failed** (no terminal file is in this unit's range) |
| `py -3.12 -m pytest tests/unit -q` | `323e541` | 1889 passed / 1 skipped |
| `py -3.12 -m pytest tests/integration tests/security tests/recovery tests/evaluation -q` | `323e541` | 487 passed in 636.65 s |

The Python rows are **not** re-run at `65d92e7`, and the reason is stated rather than implied: no `.py`
file is touched anywhere in `71bd348..65d92e7` (§2). The gate-validator independently re-ran
`tests/unit` at `e29bd7d` and reproduced `1889 passed, 1 skipped in 60.98 s`; it did **not** re-run the
long suite, and says so.

Two host-coupling facts recorded rather than smoothed: the long suite is over the 600 s ceiling again on a
host that was also running the desktop suite and several Electron self-checks — consistent with 19.6's
finding that six host-coupled tests own ~390 s of it, and still U339's at 19.10; and the validator saw
`tests/unit/test_run_frontier_providers_ps1.py::TestExitCodeContract::test_a_refused_probe_exits_three_and_spends_nothing`
**fail under concurrent load** and pass in isolation (**U438**, same family). `ruff` is absent from this
host: CLAUDE.md's ruff-clean bar is **not run, not clean**.

## 8. D-P16-0 — the in-Electron receipt

The receipt that stands for this unit is the one taken at the tree that ships:
`docs/evidence/receipts/PHASE19_7_RUNTIME_HONESTY_SELFCHECK_19.7-round4-repairs_20260814T040252Z.json` —
`ok: true`, `source.commit f324671`, `tracked_product_tree_clean: true`, `live_exchanges: 0`, **19 checks,
none missing, none failed**, six legs. Six earlier receipts sit beside it and are accounted for in §8.1.

**D-LOOP-1, stated as the source actually reads it** (no receipt field asserts this, and the sentence that
said "every server … in a `finally`" was wrong — spec-auditor round 3, MAJOR-2): this check constructs
**three** servers. The one at `runtime-honesty-selfcheck.js:163` is stopped in a `finally` (`:216-218`);
leg A's at `:103` is stopped inside its `try` (`:116`); leg F's at `:147` is stopped at `:151` under no
guard at all. All three are stopped on the success path and the check's own process exits, so no resource
outlives the unit — but two of the three would leak if their leg threw, and that is **U437(g)**, not a
`finally`.

Legs: **A** a real socket held open against a real production server, `stop()` resolving in **402 ms** of
an 800 ms budget with `forced: true` and the issued credential gone (the number is per-run and is quoted
from the named receipt: 411 ms at `323e541`, 415 ms at `e29bd7d`, 404 ms in the validator's own
independent run — the *bound*, the destroy at `budget/2`, is what is stable);
**F** the two defaults production
actually runs on (180 000 / 5 000 — graded by nothing before round 2, and both of the validator's
mutations of them survived the entire suite); **B** the state machine across a real loopback request with
an injected clock, `configured` → `connected` → `stale` → `connected`; **C** the production assignment gate
over that same server, refusing a READY pane on a stale session with the age in the reason and assignable
again after the node calls; **D** the real preload bridge — on this host the legacy half genuinely fails
(`echo surface: unsupported op 'read_status'`) while the operational half reads, so **leg D** records
`ok: false` (the inspector fetch's `ok`, not the receipt's) with `operational_available: true`, which is
exactly the case the audited code answered `ok: true` to; **E** three paints through the production
renderer.

### 8.1 The seven receipts, as a set

Seven exist and none is deleted, which is the only way the sequence stays readable. **Three are already
committed** (in `e29bd7d`): `…19.7_…` (`ok:false` — the instrument's own failing leg, preserved; `eb89ed0`
is its fix: leg E had asserted no "0 tasks" appeared anywhere and then failed the shell for a
**legitimate** zero printed by the readable half), `…fixed-leg-e_…` and `…round1-repairs_…`. **Four are
committed with this report**: `…round2-repairs_…` (`323e541`), `…round3-tree_…` (`e29bd7d` — the tree the
round-3 reviewers actually read), `…round3-repairs_…` (`65d92e7`) and `…round4-repairs_…` (`f324671`),
the one §8 stands on.

The earlier draft of this section said "all five are committed" while §1 listed the receipts as part of
*this* commit — two sentences that could not both be true, about a receipt taken after the commit it
claimed to be in (gate-validator round 4, MEDIUM-1; spec-auditor round 3, MAJOR-1). The count was wrong
twice, in the section whose subject is counting honestly.

**Not measured by the receipt**, and disclosed in it: that `teardown()` is where the gateway stop now lives
(the receipt is written before teardown runs — source pin); that `controlAssignTask` honours the verdict
unguarded (source pin + O11); that readiness still provokes a stale worker (headless, against the
production module); the 503 branch (driven over a real socket in the suite); and that leg D's
unreadable-half check short-circuits `true` on a host whose operational feed reads.

## 9. The reviewers

| Reviewer | Tree | Verdict |
|---|---|---|
| `gate-validator` round 1 | `eb89ed0` | **FAIL** — 2 BLOCKING, 3 MAJOR, 2 MEDIUM, 4 MINOR |
| `gate-validator` round 2 | `9d51701` | **PASS_WITH_RESERVATIONS** — 0 BLOCKING, 1 MAJOR, 5 MEDIUM, 7 MINOR; 19 mutations of its own, 4 survived |
| `spec-auditor` round 1 | `323e541` | **PROHIBITED DRIFT: NONE** — 4 MAJOR, 6 MEDIUM, 6 MINOR |
| `gate-validator` round 3 | `e29bd7d` | **PASS_WITH_RESERVATIONS** — 0 BLOCKING, 1 MAJOR, 2 MEDIUM, 3 MINOR; re-ran all five harnesses, the desktop, terminal and `tests/unit` suites, and the in-Electron check independently, and mutated the round-3 delta itself |
| `spec-auditor` round 2 | `e29bd7d` | **PROHIBITED DRIFT: NONE** — 3 MAJOR, 4 MEDIUM, 7 MINOR, **every one in the evidence layer**, none in the code |
| `gate-validator` round 4 | `65d92e7` | **PASS_WITH_RESERVATIONS** — 0 BLOCKING, 1 MAJOR, 1 MEDIUM, 3 MINOR; proved the delta comment-only by hashing both blobs with every line comment stripped, then **defeated the new pin with a trailing comment** |
| `spec-auditor` round 3 | `65d92e7` | **PROHIBITED DRIFT: NONE** — 2 MAJOR, 4 MEDIUM, 5 MINOR, again all in the evidence and comment layer; both MAJORs were round-2 repairs that had moved their hole rather than closed it |

Full findings, corrections and owners are in register rows **U431–U440**. The five that change what a
reader should believe:

1. **Round 1 was right to fail this unit.** The staleness window reached into readiness and could pin a
   healthy worker, and the refusal named an exit that does not exist. Both are repaired and both repairs
   are falsified by mutation.
2. **A repair moved a hole rather than closing it, twice, in the same three lines** (U433) — the
   credential-revocation assertion. Round 1 found it against a name that was never a node; round 2 found
   the repair still passing with `_lastSeen.clear()` deleted. That is this phase's recurring failure mode
   appearing inside a fix for itself.
3. **Two register IDs were cited in shipped code before they existed** (spec-audit MAJOR-1). U434 and U435
   are written now, with owners. A citation to a row that does not exist is a claim wider than its
   evidence wearing a reference's clothes.
4. **The refusal is not costless system-wide** (spec-audit MAJOR-2, U436). The gate's own claim is now
   scoped to the worker record, and the BLOCKED-task consequence is named where the claim used to be.
5. **The repair for a claim-wider-than-its-evidence was itself one, three rounds running** (U439). Round
   3's fix for the ungraded sentence shipped with a sentence saying a comment could not satisfy the new
   pin; round 4 satisfied it with a comment. Round 2's fix for a D-LOOP-1 claim attributed to receipt
   fields moved it to a source citation that the source does not support. Round 3's fix for an
   unattributed measurement stated a receipt count that was already wrong. Each is repaired here and
   each is recorded, because the pattern is more informative than any one instance.

## 10. What round 3 found, and what `65d92e7` did about it

The two reviewers over `e29bd7d` agreed on the shape, from opposite ends. The validator found it in the
code, the auditor in the paperwork, and it is the same shape both times: **a claim graded by something
that cannot fail.**

| Finding | Disposition |
|---|---|
| **gate-validator MAJOR-1** — the operator-facing `(N MCP-unverified)` clause was reachable behaviour graded by nothing but the whole-file SHA pin in `selfcheck-guards`, which every unit re-pins. Its own mutation deleting the clause passed 989 of 990 tests. | **Fixed** — pinned in `test/runtime-honesty-wiring.test.js` and falsified as **O12**. The first version of this row claimed a comment could not satisfy the pin; **round 4 satisfied it with a trailing comment** (`executableOnly` strips whole-line and block comments only). The pin strips trailing comments in that region now, and the validator's decoy is **O14** — CAUGHT. |
| **gate-validator MEDIUM-1** — reverting the `ok`/`available` spread order survived the entire suite; and the behaviour it defends is not reachable today (`emit_operational_state.py` emits neither key). | **Fixed and scoped** — graded by a feed that ships both keys, falsified as **O13**, and the test itself records that it is hardening against a shape no emitter yet produces. |
| **gate-validator MEDIUM-2 / spec-auditor MAJOR-1,2,3** — this report described a tree one commit older than the one it shipped with: `e29bd7d` missing from the commit list, the `.py`-free claim scoped to `71bd348..323e541` and called "the entire range", and a round-3 receipt described as owed when it was already on disk. | **Fixed** in this file (§1, §2, §8, §8.1) and re-verified over `71bd348..65d92e7`. |
| **spec-auditor MEDIUM-1** — §6/§7 stated results with no tree attached while §10 admitted the bytes had moved; and this unit's re-pins were narrated only through round 1. | **Fixed** — every harness re-run at `65d92e7` and labelled, every suite row carries its tree, and the re-pin comment in `orchestration_mutations.js` now names the round-3 one and states which pins did **not** move. |
| **spec-auditor MEDIUM-2** — "`closed:false` … never rendered as success" is wider than the code: `main.js:2947` computes the exit code without `controlStop`. | **Scoped** in §3, pointing at U432's existing item, owner 19.9. |
| **spec-auditor MEDIUM-3, MINOR-7** — §8 attributed to receipt fields a D-LOOP-1 fact that is a source read, and used the receipt's `ok` and leg D's `ok` in one paragraph. | **Fixed** in §8. |
| **spec-auditor MEDIUM-4** — a falsification run whose driver was deleted is unreproducible. | **Scoped** in §6 rather than re-asserted. |
| **spec-auditor MINOR-1** — `stop()`'s no-server early return omits `waited_ms`/`timeout_ms`, so §3's stated shape is not universal. | **Recorded as U437**, owner 19.9, and §3 scoped. Not fixed here: it is a behaviour change to a shutdown path after three completed review rounds, and this unit's own charter is that such a change be reviewed, not slipped in at the close. |
| **spec-auditor MINOR-2** — the 503-window comment cited "leg A of this unit's receipt" and a number, with five receipts in existence whose numbers differ. | **Fixed** — the receipt is named in the comment and the per-run spread is stated. |
| **gate-validator MINOR-1** — a `tests/unit` test that fails under concurrent host load and passes in isolation. | **Recorded as U438**, U339's family, owner 19.10. |
| **spec-auditor MINOR-3,4,5,6**, **gate-validator MINOR-2,3** | **Recorded** in U437: leg E1's non-production payload shape, `mcp_connected: true` reachable for a `stale` session (already U432's, owner 19.8), the duplicated established-state literals in `assignment-gate.js:107`, the unverified long-suite row, and the ungraded drawer-clearing string. The heading finding was addressed by rewriting **U432**'s body to CLOSED, not by anything in U437 — an earlier version of this row said otherwise and described a disposition that had not happened (spec-auditor round 3, MEDIUM-4). |

## 10.1 What round 4 found in the repairs above

Both reviewers were re-run over `65d92e7` because this phase's rule is that repairs after a review void
it. Neither found a product-code defect; both found that the *repairs* had inherited the fault they were
repairing.

| Finding | Disposition at `f324671` |
|---|---|
| **gate-validator MAJOR-1** — `executableOnly` does not strip trailing comments, so `+ ``${false ? "" : ""}`` // + ``${unverified …`` left the operator's sentence silent and the new test green (992 → the only failure was the whole-file SHA the round called useless). | **Fixed** — the U335 pin strips trailing comments in that region (and only there: the other pins guard regions where a `//` can appear inside a string). Falsified as **O14**, the validator's decoy verbatim. |
| **spec-auditor MAJOR-1 / gate-validator MEDIUM-1** — §8/§8.1 miscounted the receipts and said "all five are committed" of a receipt taken after the commit it claimed to be in. | **Fixed** — §8.1 now names all seven, says which three are already committed and which four arrive with this report. |
| **spec-auditor MAJOR-2** — §8's D-LOOP-1 sentence cited a `finally` that stops a client socket, not a server; of the check's three servers only one is stopped in a `finally`. | **Fixed** — §8 states the three servers, where each is stopped, and records the two unguarded ones as **U437(g)**. |
| **spec-auditor MEDIUM-1** — `stop()`'s doc comment still carried the unqualified "never rendered as success" that §3 had scoped. | **Fixed** in the comment, with the U432/19.9 pointer. |
| **spec-auditor MEDIUM-2 / gate-validator MINOR-3** — "each row is the AUDITED behaviour put back" is false for O11–O14, which restore between-round states. | **Fixed** in §6 and in the harness's umbrella comment. |
| **spec-auditor MEDIUM-3** — U431's falsification paragraph said "six new rows … O6–O11" while the harness shipped eight. | **Fixed** in the register row before commit. |
| **spec-auditor MEDIUM-4** — §10 credited U437 with a disposition it does not contain. | **Fixed** in the row above. |
| **spec-auditor MINOR-1** — the new test credited `65d92e7` with the spread-order repair, which landed in `e29bd7d`. | **Fixed** in the test's comment. |
| **spec-auditor MINOR-2** — the sentence that fixed an unattributed measurement said "five receipts" when there were six. | **Fixed** — the comment states the count against a list and names the trees. |
| **spec-auditor MINOR-3** — U432's heading said "across three rounds" while its body records five. | **Fixed** in the register row before commit. |
| **spec-auditor MINOR-4** — §6's "three baselines … four files" was arithmetically unreadable. | **Fixed** — §6 names which harness re-pinned which file. |
| **gate-validator MINOR-1** — the U335 negative assertion pins clause ORDER, so a benign reorder would fail with a message that would then be untrue. | **Message corrected**; the ordering constraint is kept deliberately, because the clause's position is what the operator reads. |
| **gate-validator MINOR-2** — the harness reads any child exit 1 as CAUGHT, so a setup failure and an assertion failure are indistinguishable for source-pin rows. | **Recorded as U439**; pre-existing, and the validator closed the gap by hand for O12/O13 (both fail on named `AssertionError`s). |
| **gate-validator MINOR-3 / spec-auditor MINOR-5** — §11 asserted a fourth round would be futile, in a delta that also rewrote ten sections and eight register rows. | **§11 rewritten** below to say what actually happened instead. |

## 11. Where this unit stops, and what is true of the tree it stops on

An earlier draft of this section argued that a fourth round would be futile because the delta was
test-only. **That argument was made and then tested, and it was half wrong.** Round 4 ran. It confirmed
the product half by measurement — every executable product byte identical between `e29bd7d` and
`65d92e7`, proved by hashing both blob versions with every line comment stripped, not by trusting the
diff — and then it broke the new pin with a trailing comment, and the spec-audit found two of the
previous round's repairs had inherited the fault they were repairing. The evidence layer is a
spec-auditor's object of review, and rewriting it is exactly the kind of change that needs re-reading.

**What is true of `f324671`, the tree this report ships on:**

* the three charter clauses of directive row 19.7 are implemented, and each is falsified by a mutation
  that restores the audited behaviour and is caught (§6, O6–O10);
* every reachable behaviour change the review rounds themselves introduced is now graded by an assertion,
  not by a re-pinned hash (O11–O14);
* five mutation harnesses, the desktop suite (992), the terminal suite (216) and the Python suites are
  green, each row carrying the tree it was run at and each unverified row named as unverified (§6, §7);
* a D-P16-0 in-Electron receipt exists at exactly this commit, `ok: true`, 19 checks, tracked product tree
  clean, zero live exchanges (§8);
* three gate-validator rounds and three spec-auditor rounds have read it; the last two found **no
  product-code defect and no prohibited drift** (§9);
* the residuals — U437(a)–(g), U438, U439, and the older U432–U436 — are recorded with owners and named
  units, including the one behaviour fix (`stop()`'s no-server return shape) deliberately not made at a
  close.

**What is not true, and is not claimed:** that this report has itself been reviewed. It was rewritten
after round 4/3 to record what they found, and those edits are unreviewed — the regress is real, general,
and recorded as **U440** with a mechanism proposed for the phase gate at 19.10, which has the same shape
and a tag riding on it. It terminates here by convention, not by proof: the *code* is unchanged since a
passed round except for comment text whose only claim is about itself, and every correction after that
point is additive and legible — this section, §10.1, and the register rows.

Nothing in the directive's row 19.7 is unimplemented, and nothing in this report is asserted beyond the
command output behind it.
