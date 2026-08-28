# PHASE 14E EVIDENCE REPORT — Product-level validation (PHASE GATE)
Autonomous loop iteration 30 · 2026-07-19Z · **HIGH-STAKES phase gate — mandatory independent gate-validator**
Tag: `gate/phase-14e` (then `product/complete`) · closes after all three sub-steps landed:
`.roster` → `.run` → **`.gate` (this)**. Terminal step of the whole Phase-14 track.

## Objective (directive §9 table 14E; §10.4; Plan §7 product validation)
The single **assembled end-to-end run**: one conductor + one frontier worker + one OpenCode/local
coder worker + one local reasoning worker over **live shared MCP state**, with a gated coding task,
one bounded debate, conductor replacement mid-run, and full restart + recovery — **degrading
honestly** to exactly the subset that proved live (§10.4). Plus the two open verification receipts:
the on-host Ollama smoke re-run (STATUS_RECONCILIATION item 7) and the assembled-system evidence.

`.gate` (this sub-step) is the **phase gate**, not new product code: it verifies the full 14E chain
end-to-end, resolves the two `.run` gate-validator reservations, re-confirms the tag lineage, and
writes `FINAL_PRODUCT_REPORT.md` + tags `gate/phase-14e` then `product/complete`.

## The 14E chain — sub-steps and what each proved
| Sub-step | Proves | Status |
|---|---|---|
| `.roster` (iter 28) | Honest liveness matrix (`tools/assembled/roster_report.py`): each of the four roles classified LIVE / MOCK / DETERMINISTIC_SUBSTITUTE from REAL host detection + the ENFORCED runtime gate — the single source of the which-legs-are-live truth so `.run` cannot upgrade a leg. Item-7 Ollama smoke re-run LIVE on-host. | DONE (`PHASE14E_ROSTER_EVIDENCE_REPORT.md`, work `a35a23e`, evidence `0b8ccb3`) |
| `.run` (iter 29) | The assembled end-to-end scenario (`tools/assembled/run.py`) over a REAL loopback MCP server: gated coding task CANDIDATE→gate→merge→ACCEPTED (promoted by a DIFFERENT node, inv 18) · one bounded debate (≤5 rounds, dissent preserved, non-conductor caller) · conductor replacement mid-run (zero loss) · full MCP process restart + zero-loss recovery — consuming the `.roster` matrix so no leg is upgraded. | DONE (`PHASE14E_RUN_EVIDENCE_REPORT.md`, work `5a3da44`, evidence `56e6b39`) |
| `.gate` (iter 30, this) | Full-chain verification, reservation resolution, native-git lineage re-confirm, `FINAL_PRODUCT_REPORT.md`, tags `gate/phase-14e` + `product/complete`. | DONE (this report) |

## Self-check — every criterion vs real command output (`py -3.12`, native Windows host)

### 1. Full suite green
`py -3.12 -m pytest tests/ -q` → **471 passed, 0 failed, 0 skipped** (41 pre-existing
`jsonschema.RefResolver` deprecation warnings only). Unchanged from `.run` (this gate adds no source).

### 2. JS suites green (untouched by this gate)
- `apps/desktop` (`npm test`, `node --test test/*.test.js`) → **28 passed, 0 failed, 0 skipped**.
- `terminal/test/*.test.js` (`node --test`, all 9 files) → **103 passed, 0 failed, 0 skipped**.
- **131 JS total, 0 skipped.** No JavaScript changed this sub-step.

### 3. The assembled run receipt (real output, `py -3.12 -m tools.assembled.run`)
```
coding:  PASS  merged=True  final=ACCEPTED  author=coder-A  promoted_by=gate-1  from_live_model=False
debate:  DISSENT_PRESERVED  rounds=5
succession: ok=True  pred=claude-mock  succ=fable-mock  zero_loss=True
restart: ok=True  coding=True  debate=True  snap=True
live_roles=['local_reasoning_worker']  owed=['frontier_worker']
smoke:   available=True  generated=True  model=qwen2.5:7b-instruct
```
Every leg is produced by the real governed path, not asserted:
- **Coding** — one scoped MCP objective read by the coder (inv 8), edit packaged →
  `WorktreeCandidateGate` node-local gate PASS **before** publish (inv 16) → published `CANDIDATE`
  with full provenance (inv 10/11) → real `MergeCoordinator` merge (gate PASS + operator approval,
  inv 1) → promoted CANDIDATE→ACCEPTED by `gate-1` ≠ author `coder-A` (inv 18).
- **Debate** — `worker-1` (non-conductor, §2.8) via real `DebateService`+`CostGovernor`; two
  participants hold fixed `keep`/`drop` citing the real accepted entry ⇒ `DISSENT_PRESERVED`,
  `rounds_used ≤ 5` (inv 14/15/17).
- **Succession** — `conductor-A` serializes full `ConductorState` to MCP, is killed; operator
  Resume→Selects a DIFFERENT mock model; `conductor-B` reconstructs `zero_loss=true` (inv 28).
