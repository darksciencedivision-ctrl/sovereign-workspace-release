# Phase 15B · sub-step `.modelsel` — Evidence Report

**Date:** 2026-07-19 · **Iteration:** 39 · **Status:** PASS (sub-step; NOT the phase gate)
**Work commit:** `9b6b11e` (carried by this paired evidence/register commit — two-commit convention)
**Phase gate:** `gate/phase-15b` remains **UNTAGGED** — the high-stakes 15B gate closes at
`.gate` with the mandatory independent gate-validator once `.conductor` and `.gate` also land.

## 1. Scope of this work unit

First sub-step of Phase 15B ("Anthropic adapter: multi-model + conductor-capable", directive
§11 track 15B; OP-7 revised order 15A→15C→**15B**; register **OP-6**). Extends the **live
`claude_code` frontier adapter** (gated at `gate/phase-14b`) with **per-node model selection**
(`--model`) and an **honest, roster-surfaced model-ref / fallback recording**, mirroring the
`codex` model-selection design landed and gated at `gate/phase-15c` (`resolve_codex_model_ref`
/ `codex_roster_descriptor`).

Deliberately **not** in `.modelsel` (owed to `.conductor` / `.gate`, kept honest):
- making the backend **conductor-capable** (the Phase-4 `ConductorAdapter` binding) — `.conductor`;
- any **live `claude` call** / per-model live smoke — no live call this non-interactive session
  (R8 §6 [OPERATOR] live-terms unmet; the loop does not write `config/live_operation.json`);
- the phase-gate **subscription-governor deep re-inspection** — `.gate`.

The backend selector is the only new runtime surface; the governance path (scoped MCP context
in → node-local gate → CANDIDATE out with provenance) is the shared, already-governed
`ModelWorkerAdapter`, reused verbatim.

## 2. What changed (working tree; base HEAD `f8f071a`)

| File | Change |
|---|---|
| `adapters/frontier/claude_code.py` *(M)* | Per-node model selection + honest model-ref recording: `CLAUDE_CODE_MODEL_FLAG="--model"`; `CandidateModelRef` dataclass + `CLAUDE_CANDIDATE_MODEL_REFS` (operator-named **opus-4.8** and **fable-5**, both `verified=False` — the CLI has no offline model-list, so an accepted id is only confirmed by a live smoke; never a fabricated slug); `resolve_claude_model_ref` (requested slug carried verbatim & unverified; `None`/blank ⇒ CLI-default **recorded roster fallback**, never silent); `claude_code_roster_descriptor` (embeds a `model_ref` block {requested, resolved_slug, verified, is_fallback, note} + the candidate mapping into the roster surface; `capability_descriptors` deep-copied for immutability hygiene, matching the 15C .gate NIT fix). `MockClaudeCliBackend` and real `ClaudeCliBackend` gain a `model` param; `build_command` emits `--model <slug>` only when a model is requested (default omits it ⇒ CLI default). The §2.2 command/env invariant is unchanged — a slug carries no credential and the env-scrub is untouched. **Spec-audit NIT-1 FIXED pre-commit (codex parity):** `build_command` now runs a fail-closed `_assert_no_forbidden(argv)` guard over the flags (`_FORBIDDEN_CLAUDE_ARGS` = `--dangerously-skip-permissions`/`--api-key`/`--with-api-key`/`--with-access-token`), guarded before the prompt is appended, so a per-node model slug can never smuggle a permission-bypass flag while a benign flag-shaped prompt stays a positional value. |
| `node_runtime/supervisor/frontier_spawn.py` *(M)* | Thread `model` through the REAL spawn entrypoint: `spawn_claude_code_terminal(..., model=None, ...)` resolves the `--model` slug through the single honest resolver (`resolve_claude_model_ref`) and constructs `ClaudeCliBackend(model=resolved_model)`; `attempt_live_smoke(..., model=None, ...)` surfaces `claude_code_roster_descriptor(model)` as `LiveSmokeOutcome.model_resolution` on **every** outcome — including skip-with-record and auth-pause — so which model (or the CLI-default fallback) would have run is never silent (directive §11 15B). |
| `tests/unit/test_frontier_claude_code.py` *(M)* | +5 deterministic unit tests: resolver carries requested slug / falls back honestly (blank ⇒ default, not empty slug); `build_command` selects `--model` only when requested + no credential/bypass; roster descriptor surfaces the model_ref + fallback + candidate mapping (all unverified); descriptor is immutable against caller mutation; mock backend name reflects the selected model. |
| `tests/integration/test_claude_code_adapter.py` *(M)* | +2 integration tests through the REAL `frontier_spawn` entrypoint + REAL MCP: a per-node `model` rides through to the published CANDIDATE; `attempt_live_smoke` surfaces `model_resolution` on a skip-with-record (requested model AND CLI-default fallback branches). |

