# CONTEXT_ROUTING_POLICY.md
> **DRAFT v0.1 (2026-07-16) — operator-authored asset.** Conductor files are operator-created, model-independent (Canonical Handoff §2.10.4). This draft was prepared for operator review during Phase 0; it binds nothing until the operator accepts it. Write authority: operator only (see docs/CONDUCTOR_FILES_WRITE_AUTHORITY.md).

Workers receive **scoped context only**: role + task + need-to-know set compiled from MCP
(directives slice, dependency artifacts, relevant ACCEPTED memory). Full-transcript
forwarding is prohibited by default (invariant 8). Every context package is logged (what
was routed, to whom, why, token count). Private-node memory never routes to another node.
CANDIDATE memory routes only with its status visible — never presented as accepted truth.
