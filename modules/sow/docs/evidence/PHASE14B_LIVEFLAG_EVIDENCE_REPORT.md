# PHASE 14B SUB-STEP EVIDENCE — `.liveflag` (LIVE_OPERATION_AUTHORIZED gate)
Autonomous loop iteration 20 · 2026-07-18Z · **sub-step, NOT the phase gate**
(`gate/phase-14b` is high-stakes and closes later at sub-step `.gate`, with a mandatory
independent gate-validator pass, once all 14B sub-steps land — mirroring the 14A pattern).

## Objective (directive §9 track 14B, §10.1; register OP-4/OP-5)
Phase 14B introduces the first live frontier adapter — **exactly one provider: Claude Code**
(OP-5). Directive §10.1 requires, *before any live call*, that an **enforced
`LIVE_OPERATION_AUTHORIZED` config exist FIRST**, read by the roster/profile loader,
fail-closed, citing register row **OP-4**, scoped `{provider: claude_code, terminals: 1}`.

This sub-step delivers **that gate and nothing that calls live**. Rationale (directive
§10.1): for the whole staged build the frontier ran mock, so live operation was impossible
*because no live path existed* — enforcement-by-absence. The moment a live adapter is wired
(next sub-step `.adapter`) that natural barrier is gone, so the explicit fence must already
be in place. It is landed here, first.

14B is large and decomposed (directive §3.2): **`.liveflag` (this) → `.r8tos` (ToS record) →
`.adapter` (claude CLI adapter, mock-first then one live smoke) → `.gate`**. No gate tag for a
sub-step.

## What was built (deterministic permission logic — never model output; Directive §4)
- **`control_plane/profiles/live_authorization.py` (NEW)** — the fail-closed loader/gate:
  - `load_live_authorization(path=None)` — resolution order explicit `path` > env
    `SOVEREIGN_LIVE_OPERATION_CONFIG` > repo default `config/live_operation.json`.
  - **Enforcement-by-absence:** no config ⇒ `LiveAuthorization.denied(...)` (`authorized=False`),
    NOT an error and NOT a permit.
  - **Fail-closed on malformed/out-of-scope by RAISING** `LiveAuthorizationError` (never coerced
    to a permit, never silently downgraded to a quiet denial that could mask operator error):
    bad JSON, `config_version != "1.0"`, non-bool flag, missing required field, `register_row !=
    "OP-4"`, `scope.provider != "claude_code"`, `scope.terminals != 1` (with a `bool`-exclusion
    guard so `True` cannot masquerade as `1`).
  - **Scope is NOT config-widenable:** the authorized provider (`claude_code`), register row
    (`OP-4`), and terminal count (`1`) are module constants checked against the config; a config
    naming a second provider or >1 terminal fails closed — a second provider needs a NEW operator
    authorization, never a wider file.
  - `LiveAuthorization.assert_provider_live(provider)` — the gate every future live-spawn path
    MUST call; raises unless live is authorized for exactly that provider. `denied()` is the
    fail-closed default constructor.
- **`control_plane/profiles/loader.py`** — `ProfileLoader.assert_startup(caps, live_auth=None)`
  now also calls `check_live_authorized`: a **real** subscription-backed frontier adapter
  (`subscription_backed and adapter != "mock"`) is refused at startup unless `live_auth`
  authorizes its provider. Fail-closed: `live_auth=None` (omitted) is a denial, not a pass. Mock
  frontiers carry no live path and need no authorization.
- **`adapters/roster.py`** — `build_roster(..., live_auth=None)` consults the gate (loads it if
  not injected) and records the disposition honestly in the frontier entry's notes. **The
  frontier STAYS MOCK** — the live claude_code adapter is not wired until `.adapter`.
- **`config/live_operation.example.json` (NEW, tracked)** — template only. The real
  `config/live_operation.json` is **gitignored** (`.gitignore` updated), so a fresh clone is
  DENIED-by-absence in-repo. No active authorization is committed; this session makes no live call.

## Self-check — exit criteria vs real command output
- **`py -3.12 -m pytest tests/unit/test_live_authorization.py -q` → 20 passed.** Covers:
  absent⇒denied; flag-false⇒denied; malformed JSON / bad version / non-bool / missing field ⇒
  raise; wrong register row ⇒ raise; second provider ⇒ raise; >1 terminal ⇒ raise (incl.
  `True`/float coercion caught by the bool/int guard); valid config authorizes claude_code ONLY
  (other provider still refused); env-override path; repo-default absent⇒denied; ProfileLoader
  refuses a live frontier without/omitting authorization, permits it with authorization, allows a
  mock frontier without authorization, and **refuses an unknown/future subscription-backed
  provider even with a valid claude_code authorization present** (fail-closed denylist, not a
  claude_code allowlist).
- **`py -3.12 -m pytest tests/ -q` → 387 passed** (367 prior + 20 new), 36 pre-existing
  deprecation warnings only (jsonschema RefResolver, unrelated). No regressions from the roster
  now auto-loading the gate.
- **`git status --porcelain` / `git ls-files config/`** confirm the real `config/live_operation.json`
  is absent and untracked (only the `.example.json` template is staged); `.gitignore` carries
  `config/live_operation.json`; `git status docs/canonical/` is empty (canonical set untouched).
