# SOVEREIGN MULTI-TERMINAL ORCHESTRATION WORKSPACE

## Canonical Build Handoff for Fable 5

**Document version:** v3.0  
**Date:** 2026-07-16  
**Document type:** Consolidated canonical architecture, implementation authority, build directive, phase gates, and acceptance specification  
**Intended recipient:** Fable 5 acting as the initial build engineer and candidate conductor  
**Target platform:** Windows 11  
**Current status:** Build authorized under the staged execution contract in this document  
**Supersession rule:** This document supersedes earlier planning-only directives where they conflict. Earlier artifacts remain provenance and design history.

---

# 0. HANDOFF CONTROL

## 0.1 Purpose

This document is the complete handoff for implementation of the Sovereign Multi-Terminal Orchestration Workspace.

It consolidates:

- the original multi-terminal orchestration concept;
- the Sovereign-per-terminal runtime requirement;
- the MCP shared-memory architecture;
- conductor interchangeability;
- mixed local and frontier-model operation;
- provider CLI access under subscription authentication;
- the one-terminal-per-subscription rule;
- OpenCode as a first-class local coding harness;
- bounded multimodal debate loops;
- threshold gates;
- dynamic terminal-canvas behavior;
- the independently verified architecture-plan recommendations;
- implementation phases, tests, failure criteria, and operator-reserved boundaries.

This is not a request for another broad conceptual plan. Fable 5 is authorized to build the product in controlled phases, generate the repository and source files, run tests, record evidence, and create local commits. It must stop when a phase gate fails or an operator-reserved action is reached.

## 0.2 Authority

The human operator controls:

- the objective;
- final scope;
- product direction;
- acceptance;
- external release;
- deployment;
- credentials;
- spending;
- remote publication;
- permission expansion;
- destructive actions outside the isolated project root.

Fable 5 may:

- create a new isolated repository;
- design and implement the application;
- create local files and tests;
- install ordinary development dependencies inside the project environment;
- run local builds and test suites;
- create local Git commits after passed phase gates;
- revise implementation details when required by measured evidence;
- select replaceable libraries behind stable interfaces;
- proceed from one phase to the next when the required exit criteria pass.

Fable 5 may not:

- push to a remote repository;
- publish releases;
- expose credentials;
- automate provider logins without the operator;
- purchase services;
- alter unrelated Sovereign repositories;
- erase source evidence;
- silently redefine the objective;
- declare production readiness merely because an MVP launches.

## 0.3 Canonical precedence

When instructions conflict, use this order:

1. Current explicit operator instruction.
2. This v3.0 canonical build handoff.
3. Verified architecture plan v1.0 and its clean UTF-8 successor.
4. Canonical handoff v2.4, if present in the build environment.
5. Canonical handoff v2.3.
6. Earlier architecture discussions and amendments.

All conflicts must be recorded. Do not quietly blend incompatible requirements.

---

# 1. SOURCE PROVENANCE AND CURRENT EVIDENCE

## 1.1 Verified v2.3 archive

The supplied v2.3 archive was independently inspected in the current handoff environment.

- Archive: `Sovereign_Orchestration_Workspace_Canonical_Handoff_v2.3.zip`
- SHA-256: `d8b996888905a9b8b5363a1e22de4789bc69d24838fb18eeb3bf60fd963d41d6`
- Members: 2

Member 1:

- `Sovereign_Orchestration_Workspace_Canonical_Handoff.md`
- Size: 67,814 bytes
- Lines: 568
- SHA-256: `e76bcb6b4f547cb94b3e0d749851d5da449cb42655bb3feea652d97ae3eea0e1`

Member 2:

- `Fable5_Directive_v2.3.md`
- Size: 21,065 bytes
- Lines: 142
- SHA-256: `6f14a8ce50239932cf48036313af43bb5ab989dbee51e00bd799afc85a3f2e4a`

## 1.2 Verified architecture plan report

The operator-side independent audit verified the following deliverable:

- `Sovereign_Orchestration_Workspace_Architecture_Plan_v1.0_20260716.md`
- Size: 70,547 bytes
- SHA-256: `668089B57C3162DABDE62ED249778D26F554910666FF62A552FA968BE199E48F`
- Structure: 20 required sections
- Unresolved register: U1 through U12
- Invariant coverage: all 23 inherited invariants represented
- Confirmed content: Electron, xterm.js, node-pty, ConPTY, Tauri fallback, Python control plane, SQLite WAL, content-addressed artifacts, immutable append plus compare-and-swap head pointers, VRAM residency planner, supervisor-level CLI containment, conductor succession snapshots, subscription concurrency governor, and reusable cost-capped Debate Service.

The audit found one real defect: approximately 68 lines contain double-encoded UTF-8 mojibake. The original hash authenticates the corrupted source. Fable must preserve the original, create a clean UTF-8 successor, produce a deterministic repair diff, record the new hash, and use the clean copy as the working architecture artifact.

## 1.3 Evidence classification

The following are verified design facts:

- the v2.3 package contents and hashes;
- the architecture-plan hash, size, structure, and enumerated content, as independently verified in the operator environment;
- MCP is MVP-foundational;
- conductor and worker models are interchangeable;
- locality is per node;
- local and frontier nodes may be mixed when network access exists;
- strict air-gapped mode necessarily uses only local nodes;
- one active terminal per frontier subscription/account is the default;
- current local operating target is approximately 8B to 14B models;
- voice input is STT-only;
- raw voice audio is discarded after transcription by default.

The following remain implementation hypotheses until tested:

- Electron will satisfy terminal-density and memory targets;
- node-pty/ConPTY will remain stable at the required concurrency;
- Parakeet will meet latency and VRAM targets on the available machine;
- each frontier CLI will support the required MCP and supervisor integration;
- provider subscription terms will permit the intended automation;
- model debate will reduce total cost to accepted output in the target workloads.

---

# 2. PRODUCT OBJECTIVE

Build a Windows-native, CLI-first, multi-model orchestration workspace in which:

1. The operator selects any compatible model or CLI node as the conductor.
2. The conductor remains visible in its own terminal pane.
3. The conductor can launch and coordinate worker terminal nodes.
4. Every conductor and worker runs through the Sovereign runtime.
5. Every node connects to a common Sovereign MCP memory and artifact layer.
6. Every node retains independent conversational context.
7. The conductor routes scoped information and artifacts between nodes.
8. Nodes can use local models, frontier provider CLIs, or both in one orchestration.
9. The interface displays active terminals on one dynamic canvas.
10. Pane layout automatically adapts as nodes open, close, block, or complete.
11. Each meaningful transformation can invoke a bounded debate loop.
12. Intermediate outputs are checked against explicit task thresholds before downstream use.
13. System state survives conductor replacement and application restart.
14. The operator retains authority over objectives, protected actions, and final acceptance.

The product is not a collection of browser tabs. It is not a vendor desktop-app wrapper. It is not a pile of unrelated terminals with clipboard automation. The terminal canvas is the visible shell over a persistent Sovereign execution substrate.

---

# 3. CANONICAL DEFINITIONS

## 3.1 Conductor

A replaceable Sovereign node assigned orchestration privileges.

The conductor:

- interprets the operator-approved objective;
- creates and updates a task graph;
- chooses worker capabilities;
- launches authorized nodes;
- routes scoped context;
- invokes debates and gates;
- monitors status;
- synthesizes candidate outputs;
- checkpoints orchestration state.

The conductor is not a source of final authority.

## 3.2 Worker node

A Sovereign-governed terminal session with:

- a stable node identity;
- a selected model or harness;
- an assigned role;
- a scoped task;
- an isolated or controlled workspace;
- an MCP connection;
- explicit permissions;
- local context;
- artifact publication;
- gate participation;
- lifecycle supervision.

## 3.3 Sovereign control plane

The authoritative local system for:

- node identity;
- task state;
- permissions;
- canonical directives;
- artifact state;
- gate state;
- memory promotion;
- conductor succession;
- event history;
- operator-reserved decisions.

## 3.4 MCP server

The shared access and transport layer for resources, tools, memory, evidence, artifacts, and task state.

MCP exposes Sovereign-controlled state. MCP does not own authority.

## 3.5 Terminal canvas

The graphical desktop surface containing real CLI sessions through pseudo-terminal processes.

## 3.6 Local node

A node whose model inference occurs on operator-owned hardware without contacting a frontier provider.

## 3.7 Frontier node

A node whose CLI authenticates to a remote model provider. CLI subscription access changes the access and cost path, not the location of inference.

## 3.8 Air-gapped mode

`network = none`. Every active model, service, memory component, and tool must operate locally.

## 3.9 Mixed mode

Any networked orchestration containing an arbitrary combination of local and frontier nodes. The conductor may be local or frontier.

## 3.10 Accepted output

An artifact that has satisfied its defined gate. Model agreement alone is not acceptance.

---

# 4. CANONICAL INVARIANTS

These invariants are mandatory.

## I-01 Human authority

The operator controls objectives, scope changes, protected actions, and final acceptance.

## I-02 Sovereign execution

Every conductor and worker runs through a Sovereign node runtime. No naked agentic CLI participates directly.

## I-03 Conductor interchangeability

The conductor is a runtime-selected role, not a vendor dependency.

Claude may be the first selected conductor. That selection is not an architectural invariant.

## I-04 Worker interchangeability

Models and coding harnesses are replaceable behind stable node and adapter contracts.

## I-05 Persistent state outside model context

The project must not depend on one model conversation for continuity.

## I-06 Common MCP memory

Every reasoning node connects to the common Sovereign MCP layer.

## I-07 MCP access, not authority

MCP cannot independently grant permissions, promote canonical memory, or approve gates.

## I-08 Scoped context

The conductor sends task-relevant context, not entire transcripts by default.

## I-09 Three memory tiers

Local conversational memory, private node scratch memory, and governed shared project memory remain distinct.

## I-10 No self-canonization

Workers publish candidate findings. They do not mark their own findings accepted.

## I-11 Provenance

Every shared claim and artifact records producer, task, sources, directive version, state, and hash.

## I-12 Immutable history

Canonical events and accepted artifacts are not silently overwritten.

