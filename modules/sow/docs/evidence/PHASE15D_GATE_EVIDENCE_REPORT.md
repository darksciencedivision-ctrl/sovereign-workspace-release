# PHASE 15D `.gate` — EVIDENCE REPORT

**Work unit:** `phase-15d.gate` (iteration 46)
**Date:** 2026-07-20
**Verdict:** **WORK UNIT PASS_WITH_RESERVATIONS · PHASE GATE NOT CLOSED — BUILD BLOCKED**
**Tag applied:** **NONE.** `gate/phase-15d` is deliberately NOT tagged (see §6).

---

## 0. Summary in one paragraph

This unit discharged the register item recorded as BLOCKING for the 15D gate (U45), partially
discharged U53, and then — on the mandatory independent gate-validator's FAIL, which the builder
verified and accepted without softening — **declined to tag the phase gate**. Four of the five
§11 track-15D criteria and all five §13 (OP-8) criteria require LIVE models, and they are unmet.
The §6 substitution rule does not reach them, because the live legs are neither prohibited (§11(a)
lifted §2.4 for `claude_code` and `codex`) nor absent (the CLIs run on this host). The genuine
obstacle is an operator-reserved act: the `[OPERATOR]` live-terms confirmations in
`docs/evidence/R8_TOS_VERIFICATION_CLAUDE_CODE.md` §6. The loop cannot self-discharge them without
self-authorizing a protected action (invariant 1). State is therefore **BLOCKED** per directive §8.

---

## 1. What was built

### 1.1 U45 — one verification rule, applied everywhere (the BLOCKING item)

U45 recorded that the honesty rule `.debate` established was applied in exactly one module while
three already-gated sites kept the pre-fix behaviour, on paths of greater consequence (the
`acceptance_packet@1.0` the gate engine can promote to ACCEPTED).

**The rule now has one definition**, in `adapters/frontier/claude_code.py`:

| Function | Contract |
|---|---|
| `is_live_cli_backend` | `type(x) is ClaudeCliBackend` — exact, never `isinstance` |
| `_wrapped_cli_backend` | resolves a `ClaudeCodeConductorBackend` ONE level, checked by TYPE, and only to a genuine inner backend |
| `calls_or_none` | counted calls; ABSENT or unreadable ⇒ `None`, which is not zero |
| `bind_calls_snapshot` | the bind-time snapshot, resolved through the same path verification reads |
| `verify_reported_checkpoint` | four conditions, all required (below) |

The four conditions: **(1)** exact vendor class; **(2)** a call SPENT since `calls_before`;
**(3)** a non-blank checkpoint STRING the CLI itself reported (`extract_reported_model` — a
requested `--model` slug never reaches it); **(4)** a `reported_model_at_call` stamp strictly
GREATER than `calls_before`. `calls_before=None` (no snapshot) and an unreadable counter both fail
CLOSED. Note the deliberate asymmetry, now stated in the docstring: for reporting SPEND an
unreadable counter fails toward "spent" (over-reporting is honest); for verifying a LIVE claim it
fails toward "unverified" (under-claiming is honest).

**Site fixes:**

1. `control_plane/orchestration/live_flow.py:_leg_for_backend` — exact type. A non-spawning
   subclass now classifies `mock`.
2. `control_plane/conductor/selection.py:bind_conductor_selection` — a new provider-neutral
   `ExecutingEvidence` is the ONLY route to `executing_verified`. A bare `reported_model` string is
   inert; it is recorded as `executing.reported_unverified` and named in the note, and
   `executing.model` stays `None`. Conflicting claim-vs-evidence RAISES.
3. `adapters/frontier/claude_code.py:ClaudeCodeConductorBackend.propose_plan` — snapshots before
   `generate`, so freshness is scoped to THAT call (the strongest possible scoping).
4. `live_flow._rebind` and `node_runtime/supervisor/conductor_spawn.py` — both now build evidence
   from a bind-time snapshot instead of passing the raw property.
5. `control_plane/orchestration/live_debate.py` — its private copies now DELEGATE to the single
   definition (its 121 tests are the equivalence proof).

