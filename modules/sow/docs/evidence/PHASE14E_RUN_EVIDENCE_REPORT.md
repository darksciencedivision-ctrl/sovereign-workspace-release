# PHASE 14E `.run` — Evidence Report

**Sub-step:** `phase-14e.run` (second sub-step of Phase 14E, product-level validation).
**Date:** 2026-07-19 · **Iteration:** 29 · **Status:** PASS (sub-step; no gate tag — the
high-stakes `gate/phase-14e` closes at `.gate` with mandatory gate-validator once
`.roster` → `.run` → `.gate` all land).
**Work commit:** carried in the register/evidence commit below.

## 1. Scope

The single **assembled end-to-end scenario** (directive §9 table 14E) driven over a REAL
loopback MCP server, the REAL `SuccessionManager`, the REAL `DebateService`, and the REAL
controlled merge path. It **consumes the `.roster` liveness matrix**
(`tools/assembled/roster_report.assembled_report`) as the single source of which legs are
LIVE / MOCK / DETERMINISTIC_SUBSTITUTE, so **no leg is upgraded beyond what `.roster`
proved**. Four legs are exercised in one run over one durable store:

1. A governed coding task **CANDIDATE → node-local gate → controlled merge → ACCEPTED**,
   the CANDIDATE promoted by a **DIFFERENT** node than its author (invariant 18).
2. **One bounded debate** (≤5 rounds, dissent preserved verbatim, cost-governed) requested
   by a **NON-conductor** worker, both participants citing the just-accepted artifact.
3. **Conductor replacement mid-run** — serialize → kill → reconstruct into a DIFFERENT mock
   model, zero project loss (Phase 11 `SuccessionManager`).
4. **Full MCP process restart + zero-loss recovery** over the SAME durable store — the
   ACCEPTED artifact, the debate record, and the succession snapshot all survive.

## 2. Artifacts

| Path | What |
|---|---|
| `tools/assembled/run.py` | `run_assembled_scenario(...)` orchestrates the 4 legs over a real MCP server (started twice over the same store — run, then post-restart); `_ScriptedDebater` is a self-contained deterministic debate participant (no `tests/` dependency); `AssembledRunResult` is the observable outcome; CLI `main()` emits the JSON receipt. |
| `tests/integration/test_assembled_run.py` | 5 tests — 3 deterministic (governed data path end-to-end; honest liveness / no-upgrade; determinism) + 1 live inv-18 negative (author self-promotion refused by policy) + 1 live-gated (the item-7 Ollama leg inside the assembled run, SKIP-WITH-RECORD if the daemon is absent). |

## 3. The assembled run (real command output)

`py -3.12 -m tools.assembled.run` → JSON receipt (item-7 smoke ran **live** on this host):

```
coding_task     local_gate=PASS  merged=true  merge_sha=<40 hex>  final_status=ACCEPTED
                author_node=coder-A  promoted_by=gate-1  from_live_model=false  changed=[calc.py]
debate          outcome=DISSENT_PRESERVED  rounds_used=5  dissent="drop | keep"  mcp_entry=m-…
succession      ok=true  predecessor_model=claude-mock  successor_model=fable-mock  zero_loss=true
restart_recovery ok=true  coding_entry_survived=true  debate_record_survived=true  snapshot_survived=true
liveness        live_roles=[local_reasoning_worker]  owed_roles=[frontier_worker]
                item7_ollama_smoke: available=true  generated=true
```

Each leg is produced by the real governed path, not asserted:

- **Coding task** — the conductor's assignment is published as ONE scoped MCP objective
  (invariant 8; the coder reads exactly that entry, no store sweep). The edit is produced in
  the coder's own worktree, packaged by `package_worktree_candidate`, run through
  `WorktreeCandidateGate` (node-local gate PASS **before** publish/merge, invariant 16),
  published `status=CANDIDATE` with full provenance (inv 10/11), and merged through the real
  `MergeCoordinator` (requires gate PASS + operator approval, inv 1). Promotion
  CANDIDATE→ACCEPTED is issued by a **different node** (`gate-1`), never the author (inv 18).
