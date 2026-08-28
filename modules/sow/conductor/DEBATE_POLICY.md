# DEBATE_POLICY.md
> **DRAFT v0.1 (2026-07-16) — operator-authored asset.** Conductor files are operator-created, model-independent (Canonical Handoff §2.10.4). This draft was prepared for operator review during Phase 0; it binds nothing until the operator accepts it. Write authority: operator only (see docs/CONDUCTOR_FILES_WRITE_AUTHORITY.md).

Use debate when: an artifact fails a gate on contested grounds; two capable nodes produce
materially conflicting candidates; or a decision's cost-of-error exceeds its debate budget.
Do not use debate for: settled invariants, operator-reserved decisions, or style.

Bounds (service-enforced, I-DS1): ≤5 rounds, early stop on convergence, per-debate budget,
per-caller quota, global concurrent cap. Every assertion cites MCP evidence entries — model
votes are not evidence. Dissent is preserved verbatim and flows to the gate/operator as
first-class output. You are not the sole judge of any debate you called (invariant 18).
