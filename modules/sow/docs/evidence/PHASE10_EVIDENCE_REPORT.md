# PHASE 10 EVIDENCE REPORT — Coding Worktree Isolation
Autonomous loop iteration 11 · 2026-07-17Z · gate: `gate/phase-10`

## Objective
Coding worktree isolation per Buildout Directive §5 Phase 10 / Plan §7-P10: per-node git
worktrees; controlled merge path (worker branch → gate → operator-approved merge); cross-node
mutation attempts fail and are logged. NTFS ACL depth per U10 — enforce what Windows allows
without admin; record limits honestly.

## Source state
Tags through `gate/phase-9`; freeze `--check` clean throughout. `next_step: phase-10`.

## Files
- **Work commit `4ad6a329`:** `node_runtime/workspace/{worktree,__init__}.py`;
  `tests/integration/test_worktree_isolation.py`.
- **Remediation commit `2ff117d4`:** F1–F6 fixes + regression tests.

## Exit criteria — met, mapped to code + test
- **Per-node worktrees:** `WorktreeManager.create` runs real `git worktree add -b
  node/<node_id>` — each node gets its own branch and directory. Tests: distinct branches +
  paths, real git (not skipped).
- **No cross-node mutation; attempts fail AND are logged:** each node's Phase-3 WorkspaceBinding
  contains its filesystem access to its worktree; a cross-node write (A → B's worktree via
  traversal) raises WorkspaceEscape AND emits a logged `workspace_escape` event, and the target
  file is not created. Validator independently probed three escape vectors — all refused.
- **Controlled merge path:** `MergeCoordinator.merge` is the only path to the trunk; it refuses
  unless the gate verdict is PASS/PASS_WITH_RESERVATIONS AND the operator strictly approved
  (invariant 1 — never self-authorize the protected merge), logging every refusal. A conflicting
  merge aborts and restores a clean trunk (fail closed) with a logged `merge_failed`. Tests:
  FAIL refused, unapproved refused, both → applied (trunk gets the file), unapproved work never
  reaches trunk, conflict aborts clean.

## Enforcement honesty (U10 — recorded, not overclaimed)
- **ENFORCED:** git-worktree separation (own branch + dir per node) + API-layer path containment
  (WorkspaceBinding) + controlled-merge gating (gate verdict + operator approval).
- **NOT ENFORCED (deferred, disclosed):** OS-level filesystem denial between SAME-USER node
  processes — all worktrees share one `.git` object/ref store, so a same-user process with raw
  OS access could bypass the coordinator (run its own `git merge`, rewrite refs). This needs
  restricted tokens / separate accounts / admin and is deferred to a hardening pass (U10). The
  "controlled merge is the only path" claim holds at the API layer, and the docstring says so.

## Independent review (standard-stakes: validator + spec-auditor)
- **gate-validator: PASS.** Ran the suite (282→293) + the worktree tests (real git, not
  skipped); independently probed cross-node containment (3 vectors refused, target not created,
  logged) and merge gating (FAIL/unapproved/PWR-unapproved all refused; trunk untouched until
  PASS+approved); confirmed U10 honesty (not overclaimed), scope/freeze clean, temp repo used,
  no Phase 11 smuggled, no invariant drift.
- **spec-auditor: FINDINGS 2 MAJOR / 4 MINOR / 2 NOTE** (no BLOCKER; no working exploit within
  the disclosed API-layer scope). Dispositions (all fixed pre-gate):
  - **F1 MAJOR — FIXED:** conflicting/failed merge left the trunk half-merged and unlogged.
    Now aborts (clean trunk, fail closed) + logs `merge_failed`. Real-conflict test added.
  - **F2 MAJOR — FIXED:** unvalidated node_id (defense-by-accident). Explicit validation added;
    parametrized invalid-id test.
  - **F3 MINOR — FIXED:** `operator_approved` must be strictly True (truthy no longer approves).
  - **F4 MINOR — FIXED:** worktrees/ added to `.git/info/exclude` (no trunk pollution).
  - **F5 MINOR — FIXED:** commit/get raise WorktreeError (not bare KeyError) for unknown node.
  - **F6 MINOR — FIXED:** remove() deletes the node branch (no dangling).
  - F7/F8 NOTE — accepted/recorded: no caller-identity binding (module is control-plane-internal);
    honesty disclosure accurate.

## Substitutions (loop directive §6)
None — real git operations in temp repos; the isolation + merge-gating under test is real code.

## Deviations / carried
- ruff unavailable (pip out of scope); code typed + stdlib-first.
- Carried: U10 (OS-level same-user fs/git-ref isolation — restricted tokens/separate accounts —
  deferred to Phase 13 hardening, disclosed).

## Gate verdict
**PASS.** Per-node worktrees; cross-node mutation refused + logged (target untouched);
controlled merge gated by verdict + operator approval with fail-closed conflict handling; U10
limits recorded honestly; both MAJOR review findings fixed with pinning tests before closure.
293/293 tests.

## Commits
Work `4ad6a329` → remediation `2ff117d4` → this evidence/register commit (tagged `gate/phase-10`).

## Next phase
`phase-11` — Persistence & conductor succession (**mandatory high-stakes gate-validator**):
serialize conductor state to MCP; kill mid-project → Resume→Select any (mock) model →
reconstruct with zero loss; succession cadence finalized (U11). Full snapshot/restore of
control-plane state.
