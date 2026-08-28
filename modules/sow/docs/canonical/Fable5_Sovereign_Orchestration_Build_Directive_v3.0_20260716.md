# FABLE 5 BUILD DIRECTIVE

## Sovereign Multi-Terminal Orchestration Workspace v3.0

You are receiving build authorization for the Sovereign Multi-Terminal Orchestration Workspace.

Read the accompanying canonical handoff in full before creating or modifying files.

## Authority

The human operator controls objective, scope, protected actions, external publication, credentials, and final acceptance.

You are authorized to:

- create a new isolated repository;
- implement the product in the canonical phases;
- create source files and tests;
- install normal project dependencies;
- run local commands and test suites;
- create local Git commits after passed phase gates;
- continue sequentially while each gate passes.

You are not authorized to:

- push remotely;
- publish releases;
- purchase services;
- expose or store credentials;
- alter unrelated Sovereign repositories;
- delete outside the isolated project root;
- silently change the objective;
- call an MVP production-ready without evidence.

## Product objective

Build a Windows-native CLI-first orchestration workspace with a dynamic terminal canvas.

The operator selects an interchangeable conductor. The conductor launches and coordinates Sovereign-governed worker terminal nodes. Every node connects to the common Sovereign MCP layer, preserves independent context, publishes structured artifacts, and operates under explicit permissions.

Nodes may be local, frontier-backed, or mixed when networked. Strict air-gapped mode is all-local.

Frontier models are accessed primarily through provider CLIs under subscription authentication. Use one active terminal per subscription/account by default.

OpenCode is a first-class local coding harness. Codex, Claude Code, OpenCode, Aider, and future coding CLIs must fit one replaceable coding-node contract.

## Mandatory invariants

- Human operator retains final authority.
- No naked model or agentic CLI participates.
- Conductor is a runtime role, not a vendor dependency.
- Project state lives outside model context.
- MCP is access and transport, not authority.
- Shared memory is scoped, versioned, provenance-bearing, and candidate-first.
- Workers cannot self-canonize.
- History is immutable; conflicts are explicit.
- Debate is bounded to five rounds by default.
- Concurrence is preferred, not required.
- Debate has cost limits and independent judgment.
- Gates evaluate explicit requirements.
- Locality is per node.
- One frontier terminal per subscription by default.
- Local concurrency is hardware-bounded.
- Conductor succession must work.
- Supervisor-level containment is mandatory.
- Voice is STT-only and post-MVP.
- Raw voice audio is discarded by default.
- Do not invent unrelated governance layers.

## Executable technology defaults

Begin with:

- Electron;
- TypeScript;
- xterm.js;
- node-pty / Windows ConPTY;
- Python 3.12 control plane;
- separate local MCP server;
- SQLite WAL;
- content-addressed artifact store;
- immutable append plus compare-and-swap head pointers;
- authenticated loopback WebSocket for UI/control-plane events;
- standard local MCP transport, with a supervised bridge where a client requires stdio.

Electron remains provisional until the Phase 1 spike passes its kill criteria.

## Required phase order

1. Phase 0: canonical freeze and repository foundation.
2. Phase 1: terminal compositor spike.
3. Phase 2: node process manager.
4. Phase 3: Sovereign node runtime.
5. Phase 3A: MCP shared-memory foundation.
6. Phase 4: first conductor adapter.
7. Phase 5: conductor with two workers.
8. Phase 6: multi-model and local-model adapters.
9. Phase 7: Debate Service.
10. Phase 8: Gate Service.
11. Phase 9: scoped context compiler.
12. Phase 10: coding worktree isolation.
13. Phase 11: persistence and conductor succession.
14. Phase 12: Parakeet voice input.
15. Phase 13: evaluation and hardening.

Stop when a phase gate fails. Do not skip ahead to provider integrations before the terminal, node, and MCP substrates are proven.

## Immediate Phase 0 order

1. Locate every supplied canonical handoff and architecture artifact.
2. Record paths, sizes, hashes, and encodings.
3. Preserve the original architecture plan whose reported and independently verified hash is:
   `668089B57C3162DABDE62ED249778D26F554910666FF62A552FA968BE199E48F`
4. Repair its UTF-8 mojibake into a new file without overwriting the original.
5. Produce a deterministic encoding-repair report and new hash.
6. Create a new isolated repository.
7. Do not alter an existing Sovereign repository.
8. Create the canonical conductor files.
9. Create the initial schemas for project, node, task, message, artifact, memory, evidence, debate, gate, permission, usage, and checkpoint.
10. Create the decision and unresolved registers.
11. Create the threat model.
12. Create test scaffolding.
13. Produce a Phase 0 evidence report.
14. Commit locally only after the Phase 0 gate passes.

## Phase 1 kill criteria

Reject the Electron path if, after reasonable optimization:

- pane input crosses to the wrong terminal;
- layout changes restart or corrupt sessions;
- six concurrent terminals remain unstable;
- eight panes cause unacceptable sustained memory growth;
- ANSI or resize behavior is unreliable;
- process lifecycle cannot be supervised accurately;
- ConPTY ownership cannot be contained safely.

If rejected, execute the named Tauri fallback spike and report comparative evidence.

## MCP requirements

The MCP server:

- runs separately beside the control plane;
- binds only to loopback;
- authenticates every node;
- enforces scoped access;
- separates candidate and accepted memory;
- records provenance;
- uses SQLite WAL metadata;
- stores artifacts by content hash;
- appends immutable records;
- updates current heads with CAS;
- creates explicit conflict objects;
- fails closed on disconnect;
- supports conductor replacement.

MCP cannot grant authority or promote memory on its own.

## Debate requirements

The Debate Service is reusable by authorized nodes.

Default rounds:

1. initial construction;
2. adversarial critique;
3. alternative;
4. evidence reconciliation;
5. bounded final revision.

It must enforce hard budgets, quotas, a global concurrency cap, early stopping, dissent preservation, and independent judgment.

## Reporting

Every phase report must state:

- objective;
- source state;
- files changed;
- commands run;
- tests;
- performance measurements;
- deviations;
- unresolved issues;
- gate verdict;
- commit hash;
- next phase.

Never present a reported claim as verified until you inspect the artifact or run the test.

## Required first response

Return:

1. confirmation that you understand this is staged build authorization;
2. the source artifacts available to you;
3. their hashes and encoding status;
4. the isolated repository path you will use;
5. the Phase 0 work order;
6. any hard blocker;
7. confirmation that you will not push remotely, use credentials, or mutate unrelated repositories.

Then begin Phase 0.
