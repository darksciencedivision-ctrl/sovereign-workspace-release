# PHASE 15E `.spawn` — EVIDENCE REPORT

**Work unit:** `phase-15e.spawn` (sub-step 2 of the Phase 15E decomposition:
`.picker` → **`.spawn`** → `.conductor-pane` → `.objective` → `.voice` → `.recovery` → `.gate`)
**Date:** 2026-07-24 · **Iteration:** 52 · **Status:** PASS (sub-step)
**Tag:** none. `gate/phase-15e` is a HIGH-STAKES phase gate and closes only at `.gate`, when all
seven sub-steps have landed and the mandatory independent gate-validator confirms the phase.
**Governing directive:** `AUTONOMOUS_BUILD_DIRECTIVE.md` §11 track 15E, §12 OP-7 (esp. §12.2
per-pane model picker / §12.3 attended-vs-autonomous), loop protocol §3, substitution rules §6,
honesty §10.4. Load-bearing canonical invariants: **2/29** (no naked session / supervisor
containment), **1** (attended mode grants no extra authority), **4 + I-SC1** (capability from the
descriptor, never the model name), **21/22** (I-X3 subscription cap; VRAM residency scheduled +
visible, never mid-generation eviction), **§2.2** (no credential handling), **D-LOOP-1** (a spawn
made in a work unit is torn down within it).

---

## 0. RECOVERY PROVENANCE — a crashed prior attempt was recovered and re-verified from scratch

This iteration recovered an uncommitted prior attempt at `phase-15e.spawn` (the D-LOOP-1
crash-before-commit pattern this build has hit repeatedly — LOOP_STATE notes 55/56/59/61/62 and the
`.picker` recovery in note 63). Per the established discipline, **none of the survived work was
trusted on sight**. Recovered, untracked on arrival:
`node_runtime/supervisor/pane_node_spawn.py`, `tests/unit/test_pane_node_spawn.py`,
`tests/integration/test_pane_node_spawn_flow.py`, and a scratch `tmp_refute_spawn.py`.

Re-verification this iteration (the distrust WAS load-bearing — it surfaced a real fail-closed
defect the survived tree carried, see §3):

- The survived tests **do pass** on the current tree (`20 passed`), and the survived full-suite
  count is **producible and green** (`955 passed`, exit 0) — NOT a fabricated count. This is the
  opposite of the `.picker` recovery, whose survived report was fabricated; here the survived
  report was absent and the tree was honest-but-incomplete.
- The scratch `tmp_refute_spawn.py` (a throwaway refutation driver) was **deleted** — not part of
  the deliverable, never committed.
- Independent mutation-probing (§4) confirmed the load-bearing guards are real, and the
  spec-auditor surfaced a genuine fail-closed defect (**MINOR-1**) that this iteration **fixed
  test-first** before committing.

---

## 1. What this sub-step delivers

The `.picker` sub-step (`control_plane/nodes/pane_picker.py`) only **OFFERS** options. `.spawn`
adds `node_runtime/supervisor/pane_node_spawn.py::spawn_node_from_selection` — a thin, deterministic
coordinator (Buildout Directive §4) that turns exactly ONE picker selection (provider × model ×
role) plus a mode (attended | autonomous) into a **supervised, governed spawn** — or a **fail-closed
refusal** — and produces the pane chrome the shell renders.

It **composes** the already-gated supervised spawn paths (it re-implements NO gate):

| Selection | Composed path | Governance |
|---|---|---|
| frontier `claude_code` | `frontier_spawn.spawn_claude_code_terminal` | SubscriptionGovernor (I-X3, allowance=2) |
| frontier `openai_codex_cli` | `codex_spawn.spawn_codex_terminal(role=…)` | SubscriptionGovernor (I-X3), per-role |
| local coding | `opencode_spawn.spawn_opencode_harness` | ResidencyPlanner (inv 22); NOT subscription-governed |
| local reasoning | supervised `LocalWorkerAdapter` | ResidencyPlanner (inv 22); NOT subscription-governed |
| role `conductor` | **refused (deferred)** | born by the dedicated conductor-first path in `.conductor-pane` |

**Attended vs autonomous (OP-7 §12.3):** both modes spawn through the SAME supervised path with the
SAME permission profile — the mode is a chrome/routing label, never an authority grant (invariant
1). The full interactive ConPTY attachment is the later `.conductor-pane`/`.objective` sub-step;
here the mode is carried as a first-class governed fact on the chrome.

**D-LOOP-1:** `GovernedSpawn.teardown()` releases a frontier terminal's I-X3 count (idempotent;
no-op for an ungoverned local node), so a spawn made in a work unit is released within it.

---

## 2. Exit-criterion self-check (real command output)

Interpreter: `py -3.12` (Python 3.12.10, has jsonschema; bare `python` on host is 3.14 and lacks it).

