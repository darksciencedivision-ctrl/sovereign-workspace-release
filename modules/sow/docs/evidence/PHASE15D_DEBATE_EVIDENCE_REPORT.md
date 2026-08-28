# PHASE 15D `.debate` — EVIDENCE REPORT

**Work unit:** `phase-15d.debate` (sub-step 3 of 5 in Phase 15D: `.selection` → `.flow` →
**`.debate`** → `.succession` → `.gate`)
**Date:** 2026-07-20 · **Iteration:** 44 · **Status:** PASS (sub-step)
**Tag:** none. `gate/phase-15d` is a HIGH-STAKES phase gate and closes only at `.gate`, when all
five sub-steps have landed and the mandatory independent gate-validator confirms the phase.
**Governing directive:** `AUTONOMOUS_BUILD_DIRECTIVE.md` §11 track 15D, loop protocol §3,
substitution rules §6, honesty §10.4.
**Work commit carried by this report:** `bf9b6d2`

---

## 0. Provenance — this unit's work was RECOVERED, then re-gated from scratch

Iteration 43 crashed mid-unit (runner constraint D-LOOP-1). Untracked new files for
`phase-15d.debate` survived in the working tree, **including a fully-written evidence report
claiming a passed gate-validator run, a passed spec-audit, and specific mutation statistics.**

That report was **not trusted and has been replaced by this one.** No review in it was observed in
this session, and its test counts were provably wrong against the tree it claimed to describe
(it stated 789 total / +87 / 53 unit + 34 integration; the tree at that moment measured
797 / +95 / 60 / 35). The recovered CODE was inspected, re-reviewed and re-gated here.

**That decision was load-bearing.** Two independent reviewers, run fresh against the recovered
tree, both found a **MAJOR defect in the unit's central honesty claim** — the one thing this unit
exists to provide. The prior report asserted the opposite of the truth about exactly that claim
(§4). Had the recovered material been trusted, a defect that lets a mock be published as a
real-provider result would have been committed under an evidence report certifying it correct.

---

## 1. What this unit delivers

ONE bounded debate driven through the **live-capable model binding**, MOCK-FIRST. The Debate
Service itself already existed and was gated at Phase 7 (`gate/phase-7`); this unit did **not**
re-implement it. It adds only what 15D needs on top:

1. `BackendDebater` — a `Debater` backed by any `Backend`, so the same governed debate runs on a
   mock backend or on the live `claude_code` CLI **with no branch in the service**.
2. A **fail-closed statement parse** — a model reply that is not well-formed becomes a recorded
   refusal carrying NO citations (hence UNSUPPORTED), never a fabricated evidence ref.
3. **Per-debater leg classification** and a report that refuses an unbacked `live` claim, reusing
   the `.flow` vocabulary (`ATTEMPTED_LEG`, `VALID_LEGS`, `OPERATOR_DISPOSITION_PENDING`) rather
   than inventing a second one (the recorded `.flow` constraint).

**New:** `control_plane/orchestration/live_debate.py`, `tests/unit/test_live_debate.py`,
`tests/integration/test_live_debate_flow.py`.
**Modified:** `adapters/model_adapter.py` (read-only `backend` property on `ModelWorkerAdapter`, so
a governed caller binds the backend of a node the **supervisor** spawned rather than constructing
its own and bypassing the live-spawn gates); `adapters/frontier/claude_code.py` (new
`reported_model_at_call` freshness stamp — see §3); `docs/registers/UNRESOLVED_ISSUE_REGISTER.md`
(U37–U45 recorded).

---

