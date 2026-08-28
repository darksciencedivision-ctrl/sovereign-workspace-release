# PHASE 15E `.conductor-pane` — EVIDENCE REPORT

**Work unit:** `phase-15e.conductor-pane` (sub-step 3 of the Phase 15E decomposition:
`.picker` → `.spawn` → **`.conductor-pane`** → `.objective` → `.voice` → `.recovery` → `.gate`)
**Date:** 2026-07-24 · **Iteration:** 53 · **Status:** PASS (sub-step)
**Tag:** none. `gate/phase-15e` is a HIGH-STAKES phase gate and closes only at `.gate`, when all
seven sub-steps have landed and the mandatory independent gate-validator confirms the phase.
**Governing directive:** `AUTONOMOUS_BUILD_DIRECTIVE.md` **§13 (OP-8 — the conductor is a live
conversational CLI)**, §12.4 (conductor-first startup), §11 track 15E, loop protocol §3,
substitution rules §6, honesty §10.4. Load-bearing canonical invariants: **3 + I-CN1** (the
conductor is an INTERFACE + runtime selection, never a vendor default / model name), **2/29** (no
naked session / supervisor containment), **1** (attended mode grants no extra authority; the app
never self-authorizes a succession), **21** (I-X3 subscription cap = 2), **§2.2** (no credential
handling), **28** (conductor succession works — Resume→Select reachable), **D-LOOP-1** (a spawn
made in a work unit is torn down within it).

---

## 1. What this sub-step delivers

`.spawn` refuses the conductor role and points here: *"the conductor role is spawned by the
dedicated conductor-first path (Phase 15E `.conductor-pane`), not this worker-spawn dispatcher."*
This sub-step is that dedicated path — **the conductor-first, pinned, interactive CONDUCTOR pane**:

- **`node_runtime/supervisor/conductor_pane_spawn.py` (NEW)** — `spawn_conductor_pane(...)`: the ONE
  place the live interactive CONDUCTOR pane is born. It reuses the frontier live-gate set VERBATIM
  (a conductor pane is a subscription-backed live path exactly like a live worker) and differs only
  in what it builds:
  - an **INTERACTIVE `claude` launch** (`build_interactive_command` — NO `-p`, NO
    `--output-format json`; the operator drives the session, OP-8 §13.1–2), not the one-shot worker
    command;
  - the **CONDUCTOR chrome** (`ConductorPaneChrome`): pinned pane 1, `attended` mode, model badge =
    the current **SELECTION** (fable-5 / recorded CLI-default fallback), subscription n/2 visible;
  - the **Resume→Select succession affordance** reachable from that chrome
    (`conductor_succession_affordance`).
- **`adapters/frontier/claude_code.py`** — `build_interactive_command(executable, *, model)` (pure,
  interactive argv, same fail-closed forbidden-flag guard as the headless command); the credential
  scrub extracted to a module-level `scrub_credential_env` + `is_credential_env_key` so the one-shot
  worker command AND the interactive conductor pane scrub by the ONE rule (§2.2). `build_env`
  delegates to it (behaviour byte-identical — proven by the unchanged frontier suite).
- **`terminal/compositor/conductor-pane.js` (NEW)** — pure/deterministic render model for pane 1's
  CONDUCTOR badge (`conductorBadge`) and the Resume→Select control (`conductorSuccessionControl`,
  `conductorPaneSpec`). Fail-closed: a missing selection renders "(unknown selection)", an
  unverified executing checkpoint renders unverified — never a fabricated checkpoint id (invariant 3).
- **Shell wiring (operator-run surface, directive §6)** — `apps/desktop/main.js` opens pane 1 as the
  pinned CONDUCTOR node on launch (`createConductorPane`), exposes `conductor:state` /
  `conductor:succeed`, and pushes `shell:conductor`; `preload.js` bridges `conductorState()` /
  `succeedConductor()` / `onConductor`; `renderer.js` + `index.html` draw the CONDUCTOR badge + a
  Resume→Select button on the conductor pane's chrome only.

