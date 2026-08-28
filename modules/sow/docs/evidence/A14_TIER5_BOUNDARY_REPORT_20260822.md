# A14 - TIER-5 BOUNDARY REPORT (SOW remediation loop v2)

**Document id:** SOW_TIER5_BOUNDARY_A14_20260822
**Executor:** Ox Alpha (OpenCode runtime), implementing worker - not the adjudicator of its own work
**Window:** 2026-08-22, HEAD `a3c5481` at time of writing (loop commits 35d2f14..a3c5481)
**Mode:** every suite number below is `mode: diagnostic`. **None of it may be quoted as a gate or
boundary result.** Live legs deselected: exactly four (three U472 Ollama, one U473 OpenCode) -
constraint 9; no other deselection anywhere.

---

## 1. WHY THIS DOCUMENT EXISTS

The Tier-5 units (W-55..W-62) landed without a boundary artifact. **No Tier-5 boundary record
existed before this one** [OBSERVED: docs/evidence/ holds no such document]. This report fills that
gap from measurements taken inside the loop window (C-1..C-3) plus the triages C-8/C-9/C-10.

## 2. INSTRUMENTS (C-2 full sweep - all 18 mutation/falsification instruments)

Serial execution; pre-run worktree-clean verification STATED for every instrument (U492
compensating control); post-run clean verification equally; zero contaminated trees; zero partial
counts presented as scores (U469 rule).

| family | result |
|---|---|
| JS x5 (disarm_authority 11, orchestration 21, pane_input_bypass all, readiness_signal 26, system_pane_write 39) | RAN AND CAUGHT ALL, restores byte-identical |
| Python x12 (_op12_close, _op13_permission_mode 14, _op18c_close, _op18c_probe_path, _op18d_amendment, _op18e_electron_wiring 22, _op18e_hardening 29, _op18e_live_acceptance 34, _op18e_live_shape 11, _op19_5_write_path 29, _op19_policy_delegation 40) | RAN AND CAUGHT ALL, restores byte-identical |
| wsl_path_hermeticity_check | RAN AND PASSED (54/57 hermetic; 3 skips are DECLARED host prerequisites in their own skipif reasons) |
| _op18d_close_mutations | exit 1, 28/29 RED - the REGISTERED U446 debt, all four fingerprint elements matched (R3 "GREEN (guard does not hold)"). Instrument working; known condition reproduced |

COULD NOT START: none. CERTIFIED AN UNVERIFIED TREE: none. NEVER INVOKED: none.
One repair was required to make this true: C-1 re-pinned `orchestration_mutations.js`
(collaboration_service.py pin stale since W-59/W-61; commit `35d2f14`; anchors re-read BEFORE
re-pin - all 21 unique, O4 unmoved).

## 3. ANCHOR / INTEGRITY STATE

Register prefix proofs exact throughout the window: the `17ca5ef` blob remains a byte-prefix of the
current register after every append (checked after each register commit). Freeze set intact;
`CLAUDE.md` edited twice under section 7.1 authority with same-commit manifest regenerations
(freeze_integrity_sha256 8E604CA3... -> 2AF7F985... -> 32971BBB...; operator_signature ->
PENDING, registered at U496/U498; re-signing queued once at loop end).

## 4. CANONICAL SUITE TIMING (C-3, LHP protocol)

Three serial direct-`pytest` runs, `--durations=0`, live legs deselected:

| run | wall s | pytest s | passed | failed | skipped | exit | host at start |
|---|---|---|---|---|---|---|---|
| 1 | 697.91 | 697.09 | 2802 | 0 | 2 named | 0 | cpu 6%, 435 procs |
| 2 | 652.38 | 651.46 | 2802 | 0 | 2 named | 0 | cpu 9%, 433 procs |
| 3 | 645.77 | 644.83 | 2802 | 0 | 2 named | 0 | cpu 30%, 430 procs |

Ceiling inference (one-sided, load-robust): MIN=645.77, MAX=697.91 -> **NOT BREACHED**
(MAX <= 800 s). Neither 776.59 s nor 846 s reproduces today. Stated plainly: those were single
measurements at unknown load; no delta against them is computed; the 846 s figure has NO artifact
anywhere in the tree [OBSERVED grep]. Caveat carried: today's totals EXCLUDE the four live legs;
U480's 776.59 s INCLUDED them - like-for-like full-suite timing was not taken (constraint 9).

Contract side-by-side: pytest.ini declares 2381 passed / 1 failed / 1 skipped / 638.34 s / ceiling
800 s. Measured today: 2802 passed (+421, suite growth through Tiers 0-5), 0 failed (the recorded
failure no longer exists), 2 skipped (both named host-coupled), inside the ceiling on every sample.
Disposition PARK-OP (U480): whether to re-derive the ceiling or bound growth is an operator call;
nothing is breached on today's evidence and changing the contract now would repair a condition
nobody demonstrated.

## 5. DEGRADATION CHECK (from the MIN run)

