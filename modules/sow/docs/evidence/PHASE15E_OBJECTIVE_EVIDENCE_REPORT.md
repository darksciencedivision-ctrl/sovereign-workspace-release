# PHASE 15E `.objective` — EVIDENCE REPORT

**Work unit:** `phase-15e.objective` (sub-step 4 of the Phase 15E decomposition:
`.picker` → `.spawn` → `.conductor-pane` → **`.objective`** → `.voice` → `.recovery` → `.gate`)
**Date:** 2026-07-24 · **Iteration:** 54 · **Status:** PASS (sub-step)
**Tag:** none. `gate/phase-15e` is a HIGH-STAKES phase gate and closes only at `.gate`, when all
seven sub-steps have landed and the mandatory independent gate-validator confirms the phase.
**Governing directive:** `AUTONOMOUS_BUILD_DIRECTIVE.md` **§12.5 item 5 (OP-7 — the operator command
surface: objective input + approval-queue drawer, a plan §10.3 requirement and a stated 15E exit
criterion)**, reframed by **§13 (OP-8 — the conductor is a live conversational CLI)**, §11 track 15E,
loop protocol §3, substitution rules §6, honesty §10.4. Load-bearing canonical invariants: **1**
(operator holds final authority — the app never self-authorizes; only the operator resolves an
approval), **16** (explicit gates, no override — a gate-failed plan cannot be approved into
execution), **13** (conflicts/decisions are explicit objects), **12** (append-only — a resolved item
is a new record, history is not mutated), **27/28** (observability; conductor synthesis), **§2.4/§10.4**
(mock-first; no live call in this unit).

---

## 1. What this sub-step delivers

OP-7 §12.5 item 5 named the one missing piece of the operator's surface: *"an objective input
(operator types an objective → conductor decomposes → plan surfaces for approval) and the
approval-queue drawer (plan gates, protected actions, clarifications, badge count). Without this the
conductor cannot receive work or ask the operator anything."* This sub-step is that surface — the
governed **pause for operator authority** between the conductor's decomposition and any assignment.
It **composes** the machinery already built (Phase 15D `LiveGovernedFlow`, Phase 12 `CommandBroker`,
the gate engine) and **re-implements none of it** (Directive §4 — a thin deterministic coordinator).

- **`control_plane/orchestration/operator_surface.py` (NEW)** — the authority:
  - **`ApprovalQueue`** — the ONE operator-facing drawer for the three kinds (`ApprovalKind`:
    `plan` / `protected_action` / `clarification`) with a **badge count**. Pure/deterministic
    (monotonic ids, no clock, no I/O). `resolve(item_id, operator, decision=…)` enforces
    **invariant 1** in code (a non-operator `Identity` is refused) and **invariant 16** (an
    `approve` of a non-approvable item — a gate-failed plan — is refused; final authority is not an
    override of a failed gate). Items are immutable: `resolve` writes a NEW record (append-only
    spirit, invariant 12). `drawer_model()` derives `badge_count` from the pending set so no caller
    can inflate it.
  - **`ObjectiveIntake`** — objective → **plan surfaces for approval, assigns nothing**. `submit`
    drives `LiveGovernedFlow.begin` (the conductor decomposes; the REAL gate engine renders the
    `gate@1.0` plan verdict) and then STOPS: the plan is enqueued for the operator; no worker is
    scheduled (invariant 1 — the conductor proposes, the operator disposes). `approve` resolves the
    plan item (operator-only, approvable-only) and ONLY THEN runs `run_waves` + `finish` → CANDIDATE
    → gates → conductor synthesis → acceptance packet. `reject` declines the objective — the flow is
    abandoned, nothing is assigned. One objective per intake (fail-closed on a second `submit`).
  - **`build_plan_proposal` / `propose_plan_for_approval`** — fold a `Decomposition` + the flow's
    plan verdict into an operator-facing `PlanProposal`; `approvable` is DERIVED from the gate, never
    asserted.
  - **`mirror_broker_outcome` / `apply_protected_decision`** — reflect a `CommandBroker` outcome into
    the SAME drawer (protected/destructive → `protected_action`, low-confidence/unknown →
    `clarification`, safe → nothing) carrying the broker's `pending_id`, and route a resolved
    protected-action decision back to the real broker (which re-checks operator authority itself —
    invariant 1 in two places by design). No verb is re-classified here.
- **`terminal/compositor/approval-drawer.js` (NEW)** — the pure render model: folds the
  `approval_drawer@1.0` snapshot into rows + a **recomputed** badge (an inflated payload count is
  ignored). Fail-closed: a malformed/absent snapshot yields an empty `ok:false` model (never a
  fabricated item, never a throw into the always-visible chrome); an unknown-kind row is surfaced
  (labeled "Unknown"), never dropped; `approvable` renders an Approve affordance only on strict
  `true`.
