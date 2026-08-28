# Sovereign Multi-Terminal Orchestration Workspace

Windows-native, CLI-first, multi-model orchestration workspace in which every model
terminal runs as a governed **Sovereign node**, all nodes share governed state through an
**MCP server that is access — not authority**, and the human operator retains final control.

**Status:** staged, gated build (operator authorization 2026-07-16).
**Current phase:** Phase 19, unit 19.10 — 50 tags; `gate/phase-19` **not set**. Corrected 2026-08-16
(W-08); this line previously read "Phase 1" and claimed the Phase 0 freeze signature was
outstanding. It is not: `docs/PHASE0_FREEZE_MANIFEST.json` records
`operator_signature.status = "SATISFIED_BY_OPERATOR_RULING"` since 2026-07-16.
**Gate state:** see `docs/evidence/` for per-phase evidence reports and verdicts. This line names no
successor phase on purpose — the canonical handoff does, and duplicating it here is how it went
eighteen units stale.

## Provenance

Built from the frozen canonical set in `docs/canonical/` (byte-identical copies of the
handoff bundle; hashes in `docs/PHASE0_FREEZE_MANIFEST.json`). Build source is Architecture
Plan **v1.0.1_UTF8** (`8C9B7240…`); the mojibake original v1.0 (`668089B5…`) is preserved
for provenance only. Nothing under `docs/canonical/` may be edited — the guard hook blocks it.

## Layout (Buildout Directive §3; deviations justified in Architecture Plan §8)

```
apps/desktop/        Electron + TS + xterm.js shell        (Phase 1+ / after D-UI-01)
control_plane/       Sovereign runtime: directives, tasks, gates, permissions… (P2+)
mcp_server/          Separate loopback MCP process — access, not authority     (P3A)
debate_service/      Bounded, cost-capped debate                               (P7)
scheduler/           Capability registry, resolver, queue, residency planner   (P5+)
node_runtime/        Supervisor, containment, local gate, context, workspace   (P3)
adapters/            conductor / coding{opencode,codex,claude_code,aider} / frontier / local / voice
terminal/            ConPTY host, compositor, session                          (P1+)
conductor/           Operator-authored conductor files (DRAFT, pending operator acceptance)
schemas/             @1.0 JSON Schemas — frozen at Phase 0, single source of truth
persistence/         SQLite WAL + content-addressed store, single-writer (+ plan §8 addition)
voice_bridge/        Windows WASAPI capture ↔ WSL NeMo bridge (+ plan §8 addition, P12)
tests/               unit / integration / security / recovery / evaluation
tools/manifest/      Freeze-manifest tooling (the only Phase 0 code)
tools/spike_compositor/  Phase 1 throwaway rig
docs/                canonical/ · registers/ · evidence/ · threat model · freeze manifest
```

## Gates

Phase order 0 → 1 → 2 → 3 → 3A → 4 → … → 13; each phase ends at a gate with an evidence
report; commits are local-only and land after the gate passes (`gate/phase-N` tags).
Operator-reserved: Phase 0 freeze signature, Phase 1 framework ratification (D-UI-01),
D-MCP-03 conflict-mechanism verdict at Phase 3A, all promotions and acceptance.
