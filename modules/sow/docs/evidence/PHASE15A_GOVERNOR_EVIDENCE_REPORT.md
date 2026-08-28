# Phase 15A · sub-step `.governor` — Evidence Report

**Date:** 2026-07-19 · **Iteration:** 32 · **Status:** PASS (sub-step; NOT the phase gate)
**Work commit:** carried by this evidence/register commit (two-commit convention)
**Phase gate:** `gate/phase-15a` remains **UNTAGGED** — the high-stakes 15A gate closes at
`.gate` with the mandatory independent gate-validator once all 15A sub-steps land.

## 1. Scope of this work unit

Second sub-step of Phase 15A ("Live activation + concurrency governor", directive §11,
register **OP-6**). `.liveauth` (iter31) delivered the enforced two-provider authorization
scope pinning `terminals_per_subscription` to `[1, 2]`. This unit wires the concurrency
governor to that authorization:

1. **Upgrade the subscription concurrency governor to the OP-6 per-subscription allowance
   of 2**, operator-ordered, **governor-capped at 2, reversible** — a hard cap enforced in
   code so nothing can widen concurrency past the operator ruling.
2. **Wire the supervised live-spawn path to read the allowance from
   `LiveAuthorization.terminals_per_subscription`** instead of the hardcoded `allowance=1`.
3. **Expose the `n/2` count** for the shell status bar (data only — `status()` already
   yields `in_use`/`allowance`).
4. **Directive-named subscription-governor deep re-inspection:** release-before-acquire on
   succession holds; the governor cannot be raised on inference; a 3rd terminal is still
   refused; fail-closed re-tested.