- **Restart** — the MCP server is stopped and a **fresh** `MCPServer` started over the **same**
  on-disk `SovereignStore` (a genuine restart, not a reused handle — `tools/assembled/run.py`
  calls the factory twice); `conductor-C` reconstructs and the ACCEPTED artifact, debate record,
  and succession snapshot all survive. Fail-closed: an unreadable record is NOT counted survived.

### 4. Honest liveness — no leg upgraded (central §6/§10.4 claim)
`live_roles == ['local_reasoning_worker']` and `owed_roles == ['frontier_worker']` in **both** the
roster report and the run receipt. Conductor **MOCK** (Phase-4 `MockReasoningBackend`, holds no
credential — a live frontier conductor is out of scope, §2.4 lifted only for one WORKER provider).
Frontier **MOCK + owed** — the live `claude_code` adapter exists (gate/phase-14b) but the enforced
`LIVE_OPERATION_AUTHORIZED` gate is **DENIED-by-absence** (`config/live_operation.json` intentionally
unwritten, inv 1) and the single live `claude` smoke is skip-with-record pending [OPERATOR] R8 §6
dated live-terms. Coding edit `from_live_model=False` (U31 — no live local-coder LANDED edit).
Voice **MOCK_STT** (14D skip). `test_assembled_run_reports_honest_liveness_no_upgrade` pins this.

### 5. invariant 18 enforced by POLICY, not harness convention
`test_author_cannot_self_promote_candidate_invariant_18` (LIVE negative test) proves the CANDIDATE's
author (a `worker`) is refused ACCEPTED promotion with `McpError` — promotion is gate/operator-only,
enforced in `control_plane/policy.py::authorize_transition`, not merely asserted in-test.

### 6. Native-git tag lineage & honesty invariants (re-confirmed this gate)
- `git tag -l "gate/phase-14*"` → `gate/phase-14a`, `gate/phase-14b`, `gate/phase-14c` present;
  **`gate/phase-14d` ABSENT** (correctly untagged — 14D was skip-with-record); `gate/phase-14e`
  created at this step (then `product/complete`).
- `git ls-files config/` → only `config/live_operation.example.json` tracked;
  `config/live_operation.json` **absent on disk and untracked** — the loop did NOT write it
  (inv 1, self-authorization would be creating that file once a live path exists).
- `git status --short docs/canonical/` → **empty** (canonical frozen set untouched).

## Resolution of the two `.run` gate-validator reservations
- **R1 (low — latent roster label edge): RESOLVED / does not manifest on this host.** On this host
  OpenCode `1.17.13` is detected, so `roster_report.assembled_roster` classifies `coding_worker`
  as **DETERMINISTIC_SUBSTITUTE** (real driven harness at 14C, but the accepted edit is a seeded
  stand-in, U31) and correctly **excludes it from `live_roles`**. The latent edge — a host with a
  local coder model but **no** OpenCode binary — would read `coding_worker=LIVE` (the direct
  single-shot Ollama coder, roster F1), which is honest for THAT host because a real local backend
  produces the output; but even there the assembled run's merged edit stays a seeded stand-in
  (`from_live_model=False`). The label describes the backend that produces the role's governed
  output; the run's edit-origin is reported separately and honestly. No overclaim in either case.
- **R2 (informational — the one live leg is a smoke receipt): STATED PLAINLY.** The single
  genuinely-live model execution this session is the item-7 Ollama smoke (`available=true`,
  `generated=true`, `qwen2.5:7b-instruct`), a **receipt** that a real generate succeeds on this
  host — **not** an end-to-end live governed pipeline. `.run`'s `honest_summary.genuinely_live_this_session`
  and this report both say so; every other leg is mock/deterministic by design or prohibition.

## Substitutions / honesty (directive §6/§10.4) — the assembled run reports exactly what was live
- **Rendered/visible panes are an operator-run metric** (like the Phase-1 spike and the 14A window).
  The headless run proves the governed **DATA path** end-to-end (MCP state, gate verdicts,
  provenance, succession, recovery). The UI-side recovery machine (`terminal/recovery/*.js` +
  `RecoveryStore`) is proven at `gate/phase-14a` by the Node suite (131 JS).
- **Frontier is OWED, not claimed** — no live `claude` call; `LIVE_OPERATION_AUTHORIZED`
  DENIED-by-absence; the loop did not write `config/live_operation.json` (inv 1).
- **Coding edit is a DETERMINISTIC_SUBSTITUTE** (`from_live_model=False`, U31 — no live local-coder
  LANDED edit producible headlessly). OpenCode's real spawn + tool-execution + worktree confinement
  were proven live at 14C and are not re-claimed here.
- **Voice (14D) is SKIP-WITH-RECORD** — real Parakeet not installable in this non-interactive
  session (WSL inaccessible); voice stays MockSTT (Phase-12 path). U1/U2/U4 open-for-hardware.
