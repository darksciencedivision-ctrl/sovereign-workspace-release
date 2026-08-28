# PHASE 15D `.debate` — LIVE RE-RUN — EVIDENCE REPORT

**Work unit:** `phase-15d.debate` **(LIVE re-run under OP-9)** — second live sub-step of the Phase
15D live pass (`.flow` ✔ → **`.debate`** → `.succession` → `.gate`, each re-run LIVE per OP-9).
**Date:** 2026-07-20 · **Iteration:** 48 · **Status:** PASS (sub-step)
**Tag:** none. `gate/phase-15d` is a HIGH-STAKES phase gate and closes only at `.gate`, on live
evidence, with the mandatory independent gate-validator.
**Governing directive:** `AUTONOMOUS_BUILD_DIRECTIVE.md` §14 (OP-9 — "Go live"), §11 track 15D
("one bounded live debate — budgets enforced, real tokens now"), §2.8 debate acceptance tests,
loop protocol §3, honesty §6/§10.4, D-LOOP-1 teardown constraint.

---

## 0. What this sub-step re-runs LIVE

The `.debate` **mechanism** was built and proved MOCK-FIRST at iteration 45 (`live_debate.py` +
`tests/integration/test_live_debate_flow.py`, 26 tests, no `claude` process). This sub-step is the
OP-9 **live** re-run: ONE bounded debate driven through the identical Phase-7-gated Debate Service
and the identical live-spawn gates, but with **two genuine `ClaudeCliBackend` debaters** that
actually spawn `claude` — so each leg is recorded `live` only because the CLI reported back a
verified executing checkpoint for a call spent inside THIS debate. No production code changed; the
only new file is the operator-run driver `tools/live/run_15d_debate_live_smoke.py` (the Phase-1
spike substitution pattern — a live metric, not part of `pytest tests/`).

---

## 1. The live evidence (one real bounded debate, this host, iteration 48, 2026-07-20)

One live smoke through `tools/live/run_15d_debate_live_smoke.py` — **witnessed by the builder this
iteration**. Two real `ClaudeCliBackend` debaters, each spawning `claude`, through
`control_plane.orchestration.live_debate.attempt_live_debate` over a real `MCPServer`, the real
`DebateService` (Phase 7), the real `CostGovernor`, and the real `spawn_claude_code_terminal` live
gates. Each `generate` uses synchronous `subprocess.run` with a hard timeout, so the child is gone
before the call returns — **D-LOOP-1 satisfied by construction**; no background live process.

```
py -3.12 tools/live/run_15d_debate_live_smoke.py --max-rounds 2 --timeout 150
```

Observed outcome (verbatim fields, the committed-driver run):

| field | value |
|---|---|
| `ran` / `published` / `skipped_with_record` | `true` / `true` / `false` |
| `legs` | `{debater-A: "live", debater-B: "live"}` |
| `debater_models` | `{debater-A: {model: "claude-opus-4-8[1m]", verified: true}, debater-B: {same}}` |
| `outcome` | **`DISSENT_PRESERVED`** |
| `rounds_used` | `2` (of `max_rounds = 2`; ≤5 hard cap) |
| `dissent_present` | `true` |
| `cost_actual` | `{usage_units: 200}` |
| `budget` | `{usage_units: 300}` (200 ≤ 300 — under the hard cap) |
| `debate_id` | `d-f9f4cc0d1c604bce` |
| `mcp_entry` (frozen `debate@1.0` record) | `m-31cd881562b4c2d7` |
| `report_entry` (`debate_report@1.0`) | `m-cc82851f7fb42f28` |
| a SUPPORTED evidence-cited position | `debater-A@r1` (cited `m-3c094cbe82e20b14`, **resolved** in MCP) |
| caller | `worker-caller` (role `worker` — **non-conductor**, §2.8) |
| `reason` | `bounded debate ran 2 round(s) -> DISSENT_PRESERVED; record and report published CANDIDATE to MCP` |

