# PHASE 14B SUB-STEP EVIDENCE — `.adapter` (first LIVE frontier adapter, Claude Code)
Autonomous loop iteration 22 · 2026-07-18Z · **sub-step, NOT the phase gate**
(`gate/phase-14b` is high-stakes and closes later at sub-step `.gate`, with a mandatory
independent gate-validator pass **and the subscription-governor deep re-inspection**, once
`.adapter` and `.gate` are in — mirroring the 14A pattern.)

## Objective (directive §9 table 14B, §10.1; register OP-4/OP-5; Plan §12.2/§18.3–18.4)
Build the **first live frontier adapter for Claude Code behind the base adapter contract**,
invoked by the Node Runtime supervisor as a **supervised terminal** (no naked session, inv 2).
**MOCK-FIRST then exactly ONE live smoke.** The single live call is fenced by HARD ENTRY
CONDITIONS; if any is unmet the smoke is **skip-with-record** (directive §10.4), not faked.

14B decomposition (directive §3.2): `.liveflag` (DONE, iter 20) → `.r8tos` (DONE, iter 21) →
**`.adapter` (this, iter 22)** → `.gate`. No gate tag for a sub-step.

## What was produced
- **`adapters/frontier/claude_code.py` (NEW)** — the live provider **behind the existing,
  already-governed `ModelWorkerAdapter` contract** (adapters/model_adapter.py): scoped context
  in from MCP → node-local gate → CANDIDATE out with provenance. The only new surface is the
  *backend*:
  - `MockClaudeCliBackend` — deterministic, spawns nothing; the whole governed path is proven
    with it (mock-first).
  - `ClaudeCliBackend` — the REAL subprocess (`claude -p <prompt> --output-format json`). NEVER
    invoked by the deterministic suite (exactly like `OllamaBackend`); only reachable from the
    operator-gated live smoke. Its `build_command`/`build_env`/`_classify` are pure and
    separately tested so the credential invariant is proven with no spawn.
  - `ClaudeCodeAuthError(BackendAuthPause)` — fail-closed auth/credit/rate pause (Plan §18.4).
  - `build_claude_code_adapter(...)` — configures the shared adapter as the `claude_code`
    frontier worker (subscription-backed, frontier, not offline-eligible).
- **`node_runtime/supervisor/frontier_spawn.py` (NEW)** — the **real supervisor/startup path**:
  `spawn_claude_code_terminal(...)` runs, in order and fail-closed, five gates before a live
  terminal is born: (1) `ProfileLoader.assert_startup([cap], live_auth)`; (2)
  `LiveAuthorization.assert_provider_live("claude_code")` re-asserted at the spawn site; (3) the
  R8 §6 `[OPERATOR]` live-terms confirmation; (4) `claude` CLI presence; (5)
  `SubscriptionGovernor.acquire` (I-X3, allowance 1). Only then is a supervisor-issued
  `AdapterContext(spawned_by_supervisor=True)` constructed; on any construction error the
  terminal is released (I-X3 count never wedges). `attempt_live_smoke(...)` runs EXACTLY ONE
  governed smoke and maps every gate/availability failure — and a `ClaudeCodeAuthError` — to
  **skip-with-record** with no live call.
- **`adapters/base/backend.py` (MODIFIED)** — added `BackendAuthPause` (generic fail-closed
  auth-pause the worker adapter re-raises; the supervisor pauses the node, no silent fallback).
- **`adapters/model_adapter.py` (MODIFIED)** — `execute()` now **re-raises `BackendAuthPause`**
  instead of swallowing it into a `published:False` (an auth pause is a supervisor concern, not
  a task failure). Ordinary backend faults still return structured failure as before.
- **`adapters/detect.py` (MODIFIED)** — `claude_code_available()` (detection only; never
  authenticates, never touches the credential store).
- **`adapters/roster.py` (MODIFIED)** — mock_frontier **note text only**: `build_roster` still
  returns a MOCK frontier so the deterministic suite stays all-mock; the live adapter is spawned
  ONLY via `frontier_spawn`, never from the default roster.
- **Tests (NEW):** `tests/unit/test_frontier_claude_code.py` (8),
  `tests/integration/test_claude_code_adapter.py` (6).

## Self-check — every HARD ENTRY CONDITION vs real output
- **Adapter behind the base contract; refuses a naked launch (inv 2 / I-C1):** ✓
  `build_claude_code_adapter` → `ModelWorkerAdapter(BaseAdapter)`; a non-supervisor context
  raises `NakedLaunchRefused` (`test_adapter_holds_no_credential_and_refuses_naked_launch`).
