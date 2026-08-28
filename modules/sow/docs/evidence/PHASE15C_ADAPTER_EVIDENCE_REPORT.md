# Phase 15C · sub-step `.adapter` — Evidence Report

**Date:** 2026-07-19 · **Iteration:** 37 · **Status:** PASS (sub-step; NOT the phase gate)
**Work commit:** _(carried by the paired evidence/register commit — two-commit convention)_
**Phase gate:** `gate/phase-15c` remains **UNTAGGED** — the high-stakes 15C gate closes at
`.gate` with the mandatory independent gate-validator (+ subscription-governor deep
re-inspection, now two live providers under allowance=2) once `.gate` lands.

## 1. Scope of this work unit

Second sub-step of Phase 15C ("OpenAI adapter — Codex CLI", directive §11 track 15C; §12
OP-7 revised order 15A→**15C**; register **OP-6**). Builds the **live `openai_codex_cli`
frontier adapter** behind the SAME governed `ModelWorkerAdapter` contract as `claude_code`
(adapters/frontier/claude_code.py + node_runtime/supervisor/frontier_spawn.py, gated at
`gate/phase-14b`), **mock-first** with the single live smoke **skip-with-record** (no live
`codex exec` call this non-interactive session).

The backend is the only new surface; the governance path (scoped MCP context in → node-local
gate → CANDIDATE out with provenance) is the shared, already-governed adapter, reused verbatim.
The fail-closed supervised spawn (LIVE_OPERATION_AUTHORIZED / I-X3 / R8 operator-terms / CLI
presence) lives in the real startup path `node_runtime/supervisor/codex_spawn.py`.

## 2. What changed (working tree; base HEAD `ce65bce`)

