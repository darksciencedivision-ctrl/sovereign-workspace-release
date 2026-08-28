# Phase 15B — Evidence Report (PHASE GATE)

**Date:** 2026-07-19 · **Iteration:** 41 · **Status:** PASS
**Gate:** `gate/phase-15b` (HIGH-STAKES — mandatory independent gate-validator)
**Work commit:** `3d75b3c` (this evidence/register commit carries the work hash — two-commit convention)
**Sub-steps closed:** `.modelsel` (9b6b11e) → `.conductor` (590b753) → `.gate` (this unit)

Phase 15B = the live **Anthropic** provider (`claude_code`, register **OP-6**, directive
§11 track 15B; §12 OP-7 revised order 15A→15C→**15B**) extended with **per-node model
selection** and made **conductor-capable** so the Phase-4 `ConductorAdapter` can bind the
live backend as its runtime selection (invariant 3, current selection Fable 5). This
`.gate` unit closes the phase: it verifies the full chain end-to-end, discharges the one
remaining `.conductor` spec-audit owed item (executing-model reconciliation), performs the
directive-named **subscription-governor deep re-inspection** (now **two** live providers
under allowance=2), and re-confirms tag lineage / frozen canonical hashes / config tracking
with native git.

## 1. Scope of this work unit (`.gate`)

The `.gate` step closes the high-stakes phase gate. Its **one code change** is the
executing-model reconciliation (the `.conductor` spec-audit owed item); everything else is
verification. **No authorization was widened:** `live_authorization.py` and
`subscription_governor.py` are byte-unchanged since `gate/phase-15a` (native-git verified,
§3-E). No live `claude` call is made this session.

## 2. What changed in `.gate` (working tree; base HEAD `119e8ea`)

| File | Change |
|---|---|
| `adapters/frontier/claude_code.py` *(M)* | **Executing-model reconciliation** (owed `.conductor` NIT). New pure/deterministic `extract_reported_model(payload)` reads the model the `claude -p --output-format json` response says it actually ran — a top-level string `model`, or a single-key `modelUsage` map — and returns **`None`** when absent / blank / wrong-type / ambiguous (multi-key). A checkpoint id is **never fabricated**. `ClaudeCliBackend` gains `self.reported_model` (set from the parsed JSON on the success path only). `ClaudeCodeConductorBackend.propose_plan` now **reconciles**: it records `model` = the CLI-reported checkpoint with `model_verified=True` **only** when the wrapped backend actually reported one; otherwise it keeps the **selection label** with `model_verified=False`. A new `model_selection` field always carries the selection/requested label so a CANDIDATE decision distinguishes "what ran" from "what was selected." |
| `tests/integration/test_claude_code_conductor.py` *(M)* | +10 tests: 8 parametrized `extract_reported_model` cases (top-level `model`, trimmed, single-key `modelUsage`, absent⇒None, blank⇒None, wrong-type⇒None, ambiguous⇒None, non-dict⇒None); reconciliation records the reported checkpoint as `verified=True` with the selection preserved; stays `verified=False` (selection label) when the CLI reported nothing — never fabricated. |

## 3. Exit-criterion self-check (real command output)

**A. Full 15B chain end-to-end.**
- `.modelsel`: per-node `--model <slug>` selection on `MockClaudeCliBackend`/`ClaudeCliBackend`
  (`CLAUDE_CODE_MODEL_FLAG="--model"`, emitted only when requested; omitted ⇒ CLI default).
  `resolve_claude_model_ref` carries a requested slug verbatim + unverified, `None` ⇒ recorded
  CLI-default fallback; `claude_code_roster_descriptor` surfaces a `model_ref` block
  `{requested, resolved_slug, verified=False, is_fallback, note}` + the candidate mapping — the
  fallback is a first-class roster field, never silent (directive §11 15B). `_assert_no_forbidden`
  refuses `--dangerously-skip-permissions`/`--api-key`/`--with-api-key`/`--with-access-token`.
- `.conductor`: `ConductorBackend` `@runtime_checkable` protocol `{model_name, calls, propose_plan}`
  makes "conductor-capable" a checkable claim (the Phase-4 `MockReasoningBackend` and the new
  `ClaudeCodeConductorBackend` both satisfy it). `ClaudeCodeConductorBackend` bridges the worker
  `generate` shape to `propose_plan`, parsing fail-closed (`_parse_decomposition`: non-JSON/empty/
  malformed ⇒ `([], "unstructured")`, never a fabricated decomposition). The single governed
  live-conductor spawn `node_runtime/supervisor/conductor_spawn.py` runs 5 ordered gates
  (`assert_startup` on the `claude_code` provider cap → `assert_provider_live` re-asserted → R8 §6
  operator terms → CLI presence → governor `register_subscription(allowance=live_auth.terminals_
  per_subscription)`); the `ConductorAdapter` acquires/releases at `start()`/`close()` (no
  double-count); `spawned_by_supervisor=True` so a naked session (invariant 2) is refused.