- **Shell wiring (operator-run surface, directive §6)** — `apps/desktop/main.js` folds the drawer
  with the same pure core and exposes `approvals:fetch` (read) + `approvals:decide` (records the
  operator's request, **never self-authorizes** — invariant 1, exactly as `conductor:succeed` does);
  `preload.js` bridges `approvals()` / `decideApproval()` / `onApprovals`; `renderer.js` + `index.html`
  draw the drawer, the badge, and per-row Approve/Reject (Approve shown only when approvable).

### Scope discipline (kept honest, NOT faked)
This sub-step delivers the operator command surface (objective intake + approval drawer) and its
governance. OP-8 §13.4 native-MCP orchestration WHILE conversing and §13.5 voice-IN are the **next**
sub-steps, deferred and recorded, never claimed here. The end-to-end objective→CANDIDATE→gate→
synthesis→acceptance-packet flow is Phase 15D's, driven here through the governed pause — not
re-implemented.

---

## 2. Substitution (directive §6) — what is proven headlessly vs operator-run

- **Proven headlessly (governance-bearing):** the full `ApprovalQueue` authority (invariant 1 / 16
  refusals, badge derivation, append-only resolve), the `ObjectiveIntake` pause (no assignment until
  operator approval; reject abandons; blocked-plan not approvable), the plan-proposal fold, the
  broker mirroring + round-trip to a real `CommandBroker` control event, and the JS drawer render
  model — all pure/deterministic, and the intake proven end to end over a **REAL MCP server** with a
  mock conductor/worker (no `claude` process, §2.4/§10.4).
- **Operator-run metric (like every GUI in this build):** the rendered drawer and badge, and the
  live delivery of the in-process `ApprovalQueue` snapshot over the read-only IPC channel. The shell
  currently returns an **honest EMPTY drawer** (no fabricated pending item) and `approvals:decide`
  RECORDS the operator's request; wiring the live queue feed + routing the decision to the governed
  `ApprovalQueue.resolve` / `ObjectiveIntake` is owed with the live conductor path (**U66**), exactly
  as statusbar's governor feed and the conductor selection literals (U65) are.

**No live model call was made in this work unit.**

---

## 3. Self-check — every exit criterion with real command output

| Exit criterion (OP-7 §12.5 item 5) | Evidence |
|---|---|
| Objective input → conductor decomposes → **plan surfaces for approval** | `test_submit_surfaces_a_plan_and_assigns_nothing_until_approved` (integration, real MCP): plan queued, task_count ≥ 2, badge 1 |
| **Assigns nothing** until the operator approves (invariant 1) | same test: every task stays PENDING/READY, no `artifact` ACCEPTED in MCP before approval |
| Operator approval runs the governed flow to an acceptance packet | `test_operator_approval_runs_the_flow_to_an_acceptance_packet`: `acceptance_packet@1.0`, accepted_count > 0, entries ACCEPTED in MCP, leg `mock` |
| Operator rejection declines, assigns nothing | `test_operator_rejection_declines_the_objective_and_assigns_nothing` |
| **Only the operator** may resolve (invariant 1) | `test_only_operator_may_resolve` (worker/conductor refused); integration `approve(WORKER)` raises |
| **Gate-failed plan not approvable** (invariant 16) | `test_non_approvable_item_can_be_rejected_but_never_approved` (match "invariant 16") |
| Approval drawer = plan + protected actions + clarifications + badge | queue `drawer_model()` kind_counts + `test_protected_command_is_mirrored…`, `test_clarification_is_mirrored_not_approvable`; JS `buildApprovalDrawer` kindCounts |
| Protected-action decision routes to the REAL broker | `test_protected_command_is_mirrored_and_routes_back_to_the_broker` (control event fires; broker dequeues) |
| Badge count honest (never inflated/fabricated) | queue derives from pending; JS `recomputes the badge from rows — an inflated payload badge_count is ignored`; fail-closed empty on malformed |

**Test totals (real output):**
- Python: `py -3.12 -m pytest tests/ -q` → **994 passed** (0 skipped; +20 over the 974
  `.conductor-pane` baseline). New: `tests/unit/test_operator_surface.py` (15) +
  `tests/integration/test_objective_intake.py` (5). (Among the 15 is the decision-integrity
  regression `test_apply_protected_decision_derives_the_action_from_the_recorded_decision`, which
  pins the guard that `apply_protected_decision` derives the routed action from the recorded operator
  decision — carried in with the recovered work and re-verified present/passing this iteration; see §5.)
- JS: `node --test terminal/test/*.test.js` → **132 passed** (+8 over 124; new file
  `terminal/test/approval-drawer.test.js` = 8). `node --test apps/desktop/test/*.test.js` → **35 passed**.
- Shell files (`main.js`, `preload.js`, `renderer.js`, `approval-drawer.js`) pass `node --check`.

**Mutation-intent checks:** invariant-1 (non-operator resolve) and invariant-16 (approve a
non-approvable plan) each have a dedicated raising test; the JS badge test asserts a payload
`badge_count: 99` does NOT drive the badge (rendered 1).

---

## 4. Invariant / prohibition check

- **Inv 1** — only an operator `Identity` resolves an item (enforced in `ApprovalQueue.resolve` AND
  re-checked by `CommandBroker.approve`); `ObjectiveIntake` assigns no work until operator approval;
  the shell `approvals:decide` only RECORDS the request, self-authorizes nothing. ✔
- **Inv 16** — a gate-failed plan is enqueued `approvable=False`; `resolve(decision="approve")` on it
  is refused. No operator override path; the plan is surfaced (observability) but cannot advance. ✔
- **Inv 12/13** — resolve writes a NEW immutable item (history preserved); each queued item is an
  explicit decision object. ✔
- **§2.4/§10.4 / §6** — mock-first: no `claude`/live call; the drawer render + live queue feed are
  operator-run, recorded as such, never overclaimed. ✔
- **Directive §4** — the module composes `LiveGovernedFlow`/`CommandBroker`/gate engine and
  re-implements no gate, no classifier, no lifecycle. ✔
- Frozen canonical set untouched: all four pinned canonical hashes verified intact
  (`6D3FD03B`, `8C9B7240`, `668089B5`, `CC414372`) by regenerating the manifest and comparing; the
  regenerated `docs/PHASE0_FREEZE_MANIFEST.json` was then REVERTED to HEAD (it is the Phase-0 freeze
  baseline + the operator signature, not a per-gate artifact — never rewritten by the loop).
  `config/live_operation.json` remains gitignored/untracked.

## 5. Reviews (fresh this iteration — prior in-flight review claims were treated as DEAD per D-LOOP-2)

**Recovery provenance (D-LOOP-2 / notes 55/56/70-73 pattern).** This unit's source, tests, shell
wiring and register entries (U65/U66) were recovered UNCOMMITTED from prior stall-guard iterations.
Nothing survived was trusted on sight: every dependency was re-verified by re-running the full suites
from scratch, and BOTH reviews were re-run fresh in the foreground (the earlier draft's review text
was discarded as dead). The recovered decision-integrity guard in `apply_protected_decision` (derive
the routed action from `item.decision`; refuse a contradicting supplied decision) and its regression
test `test_apply_protected_decision_derives_the_action_from_the_recorded_decision` were re-verified
present and passing — it is real code in the tree, not a claim.

- **spec-auditor (substantive new code): CLEAN** — no invariant violation, no prohibited drift (no
  TTS/voice-output, no consensus forcing/dissent suppression, no authz in `mcp_server/`, no
  opaque-agent UI, no scope expansion, no credential handling, mock-first honored, no float
  arithmetic). Traced the four highest-risk invariants to their composed source: **inv 1** enforced in
  code at `ApprovalQueue.resolve` (role≠operator ⇒ `ApprovalError`) AND independently re-checked by
  `CommandBroker.approve`, with the shell `approvals:decide` handler self-authorizing nothing; **inv
  16** `approvable = (not plan_blocked) and verdict in _PASSING_VERDICTS`, derived from the REAL
  `gate@1.0` verdict `GateEngine.evaluate` renders inside `LiveGovernedFlow.begin`, and `resolve`
  refuses approve of a non-approvable item with no override path; **inv 18/10** the surface never sets
  ACCEPTED — only the flow's gate node transitions ACCEPTED and the packet pins
  `operator_disposition="pending"`; **inv 30** a genuinely thin composition (broker classification +
  real plan gate + flow), no new authority/gate/classifier. **Four NITs, all docstring/precision,
  non-blocking; two tightened this iteration:**
  - **NIT (invariant-12 citation overstated) — FIXED this iteration (comment only):** the
    `ApprovalItem` docstring and `apply_protected_decision` cited "append-only … invariant 12" for an
    in-process queue whose `resolve` replaces the map entry rather than appending. Tightened: the
    item OBJECT is immutable and re-resolve is refused (decision integrity for the surface); the
    authoritative append-only history (inv 12) is the MCP log, which this ephemeral queue does not
    itself write.
  - **NIT ("re-implements none of them" slightly overstated) — FIXED this iteration (comment only):**
    `_protected_category` re-derives a display-only protected/destructive LABEL from the broker's own
    frozensets. Docstring tightened to say it re-implements no authority/gate/classifier/lifecycle and
    that the one re-derivation is a display label, never a re-classification.
  - **NIT (reject reason):** `apply_protected_decision` passes the caller-supplied `reason` to
    `broker.reject` rather than the item's recorded `resolve_reason`; observability only (the decision
    itself is derived from the record). Recorded, accepted.
  - **NIT (record-only decide path):** `approvals:decide` returns `{recorded:true}` for a decision
    that performs nothing governed yet (U66); safe today because `approvalSnapshot` is an honest empty
    drawer so no Approve/Reject affordance renders. Flagged so U66 wires the live feed AND the
    decision routing in the SAME step. Folded into the U66 register note.