```
$ py -3.12 -m pytest tests/unit/test_pane_node_spawn.py tests/integration/test_pane_node_spawn_flow.py -q
21 passed in 1.35s
```

```
$ py -3.12 -m pytest tests/ -q
956 passed, 61 warnings in ~195s          # 935 (.picker baseline) + 20 recovered + 1 MINOR-1 regression
```

| Criterion | Evidence | Verdict |
|---|---|---|
| One picker selection → governed supervised spawn | `test_frontier_claude_selection_spawns_governed_node`, `test_frontier_codex_selection_spawns_with_role` | PASS |
| Composes gated paths, no gate re-implemented | module dispatches to `spawn_claude_code_terminal`/`spawn_codex_terminal`/`spawn_opencode_harness`; no `governor.acquire`, allowance arithmetic, or live-auth assertion of its own | PASS |
| No naked session (inv 2/29) | empty `node_id` OR empty `permission_profile_id` → `SpawnRefused` before any dispatch; governor untouched (`test_naked_session_refused[...]`) | PASS |
| I-X3 allowance=2 enforced by real governor | 3rd frontier terminal raises `SubscriptionLimitExceeded`, count stays 2 (`test_ix3_third_frontier_terminal_refused_through_coordinator`) | PASS |
| Fail-closed refusals (greyed / un-offered role / unknown mode / missing subscription_ref / missing planner / unregistered local) | 7 dedicated tests; 2 mutation-verified (§4) | PASS |
| Local routes through ResidencyPlanner, never the governor | `test_local_selection_routes_through_residency_planner` asserts `gov.status()=={}`; queued-behind-generating visible (`test_local_selection_queued_...`) | PASS |
| Attended ≡ autonomous authority (inv 1) | `test_attended_and_autonomous_both_governed_same_authority`: same `permission_profile_id`, same `spawned_by_supervisor`, only chrome.mode differs | PASS |
| Chrome model badge carried verbatim | `test_chrome_model_badge_carried_verbatim_from_picker_option` | PASS |
| D-LOOP-1 teardown releases I-X3, idempotent | `test_teardown_is_idempotent`; no-op for local | PASS |
| End-to-end over REAL MCP (mock-first) | `test_frontier_selection_end_to_end_publishes_candidate_then_teardown`, `test_local_reasoning_selection_end_to_end_publishes_candidate`: scoped read → local gate PASS → CANDIDATE published → teardown | PASS |
| MINOR-1 fix: no leaked VRAM on harness-gate failure | `test_local_coding_harness_gate_failure_leaks_no_vram_reservation` (mutation-verified, §4) | PASS |
| No live model call / no credential (§2.2) | mock backends only (`MockClaudeCliBackend`/`MockCodexCliBackend`/`MockOpenCodeHarness`); module has no subprocess/socket/urllib self-invocation; only string ref `mcp_credential_id="mcp-ref"` | PASS |

**Substitution (Directive §6):** the pane chrome is rendered by the Electron shell, which this
non-interactive session cannot visually verify — same substitution pattern as `.picker`/Phase 1.
The chrome is proven as a pure data structure (`NodeChrome.as_dict()`); the rendered pane is an
operator-run metric, not claimed here. No live model runs (§10.4): mock-first only.

---

## 3. Spec-audit MINOR-1 — a real fail-closed defect, FIXED test-first this iteration

`ResidencyPlanner.request_load(model)` is a **mutating** call — it reserves VRAM and can flag idle
models for eviction — and the planner exposes **no cancel/release primitive** for a `LOADING`
reservation (verified: only `free_vram_mb`, no cancel/unload/evict). The survived tree called
`request_load` **before** the coding-harness presence/version/identity gate. If that gate refused
(`OpenCodeUnavailable`/`OpenCodeVersionError`/`NakedLaunchRefused`), the exception propagated leaving
a **phantom, visible-but-wrong `LOADING` residency entry** with no way to undo it — contrary to
invariant 22's "residency is scheduled, visible", and asymmetric with the frontier paths, which
deliberately release the governor count on construct-failure.

**FIX:** `_spawn_local` now builds the **side-effect-free** supervised handle FIRST (the coding
harness gate / the reasoning-adapter identity re-check — neither touches residency), and reserves
VRAM via `request_load` **only once the node is known spawnable**. A harness/identity refusal now
happens with ZERO VRAM reserved. Test-first regression added
(`test_local_coding_harness_gate_failure_leaks_no_vram_reservation`) and mutation-verified (§4).

Two further spec-audit findings were recorded as owed items (honest, not faked), not force-fixed
within this thin dispatcher's scope:

- **U63** (spec-audit MINOR-2 + NIT-1): a local CODING node reserves/badges the picker-SELECTED tag,
  but OpenCode auto-resolves its own coder model (`probe.coder_model`) — they coincide in the
  mock-first proof but can diverge on the real path; and local option `roles` are today a coarse
  uniform menu, not a per-model capability descriptor. The overstated I-SC1 comment for the local
  path was **softened this iteration** to match what the code does. Owed: thread the selected tag
  into the harness (or refuse on mismatch) + a real per-model local descriptor.
- **U64** (spec-audit NIT-2): a QUEUED/LOADING (non-resident) local node is returned as a live
  handle with no structural gate coupling `execute()` to `RESIDENT`. Latent under mock-first
  (residency is at least visible in chrome). Owed: a `ready()`/residency gate before execution.

Both are in `docs/registers/UNRESOLVED_ISSUE_REGISTER.md`. Spec-auditor found **no invariant
violations**.

---

## 4. Independent validation

**gate-validator (sub-step, isolated context): OVERALL PASS.** Re-ran the focused suite
(`20 passed`) and the full suite (`955 passed`, exit 0 — measured before the MINOR-1 fix +1),
confirmed the module composes the gated paths without re-implementing a gate, verified the
naked-session / I-X3 / local-not-governed / attended≡autonomous criteria against source, and
**mutation-tested two guards itself**: neutralizing the greyed-`available` guard failed exactly
`test_unavailable_option_refused_fail_closed`; neutralizing the frontier `subscription_ref` guard
failed exactly `test_frontier_missing_subscription_ref_refused`; both restored byte-clean. Confirmed
frozen canonical hashes intact and `config/live_operation.json` gitignored/untracked
(`git ls-files config/` → only `.example.json`). No material reservations; noted the conductor-role
deferral correctly keeps `gate/phase-15e` unapplied until `.conductor-pane` lands.

**Builder mutation checks (self, §3.4):** three guards mutated → reverted, each proven load-bearing:
(a) greyed-`available` guard → `test_unavailable_option_refused_fail_closed` FAILED;
(b) teardown `_release` → the frontier + idempotence teardown tests FAILED (`active_count==1`);
(c) MINOR-1 reorder (reserve VRAM before the handle build) →
`test_local_coding_harness_gate_failure_leaks_no_vram_reservation` FAILED
(`'loading' == 'not_loaded'`). All mutations reverted; `grep "MUTATION|False and"` clean.

**spec-auditor: no invariant violations** (inv 1/2/3/4/I-SC1/21/22, §2.2, §4, model-id honesty all
clean). MINOR-1 fixed pre-commit; MINOR-2/NIT-1/NIT-2 recorded (U63/U64) or comment-softened; NIT-3
(Claude role is chrome-only while Codex honors it functionally — Claude Code legitimately does both)
recorded here as a benign labeling note.

---

## 5. Prohibitions & invariants honored

- **§2.2 credentials:** never read/stored/transmitted; frontier paths take an injected mock backend;
  the real path invokes the host CLI's own auth downstream. No credential crosses this coordinator.
- **§2.4 live sessions:** none — mock-first, zero live model calls (§10.4 honesty).
- **inv 2/29:** no naked session — identity + supervisor-issued profile required, re-checked by the
  downstream adapter/harness as defense-in-depth.
- **inv 1:** attended mode grants no authority the profile did not already grant.
- **inv 3:** the conductor role is refused here (deferred to `.conductor-pane`), never built as a
  worker handle under a "conductor" badge.
- **inv 4 / I-SC1:** the role must be one the option OFFERED, never inferred from the model name.
- **inv 21/22:** frontier ≤2/subscription (governor-enforced); local via visible VRAM residency,
  never mid-generation eviction (queued-behind-generating proven).
- **D-LOOP-1:** teardown releases the governed count within the unit; no live process is left
  running (none was spawned — mock-first).
- **docs/canonical/ frozen:** untouched; four frozen hashes intact.

---

## 6. Files

**New (committed this unit):**
- `node_runtime/supervisor/pane_node_spawn.py` — the governed spawn coordinator
- `tests/unit/test_pane_node_spawn.py` — 14 unit tests (incl. the MINOR-1 regression)
- `tests/integration/test_pane_node_spawn_flow.py` — 2 end-to-end tests over the real MCP server

**Amended:** `docs/registers/UNRESOLVED_ISSUE_REGISTER.md` (U63, U64 opened).
**Deleted:** `tmp_refute_spawn.py` (recovered scratch, never a deliverable).
**Deliberately NOT swept:** `apps/desktop/package-lock.json` (pre-existing untracked artifact,
unrelated to this Python-only unit; carried since iter16).

## 7. Next

`next_step = phase-15e.conductor-pane` — the OP-8/§13 conductor-first, pinned, live interactive
ConPTY CONDUCTOR chat pane (pane 1 on launch), which is the dedicated path this worker-spawn
dispatcher deliberately refuses the `conductor` role to. `gate/phase-15e` (high-stakes, MANDATORY
independent gate-validator) closes only when all seven sub-steps land.
