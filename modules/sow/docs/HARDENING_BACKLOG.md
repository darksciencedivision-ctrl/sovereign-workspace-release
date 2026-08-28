# HARDENING BACKLOG — triaged at Phase 13
Sovereign Orchestration Workspace · 2026-07-17 · closes the Phase 13 "hardening backlog triaged" exit criterion.

This triages every unresolved item carried through the build (unresolved-issue register U1–U24
plus the deferred-live items) into a disposition: **DEFERRED-HARDWARE** (needs hardware/software
absent on this host), **DEFERRED-LIVE** (needs live provider access, prohibited by the build),
**DEFERRED-P-LATER** (a real follow-up with an owner phase), or **ACCEPTED** (a recorded design
limit that fails safe). None is a correctness defect in shipped code; each is a bounded, disclosed
limit. Severity is the risk if left unaddressed when the system goes live.

## Deferred — hardware / external stack absent on this host
| Item | What | Disposition | Severity |
|---|---|---|---|
| U1 | Parakeet streaming latency + VRAM under concurrency | DEFERRED-HARDWARE (Track G): GPU+WSL present, NeMo absent (pip out of scope); mock STT behind I-A1 | med |
| U2 | Windows mic capture → WSL bridge + PTT trigger | DEFERRED-HARDWARE (Track G) | med |
| U4 | CC-BY-4.0 attribution mechanics if product ships | DEFERRED-P-LATER (packaging) | low |
| U9 | ConPTY hosting a real console-subsystem coding TUI (OpenCode) in a pane | DEFERRED-P-LATER: re-verify at real-coding-TUI integration | med |

## Deferred — live provider access (prohibited by build directive §2.4)
| Item | What | Disposition | Severity |
|---|---|---|---|
| U3 / U5 | Codex/provider automation + per-account concurrency (ToS) | DEFERRED-LIVE (R8): **Claude Code R8 RECORDED 2026-07-18** (`docs/evidence/R8_TOS_VERIFICATION_CLAUDE_CODE.md`) — no verified per-account concurrency ⇒ stays 1-terminal (I-X3), governor unchanged; live-terms dated retrieval + support confirmation = `[OPERATOR]` at 14B `.adapter`. Codex out of scope (not authorized, OP-5). **UPDATE 2026-07-19 (P15A.r8, OP-6):** Codex now authorized (2nd live provider) — **Codex R8 RECORDED** (`docs/evidence/R8_TOS_VERIFICATION_OPENAI_CODEX.md`); allowance raised to **2** but the raise is **operator-ordered (OP-6), governor-capped, reversible — NOT a verified concurrency number** (both providers stay verified-at-1; basis: `docs/evidence/R8_OP6_CONCURRENCY_BASIS_NOTE.md`). Remaining `[OPERATOR]` live-terms dated retrieval = 15C (both providers). | med |
| U19 | Full Track E/R10 offline-roster benchmark freeze + static-capability verification | DEFERRED-LIVE/HARDWARE (GPU-heavy campaign); light probe shipped | med |
| deferred-live | Live frontier subscription sessions; OpenCode programmatic harness drive | DEFERRED-LIVE; adapters mock-mode, I-CH1 contract ready | med |