**A FOURTH site, found in review and fixed here:** `live_succession` took bind-time snapshots via a
local `_calls_or_zero` reading `.calls` un-unwrapped. For a conductor wrapper that snapshot (the
wrapper's `propose_plan` tally, starting at 0) and the freshness check (the inner backend's LIFETIME
CLI counter) measured different counters, making a stale checkpoint trivially verifiable — the U45
defect shape, reintroduced in the module citing U45. Latent (a live succession is owed, U51), fixed
regardless.

**Provenance added (invariant 11):** `ExecutingEvidence.rule` names the verification and reaches the
record as `executing.verified_by`. A flat `verified: true` whose only account of itself lived in a
code comment was what `_assert_legs_honest` read as authority for a `live` leg.

### 1.2 U53 — a closed conductor cannot act (PARTIAL)

`ConductorAdapter.read_accepted` and `publish_acceptance_packet` now raise `ConductorNotReady` when
`_started` is False, as the FIRST statement in each method (tests assert the MCP call count is
unchanged, so the refusal provably precedes any call). `run_cycle` already did this; its two
MCP-touching neighbours did not, which meant `.succession`'s "the predecessor is dead" claim rested
on the runner's discipline.

**Not closed.** U53 records two facts; `McpClient.call` auto-reconnect is untouched. Per the U40
amendment's precedent, U53 stays OPEN.

---

## 2. Test evidence (real command output)

```
$ py -3.12 -m pytest tests/ -q
902 passed, 61 warnings in 188.31s (0:03:08)
```
Baseline at `.succession` was 874. **+28 tests**, all new or rewritten in this unit.

```
$ node --test terminal/test/*.test.js apps/desktop/test/*.test.js
ℹ tests 149 / ℹ pass 149 / ℹ fail 0
```
JS is UNTOUCHED by this unit (every change is Python). Note on counting: `.succession` reported
"183 JS" by including `tools/spike_compositor/test/` (a throwaway Phase-1 rig); the product suites
are 149. Both numbers are correct for what they count; this report states the product figure.

New test files: `tests/unit/test_live_checkpoint_verification.py` (the U45 rule at every site),
`tests/unit/test_closed_conductor_refuses.py` (U53).

### 2.1 Mutation

**Builder:** 12 mutants of the guards this unit landed — exact-type→`isinstance` at both sites,
freshness removed, spend check removed, wrapper laundering, bare-claim-verifies restored, conflict
refusal removed, `propose_plan` snapshot defeated, `_rebind` and `conductor_spawn` trusting the raw
property, both U53 guards. **12/12 KILLED.** Harness deleted, not committed (consistent with
`.flow`/`.debate`/`.succession`); all files restored byte-identical.

**Validator (independent):** 22 mutants derived separately, **18 killed, 4 survived**. All four were
addressed in this unit after the review:

| Survivor | Disposition |
|---|---|
| `ExecutingEvidence` bool clause dead code | Equivalent mutant confirmed; `rule` validation added, clause retained as explicit and documented |
| `verify_reported_checkpoint` unreachable `calls is None ⇒ spent` branch, with INVERTED fail-closed rationale | **Removed.** The function now fails closed on an unreadable counter, and the docstring states the asymmetry rather than arguing the permissive direction |
| `_executing_verified` truthy-not-`True` accepted at the public `build_acceptance_packet` boundary | **Real gap, now tested** (`test_the_publish_time_backstop_requires_verified_to_be_exactly_true`) |
| `ConductorAdapter.reported_model` guard unpinned | **Now tested** (`test_the_adapter_reported_model_property_stays_fail_closed`) |

---

## 3. Review rounds

**gate-validator (MANDATORY, high-stakes gate): FAIL** — for the gate. It passed criteria 1–7
(U45 discharged at all three sites and confirmed by adversarial probe; U53 correct; suite counts
exact at 902/149; lineage and freeze exact) and **failed criterion 8, the honesty of the gate
verdict itself.** Its reservations 1–6 are all addressed above or in §5. Its reservation 7 is §6 of
this report.

Its adversarial probe result, recorded in full because it bounds what `live` means:

```
ATTACK A: genuine class, generate replaced   leg=live       verified=True   published=True
ATTACK B: mock wrapping a genuine backend    leg=mock       verified=False  published=True
ATTACK C: pre-stamped, no fresh call         leg=attempted  verified=False  published=True
ATTACK D: __class__ reassigned to subclass   leg=skipped    verified=False  published=False
ATTACK E: bool masquerading as int counter   leg=attempted  verified=False  published=True
```

