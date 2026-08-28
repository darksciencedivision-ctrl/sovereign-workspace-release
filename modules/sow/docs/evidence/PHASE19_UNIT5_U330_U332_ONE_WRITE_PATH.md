# Phase 19 · unit 19.5 — U330 + U332: one write path, and a gate that cannot be skipped

**Status: CHECKPOINT — not closed.** Round 4 of both mandatory reviewers is owed (§9). No tag: the
Phase 19 gate belongs to unit 19.10.

| | |
|---|---|
| Unit | `phase-19.5` (AUTONOMOUS_BUILD_DIRECTIVE.md §18, row 19.5) |
| Commits | `5d56e19` work · `79e15ec` round-1 remediation · `3374c5a` round-2 remediation · this report's commit |
| Parent | `10f4e37` (iteration 130 state commit; 19.4-followon CLOSED) |
| Issues | **U330** closed · **U332** closed · **U416** (the debate stall — see §7 on its label) closed · U410–U417 opened |
| Reviewers | gate-validator ×3 (FAIL → PASS → PASS) · spec-auditor ×1 (PROHIBITED DRIFT: NO, 2 MAJOR) |
| Suites | python 1875 + 1 skipped (unit) + 487 (rest) · desktop 944/0 · mutation 20/20 RED |

---

## 1. What was wrong

The store has had a transaction for operational task records since the range the cold audit
examined: `mutate_operational_task` opens `BEGIN IMMEDIATE`, reads the row, applies a caller
mutator to **that** row, and writes it back inside the same transaction. Two of the seven
orchestration writers used it. The other five did not:

| writer | before | after |
|---|---|---|
| `create_task` | `put_operational_task` — an upsert that would silently replace an existing task, candidates and all | `create_operational_task` — refuses an existing id |
| `update_task` | read task → `{**snapshot, status}` → upsert | `mutate_operational_task`, successor from the fenced row |
| `open_debate` | `put_operational_debate` upsert | `create_operational_debate` — refuses an existing id |
| `post_debate_turn` | read debate → append to snapshot's turn list → upsert | `mutate_operational_debate`, successor from the fenced row |
| `close_debate` | read debate → build closed record from snapshot → upsert | `mutate_operational_debate`, successor from the fenced row |
| `record_candidate` | already fenced | unchanged (but now **graded** — §4) |
| `record_synthesis` | already fenced | unchanged |

The failure this produces is not exotic. Two workers posting a turn to one debate is the ordinary
case, and whoever committed second erased the other's turn — no error to either node, no conflict
record, nothing in the transcript. `put_operational_task` and `put_operational_debate` are now
**deleted** rather than deprecated: the unfenced path does not exist to be reached by habit.

Two rules moved inside the fence with the write they guard, because both read record CONTENT:
the bounded-round ceiling (invariant 14) and the close quorum. Each mutator also re-asks the
policy against the row it is acting on rather than the snapshot a verdict was computed against
one commit earlier.

## 2. The falsification, and the four drafts it took

The directive requires "a genuinely concurrent test — TWO PROCESSES, not two threads — publishing
candidates and posting debate turns against the same task, proving neither is lost." A threaded
test cannot see this defect at all: `persistence/store.py` holds a `threading.Lock` around its
writes, so a thread test is ordered by that lock and passes against code with no database
transaction whatsoever. That is why the property survived two phases unguarded.

`tests/integration/test_operational_concurrent_processes.py` spawns two worker processes and a
third watcher process against one SQLite file. **It found the defect before the fix**: run against
the parent commit it failed with `3 acknowledged turns were lost` (the round-1 validator
independently reproduced this at `9 acknowledged turns were lost`, 3 runs of 3).

The candidate limb took four drafts, and the first three are recorded because each was measured
against the defect spliced back into `record_candidate` rather than reasoned about:

