# Correction to `PHASE19_UNIT2_U326_POLICY_DELEGATION_CHECKPOINT.md` — round 5, and the close of unit 19.2

Evidence reports are append-only (directive §2.6), so this file corrects the checkpoint rather than
editing it, following the unit-19.1 precedent (`PHASE19_UNIT1_OP13_REVERT_CHECKPOINT.CORRECTION.md`).

The checkpoint ended with: *"this document does not close the unit… the next unit's first act is
round 5 — gate-validator and spec-auditor, foreground and concurrent, on `3fa401a` plus this evidence
commit — and unit 19.2 is finished only when a round returns with nothing the fix of which changes
the tree."* **That is what this file records, and unit 19.2 closes here.**

## 1. Round 5 — both mandatory reviewers, foreground, in-turn, concurrent

Run on `021e279` (i.e. `3fa401a` + the evidence/register commit `8ac5bf4`), the two commits that
post-dated round 4 and had been reviewed by nobody. The gate-validator ran in its own git worktree
so that its mutation probe could not be read by the concurrently-running spec-auditor — the exact
collision that cost iteration 120 its first set of numbers.

**gate-validator: FAIL** — 1 MAJOR, 1 MEDIUM, 4 MINOR, 1 NIT. **Explicitly not a sixth instance of
the four-round membership-set class:** it re-attacked `ROLES`, `_SCOPED_ROLES` and `_DIRECTING_ROLES`
with its own spellings, in both the addition and removal directions, and every one went RED. Its own
16-mutation probe returned **10 RED, 2 equivalent mutants, 1 confirmation of the already-recorded
U351(b), and 4 real survivors** — all four of an *adjacent* class: a rule keyed on an input the
matrix's single deterministic world never puts in front of a policy call (`_unknown` admitting an
extra name; task status `COMPLETED`; debate state `CLOSED`; message kind `decision`). Recorded as
**U353**. It reproduced every load-bearing number in §7 of the checkpoint independently.

**spec-auditor: PROHIBITED DRIFT NONE, 0 BLOCKING** — 1 MAJOR, 4 MEDIUM, 4 MINOR, 3 NIT. No
invariant is violated by the change; invariant 7 is *restored* rather than relocated; it confirmed
by reading all 330 lines (not by trusting the AST test) that no role read survives anywhere in
`mcp_server/collaboration_service.py`, and it hand-traced P16j/P16k/P16l against the golden matrix to
confirm round 4's three survivors are really dead. Its MAJOR is **U354**; its notable MEDIUM is
**U355**.

**Both converged on the same disposition: no code-behaviour change is required.** Every remaining
finding is a false or overstated *sentence*, or a register row that needed writing.

## 2. Corrections to statements in the checkpoint and in the committed register

| Said | Correction |
|---|---|
| §5.4 and register U352: *"Any change to any rule — widening or narrowing, deny statement or membership set — moves a cell"* | **Too strong.** True claim: no change to `_SCOPED_ROLES` or `_DIRECTING_ROLES` can pass the table. Four counterexamples were demonstrated green against all 2,331 tests. **U353**, which supersedes that sentence. |
| §5.4 and register U350: the invariant-18 case *"is pinned as such in the matrix, not fixed"* | **The mitigation does not exist.** `_open_then_close` always opens over `[W1, W2]` and always posts turns as W1/W2, so no cell has a directing role that both argued and closed; the U350 fix moves zero cells. The disposition (recorded, not fixed) is unchanged and honest; its *collateral* was overstated. **U354**. |
| §4: *"17/17 → 23/23 → 29/29 → 34/34 → 37/37 RED (rounds 1 → 2 → 3 → 4)"* | Five values under four arrows. The fifth is round 4's **remediation** (P16j–P16l), not a fifth round. |
| §2: *"the second constructor in the repo"* | **Only other *non-test* constructor.** Nineteen test constructors exist (`tests/unit/test_mcp_collaboration.py:16` and eighteen in the delegation test file). The register's own phrasing ("only production constructor") was the correct one. |
| §4 line 199 and the harness: *"a test that never mentions the policy"* | The matrix helper **constructs** `SovereignPolicy()` to build the service. The true claim — and what it was reaching for — is that **no policy method is called by the grader**. Corrected in the harness docstring; recorded for the register in **U353**. |
| U344's residue enumeration | Omits `mcp_server/sovereign_tools.py:223-226` (claimed provider/model vs authenticated identity). Best classified as provenance/identity binding (invariant 11) rather than role authority — but U344's job is to enumerate. **U357(a)**. |
| U346: *"Not live today"* | True of the **voice** half only; the worker half is live on the product path today. **U357(b)**, which also corrects "the whole `TASK_STATES` enum" (it is 9 of 11). |

## 3. What changed in the tree at round 5, and why it is not a sixth patch

**Four files, docstrings and comments only — no statement, expression, constant, signature, control-flow
line or assertion changed:** `control_plane/policy.py`, `mcp_server/collaboration_service.py`,
`tests/unit/test_collaboration_policy_delegation.py`, `tools/mutation/_op19_policy_delegation_mutations.py`.

The findings that would have required *code* changes — U355 (`authorize_debate_turn` has no role
clause, so a `voice` participant may post debate turns) and U354 (the invariant-18 closer) — were
**recorded, not patched, deliberately.** Iteration 120 set that rule before round 5 ran, for the
membership-set class; it is applied here by explicit extension to the adjacent class, and the reason
is mechanical rather than a preference: patching either rule, or widening `_matrix_world` so a voice
identity participates, **moves matrix cells**, which is a code change, which voids round 5 under
directive §18's *fix-after-validation voids it* and buys a round 6 on the same tread that produced
rounds 2, 3, 4 and 5.