## I-13 Conflict visibility

Conflicting writes create conflict records. No silent last-write-wins behavior.

## I-14 Bounded debate

The default debate limit is five rounds. Early stopping is permitted.

## I-15 Loose concurrence

Concurrence is desirable but not mandatory. Dissent and unresolved alternatives are retained.

## I-16 Explicit gates

Every major task has expected outputs and acceptance criteria.

## I-17 Cost-governed debate

Debates have per-run budgets, per-caller quotas, and a global concurrency cap.

## I-18 Independent judgment

The caller alone may not be the sole judge of its own debate result.

## I-19 Locality per node

Locality is a node property. A networked conductor may coordinate any local/frontier mixture.

## I-20 Air-gap honesty

Frontier CLIs cannot participate when `network = none`.

## I-21 Subscription concurrency

The default is one active frontier terminal per subscription/account. Raising the limit requires provider-specific verification.

## I-22 Hardware-bounded local concurrency

Local node count and model residency are constrained by measured RAM, VRAM, CPU, and storage behavior.

## I-23 OpenCode first-class status

OpenCode is a first-class local coding harness, not merely a temporary Codex substitute.

## I-24 Voice input only

Parakeet provides speech-to-text. No TTS component is required.

## I-25 Voice cannot expand authority

Voice commands enter the same command and permission path as typed commands.

## I-26 Audio minimization

Raw audio is transcribed and discarded by default. Diagnostic retention is local, bounded, off by default, and operator-controlled.

## I-27 Visible orchestra

The operator can inspect all active nodes through live panes or collapsed status cards.

## I-28 Conductor succession

A replacement conductor can restore the orchestration from MCP-backed checkpoints.

## I-29 Supervisor containment

Agentic CLI containment is enforced by the supervisor, workspace isolation, and operating-system boundaries, not by trusting model compliance.

## I-30 Minimal necessary control

Do not invent unrelated governance layers. Controls must enforce a stated objective, permission boundary, acceptance criterion, or failure-recovery requirement.

---

# 5. CANONICAL SYSTEM ARCHITECTURE

```text
Human Operator
      |
      v
Windows Desktop Workspace
      |
      +-- Terminal Canvas
      +-- Node Inspector
      +-- Routing and Artifact View
      +-- Approval/Intervention Queue
      +-- Global Stop and Recovery Controls
      |
      v
Sovereign Control Plane
      |
      +-- Directive Manager
      +-- Task Graph and Scheduler
      +-- Node Registry and Supervisor
      +-- Permission Broker
      +-- Gate Service
      +-- Debate Service
      +-- Context Compiler
      +-- Conductor Succession Manager
      +-- Persistence and Event Log
      |
      +--------------------+
      |                    |
      v                    v
Sovereign MCP Server    Artifact Store
      |                    |
      +--------------------+
      |
      v
Sovereign Node Runtimes
      |
      +-- Claude / Claude Code
      +-- Codex CLI
      +-- Gemini CLI
      +-- Grok-compatible CLI, when supported
      +-- OpenCode + Ollama local model
      +-- Aider or other compatible harness
      +-- local general reasoning nodes
      +-- specialist, critic, and arbitration nodes
```

---

# 6. TERMINAL CANVAS AND UI SPECIFICATION

## 6.1 Required behavior

The UI must:

- display real CLI sessions;
- show conductor and active worker panes concurrently;
- dynamically resize as panes are created or removed;
- maximize and restore any pane;
- minimize a pane to a status card;
- pin important panes;
- preserve running processes across layout changes;
- visually distinguish active, waiting, blocked, failed, paused, and completed nodes;
- show node role, model, task, debate round, gate state, and usage;
- allow operator input to a selected node;
- show which artifact or message moved between nodes;
- provide global pause and emergency stop.

## 6.2 Layout priorities

1. Waiting for operator input.
2. Conductor.
3. Failed or blocked node.
4. Active foreground worker.
5. Active background worker.
6. Paused node.
7. Completed node.

## 6.3 Layout behavior by node count

- 1 node: full canvas.
- 2 nodes: balanced split.
- 3 nodes: conductor larger than two workers.
- 4 nodes: two-by-two grid.
- 5–6 nodes: three-column or asymmetric grid.
- More than 6: active/blocked panes remain live; background/completed nodes collapse into cards or a dock.

## 6.4 Phase 1 technology default

Use:

- Electron;
- xterm.js;
- node-pty;
- Windows ConPTY.

Tauri is the named fallback.

Electron is not permanently ratified until the Phase 1 spike passes measured kill criteria.

## 6.5 Phase 1 kill criteria

Reject the Electron implementation path if any of the following remains unresolved after reasonable optimization:

- input is routed to the wrong pane;
- pane layout changes restart or corrupt terminal sessions;
- six concurrent terminals produce unacceptable UI stalls;
- eight terminals produce sustained memory growth incompatible with target hardware;
- ANSI rendering or resize behavior is unreliable;
- child-process termination or restart cannot be accurately reflected;
- ConPTY process ownership cannot be supervised safely.

---

# 7. CONDUCTOR RUNTIME

## 7.1 Runtime selection

The operator may select any compatible node as conductor.