B–E refused. **A succeeds** — U43 route (c) verbatim, disclosed in the docstring, and the technique
this unit's own positive tests use because it is the only way to exercise the verified path
mock-first. Recorded as **U54**: the `live` claim is not machine-enforceable in-process.

**spec-auditor: 2 MAJOR + 7 MINOR + 5 NIT.** Both MAJORs fixed pre-commit:

- **MAJOR-1** — the fourth un-unified site in `live_succession` (§1.1 above). Real; fixed.
- **MAJOR-2** — `_wrapped_cli_backend` said "only `ClaudeCodeConductorBackend.wrapped_backend` is
  followed" while the code did a bare `getattr`, duck-typing the unwrap step inside a rule whose
  whole justification is that class identity must not be inferable from shape. It did not launder a
  live claim (the inner backend is still exact-type checked), but the code did not do what its
  docstring said. **Fixed** by narrowing the code to an `isinstance` check on the wrapper.

MINORs fixed: the delegating docstring claimed "three conditions" for a four-condition rule (MINOR-1);
leg classification and verification disagreed about unwrapping, so a wrapper-backed party could be
`leg="mock"` *and* carry a verification record — one artifact stating both the weaker and the
stronger claim (MINOR-2); the hand-copied selection record in `live_succession` had already drifted
from `as_record()` (MINOR-3) — fixed and now pinned by test; the verified branch erased the
recorded-fallback reason (MINOR-4) — fallback text is now preserved alongside; `verified: true`
carried no provenance (MINOR-5) — `verified_by` added; U53 marked partial not discharged (MINOR-6);
three verbatim copies of the counter read unified (MINOR-7).

The auditor cleared, on inspection: invariants 3/4/20 (vendor neutrality — `selection.py` imports no
adapter; `ExecutingEvidence` carries a bare string), invariants 1/16/28 (the U53 refusal was traced
through every call site and breaks no governed path — successor `start()` precedes `swap_conductor`,
and both early-exit `finish()` calls run against a still-started predecessor), the
`verify_reported_checkpoint` docstring line-by-line against the code, `reported_unverified` as the
right call, and the rewritten tests as re-routed rather than deleted.

