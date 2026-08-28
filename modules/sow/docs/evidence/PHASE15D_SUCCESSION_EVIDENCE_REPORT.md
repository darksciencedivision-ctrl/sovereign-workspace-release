# PHASE 15D `.succession` — EVIDENCE REPORT

**Work unit:** `phase-15d.succession` (fourth sub-step of Phase 15D; **no gate tag** — the
high-stakes `gate/phase-15d` closes at `.gate` when all sub-steps land)
**Date:** 2026-07-20 · **Iteration:** 45 · **Interpreter:** `py -3.12` (Python 3.12.10)
**Directive basis:** AUTONOMOUS_BUILD_DIRECTIVE.md §11 track 15D — *"live conductor succession:
kill the Fable-5 conductor mid-run, resume on a different backend, zero loss, then restore
selection"*
**Verdict:** **PASS_WITH_RESERVATIONS** (mock-first; every live leg OWED, not claimed)

---

## 0. Provenance — this unit began as RECOVERED CRASH MATERIAL

Iteration 44's runner died mid-unit (D-LOOP-1, the third such crash in this build). Untracked
files survived: `control_plane/orchestration/live_succession.py` plus two test files, and
uncommitted modifications to `live_flow.py` and `adapters/conductor/adapter.py`.

Handling followed the `.flow`/`.debate` precedent — **inspected, not trusted, and re-gated**:

- No orphan evidence report existed this time (unlike iter 44, where a surviving report asserted a
  gate-validator PASS that had never happened). Verified: `docs/evidence/` contained no
  `*succession*` file before this one.
- The recovered suite was green on arrival (39 tests, full suite 862). **Green was not treated as
  the bar.** Two independent reviewers were run on the recovered tree before any of it was
  believed.
- That decision was again load-bearing. **The spec-auditor returned 12 MAJOR findings and the
  gate-validator returned FAIL with 3 surviving mutants.** Three of the module's four headline
  "HONESTY RULES" did not hold as written, and a fourth was contradicted by the code on the next
  line. The recovered code's own docstrings asserted the opposite of what both reviewers found —
  the same pattern as the previous two recoveries.

Everything below describes the tree **after** those findings were fixed.

---

## 1. What this unit actually proves

A **governed conductor handover** across one interrupted run, end to end, on mock backends:

- a real MCP server, the real `Scheduler`, the real `GateEngine`, the real Phase-11
  `SuccessionManager`, the real `.flow`-gated `LiveGovernedFlow`;
- the predecessor is interrupted **between scheduling waves**, at a governed boundary, with the
  completed waves' artifacts already gated and promoted in MCP;
- the successor is a **separately-constructed adapter**, on its **own MCP session** and **own node
  id**, which **reloads all 12 conductor files from MCP** (`loaded_files == CONDUCTOR_FILE_ORDER`);
- the successor completes work the predecessor never saw (the accepted set grows);
- ACCEPTED entries are compared by **content hash read back from MCP and rehashed from stored
  bytes** — never by entry id, never trusting the publisher's own `content_hash` (I-M1);
- the succession report is published CANDIDATE by the successor and **promoted by a separate gate
  node** (invariant 18), with `operator_disposition: "pending"` (invariant 1 — gate promotion is
  not operator acceptance);
- I-X3 release-before-acquire is **observed on the real `SubscriptionGovernor`**, and an
  unobserved handoff is recorded as absent, never as correct.

## 2. What it does NOT prove — stated plainly

| Claim a reader might infer | Reality | Register |
|---|---|---|
| The successor rebuilt orchestration state from MCP | **No.** Only the CONDUCTOR is replaced. `LiveGovernedFlow`, the `TaskGraph`, `Scheduler`, workers and `_RunState` deliberately survive in-process. The `task_states` half of the zero-loss check reads that surviving object on **both** sides, so it compares it against itself. | **U48** |
| "Different backend" was demonstrated | **No.** It is a **label-difference refusal**. `capability().adapter` is the hard-coded literal `"conductor_fable5"` for every `ConductorAdapter`, so that half never discriminates; `model_name` is an attribute this module *assigns onto the backend object*. The validator built a passing report from two identical `MockReasoningBackend` objects, and another from pure strings with no backend in existence. | **U50** |
| Zero-loss `ok=True` means something was at risk | **Weakly.** Bootstrap publishes 12 conductor files as ACCEPTED, so the pre-kill set is never empty and the emptiness guard can only fire against a project this runner cannot build. Mitigated by `work_advanced`. | **U49** |
| The successor's model produced the synthesis | **No.** `_synthesize` is deterministic from MCP reads; it never calls the backend. The successor spends zero model calls and its leg honestly reads `skipped`. | **U46** |
| A live succession is merely un-run | **No — it is OWED.** This unit has **no live path at all**: no `attempt_live_*`, no `LiveAuthorization`, no supervised spawn. | **U51** |
| `restored_selection` means a fable-5 conductor is running | **No.** The selection RECORD is restored; nothing is re-bound. The conductor executing at the end is the successor. | **U52** |
| A killed conductor cannot act | **Not structurally.** `McpClient.call` auto-reconnects, and `read_accepted`/`publish_acceptance_packet` don't check `_started`. | **U53** |