- **(1) Both gate call sites in the REAL entrypoint, driven by a test:** ✓
  `spawn_claude_code_terminal` calls `assert_startup([cap], live_auth)` **and**
  `assert_provider_live("claude_code")`. `test_real_repo_authorization_denies_live_spawn` drives
  the real entrypoint with `load_live_authorization()` (repo default path, config absent →
  DENIED-by-absence) and asserts it raises `ProfileViolation`. **This discharges the `.liveflag`
  MINOR-2 latent-enforcement** (enforcement is at the real spawn site, not just in a test).
- **(2) Operator live-terms unmet ⇒ skip-with-record:** ✓ `operator_terms_confirmed=False`
  raises `LiveTermsNotConfirmed` at the entrypoint (no terminal acquired), and
  `attempt_live_smoke` maps it to `ran=False, skipped_with_record=True`
  (`test_live_smoke_unconfirmed_terms_also_skips_with_record`).
- **(3) I-X3 = exactly ONE terminal; allowance stays 1:** ✓ a second spawn on the same
  subscription raises `SubscriptionLimitExceeded`, active_count stays 1
  (`test_second_terminal_on_subscription_is_refused`); the spawn registers allowance=1 and
  **`subscription_governor.py` is unchanged** (R8 finding upheld).
- **(4) Adapter NEVER reads/extracts/stores/transmits the credential (§2.2):** ✓
  `holds_provider_credential()` is False; `build_command` carries no api-key/token/permission-
  bypass flag; `build_env` **scrubs every credential- or endpoint-bearing var** — the documented
  `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_BASE_URL`/
  `ANTHROPIC_API_URL`, Bedrock/Vertex `AWS_*`/`GOOGLE_*` creds — **plus** a fail-closed superset
  (any `ANTHROPIC_*`/`AWS_*`/`GOOGLE_*`/`CLAUDE_CODE_*` prefix or `*TOKEN*`/`*SECRET*`/`*API_KEY*`
  substring) so a NEW provider var is scrubbed by default, not transmitted. Non-secret vars
  (PATH, proxies, locale, temp) are preserved so the CLI still runs
  (`test_real_backend_env_scrubs_all_credential_and_endpoint_vars`,
  `test_real_backend_command_carries_no_credential`). No credential file is read anywhere in the
  new code. `ClaudeCliBackend.generate` is not exercised by the default suite.
- **(5) Loop did NOT write `config/live_operation.json`; expiry ⇒ fail-closed pause, no API-key
  fallback:** ✓ `git ls-files config/` shows only `live_operation.example.json`; the real config
  is absent (creating it IS self-authorization once a live path exists — inv 1). An auth/credit/
  rate pause raises `ClaudeCodeAuthError`, **propagates** through `execute()` (re-raise, not
  swallow) and is reported by `attempt_live_smoke` as a fail-closed pause with the terminal
  released (`test_auth_pause_propagates_to_fail_closed_skip`). No fallback path exists — the env
  scrub removes every alternate credential.

## THE single live smoke — outcome this session (honest)
Attempted through the real path with the real in-repo authorization
(`test_live_smoke_skips_with_record_under_repo_authorization`): **`ran=False,
skipped_with_record=True, published=False`, NO live call.** Two independent reasons, either
sufficient: (a) `config/live_operation.json` is absent (DENIED-by-absence) and the loop must not
create it (§10.4 entry condition 5); (b) the R8 §6 `[OPERATOR]` dated live-terms retrieval +
support confirmation are unmet in this non-interactive session. This is the correct
skip-with-record, not a failure (directive §10.4); the rest of Phase 14 is unaffected. The
**mock-first** proof (`test_mock_first_governed_spawn_publishes_candidate`) exercises the exact
same governed path end-to-end (MCP scoped context → local gate PASS → CANDIDATE in MCP,
content-addressed, provenance-bearing) with the mock backend, so the mechanics are proven; only
the live `claude` subprocess call is deferred to an operator-authorized run.

## Independent review (this iteration)
- **gate-validator (sub-step confirmation): PASS_WITH_RESERVATIONS.** All functional criteria
  A–G pass on direct evidence; it re-ran the suite (**12 targeted, 399 full** at review time) and
  traced the refusal path. Reservations (owned, non-blocking): (R1) the validator's Bash `git`
  was denied, so "governor byte-unchanged / canonical untouched / real config untracked" rest on
  filesystem + `.gitignore` + content inspection — the `.gate` (high-stakes) validator MUST
  re-confirm with native git; (R2) no live capability was actually exercised (by design;
  skip-with-record) — the single live subprocess path is owed to `.gate`/operator run.
