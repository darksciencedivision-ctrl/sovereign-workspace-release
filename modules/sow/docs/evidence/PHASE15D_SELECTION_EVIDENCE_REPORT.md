# Phase 15D · sub-step `.selection` — Evidence Report

**Date:** 2026-07-19 · **Loop iteration:** 42 · **Base HEAD:** `8fed664`
**Directive basis:** AUTONOMOUS_BUILD_DIRECTIVE.md §11 track 15D (register **OP-6**), §12 OP-7 order
15A→15C→15B→15D · **Status:** sub-step PASSED — `gate/phase-15d` remains **UNTAGGED**

---

## 1. Scope of this work unit

Phase 15D is large, so it is decomposed (directive §3.2). Declared sub-step order:

`.selection` (this unit) → `.flow` (conductor decomposes → Scheduler assigns by capability → workers
publish CANDIDATE over MCP → gates → conductor **synthesizes** an acceptance packet) → `.debate`
(one bounded live debate, budgets enforced) → `.succession` (kill the conductor mid-run, resume on a
different backend, zero loss, restore selection) → `.gate` (HIGH-STAKES close, mandatory
gate-validator). **No per-sub-step gate tag**; `gate/phase-15d` closes only when all sub-steps land.

This unit delivers the one 15D requirement everything else records against:

> `current_conductor` = `{model: fable-5, reason: operator_selected, since: 2026-07-19}`
> (selection preserved even when the executing checkpoint differs — **record both**)

Concretely: a deterministic, schema-pinned conductor-selection record, kept strictly separate from
the checkpoint the live CLI reports, surfaced on **every** governed-spawn outcome.

## 2. What changed (working tree; base HEAD `8fed664`)

| File | Change |
|---|---|
| `control_plane/conductor/__init__.py` | NEW package |
| `control_plane/conductor/selection.py` | NEW — the single source of the selection record + binding |
| `control_plane/recovery/succession.py` | successor record now built through the validated constructor; duplicate key-set copy removed |
| `node_runtime/supervisor/conductor_spawn.py` | `selection=` param; requests the selection's model by default; `conductor_selection` surfaced on all 4 outcome paths |
| `adapters/conductor/adapter.py` | NEW read-only `reported_model` property (fail-closed) |
| `adapters/frontier/claude_code.py` | NEW read-only `reported_model` property on `ClaudeCodeConductorBackend` (delegating, fail-closed) |
| `tests/unit/test_conductor_selection.py` | NEW — 31 tests |
| `tests/integration/test_live_conductor_selection.py` | NEW — 10 tests through the REAL entrypoint + REAL MCP |

**Three facts, recorded separately, none inferred from the others:**

```
SELECTION  = what the operator chose      fable-5 (an interface label, invariant 3)
REQUESTED  = what was asked of the CLI    the --model slug, or none ⇒ backend default
EXECUTING  = what actually ran            None until a LIVE reply reports a checkpoint id
```

## 3. Exit-criterion self-check (real command output)