### Scope discipline (kept honest, NOT faked)
Per OP-8 §13, the conductor pane ALSO orchestrates while conversing and accepts voice/file
injection. Those are the **next** sub-steps, explicitly deferred and recorded, never claimed here:
native-MCP orchestration (§13.4) → `.objective`; voice-IN (§13.5) → `.voice`; restart recovery of
the conductor-first layout → `.recovery`. This sub-step delivers the pane itself, its governance,
its interactive launch spec, and its chrome.

---

## 2. Substitution (directive §6) — what is proven headlessly vs operator-run

OP-8 §13 wants a **live interactive agentic chat** in a ConPTY pane. A live `claude` interactive
session and the rendered Electron window cannot be exercised in this non-interactive build session
(no Electron, no operator terminal, no live subscription call permitted by the loop). Per the
Phase-1 substitution pattern used throughout this build:

- **Proven headlessly (governance-bearing):** the full fail-closed gate set, the interactive argv +
  credential-scrubbed env, the honest CHOSEN/REQUESTED/EXECUTING selection record, the pinned
  CONDUCTOR chrome + badge, the Resume→Select affordance, and D-LOOP-1 teardown — all via a
  **mock-first injected launcher** that spawns NOTHING (zero live calls, §2.2/§10.4).
- **Operator-run metric (like every GUI in this build):** the actual interactive `claude` ConPTY
  drive and the rendered pane. `spawn_conductor_pane` builds and gates the interactive session but
  makes **no live call itself**; the badge honestly reads `awaiting_live_conductor` until a real
  interactive launch supplies a launcher through the identical governed path.

**No live model call was made in this work unit.** The build/env/argv builders are pure and the only
"launch" exercised is a mock session handle.

---

## 3. Honesty of the model badge (invariant 3 / I-CN1)

The conductor is an INTERFACE + runtime selection. The badge shows the operator **SELECTION label**
(`fable-5`); it is NEVER a fabricated executing checkpoint id. `spawn_conductor_pane` binds the
selection through the single honest `bind_conductor_selection` (Phase 15D `.selection`):
`executing.model` stays **None** and `model_verified=False` until a live reply reports a checkpoint —
exactly as `.succession`/`.gate` established. `model_available=False` records the directive-§11-15B
**CLI-default fallback** (the argv drops `--model`, the badge marks `is_fallback`). The JS badge
mirrors this fail-closed (unknown selection / unverified rendered explicitly).

---

## 4. Self-check — every exit criterion with real command output

| Exit criterion (OP-8 §13 / §12.4) | Evidence |
|---|---|
| Conductor-first: pane 1, pinned, labeled CONDUCTOR | `test_conductor_pane_spawns_governed_pinned_conductor_first`; JS `conductorPaneSpec` + `a pinned conductor pane-1 is never auto-collapsed` (PaneModel pin ⇒ tiling P0) |
| Model badge = current selection (fable-5 / recorded fallback) | `test_badge_shows_selection_label_executing_unverified`, `test_recorded_fallback_when_selection_model_unavailable`; JS badge tests |
| Live INTERACTIVE session (no `-p`) | `test_interactive_command_has_no_headless_flags`, `test_launch_spec_is_interactive_and_credential_scrubbed` |
| Governed node — no naked session (inv 2/3/29) | gates reused verbatim; `test_naked_session_refused`, deferred-launch test keeps it governed |
| I-X3 = 2 enforced; n/2 in chrome | `test_ix3_second_conductor_pane_on_same_subscription_allowed_third_refused`; chrome `subscription == {ref, in_use, allowance:2}` |
| §2.2 no credential handling | `test_scrub_credential_env_removes_every_credential_and_endpoint_var`; interactive env scrubbed |
| Succession Resume→Select reachable from chrome (inv 28) | `test_succession_affordance_reachable_from_chrome`; JS `conductorSuccessionControl`; shell `conductor:succeed` intent |
| Fail-closed: unauthorized / unconfirmed terms / absent CLI | `test_unauthorized_live_auth_refused…`, `test_unconfirmed_operator_terms_refused`, `test_absent_cli_refused_on_real_path` |
| D-LOOP-1 teardown releases I-X3 | `test_conductor_pane_spawns…` teardown assertions; `test_teardown_idempotent` |
| Mode is chrome, not authority (inv 1) | attended mode carried in chrome; succeed intent only forwards operator request, self-authorizes nothing |