## 2. Exit criteria and verdicts

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | ≤5 rounds (invariant 14), over-cap **refused** not clamped | PASS | validator mutants "clamp at the caller" and "clamp in `_validate_request`" both KILLED; removing the `RoundManager` clamp is killed by the full suite (Phase-7 defence-in-depth intact) |
| 2 | Evidence-cited; unresolved/fabricated citation ⇒ UNSUPPORTED | PASS | over a REAL MCP server and the REAL `EvidenceManager`; mutants "non-JSON reply fabricates a citation", "empty reply becomes an assertion", "out-of-scope refs silently kept" all KILLED |
| 3 | Dissent preserved **verbatim** (invariant 15) | PASS | mutants "smoothed summary", "suppressed", "truncated to first position" all KILLED |
| 4 | Budgets are HARD caps; clean exhaustion cutoff (invariant 17) | PASS, one gap | budget + per-caller quota proven (cross-debate quota binding after `CostGovernor` was made injectable). **The global concurrent cap is plumbed but never exercised** — debates run strictly in sequence. Self-disclosed in the test file. |
| 5 | Non-conductor caller (§2.8); invariant 18 | PASS | caller `worker-A`/role `worker`; mutants "<2 participants", "shared backend", "duplicate ids", "role whitelist removed" all KILLED |
| 6 | Driven through the governed live binding; unmet gate ⇒ skip-with-record, NO live call | PASS, one gap | every participant spawned via `spawn_claude_code_terminal` (all five gates). Gates 1/2/3/5 exercised; **gate 4 (CLI presence) is not exercised through this entrypoint** — tests inject a backend. |
| 7 | Leg honesty; vocabulary REUSED from `live_flow` | PASS **after a FAIL and fix** | see §3. Vocabulary imported, not redeclared; `live_flow.py` byte-unchanged. |
| 8 | No live call, no credentials, no canonical/config drift | PASS | §6 |
| 9 | Teardown inside the unit; I-X3 never wedged (D-LOOP-1) | PASS **after two coverage gaps** | §5 |

**Test totals (measured on the final tree, `py -3.12`):** **823 passed / 0 failed**, up from
**702** at `.flow` — **+121**, all of them in this unit's two new suites: **83 unit + 38
integration = 121** (collected node counts, including parametrisation).
Product JS unchanged: **149 pass / 0 fail** (`node --test terminal/test/*.test.js
apps/desktop/test/*.test.js`) — this unit touches no JS.

---

## 3. The MAJOR defect, and the fix

**Both reviewers, independently, found that a `live` leg was reachable with no live call.** `live`
is this unit's assertion that a real provider actually ran; publishing it for a run that did not is
exactly what §6/§10.4 forbid. Three routes:

1. **Subclass permissiveness.** `_is_vendor_cli_backend` used `isinstance`, which accepts a
   subclass. The spec-auditor found the proof **inside this unit's own integration suite**: a test
   defined `class _ReportingCli(ClaudeCliBackend)` whose `generate` spawned no process and set the
   checkpoint itself, asserted `legs["worker-A"] == "live"`, and its docstring called that *"The
   ONLY path to a `live` leg."* A mock, asserted as a real-provider result.
2. **No liveness scoping.** A genuine `ClaudeCliBackend` with `calls == 0` and `reported_model`
   set by hand classified `live` — the `live` branch never consulted the counted-call evidence.
3. **Staleness.** `reported_model` is never cleared and `calls` is a LIFETIME counter, so a backend
   reused from an earlier debate — every call in *this* one having failed — still presented a
   verified checkpoint for a debate in which nothing succeeded.

The prior evidence report asserted the opposite (§4).

**Fix.** `ClaudeCliBackend` gains `reported_model_at_call`, stamped inside `generate` **only** when
the CLI actually reported a checkpoint, so a checkpoint is datable to a specific successful call.
`verification_for(backend, *, calls_before)` now requires **all** of: exact type
(`type(b) is ClaudeCliBackend`, not `isinstance`); a non-blank **string** checkpoint; an `int`
(non-`bool`) stamp **strictly greater** than a bind-time `calls` snapshot; and evidence a call was
spent. `calls_before=None` can never verify — absence of evidence is not evidence.
`attempt_live_debate` snapshots the call count at bind time and threads it through every leg and
verification site, so every judgement describes **this debate**, not the object's lifetime.

**Consequence, accepted deliberately:** a `live` leg is now **unreachable end to end without
spawning a real `claude` process**, so no test in this build produces one — pinned by
`test_no_leg_in_this_MOCK_FIRST_suite_can_reach_live`. The positive `live` contract is tested only
at the unit level on the classifier, with docstrings stating plainly that this is a
classifier-contract test and not evidence anything ran live. This is the §10.4 posture: the same
shape `.flow` used when it made `live` unrepresentable for legs it could not back.

**What the fix does NOT do, recorded as U43 rather than claimed away.** Exact type constrains an
object's CLASS, not its behaviour. The validator confirmed three deliberate-falsification routes
survive and cannot be closed in-process: forging both instrumentation fields on a genuine backend;
reassigning `__class__`; replacing `generate` on a genuine instance. Every ACCIDENTAL and
mock-SHAPED route is closed (subclass, duck type, renamed class, metaclass `__instancecheck__`
liar, `__getattr__` proxy, attribute injection, stale checkpoint, unstamped checkpoint, bool/int
confusion — all verified refused). The docstrings were rewritten to claim exactly this and no more,
after the validator caught an earlier version still asserting "only the real class, whose
`generate` is the one that actually runs the CLI" — which the `__class__` and instance-`generate`
attacks disprove.