**Deferred to later 15A sub-steps** (recorded, not done here): dated R8 records for both
providers (`.r8`); the `n/2` count rendered in the shell status bar (`.statusbar`, JS/Electron
— the D-P14-1 constraint applies: new JS touching Electron main must be exercised under
Electron's embedded runtime before its gate closes); the phase-gate close (`.gate`).
**No JS was touched in this unit.**

## 2. What changed (working tree; base HEAD `150a340`)

| File | Change |
|---|---|
| `node_runtime/supervisor/subscription_governor.py` | Added `MAX_ALLOWANCE = 2` OP-6 hard cap; `register_subscription` REFUSES `allowance > 2` (fail closed) before touching state; **default stays 1** (never raised on inference); re-registration now **reconciles** the allowance to the currently-authorized value (bounded by `MAX_ALLOWANCE`) so a mid-session operator NARROWING binds the supervised spawn, **never evicting a mid-generation holder**. Docstring updated for OP-6. |
| `node_runtime/supervisor/frontier_spawn.py` | Gate (5) now `register_subscription(..., allowance=live_auth.terminals_per_subscription)` — authorization-driven, not hardcoded 1. Module docstring gate-5 line updated. |
| `tests/unit/test_adapter_base.py` | +5 governor deep-re-inspection tests (hard cap; default-1-never-inferred; release-before-acquire at allowance 2; re-registration narrowing binds without eviction; `status()` exposes `n/allowance`). |
| `tests/integration/test_claude_code_adapter.py` | Rewrote the old "second terminal refused" test into `test_op6_two_terminals_permitted_third_refused` (allowance=2: two admitted on the same subscription, the third refused) + added `test_config_may_narrow_allowance_to_one` (a config narrowed to 1 makes the supervised spawn refuse the second). |

## 3. Design (deterministic, fail-closed — Buildout §4)

**Concurrency is authorization-driven, never self-granted (inv 1, inv 21/I-X3).** The
governor's *default* allowance is `1`. The raise to `2` is the operator's OP-6 ruling,
carried by the code-pinned `LiveAuthorization.terminals_per_subscription` (validated into
`[1, 2]` with a bool guard in `live_authorization._validate_terminals`), and read at the
spawn site. Three independent fail-closed layers keep concurrency ≤ 2:

1. `LiveAuthorization._validate_terminals` clamps a present config to `[1, 2]` (a config may
   narrow to 1, never widen past 2; `True` cannot masquerade as `1`).
2. A DENIED authorization yields `terminals_per_subscription = 0`; gates (1)/(2) of the spawn
   path (`assert_startup`, `assert_provider_live`) refuse before the governor is ever
   consulted — and even if reached, `allowance < 1` is refused.
3. The governor hard-caps at `MAX_ALLOWANCE = 2`: `register_subscription(allowance > 2)`
   raises and registers nothing — defense-in-depth against a mis-wired or widened caller.

**No mid-generation eviction.** Re-registration reconciles the stored allowance to the
authorized value; a narrowing to 1 refuses *future* acquires while leaving already-held
terminals in place until they release — the fail-closed direction (analogous to inv 22's
"never mid-generation eviction").

## 4. Self-check — every criterion with real output

Canonical interpreter `py -3.12` (3.12.10, has jsonschema).

- **Full suite:** `py -3.12 -m pytest tests/ -q` → **484 passed, 0 skipped** (was 478 at
  `.liveauth`; +6 = 5 deep-re-inspection unit tests + 2 integration tests − 1 rewritten).
- **Governor unit tests** (`tests/unit/test_adapter_base.py`): `test_governor_hard_caps_allowance_at_two`
  (allowance=3 and 99 both raise, `status()=={}`), `test_governor_default_allowance_is_one_never_raised_on_inference`,
  `test_governor_release_before_acquire_at_allowance_two`, `test_governor_reregistration_narrowing_binds_no_eviction`,
  `test_governor_status_exposes_n_of_allowance_for_status_bar` — all PASS.
- **Integration** (`tests/integration/test_claude_code_adapter.py`):
  `test_op6_two_terminals_permitted_third_refused` (2 admitted, 3rd `SubscriptionLimitExceeded`,
  `active_count` stays 2) and `test_config_may_narrow_allowance_to_one` (narrowed→2nd refused) — PASS.
- **Succession** (`tests/integration/test_conductor_succession.py`) release-before-acquire order
  `["release","acquire"]` unchanged — PASS.

## 5. Independent confirmation

- **gate-validator (sub-step): PASS.** Re-executed the full suite itself (484 passed, 0
  skipped), independently re-verified the four frozen canonical SHA-256 prefixes
  (`CC414372`/`8C9B7240`/`668089B5`/`6D3FD03B`), confirmed `frontier_spawn` is the only
  production caller of `register_subscription` and reads the allowance from `live_auth`, and
  exhausted refutation of the central claims: no path widens concurrency past 2 (governor cap
  + config clamp + `<1` guard), no live spawn without an authorized `live_auth`, no hardcoded
  allowance remains. No JS touched; `docs/canonical/` untouched; no credential handling.
  Non-blocking observations: (1) evidentiary — its Bash `git` was denied, substituted mtime
  enumeration + independent SHA-256 (re-confirmed with native git below); (2) the pre-existing
  `setdefault` pin — **addressed this unit** by the reconcile-on-re-registration fix.
- **spec-auditor: FINDINGS → all addressed.** Invariants 1, 21/I-X3, §2.2, Buildout §4, §6/§10.4
  honesty, inv 30 all SATISFIED; no prohibited drift. **MINOR-1** (the `setdefault` pin made the
  documented "a narrowed config binds the supervised spawn" claim conditionally false on a
  long-lived governor) — **FIXED pre-commit** (reconcile the allowance on re-registration, no
  eviction; new test `test_governor_reregistration_narrowing_binds_no_eviction` proves it).
  **NIT-1** (cross-reference the two OP-6 bound constants) — **addressed** (comment linking
  `MAX_ALLOWANCE` and `_validate_terminals`).

## 6. Honesty / substitutions (§6, §10.4)

No live call is made in this unit — it is the concurrency governor. The single live `claude`
frontier smoke stays OWED (skip-with-record, pending the operator R8 §6 dated live-terms;
config already present under OP-6). The `n/2` status-bar rendering is deferred to `.statusbar`
(JS/Electron); this unit exposes only the data. Native git re-confirms what the validator's
denied-git could not: `config/live_operation.json` untracked (only `.example.json` tracked),
`docs/canonical/` clean, no JS in the change set.

## 7. Invariants exercised

inv 1 (operator holds final authority — allowance authorization-driven, never self-granted),
inv 21 / I-X3 (default 1; operator-ordered raise to ≤2; hard-capped; reversible),
inv 22-analogue (no mid-generation eviction on narrowing), inv 27 (observable — `status()`
yields `in_use`/`allowance`), inv 30 (minimal control — a constant inside the existing
governor, no new governance layer), §2.2 (zero credential handling), Buildout §4 (deterministic,
fail-closed permission logic).
