# GATE_POLICY.md
> **DRAFT v0.1 (2026-07-16) — operator-authored asset.** Conductor files are operator-created, model-independent (Canonical Handoff §2.10.4). This draft was prepared for operator review during Phase 0; it binds nothing until the operator accepts it. Write authority: operator only (see docs/CONDUCTOR_FILES_WRITE_AUTHORITY.md).

Gate kinds: local (node self-check) → stage → plan → acceptance (operator). Criteria are
declarative, written before evaluation, and referenced by id. A FAIL blocks all dependents;
there is no conductor override — a FAIL you disagree with goes to the operator with your
reasons and the evidence, not around the gate. PASS_WITH_RESERVATIONS must enumerate the
reservations and their owners. Gate verdicts reference evidence entries and any debate
record. Seeded-defect artifacts must reliably fail (this is tested, Plan §12).
