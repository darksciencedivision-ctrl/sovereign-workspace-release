# Fable 5 Directive — Sovereign Multi-Terminal Orchestration Workspace
**Standalone, paste-ready extract of Part 3 — canonical handoff v2.4 (2026-07-15).** For the full validation report and canonical amendments, see the combined handoff document.

---

# PART 3 — FABLE 5 DIRECTIVE PROMPT PLAN (PASTE-READY)

> The text between the rulers below is written to be delivered to Fable 5 (or an equivalent engineering-analysis model) as a single directive prompt. It supersedes baseline §22 by incorporating the voice (Parakeet, STT-only), Codex, deployment-profile, and MCP shared-memory amendments. It changes no approved objective; it makes the existing objective buildable.

---

## DIRECTIVE: SOVEREIGN MULTI-TERMINAL ORCHESTRATION WORKSPACE — ARCHITECTURE AND BUILD PLANNING

### A. Authority
The human operator is the final authority over objectives, scope, architecture promotion, and acceptance. You (Fable 5) act as an engineering analyst and candidate conductor-architect. You are **not** authorized to redefine the objective, expand scope, promote implementation status, grant permissions, or substitute your preferences for operator requirements. Where you must choose, present options with trade-offs and mark operator-reserved decisions.

### B. Primary objective (restate; do not expand)
Produce a complete, implementation-ready architecture and phased build plan for a **Windows-native, CLI-first, multi-model orchestration workspace** in which every conductor and worker terminal runs as a **Sovereign-governed node**, all nodes share governed project memory through a **Sovereign MCP server**, the operator can drive the system by **voice input**, and the system can run in **offline, hybrid, or cloud** deployment profiles without changing the Sovereign contract.

### C. Required architectural invariants (build to all of these)
1. The conductor coordinates; Sovereign governs; models reason; the operator retains authority.
2. Every conductor and worker terminal is a Sovereign node. **No raw/naked model or agentic-CLI session** participates in orchestration.
3. Conductor and worker models are **interchangeable** behind stable adapter contracts. The conductor is an **interface**; its **current runtime selection** is operator-chosen (today Claude) and recorded in MCP — no model is the architectural default. It must be replaceable mid-project, and on failure via succession, without changing the Sovereign contract.
4. Concurrence is preferred, not mandatory; unresolved disagreement is preserved.
5. Debate is bounded (default max 5 rounds), evidence-based, task-specific, early-stoppable, and never an unbounded token loop.
6. Every major stage ends at a gate; failed artifacts cannot silently advance.
7. **Voice is input-only** (STT). No TTS. Voice cannot bypass permissions; ambiguous commands require clarification; destructive commands require operator approval. Text and voice produce equivalent control events.
8. The **Voice Input Service** (NVIDIA Parakeet) is a transducer class, **not** a reasoning node; it is exempt from debate/gate lifecycles but runs under Sovereign governance and MCP logging.
9. Agnosticism is a property of the **adapter contract**, not any engine. Hardware dependencies (NVIDIA GPU/WSL for Parakeet and local models) are recorded, not hidden.
10. **Deployment profiles** (offline/air-gapped, hybrid, cloud) share a semantically identical Sovereign contract (identical schemas and enforcement); only adapter/client eligibility differs. Cloud-inference adapters/clients (**Codex, cloud models, Claude CoWork**) are **excluded from the offline profile**.
11. Every Sovereign node connects to a **common Sovereign MCP server** for governed access to shared memory, directives, artifacts, task state, evidence, and decisions. Manual transcript/clipboard routing is prohibited.
12. **MCP is access/transport, not authority.** Sovereign owns authorization, canonical state, identity, gates, and human-reserved decisions.
13. Three memory tiers (local conversational / shared project / private node) are distinct; model text becomes project truth only via a structured MCP publish that passes a gate or operator decision. Workers may publish `CANDIDATE`, never self-canonize.
14. Project intelligence lives in Sovereign-controlled memory/artifacts/directives/state exposed through MCP. The model session is replaceable; the project memory is not.
15. **Subscription-CLI access, one terminal per subscription:** frontier models are integrated via provider CLIs under subscription auth (Claude Code, Codex CLI, Gemini CLI), launched as terminal nodes — **one active terminal per subscription/account by default** (multiple frontier models = multiple subscriptions, one terminal each). API keys are an optional fallback. A frontier-CLI node and a local node are interchangeable at the node interface, but CLI access is **not** offline access; frontier CLIs require network and stay excluded from the air-gapped profile. **Locality is per-node and freely mixable when networked** (offline conductor + online workers, or vice versa).
16. **Offline defaults (current hardware = 8B–14B):** the offline conductor defaults to a local tool-use model (Qwen3 8–14B-class) and its coding worker to **OpenCode + a local coder (Qwen2.5/Qwen3-Coder 7–14B)** via Ollama; larger local models are a future scale-up. All models are operator-swappable and benchmarked in Phase 6; Claude is the hybrid/cloud initial conductor.
17. **Voice audio:** transcribe-then-discard by default; optional bounded, local-only, off-by-default diagnostic retention. Voice audio never egresses under the offline profile.
18. **Locality is a node property (I-L1):** local vs frontier is per-node; the conductor/control plane are locality-agnostic; any conductor drives any mix when networked.
19. **Conductor = interface (I-CN1):** the architecture knows only the Conductor interface; the current conductor is a runtime selection in MCP, not a vendor default.
20. **Conductor succession (I-CS1):** the conductor serializes full state to MCP; on loss the operator resumes by selecting any conductor model, which rebuilds from MCP — no project/context loss.
21. **Debate is a reusable service (I-DS1):** any authorized node may request debate; the service enforces bounded rounds, evidence, dissent, gates, and cost caps; the Scheduler/Permission-Broker gate who may request and enforce budgets.
22. **Coding Node is harness-agnostic (I-CH1):** OpenCode/Codex/Claude Code/Aider are interchangeable behind the coding-worker adapter.
23. **Capability scheduling (I-SC1):** the conductor schedules by capability via a capability registry, not by named vendor/model.

