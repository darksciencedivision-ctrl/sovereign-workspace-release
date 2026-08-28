# CLAUDE CODE — BUILDOUT DIRECTIVE
## Sovereign Multi-Terminal Orchestration Workspace

**Issued to:** Claude Code (CLI coding agent) · **Issued by:** the operator (Sam) · **Date:** 2026-07-16
**Companion:** read `Sovereign_Orchestration_Canonical_Report_and_Analysis_20260716.md` and the canonical spec/plan in this folder (`00`–`03`) **in full before creating or modifying any file.**
**Model note:** run this build on a stable coding model (e.g., a current Claude coding model). The "conductor = Fable 5" decision concerns the *product's* runtime; it does not dictate which model you, Claude Code, run as while building.

---

## 1. AUTHORITY & SCOPE OF THIS AUTHORIZATION

This is **staged, gated build authorization** — not open-ended license. The operator retains authority over objectives, scope, protected actions, credentials, external publication, and final acceptance.

**You ARE authorized to:**
- create ONE new, isolated repository under a fresh project root (do not build inside `SOVEREIGN_SYSTEM`, `Sov 1`, or any existing Sovereign repo);
- implement the product in the canonical phase order;
- create source files, tests, and local config;
- install normal project dependencies;
- run local commands and test suites;
- make **local** Git commits **after** a phase gate passes with evidence;
- proceed to the next phase only while each gate passes.

**You are NOT authorized to (stop and ask the operator):**
- `git push`, open PRs, publish releases, or any remote/network publication;
- create, read, store, or transmit credentials/secrets/API keys;
- purchase or sign up for paid services;
- modify or delete anything outside the new project root (no touching other Sovereign repos or the folders above);
- run frontier provider CLIs against live subscriptions during the substrate phases (mock them until Phase 6, and even then respect one-terminal-per-subscription and provider ToS);
- silently change the objective or scope;
- call any MVP "production-ready," "secure," or "done" without evidence;
- promote any capability to autonomous/live behavior without explicit operator sign-off.

If a task appears to require a prohibited action, **halt and surface it** as an operator decision.

---

## 2. HOW TO OPERATE AS CLAUDE CODE (project setup & discipline)

Set the repo up so the guardrails are enforced by configuration, not memory:

**2.1 `CLAUDE.md` (run `/init`, then edit).** Put persistent context Claude Code reloads every session: build/test/lint commands; TypeScript/Python code style; the branch/commit convention; the phase-gate rule ("no commit without a passed gate + evidence"); and a condensed copy of the **canonical invariants** (report §3) with the instruction to enforce them in code. Keep it tight and high-signal.

**2.2 `.claude/settings.json` — permissions (deny-by-default posture).** Configure `permissions.deny` and `permissions.allow`:
- `deny`: `Read(./.env)`, `Read(./.env.*)`, `Read(./secrets/**)`, `Read(**/credentials*)`, `Read(../**)` and any path outside the project root; `Bash(git push:*)`, `Bash(git remote:*)`, `Bash(gh:*)`, `Bash(npm publish:*)`, `Bash(curl:*)`, `Bash(wget:*)` and other network/publish commands.
- `allow`: the local build/test/format commands you actually use (e.g., `Bash(npm run test:*)`, `Bash(pytest:*)`, `Bash(npm run build:*)`).

**2.3 Hooks (`.claude/settings.json`).** Add a **PreToolUse** hook that hard-blocks writes/deletes outside the project root and blocks any `git push`/remote/network command — belt-and-suspenders over the permission rules. This is the code-level analogue of the product's "supervisor containment" invariant.

**2.4 Subagents (`.claude/agents/`).** Create project subagents and use them for **independent verification** (a core requirement here — never let the builder be the sole judge of its own work):
- a `gate-validator` subagent that, at each phase gate, checks exit criteria against actual test output and the plan — in an isolated context, so it isn't primed by your implementation reasoning;
- a `spec-auditor` subagent that checks new code against the canonical invariants and flags drift.
Use subagents to research/read large plan sections without polluting the main implementation context.

**2.5 `.mcp.json`.** Once the Sovereign MCP server exists (Phase 3A), register it here (loopback only) so nodes and tools reach it uniformly. Do not add MCP servers that require credentials during substrate phases.