**Test totals (real output):**
- Python: `py -3.12 -m pytest tests/ -q` → **974 passed** (0 skipped; +18 over the 956 `.spawn`
  baseline). New file `tests/unit/test_conductor_pane_spawn.py` = 18 tests.
- JS: `node --test terminal/test/*.test.js` → **124 passed**; `node --test apps/desktop/test/*.test.js`
  → **35 passed** (0 skipped). New file `terminal/test/conductor-pane.test.js` = 10 tests.
- Shell files (`main.js`, `preload.js`, `renderer.js`, `conductor-pane.js`) pass `node --check`.

**Mutation-intent checks:** the interactive command carries no `-p` and the forbidden-flag guard
refuses `--dangerously-skip-permissions` (proven in-process); the fail-closed refusals (naked
identity, missing subscription, unauthorized live_auth, unconfirmed terms, absent CLI) each have a
dedicated test that asserts NO terminal is leaked.

---

## 5. Invariant / prohibition check

- **Inv 3 / I-CN1** — conductor is interface + selection; badge = SELECTION label, executing
  unverified until a live reply. ✔
- **Inv 2/29** — no naked session: the pane is a governed conductor node; the shell spawns no PTY
  until a live interactive launch; every gate re-applies. ✔
- **Inv 1** — attended mode grants no authority; the Resume→Select button forwards the operator's
  request to the governed Python succession path and self-authorizes nothing. ✔
- **Inv 21 (I-X3)** — allowance=2 enforced by the real SubscriptionGovernor; a third pane refused;
  n/2 visible in chrome. ✔
- **§2.2** — no credential read/stored/transmitted; the env is scrubbed of every credential/endpoint
  var; the interactive argv carries no key; the OAuth token stays in the CLI's host-native store. ✔
- **Inv 28** — succession Resume→Select reachable from chrome; the real serialize/reconstruct/restore
  is the already-gated `SuccessionManager` (15D). ✔
- **§10.4 / §6** — no live call; the interactive drive + rendered pane are operator-run, recorded as
  such, never overclaimed. ✔
- **D-LOOP-1** — no live process spawned; the mock proof acquires + releases the I-X3 count within
  the unit. ✔
- Frozen canonical set untouched; `config/live_operation.json` remains gitignored/untracked.

---

## 6. Reviews

- **gate-validator (sub-step, isolated): OVERALL PASS.** Independently reproduced every count
  (`py -3.12 -m pytest tests/` → 974 passed/0 skipped; `node --test terminal/test/*.test.js` → 124;
  `apps/desktop/test/*.test.js` → 35; new JS file → 10). Verified the credential refactor is
  behavior-preserving and scrubs by ONE rule on both launch paths (`build_env(base) ==
  scrub_credential_env(base)`; endpoint override + `*TOKEN*` superset removed; 230 passed in the
  frontier/credential/conductor subset). Confirmed `build_interactive_command` emits no `-p`/
  `--output-format`/`json` and rejects `--dangerously-skip-permissions`/`--api-key`/`--with-*` via
  the shared forbidden-flag guard. Confirmed the gate set is reused verbatim (re-implements none) and
  is fail-closed **before** any governor mutation; **mutation-probed** the `subscription_ref` guard
  (disabled ⇒ exactly `test_missing_subscription_ref_refused` fails; restored byte-identical, sha256
  `1de123c5…`) and the no-wedge path (launcher raising after `acquire` ⇒ `active_count==0`). Confirmed
  invariant-3 honesty (SELECTION label; executing None/unverified; JS fails closed to "(unknown
  selection)" and refuses to brand a non-conductor chrome CONDUCTOR), no subprocess/socket/urllib in
  the new module (no live call), D-LOOP-1 acquire+release within the unit, freeze OK
  (`compute_manifest.py` → no drift; all four hashes), `config/live_operation.json` untracked, and
  `gate/phase-15e` **ABSENT** (correct). One disclosed **non-blocking observation** (not a
  reservation): the running shell renders pane-1 chrome from local `CONDUCTOR_SELECTION_RECORD`
  literals and does not yet call the Python `spawn_conductor_pane`, so the I-X3/live-gate acquisition
  is exercised only in the headless Python unit — consistent with the §6 substitution pattern and
  disclosed in §2/§7 (the live ConPTY drive is operator-run).