**This is the OP-9 `.debate` deliverable — one bounded LIVE debate, real tokens:**
- **Two live debaters, verified, not asserted:** each leg is `live` because `ClaudeCliBackend`
  read a non-blank executing checkpoint (`claude-opus-4-8[1m]`, the CLI-default primary) back out
  of the CLI's own `modelUsage` reply for a call spent since the bind-time snapshot
  (`verify_reported_checkpoint`). No requested `--model` slug reached the extractor.
- **A genuine evidence-cited SUPPORTED position, and a substantive argument (not a bare refusal):**
  `debater-A@r1` cited the seeded ref `m-3c094cbe82e20b14` — which **resolved** in MCP, so the real
  `EvidenceManager` classified it **SUPPORTED** — and argued that the note "states the constraint
  'exactly one conductor, no cloud adapters', which satisfies the count and the no-cloud-adapters
  conditions, but … does not identify any conductor by name — so it does not fully satisfy an
  acceptance criterion that requires *naming* exactly one offline conductor." A real
  evidence-anchored argument produced by a live model.
- **Bounded and budget-governed (invariants 14/17):** `max_rounds = 2` under the ≤5 hard cap;
  `cost_actual = 200` charged against a `budget = 300` hard cap — never exceeded.
- **Non-convergence recorded, dissent kept VERBATIM (invariant 15):** the two final-round positions
  differed and were not both aligned-and-supported, so the governed path recorded
  `DISSENT_PRESERVED` and preserved both positions verbatim, neither smoothed into consensus. (What
  `DISSENT_PRESERVED` did and did not demonstrate here is stated precisely in §2 — read it before
  treating this as a fully-evidenced two-sided disagreement.)
- **Published CANDIDATE over MCP (invariants 10/11):** the frozen `debate@1.0` record
  (`m-31cd881562b4c2d7`) and the `debate_report@1.0` (`m-cc82851f7fb42f28`) are both durable,
  provenance-stamped, CANDIDATE — never self-canonized.
- **Non-conductor caller (§2.8):** the debate was requested by `worker-caller`, proving the service
  is not conductor-coupled.

---

## 2. What `DISSENT_PRESERVED` did and did NOT demonstrate here (precise, not glossed)

The `RoundManager` declares `CONVERGED` only when every debater's latest position is the SAME
string **and at least one is SUPPORTED** (`round_manager/manager.py:85-91`); otherwise, at the
round cap, `DISSENT_PRESERVED`. In this run:

- `debater-A@r1` was **SUPPORTED** and made the substantive "the note never *names* a conductor"
  argument (§1). `debater-B@r2` made the **same** substantive point ("does not identify any
  conductor by name, so it fails the acceptance criterion") — i.e. the two models largely
  **agreed on the substance**, that the note is insufficient because it names no conductor.
- Their FINAL-round positions nonetheless differed in string and were not both aligned-and-SUPPORTED
  (`debater-A@r2` and `debater-B@r2` were classified UNSUPPORTED — see §3/U59 below), so
  `_converged` was false and `DISSENT_PRESERVED` followed.

Honest reading: this run **did** exercise a real SUPPORTED evidence-cited live position and real
substantive model reasoning about the criterion — a materially stronger live demonstration than two
bare refusals. It did **not** cleanly exercise the "two competing, mutually-SUPPORTED, opposed
positions held to the cap" shape: the final-round classifications were UNSUPPORTED, so the
`DISSENT_PRESERVED` here is as much an artifact of the round manager's supported-position rule (plus
the U59 / resolution-flakiness limits below) as it is of genuine held-apart disagreement. The
"preserve two opposed SUPPORTED positions verbatim" path remains proven **mock-first** (`test_dissent_is_PRESERVED_VERBATIM_when_participants_do_not_converge`), not by this live leg. Recorded, not implied by the one-word outcome.

---