**2.6 Plan mode & thinking.** Before Phase 1, Phase 3A, and any phase touching concurrency/fencing, enter **plan mode** and use extended thinking ("think hard" / "ultrathink") to lay out the approach and the test plan **before** writing code. Get the plan right, then implement against it.

**2.7 Test-driven, anti-overfit.** For each unit of work, write or define the test/target first, implement until it passes, then have an **independent subagent verify the implementation isn't overfitting to the tests**. Claude Code performs best iterating against a concrete target.

**2.8 Commits.** Conventional commits, one logical change each, **local only**. Tag the commit that closes a phase gate (e.g., `chore(gate): Phase 3A passed`) and record its hash in the phase evidence report.

---

## 3. REPOSITORY STRUCTURE (create at Phase 0; justify any deviation)

```
sovereign-orchestration-workspace/
├── CLAUDE.md
├── .claude/{settings.json, agents/, commands/}
├── .mcp.json                      # added at Phase 3A
├── apps/desktop/                  # Electron + TS + xterm.js shell
├── control_plane/{directives,tasks,nodes,routing,gates,permissions,artifacts,recovery,profiles}/
├── mcp_server/{resources,tools,auth,access_control,provenance,events,conflict}/
├── debate_service/{round_manager,evidence_manager,gate,cost_governor}/
├── scheduler/{capability_registry,resolver,queue,residency_planner}/
├── node_runtime/{supervisor,containment,debate_client,gate,context,workspace}/
├── adapters/{base,conductor,coding/{opencode,codex,claude_code,aider},frontier,local,voice_parakeet}/
├── terminal/{conpty,compositor,session}/
├── conductor/                     # operator-authored conductor files (identity, role, policies, current state)
├── schemas/                       # @1.0 frozen at Phase 0
├── tests/{unit,integration,security,recovery,evaluation}/
├── tools/{spike_compositor}/      # Phase 1 throwaway rig
└── docs/
```

---

## 4. GLOBAL ENGINEERING RULES (enforce in code)

- **Determinism where it matters:** pricing/eligibility/permission/gate logic is deterministic code, never model output. Money/units use exact decimal types, never floats.
- **MCP is access-not-authority:** authorization, memory promotion, gate verdicts, and identity live in the control plane; the MCP server rejects any state transition lacking control-plane authorization.
- **Immutable history + CAS heads:** all shared writes append; current pointers advance by compare-and-swap; conflicts create explicit conflict objects. No silent last-write-wins anywhere.
- **Fail closed:** ambiguity, disconnect, missing policy fields, or unverified capability → stop and escalate, never guess.
- **Containment at the OS/process layer:** worker nodes run in scoped worktrees with deny-by-default filesystem/network; a naked agentic process is refused at node registration.
- **Everything observable:** node state, gate state, debate rounds, routing rationale, usage/cost, and MCP connectivity are inspectable; instrument cost-to-accepted-output from day one.

---

## 5. PHASE ORDER (each ends at a gate; do not skip ahead)

For **every** phase produce an evidence report (§6) and commit locally only after the gate passes.

