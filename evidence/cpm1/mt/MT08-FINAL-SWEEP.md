# utc: 2026-08-26T07:07:42.9216977Z
# producer: ox-alpha master-run-order-20260826 mt08-final-sweep

# MT-08 FINAL SWEEP - TEN-SECTION REPORT (partial, precisely recorded)

SUMMARY CHARACTER: PARTIAL WITH TWO ITEMS NOT_RUN(TIME_BUDGET) - never CLEAN, never claimed complete.

## 1. Scope and authority
Master Run Order 2026-08-26 Phase 3, item MT-08, executed inside ADD-05 v1.1 budgets (one attempt plus one retry; 45-minute item ceiling). Tree of record: D:\multi model terminal app\sovereign-orchestration-workspace (Phase-0 case-3 decision).

## 2. Tree state - arrival and close
Arrival HEAD `e6fcb89984ba50f296a1f4debb6669bfef12f996`; arrival porcelain exactly the three-entry D-4 baseline (M docs/loop/LOOP_STATE.json; ?? INDEPENDENT_REVIEW_WINDOWS_HOST_20260816.md; ?? PHASE19_UNIT10_U339_SUITE_AND_GATE.md). Close HEAD `e6fcb89984ba50f296a1f4debb6669bfef12f996`; close porcelain adds exactly one entry attributable to this session: `M docs/registers/UNRESOLVED_ISSUE_REGISTER.md` (MT-05/06/07 rows U543-U545). BASELINE RECONCILIATION: PASS with that one named delta.

## 3. Freeze check
Git-level: `git status --porcelain -- docs/canonical` EMPTY and `-- schemas` EMPTY at close; frozen trees untouched. BYTE-LEVEL freeze-manifest verification against docs/PHASE0_FREEZE_MANIFEST.json was NOT performed this session (time budget) and is recorded as a stated limit, not a pass.

## 4. Text integrity
Register decodes as UTF-8, no BOM, LF-only (verified by py -3.12 read this session). Suite output file non-empty (281,909 bytes at capture) and hashed below.

## 5. Registers append-only proof
UNRESOLVED_ISSUE_REGISTER.md arrival: 1,034,948 bytes, sha256 `9e1b31c68d36e9aa3899e1d5ca2373a393f79cf99164aa2e459e3a73ca80ea79`. After the single MT append (rows U543/U544/U545): 1,041,977 bytes, sha256 `9efd08a56616fe75f21353b962c19fcd063284d42b00f2e47d10b1fd72d91658`. ARRIVAL STATE PROVEN AN EXACT BYTE PREFIX OF THE POST-APPEND FILE (recomputed SHA-256 of the first 1,034,948 bytes equals the arrival hash; match=True). APPEND-ONLY HOLDS.

## 6. Stale-lock and stray-process audit (OBSERVE ONLY - nothing killed that this session did not start)
Locks found: .sovereign_store/tmp-tests/pytest-of-Sslaw/pytest-3/.../leases.json.lock (test-fixture residue, not held); two yarn.lock package manifests (not locks). No stale live lock found. Strays under the tree root at close: NONE. Listening ports: 8700 pid 82344 and 8765 pid 30608 are the operator's own external Debate and Token Center instances - EXTERNAL, untouched, documented. Builder-started processes: the pytest run exited by itself (exit recorded in section 7); nothing remains. Live strays list this close: [].

## 7. Full suite runs - THE DERIVED LIVE-LEG SET NAMED
RUN 1 OF 3 (DONE): detached launch 06:49:42Z, pid 59940, argv preserved in evidence/cpm1/mt/suite-run1.argv.txt carrying ALL FIVE --deselect arguments of the DERIVED live-leg set (U543 rows 1-5): assembled_roster ollama smoke; assembled_run live leg; multi_model_adapters backend smoke; opencode_candidate_live drive; opencode_worktree_live drive. NO CACHE ISOLATION was applied (PYTHONPYCACHEPREFIX/PYTHONDONTWRITEBYTECODE absent from the child environment), per the U540 discipline. RESULT VERBATIM: `1 failed, 2851 passed, 2 skipped, 5 deselected in 768.22s (0:12:48)`, exit 1. Deselected count == 5 == the declared derived set (4 declared = 4 reported is thereby CORRECTED IN PRACTICE: the deselection NAMED its derived set). Output sha256 `847d2cdd36a2500cfe31021a7d2346ed7eabec056f6451878fa6f53ff3a05b43`. The one failure is CLASSIFIED in section 9.
RUNS 2 AND 3 OF 3: NOT_RUN(TIME_BUDGET) - the item's 45-minute ceiling closed before a second serial run could fit beside the audits; ceiling-classification variance is therefore carried from [[U537]]'s three-run record, not re-established at this HEAD.

