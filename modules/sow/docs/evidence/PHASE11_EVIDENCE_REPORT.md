# PHASE 11 EVIDENCE REPORT — Persistence & Conductor Succession
Autonomous loop iteration 12 · 2026-07-17Z · gate: `gate/phase-11` · **MANDATORY high-stakes gate**

## Objective
Persistence & conductor succession per Buildout Directive §5 Phase 11 / Plan §7-P11, §19.1
(I-CS1): serialize the conductor's operating state to MCP; kill mid-project → Resume→Select
any model → reconstruct with ZERO loss. Exit: kill-the-conductor test passes with zero project
loss; full workspace restart restores project; succession preserves I-X3/I-L1.

## Source state
Tags through `gate/phase-10`; freeze `--check` clean throughout. `next_step: phase-11`.

## Files
- **Work commit `3849f170`:** `control_plane/recovery/{succession,__init__}.py`;
  `tests/integration/test_conductor_succession.py`.
- **Remediation `e78fa79c`:** §19.1 staleness checklist completed (3 MAJOR).
- **R2 close `4dbb2bf3`:** version-advance-on-tracked-head detection.

## Exit criteria — met, mapped to code + test
- **Serialize full state to MCP:** `ConductorState` (tasks, nodes, open_debates, pending_gates,
  memory_heads, routing, outstanding_issues, directive_version, task_graph_version,
  current_conductor) serialized as an immutable succession_state snapshot (checkpoint@1.0
  metadata + integrity sha256 over the state; content in the append-only CAS store).
- **Kill mid-project → ZERO loss (THE acceptance test):** conductor A serializes, is killed
  (session dropped), a DIFFERENT model reconstructs from MCP — every operating-state field
  asserted equal field-by-field on a realistic non-empty state; only the conductor SELECTION
  changes (reason=succession). The model session is replaceable; the project memory is not.
- **Full workspace restart restores project:** snapshot survives a real server stop + fresh
  `MCPServer` over the same on-disk store; reconstruct succeeds.
- **§19.1 staleness checklist (the anti-loss mechanism) — complete and BLOCKING:** integrity;
  directive-version match (read from the integrity-covered state); **task-graph version match**;
  **event-tail currency** (ACCEPTED work landing after the snapshot is detected via an entry-id
  diff, PLUS in-place version advances on tracked heads via `memory_heads_current`);
  node-registry presence; unresolved-conflict scan; wall-clock age (advisory bound). Every item
  is blocking (any mismatch ⇒ reconciliation before assignment); `_open_conflicts`/`_accepted_after`
  fail closed on error.
- **Succession preserves I-X3:** `SuccessionManager.perform_handoff` OWNS the release-before-
  acquire ordering (predecessor terminal released before the successor claims the
  one-per-subscription slot); the test drives the succession code and proves the ordering matters.
- **Cadence (U11):** `should_snapshot` — major event OR bounded interval (default 5 min).

## Independent review (MANDATORY high-stakes: validator + spec-auditor + re-validation)
- **gate-validator pass 1: PASS_WITH_RESERVATIONS.** Zero-loss round-trip genuine and
  field-by-field; restart crosses the real persistence boundary; but the §19.1 checklist was
  incomplete.
- **spec-auditor: FINDINGS 3 MAJOR / 6 MINOR / 3 NOTE** — all in the staleness checklist (the
  mechanism between succession and project loss): M1 task-graph-version match missing; M2 age
  check was an unarmed wall-clock bound, NOT "vs event-log tail" (post-snapshot work would be
  silently lost); M3 I-X3 ordering not owned/tested by the succession code.
- **Remediation `e78fa79c`:** all 3 MAJOR fixed + report.ok made to block on all §19.1 items +
  fail-closed error paths + integrity-covered directive + insertion-order `latest()` +
  schema-drift tolerance; 5 new failing-branch tests.
- **gate-validator pass 2 (re-validation): PASS_WITH_RESERVATIONS — gate CAN CLOSE.** Ran the
  suite (305) + succession tests (12); **mutation-verified** each fix is load-bearing (reverting
  event-tail/task-graph/handoff each makes its test fail); confirmed no happy-path false positive,
  no regression, scope/freeze clean. Two fail-safe reservations: R1 (event-tail assumes
  memory_heads == complete ACCEPTED head set; a gap fails TOWARD reconcile, never silent loss) →
  **U23 recorded**; R2 (version-advance on a tracked head) → **FIXED this iteration**
  (`memory_heads_current` + test).

## Substitutions (loop directive §6)
Mock conductor models (claude-mock → fable-mock) stand in for real frontier models; the
succession machinery (serialize, MCP persistence, staleness checklist, reconstruct, I-X3
handoff) is real code. The "kill" is a real dropped MCP session; the restart is a real
stop + fresh server over the same store.

## Deviations / carried
- ruff unavailable (pip out of scope); code typed + stdlib-first.
- Carried: U11 cadence default (major events + 5 min, tunable); U23 (new: event-tail assumes
  memory_heads is the complete ACCEPTED head set — confirm/tune before real multi-entry
  projects; fails safe toward reconciliation).

## Gate verdict
**PASS.** Kill-mid-project zero loss (field-by-field, realistic state); full-restart restores
project; the §19.1 staleness checklist is complete and blocking with fail-closed error paths;
I-X3 succession ordering owned by the succession code; all 3 MAJOR review findings fixed and
mutation-verified before closure; R2 additionally closed. 305/305 tests.

## Commits
Work `3849f170` → remediation `e78fa79c` → R2 close `4dbb2bf3` → this evidence/register commit
(tagged `gate/phase-11`).

## Next phase
`phase-12` — Parakeet voice input (STT-only): full VoiceAdapter interface, propose-never-execute
command safety through the real Permission Broker, transcribe-then-discard + TTL diagnostic
retention, typed/voice control-event equivalence. Engine = mock STT by default (real Parakeet
only if NVIDIA GPU + WSL + NeMo present; else mock behind the same interface, record U1/U2 open).
All §2.8 voice acceptance tests run against the broker path.