| File | Change |
|---|---|
| `adapters/frontier/codex.py` *(M; `.detect` probe above line 305 unchanged)* | The `.adapter` additions: two worker roles (`reasoning`→`worker_reasoning` read-only, `coding`→`worker_coding_specialist` workspace-write) with capability descriptors; `resolve_codex_model_ref` (honest — a requested slug is carried verbatim & unverified, `None`⇒CLI-default recorded roster fallback, never a fabricated slug); `MockCodexCliBackend` (deterministic, spawns nothing) + real `CodexCliBackend` (`codex exec [-m <slug>] --sandbox <mode> [--cd <worktree>] <prompt>`); `build_command`/`build_env` **pure & separately tested**; `_assert_no_forbidden` structurally refuses every credential/bypass flag (`--with-api-key`/`--with-access-token`/`--api-key`/`--dangerously-bypass-*`/`danger-full-access`/`--full-auto`); env-scrub SUPERSET (`OPENAI_*`/`AZURE_*`/`ANTHROPIC_*`/`AWS_*`/`GOOGLE_*` prefixes + bare `KEY`/`AUTH`/`CREDENTIAL`/`TOKEN`/`SECRET`/`API_KEY` substrings; `CODEX_HOME` preserved — a dir pointer, not a secret); `CodexAuthError(BackendAuthPause)` fail-closed pause; `build_codex_adapter`. **Spec-audit MINOR-1 FIXED pre-commit:** a coding (`workspace-write`) backend with no isolated worktree is refused at construction (would run `cwd=None` = the supervisor's dir ≈ repo root → whole-tree write; T2/Phase-10 fail-closed) + defense-in-depth guard in `build_command`. **NIT-1 FIXED:** `_assert_no_forbidden` now guards the flag slice (prompt not yet appended). |
| `node_runtime/supervisor/codex_spawn.py` *(new)* | The governed live-Codex spawn path — the ONE place a live `openai_codex_cli` terminal is born. Mirrors `frontier_spawn.py`: **5 ordered gates** — (1) `ProfileLoader.assert_startup([cap], live_auth)` driving the REAL entrypoint; (2) `LiveAuthorization.assert_provider_live("openai_codex_cli")` re-asserted at the spawn site; (3) R8 §6 `[OPERATOR]` live-terms confirmation → `LiveTermsNotConfirmed`; (4) `codex` CLI presence (real backend only); (5) `SubscriptionGovernor.acquire` with `allowance=live_auth.terminals_per_subscription` (**not** hardcoded 1). Release-on-construct-fail so the I-X3 count never wedges. `attempt_codex_live_smoke` = one governed smoke → skip-with-record on any gate/availability failure or auth pause; NO live call. |
| `tests/unit/test_frontier_codex.py` *(new)* | 12 deterministic unit tests: capability shape (live frontier, refused without authorization); coding role → `worker_coding_specialist`; adapter holds no credential + refuses naked launch; mock deterministic; **command carries no credential/bypass flag**; coding role is `workspace-write` + `--cd` worktree-scoped; default model omits `-m` + honest resolver; `danger-full-access` refused; **coding role without worktree refused fail-closed** (MINOR-1 regression); **env scrubs all credential/endpoint vars, no secret VALUE survives, `CODEX_HOME` kept**; auth-marker classifier (auth vs ordinary text); `CodexAuthError` is a `BackendAuthPause`; spawn refuses on unconfirmed operator terms (no leaked terminal). |
| `tests/integration/test_codex_adapter.py` *(new)* | 8 integration tests through the REAL `codex_spawn` entrypoint + REAL MCP server: MOCK-FIRST governed spawn publishes a CANDIDATE (reasoning + coding roles); DENIED (absent) authorization refuses at the real entrypoint; **I-X3 under OP-6** — two terminals per subscription admitted, the THIRD refused; the single live smoke **skips-with-record** under (a) DENIED authorization and (b) unconfirmed operator terms; a backend auth pause propagates as a fail-closed skip + releases the terminal. |

## 3. Exit-criterion self-check (real command output)

**A. Shared governed contract, provider-id triple-match.** `CODEX_ADAPTER == "openai_codex_cli"`
== the frozen `node.schema.json` `adapter` enum member == a member of
`live_authorization._AUTHORIZED_PROVIDERS`, so the live gate keys on it exactly.
`build_codex_adapter` configures the same `ModelWorkerAdapter` as `claude_code`; the backend is
the only new surface. Two roles map to `worker_reasoning` / `worker_coding_specialist` (both
frozen node_class enum members).

**B. Mock-first; real backend never live in the suite.** `MockCodexCliBackend.generate` is
deterministic (sha256 of prompt) and spawns nothing. The real `CodexCliBackend.generate()` is
**never called** by the deterministic suite — only its pure `build_command`/`build_env`/`_classify`
are exercised. No `codex exec <prompt>` subprocess anywhere in the tests.

**C. Fail-closed supervised spawn (5 gates), no wedge.** `spawn_codex_terminal` runs the five
ordered gates and releases the terminal on any construction failure. Enforcement is at the real
spawn site: `test_denied_authorization_refuses_live_spawn` drives the real entrypoint with a
DENIED auth and gets `ProfileViolation`, `active_count == 0`.

**D. Credential invariant §2.2.** `build_command` emits no credential/bypass flag (all in
`_FORBIDDEN_CODEX_ARGS`, structurally refused). `build_env` scrubs a superset — proven by
`test_real_backend_env_scrubs_all_credential_and_endpoint_vars`: `OPENAI_API_KEY`,
`OPENAI_BASE_URL`, `OPENAI_ORG_ID`, `CODEX_API_KEY`, `AZURE_OPENAI_API_KEY`,
`AZURE_OPENAI_ENDPOINT`, `AWS_SECRET_ACCESS_KEY`, `ANTHROPIC_API_KEY`,
`GOOGLE_APPLICATION_CREDENTIALS`, `SOME_FUTURE_API_KEY`, `VENDOR_SECRET`, `MY_ACCESS_TOKEN`,
`APP_CREDENTIAL`, `RANDOM_KEY` all removed and **no secret VALUE survives** anywhere in the child
env; `PATH`/`HOME`/`HTTP_PROXY`/`LANG`/`TEMP`/`CODEX_HOME` preserved. The adapter never reads
`~/.codex/auth.json`; the OAuth token stays in the CLI's own host-native store.

**E. T2 — node-controlled config untrusted; sandbox pinned.** An explicit `--sandbox` is always
emitted (read-only reasoning, workspace-write coding) and takes precedence over any
node-controlled `~/.codex/config.toml`/`AGENTS.md`. `danger-full-access` is refused at
construction; a `workspace-write` sandbox with no `--cd` worktree is refused fail-closed
(construction + build_command); forbidden flags cannot be smuggled (argv is a list — no shell
word-split — and `_assert_no_forbidden` checks whole-token membership).

**F. Honest per-node model selection (§6/§10.4).** `-m <slug>` only when requested;
`resolve_codex_model_ref(None)` → `(None, "…fallback…")`, a requested slug carried verbatim with
an "unverified" note; `CODEX_CANDIDATE_MODEL_REFS` stay `verified=False`. No fabricated CLI id.

**G. Worktree isolation for the coding role.** `--cd <worktree>` scopes a coding run
(`test_coding_role_command_is_workspace_write_and_worktree_scoped`); reasoning is read-only.

**H. Fail-closed auth pause not swallowed.** `CodexAuthError(BackendAuthPause)`;
`ModelWorkerAdapter.execute` re-raises `BackendAuthPause`; `attempt_codex_live_smoke` reports it
as a pause and releases the terminal — proven live-through-the-adapter by
`test_auth_pause_propagates_to_fail_closed_skip` (`active_count == 0` after, no wedge).

**I. Single live smoke = skip-with-record; NO self-authorization.** No live `codex exec` call in
the suite. `config/live_operation.json` is **not written** by this unit (only `.example.json`
tracked; the file that authorizes `openai_codex_cli` already exists from 15A `.liveauth`).
`live_authorization.py` and `subscription_governor.py` are **byte-unchanged** (not in the diff).

**Suites (real output):**
- `py -3.12 -m pytest tests/unit/test_frontier_codex.py tests/integration/test_codex_adapter.py -q`
  → **20 passed in 4.03s** (12 unit + 8 integration; 0 skipped).
- `py -3.12 -m pytest tests/ -q` → **528 passed / 0 skipped** in 124s (was 508 at
  `phase-15c.detect`; +20 = +19 authored + 1 MINOR-1 regression test).
- JS untouched this unit (no Electron-main change; **D-P14-1 not engaged**).

## 4. Invariants & prohibitions

- **§2.2 (credentials):** zero credential handling — no `--with-api-key`/`--with-access-token`; env-scrub superset; `~/.codex/auth.json` never read; expiry ⇒ fail-closed pause, no silent API-key fallback.
- **inv 1 (operator authority):** no self-authorization — no config write; every gate READS `live_auth`, never mints it.
- **inv 2 / I-C1 (no naked session):** `build_codex_adapter` raises `NakedLaunchRefused` unless `spawned_by_supervisor=True` (test-proven).
- **inv 4/23 + I-SC1 (capability-descriptor selection, never by name):** selection is by capability descriptor; the "5.5"/"5.5 Sol" labels are honest `verified=False` operator names + `-m` config, never routing keys.
- **inv 21 / I-X3:** allowance flows from `live_auth.terminals_per_subscription`, double-capped at 2 (`MAX_ALLOWANCE` + config clamp `[1,2]`); a 3rd terminal refused; release-on-construct-fail.
- **Buildout §4 / fail-closed:** deterministic permission logic; auth ambiguity ⇒ pause; unscoped write ⇒ refused.
- **§6/§10.4 honesty:** the single live smoke is skip-with-record (no live call); no live capability claimed.
- **T2:** node-controlled `AGENTS.md`/`~/.codex/config.toml` treated as untrusted; sandbox pinned; danger/bypass flags refused structurally.
- **Frozen schemas:** `CODEX_ADAPTER`/node_class values match the frozen `node.schema.json`; no frozen artifact modified.

## 5. Substitutions (directive §6) recorded

1. **The single live smoke is skip-with-record (no live `codex exec`).** Two independent, each-sufficient reasons hold this session: (a) the tests use a `tmp_path` config / DENIED-by-absence, never the repo config; (b) the R8 §6 `[OPERATOR]` live-terms (wrapped-orchestrator ToS interpretation, `R8_TOS_VERIFICATION_OPENAI_CODEX.md` §6) are unmet in a non-interactive session. Mock-first proves the identical governed path end-to-end (MCP → local gate → CANDIDATE). No live-capability claim; the per-model accepted-id resolution is owed to `.gate`/operator.
2. **Accepted model-id resolution deferred.** The Codex CLI has no offline model-list; the operator-named GPT-5.5 slugs stay `verified=False`; the honest `resolve_codex_model_ref` fallback is wired into the roster/capability descriptor at `.gate` (see U-note below).

## 6. Validator + auditor

- **gate-validator (sub-step): PASS.** Independent, isolated. Re-executed every test itself
  (**19 → then 20 after MINOR-1** — it validated at the 19-test state, before the MINOR-1 fix
  landed; the fix only *adds* a fail-closed refusal + a test, strengthening every claim). Verified
  all 10 criteria against real artifacts. Adversarial refutation on the four highest-stakes claims
  found NO hole: (a) no live codex subprocess reachable in the default suite (real `generate`
  needs authorized `live_auth` + confirmed terms + host CLI; every test injects a mock and terms
  are unconfirmed); (b) no documented OpenAI/Azure/AWS/Google credential or endpoint var escapes
  the prefix+substring+exact scrub, no secret value survives; (c) governor allowance cannot exceed
  2 (two independent hard caps, both unchanged this sub-step); (d) no naked non-supervised
  construction (`NakedLaunchRefused`). Scope clean: only the four `.adapter` files changed;
  `control_plane/profiles/live_authorization.py` + `node_runtime/supervisor/subscription_governor.py`
  UNCHANGED; `config/live_operation.json` not modified; `docs/canonical/` porcelain empty. Two
  non-blocking owned observations, both **inherited from the gate/phase-14b template** and deferred
  by design: **U32** (`CODEX_HOME` / host `~/.codex/config.toml` residual — host-operator-sourced,
  not node-controlled; a `.gate`/live-run egress item, recorded in-code) and the preserved
  `HTTP(S)_PROXY`/CA vars (host-trust, out of adapter remit, same as claude_code).
- **spec-auditor: 1 MINOR + 2 NIT; MINOR + NIT-1 FIXED pre-commit, NIT-2 deferred-by-design.**
  Load-bearing invariants all SATISFIED (inv 1 no self-authorization; inv 2 no naked session;
  §2.2 credentials; inv 4/23 + I-SC1 capability selection; inv 21/I-X3 governor-capped;
  I-10/I-M6 CANDIDATE-never-ACCEPTED via the reused adapter; Buildout §4 fail-closed;
  §6/§10.4 honesty; T2). No prohibited drift; frozen schema pins hold.
  - **MINOR-1 (T2 containment gap) — FIXED pre-commit + regression-pinned.** A coding
    (`workspace-write`) backend constructed with no `workdir` set `--sandbox workspace-write`
    with no `--cd`, running at `cwd=None` (the supervisor's dir ≈ repo root) — whole-tree write,
    the opposite of Phase-10 worktree isolation, reachable via `spawn_codex_terminal(role="coding")`
    with `workdir` omitted. Now **refused fail-closed at construction** (and defense-in-depth in
    `build_command`); new `test_coding_role_without_worktree_refused_fail_closed` pins it.
  - **NIT-1 — FIXED.** `_assert_no_forbidden` now guards the flag slice (prompt appended after),
    so a prompt equal to a flag token is never misread (and argv-as-list never word-splits anyway).
  - **NIT-2 — deferred-by-design.** `resolve_codex_model_ref`'s recorded roster fallback is not
    yet wired into the spawn/smoke path; consistent with the module's own note that accepted-id
    resolution + roster recording are owed to `.gate` (directive §11 15C). Recorded as a `.gate`
    obligation, not assumed discharged here.

## 7. Next

`.gate` — **HIGH-STAKES** Phase 15C gate, **MANDATORY** independent gate-validator +
subscription-governor deep re-inspection (now two live providers under allowance=2). Verify the
full 15C chain end-to-end (`.detect` presence/version/auth + model-id probe → `.adapter` live
backend behind the base contract + fail-closed supervised spawn, mock-first, live smoke
skip-with-record). Discharge the NIT-2 roster-fallback recording (directive §11 15C "recorded
fallback surfaced in the roster, never silent") and the U32 residual-config egress item. Re-confirm
with native git the tag lineage + frozen canonical + `config/live_operation.json` gitignored. On
PASS write `PHASE15C_EVIDENCE_REPORT.md`, two-commit, tag `gate/phase-15c`, then `next_step =
phase-15b` (OP-7 order 15A→15C→**15B**: Anthropic adapter multi-model + conductor-capable).
15C sub-steps: `.detect` ✓ · `.adapter` ✓ · `.gate` ←.