(a) Twenty slowest led by test_live_opencode_drives_local_model_in_isolated_worktree (128.49 s),
voice_input (39.87), conductor_voice_feed (37.73), wsl_parakeet (17.82), then SEVEN rows at ~15.1 s
- the F-3/N-04 fixed Job-Object teardown tax, previously measured and ruled legitimate.
(b) Of the 29 Tier-5 tests (count DERIVED from git diff 17ca5ef..HEAD -- tests/: exactly 29 added
def-test functions across 7 files), exactly TWO appear in the slowest twenty (both
test_mcp_startup_diagnosability, 4.36 s and 2.58 s). **Tier-5 added no slow outlier.**
(c) Attribution as share, not seconds-delta: the 29 Tier-5 tests sum to 18.66 s visible =
2.89% of run total. Five-times-median threshold (median over visible aggregates 0.060 s):
346 tests exceed it, dominated by documented integration/host-coupled legs and the ~15.1 s
teardown family - no new anomaly attributable to recent tiers.

## 6. UNEXPLAINED OBSERVATIONS (not left empty)

1. Rank inversion under load: the MOST contended sample (run 3, cpu 30% at start) was the FASTEST
   (645.77 s). Within-run rank ordering is load-robust per SS5.1; cross-run totals clearly are not.
   No mechanism was identified for why contention correlated inversely here.
2. readiness_signal_mutations.js took 319.4 s while its four JS siblings took 3-52 s. Its graders
   include long-running readiness loops; whether that is intrinsic or load interaction was NOT
   decomposed - categorical verdict unaffected.
3. During C-5 calibration, nulling the store's Python `_write_lock` did NOT break exclusion: the
   concurrent opener blocked >10 s inside SQLite `BEGIN IMMEDIATE`. Exclusion therefore rests on
   TWO layers; the second was invisible until sought.

## 7. CLAIMS NOT INDEPENDENTLY VERIFIED (not left empty)

1. **Nothing in the 84 verifies that a conductor can drive a worker end to end.** The punch list is
   a code-review artifact and was never a functional acceptance list. The operator has observed the
   app does not do this. Nothing measured in this window contradicts him; Path B remains undemonstrated
   (C-10 plan queued, unexecuted).
2. The four live legs were DESELECTED today; full-suite timing INCLUDING them is unmeasured at
   current composition.
3. U495's practical blast radius on real conductor flows was probed at service level only, not
   exercised through the MCP surface end to end.
4. `codex` honoring its configured `cwd` is [REPORTED] (U483), never spawn-verified.
5. The 846 s historical figure: absence-of-artifact verified by tree search; the measurement itself
   predates this loop and was not witnessed.

## 8. METHOD DEVIATIONS (not left empty)

1. A stale external `.git/index.lock` (created 2026-08-20, 0 bytes, no git process) blocked all
   commits; removed as a DECLARED recovery act before the first commit, recorded in the loop ledger
   (single-defensible-answer recovery per the U453 discipline).
2. C-5's negative-red could not be produced through the public surface because SQLite backstops the
   Python lock (see 6.3); the addendum test is labelled CONTROL/INHERITED for the gate property and
   pins deterministic choreography instead. Recorded rather than claimed as gate coverage.
3. The executor double-appended register row U495 (stray silenced script re-run); superseded by
   appended row U497 naming the canonical block - constraint-6 letter preserved, nothing deleted.
4. One PS 5.1 parser abort (ternary) and one JSON truncation occurred before any write; retried
   cleanly. No retries of any failing test were made anywhere in the window.

## 9. PHASE-A DISPOSITIONS AT CLOSE OF WINDOW

| item | disposition | evidence |
|---|---|---|
| C-1 | CLOSED (corrective; count not incremented) | 35d2f14 |
| C-2 | MEASURED - instruments all executed, one registered debt fingerprint-matched | runs/C2_* |
| C-3 | MEASURED - NOT BREACHED; disposition PARK-OP | runs/C3_run{1,2,3}.txt |
| C-4 | CLOSED (cross-language heartbeat/staleness pin, calibrated both directions) | ab13e09 |
| C-5 | CLOSED case (a) + PARK-NEW case (b) registered U495 | 369beee, b1b8417 |
| C-6 | CLOSED (line-33 retraction + manifest + U496) | 55d5b18, e857efb |
| C-7 | CLOSED (line-51 retraction + manifest + U498) | e337978, a3c5481 |
| C-8 | MEASURED - talk-button chain fully wired; symptom = recorded non-executing states | runs/UNIT_C8_report.md |
| C-9 | MEASURED - no Tier-4 escape; antigravity auth honestly UNVERIFIED by design | runs/UNIT_C9_report.md |
| C-10 | PARKED-OP (bring-up PLAN delivered; constraint 9 honoured) | runs/UNIT_C10_plan.md |
| C-11 | this document | — |

## 10. WHAT A TIER-5 BOUNDARY WOULD STILL OWED-BE

A durable Tier-5 boundary statement needs: (1) a like-for-like full-suite timing including the four
live legs on a quiet host; (2) the live Codex bring-up of C-10 settling F2; (3) an operator ruling
on U480's ceiling and on U495's terminal-state debate policy; (4) the operator signature restored on
the regenerated freeze manifest; and (5) functional evidence that a conductor can drive a worker
end to end - which nothing in this programme measures today.

*This document records; it closes nothing that lacks evidence. It deliberately does not use the
word that previous boundary reports reached for.*