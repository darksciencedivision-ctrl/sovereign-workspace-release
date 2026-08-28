# ORCHESTRATION_RULES.md
> **DRAFT v0.1 (2026-07-16) — operator-authored asset.** Conductor files are operator-created, model-independent (Canonical Handoff §2.10.4). This draft was prepared for operator review during Phase 0; it binds nothing until the operator accepts it. Write authority: operator only (see docs/CONDUCTOR_FILES_WRITE_AUTHORITY.md).

1. Every node is spawned by the supervisor with a permission profile; a naked session is
   refused at registration (I-C1). No exceptions, including for you.
2. All inter-node transfer happens through MCP structured entries — manual transcript or
   clipboard routing is prohibited (I-M1).
3. Assignment flow: task READY → capability resolution (Scheduler) → spawn/bind (subject to
   I-X3 governor + VRAM residency plan) → scoped context → execute → artifact published
   CANDIDATE with provenance → local gate → stage gates → ACCEPTED feeds dependents (F1).
4. Fail closed: MCP disconnect, missing policy field, ambiguous instruction, unverified
   capability → stop that path, checkpoint, surface on canvas, escalate.
5. Every routing decision is logged with a rationale the operator can inspect.
6. One frontier terminal per subscription; succession releases the predecessor terminal
   before the successor claims it (I-X3).
