# PHASE 3A EVIDENCE REPORT — MCP Shared-Memory Foundation (MVP-foundational)
Autonomous loop iteration 4 · 2026-07-17Z · gate: `gate/phase-3a` · **mandatory high-stakes gate**

## Objective
The Sovereign MCP shared-memory foundation per Buildout Directive §5 Phase 3A / Plan
v1.0.1 §9.4–9.6, §9.10–9.11: a separate loopback server, per-node auth, resource/tool
catalogs with scope enforcement in the control plane (not MCP), server-enforced memory
lifecycle, provenance on every write, content-addressed artifacts, immutable append + CAS
heads with explicit conflict objects, fail-closed disconnect, conductor-replacement
support, and **no authorization logic inside MCP** (I-M2). This is the MVP-foundational
gate (D-MVP-01).

## Source state
Tags through `gate/phase-3`; freeze `--check` clean throughout. `next_step: phase-3a`.
Design pass (concurrency/fencing) done before coding per directive §2.6.

## Files
- **Work commit `e2b9d8aa`:** `persistence/{cas,store,__init__}.py`; `control_plane/policy.py`;
  `mcp_server/{lifecycle,auth,protocol,memory_service,server,run_server,__init__}.py`; 4 test files.
- **Remediation commit `96669f1b`:** 5 MAJOR + minor fixes from the mandatory review; new
  cross-process race test + worker; remediation regression suite.
- **This commit:** direct CAS-traversal unit test (R1), `.mcp.json` (§2.5), evidence + registers.

## Architecture (the separation that makes I-M2 real)
- **`persistence/`** (D-PERSIST-01): SQLite WAL store + content-addressed blob store. Data
  integrity only — immutable memory versions, provenance schema-enforced at the write
  boundary, atomic `commit_version` (version-number assignment + append + CAS head advance
  under one `BEGIN IMMEDIATE` + process write lock). No role logic.
- **`control_plane/policy.py`** — THE authority (deny-by-default): workers publish CANDIDATE
  only + own-entry transitions; promotion is gate/operator-only (I-M6); directive/
  conductor_file not worker-writable; reads project-scoped; health operator/conductor-only.
- **`mcp_server/`** — access/transport over a loopback socket (separate OS process, 127.0.0.1
  only). Authenticates identity, then delegates EVERY allow/deny to the policy. A structural
  test asserts no role literals live in `server.py` or `memory_service.py`.

## D-MCP-03 VERDICT (directive §5 requires this be recorded)
**Mechanism: immutable append + CAS head pointers — ACCEPTED and verified.** The read-
compare-append-advance is atomic under `BEGIN IMMEDIATE` (SQLite RESERVED lock) + a process
write lock, correct across both threads and separate OS processes. A losing concurrent
writer's version is **preserved as a fork** off its ancestor, the head stays on the single
winner, and an explicit `conflict_record` lists both versions — never a silent last-write-
wins (invariant 13). Evidence: `test_mcp_cross_process_race.py` (N real OS processes racing
one head → exactly one winner, N−1 conflict records, all versions preserved, `verify()` ok),
stress-looped 10× non-flaky; the independent validator ran a counterfactual (removing
`BEGIN IMMEDIATE` in a scratch copy) and confirmed the test then FAILS — i.e. the test is
load-bearing, not decorative. **D-MCP-03 closed by operator-delegation (ruling 2026-07-16).**

## Commands / tests
`py -3.12 -m pytest tests/ -q` → **169 passed** on py 3.12.10 (168 at remediation + 1 R1
unit test). Cross-process race 10×/8× non-flaky. All 9 Phase 3A gate criteria have live
passing tests (restart durability, independent/scoped context, provenance-on-every-write,
candidate/accepted separation + no self-canonization, directive-not-worker-writable,
conductor-replacement, disconnect fail-closed + uncorrupted store, concurrent-writer
conflicts, no-authz-in-MCP structural guard).

## Independent review (mandatory high-stakes)
- **gate-validator pass 1: PASS_WITH_RESERVATIONS.** Ran the suite + its own thread and
  5-process fencing probes; confirmed cross-process correctness. Flagged: private-tier read
  leak (Reservation 1) + owed closure artifacts.
- **spec-auditor: FINDINGS 5 MAJOR / 4 MINOR / 3 NOTE** — the CAS fence itself correct, but
  gate-blocking defects around it (F1 test in-process-only; F2 stale/loser reads; F3 CAS
  traversal; F4 vacuous cross-project scope; F5 connection leak).
- **Remediation** (commit `96669f1b`): every MAJOR fixed with a pinning test; private-tier
  leak fixed; minors F6/F8/F9/F12 addressed; no-authz guard extended to `memory_service.py`.
- **gate-validator pass 2 (on remediation): PASS_WITH_RESERVATIONS, no regressions, no new
  defects.** Independently reran the suite (168/168) + race 10×, and ran a counterfactual
  fence-removal in a scratch copy proving the cross-process test is load-bearing.
  Remaining reservations → dispositions:
  - R3 `.mcp.json` (§2.5) → **added this commit** (records the loopback server; U6 caveat noted).
  - R4 evidence report + gate tag → **this document + tag**.
  - R1 direct CAS-regex unit test → **added this commit** (`test_cas_ref_traversal_and_shape_refused`).
  - R2 `format_checker` inert (jsonschema has no `date-time` checker without `rfc3339-
    validator`, which pip can't install under the network prohibition) → **recorded as a
    known no-op**; provenance *shape* is fully enforced; timestamp *format* enforcement is
    deferred until the validator lib is available (new register item U14).
  - R5 F5/F6 correct in code but not asserted by a regression test → accepted; low-risk
    operational hardening, revisit at Phase 13.

## Substitutions (loop directive §6)
- **MCP SDK → stdlib loopback JSON protocol** (pip out of network scope): transport recorded
  as **U6**; `.mcp.json` and `protocol.py` state plainly this is not the MCP wire protocol;
  swapping in the SDK later is an adapter change behind `mcp_server`. Nothing is claimed as
  MCP-SDK-compliant.
- Mock/bootstrap credentials stand in for Sovereign-issued node credentials (issuance
  handoff is a Phase 4 adapter concern); the governed memory path under test is real code.

## Deviations / carried
- ruff unavailable (pip out of scope); code typed + stdlib-first.
- Carried: F10 approver≠author (invariant 18, "no node solely judges its own work") is a
  reasoning-phase concern → P7/P8 (new register item U15). U6 transport; U14 timestamp-format
  enforcement.

## Gate verdict
**PASS.** All 9 Phase 3A must-pass criteria met on machine evidence from the shipped
(remediated) code; the mandatory concurrent-writer/CAS fencing is correct and its test
proven load-bearing across real processes; every MAJOR review finding fixed with a pinning
test before closure; no authorization logic inside MCP (structural guard). **D-MCP-03 =
immutable append + CAS heads** and **D-PERSIST-01 = SQLite WAL + content-addressed store**
close by operator-delegation (ruling 2026-07-16).

## Commits
Work `e2b9d8aa` → remediation `96669f1b` → this evidence/register/`.mcp.json` commit
(tagged `gate/phase-3a`).

## Next phase
`phase-4` — first conductor adapter (loads the 12 conductor files via MCP in declared
order, runs the conductor loop, holds no credential; backend = mock reasoning model;
contract-conformance suite; I-X3 governor with mock subscription refs).
