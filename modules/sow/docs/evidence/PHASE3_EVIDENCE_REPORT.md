# PHASE 3 EVIDENCE REPORT — Sovereign Node Runtime
Autonomous loop iteration 3 · 2026-07-17Z · gate: `gate/phase-3`

## Objective
Sovereign node runtime per Buildout Directive §5 Phase 3 / Plan v1.0.1 §7-P3:
directive/role/permission loaders, supervisor containment scaffold, local gate,
structured-output validation, workspace binding. Exit: a mock-model node loads
role+permissions, produces a schema-valid artifact, fails its local gate on seeded
defects, and cannot write outside its workspace.

## Source state
Tags through `gate/phase-2` present; freeze `--check` clean at start and end.
`LOOP_STATE.json` `next_step: phase-3`.

## Files changed
- **Work commit `4d099b710791a2f223581a908b1d89e2b6fd749d`:** `node_runtime/`
  (context/loaders, workspace/binding, supervisor/containment, gate/local_gate,
  mock_node, `__init__`); 17 unit + 5 integration tests.
- **Remediation commit `99d77e4e167b62f38b846ab7327435eebcd11583`:** spec-audit fixes +
  18 new hardening tests.

## Commands run (this host)
`py -3.12 -m pytest tests/ -q` → **123 passed** (105 at work commit; +18 remediation).
Phase-3 subset incl. the Job Object grandchild-kill integration test — executed, not
skipped (validator independently confirmed).

## Exit criteria — met, each mapped to code + test
- **Loads role+permissions (fail-closed):** `context/loaders.py` refuses missing dir/file,
  empty file, unparseable JSON, `permission@1.0` schema violation, non-`deny` stance,
  foreign `node_class`, and non-UTF-8 bytes (wrapped as LoaderError). Loaded bytes hashed
  for provenance pinning. 11 loader tests.
- **Schema-valid, content-addressed artifact:** local gate validates artifact metadata
  against frozen `artifact@1.0` AND recomputes `sha256(content)` == `artifact_id` and
  `size_bytes`. Tamper and schema-drift both caught.
- **Fails local gate on seeded defects:** mock node defect modes
  (invalid_artifact_schema, missing_evidence, placeholder_text) each fail a distinct
  criterion; gate is PASS-only-if-all with no override path; unknown/empty criteria fail
  closed. 12 gate tests + parametrized mock-defect integration test.
- **Cannot write outside workspace:** `workspace/binding.py` refuses absolute paths,
  `..` escapes, junction/symlink escapes (followed via `.resolve()`), reserved device
  names, NTFS ADS, drive-relative smuggling, trailing dot/space — all refused AND logged,
  with nothing written outside (verified). 12 workspace tests incl. live `mklink /J`.

## Containment enforcement — recorded honestly (directive requirement, U10)
- **ENFORCED:** process-tree kill via Windows Job Objects (`KILL_ON_JOB_CLOSE`) — the
  integration test spawns child→grandchild and proves both die on job close;
  fail-closed on assign failure. Workspace path containment at the runtime-API layer
  (all escape classes above).
- **NOT ENFORCED THIS PHASE (P10 / U10 stays OPEN):** OS-level filesystem/network denial
  for a process that bypasses the WorkspaceBinding API with raw syscalls; the
  assign-after-spawn race window (correct product pattern CREATE_SUSPENDED→assign→resume
  is a P10 hardening item). Disclosed in both module docstrings; no overclaim.

## Independent review
- **gate-validator (isolated context): PASS_WITH_RESERVATIONS.** Ran the full suite +
  the containment test itself; mapped every exit-criterion clause to code and test;
  confirmed determinism, anti-overfit, scope, freeze, and 30-invariant drift clean.
  Reservation R-P3-1: the exit wording "cannot write outside" is met at the API layer,
  not OS-level fs denial — directive-sanctioned, recorded, U10 stays open. Disposition:
  accepted; carried to P10.
- **spec-auditor (two independent passes): no BLOCKER, no MAJOR; the load-bearing
  control (workspace containment) holds under live escape probing (junctions, UNC,
  `\\?\`, cross-drive drive-relative, prefix-confusion — all refused).** Findings +
  dispositions:
  - **MEDIUM device-name fail-open (NUL/CON/COM*) — FIXED** (component screen + 9 tests);
    was: `resolve("NUL")` wrote to the null device while the node reported success.
  - MINOR Job Object docstring GC-overclaim — FIXED (docstring corrected).
  - MINOR loader UnicodeDecodeError unwrapped — FIXED (wrapped as LoaderError + test).
  - MINOR no junction test in suite — FIXED (live `mklink /J` escape test).
  - LOW trailing dot/space aliasing, NTFS ADS — FIXED (screened + tests).
  - NOTE `use_last_error` for containment diagnostics — FIXED.
  - ACCEPTED for phase scope (recorded, not fixed): `claims_cite_evidence` checks ref
    PRESENCE not resolution (ref resolution needs the 3A CAS/memory; not a §7-P3 exit
    item); `no_placeholders` uses substring match (may trip on legitimate prose
    discussing TODO — acceptable for a local gate, tighten later); assign-after-spawn
    race (P10); non-Windows test guards absent (Windows-native charter).
  - NOTE (schema owner, not this change): `artifact@1.0` makes `schema` field optional —
    a property of the frozen Phase-0 schema; the gate honors the frozen schema as-is and
    does not modify it.

## Substitutions (loop directive §6)
Mock-model node stands in for a model-backed node; the governance path under test
(fail-closed loaders, workspace binding, local gate, structured-output validation, Job
Object containment) is the real code. Seeded defect modes are the falsifiability hook,
not product behavior.

## Deviations
ruff unavailable (pip outside permitted network use); code typed + stdlib-first.

## Unresolved issues (carried)
- U10 (OS-level fs/network denial; assign-after-spawn race) → Phase 10.
- `claims_cite_evidence` real ref-resolution → Phase 3A (needs CAS/memory).

## Gate verdict
**PASS.** All §7-P3 exit criteria met on machine evidence from the shipped code; the one
MEDIUM fail-open found in review was fixed with pinning tests before gate closure; the
containment honesty requirement is satisfied (enforced vs deferred explicitly recorded).

## Commits
Work `4d099b71` → remediation `99d77e4e` → this evidence/register commit (tagged
`gate/phase-3`).

## Next phase
`phase-3a` — MCP shared-memory foundation (MVP-foundational; **mandatory high-stakes
gate-validator confirmation**): separate loopback server, per-node auth, resource+tool
catalogs, server-enforced memory lifecycle, provenance, CAS artifact store, immutable
append + CAS heads, concurrent-writer conflict test (records D-MCP-03), fail-closed
disconnect, no authorization logic inside MCP. Closes D-PERSIST-01.