- **spec-auditor (substantive new code): CLEAN** — no invariant violation, no prohibited drift (no
  TTS, no consensus forcing, no extra approval layer, no opaque-agent UI, no scope expansion). The
  high-risk invariants for this unit all hold (3/I-CN1, 1, 2/29, 21/I-X3, 28, §2.2, §2.4/§10.4,
  D-LOOP-1) — cited to source. Four hygiene findings, none blocking:
  - **MINOR-1** (shell hard-codes the conductor SELECTION as JS literals instead of sourcing the
    canonical `OPERATOR_SELECTED_CONDUCTOR` over IPC — drift-capable, currently matching so the badge
    stays honest) → **recorded as U65**; an inline sync note added at `main.js` flags the requirement.
    The honest fix (deliver the governed selection/chrome over the read-only IPC, as `inspector:`/
    `statusbar:` do) is owed to when the live conductor path is wired (a later 15E sub-step).
  - **MINOR-2** (preload/main/conductor-pane.js comments overstated the IPC/forwarding wiring for a
    data-affordance-only sub-step) → **FIXED pre-commit**: the three comment sites now state the
    succeed intent only RECORDS/acknowledges the operator's request and that real forwarding + the
    IPC delivery of governed facts is deferred to a later sub-step.
  - **NIT-3** (Resume→Select button lives in every pane's chrome, hidden for non-conductor panes;
    return value ignored ⇒ no operator-visible ack yet) → **recorded/accepted**: the conductor pane's
    chrome is an operator-run surface; visible acknowledgement is owed with the live wiring.
  - **NIT-4** (the gate keys on the PROVIDER capability `node_class=worker_reasoning` for a
    role-conductor pane) → **FIXED pre-commit**: a one-line note added at the call site (the
    conductor-ness is chrome + interactive launch, not a distinct capability).

  All four post-fix files re-pass `node --check`; the focused Python (18) + JS (10) suites stay green
  after the comment-only edits (no behavior change).

---

## 7. Owed / deferred (honest limits)

- OP-8 §13.4 native-MCP orchestration (conductor dispatches to worker CLIs while conversing) → `.objective`.
- OP-8 §13.5 voice-IN (Parakeet, propose-never-execute) → `.voice`.
- OP-8 §13.3 file/context injection mid-conversation → `.objective`/later 15E.
- Restart recovery restoring the conductor-first layout → `.recovery`.
- The live interactive `claude` ConPTY drive + rendered pane are operator-run (directive §6); a
  live-capability claim requires a real operator run.
- U58 (live flow workers) carried into 15E remains open.
- **U65 (new, MINOR-1):** the shell renders pane-1's badge from local `CONDUCTOR_SELECTION_RECORD`
  literals that MUST mirror `control_plane/conductor/selection.OPERATOR_SELECTED_CONDUCTOR`; the honest
  fix is to source the governed selection/chrome over the read-only IPC (as `inspector:`/`statusbar:`
  do). Owed to when the live conductor path is wired (a later 15E sub-step). Matches today ⇒ badge honest.
- **NIT-3 (recorded/accepted):** the Resume→Select button is present in every pane's chrome and hidden
  for non-conductor panes; a visible operator acknowledgement of the succeed request is owed with the
  live wiring.
- The shell's conductor chrome (main.js/renderer.js/index.html) is an operator-run surface: its DATA
  shape is headlessly tested (`terminal/test/conductor-pane.test.js`), the painting is operator-verified.

**Work commit:** `15b8b4a` · **Evidence/register commit:** this commit.
