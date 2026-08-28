# Phase 15C — Evidence Report (PHASE GATE)

**Date:** 2026-07-19 · **Iteration:** 38 · **Status:** PASS_WITH_RESERVATIONS
**Gate:** `gate/phase-15c` (HIGH-STAKES — mandatory independent gate-validator)
**Work commit:** _(carried by the paired evidence/register commit — two-commit convention)_
**Sub-steps closed:** `.detect` (357df95) → `.adapter` (bbe3f7d) → `.gate` (this unit)

Phase 15C = the second live frontier provider under register **OP-6** (directive §11 track
15C; §12 OP-7 revised order 15A→**15C**→15B): the host **OpenAI Codex CLI**
(`openai_codex_cli`) wired live behind the SAME governed `ModelWorkerAdapter` contract as
`claude_code`, spawned only through a fail-closed supervised path. This `.gate` unit closes
the phase: it verifies the full chain end-to-end, performs the directive-named
**subscription-governor deep re-inspection** (now **two** live providers under allowance=2),
discharges the one remaining `.adapter` observation (NIT-2, roster fallback surfacing), and
re-confirms tag lineage / frozen canonical hashes / config tracking with native git.

## 1. Scope of this work unit (`.gate`)

The `.gate` step closes the high-stakes phase gate. Its **one code change** is the NIT-2
discharge (below); everything else is verification. No authorization was widened: the live
authorization and the subscription governor are **byte-unchanged since `gate/phase-15a`**.

## 2. What changed in `.gate` (working tree; base HEAD `600cbf1`)

| File | Change |
|---|---|
| `adapters/frontier/codex.py` *(M)* | **NIT-2 discharge.** New pure/deterministic `codex_roster_descriptor(role, requested_model)` — a roster/capability descriptor whose `model_ref` block `{requested, resolved_slug, verified, is_fallback, note}` SURFACES the per-node model resolution, so directive §11 15C ("unavailable ⇒ recorded fallback surfaced in the roster, never silent") is EXPLICIT, not assumed. `resolve_codex_model_ref` is the single source of the slug/note it carries; `None` request ⇒ `resolved_slug=None`/`is_fallback=True`; a requested slug is carried verbatim with `verified=False` (no fabricated CLI id). `capability_descriptors` is a `copy.deepcopy` of the module constants (immutability hygiene; spec-audit `.gate` NIT). |
| `node_runtime/supervisor/codex_spawn.py` *(M)* | `spawn_codex_terminal` now derives the `-m` slug SOLELY through `resolve_codex_model_ref(model)` (single source; the roster surface and the spawned slug cannot diverge). `LiveSmokeOutcome` gained `model_resolution: dict | None`; `attempt_codex_live_smoke` populates it via `codex_roster_descriptor` on EVERY return path — including skip-with-record and the auth-pause path — so which model (or CLI-default fallback) would have run is never silent. |
| `tests/unit/test_frontier_codex.py` *(M)* | +5 tests: descriptor surfaces the CLI-default fallback (`is_fallback=True`); descriptor carries a requested slug verbatim + unverified; unknown role refused; live-smoke outcome surfaces `model_resolution` even on skip-with-record (no leaked terminal); descriptor capability_descriptors are independent copies (no write-back to constants). |

## 3. Exit-criterion self-check (real command output)

**A. Full 15C chain end-to-end.**
- `.detect`: `adapters/frontier/codex.py` probe makes NO live model call (only `codex --version`
  / `codex login status` / `codex exec --help`); fail-closed on absent/timeout/unparseable/
  unauth; never reads `~/.codex/auth.json`; `adapters/detect.codex_available()` is a pure PATH
  check. `CODEX_ADAPTER == "openai_codex_cli"` == the frozen `schemas/node.schema.json` adapter
  enum member == a member of `live_authorization._AUTHORIZED_PROVIDERS`.
- `.adapter`: `CodexCliBackend` (real) + `MockCodexCliBackend` (spawns nothing) behind the
  shared `ModelWorkerAdapter`; spawn ONLY via `node_runtime/supervisor/codex_spawn.py` (5 ordered
  gates mirroring `frontier_spawn.py`). §2.2: `build_command` carries no credential/bypass flag;
  `build_env` scrubs the documented superset while preserving `CODEX_HOME`/`PATH`/`HOME`. T2:
  explicit `--sandbox` always emitted, `danger-full-access`/bypass refused structurally, coding
  role refused without an isolated worktree (`--cd`).

**B. Subscription-governor DEEP RE-INSPECTION — two live providers under allowance=2.**
`node_runtime/supervisor/subscription_governor.py`: `MAX_ALLOWANCE == 2` (hard cap);
`register_subscription(allowance=3|99)` RAISES (never raise on inference); a 3rd terminal per
subscription refused; succession = release-before-acquire (proven at allowance 1 AND 2);
unregistered acquire refused; narrowing 2→1 keeps existing holders (no mid-generation eviction)
while binding the next acquire. Both live spawn paths (`frontier_spawn` for `claude_code`,
`codex_spawn` for `openai_codex_cli`) read allowance from
`live_auth.terminals_per_subscription`, code-pinned to `[1, 2]` in
`live_authorization._validate_terminals` — never a hardcoded governor default. Native git:
`git diff --stat gate/phase-15a -- node_runtime/supervisor/subscription_governor.py
control_plane/profiles/live_authorization.py` is **EMPTY** (byte-unchanged; 15C widens nothing).

**C. NIT-2 discharged.** See §2. `codex_roster_descriptor` + `LiveSmokeOutcome.model_resolution`
make the recorded fallback a first-class field of the roster/outcome surface.