### D. Required behaviors to specify
- **Conductor:** decompose objective; propose task graph; select workers/models by capability; launch nodes via Sovereign; route scoped context; run debates; request revisions; synthesize candidates; prepare the operator acceptance packet. Load operator conductor files at startup via MCP before assigning any work. Must not alter the canonical directive, bypass the Permission Broker, or declare final acceptance.
- **Worker:** stable node identity; assigned role; scoped context; selected model; defined workspace; explicit permissions; structured artifacts; bounded debate where assigned; local gate before downstream use.
- **Voice (Parakeet, STT-only):** push-to-talk/trigger capture → transcribe (offline NeMo or NIM) → confidence → `propose_command` (never auto-execute) → Permission Broker → approval queue if ambiguous/destructive → logged control event.
- **Codex worker (coding specialist):** isolated Git worktree; all shell/fs/git/network actions mediated by the Permission Broker; `AGENTS.md`/MCP config treated as node-controlled untrusted input; `offline_profile_eligible: false`; session-resume/compaction surfaced but project state kept outside model context.
- **OpenCode worker (offline coding specialist):** open-source terminal harness driving a local coder (Qwen2.5/Qwen3-Coder 7–14B) via Ollama; same Permission-Broker mediation, worktree isolation, and config-trust boundary as Codex; `offline_profile_eligible: true`. Codex (online) and OpenCode (offline) are symmetric behind one coding-adapter contract.
- **Subscription concurrency:** one active terminal per subscription/account by default; local-model terminals bounded only by hardware. The conductor may open however many *local* worker terminals it needs; frontier terminals are one-per-subscription.
- **Deployment profiles:** a profile loader that fails closed if a cloud adapter/client is requested under the offline profile; identical schemas across profiles.
- **MCP layer:** governed resources/tools; node authentication; role/task/project scoping; read/write and candidate/accepted separation; provenance on every entry; conflict handling (no silent last-write-wins); fail-closed disconnect.
- **Interface:** conductor + workers on one dynamic terminal canvas; auto-resize; maximize/restore/minimize/pin/pause/resume/terminate; sessions preserved across layout changes; background/completed nodes collapse to status cards; operator-required panes stay visible; routing, artifacts, gate state, node metadata, and MCP connectivity are visible.