## 3. Exit criteria (directive §11 15D "one bounded live debate", §2.8) and verdicts

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | One **bounded LIVE debate** on the live-capable binding, **real tokens** | **PASS (live)** | §1: two `live` legs, verified checkpoint `claude-opus-4-8[1m]`; 2 real rounds published. |
| 2 | ≤5 rounds hard cap (invariant 14) | **PASS** | `max_rounds = 2`; `rounds_used = 2`. The `max_rounds > 5` refusal is proven deterministically by the mock-first suite (`test_a_request_over_the_five_round_hard_cap_is_REFUSED`). |
| 3 | Per-debate budget enforced, clean cutoff (invariant 17) | **PASS** | `cost_actual = 200 ≤ budget = 300`. Budget-exhaustion cutoff proven deterministically (`test_exhausted_budget_cuts_off_CLEANLY_...`). |
| 4 | Evidence-cited assertions; a model vote is not evidence | **PASS (live SUPPORTED shown)** | Real `EvidenceManager` resolved a live citation against MCP: `debater-A@r1` cited `m-3c094cbe82e20b14`, it resolved ⇒ **SUPPORTED**. Non-resolving/absent-content citations ⇒ UNSUPPORTED (§U59). No citation fabricated (`parse_statement` drops non-scoped/invented refs). |
| 5 | Dissent preserved VERBATIM (invariant 15) | **PASS (mechanism), with §2 caveat** | `outcome = DISSENT_PRESERVED`, `dissent_present = true`; both live positions kept verbatim in `m-cc82851f7fb42f28`. §2 records precisely what this did/did-not exercise — the two-opposed-SUPPORTED path stays mock-first. |
| 6 | No node solely judges its own work (invariant 18) | **PASS (instance-distinct), with limit** | Two DISTINCT `ClaudeCliBackend` **instances** (`attempt_live_debate` refuses a shared backend and duplicate ids); non-conductor caller `worker-caller` (§2.8). LIMIT (§4): both instances resolved to the SAME checkpoint `claude-opus-4-8[1m]`, so this is one model under two node labels, not two distinct reasoners. |
| 7 | `live` only on a VERIFIED checkpoint; never present mock/attempted as live (§6/§10.4) | **PASS** | `build_debate_report` refuses a `live` leg without a verified checkpoint (both directions); proven by 6 refutation tests incl. `test_a_SUBCLASS_that_never_ran_the_CLI_cannot_be_packaged_as_LIVE` and `test_a_STALE_checkpoint_...`. Here both legs carry a real, freshly-stamped checkpoint. |
| 8 | §2.2 — invoke host CLI; never read/store/transmit the credential | **PASS** | `ClaudeCliBackend.build_env` scrubs every credential/endpoint var (fail-closed superset); no `--api-key`/bypass flag (`_assert_no_forbidden`). OAuth stays in the CLI's host-native store; no repo/MCP credential write. |
| 9 | D-LOOP-1 — live processes torn down within the unit | **PASS** | Synchronous `subprocess.run` with a hard timeout per `generate`; every I-X3 terminal released in `attempt_live_debate`'s `finally` (`_teardown`); the driver printed and exited 0; no background live process spawned. |
| 10 | I-X3 governor caps at the authorized allowance (2) | **PASS** | Two live debaters acquired two terminals on `sub-anthropic` (allowance = `live_auth.terminals_per_subscription` = 2 from the OP-6 config) and both were released at teardown. A 3rd concurrent terminal is refused (mock-first `test_exceeding_the_subscription_allowance_skips_with_record`). |

---

## 4. Limits, honestly (recorded, not glossed)

