# CLAUDE.md — Sovereign Orchestration Workspace

Windows-native, CLI-first, multi-model orchestration workspace. Every terminal is a
Sovereign-governed node; nodes share governed state through a Sovereign MCP server
(access, not authority); the operator (Sam) retains final authority.

**Authorization posture: STAGED, GATED BUILD.** No commit without a passed phase gate +
evidence report (`docs/evidence/`). Stop at every operator-reserved decision. Never push,
never touch credentials, never modify anything outside this repo, never call anything
"production-ready" without evidence.

## Canonical sources (frozen — do not edit; see PHASE0_FREEZE_MANIFEST.json)

| Doc | Path | SHA-256 (prefix) |
|---|---|---|
| v2.4 spec + directive | `docs/canonical/Sovereign_Orchestration_Workspace_Canonical_Handoff.md` | `6D3FD03B` |
| Architecture Plan v1.0.1 (BUILD FROM THIS) | `docs/canonical/...Architecture_Plan_v1.0.1_UTF8_20260716.md` | `8C9B7240` |
| Architecture Plan v1.0 (provenance only) | `docs/canonical/...Architecture_Plan_v1.0_20260716.md` | `668089B5` |
| Buildout directive (governs execution) | `docs/canonical/Claude_Code_Buildout_Directive_20260716.md` | `CC414372` |

Precedence: v2.4 spec → Architecture Plan v1.0.1 → Buildout Directive → this file.

## Commands

- Python tests: `python -m pytest tests/ -q`
- Freeze manifest: `python tools/manifest/compute_manifest.py` (regenerates `docs/PHASE0_FREEZE_MANIFEST.json`; hash changes require a new evidence entry)
- Phase 1 spike (from `tools/spike_compositor/`): `npm install && npm start` (Windows host only; ConPTY)

## Code style

- Python 3.12 target (control plane, MCP, debate, scheduler): typed, `ruff`-clean, stdlib-first; money/units = `decimal.Decimal`, never float.
- TypeScript (Electron shell): strict mode, no `any` in control-flow code.
- JSON Schemas in `schemas/` are frozen `@1.0`; every envelope pins its schema version. RETRACTED (W-60/U487): they are NOT the single source of truth - they ground the envelope/plan families only; the operational record family is deliberately unschematized (see `schemas/README.md`, "What schemas/ does NOT govern").
- Conventional commits, one logical change each, **local only**. Gate commits tagged `gate/phase-N` and recorded in the phase evidence report.

## Condensed canonical invariants (enforce in code — full text in docs/canonical/)

**Authority:** (1) operator holds final authority — the app never self-authorizes protected
actions; (2) every terminal is a Sovereign node — no raw model / naked agentic-CLI session;
(3) conductor is an interface + runtime selection (current: Fable 5, operator-selected
2026-07-16), never a vendor default; (4) workers interchangeable behind adapter contracts;
(5) project state lives outside model context.
**Memory/MCP:** (6) one common MCP server for all nodes; (7) **MCP is access, not
authority** — no authorization logic inside `mcp_server/`; (8) context is scoped, never
blanket-forwarded; (9) three memory tiers (local conversational / shared project / private
node); (10) workers publish CANDIDATE, never self-canonize; (11) provenance on every shared
entry; (12) immutable append-only history; (13) conflicts are explicit objects — never
silent last-write-wins (CAS head pointers).
**Reasoning:** (14) debate bounded ≤5 rounds; (15) concurrence preferred, not forced —
dissent preserved; (16) explicit gates — failed artifacts cannot advance, no conductor
override; (17) debate cost-governed (budget/quota/global cap) - RETRACTED for the MCP collaboration path (W-61/U488/U493): recorded unimplemented there, budget_units stored but never read; enforced only on the debate_service path; (18) no node solely judges
its own work.
**Deployment/access:** (19) locality is per-node; (20) air-gap honesty — offline profile
excludes every cloud adapter/client, loader fails closed; (21) one frontier terminal per
subscription by default; (22) local concurrency is hardware-bounded (8–14B tier; VRAM
residency is scheduled, visible, never mid-generation eviction); (23) OpenCode is
first-class — coding harnesses interchangeable behind one contract.
**Voice/UI/safety:** (24) voice is STT-only (Parakeet), post-MVP; (25) voice cannot expand
authority — propose, never execute; (26) audio transcribe-then-discard by default; (27) the
orchestra is visible; (28) conductor succession works (serialize to MCP, Resume→Select);
(29) supervisor-level containment at the OS/process layer — never trust the harness;
(30) minimal necessary control — no invented governance layers.

## Global engineering rules (Buildout Directive §4)

Deterministic code for pricing/eligibility/permission/gate logic — never model output.
Fail closed on ambiguity, disconnect, missing policy, unverified capability. Everything
observable: node/gate/debate state, routing rationale, usage cost. Instrument
cost-to-accepted-output from day one.

## Phase gate rule

Work proceeds Phase 0 → 1 → 2 → 3 → 3A → 4 → … 13 (Buildout Directive §5). Each phase ends
at a gate with an evidence report (§6). High-stakes gates (P1, P3A, P11) additionally
require independent confirmation by the `gate-validator` subagent. **Operator ruling
2026-07-16 (register OP-1..OP-3): the build runs as an autonomous loop —
AUTONOMOUS_BUILD_DIRECTIVE.md governs; formerly operator-interactive gates close by
delegation on recorded evidence; the operator is addressed only at COMPLETE or BLOCKED.**
Standing prohibitions in the directive §2 are NOT waived. **Stop the moment a gate fails**
— fix it; report to the operator only if BLOCKED per directive §8.

## Environment notes (recorded 2026-07-16)

- Build sessions running in a Linux sandbox against this mounted Windows folder: the mount
  corrupts git's lock/rename protocol. Mitigation: git-dir kept sandbox-local during a
  session (`/tmp/sow.git` via `/tmp/g.sh`), `.git/` mirrored to this folder with plain
  copies after each gate commit and verified with `git fsck`. Native Windows git on this
  repo is unaffected.
- ConPTY/Electron cannot execute in the Linux sandbox: **Phase 1 spike metrics must be
  produced by an operator run on the Windows host** (`tools/spike_compositor/`, one-command
  runner). Headless logic tests cover what Linux can verify.