---

## 4. All review findings

Two full review rounds by an independent `gate-validator` and an independent `spec-auditor`, each
run twice (once on the recovered tree, once on the fixed tree).

### Round 1 — on the RECOVERED tree

| Finding | Source | Disposition |
|---|---|---|
| **MAJOR — a `live` leg reachable with no live call** (3 routes, §3) | both reviewers | FIXED (§3) |
| **MAJOR — the recovered report's refutation was invalid.** It claimed three spoof backends were refused; none of the three inherits `ClaudeCliBackend`, so the `isinstance` failure was tautological and probed nothing. A successful refutation was sitting in the same changeset. | auditor | Report REPLACED (this document) |
| Non-string `model` reached a live leg (`str(123).strip()` is truthy) | validator | FIXED — `isinstance(model, str)` guard + 8-case parametrized test |
| Guard/emit asymmetry: guard used `verification.get`, emit used `node in verification`/`[]` — a mapping whose `get` and `__contains__` disagree emitted a live leg with an EMPTY checkpoint map | validator | FIXED (see round 2 for the complete fix) |
| Deleting `_teardown()` on the partial-spawn-failure path survived all 95 tests (the D-LOOP-1 I-X3 wedge) | validator | FIXED — allowance test now asserts `in_use == 0` / `active == []` |
| Unbounded model/CLI text into immutable artifacts | auditor | FIXED — `_bounded()` with a MARKED truncation |
| Role-whitelist rationale rested on a threat that does not exist (`SovereignPolicy` already refuses a gate promoting an entry it authored) | auditor | FIXED — rationale withdrawn in the module *and*, in round 2, in the two test docstrings that still repeated it |
| Module header claimed "nothing here spawns a `claude` process" — false with `backend=None` | auditor | FIXED — header now states the real guarantee |
| >2 debaters structurally impossible (MAX_ALLOWANCE=2); inv-18 backend-identity check inert on the live path (all live specs use `backend=None`) | auditor | RECORDED — U44 / U38 |
| Test-count claims in the recovered report wrong in four places | validator | Superseded by this report |

### Round 2 — on the FIXED tree

| Finding | Source | Disposition |
|---|---|---|
| **MAJOR — the demotion reached `legs` but not `debater_models`.** `debater_leg` demoted the contradictory case (checkpoint dated to a call the counter says never happened) to `skipped`, but `verification_for` never consulted `calls`, so the artifact published `legs: {"worker-A": "skipped"}` **and** `debater_models: {"worker-A": {"verified": true}}` — the weaker claim in one field, the stronger in the field that carries the evidence. | auditor | FIXED — spend check moved INTO `verification_for`; plus `_assert_debate_legs_honest` now enforces the **reverse** direction (a checkpoint record on a non-`live` leg is refused) |
| Fix incomplete: `build_debate_report` still made TWO `verification.get(node)` calls (guard + emit), and the comment claimed "One lookup, one truth" | validator | FIXED — resolved ONCE into a snapshot passed to both; test asserts exactly one lookup per node |
| Docstrings still overclaimed: exact type does not imply the real `generate` (`__class__` reassignment, instance-level `generate` replacement both reach `live`) | validator | FIXED — docstrings narrowed; U43 widened to name all three routes |
| Module header misattributed the freshness guarantee to `build_debate_report` | auditor | FIXED — header now states exactly which function holds which rule |
| `_MAX_RECORDED_DETAIL_CHARS` comment claimed a bound on model output, but `position` — the largest model-controlled field, and the one in the frozen record — was unbounded | auditor | FIXED — `position` bounded at 2000 chars with a MARKED, NOTED truncation; short positions carried verbatim (inv 15) |
| `ran` comment claimed derivation-from-evidence "never from which branch"; the success paths return `ran=True` as a branch constant (reachable with a zero-round budget) | auditor | FIXED — comment now states the real split; `ran` means "the debate ran", spend lives in `legs` |
| Two test docstrings still asserted the withdrawn gate-role threat | auditor | FIXED |
| A test docstring cited `live_flow._leg_for_backend` as "the same non-spoofable rule" — false in both halves | auditor | FIXED — claim withdrawn, U45 recorded |
| Mutant M9: `_teardown()` deleted on the GENERIC-exception path survived all 113 tests | validator | FIXED — new test |
| Mutant M13: `_bounded` made an identity function survived all 113 tests (fix had ZERO coverage) | validator | FIXED — three new tests |
| **MAJOR — the same defect remains in `live_flow` / `selection.py` / `propose_plan`, feeding the ACCEPTED-promotable acceptance packet** | auditor | **NOT fixed — recorded as U45, BLOCKING for `gate/phase-15d`.** See §7. |
| U37–U43 were cited in code but existed in NO register | auditor | FIXED — U37–U45 written to the unresolved-issue register |

