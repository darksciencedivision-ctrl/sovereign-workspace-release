# Phase 15A · sub-step `.liveauth` — Evidence Report

**Date:** 2026-07-19 · **Iteration:** 31 · **Status:** PASS (sub-step; NOT the phase gate)
**Work commit:** `1fb8b30` (this evidence/register commit carries the work hash — two-commit convention)
**Phase gate:** `gate/phase-15a` remains **UNTAGGED** — the high-stakes 15A gate closes at
`.gate` with the mandatory independent gate-validator once all 15A sub-steps land.

## 1. Scope of this work unit

Directive §11 (register **OP-6**) authorizes live multi-model orchestration. Track 15A
("Live activation + concurrency governor") is large and high-stakes; per directive §3.2 it
is decomposed into sub-steps. This unit is the **first** sub-step, `.liveauth`, delivering
the authorization foundation the rest of 15A/15B/15C/15D build on:

1. **Rewrite `control_plane/profiles/live_authorization.py`** from the OP-4 single-provider
   scope `{provider: claude_code, terminals: 1}` to the OP-6 two-provider scope
   `{providers: [claude_code, openai_codex_cli], terminals_per_subscription: 2}`, citing
   register row **OP-6**.
2. **Create the real `config/live_operation.json`** — OP-6 §11(c) explicitly authorizes the
   loop to create/maintain it (it is the authorization the 14B restraint was waiting for).
   The file stays **gitignored**: a fresh clone is still DENIED-by-absence.
3. **Update the example template** `config/live_operation.example.json` to the 1.1 shape.
4. **Fail-closed paths re-tested**: absence ⇒ DENIED (unchanged); malformed / out-of-scope /
   scope-widening ⇒ RAISE.

**Deferred to later 15A sub-steps** (recorded, not done here): subscription-governor
per-subscription allowance=2 wiring + deep re-inspection (`.governor`); dated R8 records for
both providers (`.r8`); the `n/2` count in the shell status bar (`.statusbar`, JS/Electron —
D-P14-1 constraint applies); the phase-gate close (`.gate`).

## 2. What changed (working tree; base HEAD `69da6d0`)

| File | Change |
|---|---|
| `control_plane/profiles/live_authorization.py` | REWRITTEN to the OP-6 two-provider scope (details §3). |
| `config/live_operation.example.json` | Template updated to `config_version 1.1`, two-provider scope, cites OP-6. |
| `config/live_operation.json` | **CREATED** (gitignored, NOT committed) — the real live-operation authorization switch under OP-6. |
| `tests/unit/test_live_authorization.py` | Rewritten: two-provider fail-closed coverage (27 tests). |
| `tests/integration/test_claude_code_adapter.py` | `_VALID_AUTH` → 1.1; two DENIED-path tests reworked to an explicitly-absent path (repo default is now authorized under OP-6). |
| `tests/unit/test_frontier_claude_code.py` | Inline config → 1.1 two-provider shape. |
| `tools/assembled/roster_report.py` | Frontier reason/comment updated: gate reads SATISFIED when the loop-created config is present; cites OP-6 (was OP-4/OP-5 "config intentionally unwritten"). Frontier backend stays MOCK, live still OWED. Conductor reason updated (spec-auditor MINOR-2): "two OP-6 live worker providers" (was "one"). |
| `tests/integration/test_assembled_roster.py` | `test_frontier_gate_state_matches_real_authorization` made robust to both gate states. |
| `control_plane/profiles/loader.py` | Citation staleness fixed (spec-auditor MINOR-1): the live-authorization docstring + `ProfileViolation` message now cite OP-6 (superseding OP-4/OP-5). Behavior unchanged. |

## 3. Authorization design (fail-closed, deterministic — Buildout §4)

Scope is **pinned in code**, not in the config, so a present config can only *match or
narrow*, never widen authority beyond the operator ruling:

- `_AUTHORIZING_REGISTER_ROW = "OP-6"` — a config citing any other row RAISES.
- `_AUTHORIZED_PROVIDERS = frozenset({"claude_code", "openai_codex_cli"})` — the canonical
  ids are the frozen `node.schema.json` `adapter` enum values (schemas/ is the single source
  of truth). A provider outside this set RAISES (a third provider needs a NEW operator
  authorization, never a wider config).
