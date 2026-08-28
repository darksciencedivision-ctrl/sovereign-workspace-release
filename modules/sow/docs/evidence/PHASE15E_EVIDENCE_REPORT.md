# PHASE 15E — EVIDENCE REPORT (phase gate `.gate`, HIGH-STAKES)

**Work unit:** `phase-15e.gate` (7th and final sub-step of the Phase 15E decomposition:
`.picker` → `.spawn` → `.conductor-pane` → `.objective` → `.voice` → `.recovery` → **`.gate`**)
**Track:** Phase 15E — Node-launcher UI + visible assembled run (directive §11, OP-7 §12, OP-8 §13, OP-9 §14).
**Date:** 2026-07-24 · **Iteration:** 57 · **Status:** **PASS_WITH_RESERVATIONS** (HIGH-STAKES phase gate — mandatory independent gate-validator).
**Tags on this closure:** `gate/phase-15e`, then the Phase-15 terminal `product/live`.
**Governing docs:** `AUTONOMOUS_BUILD_DIRECTIVE.md` §11 (track 15E), §12 (OP-7 amendment: per-pane
picker + conductor-first + operator command surface), §13 (OP-8: conductor is a live conversational
CLI; voice-IN; TTS flagged/owed), §14 (OP-9: live-terms confirmed), loop protocol §3, substitution
rules §6, honesty §10.4. Precedence: v2.4 spec → Architecture Plan v1.0.1 → Buildout Directive.

`.gate` is the aggregate **closure** of Phase 15E. It adds **no production code** — its job is to
confirm the whole of 15E holds, on independently reproduced evidence, and to close the high-stakes
gate. All six implementation sub-steps landed with their own PASS evidence + gate-validator +
spec-auditor; this report rolls them up and records the phase verdict.

---

## 1. Sub-step ledger (all six landed, each independently reviewed)

| Sub-step | Work commit | Evidence report | Sub-step verdict |
|---|---|---|---|
| `.picker` — per-pane model picker + VRAM residency planner (inv 22; live `ollama list` is a host-enumerated INPUT) | `fb6a1dd` | `PHASE15E_PICKER_EVIDENCE_REPORT.md` | PASS · validator PASS · auditor CLEAN (recovered a fabricated/stale prior report; re-ran fresh) |
| `.spawn` — governed node spawn from a picker selection (inv 2/22, I-X3=2, D-LOOP-1) | `b1aac00` | `PHASE15E_SPAWN_EVIDENCE_REPORT.md` | PASS · validator PASS · auditor CLEAN (MINOR-1 fail-closed defect fixed pre-commit) |
| `.conductor-pane` — governed conductor-first interactive CONDUCTOR pane (OP-8 §13, inv 3/I-CN1, I-X3) | `15b8b4a` | `PHASE15E_CONDUCTOR_PANE_EVIDENCE_REPORT.md` | PASS · validator PASS · auditor CLEAN |
| `.objective` — operator command surface: objective intake + unified approval-queue drawer (OP-7 §12.5, inv 1/16) | `6f0cb39` | `PHASE15E_OBJECTIVE_EVIDENCE_REPORT.md` | PASS · validator PASS · auditor CLEAN |
| `.voice` — voice-IN to the live CONDUCTOR (OP-8 §13.5, inv 24/25/26, I-V1..V3; NO TTS) | `8bcbfa1` | `PHASE15E_VOICE_EVIDENCE_REPORT.md` | PASS · validator PASS · auditor CLEAN |
| `.recovery` — conductor-first LAYOUT restart recovery (§9 track 14A, OP-7 §12.4, inv 2/1/3/12) | `66fe2bf` | `PHASE15E_RECOVERY_EVIDENCE_REPORT.md` | PASS · validator PASS · auditor CLEAN |

## 2. Phase 15E exit criteria (§12 consolidated list + §13 OP-8) and verdicts