- **Debate** — requested by `worker-1` (a NON-conductor, Phase 7 §2.8) through the real
  `DebateService` + `CostGovernor`; two participants hold fixed opposing positions
  (`keep`/`drop`), both cite the REAL just-accepted CANDIDATE entry as evidence; the outcome
  is `DISSENT_PRESERVED` (dissent kept verbatim, not forced — inv 15) within ≤5 rounds
  (inv 14) under budget (inv 17).
- **Succession** — `conductor-A` serializes full `ConductorState` (tasks, non-empty node
  registry, open debates, ACCEPTED memory heads, routing) to MCP, then is killed; the
  operator Resume→Selects a DIFFERENT mock model and `conductor-B` reconstructs from MCP with
  `zero_loss=true` (inv 28).
- **Restart + recovery** — the MCP server process is stopped and a fresh server started over
  the SAME durable `store_dir`; `conductor-C` reconstructs again and the ACCEPTED coding
  artifact, the debate record, and the succession snapshot all survive (zero project loss
  across a real process restart). Fail-closed: an unreadable debate record is counted as
  NOT survived.

## 4. Self-check against exit criteria (real command output)

- **Governed coding task CANDIDATE→gate→merge→ACCEPTED, promoted by a different node** —
  `test_assembled_run_governed_data_path_end_to_end` PASS (local_gate PASS, merged with a
  40-hex sha, final_status ACCEPTED, `promoted_by != author_node`).
- **U31 honesty — merged edit is a seeded stand-in, never a live model edit** —
  `from_live_model is False` asserted; the receipt records it verbatim.
- **Bounded debate, non-conductor caller, dissent preserved, ≤5 rounds** — same test:
  `outcome == DISSENT_PRESERVED`, `rounds_used <= 5`, both `keep` and `drop` in dissent.
- **Conductor replacement mid-run into a different model, zero loss** — `succ.ok is True`,
  `predecessor_model != successor_model`, `zero_loss is True`.
- **Full restart + recovery over the same durable store** — `restart.ok is True` with all
  three survivors true.
- **No leg upgraded past `.roster`** — `test_assembled_run_reports_honest_liveness_no_upgrade`
  PASS (frontier `owed is True`, conductor `MOCK`, voice `MOCK_STT`, coding
  `from_live_model False`).
- **Determinism of the governed verdicts** — `test_assembled_run_is_deterministic` PASS.
- **inv 18 enforced LIVE by policy (not harness convention)** —
  `test_author_cannot_self_promote_candidate_invariant_18` PASS: the CANDIDATE's author (a
  `worker`) attempting to promote its own entry to ACCEPTED is refused with `McpError`
  (promotion is gate/operator-only, `control_plane.policy.authorize_transition`). This proves
  the refusal the harness relies on when it routes promotion through the distinct `gate-1` node.
- **The one genuinely-live leg** — `test_assembled_run_live_ollama_leg_or_skip_with_record`
  **RAN live** (Ollama daemon reachable): `item7_ollama_smoke.available` and `generated` both
  true, `local_reasoning_worker` in `live_roles`; degrades to SKIP-WITH-RECORD if the daemon
  is absent (never faked).
- **Suite:** `py -3.12 -m pytest tests/ -q` → **471 passed, 0 failed, 0 skipped** (was 466 at
  `.roster`; +5 this sub-step). JS suites untouched (131, no JS changed).

## 5. Independent confirmation

- **gate-validator (sub-step): PASS** in an isolated context. It re-executed every command
  itself (`py -3.12`): the targeted suite (**5 passed, 0 skipped** — the live Ollama leg RAN),
  the assembled CLI receipt (inspected value-by-value), and the full suite (**470 passed** at
  its run, pre-fix). It confirmed each criterion 1–6 verified against real output: the node-local
  gate is a genuine `LocalGate().evaluate(...)` (a FAIL cannot reach the merge), promotion is a
  separate `transition` by `gate-1` ≠ author, the debate caller is a non-conductor citing the real
  accepted entry, succession reconstructs a DIFFERENT model with a full-state zero-loss check, the
  MCP restart is a genuine new server over the same on-disk `SovereignStore` (no reused handle),
  no `config/live_operation.json` written, and `live_roles=[local_reasoning_worker]` in both roster
  and run (no leg upgraded). Two **non-blocking** reservations, both flagged for the `.gate`
  reviewer: **R1** (low) a latent `roster_report` label edge — if OpenCode were absent but a coder
  model present, `coding_worker` would read `LIVE` while the run's edit is always a seeded stand-in;
  **does NOT manifest on this host** (OpenCode detected → `DETERMINISTIC_SUBSTITUTE`, correctly
  excluded from `live_roles`). **R2** (informational) the genuinely-live leg is the roster Ollama
  smoke receipt, not an end-to-end live governed pipeline — which the report states plainly.
