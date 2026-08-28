# PHASE 14A GATE EVIDENCE — Product UI + IPC (`gate/phase-14a`, HIGH-STAKES)
Autonomous loop iteration 19 · 2026-07-18Z · **phase-gate close** · mandatory gate-validator
(directive §9 track 14A is a high-stakes gate — independent gate-validator confirmation required).

## Objective
Close Phase 14A (directive §9 track 14A): a real Electron/xterm.js/node-pty workspace in
`apps/desktop` + `terminal/` — terminal canvas, pane create/destroy, dynamic tiling (Plan §10.2),
maximize/restore/minimize/pin, status cards, routing/artifact inspector — over **authenticated
loopback IPC** (D-IPC-01) to the existing control plane, with **UI recovery after process restart**
and **ConPTY sessions supervised by the real Node Runtime (no naked sessions)**.

Phase 14A was decomposed (directive §3.2, large phase) into five named sub-steps, one per iteration.
All five have now landed; this report closes the phase gate.

## Sub-step ledger (each self-checked, gate-validated, evidenced)
| Sub-step | Content | Work | Evidence | Verdict |
|---|---|---|---|---|
| `.ipc` | Authenticated loopback WebSocket IPC (D-IPC-01): hand-rolled RFC 6455 on Python stdlib, per-node auth + `envelope@1.0` schema validation + hmac-sha256 compute/verify, fail-closed; real shell→IPC→MCP bridge | `7eb96e3` | `PHASE14A_IPC_EVIDENCE_REPORT.md` | PASS (sub-step) |
| `.shell` | Product Electron/xterm/node-pty scaffold: session registry (append-only, byte-exact scrollback), ConPTY session-manager with fail-closed supervised admission (no naked sessions), deterministic pane/window model, Node IPC client mirroring `client.py`, `IpcSupervisor` | `16448bb` | `PHASE14A_SHELL_EVIDENCE_REPORT.md` | PASS (sub-step) |
| `.tiling` | Plan §10.2 pane-layout policy + geometry (`tiling.js`): P0..P4 priority classes, near-square grid w/ P0/P1 double cells, visible cap, status-card rail, the §10.2 hard rule (P1 never auto-collapsed), 250 ms membership-gated relayout | `58dade9` | `PHASE14A_TILING_EVIDENCE_REPORT.md` | PASS (sub-step) |
| `.inspector` | Plan §10.3 routing/artifact inspector, read-only over D-IPC-01: per-task artifacts-published (real), gate chain reconstructed from decision entries (derived), context-routed reported unreadable (honest); LIVE read of a real seeded MCP server | `9830768` | `PHASE14A_INSPECTOR_EVIDENCE_REPORT.md` | PASS (sub-step) |
| `.recovery` | UI recovery after control-plane/process restart: pure recovery state machine (fail-closed admission, teardown on loss, re-admit only on re-verify, monotonic epoch), pure session reconstruction (no naked re-spawn), atomic durable log, observable banner; **LIVE gateway kill+restart** | this iteration | `PHASE14A_RECOVERY_EVIDENCE_REPORT.md` | PASS (sub-step) |

## Gate exit criteria (directive §9 table 14A) — disposition
- **Real Electron/xterm/node-pty workspace (canvas, pane create/destroy, tiling §10.2, max/restore/
  min/pin, status cards, inspector):** DELIVERED as product code in `apps/desktop` + `terminal/`.
  The pane/window model, tiling policy/geometry, session lifecycle, and inspector data model are pure
  and headlessly tested; the rendered Electron surfaces are operator-run metrics (§6 substitution,
  `apps/desktop/RUN_ON_WINDOWS.md`) — not claimed as observed. **Approval-queue drawer:** the voice
  Permission Broker approval queue exists and is tested (Phase 12); its dedicated shell *drawer*
  surface is deferred with the other operator-run GUI surfaces — recorded, not faked.
- **Authenticated loopback IPC (D-IPC-01, schema-validated envelopes):** DELIVERED (`.ipc`), D-IPC-01
  CLOSED by delegation; cross-language proven Node client ↔ Python gateway; real bridge to MCP.
- **UI recovery after process restart:** DELIVERED (`.recovery`) — fail-closed recovery state machine +
  session reconstruction, proven by a LIVE gateway kill+restart through the real IPC client.
- **ConPTY sessions supervised by the real Node Runtime (no naked sessions):** ENFORCED at the
  governance layer — `SessionManager.spawn` refuses a session without a node binding and a verified
  supervisor admission, kills a refused/orphaned PTY, and tears all sessions down on channel loss.
  OS-level pid→JobObject containment from the Node shell is NOT yet wired (U25/U26, disclosed) — the
  kernel-level kill-on-close containment remains the Node Runtime's (Phase 3/10, enforced there).