- **No live call:** the sub-step adds a gate and a template; nothing invokes the `claude` CLI or
  any provider. `.adapter` will.
- **JS suites untouched this sub-step** (no JS files changed; last recorded 131 JS green).

## Substitutions / deferrals (directive §6; honest record)
- **No frozen schema added.** `schemas/` is frozen at exactly twelve @1.0 files (schemas/README);
  the live-operation config is a runtime authorization switch, not a governed message envelope, so
  it is validated by deterministic Python checks in the loader — not a new schema file.
- **No active authorization committed.** OP-4/OP-5 authorize live, but `.liveflag` makes no live
  call by design; the real config stays gitignored so the repo default is DENIED. The operator (or
  the `.adapter` host run) drops the real `config/live_operation.json` when the live smoke runs.
- **R8 ToS verification** for Claude Code is the NEXT sub-step (`.r8tos`), required before the
  first live call (directive §10.1) — not part of `.liveflag`.

## Independent gate-validator (sub-step confirmation)
**VERDICT: PASS_WITH_RESERVATIONS** (isolated context; all commands re-run independently). All
five directive §10.1 criteria met on inspected evidence: the gate is landed first, fail-closed,
scoped exactly to OP-4/OP-5/I-X3, read by both roster and profile loader, and makes NO live call
(grep of `control_plane/profiles/` for `subprocess|Popen|requests|urllib|http|anthropic|api_key|
socket` → no matches; no `adapters/**/claude_code*` file exists; frontier hardcoded mock). Bool/
float coercion on `terminals` confirmed caught. Full suite 386→**387 pass** after the R2 fix.
Reservations: **R1** — the validator's Bash tool denied `git`, so it could not confirm tracking
via git; it verified via Glob (real config absent) + `.gitignore`. **Closed in this report**: I ran
`git ls-files config/` (real config untracked) and `git status docs/canonical/` (empty) directly.
**R2** — the mock/live distinction keyed on the adapter-name string `"mock"`; a real adapter
mislabeled `"mock"` could bypass. **ADDRESSED this iteration** (see below) — same issue the
spec-auditor raised as MINOR-1.

## spec-auditor (substantive new code)
**VERDICT: CLEAN on all load-bearing invariants** (inv 1 operator-authority/no-self-authorization,
inv 7 no-authz-in-MCP, inv 16/30 explicit-gate/minimal-control, inv 21/I-X3, §4 deterministic/
fail-closed, §2.2 no-credential-handling), + 2 MINOR:
- **MINOR-1 (= validator R2): live gate keyed on the `"mock"` name string (fail-open direction).**
  **FIXED this iteration.** `_is_live_subscription` now keys on a named constant `_MOCK_ADAPTER =
  "mock"` documented as the *reserved* mock-backend sentinel from `node.schema.json`'s frozen
  `adapter` enum, deliberately a **denylist** so any other subscription-backed adapter — including a
  provider added to the enum later — is treated as a live path and requires authorization
  (fail-closed). Note (rejecting the auditor's `subscription_backed=False`-for-mock alternative):
  `subscription_backed` alone cannot be the signal because the mock *conductor*
  (`adapters/conductor/adapter.py:53`) is subscription-backed by node class yet has no live backend
  — keying purely on it would wrongly force the mock conductor to need live authorization. New test
  `test_startup_refuses_unknown_future_frontier_provider` pins the fail-closed denylist direction.
- **MINOR-2: the gate is currently latent (assert_startup / build_roster invoked only from tests).**
  ACCEPTED for `.liveflag` (no live spawn path exists yet). **Recorded as an explicit `.adapter`
  entry condition:** when the live claude_code adapter is wired, the real supervisor/startup path
  MUST call `ProfileLoader.assert_startup(caps, live_auth=load_live_authorization())` before any
  live spawn, AND the primary unbypassable gate `LiveAuthorization.assert_provider_live(provider)`
  must be called at the live-spawn site itself, with a test driving that real entrypoint. The
  `.adapter` reviewer must also confirm nothing in the autonomous loop writes
  `config/live_operation.json` itself (creating that file IS the authorization — self-writing it
  would be self-authorization once a live path exists).

## Invariant touchpoints
- **Inv 1 (operator holds final authority; app never self-authorizes):** authorization is
  operator-granted (OP-4) and fail-closed; the app cannot self-grant — absence/malformed/out-of-
  scope all deny.
- **Inv 7 (MCP is access, not authority):** no authorization logic added inside `mcp_server/` —
  the gate lives in `control_plane/profiles/`.
- **Inv 16/30 (explicit gates; minimal necessary control):** one explicit, deterministic gate; no
  invented governance layer.
- **Inv 21 / I-X3 (one frontier terminal per subscription):** `terminals: 1` enforced; >1 fails
  closed. The existing `SubscriptionGovernor` continues to bound concurrency at spawn.
- **Prohibition §2.2 (no credential handling):** the gate reads an authorization *flag* only; it
  reads/stores/transmits NO credential.

## Disposition
`phase-14b.liveflag` PASSED as a **sub-step** (not the phase gate). `gate/phase-14b` remains
UNTAGGED — the high-stakes phase gate awaits sub-steps `.r8tos`, `.adapter`, `.gate`. Next:
`phase-14b.r8tos`.
