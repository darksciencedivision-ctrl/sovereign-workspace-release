# PHASE 15E `.picker` — EVIDENCE REPORT

**Work unit:** `phase-15e.picker` (sub-step 1 of the Phase 15E decomposition:
**`.picker`** → `.spawn` → `.conductor-pane` → `.objective` → `.voice` → `.recovery` → `.gate`)
**Date:** 2026-07-24 · **Iteration:** 51 · **Status:** PASS (sub-step)
**Tag:** none. `gate/phase-15e` is a HIGH-STAKES phase gate and closes only at `.gate`, when all
sub-steps have landed and the mandatory independent gate-validator confirms the phase.
**Governing directive:** `AUTONOMOUS_BUILD_DIRECTIVE.md` §11 track 15E, §12 OP-7 (esp. §12.2
per-pane model picker), §13 OP-8, loop protocol §3, substitution rules §6, honesty §10.4.
Invariant 22 (VRAM residency scheduled/visible/never mid-generation eviction) is the load-bearing
canonical invariant for this unit.

---

## 0. RECOVERY PROVENANCE — a crashed prior attempt left a BROKEN tree and a FALSE report

This iteration recovered an uncommitted prior attempt at `phase-15e.picker` (the D-LOOP-1
crash-before-commit pattern this build has hit repeatedly — see LOOP_STATE notes 55/56/59/61/62).
Per the established discipline, **none of the survived work was trusted on sight**; the tree and
its evidence report were re-verified from scratch. That distrust was load-bearing:

- **The survived tree was BROKEN.** `py -3.12 -m pytest tests/unit/test_residency_planner.py
  tests/unit/test_pane_picker.py -q` on arrival → **3 failed, 21 passed**. The three failures were
  precisely the invariant-22 tests: `test_generating_model_is_never_evicted_new_load_is_queued`,
  `test_queued_model_is_promoted_when_generator_goes_idle`,
  `test_re_request_of_awaiting_eviction_keeps_it_resident`
  (`AssertionError: assert 'evicted' == 'awaiting_eviction'`). A **generating model was being
  evicted** — a direct violation of invariant 22 ("VRAM residency is scheduled, visible, **never
  mid-generation eviction**").
- **The survived evidence report was FABRICATED/STALE.** It claimed a gate-validator ran
  "PASS_WITH_RESERVATIONS" and "**mutation-probed invariant 22 by reverting the generating-guard
  (`and not x.generating`)**" — but **that guard was not in the code**, and the report's "22
  passed / 931 passed / 933 passed" counts could not have been produced on the tree that shipped.
  Like the orphan reports in notes 55/56, this report was **replaced wholesale**, not trusted.

**THE FIX (this iteration, test-first — the failing tests already encoded the requirement):** the
eviction candidate set in `ResidencyPlanner.request_load()` was missing the invariant-22 guard.
Added `and not x.generating` so a mid-generation model is never in the evictable set; it is instead
handled as an `AWAITING_EVICTION` blocker and the new load is `QUEUED`. Mutation-verified: reverting
the guard fails exactly those 3 tests (confirmed independently by the gate-validator below).

Nothing else was swept: `apps/desktop/package-lock.json` remains untracked and deliberately NOT
included in this Python-only unit (carried R4 from the 15D notes).

---

## 1. Exit criteria (OP-7 §12.2 + invariant 22) and verdicts

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | Picker offers BOTH live provider adapters with probed model labels — Anthropic: Opus 4.8 / Fable 5 / CLI default; OpenAI: 5.5 / 5.5 Sol / CLI default | **PASS** | `control_plane/nodes/pane_picker.py` reads `CLAUDE_CANDIDATE_MODEL_REFS` / `CODEX_CANDIDATE_MODEL_REFS` + each adapter's `resolve_*_model_ref`; test `test_both_frontier_providers_offered_when_authorized`. Fresh live enumeration shows all six frontier labels (§3). |
| 2 | Slugs are UNVERIFIED operator labels, never fabricated CLI ids; CLI-default is a recorded fallback | **PASS** | Every frontier option carries `verified:false`; "CLI default" has `model_slug:null, is_fallback:true`. `test_frontier_slugs_are_unverified_labels_never_fabricated`; fresh enumeration `frontier_verified_true_count=0`. |
| 3 | Local model list enumerated live from the operator's `ollama list` | **PASS** | `_local_options` consumes `adapters.detect.ollama_models()`; the freshly-witnessed driver captured **43 real local models** this iteration (§3). Empty enumeration ⇒ zero local options RECORDED (`test_empty_ollama_enumeration_yields_zero_local_options`), never a fabricated model. |
| 4 | Local models route through the VRAM residency planner; picker shows residency (resident / loading / awaiting-eviction) | **PASS** | NEW `scheduler/residency_planner/residency_planner.py`; each local option carries `residency` from `ResidencyPlanner.residency_map()`; absent ⇒ `not_loaded` (`test_local_model_without_residency_reads_not_loaded`). |
| 5 | **Invariant 22 — never mid-generation eviction; swaps visible** | **PASS** | `request_load` evicts only IDLE resident models (LRU) — the `and not x.generating` guard (§0) keeps a generating model out of the evictable set; when room is only reclaimable from a generating model it flags that model `awaiting_eviction` and QUEUES the new load; `mark_idle` performs the visible swap and promotes the queued model. Mutation-verified load-bearing (§4). |
| 6 | Fail closed: an unavailable frontier provider is SHOWN (greyed) with a specific reason, never hidden or silently authorized | **PASS** | Frontier availability gated on `LiveAuthorization.is_provider_live`; denied ⇒ option present with `available:false` + reason (`test_unauthorized_frontier_is_shown_but_greyed_with_reason`). Codex additionally requires host presence + auth, each unmet condition named (`test_codex_unavailable_names_each_missing_condition`); Anthropic additionally requires `claude` CLI presence (`test_anthropic_greyed_when_cli_absent_even_if_authorized`). |
| 7 | Selecting spawns a governed node through supervisor + governor (naked sessions refused) | **DEFERRED to `.spawn`** | This unit only OFFERS options (the picker data model). The governed spawn path from a selection — through `node_runtime/supervisor` + `SubscriptionGovernor`, refusing naked sessions — is sub-step `.spawn`. Declared, not claimed; confirmed an honest scope boundary by the gate-validator (no hidden spawn path exists). |
| 8 | §2 prohibitions: no live model call, no credential handling (§2.2), loop must not write `config/live_operation.json` (inv 1), `docs/canonical/` untouched | **PASS** | `pane_picker.py` + `residency_planner.py` import no `subprocess`/`socket`/`os`/clock/random, make no model call. The host driver performs only a benign local `ollama list` (§2.4), the local Ollama `/api/tags`+`/api/ps` reads, and the credential-free `probe_codex`; NO frontier model call. `config/live_operation.json` is gitignored + untracked (operator-created), unchanged by the loop. Four frozen canonical hashes re-verified (§5). |

---

## 2. What was built

**`scheduler/residency_planner/residency_planner.py` (NEW, pure/deterministic).** A VRAM
residency state machine over local models (states `not_loaded` / `loading` / `resident` /
`awaiting_eviction` / `queued` / `evicted`). `request_load` fits a model into the budget,
evicting only IDLE resident models least-recently-touched first; when the only remaining VRAM is
held by a **generating** model it never force-evicts — it flags the generator `awaiting_eviction`
and QUEUES the load (invariant 22). Only the **minimal LRU prefix** of generators whose cumulative
footprint covers the deficit is flagged (spec-audit MINOR-1, §4). `mark_generating`/`mark_idle`
drive the lifecycle; `mark_idle` performs the deferred swap and promotes queued models that now
fit. Holds no GPU handle and no wall clock — recency is an internal monotonic counter (replay-safe;
`Date.now()` is banned in this build). Budget and footprints are caller-injected (host-probed by
the driver).

**`control_plane/nodes/pane_picker.py` (NEW, pure/deterministic).** `build_pane_picker` assembles
the provider-neutral option set OP-7 §12.2 requires: Anthropic + OpenAI frontier options (probed
labels, availability gated on `LiveAuthorization`; Anthropic also on `claude` presence, Codex also
on host presence+auth) and one option per live-enumerated Ollama model annotated with its residency
state. Returns both grouped `providers` and a flat `options` list plus honest `counts` and the
`authorization` provenance. Nothing is hidden: an unavailable option appears with `available:false`
and a specific reason. Local models advertise a UNIFORM coarse worker-role menu
(`["reasoning","coding"]`) — capability is resolved by descriptor at `.spawn`, NEVER inferred from
the model name (I-SC1).

**`tools/live/enumerate_pane_picker.py` (NEW, operator-run metric — NOT in pytest).** Captures the
real host inputs (live `ollama list`, `/api/ps` VRAM + `/api/tags` disk footprints, the
`LiveAuthorization` gate, the benign `probe_codex` + `claude_code_available`) and prints the exact
picker JSON the shell selector would render. Substitution pattern (Phase-1 spike): the rendered
selector is an operator surface; this records the live data it consumes, never asserting a GUI.

**Tests (NEW):** `tests/unit/test_residency_planner.py` (16) + `tests/unit/test_pane_picker.py`
(10) = **26**, all green.

---

## 3. Live operator-run metric (substitution §6) — freshly witnessed THIS iteration

`py -3.12 tools/live/enumerate_pane_picker.py` on this Windows host, re-run and captured verbatim
this iteration to `docs/evidence/live/phase15e_picker_enumeration.json` (the survived JSON was
regenerated — not trusted). Witnessed values:

- `authorization`: live-authorized for `[claude_code, openai_codex_cli]`, register OP-6, 2
  terminals/subscription (read from the gitignored, operator-created `config/live_operation.json`).
- `claude_probe`: `present:true`; `codex_probe`: `present:true, authenticated:true` (benign local
  probes; NO model call).
- `ollama_enumerated`: **43** real local models (e.g. `qwen3:14b`, `qwen2.5-coder:7b`,
  `deepseek-r1:70b`, `llama3.3:70b`).
- `picker.counts`: `{total:49, available:49, frontier:6, local:43}`; `frontier_verified_true_count
  = 0`; no option is `available:false` without a reason.
- residency snapshot seeded from real disk sizes; the VRAM budget is a recorded stand-in (see
  substitution note). Residency reflects live host state at capture time — an honest snapshot,
  non-deterministic across runs by design.

**Substitution recorded (§6):** the total-VRAM budget in the driver is a conservative stand-in
(sum of running-model `size_vram` if any, else a 12 GiB default) because a portable GPU-VRAM query
is out of scope for this session. The emitted metric records this in `residency_provenance` with
`estimate:true` and a `budget_source` string. This is a **driver-side default, never a planner
assumption** — the pure planner takes the budget as an injected input, so the operator supplies the
real GPU budget at render time.

---

## 4. Reviews (run FRESH on the final tree this iteration — the survived report's reviews were discarded)

- **gate-validator (sub-step, isolated): OVERALL PASS.** Ran the two new files (24 passed at review
  time) and the full suite (**933 passed**) in its own context. **Independently reproduced the
  invariant-22 mutation probe**: backed up `residency_planner.py`, reverted the
  `and not x.generating` guard, re-ran → **3 failed, 11 passed** (exactly the generating-model
  tests), restored from backup, re-verified the file hash and green suite — confirming the guard is
  real and load-bearing, not decorative. Verified fail-closed picker honesty (no path marks a
  frontier option available without `LiveAuthorization.is_provider_live`; all frontier
  `verified:false`; CLI-default `model_slug:None`; empty enumeration ⇒ zero local; local slugs all
  present in the real enumeration), no banned calls (no clock/random/subprocess/socket), no frontier
  model call, `config/live_operation.json` gitignored+untracked+not-created-by-loop, `docs/canonical/`
  untouched, all four frozen canonical prefixes intact, and that `.spawn` is an honest scope boundary.
  Reservations (all honest-labeling, non-blocking): **R1** the residency budget is a disclosed
  stand-in (`estimate:true`), not a real GPU query; **R2** the driver stderr file is empty (benign);
  **R3** stray untracked `apps/desktop/package-lock.json` (out of scope, flagged for hygiene).
- **spec-auditor (isolated): CLEAN — no invariant violations, no prohibited drift.** Confirmed
  invariant 22 upheld (generating model never reclaimed; deterministic monotonic recency, no wall
  clock), invariant 20 fail-closed greyed-not-hidden, invariant 1 (LiveAuthorization-gated, no
  self-authorization), **invariants 3/4 + I-SC1 the highest-risk item and clean** (uniform local
  role menu, no capability-from-name substring match), §2.2/§2.4 (no credential; VRAM integer MB, no
  float money). One **MINOR-1** + 3 NITs, none blocking (§4a).

## 4a. Review-driven changes (applied this iteration; §7 details)

**MINOR-1 (over-eager `AWAITING_EVICTION` flagging)** → **FIXED.** When a load is queued behind
generators, only the least-recently-touched PREFIX of generators whose cumulative footprint covers
the remaining deficit is flagged `awaiting_eviction` — never every generator (which would needlessly
evict a mid-generation model the operator may still want resident once it idles). Two new tests:
`test_only_minimal_lru_prefix_of_generators_is_flagged`,
`test_prefix_extends_when_one_generator_cannot_cover_deficit` (+2 over the 24 the validator saw).
Never violates invariant 22 (nothing is force-evicted). **NIT-1** (queue promotion ordered by name,
not FIFO — no invariant mandates fairness), **NIT-2** (conductor-role eligibility hard-coded to the
Anthropic tuple rather than descriptor-derived; consistent with D-COND-01 today — recorded as a
`.spawn`/roster follow-up), **NIT-3** (driver live-I/O boundary confirmed honest, not a fault) →
**accepted, recorded, no code change**.

---

## 5. Held invariants / freeze

Four frozen canonical prefixes re-verified unchanged: v2.4 spec `6D3FD03B`, Architecture Plan
v1.0.1 `8C9B7240`, Plan v1.0 `668089B5`, Buildout Directive `CC414372`. `docs/canonical/`
untouched. `config/live_operation.json` gitignored + untracked, unchanged by this unit (inv 1 —
the loop did not create or edit it). No `git push`, no credential read/store/transmit (§2.2): the
picker names providers and reads a benign local model list only.

---

## 6. Test totals & review outcomes

- **Two new files:** `py -3.12 -m pytest tests/unit/test_residency_planner.py
  tests/unit/test_pane_picker.py -q` → **26 passed** (16 residency + 10 picker).
- **Full Python suite (post-MINOR-1-fix, this iteration):** `py -3.12 -m pytest tests/ -q` →
  **935 passed** (61 pre-existing `jsonschema.RefResolver` deprecation warnings only) — +26 over the
  `.gate`-close baseline of 909 (933 as the gate-validator independently measured pre-MINOR-1, +2
  the two MINOR-1 tests).
- Review outcomes: gate-validator OVERALL PASS (3 honest-labeling reservations); spec-auditor CLEAN
  (MINOR-1 fixed, 3 NITs accepted/recorded).

---

## 7. spec-auditor findings — full disposition

| # | Finding | Disposition |
|---|---|---|
| MINOR-1 | Queued-behind-generators path flags EVERY generating occupier `AWAITING_EVICTION`, not just the LRU prefix covering the deficit — a latent unnecessary eviction of a model still wanted resident | **FIXED.** Prefix now extends LRU-first only until the cumulative footprint covers the deficit, then stops. Never violates invariant 22. Two new tests prove the minimal-prefix and prefix-extension behavior. |
| NIT-1 | `_promote_queued` orders QUEUED models by name, not queue-arrival (deterministic but not FIFO-fair) | **Accepted, no action.** No invariant mandates promotion fairness; determinism is preserved. Recorded. |
| NIT-2 | Conductor-role eligibility is a literal on the Anthropic tuple (`_ANTHROPIC_ROLES`) rather than read from each adapter's `conductor_capable` descriptor | **Accepted, recorded as a `.spawn`/roster follow-up.** Consistent with D-COND-01 (claude_code is the sole conductor-capable adapter today); it is only an OFFER, no control-path coupling. Deriving from the descriptor is the cleaner shape when a second conductor-capable adapter exists. |
| NIT-3 | Driver performs live `urllib` I/O and is excluded from pytest; 12 GiB fallback budget | **Confirmed honest, no action.** Operator-run metric (Phase-1 substitution), budget emitted with `estimate:true` + `budget_source` provenance, no wall clock. |