| # | Criterion | Evidence |
|---|---|---|
| 1 | Pinned record is fable-5 / operator_selected / since 2026-07-19 | `OPERATOR_SELECTED_CONDUCTOR` (`selection.py`); validated by validator's own probe against the frozen `checkpoint@1.0` `current_conductor` definition with a format checker: `errors: []`, extra key rejected |
| 2 | Reason enum + key set derived from the FROZEN schema, not restated | validator confirmed `offline_mode` appears **nowhere** in the module source yet `CONDUCTOR_SELECTION_REASONS == ('operator_selected','offline_mode','succession')` |
| 3 | Selection / requested / executing recorded separately on EVERY path | all 4 `ConductorSmokeOutcome` return sites carry `conductor_selection`; record built **before** the spawn so pre-backend refusals still name the selection |
| 4 | `executing.model` is None where nothing executed | validator matrix: skip-with-record, denied-auth, unavailable-fallback and mock paths all `verified=False exec=None` |
| 5 | A requested slug can never be recorded as verified | validator refutation FAILED: `reported_model ∈ {None,"","   ",True,0,dict,list}` → all `verified=False`; a lying resolver populated only `resolved_slug`; only `extract_reported_model(parsed CLI JSON)` can set it |
| 6 | Unavailable model ⇒ RECORDED fallback, never silent | `model_available=False` ⇒ `resolved_slug=None`, `is_fallback=True`, note contains "fallback"; no slug invented |
| 7 | Succession contract (invariant 28) not weakened | validator round-tripped a real `MCPServer` + `SuccessionManager`: `integrity_ok: True`, successor validates, `node_id` does not leak into the checkpoint conductor; `test_conductor_succession.py` 12/12 incl. zero-loss + tamper-detect |
| 8 | No live call, no credential handling (§2.2) | module has no `subprocess`/`socket`/`urllib`/`os.environ`; its only I/O is reading the frozen schema. Validator's instrumented subprocess recorder over the new tests: `SUBPROCESS_CALLS: []` |
| 9 | Loop did not write `config/live_operation.json` | untracked/gitignored; mtime `09:38:36` vs this unit's files `15:33–15:49` |
| 10 | Scope + frozen canonical intact | exactly the 8 declared files; `docs/canonical/` clean; `compute_manifest.py --check` → `freeze check OK: no drift` |

### Commands

```
py -3.12 -m pytest tests/unit/test_conductor_selection.py tests/integration/test_live_conductor_selection.py -q
# 41 passed

py -3.12 -m pytest tests/ -q
# 610 passed, 41 warnings   (baseline 569 at gate/phase-15b; +41)
```

JS untouched this unit (149 product JS unchanged).

## 4. Substitutions (directive §6) & honesty notes

1. **No live `claude` call.** The governing gate is the R8 §6 `[OPERATOR]` live-terms confirmation,
   which the loop cannot self-discharge (§10.4). Mock-first proves the full governed path
   (12 conductor files loaded in order → CANDIDATE decision published → governor released).
   **No live-capability claim is made for the selection binding.**
2. **`label_mismatch` is a surfaced pair, not an adjudication.** The selection is an operator LABEL
   (`fable-5`); a live CLI reports a full checkpoint id (`claude-fable-5-<date>`). No
   label→checkpoint mapping exists yet, so on a real live run this flag will read `true`. The first
   live smoke supplies that mapping — **owed item**, recorded here rather than faked by a guess.
3. **`model_available` is an unwired probe hook.** Neither live CLI has an offline model-list, so in
   production the value stays `None` and an unusable slug surfaces as a live-call failure
   (skip-with-record). The fallback branch is exercised by tests, not by a production probe.
4. **Two dates for one selection.** `2026-07-16` (freeze manifest, `conductor/IDENTITY.md`, the
   schema `$comment`) is when the operator first selected fable-5; `2026-07-19` is when that
   selection became the LIVE conductor under OP-6 and is what §11 15D pins for this record. Same
   selection, two events — noted in code so the pair does not read as drift.

## 5. Invariants exercised

- **1 (operator holds final authority)** — the module labels and records; it spawns nothing,
  authorizes nothing, and selects nothing on the operator's behalf.
- **3 (conductor is an interface + runtime selection, never a vendor default)** — binding never
  rewrites the selection; the executing checkpoint is recorded beside it, never over it.
- **4 / 20 (interchangeability, air-gap honesty)** — the control-plane module imports **no adapter**;
  slug resolution is provider-neutral with an injectable `resolver=` (proven by a codex-shaped
  resolver test), so a successor on another backend binds through the same path.
- **11 (provenance)** — `directive_version` is carried or absent, never inferred onto a record.
- **16 / 10 (gates, CANDIDATE-only)** — the conductor still proposes; nothing here promotes.
- **28 (succession works)** — successor records now flow through one validated constructor;
  a malformed successor selection is refused **before** any MCP write.