**Findings against my own tests, rewritten not argued away:** one tautology the validator caught
(`test_blank_or_malformed_reported_model_never_marks_verified` — after the fix NO `reported_model`
verifies, so all five parametrized cases passed vacuously; rewritten to discriminate on the CLAIM
channel, with a positive case proving the assertion discriminates), and one name stronger than its
body (`test_no_test_in_this_suite_spawns_a_claude_process` — a function monkeypatching itself cannot
establish a suite-wide property; renamed and rescoped to what the body proves, with the suite-wide
property attributed to the validator's external run).

---

## 4. Prohibition compliance

- **No frontier-subscription call.** Validator ran the full suite under a `subprocess.Popen` hook
  placed BELOW any patched `subprocess.run`: **493 spawns, zero `claude`.** Suite green with
  `claude` hard-banned.
- **SCOPING CORRECTION (U55).** "No live call" as previous reports stated it is **not accurate** and
  is corrected here: the suite spawns real `codex` (`--version` / `exec --help` / `login status`,
  detection only) and real `opencode` (`--version` ×8, plus **two real `opencode run` invocations
  against local Ollama with `qwen2.5-coder:7b`**). Pre-existing 14C/15C tests, not this unit. The
  precise claim: **no frontier-subscription call; local Ollama calls are made and always have been**
  (§2.4 permits them — no credentials involved).
- **No credential handling (§2.2).** No provider credential is read, stored or transmitted. Precise:
  the orchestration modules DO mint internal MCP identities via `credentials.issue` — access, not
  authority (invariant 7).
- **`config/live_operation.json` NOT written by this unit.** Correcting a drafting error caught in
  review: the file is **present** (667 bytes, mtime 2026-07-19, predating this unit), untracked and
  gitignored — not absent. Its presence is material to §6.
- **Frozen set intact.** `py -3.12 tools/manifest/compute_manifest.py --check` → `freeze check OK:
  no drift in FROZEN set`. Four canonical hashes verified: `CC414372`, `8C9B7240`, `668089B5`,
  `6D3FD03B`. `git status --short docs/canonical/ schemas/ mcp_server/` → empty.
- **Tag lineage verified:** `gate/phase-14a,14b,14c,14e,15a,15b,15c` present; `14d` correctly
  UNTAGGED; **`gate/phase-15d` absent, and stays absent** (§6).
- `apps/desktop/package-lock.json` remains untracked and is deliberately NOT swept into either
  commit — it predates this unit (consistent with `.debate`/`.succession`).
- `ruff` is not installed on this host, so the CLAUDE.md "ruff-clean" bar is **UNVERIFIED** for this
  unit, as for every prior unit.

---

## 5. Substitutions used in this unit

Per §6, recorded explicitly:

1. **The positive `live` path is exercised at classifier level only**, using a genuine
   `ClaudeCliBackend` whose `generate` is replaced. Nothing spawns. This is a substitution, and
   U54 records that it is the same technique that defeats the rule adversarially. **It is not
   evidence that a live call works.**
2. **Every `live` leg in this repository remains a mock-first construction.** No result in this
   build has been produced by a frontier provider.

---

## 6. THE GATE IS NOT CLOSED — and why (U56)

The mandatory validator's verdict on criterion 8 was FAIL. The builder independently verified its
central premise (reading `R8_TOS_VERIFICATION_CLAUDE_CODE.md` §6) and **accepts it without
softening**.

**§11 track 15D — 1 of 5 criteria met.** Only the `current_conductor` selection record (`.selection`)
is met. The LIVE conductor backend, the LIVE governed loop, the bounded LIVE debate, and the LIVE
conductor succession are all unmet. **§13 (OP-8) — 0 of 5 met**: the strings `conductor`, `voice`
and `parakeet` appear **zero times** anywhere under `apps/desktop/`. The interactive ConPTY
conductor pane is not built, not substituted, and not skipped-with-record — absent.

**§6 substitution does not reach these.** §6 applies to criteria assuming something *prohibited* or
*absent*. Neither holds: §11(a) explicitly lifted §2.4 for `claude_code` and `codex`, and both CLIs
demonstrably execute on this host (the suite's own spawn log). Invoking §6 for something authorized
and present, merely un-run, inverts the rule — and §6 closes with "never present a substituted
result as the real-provider result", which tagging the phase would do. Tagging would also be an
invariant-16 conductor override of a gate.

**The genuine blocker is narrow and operator-reserved.** `R8_TOS_VERIFICATION_CLAUDE_CODE.md` §6
lists `[OPERATOR]` confirmation items as explicit entry conditions for ANY live smoke. Item 2 —
*"confirm nothing in the current terms prohibits running the first-party `claude` CLI under the
operator's own subscription from a supervising process for the operator's own use"* — is an operator
determination. For the loop to read the terms, decide they permit it, and then spend the operator's
subscription on that reading would be self-authorization of a protected action (invariant 1). The
delegation ruling in §1 enumerates what is delegated; R8 live-terms are not in it.

**Terminal state: BLOCKED (directive §8).** Recorded in `docs/loop/LOOP_STATE.json` with
`blocked_reason` and `smallest_unblocking_action`.

### What the operator can do

The smallest unblocking action is item 2 above: confirm (or refuse) that the current Claude Code
consumer terms permit supervised first-party CLI invocation under the operator's own subscription.
A **refusal is equally unblocking** — R8 §6 already specifies the response ("do not run the live
smoke — record and skip-with-record"), which would let 15D close honestly as a governed-path proof
with the live legs permanently OWED rather than pending.

Separately, and NOT taken by the loop because it would advance past an unclosed high-stakes gate
(invariant 16): the §13 OP-8 conductor-pane surface could be built mock-first without any live
call. If the operator prefers the loop to proceed there while the terms question is open, that is
an operator instruction to give — the loop will not take it unilaterally.

---

## 7. Commits

| Commit | Content |
|---|---|
| (work) | `feat(verification): phase-15d.gate — one checkpoint-verification rule at every site (U45, U53)` |
| (evidence) | this report + register amendments, carrying the work hash |
| (state) | `LOOP_STATE.json` → `status: BLOCKED` |

**No tag.** `gate/phase-15d` is not applied and must not be applied until the §11/§13 criteria are
met or formally re-scoped by the operator.