### E. Required research tasks (investigate and compare; separate fact from assumption)
1. Windows terminal embedding options and ConPTY capabilities/constraints.
2. Desktop UI frameworks (Electron/Tauri/WinUI 3/WebView2/Avalonia/xterm.js) for many live terminals.
3. Model CLI/API adapter requirements; multi-session limits; automation/licensing/ToS constraints per provider.
4. **Codex specifics:** auth (ChatGPT account vs API key), `codex resume`/compaction behavior, parallel/cloud sessions, sandbox model, `AGENTS.md`/MCP surface, confirmation of cloud-only inference.
5. **Voice / Parakeet (Track G):** NeMo on Windows 11 + WSL; NVIDIA GPU/driver/CUDA (CC ≥ 8.0) requirements; mic capture into WSL; batch vs streaming latency; VRAM under concurrency with local reasoning models; accuracy on operator/technical vocabulary; push-to-talk vs wake trigger; command-mapping safety; v2 vs v3; NeMo-local vs NIM-cloud; CC-BY-4.0 attribution obligations.
6. **MCP:** server frameworks, resource/tool design, node authentication, access-control models, transport per profile (stdio/local socket/networked), conflict-resolution (CAS vs immutable-append), event streaming, provenance storage.
7. Sovereign control-plane integration (central vs embedded vs hybrid); node sandbox/workspace isolation (Git worktrees, WSL, containers).
8. Structured message/artifact protocols; persistence and crash recovery; security/trust boundaries.
9. Claude CoWork as a governed MCP client class; permission and logging model; offline-profile exclusion.
10. **Subscription-CLI viability:** confirm each provider's **per-account concurrency allowance** (the design uses one terminal per subscription by default — verify before ever raising it); auth/session lifecycle for Claude Code / Codex CLI / Gemini CLI; API-key fallback path.
11. **Local model benchmarking (Track E):** finalize the offline conductor (Qwen3 8–14B-class) and the OpenCode + local-coder pairing (Qwen2.5/Qwen3-Coder 7–14B) against the orchestration and coding task sets on current 8–14B-capable hardware; measure tool-calling reliability, long-context, structured output, and recovery; VRAM sizing and the scale-up path to 24B+.
12. **Coding harnesses:** compare OpenCode / Codex / Claude Code / Aider behind one coding-adapter contract (session model, tool execution, config-trust surface, local vs subscription).

### F. Required implementation outputs
Deliver all baseline outputs (system context diagram; component architecture; control-plane design; node-runtime design; conductor design; model-adapter interface; message/artifact/task-graph/gate/permission/event schemas; UI wireframe + pane-layout algorithm; persistence and crash-recovery; workspace isolation; threat model; testing strategy; phased roadmap; MVP definition; technology recommendation; prototype repo structure; dependency list; risk register; acceptance matrix), **plus** these amendment-specific outputs:
- Voice Input Service adapter interface + capability metadata + command-safety flow.
- Deployment-profile model (offline/hybrid/cloud) with adapter/client eligibility matrix and fail-closed profile loader.
- Codex worker-adapter wrapper spec (broker mediation, worktree isolation, config-trust boundary).
- MCP server component design, resource catalog, tool catalog, node-auth model, access-control model, memory schema, memory-state lifecycle, provenance schema, conductor-file loading process, worker context-loading process, CoWork access model, disconnect/recovery, conflict resolution.
- Subscription-CLI adapter spec (wrapping provider CLIs under subscription auth; **one-terminal-per-subscription concurrency governor**; ToS-compliance checks; API-key fallback path).
- OpenCode offline coding-adapter spec (harness + local model via Ollama; Permission-Broker mediation; worktree isolation; symmetric to the Codex adapter).
- Six-subsystem decomposition (Desktop Workspace, Conductor-interface, Sovereign Runtime, MCP, Debate Service, Scheduler, Node Runtime, Adapters).
- Conductor-interface spec + current-conductor record; Conductor Succession spec (state-serialization schema, cadence, resume/select flow).
- Debate Service spec (request API, round/evidence/gate managers, cost governor, caller authorization).
- Coding Node adapter (harness-agnostic: OpenCode/Codex/Claude Code/Aider × local/frontier model).
- Scheduler + capability registry (capability descriptors; capability→node resolution over the Task Graph).
- Offline-profile default roster (local conductor + local coding worker) with the Phase 6/Track E benchmark plan that finalizes the checkpoints.
- Voice audio-retention implementation (transcribe-then-discard; optional bounded local diagnostic retention with TTL purge).