- **Phase 0 — Canonical freeze & repo foundation.** Locate every supplied canonical/plan artifact; record paths, sizes, sha256, encodings; confirm you are building from the clean `v1.0.1_UTF8` plan (`8C9B7240…`) and preserve the original (`668089B5…`) untouched. Create the isolated repo, `CLAUDE.md`, `.claude/` config + hooks, the conductor files, the `@1.0` schemas (project, node, task, message, artifact, memory, evidence, debate, gate, permission, usage, checkpoint), the decision + unresolved registers, the threat model, and test scaffolding. **Gate:** repo + schemas + registers + guardrails exist; no product code yet.
- **Phase 1 — Terminal compositor spike** (`tools/spike_compositor/`, Electron+xterm.js+node-pty). Demonstrate ≥6 concurrent interactive ConPTY sessions (incl. a full-screen TUI and a ~1 MB/s streamer), correct pane resize/reflow, session survival across layout changes/detach-reattach, and supervised process lifecycle. Capture p95 input latency, dropped-output detection, RAM/CPU at 6 and 8 panes. **Kill criteria (reject Electron and run the Tauri fallback spike, then report comparative evidence):** input crosses to the wrong pane; layout changes restart/corrupt sessions; instability at 6 terminals; unacceptable memory growth at 8 panes; unreliable ANSI/resize; process lifecycle not supervisable; ConPTY ownership not safely containable. **Gate = OPERATOR ratifies the framework (D-UI-01).** Do not proceed to product UI until ratified.
- **Phase 2 — Node process manager** (registry, states, heartbeat, event log).
- **Phase 3 — Sovereign node runtime** (directive/role/permission loaders, supervisor containment, local gate, structured output).
- **Phase 3A — MCP shared-memory foundation (MVP-foundational).** Separate loopback server; per-node auth; resource + tool catalogs with scope enforcement in the control plane (not MCP); memory-state lifecycle server-enforced; provenance on every write; artifacts by content hash; immutable append + CAS heads; **explicit conflict objects (run the concurrent-writer test; record the D-MCP-03 verdict)**; fail-closed disconnect; conductor-replacement support. **Gate (all must pass):** memory survives restart; nodes keep independent context; every shared write has provenance; candidate/accepted separated; canonical directive not worker-writable; conductor replacement preserves memory; disconnect never corrupts state; concurrent-writer test yields conflict records, never silent overwrite; **no authorization logic inside MCP.**
- **Phase 4 — First conductor adapter** (loads conductor files; runs the conductor loop; holds no credential).
- **Phase 5 — Conductor + two workers** (launch/assign via Sovereign + MCP; capability-based assignment via the Scheduler; route one artifact; all transfers logged).
- **Phase 6 — Multi-model & local adapters** (≥3 backends incl. an OpenCode+local-coder coding node and ≥1 local reasoning model; frontier adapters mocked or, if the operator authorizes, one-terminal-per-subscription with ToS verified).
- **Phase 7 — Debate Service** (reusable; ≤5 rounds; budgets/quotas/global cap; dissent preserved; independent judgment; caller authorization).
- **Phase 8 — Gate Service** (explicit criteria; failed artifacts cannot advance; traceable reasons).
- **Phase 9 — Scoped context compiler** (no blanket transcript forwarding; measured token reduction).
- **Phase 10 — Coding worktree isolation** (per-node worktrees; controlled merge; no cross-node mutation).
- **Phase 11 — Persistence & conductor succession** (serialize conductor state to MCP; kill mid-project → Resume→Select any model → reconstruct with zero loss).
- **Phase 12 — Parakeet voice input** (STT-only; push-to-talk; command preview; approval for destructive commands; raw audio discarded by default; text and voice produce equivalent control events).
- **Phase 13 — Evaluation & hardening** (measure against simpler baselines: single model; conductor + raw workers; Sovereign workers no debate; Sovereign workers + bounded debate — report cost-to-accepted-output, drift, evidence quality, correction burden, recovery).

**Stop the moment a phase gate fails.** Do not integrate provider CLIs before the terminal, node, and MCP substrates are proven.

---

## 6. PER-PHASE EVIDENCE REPORT (required before each commit)

State: objective · source state · files changed · commands run · tests (and results) · performance measurements · deviations from the plan · unresolved issues · gate verdict (with the criteria checked) · commit hash · next phase. **Never present a reported result as verified until you have inspected the artifact or run the test yourself** — and where the phase gate is high-stakes (P1, P3A, P11), have the `gate-validator` subagent confirm it independently.

---

## 7. REQUIRED FIRST RESPONSE (before writing anything)

Return:
1. confirmation that you understand this is **staged, gated** build authorization (not open-ended);
2. the source artifacts available to you, with their sizes, sha256, and encoding status (confirm you will build from `8C9B7240…` and preserve `668089B5…`);
3. the isolated repository path you will create and use;
4. your Phase 0 work order and the `.claude/` guardrail config (permissions + hooks) you will put in place first;
5. any hard blocker;
6. explicit confirmation that you will not push remotely, use credentials, purchase services, or modify anything outside the project root.

Then begin Phase 0.

*End of Claude Code buildout directive — 2026-07-16.*