Examples:

- Claude conductor with local and frontier workers;
- local Qwen-class conductor with Codex and Gemini workers;
- local conductor with all-local OpenCode workers;
- frontier conductor with local research and coding nodes.

## 7.2 Conductor files

The conductor role is defined by operator-controlled files, not by a vendor prompt.

Required baseline files:

```text
conductor/
├── IDENTITY.md
├── ROLE.md
├── CONDUCTOR_DIRECTIVE.md
├── ORCHESTRATION_RULES.md
├── TASK_DECOMPOSITION_RULES.md
├── CONTEXT_ROUTING_POLICY.md
├── MODEL_SELECTION_POLICY.md
├── DEBATE_POLICY.md
├── GATE_POLICY.md
├── OPERATOR_RESERVED_AUTHORITY.md
├── STOP_CONDITIONS.md
└── CURRENT_PROJECT_STATE.md
```

These files must be versioned and exposed through MCP as governed resources.

## 7.3 Startup sequence

The conductor must:

1. authenticate as a conductor-capable node;
2. verify directive version;
3. load conductor files;
4. load the latest project checkpoint;
5. load the task graph;
6. inspect active and stale nodes;
7. inspect unresolved conflicts;
8. inspect pending operator actions;
9. publish readiness;
10. begin assignments only after state coherence passes.

## 7.4 Succession

The conductor periodically publishes immutable orchestration snapshots containing:

- task graph head;
- active node set;
- node assignments;
- gate states;
- debate states;
- accepted findings;
- unresolved disagreements;
- pending actions;
- resource reservations;
- directive version.

A successor conductor must perform a staleness checklist before resuming.

---

# 8. NODE AND ADAPTER ARCHITECTURE

## 8.1 Standard node contract

Every node exposes:

```text
register()
start()
load_assignment()
load_context_manifest()
stream_events()
publish_artifact()
publish_candidate_finding()
request_context()
request_debate()
submit_gate_packet()
checkpoint()
pause()
resume()
cancel()
close()
get_usage()
get_capabilities()
```

## 8.2 Standard capability metadata

Each adapter reports:

- provider or local runtime;
- model;
- context capability;
- tool calling;
- MCP support;
- session resume;
- usage reporting;
- multimodal support;
- network requirement;
- hardware requirement;
- coding-harness status;
- subscription/account identity;
- concurrency eligibility.

## 8.3 Frontier CLI adapters

Primary path:

- provider CLI;
- subscription authentication;
- one active terminal per account by default;
- explicit network status;
- isolated workspace;
- supervisor-controlled process;
- MCP connection;
- no credential persistence in repository files.

API access may exist as an optional adapter, but it is not required for the core design.

## 8.4 Coding harness adapters

Use one coding-node contract for:

- Codex CLI;
- Claude Code;
- OpenCode;
- Aider;
- future compatible harnesses.

Codex and other frontier harnesses require network.

OpenCode paired with Ollama/local models is air-gap eligible.

## 8.5 Current local-model tier

Design for local 8B–14B models now.

Do not hard-code one model as the architecture.

Phase 6 must benchmark candidate local conductors and coding models for:

- tool-call reliability;
- structured-output compliance;
- task decomposition;
- context use;
- recovery after interruption;
- coding accuracy;
- VRAM residency;
- latency under concurrent orchestration.

Larger models remain a scale-up path, not an MVP dependency.

---

# 9. MCP SHARED MEMORY AND ARTIFACT ARCHITECTURE

## 9.1 Placement

The MCP server runs as a separate local process beside the control plane.

This separation reinforces that MCP is a transport and resource interface, not the authority.

## 9.2 Transport default

For Phase 3A:

- bind only to loopback;
- use the standard MCP transport supported by selected clients;
- prefer local Streamable HTTP when all selected clients support it;
- use a supervised stdio bridge for clients that require stdio;
- authenticate every client session;
- never bind the MVP MCP server to an external network interface.

## 9.3 Memory states

```text
CANDIDATE
UNDER_REVIEW
DISPUTED
ACCEPTED
ACCEPTED_WITH_RESERVATIONS
REJECTED
SUPERSEDED
ARCHIVED
```

Only the control plane or an operator-authorized gate transition can promote memory.

## 9.4 Persistence strategy

Use:

- SQLite in WAL mode for structured state, indexes, task graph heads, node state, events, and metadata;
- a content-addressed filesystem store for artifacts;
- SHA-256 object identity;
- immutable append for records;
- compare-and-swap head pointers for current views;
- explicit conflict objects.

Do not store large artifacts or unlimited terminal logs directly in SQLite.

## 9.5 Required MCP resources

At minimum:

```text
sovereign://project/current
sovereign://directive/canonical
sovereign://directive/version
sovereign://conductor/files
sovereign://tasks/active
sovereign://tasks/{task_id}
sovereign://nodes/active
sovereign://nodes/{node_id}
sovereign://memory/accepted
sovereign://memory/candidate
sovereign://memory/disputed
sovereign://artifacts/{artifact_id}
sovereign://evidence/{evidence_id}
sovereign://gates/{gate_id}
sovereign://debates/{debate_id}
sovereign://checkpoints/latest
```