- **Re-verify U9 with a real console TUI in a pane:** **DEFERRED** (gate-validator R1) — requires a
  live window + a real coding TUI (OpenCode / track 14C), impossible in this headless session.
  Tracked: `docs/HARDENING_BACKLOG.md` U9, `UNRESOLVED_ISSUE_REGISTER.md`. This is the one listed
  criterion not met, and the reason the gate closes **PASS_WITH_RESERVATIONS**, not clean PASS.

## Mandatory independent gate-validator (high-stakes)
**VERDICT: PASS_WITH_RESERVATIONS** (isolated context, all commands re-run independently). The
load-bearing recovery governance logic is correct, fail-closed, and proven by real assertions plus a
genuine multi-process live test; the full 14A gate holds. Observed tallies: **131 JS pass / 0 fail /
0 skipped** (live tests ran), **367 pytest pass** (incl. `test_ipc_gateway.py` 9/9), 4 backward-compat
supervisor tests unchanged, all `node --check` clean, `docs/canonical/` untouched. Reservations
(all pre-existing/documented, none a regression): **R1** U9 real-TUI re-verify deferred (the sole
unmet listed criterion); **R2** OS-level containment from the Node shell deferred (U25/U26); **R3**
GUI operator-run substituted, not observed (§6); **R4** benign count drift. No GUI-substitution
overclaim found.

Precedent: high-stakes gates P3A and P11 also closed **PASS_WITH_RESERVATIONS** with documented,
non-blocking reservations — consistent with this disposition.

## spec-auditor (substantive new `.recovery` code)
**CLEAN with 2 MINOR, both FIXED + pinned this iteration** (atomic persist; explicit
`IPC_ALLOW_FIXED_CRED` opt-in for the recovery-model credential shim). All at-risk invariants hold
(I-2, I-16/fail-closed, I-12, I-27, I-7/I-M2, I-20, §2.2, determinism). No drift / certainty-inflation.

## Delegated decisions closed by this gate
- **D-IPC-01 CLOSED** (loopback WebSocket, schema-validated envelopes) — already recorded at `.ipc`
  (owning phase 14A); this gate confirms it in production use across all five sub-steps.
- **D-UI-01 = Electron** — ratified at `gate/phase-1` (spike, no kill criteria); 14A builds the real
  Electron product on that ratification. No re-open.

## Substitutions (loop directive §6) — carried to the final product report
- Electron/xterm/node-pty GUI surfaces are operator-run metrics; all governance-bearing logic beneath
  them is headlessly tested (incl. two LIVE subprocess proofs: the inspector read of a real seeded MCP
  server, and the recovery gateway kill+restart). No rendered behaviour claimed as observed.
- Frontier/local adapters remain mock for the build (prohibition §2.4); 14A is provider-agnostic
  shell + IPC, so no live adapter is exercised here (that is tracks 14B/14C/14E).

## Open items carried past the gate (honestly recorded, not failures)
- **U9** — real console-TUI re-verify in a pane (R1; needs 14C + live window).
- **U25** — IPC→MCP per-node credential broker (gates any IPC WRITE; the inspector + recovery paths
  are read-only / control-only and do not need it).
- **U26** — OS pid→JobObject containment driven from the Node shell (governance gate enforced now;
  kernel-level containment is the Node Runtime's, Phase 3/10).
- **U27/U28** — durable `gate@1.0` store + `ScopedContext` serialization so the inspector shows native
  gate verdicts and real routed context (currently derived / declared-unreadable, honestly).

## Test totals (whole repo)
- JS: **131 passed / 0 failed / 0 skipped** (`node --test terminal/test/*.test.js
  apps/desktop/test/*.test.js`) — terminal 104, apps/desktop 27; 3 LIVE subprocess tests
  (2 inspector + 1 recovery) ran, not skipped.
- Python: **367 passed** (`py -3.12 -m pytest tests/ -q`).

## Gate verdict
**`gate/phase-14a` — PASS_WITH_RESERVATIONS.** All five sub-steps landed and evidenced; mandatory
high-stakes gate-validator confirmed independently; spec-auditor CLEAN (MINORs fixed). Reservations
R1–R4 are documented and non-blocking (R1 the sole deferred listed criterion, tracked). The product
shell + authenticated IPC + supervised sessions + UI recovery are real and headlessly proven; the
rendered surfaces are honest operator-run metrics.

## Commits
Work commit (source) → this evidence/register commit (carries the work hash) → **tag `gate/phase-14a`**
→ loop-state commit. Two-commit convention.

## Next
`phase-14b` — first live frontier adapter (exactly ONE provider = Claude Code, per OP-4/OP-5). Entry
condition: `LIVE_OPERATION_AUTHORIZED` enforced config must exist first (fail-closed, roster/profile
loader, register row OP-4, scoped `{provider: claude_code, terminals: 1}`); R8 ToS verification
recorded before the first live call; the adapter invokes the host's already-authenticated `claude`
CLI and never handles the credential (§2.2 stands).
