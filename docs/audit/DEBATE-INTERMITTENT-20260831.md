# utc: 2026-09-01T03:25:00Z
# producer: claude-code post-seal measurement

# Debate hostile e2e — the instability is not what the record says it is

**What this document is.** A BUILDER measurement. Not a reviewer verdict, not a gate status, not a
diagnosis. It records three runs and what they exclude. `evidence/GATE-LEDGER.json` is untouched.

**Why it exists.** `docs/RELEASE-ASSURANCE.md` has stated, across several revisions, that this
failure *"passes 9 of 9 on its own and 185 of 185 with its whole module, and fails only in the
whole-product run."* That sentence is false. It is an assurance line sitting next to a fresh cut,
and it sent four investigations down the wrong road.

---

## 1. What was measured

**Whole-product run**, `py -3.12 -m pytest .` from the repository root, at commit `69fc54b` plus
the suite's own uncommitted re-stamps (sealed as `95526a4`):

```
1 failed, 4030 passed, 4 skipped, 61 warnings, 1 error, 473 subtests passed in 1023.62s (17:03)

FAILED  modules/debate/tests/test_v1_2_1_hostile_e2e.py::test_short_interjection_does_not_suppress_speech
ERROR   modules/debate/tests/test_smoke.py::test_smoke_and_operator_controls
```

Both are in `modules/debate`. The ERROR is new against the previous whole-product run, which
reported 4,000 passed / 1 failed / **0 errors**.

**The Debate module alone**, `pytest modules/debate/tests`:

```
185 passed, 1 error in 104.89s
ERROR  modules/debate/tests/test_v1_2_1_hostile_e2e.py::test_control_echo_blocked_public_clean_turn_completes
```

A *different* test from the one that failed in the whole-product run.

**The hostile e2e file alone**, three consecutive runs, nothing else collected:

| run | result |
|---|---|
| 1 | 9 passed |
| 2 | **2 failed**, 7 passed — `test_control_echo_blocked_public_clean_turn_completes`, `test_short_interjection_does_not_suppress_speech` |
| 3 | 9 passed |

---

## 2. What that excludes

The suite is flaky **standalone**. "Fails only in the whole-product run" is falsified by run 2:
one file, nine tests, no other module collected, two failures.

This matters beyond the wording. The four causes the record lists as tested-and-ruled-out — the
state root, the repository-root `conftest.py` PYTHONPATH, a port collision with the smoke suite,
and a shared state-root configuration — are all **cross-run or cross-module** hypotheses. They
were ruled out against a question the evidence no longer supports. That is why "the cause is not
known" has survived this long: the search was in the wrong place, not insufficiently thorough.

Cross-run interference may still exist on top of this. It is no longer the whole story, and it can
no longer be assumed to be any of the story.

---

## 3. What is NOT claimed

Deliberately, because the temptation here is to name a cause that sounds right:

- **Not** identified as a product defect in Debate.
- **Not** identified as a fixture-hermeticity problem (tests leaking state into one another).
- **Not** identified as a shared port or shared state-root problem.
- **Not** attributed to load, to this host, or to anything else convenient.

All four remain open. The failing tests concern turn completion and speech suppression over
WebSocket queues, so intra-suite timing is the obvious next place to look — obvious is not
measured, and this document does not promote it.

**Nor is it claimed that Debate v1.2.1 is unsound.** It remains the best-evidenced module in the
corpus on its own record (director-accepted, cold-extracted suite, soak, hostile e2e). What is
recorded here is that one suite's *stability* is not what the assurance file says.

---

## 4. What is forbidden as a close

**Rerun-until-green does not close this.** Run 1 and run 3 above are both green, and neither is
evidence. A flake that passes two times in three will pass a confirmation run more often than not,
and treating that as a fix converts a known-unknown into an unknown-unknown.

The close is an isolated reproduction: a mechanism that makes run 2 happen on demand. Until then
the honest state is open, intermittent, cause unlocated.

---

## 5. What this document changed

`docs/RELEASE-ASSURANCE.md` carried the falsified sentence and is corrected in the same commit as
this file. `docs/audit/SYSTEM-REVIEW-20260831.md` was checked and does **not** contain it — its two
Debate references are a test-ratio figure and a listening-port observation, both still true. The
instruction to correct two documents is recorded here as having applied to one.

---

BUILDER CLAIM: No gate is submitted for reviewer evaluation. No PASS status is asserted by the builder.