**B. Executing-model reconciliation (the `.gate` code change) — honest & fail-closed.**
`extract_reported_model` returns the CLI-reported id only when the JSON actually carries a
non-blank string; every other case (absent, blank, wrong type, ambiguous multi-key `modelUsage`,
non-dict) ⇒ `None`. `propose_plan` records `model_verified=True` **only** when a real reported
checkpoint exists; the mock/deterministic path (no `reported_model`) keeps the selection label
and `model_verified=False`. A requested `--model` slug can therefore **never** be recorded as a
verified checkpoint. The existing mock-first assertion
`body["model"] == "claude_code:conductor:fable-5"` still holds (that path reports no checkpoint).

**C. Subscription-governor DEEP RE-INSPECTION — two live providers under allowance=2.**
`node_runtime/supervisor/subscription_governor.py`: `MAX_ALLOWANCE == 2` (hard cap, line 29);
`register_subscription(allowance>2)` **raises** `ValueError` (line 51–57 — never raise on
inference); a 3rd terminal per subscription refused (`acquire` raises `SubscriptionLimitExceeded`
at `len(active) >= allowance`); succession = release-before-acquire; a mid-session NARROWING
2→1 keeps held terminals and refuses only FUTURE acquires (no mid-generation eviction, lines
64–70). Both live spawn paths (`frontier_spawn` for `claude_code`, `codex_spawn` for
`openai_codex_cli`) read allowance from `live_auth.terminals_per_subscription` (code-pinned
`[1, 2]` in `live_authorization`), never a hardcoded governor default. Native git:
`git diff --stat gate/phase-15a -- node_runtime/supervisor/subscription_governor.py
control_plane/profiles/live_authorization.py` is **EMPTY** (byte-unchanged; 15B widens nothing).

**D. Live smoke — skip-with-record (honest).** The single live `claude` smoke (per-model worker
+ conductor) is NOT run this non-interactive session. The governing gate is the R8 §6
`[OPERATOR]` live-terms confirmation (`operator_terms_confirmed`), which the loop cannot self-
discharge; unmet ⇒ skip-with-record (directive §10.4). The mock-first proof exercises the full
governed MCP → local-gate → CANDIDATE path (12 conductor files loaded in declared order, a
CANDIDATE decision published, governor acquired then released). **No live-capability claim is
made** — a live-capability claim requires a real live `claude` call. `config/live_operation.json`
is present on disk (created at 15A under OP-6 §11(c), citing OP-6, scope-pinned; gitignored,
never committed) and was **NOT** created or modified by this `.gate` unit.

**E. Native-git re-confirm.** Tags: `gate/phase-14a,14b,14c,14e,15a,15c` present; `14d` correctly
UNTAGGED (skipped-with-record); `15b` NOT yet tagged (this step tags it). Frozen canonical hash
prefixes intact (`sha256sum docs/canonical/…`): Buildout Directive `cc414372`, Architecture Plan
v1.0.1 `8c9b7240`, Architecture Plan v1.0 `668089b5`, Canonical Handoff `6d3fd03b`.
`git ls-files config/` shows ONLY `config/live_operation.example.json`;
`config/live_operation.json` is gitignored (`.gitignore:19`) and untracked.

**F. Tests.** `py -3.12 -m pytest tests/ -q` → **569 passed, 0 skipped** (was 559 at
`gate/phase-15c`; +10 `.gate` reconciliation tests). Conductor integration subset
`tests/integration/test_claude_code_conductor.py` → **28 passed** (was 18; +10). JS suites
untouched: `node --test` → **183 passed, 0 failed**.

## 4. Independent confirmation