**No live provider call was made** (R8 §6 [OPERATOR] live-terms cannot be self-discharged by the
loop, §10.4). `config/live_operation.json` was **not written** by this unit (mtime
`2026-07-19 09:38:36`, hours older than these files; absent from `git status`).

---

## 3. Findings fixed in this unit

### From the gate-validator (FAIL → fixed)

| # | Finding | Fix |
|---|---|---|
| V1 | **A kill that never happened produced a gate-ACCEPTED succession.** With `close()` neutered, the runner published the claim *"the conductor was replaced mid-run with no loss of gated project state"* while `predecessor_dead.is_active` sat at `True` in the trace. `_death_evidence` **recorded** liveness and nothing ever **checked** it. | `run()` now RAISES `SuccessionError` if `is_active` survives `close()`. Mutant **A** KILLED. |
| V2 | "Structurally provable" different-backend claim is false. | Rewritten throughout as a label-difference refusal; U50 opened. |
| V3 | **Surviving mutant (M13):** with `swap_conductor`'s rebind removed, the **closed predecessor** synthesized and published the acceptance packet — all 120 tests passed. The packet's own `synthesized_by` cannot detect this (same constant for both). | New test pins packet authorship to the successor's node id via **MCP provenance**, which the author cannot forge. Mutant **I** KILLED. |
| V4 | Surviving mutant: `_death_evidence["is_active"]` could be decoupled from real liveness. | Pinned on a **live** adapter, where `is_active=True` while `not ready=False` — the post-kill pair alone could not discriminate. Mutant **G** KILLED. |
| V5 | Surviving mutant: resume-buys-extra-waves unpinned. | Pinned — and required a **strictly sequential** 3-task chain plus a bound patched below the chain length, because quiescence normally pre-empts the bound (`_max_waves(n)=n+1` vs chain `n`). Mutant **J** KILLED. |
| V6 | `test_the_successor_synthesized_the_packet_...` claimed more than its body pinned. | Renamed to `test_the_packet_covers_pre_and_post_kill_work_and_the_swap_is_recorded`; the authorship claim moved to the test that actually proves it. |

### From the spec-auditor (12 MAJOR)

| # | Finding | Disposition |
|---|---|---|
| M1 | Successor inherits all in-process state; docstring claimed the opposite. | Docstring **corrected**; limit recorded as **U48**; `task_states` checks explicitly labelled non-evidential. |
| M2 | §19.1 staleness computed then **ignored** — `run_waves()` ran unconditionally on the next line. | **Now enforced**: a failed checklist refuses the successor before it assigns work. Mutant **B** KILLED. |
| M3 | Anti-vacuity guard structurally unreachable. | **Mitigated**: new `work_advanced` check; durable claim gated on `ok AND work_advanced`. Mutants **C**, **D** KILLED. **U49**. |
| M4 | Different-backend overclaim. | Same as V2. **U50**. |
| M5 | Hard-coded vendor label `conductor_fable5`/`frontier`/`subscription_backed` in `capability()`. | Recorded (**U50**); the *fix* touches 15B-gated `adapters/conductor/adapter.py` capability semantics and is deferred to `.gate` rather than silently widening this unit. |
| M6 | `restored_selection` asserts a `claude_code` identity for a run with no vendor CLI. | **Mitigated**: `restored_selection_note` added to the artifact. Mutant **H** KILLED. **U52**. |
| M7 | Hard-coded `"mock_reasoning"` adapter label on the generic path. | **Fixed**: taken from the successor's own `capability().adapter`. |
| M8 | No supervisor participates; `spawned_by_supervisor=True` self-attested. | Recorded as part of **U51** (no live/supervised path exists here). |
| M9 | Silent last-write-wins on report promotion. | **Fixed**: a non-applied promotion raises with the conflict (invariant 13). Mutant **F** KILLED. |
| M10 | **U46/U47 cited in code but existed in no register.** | **Written** (U46, U47), plus U48–U53; **U40 amended** (it enumerated two envelopes; `succession_report@1.0` is a third). |
| M11 | The two stated limits were not the load-bearing ones. | The load-bearing ones are now U48/U49/U50/U51; U47's imprecision corrected. |
| M12 | Module advertised live legs/binding that do not exist. | Header **corrected**; **U51** opened; mock helpers now **refuse** a vendor backend (mutant **E** KILLED). |

MINOR also fixed: blanket `except` flattening governance refusals into environment skips (new
`governance_refusal` flag); `published=True` regardless of gate verdict (new `report_verdict`);
construction outside the teardown guarantee (moved inside `try`; predecessor closed in `finally`);
fabricated `("acquire","release")` ordering where only "no release observed" was witnessed.

