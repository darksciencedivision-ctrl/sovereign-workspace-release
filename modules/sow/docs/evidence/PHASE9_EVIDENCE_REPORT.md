# PHASE 9 EVIDENCE REPORT — Scoped Context Compiler
Autonomous loop iteration 10 · 2026-07-17Z · gate: `gate/phase-9`

## Objective
Scoped context compiler per Buildout Directive §5 Phase 9 / Plan §7-P9: assemble a node's
context from MCP by role + task + need-to-know; no default full-transcript forwarding
(invariant 8). Exit: measured token reduction vs a naive baseline on a reference project;
workers demonstrably receive only scoped context.

## Source state
Tags through `gate/phase-8`; freeze `--check` clean throughout. `next_step: phase-9`.

## Files
- **Work commit `fd6e709a`:** `control_plane/routing/{context_compiler,token_meter,__init__}.py`;
  `tests/integration/test_context_compiler.py`.
- **Remediation commit `b352ef70`:** naive-baseline surface hardened (MINOR).

## Exit criteria — met, mapped to code + test
- **Scoped assembly by role+task+need-to-know from MCP:** `ContextCompiler.compile` pulls only
  the task objective + the ACCEPTED outputs of the task's DIRECT dependencies (filtered by
  `provenance.task_id ∈ deps`) + the node's role scope + explicitly requested evidence — all
  via MCP `get_content`/`read_status` (policy-mediated, provenance-bearing). No side channel.
- **No default full-transcript forwarding (inv 8):** the default path is scoped; the naive
  whole-transcript forward exists only as the measurement comparand and is now named
  `measurement_baseline_naive` with a `_measurement_only` guard that refuses (ValueError) if
  invoked as a context path.
- **Workers receive ONLY scoped context:** test asserts `included_entry_ids` is exactly
  {objective, dep1, dep2} and that the six non-dependency findings' bodies are absent from the
  rendered bundle. A compiler returning everything fails both the set-equality and
  sibling-absence assertions.
- **MEASURED token reduction:** real tiktoken (cl100k_base). On the reference project (an
  objective + 8 chunky findings, target task depends on 2): **scoped ≈1053 vs naive ≈4097
  tokens → 74.3% reduction** (≥50% threshold met with headroom). Tokenizer method recorded
  honestly (tiktoken vs word-proxy); the validator independently reproduced the number.

## Independent review (standard-stakes: validator + spec-auditor)
- **gate-validator: PASS.** Ran the suite (277) + the compiler test with `-s`, independently
  reconstructed the tiktoken measurement (~74.2%), confirmed scoping is genuine need-to-know
  (set-equality + sibling-absence), naive is baseline-only (no live caller), reads are
  policy-mediated and project-scoped server-side (cross-project leak impossible),
  scope/freeze clean, no Phase 10 smuggled, no invariant drift.
- **spec-auditor: CLEAN (0 BLOCKER, 0 MAJOR, 1 MINOR, 7 NOTE).** Confirmed spec fidelity, no
  leak path (null task_id correctly excludes the objective; candidates/superseded/CAS-loser
  forks excluded by the store's head-join + shared-tier filter; cross-project blocked
  server-side), token_meter non-gameable (method bound to the same closure that counts;
  div-by-zero handled), tests genuinely prove scoping (independently reproduced 74.38%
  word-proxy). MINOR (naive-baseline public surface, latent inv-8 misuse risk) → **FIXED**
  (renamed + guard). NOTEs (N+1 get_content, caller-trusted objective/evidence refs which are
  still server-side policy-checked, role_scope passed not MCP-read) → accepted/recorded.

## Substitutions (loop directive §6)
None — real tiktoken tokenizer used (present on host); reference project is real MCP entries.

## Deviations / carried
- ruff unavailable (pip out of scope); code typed + stdlib-first.
- Carried: the compiler is a capability (not yet wired into a live worker-dispatch loop);
  live integration into the conductor prototype is a later-phase concern (→ U22).

## Gate verdict
**PASS.** Scoped need-to-know assembly with no default full-transcript forwarding; 74.3%
measured token reduction with a real tokenizer; workers demonstrably receive only scoped
context; spec-auditor CLEAN with the single MINOR hardened before closure. 277/277 tests.

## Commits
Work `fd6e709a` → remediation `b352ef70` → this evidence/register commit (tagged `gate/phase-9`).

## Next phase
`phase-10` — Coding worktree isolation (node_runtime/workspace/): per-node git worktrees,
controlled merge path (worker branch → gate → operator-approved merge), cross-node mutation
attempts fail and are logged. NTFS ACL depth per U10 (enforce what Windows allows without
admin; record limits honestly).