- **gate-validator (mandatory, high-stakes): PASS.** All seven criteria independently
  re-executed in an isolated context: full pytest **569 passed** (exit 0); JS `node --test`
  114 (terminal) + 35 (apps/desktop) = 149 pass / 0 fail; the conductor file 28 passed. The
  adversarial refutation — "could a requested slug ever be recorded as a verified checkpoint?"
  — **failed to refute**: the only writer of `reported_model` is `ClaudeCliBackend.generate`
  from `json.loads(proc.stdout)` (the CLI response); the requested slug flows only into
  `build_command`'s `--model` argv and never into `extract_reported_model`, so a requested slug
  can appear as `model` ONLY with `model_verified=False`. §2.2 intact (only `os.environ` read is
  `build_env`, which pops every credential/endpoint key; `_assert_no_forbidden` refuses the
  bypass/credential flags before the prompt is appended). No live `claude` subprocess reachable
  from the default suite; live smoke skip-with-record; `config/live_operation.json` gitignored,
  not created/modified by this unit. Governor deep re-inspection: `MAX_ALLOWANCE=2`, `register`
  raises on allowance>2 (no raise-on-inference), narrows without mid-generation eviction, 3rd
  terminal refused; `git diff --stat gate/phase-15a` of governor + live_authorization EMPTY. Tag
  lineage + four frozen canonical hashes intact; `docs/canonical/` unmodified. Conductor adds no
  authority, refuses a naked session, publishes CANDIDATE-only. **Reservations (all owned,
  non-blocking):** (R1) the `.gate` change is uncommitted at validation time — the gate commit +
  tag follow this PASS (this report's two-commit); (R2) the untracked
  `apps/desktop/package-lock.json` must NOT be swept into the gate commit (it is not — scope is
  the two intended files + this report); (R3) no real live `claude` call this session (R8 §6
  operator terms undischarged) — required honest behavior (§10.4), no live-capability claimed.
- **spec-auditor (substantive new code): CLEAN.** No load-bearing invariant violated. Invariant 3
  preserved (the decision records what the CLI reports as `model`, carrying the selection
  separately in `model_selection`, so a silent CLI model substitution surfaces as
  `model != model_selection` rather than being masked — no overclaim); §4 fail-closed
  (non-dict/blank/wrong-type/ambiguous ⇒ None, checkpoint never fabricated; a success overwrites
  `reported_model` every call so no stale value leaks; on a `generate` exception the value is not
  read); §2.2 untouched (only the CLI's own `model`/`modelUsage` id is read, never a credential);
  invariants 10/11/16 intact (CANDIDATE-only publish). One optional NIT: once the live smoke
  confirms the canonical CLI JSON field, the single-key `modelUsage` shape-heuristic could be
  tightened to that one confirmed location — a post-live-smoke enhancement, not a defect (the
  heuristic already fails closed on the multi-key case).

## 5. Substitutions & honesty ledger (directive §6)

- **Live `claude` smoke (worker + conductor) — SUBSTITUTED by mock-first + skip-with-record**
  (directive §10.4). The governed path is proven end-to-end with mock/JSON backends; the real
  `ClaudeCliBackend`/`ClaudeCodeConductorBackend` live subprocess is never reached in the default
  suite. Owed: one operator-authorized live smoke (R8 §6 live-terms discharged on the host) before
  any live-capability claim for Anthropic, per available model ref (`opus-4.8`, `fable-5`, CLI
  default), sequential, minimal tokens.
- **Accepted `--model` slug verification — DEFERRED to the live smoke.** The `claude` CLI has no
  offline model-list; `opus-4.8` / `fable-5` stay `verified=False` in the roster until a live
  `claude -p --model <slug>` smoke confirms the CLI accepts them (unavailable ⇒ recorded fallback,
  never silent). No slug is fabricated.
- **Executing-model reconciliation exercised via a reporting stand-in.** The reconciliation is
  proven with a `_ReportingBackend` that mimics `ClaudeCliBackend.generate` setting
  `reported_model`; the real subprocess path is confirmed on the live smoke. The exact CLI JSON
  field carrying the model id is confirmed at that live smoke — `extract_reported_model` is
  fail-closed for every shape it does not recognize.

## 6. Owed / open items

- `[OPERATOR]` R8 §6 dated live-terms for `claude_code` + one operator-authorized live `claude`
  smoke (worker + conductor, per available model) — before any live-capability claim for Anthropic.
- Reconcile the exact `claude -p --output-format json` model field on the first live smoke
  (`extract_reported_model` already handles the two documented shapes fail-closed).
- Next: `phase-15d` (OP-7 order 15A→15C→15B→**15D**): live conductor (Fable-5 selection) +
  inter-model flow + live conductor succession.
- Open backlog carried forward: U5 (concurrency verified-at-1; OP-6 raise operator-ordered,
  governor-capped, reversible), U32 (host `~/.codex/config.toml` egress — 15C owed live item).

## 7. Verdict

**PASS.** Phase 15B is COMPLETE: `.modelsel` + `.conductor` + `.gate` landed. The live
Anthropic (`claude_code`) adapter has per-node `--model` selection with an honest roster
`model_ref` fallback, and is conductor-capable behind the governed contract (no naked session,
no credential, subscription-governed). The `.gate` code change discharges the `.conductor`
owed item — the executing model is reconciled from the `claude` CLI's own JSON response,
fail-closed, never fabricated, never a requested slug marked verified. The subscription-governor
deep re-inspection confirms allowance stays ≤2 across both live providers with no
raise-on-inference and release-before-acquire on succession; the governor and live_authorization
are byte-unchanged since `gate/phase-15a`. Independent gate-validator **PASS**; spec-auditor
**CLEAN**. Tag `gate/phase-15b`. The single live `claude` smoke remains skip-with-record until
the operator discharges the R8 §6 live-terms — no live-capability is claimed. Next:
`phase-15d`.
