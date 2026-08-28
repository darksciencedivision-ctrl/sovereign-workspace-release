# MODEL_SELECTION_POLICY.md
> **DRAFT v0.1 (2026-07-16) — operator-authored asset.** Conductor files are operator-created, model-independent (Canonical Handoff §2.10.4). This draft was prepared for operator review during Phase 0; it binds nothing until the operator accepts it. Write authority: operator only (see docs/CONDUCTOR_FILES_WRITE_AUTHORITY.md).

Select by **capability descriptor** through the Scheduler registry — never by vendor name
(I-SC1). Ranking inputs: benchmark fit (Track E/R10 ACCEPTED evidence), current load, cost
class under the active profile, VRAM residency delta (offline). Respect: profile
eligibility (fail-closed loader, I-D1/I-D2), one-terminal-per-subscription (I-X3), locality
freedom when networked (I-L1). Offline defaults at current hardware: conductor Qwen3
8–14B-class; coding OpenCode + Qwen2.5/Qwen3-Coder 7–14B via Ollama (D-COND-02/D-CODEX-03).
Hardware constraints are recorded, never hidden (I-A1).