- **gate-validator (sub-step, isolated): OVERALL PASS.** Independently reproduced every count in its
  own context (`994 passed` Python in 196.44s / `132` terminal JS / `35` apps/desktop; `node --check`
  clean on all four shell files; the two new Python files alone `20 passed`). **Mutation-proved
  invariant 1**: recorded the baseline SHA-256 of `operator_surface.py`, disabled the operator-role
  guard in `ApprovalQueue.resolve`, and saw exactly the four invariant-1 authority assertions fail
  (worker/conductor resolve, the protected-action worker-resolve leg, and the integration worker-approve
  leg) with 16 others still green, then restored the file **byte-identical (SHA-256 re-verified)** and
  deleted the backup. Confirmed invariant 16 (`approvable` derived from the REAL
  `GateEngine.evaluate(define_gate("plan",…))` verdict in `LiveGovernedFlow.begin`; `resolve` refuses
  approve of a non-approvable item with no override branch), the invariant-1 pause over a **live
  loopback MCP server** (no artifact ACCEPTED before approval), §4 composition (no gate/classifier/
  lifecycle defined), badge honesty (Python derives; JS recomputes and ignores an inflated
  `badge_count: 99 → 1`; fail-closed empty on malformed), decision integrity (`apply_protected_decision`
  derives from `item.decision`, refuses a contradicting supplied decision), mock-first (no
  `subprocess/socket/urllib/http/Popen` in `operator_surface.py`, no `require/child_process/net/http/
  fetch/spawn/exec` in `approval-drawer.js`; packet leg `mock`; shell records-only, no self-authorization),
  the four frozen canonical hashes (`6D3FD03B/8C9B7240/668089B5/CC414372` all match), and
  `config/live_operation.json` gitignored/untracked. Housekeeping: mutated file restored byte-identical,
  temp backup removed, no lingering test/background processes (pytest foreground; MCP fixtures tear down
  via `srv.stop()`). **One owned reservation — U66** (disclosed carry, NOT a gate failure): the live
  in-process `ApprovalQueue` snapshot is not yet delivered over read-only IPC, so the shell renders an
  honest EMPTY drawer and `approvals:decide` only RECORDS the operator's request — the declared scope of
  a mock-first, operator-run surface, registered as U66, with the governed authority path fully
  exercised Python-side over a real MCP server. The validator explicitly notes the high-stakes
  `gate/phase-15e` itself still requires the mandatory independent confirmation at `.gate` once all
  seven sub-steps land.

## 6. Owed / deferred (honest limits)

- **U66 (new):** the shell returns an honest EMPTY approval drawer and `approvals:decide` only
  RECORDS the operator's request; delivering the live in-process `ApprovalQueue` snapshot over the
  read-only IPC channel and routing the operator's decision to the governed
  `ApprovalQueue.resolve` / `ObjectiveIntake.approve|reject` / `CommandBroker` is owed with the live
  conductor path (a later 15E wiring), like statusbar's governor feed and the conductor selection
  literals (U65).
- OP-8 §13.4 native-MCP orchestration WHILE conversing → next 15E sub-step; §13.5 voice-IN → `.voice`.
- Answering a clarification (re-submitting a clarified command) is the broker's normal path, exercised
  end-to-end in `.voice`; here a clarification can be surfaced and dismissed.
- U58 (live flow workers) carried into 15E remains open.
- The shell drawer/badge is an operator-run surface: its DATA shape is headlessly tested
  (`terminal/test/approval-drawer.test.js`), the painting is operator-verified.

**Work commit:** `6f0cb39` · **Evidence/register commit:** this commit.