---

## 4. Verification — real command output

**Mutation testing** (throwaway harness, in-repo per §2.5, **deleted before commit**, not
committed — consistent with `.flow`/`.debate`):

```
[KILLED ] A: kill refusal disabled
[KILLED ] B: staleness enforcement disabled
[KILLED ] C: work_advanced dropped from the durable claim
[KILLED ] D: work_advanced always True
[KILLED ] E: vendor-backend guard disabled
[KILLED ] F: lost-CAS promotion ignored
[KILLED ] G: death evidence decoupled from real liveness
[KILLED ] H: restored_selection_note removed
[KILLED ] I: swap_conductor omits the conductor rebind
[KILLED ] J: resume buys extra waves

restored byte-identical: True
SURVIVORS: none
```

Four of those ten **survived their first run** (C, F, G, J) and are only enforced because the
harness caught them — including my own new guards. Recorded because the alternative is claiming
enforcement that isn't there.

**Test suites:**

```
874 passed, 61 warnings in 186.92s          # full pytest, py -3.12 (was 862 on arrival, 823 at .debate)
51 passed in 17.23s                          # succession subset (was 39 on arrival; +12)
tests 183 | pass 183 | fail 0                # node --test (untouched by this unit — all changes are Python)
```

**Frozen set / scope:**

```
freeze check OK: no drift in FROZEN set against recorded manifest
git status --short docs/canonical/ schemas/   ->  (empty)
```

Canonical hashes intact: `CC414372` / `8C9B7240` / `668089B5` / `6D3FD03B`.

**Mock-first / §2.2:** `subprocess` appears nowhere in `live_succession.py`; the integration suite
bans `subprocess.Popen` (below anything patching `subprocess.run`) and observes `spawned == []`. No
credential is read, stored or transmitted. Precisely stated (the flat "no credential handling"
phrasing was corrected in `.debate` and the correction stands): the module **does** mint internal
MCP identities via `srv.credentials.issue` — in-process test tokens, access not authority
(invariant 7), never a provider credential.

---

## 5. Substitutions (directive §6)

| Criterion | Substitution | Recorded |
|---|---|---|
| "kill the **Fable-5** conductor" | Mock backends labelled `mock-fable5` / `mock-successor`. No vendor CLI participates. | U50, U51 |
| "resume on a **different backend**" | Two `MockReasoningBackend` instances differing by an assigned `model_name`. Genuinely different: adapter object, MCP session, node id. Not different: backend class. | U50 |
| "**live** conductor succession" | No live path exists in this unit. OWED, not skipped-with-record — there is nothing to skip. | U51 |
| One bounded live debate / live models | Out of scope for this sub-step; owed at `.gate`/15E. | — |

Never presented as a real-provider result.

---

## 6. Reservations carried to `.gate`

1. **U45 remains BLOCKING** for `gate/phase-15d` and is untouched here.
2. **U48–U53** all land on `.gate` (U53's adapter-side `_started` checks are small and contained;
   U50's `capability()` fix touches 15B-gated code).
3. `live_flow.py` — `.flow`-gated — was **restructured** by this unit (`begin`/`run_waves`/`finish`/
   `swap_conductor`). The validator proved behavioural equivalence: an identical 4-scenario
   structural probe hashed **identically** pre- and post-refactor
   (`c7a28fb6…4ef200`), and wave budgeting, quiescence and the plan-blocked path were each
   separately pinned. Noted because U45 previously declined a comparable edit on §3.6 grounds; the
   inconsistency is now disclosed rather than left implicit.
4. `ruff` unavailable on this host (pip out of scope), so the ruff-clean rule is **UNVERIFIED** for
   this unit — same standing gap as `.flow`/`.debate`.
5. `apps/desktop/package-lock.json` remains untracked and was deliberately **not** swept into
   either commit (it predates this unit).

---

## 7. Files

| File | Change |
|---|---|
| `control_plane/orchestration/live_succession.py` | NEW — succession runner, zero-loss comparison, report builder |
| `control_plane/orchestration/live_flow.py` | MODIFIED — `run()` decomposed into `begin`/`run_waves`/`finish`; `swap_conductor` |
| `adapters/conductor/adapter.py` | MODIFIED — `is_active` (liveness) and `backend` (read-only) properties |
| `tests/integration/test_live_succession.py` | NEW — 22 tests through a real MCP server |
| `tests/unit/test_live_succession_zero_loss.py` | NEW — 29 pure tests (incl. a 7-case parametrised spend-merge) |
| `docs/registers/UNRESOLVED_ISSUE_REGISTER.md` | U46–U53 + U40 amendment |

**Independent review:** gate-validator (sub-step) FAIL → all blocking findings fixed and
re-verified by mutation; spec-auditor 12 MAJOR / 9 MINOR / 3 NIT → all MAJOR addressed or recorded
as an open register item with a named owner.