- **spec-auditor: 2 MAJOR + 2 MINOR — ALL FIXED this iteration, re-tested green:**
  - **MAJOR-1** (credential env scrub incomplete + overclaiming docstring): FIXED — `build_env`
    now scrubs the full documented key set **and** a fail-closed prefix/substring superset
    (`_is_credential_key`); docstrings corrected to state exactly what is enforced (no
    "guarantees" overclaim). New test covers `CLAUDE_CODE_OAUTH_TOKEN`, endpoint overrides,
    Bedrock/Vertex creds, and a future `*_API_KEY`/`*SECRET*` var.
  - **MAJOR-2** (fail-closed `ClaudeCodeAuthError` pause path was unreachable because
    `ModelWorkerAdapter.execute` swallowed every exception): FIXED — introduced generic
    `BackendAuthPause`; `ClaudeCodeAuthError` subclasses it; `execute()` re-raises it;
    `attempt_live_smoke` reports the pause and releases the terminal. New regression test
    `test_auth_pause_propagates_to_fail_closed_skip` exercises the previously-dead path.
  - **MINOR-1** (over-broad auth substrings could mislabel ordinary faults): FIXED — markers
    tightened to specific phrases (`http 401`, `credit balance`, …); test asserts a benign
    "…defines 403…" string is NOT classified as auth.
  - **MINOR-2** (smoke `reason` embedded the raw result dict): FIXED — bounded, structured reason.
- spec-auditor confirmed CLEAN on the load-bearing invariants (inv 1 no self-authorization; inv 2
  no naked session; inv 4 one contract; inv 7/I-M2 nothing added to `mcp_server/`; inv 10
  CANDIDATE-only; inv 16/§4 deterministic fail-closed gates; inv 21/I-X3; §10.1 single provider).

## Test results (real command output, py -3.12 / node)
- `pytest tests/unit/test_frontier_claude_code.py tests/integration/test_claude_code_adapter.py
  tests/integration/test_multi_model_adapters.py -q` → **17 passed**.
- Full suite `pytest tests/ -q` → **401 passed, 36 warnings** (was 387 pre-14b.adapter;
  +14 net new tests; pre-existing `jsonschema.RefResolver` deprecations only).
- JS suite **131** unchanged (no JS touched this iteration).

## Substitutions / deferrals (directive §6; honest record)
- **The single live smoke is skip-with-record** (no `claude` subprocess ran) — the real
  `ClaudeCliBackend.generate` path is proven only at the pure command/env layer; the end-to-end
  live subprocess is deferred to `.gate`/operator run (entry conditions unmet: config absent by
  design; `[OPERATOR]` live-terms unconfirmed). Recorded, not faked.
- **`[OPERATOR]` live-terms items** (R8 §6): dated Consumer Terms + Usage Policy + Claude Code
  headless-docs retrieval and any concurrency support-confirmation remain hard gates the
  `.gate`/operator run MUST satisfy before the live smoke.

## Invariant touchpoints
- **Inv 1 (operator final authority; app never self-authorizes):** the live path is fenced by an
  operator-owned `LIVE_OPERATION_AUTHORIZED` config the loop cannot fabricate or widen; the loop
  did not write it.
- **Inv 2 (every terminal a Sovereign node; no naked session):** adapter refused unless
  supervisor-issued.
- **Inv 4 (workers interchangeable behind adapter contracts):** the live provider is the same
  `ModelWorkerAdapter` + `Backend` protocol as the mock/local backends.
- **Inv 21 / I-X3 (one frontier terminal per subscription):** allowance stays 1; second refused.
- **Prohibition §2.2 (no credential handling):** honored — the adapter invokes the host CLI whose
  own host-native store holds the OAuth token; the env is scrubbed of every credential/endpoint
  var; no key is created, read, stored, or transmitted.

## Disposition
`phase-14b.adapter` PASSED as a **sub-step** (not the phase gate). `gate/phase-14b` remains
**UNTAGGED** — the high-stakes phase gate awaits sub-step `.gate` (mandatory gate-validator + the
subscription-governor deep re-inspection). Next: `phase-14b.gate`.
