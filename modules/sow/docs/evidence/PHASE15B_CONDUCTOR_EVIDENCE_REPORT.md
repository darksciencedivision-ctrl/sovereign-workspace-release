# Phase 15B · sub-step `.conductor` — Evidence Report

**Date:** 2026-07-19 · **Iteration:** 40 · **Status:** PASS (sub-step; NOT the phase gate)
**Work commit:** `590b753` (carried by this paired evidence/register commit — two-commit convention)
**Phase gate:** `gate/phase-15b` remains **UNTAGGED** — the high-stakes 15B gate closes at
`.gate` with the mandatory independent gate-validator once `.gate` also lands.

## 1. Scope of this work unit

Second sub-step of Phase 15B ("Anthropic adapter: multi-model + conductor-capable", directive
§11 track 15B; register **OP-6**). Makes the **live `claude_code` backend conductor-capable** so
the Phase-4 `ConductorAdapter` (`adapters/conductor/`) can bind it as its runtime selection
(invariant 3 — the conductor is an INTERFACE + runtime selection, current selection Fable 5).

The binding reuses the **already-governed Phase-4 conductor path verbatim** (conductor-file load
order from MCP, CANDIDATE-only publish, subscription governor acquire/release at start/close,
succession export) and the **Phase-14B live-frontier gate set verbatim** (`frontier_spawn`'s five
ordered gates). The only new runtime surfaces are (a) a backend *bridge* from the worker `Backend`
(`generate`) shape to the conductor `ConductorBackend` (`propose_plan`) shape, and (b) the governed
live-conductor spawn wiring.

Deliberately **not** in `.conductor` (owed to `.gate` / operator, kept honest):
- any **live `claude` conductor call** — no live call this non-interactive session (R8 §6
  [OPERATOR] live-terms unmet; the loop does not write `config/live_operation.json`, invariant 1);
- the phase-gate **subscription-governor deep re-inspection** and native-git tag/hash re-confirm —
  `.gate`;
- reconciling the recorded executing-model from the live CLI JSON response (spec-audit NIT below) —
  a live `.gate` item; mock-first this session marks it `model_verified: False`.

## 2. What changed (working tree; base HEAD `6bc9936`)