**D. Live smoke — skip-with-record (honest).** The single live `codex exec` smoke is NOT run
this non-interactive session, for two independent each-sufficient reasons (directive §10.4):
(1) R8 §6 `[OPERATOR]` live-terms are unmet; (2) the deterministic suite uses a
tmp_path/DENIED-by-absence config, never the repo one — the loop makes no live call and does
not depend on the operator's on-disk `config/live_operation.json`. The mock-first proof
exercises the full governed MCP → local-gate → CANDIDATE path (reasoning + coding roles). **No
live-capability claim is made** — a live-capability claim requires a real `codex exec` call.

**E. Native-git re-confirm.** Tags: `gate/phase-14a,14b,14c,14e,15a` present; `14d` correctly
UNTAGGED (skipped-with-record); `15c` NOT yet tagged (this step tags it). Frozen canonical
hashes intact (`sha256sum docs/canonical/…`): Buildout Directive `cc414372`, Architecture Plan
v1.0.1 `8c9b7240`, Architecture Plan v1.0 `668089b5`, Canonical Handoff `6d3fd03b`.
`git ls-files config/` shows ONLY `config/live_operation.example.json`;
`config/live_operation.json` is gitignored (`.gitignore:19`) and untracked.

**F. Tests.** `py -3.12 -m pytest tests/ -q` → **533 passed, 0 skipped** (was 528 at `.adapter`;
+5 NIT-2 gate tests). Codex integration/live subset
`tests/integration/test_codex_adapter.py tests/integration/test_codex_detect_live.py` →
**10 passed, 0 skipped** (the live `.detect` probes RAN — codex really installed on host). JS
suites untouched: **149 passed, 0 skipped**.

## 4. Independent confirmation

- **gate-validator (mandatory, high-stakes): PASS_WITH_RESERVATIONS.** All 7 criteria verified
  by re-execution in an isolated context (full pytest 533/0; codex subset 10/0; all 4 canonical
  hashes; native `git diff --stat gate/phase-15a` empty; governor refutation probes; credential
  scrub leaked 0/14 keys; coding-without-worktree and `danger-full-access` refused; no live
  subprocess reachable from the default suite; no fabricated model id). Reservations are
  procedural, all owned: (R1) validation was against the uncommitted tree — the `gate/phase-15c`
  commit MUST contain exactly the three `.gate` files and nothing under
  `subscription_governor.py`/`live_authorization.py`/`schemas/` (satisfied — see §5); (R2) the
  validator accidentally regenerated `docs/PHASE0_FREEZE_MANIFEST.json` and restored it
  byte-identical with `git checkout --` (tree clean); (R3) untracked `apps/desktop/package-lock.json`
  present since session start — benign npm lockfile, not a gate blocker, left untracked.
- **spec-auditor (substantive new code): CLEAN.** No invariant violation, no prohibited drift.
  Invariants 3/4 (selection by capability descriptor, never by name — `model_ref` is transparency
  metadata, not the discriminator), 10/11 (descriptor is read-only, `verified` hard-pinned False,
  CANDIDATE still flows only through the governed adapter), §2.2 (no credential touched),
  model-id honesty, fail-closed, determinism — all PASS. 3 NITs: the immutability-hygiene NIT
  (shallow copy) was FIXED this unit (`copy.deepcopy` + regression test); a post-smoke
  `verified=True` update is a legitimate future enhancement (the under-claim direction is the
  fail-safe one, not required by NIT-2); a `dict` vs `dict[str, Any]` typing nit — cosmetic.

## 5. Substitutions & honesty ledger (directive §6)

- **Live `codex exec` smoke — SUBSTITUTED by mock-first + skip-with-record** (directive §10.4).
  The governed path is proven end-to-end with `MockCodexCliBackend`; the real backend's
  `generate()` is never called in the default suite. Owed: one operator-authorized live smoke
  (R8 §6 live-terms + present on-disk config) before any live-capability claim.
- **U32 (recorded, UNRESOLVED, owed to a live run):** residual host `~/.codex/config.toml`
  keys the CLI flags do not override (declared MCP servers/hooks) — an egress review item for the
  live run. `CODEX_HOME` is deliberately NOT relocated (relocating it + copying `auth.json` would
  BE credential handling, §2.2). Preserved `HTTP(S)_PROXY`/CA vars are host-trust, out of the
  adapter's remit (inherited from the `gate/phase-14b` template).
- **U5 (concurrency verified-at-1):** the OP-6 raise to 2 is operator-ordered, governor-capped,
  reversible; no vendor-published per-account concurrency allowance was found to independently
  verify a value >1 (the cap is the operator ruling, not an inference).

## 6. Owed / open items

- `[OPERATOR]` R8 §6 dated live-terms for `openai_codex_cli` + one operator-authorized live
  `codex exec` smoke — before any live-capability claim for Codex.
- Track 15B next (OP-7 order 15A→15C→**15B**): Anthropic adapter multi-model + conductor-capable.
- Open backlog carried forward: U5, U29 (env-scrub keys on `API_KEY`/`APIKEY` not bare `_KEY`
  suffix — CLI reads only prefix-scrubbed vars, non-blocking), U32.

## 7. Verdict

**PASS_WITH_RESERVATIONS.** Phase 15C is COMPLETE: `.detect` + `.adapter` + `.gate` landed, the
full chain verified end-to-end, the subscription-governor deep re-inspection confirms allowance
stays ≤2 across both live providers with no raise-on-inference and release-before-acquire on
succession, NIT-2 discharged, canonical set + tag lineage + config tracking re-confirmed with
native git. Tag `gate/phase-15c`. Next: `phase-15b`.
