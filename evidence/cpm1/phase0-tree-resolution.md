# utc: 2026-08-26T06:27:10.6929188Z
# producer: ox-alpha master-run-order-20260826 phase0-tree-resolution

## Question
MASTER-RUN-ORDER-20260826.md Phase 0: which tree holds tools/run_phase19_gate.py and docs/loop/LOOP_STATE.json?

## Findings - read from disk this session, hashes computed this session

| path | bytes | mtimeUTC | sha256 |
|---|---|---|---|
| D:\multi model terminal app\sovereign-orchestration-workspace\tools\run_phase19_gate.py | 20918 | 2026-08-23T07:51:05Z | `8e1e36c68286f1bcd4512920b875d5665d4d4b392876f38620c01abc147a4b27` |
| D:\multi model terminal app\sovereign-orchestration-workspace\docs\loop\LOOP_STATE.json | 611654 | 2026-08-15T17:32:05Z | `981a97f42ae7dccd390eced5036bedb42e87635d07e0d31b4f048932bd5fe97b` |
| D:\Product Software\Production Workspace\modules\sow\tools\run_phase19_gate.py | 19574 | 2026-08-16T23:37:02Z | `003f54a28d843d6773c93edfdff48d576b3822ee29195786dff415ff6aeabfd0` |
| D:\Product Software\Production Workspace\modules\sow\docs\loop\LOOP_STATE.json | 611654 | 2026-08-15T17:32:05Z | `981a97f42ae7dccd390eced5036bedb42e87635d07e0d31b4f048932bd5fe97b` |

Both trees hold a Phase-19 gate runner pair. The two LOOP_STATE.json copies are byte-identical (`981a97f42ae7dccd390eced5036bedb42e87635d07e0d31b4f048932bd5fe97b`); the gate runners differ (20918 vs 19574 bytes).

## Git

- D:\multi model terminal app\sovereign-orchestration-workspace: HEAD `e6fcb89984ba50f296a1f4debb6669bfef12f996` (commit 2026-08-24T00:57:36-05:00 "docs(register): close Session 8 with N2 finding, U541 tally correction, and CU-A1 assurance residual"). status --porcelain carries 3 entries:
`
 M docs/loop/LOOP_STATE.json
?? docs/evidence/INDEPENDENT_REVIEW_WINDOWS_HOST_20260816.md
?? docs/evidence/PHASE19_UNIT10_U339_SUITE_AND_GATE.md
`
- D:\Product Software\Production Workspace\modules\sow: NOT a git repository (`git rev-parse HEAD` -> fatal: not a git repository). The enclosing Production Workspace is not a repo either (session environment reports "Is directory a git repo: no").

This HEAD matches the SOW quiescence HEAD recorded in Gate 8a's note (`e6fcb899`), so the "SOW upstream" inspected during CP-M1 Band 0 is this same multi-model-terminal tree.

## Rule applied - decided, not deliberated

MASTER-RUN-ORDER-20260826.md section 1, third case: **both** trees hold a Phase-19 gate runner. Rule: record it as a finding, operate on the **multi-model-terminal** tree for SPA and MT (its constraints name product/multi-frontier-v2 and apps/desktop/ipc/client.js), and note the ambiguity loudly in the final report.

## Decision

- Phases 1-2 (SPA discovery, Track A if unlocked) operate on: D:\multi model terminal app\sovereign-orchestration-workspace
- Phase 3 (MT-P1) operates on: D:\multi model terminal app\sovereign-orchestration-workspace
- Phase 4 (CP-M1 G28-G124) operates on: D:\Product Software\Production Workspace (disjoint)
- AMBIGUITY_FLAG: carried to docs/CP-M1-FINAL-REPORT.md as required by the master run order.