- **spec-auditor:** load-bearing governance invariants (inv 1, 7, 8, 10/18, 11/12, 14/15/17, 16,
  28, §6/§10.4 honesty, §2.2 credentials) **CLEAN**; no prohibited drift. 1 MAJOR + 2 MINOR —
  **ALL FIXED pre-commit** and re-tested green:
  - **MAJOR (M1)** — `tools/assembled/run.py` hard-imported `tests.fixtures.mock_debater` (a
    `tools/` module reaching into `tests/`, unimportable in a tests-excluded/offline profile).
    **FIXED**: replaced with a self-contained `_ScriptedDebater` in `run.py` + an optional
    `debaters=` injection seam on `run_assembled_scenario`. `grep -rn "from tests" tools/` now
    finds no first-party hit.
  - **MINOR (M2)** — the merge's operator approval is auto-supplied (`operator_approved=True`) but
    was not disclosed in `honest_summary`. **FIXED**: added a `merge_approval` field labeling it a
    SIMULATED standing-delegation approval (operator ruling 2026-07-16), NOT a live per-merge act;
    also added a `debate_participants` field labeling the scripted (non-live) debaters.
  - **MINOR (M3)** — the "the author never can" comment overstated what the harness exercised.
    **FIXED**: softened the comment AND added the live negative test above that proves the
    author-self-promotion refusal at the policy layer.
- **Post-fix full suite:** `py -3.12 -m pytest tests/ -q` → **471 passed, 0 failed, 0 skipped**.

## 6. Substitutions & honesty (directive §6/§10.4)

- **The rendered/visible panes are an operator-run metric** (like the Phase-1 spike and the
  14A window). This headless run proves the governed **DATA path** end-to-end (MCP state,
  gate verdicts, provenance, succession, recovery). It does **not** claim a rendered surface.
  The UI-side recovery machine (`terminal/recovery/*.js` + `RecoveryStore`) is proven at
  `gate/phase-14a` by the Node suite; this run proves the corresponding governed data-path
  recovery (MCP restart + zero-loss conductor reconstruction).
- **Frontier is OWED, not claimed** — no live `claude` call is made; the enforced
  `LIVE_OPERATION_AUTHORIZED` gate is DENIED-by-absence (config intentionally unwritten,
  inv 1) and the single live `claude` smoke stays skip-with-record.
- **The coding edit is a DETERMINISTIC_SUBSTITUTE** (`from_live_model=False`, U31: no live
  local-coder LANDED edit producible headlessly). The governed CANDIDATE→gate→merge→ACCEPTED
  path is the system under test; the OpenCode drive itself was proven live at 14C and is not
  re-claimed here.
- **Voice (14D) remains SKIP-WITH-RECORD** — real Parakeet not installed; voice stays
  MockSTT (Phase-12 path).
- **The item-7 Ollama receipt is the one genuinely-live model execution this session**;
  every other leg is labeled exactly at its proven level.
- **No credential handling (§2.2); the loop did not write `config/live_operation.json`
  (inv 1).**

## 7. Next

`phase-14e.gate` — CLOSE `gate/phase-14e` (HIGH-STAKES, MANDATORY independent gate-validator):
verify the full 14E chain (`.roster` liveness matrix → `.run` assembled scenario), write
`FINAL_PRODUCT_REPORT.md`, two-commit, tag `product/complete` + `gate/phase-14e`, then address
the operator ONCE (COMPLETE, not BLOCKED).