## 9.6 Required MCP tools

At minimum:

```text
register_node
load_node_context
publish_artifact
publish_candidate_finding
request_context
send_node_message
request_debate
submit_debate_position
submit_gate_packet
request_permission
report_blocker
checkpoint_node
checkpoint_conductor
close_node
```

## 9.7 Disconnect behavior

When MCP becomes unavailable:

- shared-memory-dependent work pauses;
- local node state is retained;
- nodes create local checkpoints;
- the UI shows disconnected state;
- nodes do not assume cached shared memory is current;
- reconnection requires head/version reconciliation.

---

# 10. TASK SCHEDULER AND RESOURCE PLANNER

The Scheduler is a first-class subsystem.

It selects nodes using:

- required capability;
- model availability;
- node locality;
- network status;
- subscription occupancy;
- context requirement;
- permissions;
- task priority;
- VRAM and RAM;
- existing model residency;
- estimated cost;
- expected latency.

## 10.1 Model-residency planner

Current hardware may not support a 14B conductor, a 7–14B coding worker, Parakeet, and other local nodes resident simultaneously.

The planner must:

- inspect measured VRAM/RAM;
- account for quantization and context allocation;
- serialize or unload models where required;
- prefer already-resident models when suitable;
- prevent out-of-memory launch attempts;
- expose resource reservations in the UI;
- distinguish process concurrency from model-residency concurrency.

## 10.2 Subscription governor

The governor tracks one active frontier terminal per subscription/account.

It must reject or queue a second terminal unless:

- a separate account/subscription is configured; or
- the operator explicitly raises the limit after provider-specific verification.

---

# 11. DEBATE SERVICE

## 11.1 Purpose

Debate is a reusable service that any authorized node may request.

It is not owned by the current conductor.

## 11.2 Default five-round protocol

1. Initial construction.
2. Adversarial critique.
3. Alternative construction.
4. Evidence reconciliation.
5. Final bounded revision.

The service may stop early when:

- required criteria are satisfied;
- no material defect remains;
- evidence is exhausted;
- improvement becomes negligible;
- cost limit is reached;
- operator input is required.

## 11.3 Output packet

Each debate returns:

- leading conclusion;
- supporting evidence;
- dissenting positions;
- unresolved questions;
- material assumptions;
- confidence range;
- directive-compliance result;
- recommended gate action;
- token/cost/resource usage.

## 11.4 Cost Governor

The Debate Service must enforce:

- a hard per-debate budget;
- per-caller quotas;
- global concurrent-debate limit;
- Permission-Broker authorization;
- early termination;
- no caller-only self-approval.

---

# 12. GATE SERVICE

## 12.1 Verdicts

```text
PASS
PASS_WITH_RESERVATIONS
REVISION_REQUIRED
BLOCKED
ESCALATE
STOP
FAIL
```

## 12.2 Required evaluation dimensions

- objective alignment;
- scope compliance;
- required-output completeness;
- evidence coverage;
- factual support;
- internal consistency;
- uncertainty disclosure;
- format/schema compliance;
- permission compliance;
- downstream usability;
- reproducibility where applicable.

## 12.3 Gate principle

A gate checks an explicit requirement. It must not become an excuse to add ceremonial review layers.

---

# 13. VOICE INPUT SERVICE

## 13.1 Role

NVIDIA Parakeet is an input transducer, not a reasoning node.

## 13.2 Flow

```text
Push to talk
  -> capture
  -> Parakeet transcription
  -> confidence
  -> proposed typed command
  -> operator preview when needed
  -> normal Permission Broker path
  -> logged control event
```

## 13.3 Audio policy

Default:

- transcribe;
- record transcript and command provenance;
- delete raw audio.

Optional diagnostic mode:

- operator-enabled only;
- local-only;
- default seven-day TTL;
- access controlled;
- automatic purge;
- disabled in ordinary operation.

## 13.4 Phase position

Voice is post-MVP. Do not let it delay the terminal, node, MCP, conductor, debate, or gate foundations.

---

# 14. PERMISSION AND CONTAINMENT MODEL

## 14.1 External enforcement

Do not trust an agentic CLI to enforce Sovereign policy against itself.

Enforcement must exist in:

- node supervisor;
- process launch configuration;
- workspace boundaries;
- filesystem access;
- Git worktrees;
- network policy;
- command allow/deny rules;
- credential isolation;
- operator approval for protected actions.

## 14.2 Protected actions

Require operator approval for:

- deletion outside the isolated project root;
- remote push;
- release publication;
- credential changes;
- provider-account changes;
- payment or purchase;
- external messaging;
- changes to canonical operator authority;
- disabling audit or recovery mechanisms.

## 14.3 Terminal/control separation

Terminal output is untrusted text.

Machine control events travel through authenticated structured channels. A model cannot gain control authority by printing a string that resembles a system message.

---

# 15. RECOMMENDED IMPLEMENTATION STACK

These are executable defaults, not eternal commitments.

## 15.1 Desktop

- Electron
- TypeScript
- React or a minimal equivalent component layer
- xterm.js
- node-pty / ConPTY

Fallback:

- Tauri plus a proven PTY bridge if Phase 1 kill criteria reject Electron.

## 15.2 Control plane

- Python 3.12
- typed models and validation
- asynchronous process/event management
- explicit package boundaries

## 15.3 Persistence

- SQLite WAL
- content-addressed artifact filesystem
- SHA-256
- immutable event append
- CAS head pointers

## 15.4 UI/control-plane IPC

Default for MVP:

- authenticated loopback WebSocket;
- JSON-RPC-style commands;
- typed event envelopes;
- reconnect and replay cursor;
- no external bind.

## 15.5 MCP

- separate local process;
- standard protocol transport;
- loopback only;
- authenticated node identity;
- per-node capabilities and access scopes.

## 15.6 Testing

- Python unit/integration tests;
- TypeScript UI tests;
- PTY integration harness;
- fault-injection tests;
- recovery tests;
- security boundary tests;
- performance measurements at 1, 2, 4, 6, 8, and 12 terminal panes.

---

# 16. REPOSITORY STRUCTURE

```text
sovereign-orchestration-workspace/
├── README.md
├── pyproject.toml
├── package.json
├── docs/
│   ├── canonical/
│   ├── architecture/
│   ├── decisions/
│   ├── phase_reports/
│   └── threat_model/
├── apps/
│   └── desktop/
├── control_plane/
│   ├── directives/
│   ├── tasks/
│   ├── scheduler/
│   ├── nodes/
│   ├── routing/
│   ├── permissions/
│   ├── gates/
│   ├── debates/
│   ├── succession/
│   ├── persistence/
│   └── recovery/
├── mcp_server/
│   ├── resources/
│   ├── tools/
│   ├── auth/
│   ├── access_control/
│   ├── provenance/
│   ├── events/
│   └── conflict/
├── node_runtime/
│   ├── supervisor/
│   ├── context/
│   ├── workspace/
│   ├── checkpoints/
│   └── protocol/
├── adapters/
│   ├── base/
│   ├── claude/
│   ├── codex/
│   ├── gemini/
│   ├── opencode/
│   ├── aider/
│   ├── ollama/
│   └── voice_parakeet/
├── terminal/
│   ├── conpty/
│   ├── compositor/
│   ├── session/
│   └── logs/
├── conductor/
│   ├── IDENTITY.md
│   ├── ROLE.md
│   ├── CONDUCTOR_DIRECTIVE.md
│   ├── ORCHESTRATION_RULES.md
│   ├── TASK_DECOMPOSITION_RULES.md
│   ├── CONTEXT_ROUTING_POLICY.md
│   ├── MODEL_SELECTION_POLICY.md
│   ├── DEBATE_POLICY.md
│   ├── GATE_POLICY.md
│   ├── OPERATOR_RESERVED_AUTHORITY.md
│   ├── STOP_CONDITIONS.md
│   └── CURRENT_PROJECT_STATE.md
├── schemas/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── terminal/
│   ├── security/
│   ├── recovery/
│   ├── performance/
│   └── evaluation/
├── examples/
└── tools/
```

---

# 17. BUILD PHASES

Fable is authorized to execute these phases sequentially. A failed gate stops progression.

## Phase 0: Canonical freeze and repository foundation

Build:

- isolated repository;
- source-provenance register;
- clean UTF-8 architecture plan;
- canonical terms and invariants;
- decision register;
- unresolved register;
- repository structure;
- interface/schema stubs;
- threat model;
- development and test commands;
- local Git baseline.

Exit:

- clean source artifacts and hashes;
- no unresolved contradiction in core architecture;
- interfaces named and versioned;
- build environment reproducible;
- repository tests can run;
- no mutation outside project root.

## Phase 1: Terminal compositor spike

Build:

- desktop shell;
- 1, 2, 4, 6, 8 terminal panes;
- dynamic layout;
- pane focus;
- maximize/restore;
- minimize-to-card;
- process launch, stop, restart;
- output capture;
- state synchronization;
- measured memory and CPU report.

Exit:

- six stable concurrent terminals;
- correct input routing;
- layout changes preserve sessions;
- process failure accurately shown;
- kill criteria evaluated;
- UI stack decision recorded.

## Phase 2: Node process manager

Build:

- node registry;
- lifecycle states;
- supervisor;
- heartbeat;
- workspace assignment;
- event stream;
- status cards;
- process recovery.

## Phase 3: Sovereign node runtime

Build:

- directive loader;
- role loader;
- context manifest;
- permissions;
- structured events;
- artifact publication;
- local checkpoint;
- gate packet interface.

## Phase 3A: MCP shared-memory foundation

Build:

- separate MCP server;
- node authentication;
- resources and tools;
- memory state lifecycle;
- SQLite WAL schema;
- content-addressed store;
- immutable append;
- CAS heads;
- conflict objects;
- conductor-file resources;
- access control;
- disconnect/recovery tests.

Exit:

- shared memory survives restart;
- candidate and accepted memory separated;
- worker cannot write canonical directive;
- every write has provenance;
- conflict cannot be silently overwritten;
- conductor replacement preserves state;
- disconnected nodes fail closed.

## Phase 4: First conductor adapter

