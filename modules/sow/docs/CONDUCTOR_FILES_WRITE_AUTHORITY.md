# CONDUCTOR FILES — LIST & WRITE AUTHORITY (U8, first pass at Phase 0)
Per Canonical Handoff §2.10.4 and Plan §9.5 (`sovereign://conductor_files/*` —
operator-writable only). Refined at Phase 3A when the files become MCP resources.

## Declared file list (12 — closed set at @1.0)

`IDENTITY.md`, `ROLE.md`, `CONDUCTOR_DIRECTIVE.md`, `ORCHESTRATION_RULES.md`,
`TASK_DECOMPOSITION_RULES.md`, `CONTEXT_ROUTING_POLICY.md`, `DEBATE_POLICY.md`,
`GATE_POLICY.md`, `MODEL_SELECTION_POLICY.md`, `OPERATOR_RESERVED_AUTHORITY.md`,
`STOP_CONDITIONS.md`, `CURRENT_PROJECT_STATE.md`

Adding/removing a file from this set is an operator decision recorded in the decision
register with a new manifest hash.

## Write authority

| Principal | Authority |
|---|---|
| Operator (Sam) | **Sole write authority** for all 12 files |
| Conductor (any runtime selection) | Read at startup (mandatory, in declared order); may **propose** changes only as CANDIDATE memory entries (kind `conductor_file`) that the operator reviews and applies |
| Workers | Read only what context routing scopes to them; never write |
| CoWork / external clients | Read-only where scoped; every access logged (D-COWORK-01); canonical files never writable (T14) |
| MCP server | Serves the files; enforces nothing itself (I-M2) — write rejection comes from Sovereign policy |

Note on `CURRENT_PROJECT_STATE.md`: runtime project state is carried by succession
snapshots (checkpoint@1.0) and the task graph, **not** by editing this file mid-flight;
the file is the operator's curated summary and stays operator-writable-only.

## Versioning (first pass)

Each file carries a `DRAFT vX.Y` header until operator acceptance, then `v1.0`. Every
accepted version is hashed into the freeze/update manifest; the conductor's startup
staleness checklist compares loaded hashes against the manifest and fails closed on
mismatch (T15).

## Status (2026-07-16)

All 12 files exist as **DRAFT v0.1**, authored during Phase 0 for operator review.
They bind nothing until accepted. Acceptance may accompany the Phase 0 freeze signature
or follow separately — operator's choice.