**Findings against my own tests, all rewritten rather than argued away:** the vacuous I-X3 loop
(reused node ids, so it passed with zero releases); a tautological deepcopy assertion; a
self-referential refusal-marker assertion; a test name claiming the global cap while the body
proved the per-caller quota; and — in round 2 — a test whose **premise was wrong**
(`test_ran_reflects_a_backend_that_was_already_spent...` asserted that another debate's lifetime
spend should make THIS debate `ran=True`, on the grounds that over-reporting spend is the honest
direction). Over-reporting is the safe direction for *whether* a call was spent; it is not a
licence to bill this debate for another's calls. Rewritten to per-debate semantics.

---

## 5. Mutation testing

Run by me and, independently, by the validator; every mutated file restored and verified
sha256-identical.

- **Validator, round 1 (recovered tree):** 35 mutants, 34 killed, 1 survived — M03, the
  partial-spawn teardown gap, a real coverage hole (fixed).
- **Validator, round 2 (fixed tree):** 21 mutants, 18 killed, 3 survived — M9 (generic-exception
  teardown) and M13 (`_bounded` uncovered), both real gaps now closed with tests; M14 assessed
  EQUIVALENT.
- **Builder, final:** 10 mutants over the fix surface — subclass-permissive `isinstance` restored;
  freshness check dropped; non-string model accepted; teardown deleted on the generic-exception
  path; `_bounded` neutered; `verification_for` spend check dropped; reverse-direction guard
  removed; verification resolved per-lookup again; position bound removed — **all KILLED**.
- **An EQUIVALENT-mutant claim I made, and the reviewer REFUTED.** I claimed that removing
  `spent and` from `debater_leg`'s live branch was equivalent, because `verification_for` applies
  the identical check internally — and asserted that categorically in the code. It is false. The
  two functions read the call counter **separately**, so a counter that advances between the reads
  (a concurrent call landing mid-classification) makes them disagree, and the `and` takes the
  earlier, lower — fail-closed — reading. Without it that backend classifies `live` on the strength
  of a call that had not happened when the leg was judged. The claim is withdrawn, the code comment
  now says the opposite, and the case is pinned by
  `test_the_live_branch_takes_the_EARLIER_reading_of_a_moving_counter`. The mutant is now KILLED.
- **A second reviewer-found gap in my own coverage:** the bool exclusion in the freshness-stamp
  guard was unpinned. The test used `calls_before=5`, where `True` (== 1) is rejected by magnitude
  (`1 <= 5`) rather than by the bool guard, so its docstring described a case it never constructed
  and a mutant removing the guard survived. Rewritten to `calls_before=0`, where the guard is the
  only thing that rejects `True`. Mutant now KILLED.
- **The throwaway mutation harness was DELETED, not committed.** It had drifted against the final
  tree (5 of 28 anchors missing, including three core honesty mutants) and contained none of the
  final fix-surface mutants, so committing it would have been a misleading artifact implying
  coverage it no longer had. Consistent with `.flow`/`.selection`, whose harnesses were also not
  committed. The mutants above are described precisely enough to re-derive.

**Refutation attempt on the fixed honesty claim: PARTIALLY SUCCEEDED, and the code now says so.**
Every accidental and mock-shaped attack was refused; the three deliberate-falsification routes
succeeded and are recorded as U43. The earlier claim that refutation "FAILED" is withdrawn.

---

## 6. Prohibitions and frozen-set check (§2)

- **No live call.** Instrumented spawn ban over both new suites, hooked at `subprocess.Popen` —
  *below* any `subprocess.run` a test patches for itself: **`SUBPROCESS_SPAWN_COUNT: 0`**, 121
  passed. Ban proven **load-bearing** by a control run on `tests/integration/test_mcp_separate_process.py`
  (count 1). Tests needing the real `ClaudeCliBackend` stub only its transport, so the adapter's own
  `generate`/parse/stamp path runs while spawning nothing.