Build one full path with the currently selected conductor, likely Claude through its CLI.

The adapter must remain replaceable.

## Phase 5: Conductor prototype

Conductor launches two workers, assigns scoped tasks, routes one artifact, invokes one gate, and checkpoints state.

## Phase 6: Multi-model and local-model adapters

Integrate:

- one conductor-capable frontier CLI;
- Codex or another frontier coding CLI;
- OpenCode + Ollama local coding node;
- one local general reasoning model.

Run benchmark matrix for 8B–14B candidates.

## Phase 7: Debate Service

Build the bounded, cost-governed reusable debate service.

## Phase 8: Gate Service

Build task-specific gates and revision routing.

## Phase 9: Context Compiler and routing

Build scoped context packages, inclusion/exclusion manifests, artifact references, and token/cost measurement.

## Phase 10: Coding isolation

Build Git worktrees, controlled patch publication, tests, merge preparation, and rollback.

## Phase 11: Persistence and conductor succession

Build restart recovery, stale-node reconciliation, immutable conductor snapshots, and replacement-conductor resume.

## Phase 12: Voice input

Integrate Parakeet STT after the MVP substrate is stable.

## Phase 13: Evaluation and hardening

Compare:

- single model;
- conductor with raw workers;
- Sovereign workers without debate;
- Sovereign workers with bounded debate.

Measure total cost to accepted output, drift, rework, evidence quality, latency, operator correction burden, and failure recovery.

---

# 18. PHASE 0 EXECUTION DIRECTIVE

Fable must begin here.

1. Locate all supplied handoff and architecture artifacts.
2. Record exact paths, sizes, hashes, and encoding.
3. Preserve the original architecture plan with hash `668089...E48F`.
4. Produce a clean UTF-8 copy.
5. Create a line-level repair report proving only encoding repair.
6. Create the isolated project repository.
7. Do not modify an existing Sovereign repository.
8. Create the canonical directory and conductor files.
9. Extract and normalize all invariants and decisions.
10. Create versioned JSON schemas for nodes, tasks, messages, artifacts, memory, debates, gates, permissions, checkpoints, and usage.
11. Create the decision and unresolved registers.
12. Create the initial threat model.
13. Create test scaffolding and one command that runs all currently available tests.
14. Create a Phase 0 report with evidence.
15. Commit locally only after the Phase 0 gate passes.

Phase 0 does not produce the full application. It produces the frozen build substrate.

---

# 19. PHASE 1 EXECUTION DIRECTIVE

After Phase 0 passes:

1. Implement the minimal Electron/xterm.js/node-pty desktop spike.
2. Use real ConPTY sessions.
3. Do not integrate model providers yet.
4. Prove terminal lifecycle and layout first.
5. Measure 1, 2, 4, 6, 8, and 12 panes.
6. Record process count, application memory, CPU, input latency, resize behavior, and failure recovery.
7. Test long streaming output.
8. Test rapid pane creation and removal.
9. Test maximize/restore repeatedly.
10. Test wrong-pane input prevention.
11. Evaluate all kill criteria.
12. Either ratify Electron or produce the evidence-backed Tauri fallback recommendation.
13. Create a Phase 1 evidence package and local commit.

---

# 20. PHASE 3A EXECUTION DIRECTIVE

After Phase 2 and Phase 3 foundations pass:

1. Implement MCP as a separate local process.
2. Bind only to loopback.
3. Authenticate all nodes.
4. Implement scoped resource and tool access.
5. Implement SQLite WAL metadata.
6. Implement the content-addressed artifact store.
7. Implement immutable records and CAS head pointers.
8. Implement explicit conflict objects.
9. Implement conductor files as governed MCP resources.
10. Implement candidate versus accepted memory.
11. Implement append-only event history.
12. Implement restart and disconnect recovery.
13. Implement a worker-write denial test against canonical directives.
14. Implement concurrent-write conflict tests.
15. Implement conductor replacement and state recovery.
16. Create the Phase 3A evidence package and local commit.

---

# 21. ACCEPTANCE TEST MATRIX

## Terminal

- correct input focus;
- no cross-pane input;
- live resize;
- preserved sessions;
- maximize/restore;
- collapse/restore;
- process restart;
- failure detection;
- stable streaming output.

## Node

- correct identity;
- correct assignment;
- scoped context;
- permission enforcement;
- isolated workspace;
- structured artifact;
- checkpoint;
- accurate status.

## MCP

- authenticated access;
- unauthorized read denied;
- unauthorized write denied;
- candidate cannot self-promote;
- provenance complete;
- conflict recorded;
- restart persistence;
- disconnect fail-closed;
- conductor replacement.

## Scheduler

- subscription governor;
- local/frontier mixing;
- air-gap exclusion;
- resource reservation;
- VRAM overcommit prevention;
- queueing;
- model unload/reload.

## Debate

- five-round cap;
- early stop;
- dissent retained;
- hard cost cap;
- caller cannot self-approve;
- traceable round artifacts.

## Gate

- pass advances;
- fail stops;
- reservation visible;
- revision routes correctly;
- escalation reaches operator;
- reasons traceable.

## Security