- **No credential handling (§2.2).** Local Ollama is loopback, no credentials (§2.4).

## Open / owed items honestly carried to the final report
- **Single live `claude` frontier smoke — OWED** (skip-with-record at 14B; pending [OPERATOR] R8 §6
  dated live-terms **and** `config/live_operation.json` present, which the loop must NOT create).
- **U31 — no live local-coder LANDED edit** (model-quality limit; the governed chain is proven with
  a seeded edit). Non-blocking.
- **U1 / U2 / U4 — open-for-hardware** (Parakeet latency/VRAM, mic→WSL bridge, CC-BY attribution),
  from the 14D skip-with-record.
- **U5 / U29** — provider per-account concurrency verified-at-1 (I-X3), env-scrub substring width;
  non-blocking, defence-in-depth.

## Invariant touchpoints (assembled run)
Inv 1 (protected merge never self-authorized) · 8 (scoped context, single objective read) · 10/11
(CANDIDATE + provenance) · 14/15/17 (bounded/dissent-preserved/cost-governed debate) · 16 (failed
artifact cannot advance) · 18 (no node solely judges its own work — author self-promotion refused
by policy) · 28 (conductor succession, zero loss) · §2.2 (no credentials) · §6/§10.4 (honest
substitution, no overclaim).

## Independent review (this iteration)
- **spec-auditor: N/A** — `.gate` adds no substantive product source (verification + reporting
  gate). The substantive `.roster`/`.run` code was spec-audited at iters 28/29 (all MAJOR/MINOR
  fixed pre-commit and re-tested; load-bearing governance invariants CLEAN, no prohibited drift).
- **gate-validator (MANDATORY, high-stakes): PASS_WITH_RESERVATIONS.** In an isolated context the
  validator re-executed the full suite (**471 passed, 0 failed, 0 skipped** — the live Ollama test
  did NOT skip), the assembled CLI receipt (value-by-value: coding `merged` with a 40-hex sha +
  `promoted_by=gate-1 != author=coder-A`; debate `DISSENT_PRESERVED` `rounds_used=5`; succession
  `zero_loss` into a different model; restart all-survived), the JS suites (**28 + 103 = 131, 0
  skip**), the inv-18 negative test (author self-promotion refused with `McpError`, enforced in
  `control_plane/policy.py::authorize_transition`, not in-harness), and the honesty invariants. It
  **specifically attempted to refute** any live-capability overclaim and **found none**:
  `from_live_model` is hardcoded `False` on the assembled coding path and carried verbatim into the
  receipt; the published CANDIDATE provenance records `model="seeded-edit"` (never a fabricated
  model id); the only `subprocess` calls are `git` repo-seeding — no `claude` spawn; the frontier
  gate is DENIED-by-absence. Canonical integrity independently re-hashed (directive `CC414372`,
  plan v1.0.1 `8C9B7240`, v1.0 `668089B5`, v2.4 `6D3FD03B` — all match the freeze). **Reservations,
  all non-blocking:** (R1) the validator's OWN Bash environment denied the `git` CLI, so it
  confirmed tag lineage via `.git/refs/tags/` loose refs + independent hashing rather than by
  running `git` itself — **closed here:** the builder independently ran native `git tag -l
  "gate/phase-14*"`, `git ls-files config/`, and `git status --short docs/canonical/` this session
  with the same result (14a/14b/14c present, 14d absent, `config/live_operation.json` untracked +
  absent, `docs/canonical/` clean); (R2) `rounds_used=5` sits exactly at the ≤5 cap — within bound,
  noted for transparency; (R3) the inv-18 negative test exercises the worker-author promotion
  refusal (`I-M6`, exactly the branch the assembled run's `coder-A` relies on) — the sibling
  gate-self-promotion branch also exists in `policy.py` and is policy-enforced though not exercised
  by this specific test. The validator's explicit conclusion: "**Gate may close.**" Precedent:
  P3A / P11 / 14A / 14B also closed PASS_WITH_RESERVATIONS.

## Disposition
`phase-14e.gate` **PASSED**. **Phase 14E COMPLETE** — all three sub-steps landed
(`.roster` → `.run` → `.gate`): the assembled system is proven end-to-end over live shared MCP,
degrading honestly to exactly the subset that proved live (local reasoning Ollama LIVE; conductor
and frontier MOCK; coding DETERMINISTIC_SUBSTITUTE; voice MOCK_STT). **This closes the entire
Phase-14 track.** Tags: `gate/phase-14e` (HIGH-STAKES, mandatory gate-validator) then
`product/complete`. `FINAL_PRODUCT_REPORT.md` written at repo root. Per directive §9/§10.4 the
operator is now addressed ONCE — this is a **COMPLETE**, not a BLOCKED. Promotion to the
`SOVEREIGN_ORCHESTRATION_WORKSPACE_v1` naming remains operator-reserved.