| File | Change |
|---|---|
| `adapters/base/backend.py` *(M)* | New `ConductorBackend` `@runtime_checkable` Protocol formalising conductor-capability: `model_name: str`, `calls: int`, `propose_plan(objective, conductor_files, cycle) -> dict`. Makes "conductor-capable" a checkable claim; Phase-4 `MockReasoningBackend` and the new wrapper both satisfy it. |
| `adapters/frontier/claude_code.py` *(M)* | New **`ClaudeCodeConductorBackend`** — wraps a claude_code worker `Backend` and produces conductor DECISION dicts, so the ConductorAdapter binds the LIVE backend. Adds no authority (no spawn, no self-authorization), holds no credential (§2.2 — only calls the wrapped `generate`; the env-scrub is inherited). Pure helpers `_build_decomposition_prompt` (bounded, uses the conductor's OWN policy files, invariant 8), `_extract_json_object` + `_parse_decomposition` (fail-closed: garbage/malformed ⇒ `([], "unstructured")`, NEVER a fabricated decomposition). `claude_code_conductor_descriptor` (roster/Inspector honesty: node_class `conductor`, `conductor_capable=True`, reuses the `.modelsel` `model_ref` fallback surface). Import-time `ConductorBackend` type assertion. **Spec-audit NIT FIXED pre-commit:** `propose_plan` now stamps `model_verified: False` INSIDE the decision body (mirrors the roster `model_ref.verified`) so a CANDIDATE artifact is never read as a confirmed checkpoint. |
| `node_runtime/supervisor/conductor_spawn.py` *(NEW)* | Governed live-conductor spawn — the ONE place a live claude_code-backed conductor is born. `spawn_claude_code_conductor` runs the five ordered gates mirroring `frontier_spawn` (assert_startup on the `claude_code` provider cap + assert_provider_live re-asserted + R8 §6 operator-terms + CLI presence + governor `register_subscription` with allowance from `live_auth.terminals_per_subscription`), then binds `ClaudeCodeConductorBackend` into `ConductorAdapter` with `spawned_by_supervisor=True`. It only *registers* the subscription; the adapter acquires/releases at start()/close() (no double-count). `attempt_live_conductor_smoke` runs exactly one governed cycle (spawn → start → run_cycle → close); every gate/availability failure is **skip-with-record** with the terminal never wedged; a `BackendAuthPause` mid-cycle is a fail-closed pause that releases the terminal. `model_resolution` surfaced on every outcome. |
| `tests/integration/test_claude_code_conductor.py` *(NEW, 18 tests)* | Protocol satisfied by wrapper AND Phase-4 mock; `propose_plan` structured-parse + fail-closed-on-prose + 5-case malformed parametrization + fenced-JSON; MOCK-FIRST end-to-end through the REAL spawn entrypoint + REAL MCP publishing a CANDIDATE decision; governed smoke publishes + records model; DENIED-by-absence auth and unconfirmed terms both skip-with-record; I-X3 allowance from live_auth (OP-6=2), third conductor refused; conductor holds no credential + real-backend env-scrub inherited; auth-pause releases terminal; conductor descriptor honesty. |

## 3. Exit-criterion self-check (real command output)

**A. The Phase-4 ConductorAdapter binds the live claude_code backend and runs a governed cycle.**
`test_mock_first_conductor_publishes_candidate_decision` spawns via the real
`spawn_claude_code_conductor`, starts a real `MCPServer`, loads all 12 conductor files in declared
order (`adapter.loaded_files == CONDUCTOR_FILE_ORDER`), runs a cycle, and reads back the published
row with `read_status status="CANDIDATE"` — `kind == "decision"`, `parse_mode == "structured"`,
`model == "claude_code:conductor:fable-5"`, 2 proposed tasks. Conductor proposes CANDIDATE, never
self-promotes (invariant 16).

**B. No naked session (invariant 2 / I-C1).** `spawn_claude_code_conductor` builds
`AdapterContext(spawned_by_supervisor=True)`; `BaseAdapter.__init__` fail-closes a naked/no-profile
launch. Governed contract reused, no bypass.

**C. No credential handling (§2.2).** `adapter.holds_provider_credential() is False`; the wrapped
`ClaudeCliBackend.build_env` scrub is inherited (`test_real_backend_scrubs_credentials_conductor_path`
drops `ANTHROPIC_API_KEY`/`CLAUDE_CODE_OAUTH_TOKEN`, keeps `PATH`/`LANG`). No credential read, no
`--api-key`/`--with-api-key` anywhere in the new code.

**D. Mock-first; NO live call.** Every test injects a mock backend; the real `ClaudeCliBackend.generate`
(`subprocess`) is never reached. The single live smoke is skip-with-record; the loop wrote no
`config/live_operation.json`.

**E. Fail-closed honesty.** `_parse_decomposition` never fabricates tasks (5-case parametrized +
prose case). All five live gates apply; DENIED-by-absence auth and unconfirmed terms skip-with-record;
terminal never wedged (`active_count == 0` on every skip/pause path). The decision body carries
`model_verified: False` — the recorded model is a selection label, not a confirmed checkpoint.

**F. Invariant 3 not overclaimed.** `ConductorAdapter.capability()` still returns the selection label
`conductor_fable5`; the EXECUTING model is recorded honestly on the decision + provenance; roster
`model_ref.verified=False`/`is_fallback` surfaced.

**Command output:**
- `py -3.12 -m pytest tests/integration/test_claude_code_conductor.py -q` → **18 passed**
- `py -3.12 -m pytest tests/integration/test_claude_code_conductor.py tests/integration/test_claude_code_adapter.py tests/integration/test_conductor_adapter.py -q` → **38 passed**
- `py -3.12 -m pytest tests/ -q` → **559 passed** (was 541 at `gate/phase-15c`; +18 = exactly the
  new tests; NIT fix added a field + assertion, not a new test). JS suites untouched (no JS changed).

## 4. Substitutions (Directive §6) — recorded honestly

- **No live `claude` conductor call** — mock-first (`MockClaudeCliBackend` / a JSON-returning test
  backend). The single live conductor smoke is **skip-with-record** (directive §10.4) for two
  independent reasons: R8 §6 [OPERATOR] live-terms unmet, AND the loop does not write
  `config/live_operation.json` (invariant 1 — writing it would be self-authorization). The full
  governed path (five gates → conductor-file load → CANDIDATE decision) is proven with the mock.
- **Conductor decomposition quality** is not asserted — only orchestration mechanics. A mock/prose
  backend yields the honest `unstructured` (empty-tasks) path; a JSON backend yields `structured`.

## 5. Independent confirmation

- **gate-validator (sub-step):** PASS_WITH_RESERVATIONS. All 8 criteria met on real command output
  (18/18 conductor, 559/559 full suite, scope = exactly the 4 files, canonical untouched, no live
  call, no credential handling). Reservations non-blocking: (R1) `config/live_operation.json` exists
  in the working tree from an earlier unit (mtime 09:38, before this unit; gitignored; not created
  here; tests use their own `tmp_path` configs) — flagged for the eventual `.gate` reviewer; (R2)
  the import-time protocol assertion is a static annotation, runtime `isinstance` is in the test;
  (R3) Phase 15B is a loop/OP-register extension of directive §5.
- **spec-auditor:** CLEAN. Invariants 2/3/8/16, §2.2, §4 fail-closed/model-ID honesty, I-X3 all
  PASS; no invented governance layer, no self-authorization. One NIT (decision-body `model` field
  lacked an inline unverified marker) — **FIXED pre-commit** via `model_verified: False` + a test
  assertion; live-CLI executing-model reconciliation recorded as an owed `.gate` item.

## 6. Owed / open items (carried forward)

- **[OPERATOR] R8 §6 live-terms** + one operator-authorized live `claude` conductor smoke before any
  Anthropic conductor live-capability claim (`.gate` / operator).
- **Live executing-model reconciliation** (spec-audit NIT): on the live path, read the true model
  from the `claude` CLI JSON response rather than recording the requested slug — `.gate` live item.
- Phase-gate **subscription-governor deep re-inspection** (two live providers, allowance≤2) + native-git
  tag/hash re-confirm — `.gate`.
- U5 (verified-at-1, operator-ordered ceiling), U29, U32 — unchanged, tracked.

**Next:** `phase-15b.gate` — close `gate/phase-15b` (high-stakes, MANDATORY independent gate-validator)
verifying the full 15B chain (`.modelsel` per-node model selection → `.conductor` conductor-capable
binding) + the model-ID probe/live-smoke honesty pass; then `next_step = phase-15d`.