- **Two distinct backend INSTANCES, but the SAME model (invariant-18 scope).** Invariant 18 is
  satisfied at the level the code enforces — two separate `ClaudeCliBackend` objects, a shared
  instance refused, distinct node ids — but both requested the CLI default and both resolved to the
  identical checkpoint `claude-opus-4-8[1m]`. This is therefore **one model arguing under two node
  labels, not two distinct reasoners**. The code records exactly this as owed
  (`live_debate.py:649-657`: "two separate instances of the same model remain indistinguishable
  here — recorded as owed, not claimed away"). A live debate between **different** models
  (e.g. Anthropic vs. a live Codex/GPT worker) is OWED to `.gate`/15E; nothing here should be read
  as a two-distinct-model disagreement.
- **U59:** live debaters receive scoped evidence **ref ids** in the prompt, not the **resolved
  content** of those entries, so a live model with no MCP-read tool cannot inspect the evidence body
  and (when it does not simply cite the ref) fails closed to UNSUPPORTED. A scoped evidence-body
  read for live debaters (invariant 8) is OWED.
- **Transient loopback-MCP flakiness under multi-minute live timing (observed, recorded).** Across
  three live runs this iteration the loopback `caller_client` socket proved unreliable while the
  ~2–4 minutes of sequential live `claude` calls ran: one run aborted in the publish tail
  (`WinError 10053`, reported honestly as `skipped_with_record` with the debate un-published — the
  governed path's fail-closed degrade, not a false PASS), and even the successful run showed
  **intermittent** evidence resolution (the same ref `m-3c094cbe82e20b14` resolved for
  `debater-A@r1` but not for `debater-B@r2`). This is an environmental/robustness limit of the
  loopback transport under live latency (transport is the standing U6 item), **not** a governance
  defect: no un-verified leg was ever labelled `live`, and a failed publish degraded honestly. A
  keep-alive / reconnect hardening for the caller channel across long live calls is OWED (recorded
  for `.gate`/hardening).
- **Executing checkpoint = CLI default (`claude-opus-4-8[1m]`), not the fable-5 selection.** This
  sub-step drives the debaters on the CLI-default model (the most reliable route to a verified live
  checkpoint on an arbitrary host). `claude-fable-5` as an accepted slug was confirmed end-to-end at
  `.flow` (U33); the debate participants are **workers** (reasoning), not the conductor, so the
  fable-5 selection is not a `.debate` criterion. `--model claude-fable-5` is accepted by the driver
  for anyone who wants to drive the debaters on that checkpoint.
- **Operator-run-metric trust boundary.** The live result of §1 is an operator-run metric
  (Phase-1-spike pattern). Its debate/report entry ids are per-run and NOT independently
  re-derivable from the repo. The committed, CI-runnable proof is the mock-first suite (§5); the
  live headline is the witnessed run. The high-stakes `.gate` validator must obtain its own fresh
  live evidence and must not treat this sub-step as independent confirmation of the live claim.
- **U54/U43 (carried):** the `live` rule constrains the backend CLASS and the checkpoint evidence,
  not a determined in-process falsifier's BEHAVIOUR — every accidental and mock-shaped route is
  refused; a caller that sets out to forge its own evidence is not. Documented, not closable
  in-process.
- **Cost:** the live legs spent **12 `claude` calls total across three runs** (2 debaters × 2 rounds
  each), minimal prompts — smoke-scale (§11 budget discipline). Why three runs: run 1 (seed role
  `operator`) published fully; the seed role was then lowered to `worker` (least privilege, spec-
  auditor NIT-1); run 2 (worker seed) proved the worker-role seed publishes but hit the transient
  loopback disconnect above; run 3 (the committed driver) published fully and is the §1 witnessed
  result — so the committed driver matches a witnessed full-success run.
- **Substantive 15D items still OWED to later live sub-steps / `.gate`:** live conductor succession
  (`.succession`), the OP-8 interactive ConPTY conductor pane + voice-in (15E), a
  different-model live debate, and the caller-channel keep-alive hardening. This sub-step is the
  one-bounded-live-debate item only.

---

## 5. Tests & suite

- **No production code changed.** The only new file is `tools/live/run_15d_debate_live_smoke.py`,
  an operator-run driver (not collected by `pytest tests/`).
- The `.debate` mechanism's mock-first proof is unchanged and green:
  `tests/integration/test_live_debate_flow.py` (26 tests) + `tests/unit/test_live_debate.py`.
- Full suite: **908 passed** (`py -3.12 -m pytest tests/ -q`, 187.62s builder-run; gate-validator
  independently re-ran in isolation: **908 passed**, 189.73s). JS product suite unaffected (no JS
  change).

---

## 6. Reproduction & raw outcome

```
py -3.12 tools/live/run_15d_debate_live_smoke.py --max-rounds 2 --timeout 150
```
Witnessed stdout (iteration 48, committed-driver run): `ran=true published=true
skipped_with_record=false`, `legs={debater-A: live, debater-B: live}`,
`debater_models={debater-A/B: {model: "claude-opus-4-8[1m]", verified: true}}`,
`outcome=DISSENT_PRESERVED`, `rounds_used=2`, `cost_actual={usage_units: 200}`,
`budget={usage_units: 300}`, `debate_id=d-f9f4cc0d1c604bce`, `mcp_entry=m-31cd881562b4c2d7`,
`report_entry=m-cc82851f7fb42f28`, `debater-A@r1` SUPPORTED (cited `m-3c094cbe82e20b14`), caller
`worker-caller` (non-conductor). Per-run entry ids differ each run (operator-run-metric limit, §4).

---

## 7. Independent review (this iteration)

**gate-validator (sub-step, isolated) — PASS_WITH_RESERVATIONS.** Re-ran the full suite in its own
context (**908 passed**, 189.73s). Confirmed: the driver drives the REAL governed path with two
distinct real backends, real `live_auth` from the repo config, `cli_present` DETECTED not
hardcoded, `operator_terms_confirmed=True` on the OP-9 basis, non-conductor caller; NO production
code changed. Traced the honesty guarantee end to end — a leg is `live` only on a verified fresh
CLI checkpoint (`verify_reported_checkpoint`, four conditions), the requested `--model` slug never
reaches `extract_reported_model`, and `build_debate_report` refuses a `live` leg without a verified
checkpoint in both directions. Bounds (≤5 cap, budget hard cap, dissent verbatim, invariant-18
shared-backend/dup-id/pre-held-id refusals, I-X3 allowance=2 with `finally` teardown) verified
against artifacts. §2.2 scrub intact, no bypass flag. Tag lineage (15a/15b/15c present, 15d ABSENT
— correct), four frozen canonical hashes intact, `docs/canonical`/`schemas`/`mcp_server` untouched,
`config/live_operation.json` gitignored+untracked. Reservations, both inherent/disclosed, not
defects: **R1** — the live headline rests on the builder's witnessed stdout (operator-run metric,
per-run ids non-reproducible); the `.gate` validator MUST obtain its own fresh live evidence.
**R2 — U59** — the live debate demonstrated the governed machinery; a fully-evidenced two-sided
live disagreement (with resolved evidence bodies) is owed.

**spec-auditor — no code invariant violations, no prohibited drift.** Confirmed invariant 1 (the
loop is not self-authorizing — `operator_terms_confirmed=True` on the recorded OP-9 basis, every
other gate real and un-bypassed), 3/4/I-SC1, 10/11, 14/15/17/18, §2.2, D-LOOP-1; nothing added to
`mcp_server/`, no new governance layer, schemas frozen `@1.0` and the canonical set untouched. Two
MINOR **evidence-report** overclaims were raised and are FIXED in this report: **MINOR-1** (the
earlier draft framed the two backends as "one model does not judge its own work" while both ran the
same checkpoint — corrected in §3 criterion 6 and §4: distinct instances, SAME model, a two-distinct-
model debate owed) and **MINOR-2** (the earlier draft framed `DISSENT_PRESERVED` as genuine
competing supported positions — corrected in §2: precisely what it did/did-not demonstrate, the
two-opposed-SUPPORTED path stays mock-first). **NIT-1** (the driver minted an `operator`-role
credential merely to seed evidence) is FIXED — the seed now uses a least-privilege `worker` role
(`evidence` is not an operator-only kind; workers may publish CANDIDATE).

New/amended unresolved items: **U59** (live debaters get ref-ids, not resolved evidence bodies —
owed); a recorded **transient loopback-MCP flakiness** observation under live timing (U6 transport,
caller-channel keep-alive owed); amendment to **U33** (fable-5 is a worker-selectable slug, CLI
default used here); the invariant-18 **same-model** limit (two-distinct-model live debate owed).

## 8. Commit hygiene

The untracked `apps/desktop/package-lock.json` (unrelated, unresolved from `.flow` R4) is
**excluded** from this unit's commits. Only this work unit's files are staged:
`tools/live/run_15d_debate_live_smoke.py`, plus the register/evidence pair and the state update.