| draft | detection under the spliced defect |
|---|---|
| 1. publish one candidate at the end | **0/3** — the turn loops drift the processes apart; no candidate write ever contends. *This is the decorative version the round-1 gate-validator caught as MAJOR-1.* |
| 2. one revision per round, assert the FINAL revision | **1/3** — the final state only reveals a loss in the last write |
| 3. one revision per turn, each WRITER watching its peer | **2/5** — a writer cannot see the damage it does: it destroys the PEER's revision, and its own pre-transaction snapshot is never older than what it last read |
| 4. a third watcher process + a 1000-revision burst where both workers hammer the one task row | **6/6, then 4/4 on the round-3 tree; 0/4 false positives clean** |

Round 3's validator ran the fixed tree **66 times** (sequential, 4-way and 16-way concurrent) with
**zero** failures, and 12/12 detection spliced.

Draft 3 was **deleted**, not kept as belt-and-braces. A check that cannot fire is what round 1
existed to remove.

The docstring now labels every claim by what it can catch, including one it cannot grade
(the bounded-round ceiling is unbreachable across processes, because each node is the sole writer
of its own turns — mutation row F2 and the racing unit test grade that instead).

**Anti-vacuity.** The round-2 validator blinded the watcher and got one spliced run in four through
undetected while both existing guards held. The watcher now reports `distinct_observations`
(distinct `(node, revision)` pairs actually seen — ~2,060 live, 2 blind) and the test asserts it.
Measured after the fix: clean 0/4, spliced 4/4, spliced-with-blinded-watcher 4/4 caught **by that
guard**. Round 3 attacked it two further ways (subsample 1-in-500 → caught by this guard; amnesiac
and detection-deleted → caught by other assertions).

## 3. U332 — the gate that was a loop over the caller's own list

`publish_synthesis` verified `for debate_id in debate_ids: ...`, so an empty list satisfied it
vacuously, and because `get_debate` is project-scoped rather than task-scoped, a CLOSED debate from
a **different task** satisfied a named id. `mcp_server/sovereign_tools.py:_considered_debates`
replaces it with four rules computed from the task's own debates:

1. no debate on this task may still be OPEN — named or not (omission was the bypass);
2. every named id must belong to this task;
3. every named id must be CLOSED (`_nonempty_strings` applies exactly when a closed debate exists — the directive's instruction, on the branch where there is something to skip);
4. every CLOSED debate on the task must be named.

ABORTED debates are reported separately as `aborted_debate_ids`, **from the store rather than from
the caller**, so a deliberation that never concluded cannot be presented as one that did — and
cannot block the task forever either. A task that never needed a debate stays synthesisable; the
cross-check, not the list's length, is what closes the hole.

## 4. Falsification — mutation harness

`tools/mutation/_op19_5_write_path_mutations.py`: **20/20 RED, every restore byte-identical.**
Unlike its siblings it runs a **per-target baseline first** — the limit recorded as U356 — and that
guard earned itself twice in this unit: it refused to grade when a selector named a test that had
been renamed, and three rows came back GREEN on their first run. All three GREENs were real:

- **F2** as first written mutated the ceiling VALUE (immutable, so reading it from a snapshot is
  not a defect); the count is what moves.
- **F6** as first written mutated the service and was graded by a store-level test the service
  cannot affect.
- **A2** as first written removed the pre-transaction state check, which changes no observable
  refusal because the in-fence check raises the same sentence. That result is why the outer state
  checks are now documented as early/ordering guards rather than as the guarantee.

Row **F7** grades `record_candidate` — a writer this unit did not change, which was inside the
fence already and graded by nothing, so the defect could be spliced into it with the whole suite
green (round-1 MAJOR-1's second half).

## 5. Commands and results

| command | result |
|---|---|
| `pytest tests/integration/test_operational_concurrent_processes.py` on the PARENT `10f4e37` | **FAILED — `3 acknowledged turns were lost`** (the pre-fix red) |
| `py -3.12 -m pytest tests/unit -q` | **1875 passed, 1 skipped**, 61.5 s |
| `py -3.12 -m pytest tests/integration tests/security tests/recovery tests/evaluation -q` | **487 passed**, 559.9 s |
| `cd apps/desktop && npm test` | **944 pass / 0 fail**, 98 s |
| `py -3.12 tools/mutation/_op19_5_write_path_mutations.py` | baseline all PASS → **20/20 RED**, all restores byte-identical |
| `py -3.12 tools/evaluation/u326_before_after.py` | **19 of 34 scenarios differ** (unit 19.2's figure, reproducible again — see §6) |
| defect-splice measurements (`record_candidate` snapshot defect) | clean **0/4**, spliced **4/4**, spliced + blinded watcher **4/4** |

**Corrections to earlier claims in this unit's own commit messages**, because the reviewers caught
them and an evidence report that repeats them would be worse than the error:

- `5d56e19` said "2360 passed / 1 skipped". The round-1 validator could not reproduce a fully green
  long-suite run at that commit — three attempts, two different single failures, neither in code
  this unit touches (recorded with its diagnosis as **U413**). The number above is this tree's.
- `3374c5a` said "1875 passed / 1 skipped" for the unit suite. At that commit the truth was
  **1874 passed, 1 skipped of 1875 collected** (round-3 validator MINOR-B). The 1875 in the table
  above is this tree, which adds one test (§7).
- **`ruff` is not installed on this host.** CLAUDE.md's "ruff-clean" bar is therefore **not run**
  for this unit's Python, not "clean". Both validators reported the same.

## 6. Collateral this unit caused, and repaired

`tools/evaluation/u326_before_after.py` loads the pre-U326 `collaboration_service.py` from `b529314`
and runs it against the CURRENT store — so deleting `put_operational_*` killed it
(`AttributeError`), and unit 19.2's central quantitative claim stopped being reproducible. A
`_PreU330Store` shim **in the tool, never in `persistence/`** restores the blind upsert the
historical module expects. The round-2 validator verified the shim is faithful by running the
original tool in a pre-19.5 worktree and diffing all 34 rows: **identical**.

## 7. The label collision (U416)

The directive's 19.5 row calls the debate-stall defect "**U331 note**". Register **U331** is a
different issue — *conductor readiness is hard-pinned to one vendor and one model* — opened by the
same cold audit and **owned by unit 19.6**. The stall had no row of its own. This unit initially
propagated the directive's label into sixteen sites, which would have made this report read as
closing U331 while U331 stayed untouched and owed, against Phase 19's own exit criterion. All
sixteen now cite **U416**, a new row stating both the defect and the collision.
`AUTONOMOUS_BUILD_DIRECTIVE.md` is deliberately **not** edited: it is the operator-adopted document,
and the correction belongs in the register its numbering refers to.

## 8. Reviewers

**gate-validator round 1 (`5d56e19`): FAIL — 1 MAJOR.** The candidate limb of the required
falsification could not fail (§2). Also 5 MEDIUM, 9 MINOR.

**gate-validator round 2 (`79e15ec`): PASS — 0 BLOCKING, 0 MAJOR, 3 MEDIUM, 9 MINOR.** Reproduced
every measurement and exceeded them (12/12 spliced, 66/66 clean). Three MEDIUMs were fixed rather
than carried, because two were hazards and one was a false claim: a D-LOOP-1 orphan (the watcher
could spin at 100% CPU forever if a worker hung — demonstrated), the blindable anti-vacuity guards,
and the U331 label.

**gate-validator round 3 (`3374c5a`): PASS — 0 BLOCKING, 0 MAJOR.** Independently broke the orphan
fix three ways and confirmed it holds for the watcher; found that the hung *workers* are still
orphaned (**U418**), and two disclosure errors this report corrects (§5).

**spec-auditor round 1 (`3374c5a`): PROHIBITED DRIFT — NO.** 0 BLOCKING, 2 MAJOR, 7 MEDIUM,
6 MINOR. It confirmed the two questions this unit was least sure of: policy calls inside the store
transaction are **not** an invariant-7 layering violation (the store imports nothing from
`control_plane`, evaluates no rule, and runs an opaque callable its caller supplied — asking the
verdict against the row acted on is strictly stronger than asking it against a snapshot); and
`abort_debate` is **not** the gate override invariant 16 forbids (ABORTED is not CLOSED, the
synthesis gate refuses to count it, turns survive, `decision` stays `None`, and the frozen plan
already anticipates a debate ending without convergence).

Both MAJORs were about claims, not mechanism, and both are addressed in this commit:

- **MAJOR-1** — `authorize_debate_abort`'s docstring asserted an invariant-18 protection the rule
  does not provide. It restricts by ROLE, not participation, and a task's participant set includes
  its creator — so **a conductor can abort a debate it is arguing in**, which is U350's open
  question inherited from `close_debate`, not a protection. The docstring now says what the rule
  does and why (refusing every participant would restore the stall U416 exists to end), cites U350,
  and the case is pinned twice: `test_the_conductor_may_abort_a_debate_it_is_arguing_in` and a new
  `abort_own_debate` column in the verdict matrix, where `conductor(creator)` reads `'ok'`. U350's
  eventual answer now moves a cell instead of passing unnoticed.
- **MAJOR-2** — two register rows cited an evidence document that did not exist. This is it.

## 9. What is owed, and why this is a checkpoint

**Round 4 of both mandatory reviewers.** The MAJOR-1 repair changed `control_plane/policy.py`
(docstring), one test name, one new test and eight matrix cells after the round-3 gate-validator and
the round-1 spec-auditor had passed — and fix-after-validation voids the validation. Round 4 is the
next unit's first act (directive §18's split rule, PRINT-MODE FACT D-LOOP-2: nothing survives a
turn, so it is re-run fresh and foreground, never "in flight").

**Carried, all recorded, none repaired after validation:**

| row | what |
|---|---|
| U410 | `record_synthesis` reaches COMPLETED with no debate gate (the gate is on the tool path only) |
| U411 | the synthesis gate is only as complete as the caller's debate-read scope |
| U412 | the Inspector renders ABORTED with the green ACCEPTED chip — owner **19.8**, because D-P16-0 binds shell/UI changes to an in-Electron receipt this unit does not build |
| U413 | `test_concurrent_writers_yield_conflict_never_silent_overwrite` is non-deterministic by construction — and U282's owed diagnosis, supplied by the round-1 validator |
| U414 | ABORTED vs the frozen `debate@1.0` enum; and the operational record family pins no schema at all |
| U415 | five smaller round-1 residues |
| U417 | three round-2 residues |
| U418 | round-3 and spec-audit findings: hung workers are orphans; the abort precondition is model-asserted and verified by nothing; the abort emits no append-only trace; the gate's OPEN deny-list is fail-open for a future third state; `record_candidate` does not re-ask its rule in-fence; and four prose corrections |

**Not decided by this unit:** whether the abort path should be narrowed by participation (U350),
and whether the eight new rows should bind `gate/phase-19`, whose exit criterion names only
U326–U339 (spec-audit MEDIUM-7 — it is 19.10's call, not this unit's).


---

## §11 — CLOSE-NOTE (appended 2026-08-11, iteration 132). Unit 19.5 is CLOSED.

**This section supersedes the header's "Status: CHECKPOINT".** The header is left as written because
this document is append-only; read it as historical. What was owed there — round 4 of both mandatory
reviewers — ran, found more, was repaired, and was re-reviewed. Four rounds happened in this turn, all
FOREGROUND and IN-TURN (D-LOOP-2: nothing survives a `claude -p` turn, so nothing was "in flight").

### What the owed rounds actually found

| round | reviewer | verdict | outcome |
|---|---|---|---|
| 4 | gate-validator (over `916056e`) | **PASS** — 0 BLOCKING / 0 MAJOR, 6 CARRIED | verified the rule unchanged, spliced 4 defects into the new abort test and the new matrix cell and got RED from each, reproduced 20/20 RED and `19 of 34 scenarios differ`. Worked on a byte-copy of the tree because the harness is unsafe beside a live pytest (its own CARRIED-5 → U423(c)). |
| 2 | spec-auditor (over `916056e`) | **PROHIBITED DRIFT: NONE**, 1 MAJOR | the MAJOR-1 repair had replaced one over-claim with another: the docstring asserted "the operator remains reachable as final authority … including when the conductor is the pane that died" — operator recourse no product path provides (the shell mints role `"shell"`; `apps/desktop/` has no abort handler). |
| 3 | spec-auditor (over the repair) | **PROHIBITED DRIFT: NONE**, 1 MAJOR | the *second* draft claimed the opposite impossibility — "nothing in the shipped shell can abort its debates" — refuted by `conductor:launch` (`apps/desktop/main.js:1530`) minting a successor `conductor` (`:912`) whom this role-based rule admits. |
| 4 | spec-auditor (over the repair) | **PROHIBITED DRIFT: NONE**, 1 MAJOR | the register row that replaced the docstring's claim asserted a false universal — "the two operator-role mints in product code" — with five more in the tree. |
| 5 | spec-auditor (final tree) | **PROHIBITED DRIFT: NONE**, **NO MAJOR**, 6 CARRIED (LOW/INFO) | → U424 |
| 5 | gate-validator (final tree) | **PASS** — 0 BLOCKING / 0 MAJOR, 8 CARRIED | → U425 |

### The lesson this unit adds to its own §-earlier one

A test that cannot fail looks exactly like a test that passes (§ earlier). Its sibling, learned here at
a cost of three MAJORs: **an authority module that explains the product will be wrong about the
product.** Each draft of `authorize_debate_abort`'s docstring was more carefully argued than the last
and each was falsified by a grep. The fix that finally held was not a better sentence — it was deleting
the class of sentence: the module now states its verdicts and defers every product-reachability
question to [[U420]], which is the register's job and where a claim can be corrected by append. The
executable rule was never touched by any of it; the round-5 validator proved this by comparing the ASTs
of `916056e`'s and the final `policy.py` with docstrings stripped (`AST_EQUAL_IGNORING_DOCSTRINGS: True`).

### Measurements, re-run FRESH this turn on this host (D-LOOP-2), by the builder and again by the round-5 validator

| suite | builder | validator (independent re-run) |
|---|---|---|
| `py -3.12 -m pytest tests/unit -q` | 1875 passed, 1 skipped (64.7 s) | 1875 passed, 1 skipped (66.4 s) |
| `py -3.12 -m pytest tests/integration tests/security tests/recovery tests/evaluation -q` | 487 passed (607.8 s) | 487 passed (564.0 s) |
| `npm test` (apps/desktop) | 944 pass / 0 fail | 944 pass / 0 fail |
| `py -3.12 tools/mutation/_op19_5_write_path_mutations.py` | 20/20 RED, restores byte-identical | 19/19 baseline PASS, then 20/20 RED, restores byte-identical |

`ruff` remains absent from this host, so CLAUDE.md's ruff-clean bar is **NOT RUN** — not clean, as §5
already records. The 600 s ceiling on the long suite is [[U339]]/19.10's, and the builder's 607.8 s run
sits just over it while the validator's 564.0 s sits under: the same suite, the same tree, host load the
only difference. That is the diagnosis 19.10 is chartered to make, recorded here as data for it.

### Rows opened by the owed rounds

**U420** (who can actually reach the abort rule; three drafts, and the conductor-death recourse runs
through a relaunched SUCCESSOR conductor, established by inspection with no test exercising it) ·
**U421** (six of eight `abort_own_debate` matrix cells are decided upstream in `authorize_open_debate`;
found independently by both reviewers) · **U422** (five claim defects in this unit's own evidence and
registers, two corrected by append, three carried) · **U423** (eight residues) · **U424** (four
round-5 spec-audit residues) · **U425** (three round-5 validator findings, including one the builder
introduced and did NOT repair, by rule).

### On the two acts that came after the last validation

The reviewers were the last acts to touch code. Everything after them is bookkeeping of the kind this
build has always held to be non-voiding: the register rows U424/U425 exist *because both reviewers
asked for their MEDIUM-and-below findings to be carried as rows*, and this close-note is an evidence
act. No executable line changed after the round-5 gate-validator's PASS. The four measurements above
were taken on the tree that was committed.

**Still owed by 19.5 to no one:** nothing. **Still owed by later units:** U410–U425 as recorded, owners
named in each row. The Phase 19 gate and its tag are 19.10's; 19.6 is next.