### G. Required repository plan (propose; justify any deviation)
Extend the baseline structure with:
```text
sovereign-orchestration-workspace/
├── apps/desktop/
├── control_plane/{directives,tasks,nodes,routing,gates,permissions,artifacts,recovery,profiles}/
├── mcp_server/{resources,tools,auth,access_control,provenance,events,conflict}/
├── debate_service/{round_manager,evidence_manager,gate,cost_governor}/
├── scheduler/{capability_registry,resolver,queue}/
├── node_runtime/{supervisor,debate_client,gate,context,workspace}/
├── adapters/{base,conductor,coding/{opencode,codex,claude_code,aider},local,frontier,voice_parakeet}/
├── conductor/            # operator-created conductor files (IDENTITY, ROLE, *_POLICY, CURRENT_PROJECT_STATE)
├── terminal/{conpty,compositor,session}/
├── schemas/
├── tests/{unit,integration,security,recovery,evaluation}/
├── examples/
├── docs/
└── tools/
```

### H. Required planning order
Restate objective → identify hard constraints → separate facts/assumptions → identify unknowns → define invariants → define architecture (incl. MCP layer + profiles + voice + Codex) → define trust boundaries → define interfaces/schemas → define state, MCP memory, and persistence → define UI behavior → define failure modes → define phased build plan → define tests/acceptance gates → identify unresolved operator decisions.

### I. Phased build plan (exit-criteria driven)
- **Phase 0** — Canonical spec freeze (incl. this amendment layer).
- **Phase 1** — Terminal compositor spike (≥6 concurrent terminals, resize, capture, isolation).
- **Phase 2** — Node process manager (registry, states, heartbeat, event log).
- **Phase 3** — Sovereign node runtime (directive/role/permission loaders, local gate, structured output).
- **Phase 3A (NEW, before broad orchestration)** — **MCP shared-memory foundation:** MCP server, node auth, resource/tool registries, project-memory schema, conductor-file resources, artifact/task/evidence resources, access control, event logging, versioning, conflict handling, health checks. *Exit:* shared memory survives CLI restart; nodes retain independent local context; every shared write has provenance; candidate/accepted separated; canonical directive not worker-writable; CoWork access logged and permission-controlled; conductor replacement preserves memory; MCP disconnect does not corrupt state. **MVP status: foundational (operator ruling v2.1) — included in the MVP; update baseline §17 accordingly (see §2.11).**
- **Phase 4** — First model adapter (Claude as initial conductor path).
- **Phase 5** — Conductor prototype (launch/assign 2 workers via Sovereign + MCP; route 1 artifact; all transfers logged); capability-based assignment via the Scheduler.
- **Phase 6** — Multi-model adapters (≥3 backends incl. **Codex** as coding specialist and ≥1 local model); capability-based selection.
- **Phase 7** — Debate **Service** (reusable; any authorized node may request; ≤5 rounds, early stop, dissent preserved, cost caps; caller authorization + budget enforcement).
- **Phase 8** — Gate engine (failed artifacts cannot advance; reasons traceable).
- **Phase 9** — Context compiler and routing (no default full-transcript forwarding; token reduction measured).
- **Phase 10** — Workspace isolation and coding support (Git worktrees; controlled merge).
- **Phase 11** — Persistence, recovery, and **conductor succession** (periodic conductor-state serialization to MCP; hot Resume→Select→reconstruct; restart restores project; new conductor resumes with no context loss).
- **Phase 12** — **Voice control (STT-only, Parakeet):** push-to-talk, transcription, command preview, approval for destructive commands, node selection/dictation, transcript log. *Exit:* voice cannot bypass permissions; ambiguous commands require clarification; text and voice produce equivalent control events; offline profile transcribes with `network = none`.
- **Phase 13** — Evaluation and hardening against simpler baselines (single model; conductor + raw workers; Sovereign workers no debate; Sovereign workers + bounded debate).

