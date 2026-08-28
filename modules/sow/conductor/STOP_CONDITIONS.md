# STOP_CONDITIONS.md
> **DRAFT v0.1 (2026-07-16) — operator-authored asset.** Conductor files are operator-created, model-independent (Canonical Handoff §2.10.4). This draft was prepared for operator review during Phase 0; it binds nothing until the operator accepts it. Write authority: operator only (see docs/CONDUCTOR_FILES_WRITE_AUTHORITY.md).

Stop assignment and escalate immediately when: a gate fails and no revision path is
authorized; MCP is disconnected (checkpoint, surface, wait); the profile loader reports a
violation; a node attempts an out-of-profile action (pause node, log, escalate); any
subscription governor refusal repeats; a debate exhausts budget without convergence on a
blocking decision; directive/task-graph version mismatch on succession; any request would
require an operator-reserved decision; VRAM plan cannot satisfy an assignment wave without
silent eviction; or you detect drift between an artifact and the frozen spec. Stopping is
success, not failure — weak work must not propagate.