- `_PROVIDER_ALIASES = {"codex": "openai_codex_cli"}` — the operator/directive shorthand
  "codex" normalizes deterministically to the schema id, so `assert_provider_live(cap.adapter)`
  (called by the profile loader and supervised spawn path with the schema enum value) works
  directly; the resolved `providers` frozenset stores canonical ids only.
- `_MAX_TERMINALS_PER_SUBSCRIPTION = 2` (OP-6; was 1 under OP-4/I-X3) — a config may narrow
  to 1; `terminals_per_subscription > 2` or `< 1` RAISES; `True` cannot masquerade as `1`
  (isinstance-bool guard).
- `config_version` bumped `"1.0" → "1.1"` (scope shape changed); a stale 1.0 config RAISES.
- Absence ⇒ `LiveAuthorization.denied(...)` (`authorized=False`, empty `providers`).

`§2.2` holds in full: this module handles **no credential** — it reads a JSON authorization
flag. No live call is made in this sub-step; the frontier/worker backends stay mock/owed.

## 4. Self-check — exit criteria with real command output

- Targeted suites: `py -3.12 -m pytest tests/unit/test_live_authorization.py
  tests/integration/test_claude_code_adapter.py tests/unit/test_frontier_claude_code.py -q`
  → **41 passed**.
- Full suite: `py -3.12 -m pytest tests/ -q` → **478 passed, 0 failed** (was 471 at
  gate/phase-14e; +7 net from the rewritten `.liveauth` coverage). JS untouched (no JS files
  changed this unit; product JS stays 131).
- `git status` shows the 7 changed tracked files above; **`config/live_operation.json` is
  absent from status (gitignored)**; `docs/canonical/` is clean.

## 5. Honesty / substitution notes (§6 / §10.4)

- **No live call, no capability claim.** `.liveauth` establishes the authorization gate only.
  Wiring a live worker backend, the governor allowance=2, the status bar, dated R8 records,
  and any live smoke are later 15A/15B/15C/15D sub-steps.
- The real `config/live_operation.json` exists **on this host only** (gitignored). A fresh
  clone / CI runs DENIED-by-absence — the tests are decoupled from the on-disk file (they use
  explicit temp/absent paths), so the suite is green in both states.
- The `codex` → `openai_codex_cli` mapping is recorded here and in the config comments: the
  operator's shorthand and the frozen schema id are the same provider.

## 6. Independent verification

- **spec-auditor:** **CLEAN on all load-bearing invariants** (inv 1 — loop-created config is
  not self-authorization because scope is code-pinned and can only narrow; §2.2 — zero
  credential handling; inv 21/I-X3 — hard cap at 2, bool-guarded; Buildout §4 — every
  malformed/out-of-scope path raises, absence denies; schemas frozen — provider ids match the
  frozen enum, `codex` alias never becomes a distinct identity; §6/§10.4 — no live claim). No
  MAJOR. Two MINOR staleness findings — **both FIXED pre-commit + re-tested**: MINOR-1
  (`loader.py` OP-4 citation → OP-6), MINOR-2 (`roster_report.py` conductor reason "one
  provider" → "two OP-6 providers").
- **gate-validator (sub-step confirmation):** **PASS**. Every criterion re-executed in an
  isolated context; fail-closed refutation attempts (widen providers/terminals, forge
  register row/version, alias abuse, unknown future frontier) **all closed — no bypass found**.
  Full suite `478 passed, 0 failures, 0 skips`; targeted subset `53 passed`; provider ids
  match `schemas/node.schema.json:12`; module handles no credential/subprocess; real config
  gitignored (triangulated via `.gitignore:19`, `git status`, `git ls-files`);
  `docs/canonical/` untouched. Note: this confirms the SUB-STEP only — the mandatory
  high-stakes `gate-validator` runs at `.gate` to close `gate/phase-15a`.

_Final full-suite re-run after the two MINOR fixes: `478 passed` (the fixes are
comment/message-string only, non-behavioral)._

## 7. Register / decisions

Sub-step `phase-15a.liveauth` PASSED — recorded in `docs/registers/DECISION_REGISTER.md`.
`gate/phase-15a` UNTAGGED (awaits `.governor` / `.r8` / `.statusbar` / `.gate`).
