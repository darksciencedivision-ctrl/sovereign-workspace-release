# PHASE 14E `.roster` — Evidence Report

**Sub-step:** `phase-14e.roster` (first sub-step of Phase 14E, product-level validation).
**Date:** 2026-07-18 · **Iteration:** 28 · **Status:** PASS (sub-step; no gate tag — the
high-stakes `gate/phase-14e` closes at `.gate` with mandatory gate-validator once
`.roster` → `.run` → `.gate` all land).
**Work commit:** carried in the register/evidence commit below.

## 1. Scope

Phase 14E is the assembled product-level validation run (directive §9 table 14E): one
conductor + one frontier worker + one OpenCode/local coder worker + one local reasoning
worker over live shared MCP, then succession + one bounded debate + one gated coding task +
full restart/recovery, **degrading honestly (§10.4) to whatever subset proved live.**

14E is large, so it is decomposed (directive §3.2): **`.roster` → `.run` → `.gate`.** This
`.roster` sub-step delivers the two things every honest assembled run needs up front:

1. **An honest, deterministic liveness matrix** for the four assembled roles — each classified
   LIVE / MOCK / DETERMINISTIC_SUBSTITUTE with a reason, computed from real host detection and
   the enforced runtime gates, never asserted. This is the single source of the "which legs are
   live" truth so `.run` cannot quietly upgrade a leg.