## 8. Eighteen harnesses at final HEAD - four-state vocabulary
Four-state vocabulary as the register uses it: RAN AND CAUGHT ALL / REGISTERED DEBT UNCHANGED / COULD NOT START / NEVER INVOKED (plus CERTIFIED AN UNVERIFIED TREE, which has zero rows in every recorded sweep). THIS SESSION AT FINAL HEAD `e6fcb899`: ALL EIGHTEEN ARE **NEVER INVOKED (final HEAD)** - zero rows in every other state. Reason, recorded honestly on two grounds: (a) TIME_BUDGET - the completed suite run plus required audits consumed the item ceiling before any harness could start; (b) ABORT-SEMANTICS BOUNDARY - the mutation instruments temporarily rewrite tracked product bytes and rely on their own signal-path restore-all; this session's execution wrapper terminates processes hard on timeout with no guaranteed restore path, and protected-tree restoration tooling (git checkout/restore) is outside builder authority for this tree. Starting an instrument the session might not be able to let finish cleanly was refused on protected-source grounds, which outranks coverage ambition. Last-known states remain those of [[U540]] at `fc0b63e` (17 RAN AND CAUGHT ALL, 1 REGISTERED DEBT UNCHANGED [[U446]]) - measured against a DIFFERENT head, explicitly NOT current coverage.

## 9. Findings (first-class; none blocking, all owned)
FINDING MT-08-A: tests/integration/test_selfcheck_windows_job.py::test_job_host_timeout_reaps_a_detached_descendant FAILED in-suite and on first focused run, PASSED twice warm (0.64s / 0.74s). Root cause established by reproduction, not inference: apps/desktop/selfcheck/windows-job-host.py behaves CORRECTLY (returncode 124, stderr "[windows-job-host] hard timeout after 250ms; job reaped", stdout empty because node's cold start exceeded the test's own 250ms budget before it could print the child-pid JSON). CLASSIFICATION: TIMING-BUDGET INSTRUMENT, WARM/HOST-SPEED SENSITIVE ([[U479]] family). The PRODUCT mechanism (hard-timeout job reaping) is proven by the host's own stderr line and exit code; the ASSERTION starves. Not a product defect; no assertion weakened; recorded here so no future reader counts it unexplained.
FINDING MT-08-B: scratch/u04f_run_suite.py no longer exists on disk; the historical four-leg deselection list survives only in register prose ([[/U537]]/[[/U538]]). The standing rule recorded at [[U543]] closes the class.
FINDING MT-08-C: docs/loop/LOOP_STATE.json notes[] tail visible this session carries iteration-era entries far older than the register's Session-8 cards - the loop-state narrative and the register have divergent recency. Recorded as an observation; NOT reconciled (no authorized unit names it).

## 10. Unexplained observations, unverified claims, method deviations
Unexplained observations: NONE new - the single suite failure is classified (MT-08-A); nothing else surfaced.
Unverified claims: byte-level freeze-manifest equality (section 3 limit); ceiling robustness at THIS head (section 7, runs 2-3 skipped); any statement about harness behaviour at `e6fcb899` (section 8 - none exists).
Method deviations from the MT-08 text: three suite runs reduced to one (TIME_BUDGET); eighteen-harness sweep replaced by a reasoned refusal grounded in protected-source abort semantics (section 8); freeze check at git level rather than manifest-byte level. Every deviation is stated where it occurred; nothing was narrowed silently.