## Deferred — real follow-up, owner phase
| Item | What | Disposition | Severity |
|---|---|---|---|
| U6 | MCP transport final choice (SDK vs stdlib loopback) | ACCEPTED-FOR-NOW: stdlib loopback works; SDK swap is an adapter change behind mcp_server | low |
| U10 | OS-level same-user fs/git-ref isolation (restricted tokens / separate accounts) | DEFERRED-P-LATER (hardening): API-layer + git-worktree + Job Object enforced; raw-syscall/own-git bypass out of scope | **high** if multi-tenant; low single-operator |
| U13 | Local-gate evidence-ref resolution (presence vs resolution) | DEFERRED-P8/P3A: gate now resolves via evidence_manager in debate; local gate checks presence | low |
| U14 | Timestamp-format enforcement (needs rfc3339-validator) | ACCEPTED: shape enforced; format enforcement when validator lib available | low |
| U20 | Effective-budget disclosure vs frozen debate@1.0 shape | ACCEPTED: conveyed via outcome + cost_actual | low |
| U21 | Operator state-force override path (not implemented) | DEFERRED-P-LATER (operator console): state machine is absolute; recovery = redo-and-repass | med |
| U22 | Wire ContextCompiler into the live conductor→worker dispatch loop | DEFERRED-P-LATER (integration): proven as a capability | low |
| U23 | Succession event-tail assumes memory_heads == complete ACCEPTED head set | ACCEPTED (fail-safe toward reconcile, never silent loss); confirm basis before multi-entry projects | low |
| U24 | Voice command target-scope check when real dispatch is wired; real-audio buffer-free discard | DEFERRED-P-LATER: control events logged not executed yet | low |
| U29 | Claude Code adapter env-scrub keys on `API_KEY`/`APIKEY` substring, not a bare `_KEY` suffix (gate/phase-14b validator R2). NOT a §2.2 vector for this adapter — the `claude` CLI reads only `ANTHROPIC_*`/`CLAUDE_CODE_*` vars, all prefix-scrubbed; a hypothetical `*_KEY`-only secret survives but is never transmitted by the CLI | DEFERRED-P-LATER (defence-in-depth): widen the substring set if a bare `_KEY` var ever becomes provider-relevant | low |
| U30 | OpenCode reads provider config from its own config file (`opencode.json` / `OPENCODE_CONFIG`), not only env vars (spec-audit note, phase-14c.harness). The §2.2 env scrub does not reach that file; the §2.3 no-paid-path guarantee therefore rests on the enforced `ollama/*` model pin (`_require_local_model`, now in code) + the non-loopback `OLLAMA_HOST` drop | **DISCHARGED 2026-07-18 (phase-14c.worktree):** the driver writes a session-local `opencode.json` (loopback Ollama only) + points `OPENCODE_CONFIG` at it (set after the scrub); `write_scoped_opencode_config` refuses a non-loopback baseURL / non-ollama model — config isolation no longer rests on the pin alone | done |
| U31 | A small LOCAL coder model reliably COMPLETING a schema-correct headless edit through OpenCode's Ollama/OpenAI-compatible tool path was not producible this session (~10 real drives; tool JSON as text, wrong tool-arg schema/paths, single-turn stops). Model-quality limit, NOT a harness/governance defect (OpenCode's real drive + real tool execution + worktree confinement + U30 config isolation all proven, live + deterministic) | DEFERRED-P-LATER (owner: phase-14c.gate / 14E): a landed live edit needs a better agentic local model / tool-schema shaping / multi-turn budget; `.gate` must not claim a live landed edit or live merge without a real produced edit (gate-validator reservation) | low |

## Cross-cutting hardening (recorded)
- **ruff-clean bar** could not be machine-verified (ruff not installed; pip out of scope). Code is
  typed and stdlib-first by inspection. → DEFERRED-P-LATER (CI).
- **jsonschema RefResolver deprecation** (used in schema validation): works today; migrate to the
  `referencing` library before a jsonschema major bump. → DEFERRED-P-LATER.
- **Monitor TOCTOU** (Phase 2 heartbeat) self-healing; **reader-thread teardown** cosmetic. → ACCEPTED.

## Highest-priority item for a live deployment
**U10 (OS-level same-user isolation).** Everything else is low/medium or gated by absent
hardware/live access. If the workspace is ever run multi-tenant (nodes not all trusted, same OS
user), the shared `.git` store and same-user filesystem are a real boundary that the current
API-layer + git-worktree + Job Object containment does not fully close. Owner: a dedicated
hardening pass with restricted tokens / separate accounts. Single-operator use (the shipped
posture) is not exposed.