2. **The item-7 on-host Ollama smoke re-run** — the deferred verification receipt from
   `STATUS_RECONCILIATION_20260718.md §3 item 7` ("◐ artifact-attested … scheduled into Phase
   14E on-host"). Now executed live on this host: real model list + real generate + latency.

No live frontier call (owed — skip-with-record at 14B). No credential handling (§2.2). Local
Ollama over loopback is permitted (§2.4: a detected local model, no credentials).

## 2. Artifacts

| Path | What |
|---|---|
| `tools/assembled/__init__.py` | Phase 14E assembled-validation harness package. |
| `tools/assembled/roster_report.py` | `assembled_roster()` (4-role honest liveness matrix), `run_ollama_smoke()` (item-7 receipt, fail-closed), `assembled_report()` (combined deterministic report), CLI `main()`. |
| `tests/integration/test_assembled_roster.py` | 12 tests — 10 deterministic + 2 live-gated (item-7 smoke + local_reasoning LIVE). |

## 3. The honest liveness matrix (assembled roster)

| Role | Backend | Liveness | Basis |
|---|---|---|---|
| conductor | mock (`MockReasoningBackend`) | **MOCK** | Phase-4 deterministic mock reasoner; holds no credential; a live frontier conductor is out of scope (§2.4 lifted only for one worker provider). Succession proven live at gate/phase-11. |
| frontier_worker | mock | **MOCK** (owed) | Live `claude_code` adapter exists (gate/phase-14b); operator auth recorded (OP-4/OP-5) but the **enforced runtime gate `LIVE_OPERATION_AUTHORIZED` is consulted at classification time and returns DENIED-by-absence** (config/live_operation.json intentionally unwritten, inv 1); single live `claude` smoke is SKIP-WITH-RECORD pending [OPERATOR] R8 §6 dated live-terms. **live is OWED, never claimed.** |
| coding_worker | opencode+ollama | **DETERMINISTIC_SUBSTITUTE** | OpenCode proven driven LIVE at gate/phase-14c (real spawn, tool-exec, worktree confinement against `ollama/qwen2.5-coder:7b`) but no live local-coder LANDED edit (U31); the CANDIDATE→gate→merge chain was closed with a deterministic seeded edit (`from_live_model=False`). |
| local_reasoning_worker | ollama | **LIVE** | Real detected local Ollama model (`ollama/qwen3:8b`) on 127.0.0.1, §2.4-permitted, no credentials. The item-7 smoke below is the live receipt that a real generate succeeds on this host. |

`live_roles = ['local_reasoning_worker']` · `owed_roles = ['frontier_worker']`. Under
`allow_live=False` (the deterministic view) **no leg is LIVE** — only real host detection
unlocks a live label (fail-closed).

## 4. Item-7 receipt — on-host Ollama smoke re-run (executed LIVE)

`py -3.12 -m tools.assembled.roster_report` → `item7_ollama_smoke`:

```
available        True
model            qwen2.5:7b-instruct
generated        True
latency_s        4.171
response_preview 'SOVEREIGN'
done_reason      stop
eval_count       5
n_models         43            (real model list enumerated from 127.0.0.1:11434/api/tags)
coder_models     ['qwen3-coder:30b', 'deepseek-coder-v2:latest', 'qwen2.5-coder:7b', 'qwen2.5-coder:32b']
```

This is a **real daemon generation**, not artifact-attestation — it discharges
STATUS_RECONCILIATION §3 item 7 exactly. The smoke prefers a clean non-thinking instruct
model (its answer lands in `response`); a thinking-family model (e.g. qwen3) answers in a
separate `thinking` field, so the receipt counts **either** field as a real generation — it
proves the daemon+model ran, not one family's output-formatting quirk. Fail-closed: if the
daemon is unreachable, or the `/api/generate` fails after a reachable `/api/tags`,
`available`/`generated` report honestly and **nothing is fabricated** (§6/§10.4).

## 5. Self-check against exit criteria (real command output)

- **Four assembled roles present + honestly classified** — `test_four_assembled_roles_present_and_ordered`, `test_every_role_has_a_reason_and_valid_liveness` PASS.
- **Frontier never claimed live; gate state reflects the real enforced gate** — `test_frontier_worker_is_mock_and_owed_not_claimed_live`, `test_frontier_gate_state_matches_real_authorization` (asserts DENIED-by-absence, never "satisfied") PASS.
- **Conductor MOCK + no credential; no token/secret field leaks (§2.2)** — `test_conductor_is_mock_and_carries_no_credential`, `test_no_role_dict_leaks_a_token_field` PASS.
- **Fail-closed smoke (no fabrication when daemon down / mid-generate failure)** — `test_smoke_degrades_honestly_when_daemon_absent` PASS; the `/api/generate` call is guarded and returns an honest `generated=False` record on failure.
- **Item-7 smoke runs live; local_reasoning is LIVE with a real model** — `test_item7_ollama_smoke_runs_live`, `test_local_reasoning_worker_is_live_when_ollama_present` **RAN (not skipped)** and PASS.
- **Coding worker not under-claimed as mock when a real coder is present** — `test_coding_worker_is_live_direct_when_coder_present_but_no_opencode` PASS.
- **Suite:** `py -3.12 -m pytest tests/ -q` → **466 passed, 0 failed, 0 skipped** (was 454 at gate/phase-14c; +12 this sub-step). JS suites untouched (131, no JS changed).

## 6. Independent confirmation

- **gate-validator (sub-step):** PASS_WITH_RESERVATIONS in an isolated context — re-ran the full
  and targeted suites (confirmed the two live tests actually executed, not skipped), verified the
  conductor genuinely uses `MockReasoningBackend`, confirmed no credential handling, and ran the
  live receipt itself. Reservation **R1** (frontier reason claimed "LIVE_OPERATION_AUTHORIZED is
  satisfied" while the gate is DENIED-by-absence) — **FIXED this iteration**: the classifier now
  calls `load_live_authorization().is_provider_live("claude_code")` and renders the real gate
  state; `test_frontier_gate_state_matches_real_authorization` pins it.
- **spec-auditor:** load-bearing invariants (I-3, I-7, I-10/11, I-20, §2.2, §2.4, §6/§10.4 honesty,
  determinism, fail-closed) **CLEAN**. 1 MAJOR (same as R1) + 3 MINOR + 1 nit — **ALL FIXED
  pre-commit**: MAJOR (frontier gate state) fixed as above; MINOR-1 (`/api/generate` unguarded →
  wrapped, honest failure record); MINOR-2 (local_reasoning reason no longer asserts a receipt was
  run — hedged to "when run_smoke=True"); MINOR-3 (coder present + OpenCode absent now classified
  LIVE-direct-Ollama, not a false MOCK); nit (redundant `import json` in `main()` removed).

## 7. Substitutions & honesty (directive §6/§10.4)

- The frontier live capability is **OWED, not claimed** — the enforced `LIVE_OPERATION_AUTHORIZED`
  gate is DENIED-by-absence and the single live `claude` smoke stays skip-with-record.
- The coding worker's accepted content is a **DETERMINISTIC_SUBSTITUTE** (U31: no live local-coder
  landed edit); the OpenCode drive itself was proven live at 14C but is not re-claimed here.
- Voice (14D) remains SKIP-WITH-RECORD (real Parakeet not installed) — not part of `.roster`.
- The item-7 smoke is the one genuinely-live model execution this session; every other leg is
  labeled exactly at its proven level.

## 8. Next

`phase-14e.run` — the single assembled end-to-end scenario over live MCP: one governed coding
task CANDIDATE→gate→ACCEPTED across the roster + one bounded debate + conductor replacement
mid-run + full restart/recovery, consuming this liveness matrix so no leg is upgraded beyond
what `.roster` proved. Then `.gate` closes `gate/phase-14e` (mandatory gate-validator),
writes `FINAL_PRODUCT_REPORT.md`, tags `product/complete`, and addresses the operator once
(COMPLETE).
