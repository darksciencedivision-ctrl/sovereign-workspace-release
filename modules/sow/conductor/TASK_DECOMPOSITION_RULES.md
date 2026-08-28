# TASK_DECOMPOSITION_RULES.md
> **DRAFT v0.1 (2026-07-16) — operator-authored asset.** Conductor files are operator-created, model-independent (Canonical Handoff §2.10.4). This draft was prepared for operator review during Phase 0; it binds nothing until the operator accepts it. Write authority: operator only (see docs/CONDUCTOR_FILES_WRITE_AUTHORITY.md).

Decompose to tasks that: (a) have one owning capability descriptor; (b) declare explicit
deps; (c) carry a budget (tokens/wallclock); (d) end at a defined gate with declarative
criteria stated **before** work begins; (e) produce structured artifacts, never loose prose
in a terminal. Prefer the smallest task that yields a gateable artifact. Do not create
tasks whose acceptance criteria you cannot state — take those to the operator as open
questions. The plan gate (operator) approves the graph before first assignment.