- **Buildout §4 (deterministic, fail closed)** — no clock is read (all timestamps injected); blank
  model, unknown reason, date-only timestamp, non-mapping record, unknown key all RAISE.

## 6. Verdicts

**gate-validator (sub-step, isolated context, re-run on the FINAL tree): PASS_WITH_RESERVATIONS.**
All 7 criteria re-executed independently (610/610 pytest reproduced; refutation of the
verified-checkpoint path failed; succession round-trip + 12/12 succession tests; frozen hashes and
manifest check). Reservations, all owned and non-blocking:

- **R1** `succession.py` missing-`model` raised a bare `KeyError` → **FIXED this unit** (now
  `ConductorSelectionError`, regression-pinned).
- **R2** `__post_init__` does not type-check `adapter`/`subscription_ref`/`directive_version`; caught
  one step later by `jsonschema.validate` at the publish boundary, so no bad checkpoint can be
  published. Pre-existing behavior, unchanged by this diff. **OPEN, carried to `.gate`.**
- **R3** the `backend=` injection seam is mock-only by documentation, not gated: an injected backend
  defining `reported_model` yields `verified=True` without a live call. Production constructs a real
  `ClaudeCliBackend` and the default mock lacks the attribute. **OPEN, carried to `.gate`.**
- **R4** benign untracked `apps/desktop/package-lock.json`, pre-existing at session start, not
  swept into this commit.

**spec-auditor: 2 MAJOR + 7 MINOR + 4 NIT on the first pass → re-audit confirms both MAJOR and all
MINOR/NIT DISCHARGED**, plus 4 MINOR / 4 NIT raised on the fixed tree, of which the two the auditor
named as worth closing now were fixed:

- **MAJOR-1 (FIXED)** the vendor adapter was welded into the generic selection layer → module now
  imports no adapter; injectable resolver; the recorded provider string pinned structurally by test.
- **MAJOR-2 (FIXED)** `executing.model` echoed the requested slug where nothing executed → it is now
  `None` unless a live reply reported a checkpoint id; the would-be-argv slug moved to `resolved_slug`.
- **F2 (FIXED)** a caller-supplied `reason`/`since` was silently discarded by `reconstruct` — which
  would let an explicit operator re-selection be recorded as a system recovery. Now refused.
- **F3 (FIXED)** the fail-closed comment claimed more than the code did on a missing `model`. Now
  refused with the module's own error type.
- **F1 (OPEN, carried to `.gate`)** the published CANDIDATE decision still writes the selection label
  into its `model` field when nothing executed (`model_verified:false` and `model_selection` sit
  beside it, so it is not silent), and `ConductorAdapter` provenance sets `model` unconditionally
  with no verified flag. Pre-existing to 15D; it is the same shape MAJOR-2 named, now the only place
  it survives. Not expanded into this unit's scope — recorded, not silently skipped.
- **F4 (OPEN, carried to `.gate`)** a restored selection is stamped `operator_selected` with no
  operator act in the loop; the frozen enum has no `restored` value, so this needs a register
  decision rather than a code change. Also: `succession.py` uses `_now_iso()` for the successor's
  `since`, ignoring an injected `reconstruct(now=...)`.
- **F5–F8 (3 FIXED, 1 recorded)** rename residue cleared; chained-succession coverage added
  (`test_chained_succession_reserializes_a_reconstructed_record`); the compact-datetime form
  (`20260719T120000`) is still accepted — the code comment claims only bare-date rejection, so no
  overclaim stands, but the residue is recorded here.

**Test totals:** **610/610 pytest** (`py -3.12`; baseline 569 at `gate/phase-15b`, +41), 149 product
JS unchanged. **No live call. No credential handling. `gate/phase-15d` UNTAGGED.**