- **No credential handling (§2.2).** The module imports no `os`/`subprocess`/`socket`/`urllib` and
  calls no `open()`. It does mint **MCP** credentials via `server.credentials.issue` — internal
  node identity, not a provider credential; the flat claim "no credential handling" in the prior
  report was imprecise and is corrected here.
- **`config/live_operation.json` NOT created or modified** (mtime `2026-07-19 09:38`, hours older
  than this unit's files); `git ls-files config/` shows only `.example.json`; gitignored.
- **`docs/canonical/` untouched**; frozen hashes `CC414372 / 8C9B7240 / 668089B5 / 6D3FD03B`
  verified intact by the validator.
- **`control_plane/orchestration/live_flow.py` byte-unchanged** (`git diff --exit-code`, rc 0).
- **15B regression check:** 194 claude/conductor/frontier/model tests pass; the `claude_code.py`
  change is purely additive and `extract_reported_model` is untouched.
- No push, no remote, no purchase, no schema added to the frozen `schemas/` set.

---

## 7. Substitutions and honest limits (§6, §10.4)

- **MOCK-FIRST; no live call was made.** The governing gate is the R8 §6 `[OPERATOR]` live-terms
  confirmation, which the loop cannot self-discharge. Every live gate still ran — a mock proof
  needs an authorized `live_auth` and confirmed operator terms exactly as a live run does. **No
  live-capability claim is made for the debate path.**
- **The SUBSTANTIVE 15D criteria remain outstanding** and this sub-step is a small fraction of the
  phase gate: live models, a live debate, live conductor succession, the §13 OP-8 interactive
  ConPTY conductor pane, voice-in.
- **U45 is BLOCKING for `gate/phase-15d`.** The defect fixed here still exists in
  `live_flow._leg_for_backend`, `selection.bind_conductor_selection` and
  `ClaudeCodeConductorBackend.propose_plan` — and those feed the acceptance packet the gate engine
  can promote to **ACCEPTED**, a higher-consequence surface than the debate report. Not fixed here
  because those files are `.flow`- and 15B-gated; fixing them re-opens two closed gates and exceeds
  one work unit (§3.6). `reported_model_at_call` already exists, so the fix is mechanical.
- **Open gaps in this unit's own coverage, stated not glossed:** the invariant-17 global concurrent
  cap is plumbed but never exercised (debates run in sequence); the CLI-presence gate is not
  exercised through this entrypoint.
- **`ruff` unavailable on this host** (pip out of scope), so the ruff-clean rule is UNVERIFIED for
  this unit, as for `.flow`.
- **Owed:** U37 (descriptors declared, not Scheduler-resolved), U38 (inv-18 distinctness), U39
  (synthetic cost unit; `max_tokens` ignored), U40 (two `@1.0` envelopes with no schema file), U41
  (evidence resolved through the caller's client), U42 (diverged JSON extractor), U43 (accepted
  falsification limit), U44 (two-participant structural limit), U45 (above).

---

## 8. Verdict

**PASS (sub-step)**, after a FAIL-and-fix on the unit's central claim.

**Review lineage, stated exactly** (an earlier draft of this section said "final independent
verdicts were obtained on the fixed tree", which was itself an overclaim — the round-2 verdicts
predated five subsequent changes, and a reviewer caught it):

- **Round 1** — gate-validator PASS_WITH_RESERVATIONS + spec-auditor FINDINGS, on the RECOVERED
  tree. Both found the MAJOR live-classification defect.
- **Round 2** — gate-validator **FAIL** + spec-auditor 3 MAJOR, on the first fixed tree. Produced
  the contradictory-evidence MAJOR, the single-lookup gap, the docstring overclaims, M9/M13, and
  the register gap.
- **Round 3 (final)** — gate-validator **PASS_WITH_RESERVATIONS** on the tree being committed. It
  verified all four required items discharged, confirmed every measurement above, and **refuted my
  EQUIVALENT-mutant claim** (§5). Its blocking reservations R1 (false equivalence claim in code and
  report) and R2 (this section's wording) are discharged here; R3 (unpinned bool guard), R4 (stale
  harness) and R6 (dead test code) are discharged in the committed tree. R5 is addressed by
  committing an explicit file list rather than `git add -A`.

No reviewer verdict on the exact committed bytes can exist until after the commit; what is claimed
here is that every reservation raised against the reviewed tree is discharged, and the changes made
since round 3 are the discharges themselves — each pinned by a test and a killed mutant.

U45 is carried forward as **BLOCKING for `gate/phase-15d`**.

`gate/phase-15d` remains **UNTAGGED**. Next work unit: `phase-15d.succession`.