| # | 15E exit criterion | Verdict | Where proven (headless) / substitution |
|---|---|---|---|
| 1 | **Conductor-first labeled pane** — pane 1 auto-spawns as CONDUCTOR, model badge = current selection (fable-5 or recorded fallback), pinned by default; succession (Resume→Select) reachable from its chrome | **PASS** | `.conductor-pane` (`node_runtime/supervisor/conductor_pane_spawn.py`, `terminal/compositor/conductor-pane.js`) + `.recovery` (`terminal/recovery/layout-reconstruct.js` emits the pinned CONDUCTOR pane-1 UNCONDITIONALLY — structural, not data-driven). Badge shows the SELECTION label, `verified:false` until an `ExecutingEvidence`-backed live reply (inv 3, no fabricated checkpoint). |
| 2 | **Per-pane picker with live Ollama enumeration + residency states** (resident / loading / awaiting-eviction), swaps visible, never mid-generation (inv 22) | **PASS** | `.picker` (`control_plane/nodes/pane_picker.py` pure data model; `ollama list` enumerated live by the operator-run `tools/live/enumerate_pane_picker.py`, fed as INPUT; residency annotated per model; frontier options fail-closed/greyed-with-reason via `LiveAuthorization`). Rendered picker panel = operator-run metric (§6). |
| 3 | **One attended node + one autonomous node on the SAME subscription** (allowance=2 proof, I-X3 raised to 2 by OP-6, governor-enforced) | **PASS** | `.spawn` + `.conductor-pane`. Governor-enforced: `test_ix3_second_conductor_pane_on_same_subscription_allowed_third_refused` and `test_ix3_third_frontier_terminal_refused_through_coordinator` reach `active_count==2` then raise `SubscriptionLimitExceeded`; `test_attended_and_autonomous_both_governed_same_authority` confirms attended mode grants **no** extra authority (inv 1). |
| 4 | **Objective entered in UI → decompose → assign → CANDIDATE → gate → conductor synthesis → acceptance packet visible in the Inspector** | **PASS (logic) / operator-run (render)** | `.objective` (`control_plane/orchestration/operator_surface.py`: `ObjectiveIntake.submit` decomposes+gates then STOPS; assignment only after operator `approve` → `run_waves`+`finish` → CANDIDATE → gates → conductor synthesis → acceptance packet). Proven end-to-end over a REAL MCP server in `tests/integration/test_objective_intake.py`. Live model legs are mock-first (§2.4/§10.4); Inspector render is operator-run (§6). |
| 5 | **Approval-queue exercised at least once** (plan gate; one unified drawer for plan / protected_action / clarification; badge derived from pending) | **PASS** | `.objective` (`ApprovalQueue`; `approvable` DERIVED from the real `gate@1.0` verdict, never asserted; `resolve` operator-only [inv 1] and refuses approving a gate-failed plan [inv 16, no override path]; badge RECOMPUTED so an inflated payload can't drive it). `terminal/compositor/approval-drawer.js` pure render model, fail-closed. |
| 6 | **Restart recovery restoring the conductor-first layout** (panes reattaching) | **PASS (logic) / operator-run (render)** | `.recovery` (`terminal/recovery/layout-reconstruct.js` + `apps/desktop/recovery-store.js`): the pinned CONDUCTOR pane-1 is rebuilt from the operator SELECTION even on a null/corrupt snapshot; NO worker pane reattaches to a live session on boot (inv 2 — `reattach:false`/`admitted:false`), admission SHUT until the governed channel re-verifies (no naked session in the gap). |
| 7 | **(OP-8 §13) Live CONDUCTOR chat pane:** open the app → land in a live CONDUCTOR chat → type OR speak a request → watch it farm work to the other model CLIs and synthesize back → inject a file mid-conversation → keep talking, no file-load/restart | **PASS (governed path) / operator-run (live conversation)** | `.conductor-pane` builds the governed interactive pane (real `claude` CLI in a ConPTY, fable-5 selection, launched only through supervisor+governor, credential-scrubbed env); `.voice` adds voice-IN on the **same command path as typing** (`voice_bridge/conductor_voice.py`: typed/voice equivalence; protected/destructive verbs PROPOSE via the real CommandBroker, never auto-execute — inv 25). The live interactive conversation + orchestration-while-conversing are operator-run metrics (§6, like the Phase-1 spike); the governed data path is headless-tested. **Voice-OUT/TTS is NOT built** — I-V2/D-VOICE-02 stands; owed-by-operator-decision per OP-8 §13.6. |

## 3. Independent verification (this closure, run FRESH in the foreground)

**Test suites — reproduced by me and independently by the gate-validator in an isolated context:**

```
py -3.12 -m pytest tests/ -q      → 1011 passed, 0 failed, 0 skipped   (199.16s; 61 pre-existing jsonschema deprecation warnings only)
node --test terminal/test/*.test.js       → tests 155  pass 155  fail 0
node --test apps/desktop/test/*.test.js   → tests 38   pass 38   fail 0
```
Total: **1011 Python + 193 JS = 1204 tests green, 0 skipped.**

**gate-validator (MANDATORY, high-stakes, isolated context): OVERALL PASS_WITH_RESERVATIONS.**
Independently reproduced 1011 / 155 / 38. Confirmed: tags (`gate/phase-15a..15d` present,
`gate/phase-15e` + `product/live` absent); all 6 sub-step work+evidence commits; conductor-first is
structural (pinned pane-1 even on null snapshot); voice routes protected/destructive to the broker
and exposes NO speech-out method; objective assigns nothing until operator approve and `approvable`
derives from the real gate; allowance=2 governor-enforced; owed items (U58, U63–U68) disclosed in the
register; **no** live model/subprocess/socket/urllib call in any new 15E product source (mock-first);
`mcp_server/` untouched (no authz added); no credential handling; `config/live_operation.json`
untracked/gitignored; **the 4 frozen canonical SHA-256 match `PHASE0_FREEZE_MANIFEST.json`
(6D3FD03B / 8C9B7240 / 668089B5 / CC414372)**; no float. Its one mutation (manifest recompute) was
restored byte-identical; working tree clean. **Reservations (disclosed-and-owed, non-blocking):**
(R1) the end-to-end live assembled run through the rendered GUI is the §6 operator-run substitution —
governance LOGIC is proven headless against the real MCP server, but Inspector render + live model
runs + rendered picker are operator-run metrics; (R2) six live-feed IPC wirings are OWED
(U58/U63/U64/U65/U66/U67/U68), all disclosed with owed-FIX statements — the shell renders/records
honestly rather than fabricating a live result.

**spec-auditor (canonical-drift, isolated): CLEAN — no MAJOR/MINOR.** Traced inv 1 (operator final
authority — the shell's `approvals:decide`/`conductor:succeed`/`voice:propose` RECORD requests and
self-authorize nothing; authority stays in `ApprovalQueue.resolve`/`CommandBroker`), inv 16 (no
override of a failed gate), inv 2/29 (no naked sessions; supervisor+governor gating; recovery never
auto-attaches), inv 25 + I-V2/D-VOICE-02 (voice proposes, never executes; NO TTS method by
construction), inv 26 (transcribe-then-discard), inv 3/I-CN1 (conductor is an interface; selection
label; no fabricated executing checkpoint), I-SC1 (capability from descriptor, never name-inferred),
plus no float / no authz-in-`mcp_server` / no credential handling. **2 NITs, non-blocking:** NIT-1 —
the shell hard-codes the `fable-5` selection label as a display copy (honest today; the drift risk is
already owed as U65, fix = source it over read-only IPC like the inspector/statusbar); NIT-2 — the
record-only shell handlers return `{recorded:true}` with no identity check (safe — they mutate no
governed state; the operator-role check must remain in `ApprovalQueue.resolve`/`CommandBroker`, which
it does). Both fold into the existing owed U65/U66/U67.

## 4. Substitutions and honesty (directive §6 / §10.4 — nothing faked, nothing overclaimed)

- **Rendered GUI + live model conversation = operator-run metrics**, exactly as the Phase-1 spike and
  every prior 14A/15x GUI/live surface. The governance/data paths are headless-tested; the visible
  window, the live Inspector render, the live per-pane conversation, and the visibly-reattaching panes
  are produced by an operator run of `apps/desktop` on the Windows host.
- **Mock-first (§2.4/§10.4):** this session made NO live `claude`/`codex`/Ollama model call. No new
  15E product source imports subprocess/socket/urllib. Live legs are exercised through the governed,
  fail-closed spawn path built and gated at 15A/15B/15C/15D; running them live is an operator act.
- **OWED, disclosed, never claimed as live** (all in `UNRESOLVED_ISSUE_REGISTER.md`): **U58** live-flow
  worker legs (the live `.flow` proved a live conductor, not live workers); **U63** local coder vs
  picker-selected tag divergence; **U64** residency-completion gate before `execute()`; **U65**
  conductor badge over IPC; **U66** approval queue over IPC; **U67** voice audio → bridge over IPC;
  **U68** worker-pane chrome into the recovery snapshot. Each is the same owed live-feed pattern; the
  shell renders/records honestly (empty drawer, request-only) in the interim.
- **Voice-OUT / TTS:** NOT built. Frozen invariant I-V2 / D-VOICE-02 ("voice input only; the system
  does not talk back") stands. Per OP-8 §13.6 a spoken answer is an explicit operator reversal — it is
  **OWED-BY-OPERATOR-DECISION** (would become OP-9-TTS + a 16th track), recorded, never faked.

## 5. Prohibitions held (directive §2, unchanged)

No push / no remotes / no PRs; no credential created, read, stored, or transmitted (the CLIs use their
own host-native auth); no purchases/sign-ups; nothing modified outside the repo root; `docs/canonical/`
frozen (4 hashes verified); registers/evidence append-only; `config/live_operation.json` never
committed. D-LOOP-1 teardown: no live CLI process was spawned this unit, so none could be left running.

## 6. Delegated decisions closed by this gate (operator-delegation, ruling 2026-07-16 / OP-6/OP-7/OP-8/OP-9)

- **D-UI-01 product surface** — the node-launcher UI, per-pane picker, conductor-first pane, operator
  command surface (objective + approval drawer), and voice-IN are delivered behind the governed
  contracts; the rendered surface is operator-run. Closed on recorded evidence.
- **OP-7 §12 requirements** (per-pane picker w/ live Ollama enumeration + residency; interactive panes
  as governed MCP-attached nodes [attended vs autonomous]; conductor-first startup; operator command
  surface) — implemented and gated. **OP-8 §13** (conductor as a live conversational CLI; voice-IN;
  TTS flagged/owed) — governed path implemented; live conversation is operator-run; TTS owed.

## 7. Phase verdict

**PASS_WITH_RESERVATIONS.** All seven 15E exit criteria are met — governance/data logic proven headless
on 1204 green tests against the real MCP server, GUI/live surfaces substituted as operator-run metrics
per §6, every live-feed gap disclosed and owed (never faked). Independent gate-validator concurs
(PASS_WITH_RESERVATIONS, isolated); spec-auditor CLEAN. Precedent: P3A, P11, 14A, 15A/15C/15D all
closed PASS_WITH_RESERVATIONS on the identical substitution pattern. **`gate/phase-15e` closes; the
Phase-15 terminal tag `product/live` follows; the operator is addressed once (`FINAL_LIVE_REPORT.md`).**