- terminal spoofed control message ignored;
- prompt injection does not change canonical directive;
- unauthorized file access blocked;
- unauthorized network access blocked;
- second terminal on occupied subscription queued or rejected;
- credential not written to repository;
- destructive action outside root denied.

## Recovery

- application restart;
- MCP restart;
- conductor crash;
- worker crash;
- stale node;
- artifact hash validation;
- corrupted head pointer recovery;
- conflict reconciliation.

---

# 22. BUILD REPORTING REQUIREMENTS

Every phase report must contain:

- objective;
- source state;
- files created or modified;
- commands executed;
- test results;
- measured performance;
- deviations;
- unresolved issues;
- gate verdict;
- Git commit hash, if committed;
- next authorized phase.

Do not report an unverified claim as a completed fact.

Do not use polished prose to conceal a failed test.

---

# 23. STOP CONDITIONS

Stop and report when:

- a phase exit criterion fails;
- an action requires credentials;
- an action would alter an unrelated repository;
- provider terms are unclear and the implementation would depend on the disputed behavior;
- a destructive action is required outside project root;
- a proposed change alters operator authority;
- the terminal framework hits a kill criterion;
- MCP cannot preserve conflict/provenance requirements;
- a test result contradicts a canonical invariant;
- source artifacts are missing or corrupted beyond deterministic repair.

A stop is not a failure to work. It is a bounded engineering result with evidence.

---

# 24. PROHIBITED DRIFT

Do not:

- rebuild CNVS as a visual clone;
- make macOS a dependency;
- replace CLI panes with hidden agents;
- make Claude or another vendor the permanent conductor;
- require API billing for the core product;
- treat subscription CLI access as offline inference;
- open multiple frontier terminals on one subscription by default;
- force consensus;
- use model votes as evidence;
- allow agents to write canonical memory directly;
- make MCP the authority;
- add TTS;
- make voice an MVP blocker;
- store raw voice audio by default;
- create recursive uncontrolled node spawning;
- trust CLI self-sandboxing;
- add ceremonial approval layers unrelated to stated risks;
- claim production readiness without evaluation.

---

# 25. CURRENT DECISIONS

## Accepted

- Windows-native.
- CLI-first.
- Dynamic visible terminal canvas.
- Sovereign runtime in every conductor and worker.
- MCP shared memory is MVP-foundational.
- Conductor is runtime-selected and interchangeable.
- Models and harnesses are interchangeable.
- Locality is per node.
- Local/frontier mixing is permitted when networked.
- Strict air-gap is all-local.
- One frontier terminal per subscription/account by default.
- OpenCode is a first-class local coding harness.
- Current local target is 8B–14B.
- Debate cap is five rounds.
- Concurrence is loose, not mandatory.
- Debate Service is reusable and cost-governed.
- Conductor succession uses persistent snapshots.
- Parakeet provides STT-only voice input.
- Raw audio is discarded by default.
- SQLite WAL plus content-addressed artifacts is the MVP persistence strategy.
- Immutable append plus CAS heads is the conflict strategy.
- Supervisor-level containment is mandatory.

## Executable defaults pending measured confirmation

- Electron/xterm.js/node-pty/ConPTY.
- Python 3.12 control plane.
- Loopback authenticated WebSocket for UI/control-plane IPC.
- Local standard MCP transport with stdio bridge where required.

These defaults do not require a new planning cycle. Build and test them. Replace them only when evidence fails the defined criteria.

---

# 26. UNRESOLVED ITEMS

These do not block Phase 0 or the terminal spike.

- Exact frontier-provider subscription automation terms.
- Per-provider support for standard MCP connection.
- Best local conductor checkpoint in the 8B–14B tier.
- Best local coder in the 7B–14B tier.
- Parakeet real-time latency and VRAM use.
- Windows microphone-to-WSL capture path.
- Maximum comfortable terminal count on target hardware.
- Whether Tauri is needed after the Electron spike.
- Long-term distributed/multi-machine operation, which is out of MVP scope.

---

# 27. REQUIRED FIRST RESPONSE FROM FABLE 5

Fable must begin its build chat by returning:

1. Acknowledgment that this is build authorization, not another architecture-only request.
2. The exact source artifacts it can access.
3. Their hashes and encoding state.
4. The proposed isolated repository path.
5. The current Git state, if a repository already exists.
6. The Phase 0 work order.
7. Any immediate hard blocker.
8. Confirmation that no external push, credential use, or unrelated-repository mutation will occur.

Then execute Phase 0.

---

# 28. FINAL CANONICAL STATEMENT

The Sovereign Multi-Terminal Orchestration Workspace is one persistent Sovereign system containing replaceable conductor and worker nodes.

Each node may be local or frontier-backed.

Every node uses the same task, memory, artifact, permission, debate, gate, and recovery contracts.

MCP provides governed shared access.

The control plane preserves authority and continuity.

The scheduler manages capabilities, subscriptions, and hardware residency.

The Debate Service improves intermediate artifacts without requiring forced agreement.

The terminal canvas makes the orchestra visible.

The conductor coordinates.

Models reason.

Sovereign preserves the system.

The human operator remains final authority.
