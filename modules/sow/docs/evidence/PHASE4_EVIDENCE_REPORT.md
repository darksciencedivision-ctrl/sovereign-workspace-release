# PHASE 4 EVIDENCE REPORT — First Conductor Adapter
Autonomous loop iteration 5 · 2026-07-17Z · gate: `gate/phase-4`

## Objective
First conductor adapter per Buildout Directive §5 Phase 4 / Plan §7-P4, §12.2: loads the
conductor files, runs the conductor loop, holds no credential; passes the adapter contract
conformance suite; I-X3 one-terminal-per-subscription enforced; session resume surfaced.
Backend = deterministic mock reasoning model (live providers prohibited, §2.4).

## Source state
Tags through `gate/phase-3a`; freeze `--check` clean throughout. `next_step: phase-4`.

## Files
- **Work commit `78559aca`:** `adapters/base/{contract,mock_backend,__init__}.py`;
  `adapters/conductor/{adapter,bootstrap,__init__}.py`; `adapters/__init__.py`;
  `node_runtime/supervisor/subscription_governor.py`; `control_plane/profiles/loader.py`;
  `mcp_server/{memory_service,server}.py` (get_content op); 2 test files.
- **Remediation commit `35b179d8`:** F1/F2 fixes + strengthened tests.

## Exit criteria — met, mapped to code + test
- **Loads conductor files:** `ConductorAdapter._load_conductor_files` reads all 12
  operator-authored files FROM MCP (`get_content`), in the canonical declared order
  (`CONDUCTOR_FILE_ORDER`, matching Handoff §2.10.4 exactly), BEFORE it can act. The adapter
  has no `conductor_dir` — MCP is its only context source (invariant 8). Fails closed on a
  missing ref or if `run_cycle` is called before load. Tests: order preserved; **12
  get_content calls in order** (strengthened proof); missing-ref fail-closed; act-before-load
  refused.
- **Runs the conductor loop:** `run_cycle` drives the deterministic mock backend and records
  the decision in MCP as a **CANDIDATE** proposal (conductor proposes, never self-promotes —
  invariant 10). Test reads it back.
- **Holds no credential:** `holds_provider_credential()` is False; `AdapterContext` carries
  only references (`mcp_credential_id`, `subscription_ref`), never a provider secret;
  `export_session_state` keys are allowlisted with no credential material (test asserts the
  key set + absence of secret substrings).
- **§12.2 conformance:** schema-valid artifacts (store validates memory@1.0 on publish);
  context via MCP only (structural + call-count proof); resume/state export (secret-free);
  naked-launch refusal (I-C1); eligibility flags honored — the fail-closed profile loader
  excludes the frontier conductor from the offline profile (I-D2). Broker-mediation leg is a
  Node-Runtime/Phase-5 concern (F5 NOTE) — re-checked at Phase 5.
- **I-X3 one-terminal rule:** the `SubscriptionGovernor` is wired into `start()`/`close()`;
  a second terminal on one subscription is refused, an unregistered subscription fails
  closed, and succession (release→acquire) works. Tests drive it through the adapter.
- **Session resume surfaced:** `get_context_status` (loaded/expected/ready) + `export_session_state`.

## Independent review (standard-stakes: validator + spec-auditor)
- **gate-validator: PASS_WITH_RESERVATIONS.** Ran the suite (194 → 197 post-fix),
  confirmed load-order, fail-closed, no-credential, I-X3 wiring, no Phase-5 smuggling, freeze
  clean, and that the new `get_content` op is policy-gated (I-M2, no bypass). Reservations:
  R1 subscription leak on load failure → **fixed (F2)**; R2 mock decision content-name-seeded
  → recorded (revisit with real backend).
- **spec-auditor: FINDINGS 1 MAJOR / 2 MINOR / 2 NOTE.** Dispositions:
  - **F1 MAJOR — FIXED:** `get_content`/`get_head` returned any tier — a `private_node`
    entry could be read by another same-project node. Added `policy.authorize_read_entry`
    enforcing tier ownership (invariant 9); both direct-read paths use it; pinned by a
    regression test (node B denied A's private bytes; A allowed).
  - **F2 MINOR — FIXED:** governor-terminal leak on load failure (start now releases on
    failure; pinned).
  - **F3 MINOR — FIXED:** context-via-MCP now proven by counting the 12 `get_content` calls.
  - **F4 NOTE — addressed:** export-state key allowlist assertion.
  - **F5 NOTE — recorded:** broker-mediation conformance leg deferred to Phase 5 (re-check there).
  - Verified CLEAN by the auditor: holds-no-credential genuinely true; load-order enforced
    (tuple, not dict luck); worker cannot publish conductor_file (operator-only, confirmed
    against the authority); I-X3 governor race-free under its lock; profile loader fail-closed.

## Substitutions (loop directive §6)
Mock reasoning backend stands in for the fable-5 frontier model (no provider network use);
the governed conductor path (MCP file loading, decision recording, I-X3, profile eligibility)
is real code. Bootstrap/mock credentials stand in for Sovereign-issued node credentials
(issuance handoff is later-phase).

## Deviations / carried
- ruff unavailable (pip out of scope); code typed + stdlib-first.
- Carried: broker-mediation conformance leg → Phase 5; mock decision quality → real-backend
  phase; U6/U14/U15 unchanged.

## Gate verdict
**PASS.** All Phase 4 exit criteria met on machine evidence from the remediated code; the
one MAJOR review finding (tier-isolation gap on by-id reads — a real authority-layer defect)
fixed with a pinning test before closure; the new read op is policy-gated (I-M2). 197/197 tests.

## Commits
Work `78559aca` → remediation `35b179d8` → this evidence/register commit (tagged `gate/phase-4`).

## Next phase
`phase-5` — conductor + two workers end-to-end: capability-based assignment via the
Scheduler, one artifact routed CANDIDATE→gate→ACCEPTED, zero manual transcript routing,
every hop provenanced; plan gate + acceptance packet. (Broker-mediation conformance leg
re-checked here.)