### J. Prohibited drift (do not)
Turn this into a generic governance platform; add unrelated approval layers; replace visible CLI terminals with opaque agents; make the conductor a permanent vendor dependency; allow raw model or **naked agentic-CLI (e.g., Codex)** sessions outside Sovereign; force consensus; treat model votes as evidence; assume more agents always improve quality; begin implementation before architecture/interfaces are defined; silently redefine the objective; recommend macOS-only dependencies; **add a TTS component**; **make voice control an MVP prerequisite**; **treat Parakeet as a reasoning node**; **make Codex or any cloud client mandatory / include it in the offline profile**; let the **MCP server become an authority**; allow **silent last-write-wins** on canonical memory; let **CoWork silently modify canonical files**; build around vendor desktop apps/browser UIs; **treat any single model as the architectural default conductor (it is a runtime selection, not a default)**; **couple debate to the conductor so other nodes cannot request it**; **hard-code vendor/model names where a capability descriptor belongs**; **equate CLI/subscription access with offline capability**; **open more than one terminal per subscription by default (the rule is one terminal per subscription unless the provider's per-account concurrency is verified)**; grant autonomous destructive system access.

### K. Required registers
Maintain a **decision register** (ID, question, options, evidence, trade-offs, recommendation, operator-approval-required, status) and an **unresolved-issue register** (unknown provider/voice/MCP constraints, framework choice, security/performance uncertainties, operator decisions, deferred features). Seed them from Part 1 §1.4 and Part 2 §2.9 / §2.10.10, including the open items: deployment-profile ratification (I-D1/I-D2), CoWork/offline exclusion (D-COWORK-02), subscription ToS/concurrency (D-ACCESS-02), Parakeet latency/VRAM (Track G), and MCP conflict-resolution choice. Findings 6/8 and the Codex offline substitute are resolved (D-COND-02, D-VOICE-04, D-CODEX-03).

### L. Completion standard
The directive is complete only when the plan is detailed enough that an engineer or engineering model can begin Phase 0/1/3A without reinterpreting the product, with: coherent architecture; defined interfaces/schemas (incl. MCP + voice + profiles); explicit research tasks; documented risks; bounded MVP; phase exit criteria; isolated operator decisions; and **no silent scope drift**. Completion does not mean implementation is approved.

### M. Required final response format
Return, in order: (1) Executive assessment; (2) Requirement restatement; (3) Architecture proposal; (4) Technology options; (5) Recommended stack; (6) Research findings and unknowns; (7) Detailed implementation phases (incl. 3A and 12); (8) Repository plan; (9) Schema/interface definitions (incl. MCP + voice adapter); (10) UI design specification; (11) Threat and failure analysis; (12) Testing and evaluation plan; (13) Cost and performance considerations; (14) Operator decision points; (15) Proposed Phase 0 execution directive; (16) Proposed Phase 1 terminal-compositor directive; (17) Proposed Phase 3A MCP-foundation directive; (18) Subscription-CLI access and ToS-compliance plan; (19) Conductor-succession, Debate-Service, and Scheduler/capability-registry specs; (20) Final confidence statement with explicit uncertainty.

---

## REVISED CANONICAL INVARIANT (supersedes the baseline single-line invariant)

> Every conductor and worker model operates through a Sovereign node, and every Sovereign node connects to a common Sovereign MCP server for governed access to shared project memory, directives, artifacts, task state, evidence, and decisions. Conductor files are operator-created, model-independent assets. The conductor is an interface whose current runtime selection is operator-chosen (today Claude); no model is the architectural default. Claude CoWork may assist through the MCP server (networked modes only; excluded from the strict air-gapped mode), but neither owns the architecture. Voice is an input-only surface. Frontier models are reached through provider CLIs under subscription auth — one terminal per subscription by default — and present the same node interface as local models; locality is per-node and freely mixable when networked, though only local nodes run in the strict air-gapped profile. The system runs offline, hybrid, or cloud under one identical Sovereign contract. The model session is replaceable; the project memory is not. The conductor coordinates, Sovereign governs, models reason, and the human operator retains final authority.

---

## APPENDIX — SOURCES (verified 2026-07-15)
- NVIDIA Parakeet TDT 0.6B v2 — model card: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2
- NVIDIA Parakeet TDT 0.6B v3 (multilingual) — model card: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3
- NVIDIA ASR NIM Support Matrix (GPU/Compute Capability, Windows/WSL): https://docs.nvidia.com/nim/speech/latest/reference/support-matrix/asr.html
- NVIDIA Technical Blog — Parakeet ASR models: https://developer.nvidia.com/blog/pushing-the-boundaries-of-speech-recognition-with-nemo-parakeet-asr-models/
- NVIDIA-NeMo/Speech (framework): https://github.com/NVIDIA-NeMo/Speech
- OpenAI Codex CLI docs: https://developers.openai.com/codex/cli
- OpenAI Codex models: https://developers.openai.com/codex/models
- openai/codex (GitHub): https://github.com/openai/codex

*End of combined canonical handoff v2.4.*