## 3. Exit-criterion self-check (real command output)

**A. Per-node model selection exists.** `ClaudeCliBackend(model="opus-4.8").build_command(...)`
emits `--model opus-4.8`; `ClaudeCliBackend().build_command(...)` (and a blank `model="   "`)
omits `--model` (CLI default). Proven by `test_real_backend_command_selects_model_when_requested`.

**B. Model-id honesty (directive §11 15B).** opus-4.8 and fable-5 are recorded as UNVERIFIED
candidates (`verified=False`); `resolve_claude_model_ref` never fabricates an accepted slug; an
absent/blank model resolves to a RECORDED CLI-default fallback (`is_fallback=True`, note carries
"fallback"), surfaced in `claude_code_roster_descriptor`. Proven by
`test_resolver_carries_requested_slug_and_falls_back_honestly` +
`test_roster_descriptor_surfaces_model_ref_and_fallback`.

**C. Credential invariant §2.2 holds.** The `--model` path carries no key on the command line
(asserted in the unit test) and does not touch `build_env`. The pre-existing
`test_real_backend_env_scrubs_all_credential_and_endpoint_vars` remains green.

**D. Threads through the REAL entrypoint; resolution never silent.** `model` flows through
`spawn_claude_code_terminal` and `attempt_live_smoke`; `LiveSmokeOutcome.model_resolution` is
present on every outcome. Proven by `test_per_node_model_selection_end_to_end` +
`test_live_smoke_surfaces_model_resolution_even_on_skip`.

**E. No live call; no self-authorization.** The deterministic suite makes no `claude` subprocess
call (only the pure `build_command`/`build_env` are exercised; the mock backend spawns nothing).
The loop does not write `config/live_operation.json`.

### Commands
```
py -3.12 -m pytest tests/unit/test_frontier_claude_code.py tests/integration/test_claude_code_adapter.py -q
# 23 passed

py -3.12 -m pytest tests/ -q
# 541 passed  (baseline 533 at gate/phase-15c; +8 = 6 unit + 2 integration)
```
JS suites untouched (149; no JS changed this sub-step).

## 4. Substitutions (directive §6) & honesty notes

- **No live `claude` call this session** — the accepted-id verification for opus-4.8 / fable-5 and
  the one-smoke-per-available-model are deferred to `.conductor` / `.gate` + operator (R8 §6
  [OPERATOR] live-terms unmet; the loop must not create `config/live_operation.json` = no
  self-authorization once a live path exists, inv 1). The mock-first path proves the exact same
  governed MCP → local-gate → CANDIDATE flow with the selected model. **No live-capability claim.**
- **Conductor-capability is NOT claimed here** (invariant 3 preserved) — it is the `.conductor`
  sub-step; this unit adds only worker-path model selection.

## 5. Invariants exercised

Inv 2 (no naked sessions — supervised spawn unchanged), inv 3 (conductor is an interface — not
touched/overclaimed here), inv 10/11 (CANDIDATE + provenance path reused verbatim), §2.2 (no
credential handling — command/env invariant preserved), §4 (deterministic, fail-closed resolver +
descriptor; blank ⇒ default, never an empty slug), directive §11 15B (probe/record model IDs;
unavailable ⇒ recorded fallback surfaced in the roster, never silent).

## 6. Verdicts

- **Self-check:** all `.modelsel` criteria PASS on real command output (above).
- **spec-auditor:** **CLEAN** — every load-bearing invariant PASS (credential §2.2, model-id
  honesty §11 15B, conductor non-overclaim [inv 3], determinism/fail-closed §4, no live call, no
  drift). Two NITs: **NIT-1** (codex-parity defense-in-depth guard absent in `build_command`) —
  **FIXED pre-commit** + regression test `test_build_command_refuses_permission_bypass_slug`;
  **NIT-2** (cosmetic mock-normalization inconsistency; claude's is the more honest of the two) —
  accepted, no change.
- **gate-validator (sub-step):** **PASS** (no reservations). Independent, isolated context; every
  criterion re-inspected in source and re-run. All six exit criteria confirmed (per-node `--model`;
  model-id honesty with no `verified=True`/fabricated slug anywhere; §2.2 strengthened by the new
  `_assert_no_forbidden` guard, refutation `model="--dangerously-skip-permissions"` ⇒ `ValueError`;
  model threads through the real entrypoint with `model_resolution` on all three smoke paths; no
  live call, every test config write targets `tmp_path`, `config/live_operation.json` untracked +
  gitignored; no regression). Scope clean (exactly the 4 intended files; no canonical/product drift).

`gate/phase-15b` stays **UNTAGGED**; next `next_step = phase-15b.conductor`.