### 3.1 The correction was itself reviewed, and its first draft was false

A third foreground review (read-only delta validation) was run on the uncommitted correction before
anything was committed. **It returned FAIL**, and it was right on all three counts: the new
`policy.py` sentence denied a delta the evidence records (the `voice` `open_debate` refusal string);
the new test-docstring sentence claimed no membership-set change can pass the table, which is false
for `ROLES` (adding a member moves no cell, because no identity in the world carries the new name —
`ROLES` is pinned by two other tests instead); and it cited U353/U355/U356 while the register still
ended at U352. All three were repaired before commit, using the reviewer's own proposed replacements.

A fourth read-only pass then truth-checked the repaired prose **and the six new register rows**, and
found **six more false sentences — all six in rows I had just written**: a claim that an untracked
generator would re-emit superseded text (it refuses to append while the rows exist); an "each" that
did not hold for two of the four widenings; a correct conclusion resting on a false reason; a
throwaway "so does widening in that direction" that is false for the only reachable widening; a
standing-rule citation that silently broadened the rule's class name; and a row title that
contradicted its own body two lines later ("nine rows" vs fifteen). All six are repaired, plus eight
qualifier-level overstatements the same pass flagged in the docstrings (including "all fifteen moved"
— fourteen moved, the fifteenth was deleted as provably dead, U343; and "a rule change here is now
the only way any of them can move" — a deleted call site in `mcp_server/` still moves a verdict,
which is what the harness's Group C rows exist to catch).

**This is recorded prominently because it is the unit's actual lesson.** The defect this unit kept
producing was never in the authority code — it was documentation asserting absolutes the code
falsifies, and it recurred *four times in the fixes for itself*, including twice in this correction.
The stopping rule adopted here, and the one that closes the unit: **from round 5 onward, a finding
whose repair would change the tree goes to a register row, not a patch.** That bounds the regress
without softening anything — nothing was downgraded, dismissed, or left unwritten.

## 4. Measurements — every number re-taken on the final tree, in the foreground

| Command | Result |
|---|---|
| `py -3.12 -m pytest tests/unit -q` | **1845 passed, 1 skipped, 59.63 s** |
| `py -3.12 -m pytest tests/integration -q` | **478 passed, 593.98 s** |
| `py -3.12 -m pytest tests/security tests/recovery tests/evaluation -q` | **8 passed, 10.39 s** |
| Python total | **2331 passed, 1 skipped** |
| `py -3.12 tools/mutation/_op19_policy_delegation_mutations.py` | **37/37 RED, all restores byte-identical** |
| `py -3.12 tools/evaluation/u326_before_after.py` | **base=b529314 · 19 of 34 scenarios differ** |
| `npm test` in `apps/desktop` | **pass 836 · fail 0 · skipped 0** |
| `node --test test/*.test.js` in `terminal` | **tests 216 · pass 216 · fail 0** |

The suite is split three ways because it runs ~11 minutes against a 600 s per-command ceiling;
1845 + 478 + 8 = 2331 is the whole of `tests/`. Unlike the checkpoint, the JS suites were re-run on
**this** tree rather than attributed to an earlier commit.

**One failure occurred and is not being hidden.** The first integration run of the corrected tree
returned *1 failed, 477 passed*: `test_opencode_candidate_live.py::test_live_drive_then_governed_candidate_and_merge`,
taken while a reviewer subagent was working in the same repository. Re-run alone: 478 passed. The
test alone: 1 passed in 68.03 s. It drives a live local harness on a wall-clock budget, so its
verdict is load-dependent; nothing in the round-5 change is executable, so it cannot be attributed to
the change. Recorded as **U359** — *green when the machine is quiet* is a weaker property than green,
and this loop routinely measures suites while subagents work in the same tree.

**Live provider calls made by this unit: zero**, at round 5 as before. D-LOOP-1 teardown is vacuous
for the Python work; the reviewer worktree was removed and the tree left clean.

## 5. Register rows appended at round 5

**U353** (the verdict matrix pins one world — the four demonstrated widenings; supersedes U352's
absolute) · **U354** (corrects U350: the invariant-18 case is pinned nowhere) · **U355**
(`authorize_debate_turn` has no role clause — a `voice` participant may post debate turns; invariants
24/25; recorded not patched) · **U356** (the mutation harness has no unmutated baseline, so RED means
"exited non-zero under mutation") · **U357** (accuracy corrections to U344 and U346) · **U358**
(process: unit 19.2 opened fifteen open rows that Phase 19's exit criteria — U326–U339 — do not
cover; unit 19.10 must enumerate them at the phase gate) · **U359** (the load-dependent live test).

## 6. What this correction does NOT claim

It does not claim the verdict matrix sees everything — U353 says precisely what it cannot see, and
that limit was demonstrated rather than reasoned. It does not claim the collaboration rules are
*right*: U349 (uncapped debate cost, invariant 17), U350/U354 (the self-judging closer, invariant 18)
and U355 (voice debate turns, invariant 25) are open exposures on this path, recorded and unowned by
any Phase-19 unit. It does not claim single-point-of-change across the product — `apps/desktop/main.js`
holds a fourth, divergent copy (U345). It does not claim the reviewers are exhausted; it claims that
five rounds have converged, that the sixth round's findings would not change the tree, and that
continuing to patch prose in a tested file is what keeps voiding the validation.

**Unit 19.2 (U326) closes here.** Phase 19 does not: **U328–U339 remain open**, this is unit two of
ten, no tag was created or moved (`gate/phase-19` does not exist; `product/multi-frontier-v2` still
points at `cd08878`), and the next unit is **19.3 — U328** (nothing writes into a pane that may be
showing a modal).
