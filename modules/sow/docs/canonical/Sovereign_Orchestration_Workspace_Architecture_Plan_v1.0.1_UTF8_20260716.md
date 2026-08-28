# SOVEREIGN MULTI-TERMINAL ORCHESTRATION WORKSPACE
## Architecture and Phased Build Plan v1.0

**Document type:** Architecture proposal + phased build plan (planning deliverable; NOT an implementation authorization)
**Responds to:** Fable 5 Directive — canonical handoff v2.4 (2026-07-15), Part 3, sections A–M
**Prepared by:** Fable 5 (engineering analyst / candidate conductor-architect, non-authoritative)
**Date:** 2026-07-16
**Operator authority:** The human operator retains final authority over objectives, scope, architecture promotion, and acceptance. Every operator-reserved decision is marked `[OPERATOR]`. Nothing here promotes implementation status.

**Status flags (all explicit):**
- `ARCHITECTURE_PROPOSED: true`
- `IMPLEMENTATION_AUTHORIZED: false`
- `PHASE0_ISSUED: false` (proposed directive in §15)
- `RESEARCH_SPIKES_EXECUTED: false` (defined in §6; execution requires operator go)

---

## 1. EXECUTIVE ASSESSMENT

The v2.4 canonical handoff describes a buildable system. The objective — a Windows-native, CLI-first, multi-model orchestration workspace where every terminal is a Sovereign-governed node, all nodes share governed memory through a Sovereign MCP server, the operator can drive it by voice, and the same contract runs offline/hybrid/cloud — is internally coherent after the v2.1–v2.4 amendment layers. The three historical contradictions (Codex vs. offline; vendor-default conductor vs. agnosticism; multi-terminal CLI use vs. subscription ToS) are each resolved by an explicit mechanism already ratified or pending ratification: deployment profiles with a fail-closed loader (I-D1/I-D2), conductor-as-interface with a runtime selection record (I-CN1), and the one-terminal-per-subscription governor (I-X3).

**Overall assessment: GREEN for Phase 0/1/3A planning, with four load-bearing risks that the phase plan front-loads:**

1. **Terminal compositing on Windows is the least-substitutable technical risk.** Everything else (MCP, gates, debate, scheduler) is portable software engineering; hosting ≥6 live, interactive, resizable ConPTY sessions inside one canvas is Windows-specific and framework-constraining. Phase 1 is therefore a true spike with kill criteria, not a formality. Confidence that at least one candidate stack (Electron/xterm.js/node-pty being the most proven) passes the spike: high; confidence in any *specific* framework before the spike: medium.
2. **MCP is MVP-foundational (operator ruling v2.1) and therefore on the critical path.** The design below keeps it strictly access/transport (I-M2): a thin governed façade over Sovereign-owned state, so that a failure or compromise of the MCP layer cannot mint authority. The main engineering choice inside Phase 3A — conflict handling — is recommended as **immutable append + compare-and-swap head pointers** (§9.6), pending operator approval (D-MCP-03).
3. **VRAM concurrency is the binding constraint of the offline profile, not model quality.** A 14B-class conductor + a 7–14B coder + Parakeet on one current-generation 16 GB-class GPU do not comfortably coexist at useful quantizations; the offline profile must support **model paging / sequential residency** as a first-class scheduler behavior, not an afterthought (§13.3). Track E/G measures this before any offline-profile acceptance claim.
4. **The governance perimeter around agentic CLIs (Codex-class) is a real boundary, not a wrapper fiction, only if enforcement is at the OS/workspace layer.** The adapter cannot rely on the harness's cooperation. The design places enforcement in the Node Runtime supervisor: worktree-scoped filesystem ACLs, deny-by-default network egress policy, and broker-mediated command execution (§9.8, §11.2). A naked agentic process is refused at node registration.

Scope discipline: this plan adds **no** new objectives, no TTS, no consensus forcing, and no additional approval layers beyond the baseline's Permission Broker + gates. Where the handoff leaves a decision to the operator, this plan presents options and a recommendation and stops (§14). Voice remains post-MVP (Phase 12). Completion of this document does not authorize implementation (directive §L).

---

## 2. REQUIREMENT RESTATEMENT (no expansion)

### 2.1 Objective
Produce a Windows-native, CLI-first, multi-model orchestration workspace in which:
- every conductor and worker terminal runs as a **Sovereign-governed node** (no raw model or naked agentic-CLI session participates);
- all nodes share governed project memory, directives, artifacts, task state, evidence, and decisions through a **common Sovereign MCP server** (access/transport only; Sovereign retains authority);
- the operator can drive the system by **voice input only** (NVIDIA Parakeet, STT; no TTS), with voice unable to bypass permissions;
- the system runs in **offline/air-gapped, hybrid, or cloud** deployment modes under one semantically identical Sovereign contract, where modes are node selections over one architecture (D-ARCH-01).

### 2.2 Binding invariants (build-to list)
All 23 invariants of directive §C are binding, including: conductor coordinates / Sovereign governs / models reason / operator retains authority (C1); every terminal a Sovereign node (C2); interchangeable models behind adapter contracts with conductor-as-interface and runtime selection (C3, I-CN1); concurrence preferred not mandatory (C4); bounded evidence-based debate ≤5 rounds (C5); gates on every major stage (C6); voice input-only, non-escalating, equivalent control events (C7, I-V1..V3); Parakeet as transducer class (C8); adapter-contract agnosticism with recorded hardware dependencies (C9, I-A1); deployment profiles with cloud exclusion from offline (C10, I-D1/I-D2); common MCP server, no manual transcript routing (C11, I-M1); MCP access-not-authority (C12, I-M2); three memory tiers with candidate/accepted separation and no self-canonization (C13, I-M3..M6); project intelligence outside model context (C14); subscription-CLI primary with one terminal per subscription (C15, I-X1..X3); offline defaults at the 8–14B tier with OpenCode+local coder (C16, D-COND-02/D-CODEX-03/D-CODE-04); transcribe-then-discard voice audio (C17, D-VOICE-04); locality as node property (C18, I-L1); conductor succession via MCP state serialization (C20, I-CS1); debate as reusable cost-capped service (C21, I-DS1); harness-agnostic Coding Node (C22, I-CH1); capability scheduling (C23, I-SC1).

### 2.3 Explicit exclusions (prohibited drift, §J)
No TTS; voice is not an MVP prerequisite; Parakeet is never a reasoning node; Codex/CoWork/cloud clients are never mandatory and never offline-eligible; MCP never becomes an authority; no silent last-write-wins; no vendor-default conductor; debate not conductor-coupled; no hard-coded vendor names where a capability descriptor belongs; CLI/subscription access ≠ offline capability; one terminal per subscription unless provider concurrency is verified; no autonomous destructive access; no macOS-only dependencies; no implementation before architecture/interfaces are defined.

### 2.4 Success measure (unchanged from baseline)
Total cost to accepted output, resistance to drift, evidence quality, operator-correction burden, and recovery — not terminal count.

---

## 3. ARCHITECTURE PROPOSAL

### 3.1 One architecture, six-subsystem decomposition (per §2.13.3)

```
Operator (final authority)
    │  text / voice (Phase 12) — same command bus
    ▼
┌───────────────────────────────────────────────────────────────┐
│ DESKTOP WORKSPACE  (terminal canvas, status cards, approvals) │
└───────────────┬───────────────────────────────────────────────┘
                ▼
┌───────────────────────────────────────────────────────────────┐
│ CONDUCTOR (interface; current runtime selection recorded      │
│ in MCP — today: Claude, operator-selected)                    │
└───────────────┬───────────────────────────────────────────────┘
                ▼
┌───────────────────────────────────────────────────────────────┐
│ SOVEREIGN RUNTIME (control plane: directives, task graph,     │
│ gates, Permission Broker, node registry, event log, recovery, │
│ profile loader)                                               │
└───────┬───────────────┬───────────────┬───────────────────────┘
        ▼               ▼               ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│ MCP SERVER    │ │ DEBATE        │ │ SCHEDULER     │
│ (governed     │ │ SERVICE       │ │ (capability   │
│ shared state  │ │ (reusable,    │ │ registry +    │
│ access/       │ │ bounded,      │ │ resolver over │
│ transport)    │ │ cost-capped)  │ │ Task Graph)   │
└───────┬───────┘ └───────┬───────┘ └───────┬───────┘
        └────────────┬────┴────────────────┘
                     ▼
┌───────────────────────────────────────────────────────────────┐
│ NODE RUNTIME (per-node supervisor, debate client, local gate, │
│ context loader, workspace/worktree manager)                   │
└───────────────┬───────────────────────────────────────────────┘
                ▼
┌───────────────────────────────────────────────────────────────┐
│ ADAPTERS (conductor / worker / coding / local / frontier /    │
│ voice_parakeet — capability-described, vendor-neutral)        │
└───────────────┬───────────────────────────────────────────────┘
                ▼
   CLI harnesses (Claude Code, Codex CLI, Gemini CLI, OpenCode,
   Aider) · local models (Ollama) · Parakeet (NeMo/WSL)
```

Every node is the identical stack `Node = Sovereign Runtime client + MCP client + Adapter + CLI/harness + Model`; only the adapter/harness/model vary (D-ARCH-01). Deployment mode is emergent from node selection; the only hard constraint is air-gapped ⇒ all-local (`network = none`).

### 3.2 Control-plane placement `[OPERATOR — D-MCP-02 proposed: accept]`
Recommended topology: **central Sovereign control plane process** on the operator's machine, with the MCP server **co-located beside it as a separate process** sharing the same durable store through Sovereign-mediated writes. Rationale: (a) a central broker is required anyway for permissions and gates; (b) a separate MCP process enforces I-M2 structurally — the MCP server holds a *read/append capability* to Sovereign state, never the authorization logic; (c) crash isolation: an MCP fault cannot take down gate/permission state. The alternative (MCP embedded in the control plane) saves one process but blurs the authority boundary; rejected on I-M2 grounds. Hybrid (embedded now, split later) is acceptable if Phase 3A finds IPC overhead material — flagged as a reversible implementation detail.

### 3.3 Trust boundaries (summary; full treatment §11)
- **TB-1 Operator ↔ system:** only surface where authority enters. Text and voice converge on one command bus *before* the Permission Broker.
- **TB-2 Control protocol ↔ terminal text:** structured envelopes (signed, schema-validated) are control; anything printed by a model/harness in a terminal is untrusted output, never parsed as a command.
- **TB-3 Sovereign ↔ MCP:** MCP requests carry authenticated node identity + role + task + scope; MCP holds no authorization logic; every write is provenance-stamped and lands as CANDIDATE-tier unless the writer's role permits more.
- **TB-4 Node ↔ harness/model:** harness config (`AGENTS.md`, MCP config files, model output) is node-controlled untrusted input; enforcement is outside the harness (supervisor + broker + workspace isolation).
- **TB-5 Voice ↔ command bus:** transcripts are proposals (`propose_command`), never executions; Permission Broker + approval queue sit between.
- **TB-6 Profile boundary:** profile loader is fail-closed; a cloud adapter requested under `offline_airgapped` aborts startup with a logged violation.

### 3.4 Key runtime flows

**F1 — Task assignment (happy path):** Operator accepts objective → Conductor (loads conductor files from MCP first, C/D §D) proposes task graph → operator approves plan gate → Scheduler resolves each READY task's capability descriptor to a node (spawning via Node Runtime if needed, subject to I-X3 governor and VRAM budget) → node executes in scoped workspace → artifact published to MCP as CANDIDATE with provenance → local gate → downstream gate/debate as configured → ACCEPTED entries feed dependent tasks → conductor synthesizes → operator acceptance packet.

**F2 — Debate:** any authorized node calls `debate.request` → Permission Broker checks caller authorization + budget → Debate Service runs ≤5 evidence-based rounds with early stop → result + preserved dissent recorded to MCP → gate verdict references debate record.

**F3 — Voice command:** push-to-talk → Parakeet transcribes (audio discarded post-transcription unless diagnostic retention ON) → confidence check → `propose_command` maps to candidate control action → Permission Broker → (ambiguous ⇒ clarification; destructive/protected ⇒ approval queue) → executed as ordinary logged control event, byte-equivalent to its typed form.

**F4 — Conductor succession:** conductor serializes operating state to MCP after every major event + bounded interval → on loss, operator hits **Resume → Select model** → new conductor adapter loads conductor files + succession state from MCP → verifies directive version, task-graph version, checkpoint timestamp, node registry, unresolved conflicts → resumes assignment. No project loss (I-CS1).

**F5 — MCP disconnect:** node detects disconnect → stops shared-memory-dependent work → checkpoints local state → surfaces DISCONNECTED on canvas → on reconnect, reconciles (version vectors / head pointers) before resuming. Fail closed; stale memory is never assumed current.

---

## 4. TECHNOLOGY OPTIONS

Evidence labels used below: **[V]** = verified in the v2.4 handoff against vendor sources 2026-07-15; **[K]** = analyst knowledge, stable and low-drift but to be re-verified in Phase 0 research; **[U]** = unverified, requires the named spike.

### 4.1 Terminal embedding (the load-bearing choice)
- **ConPTY (Windows Pseudo Console API)** is the only supported Windows mechanism for hosting arbitrary interactive console apps (provider CLIs are console apps). Available since Windows 10 1809; mature on Windows 11. **[K]** Constraints: VT-sequence based (host must render VT100/xterm streams); resize is supported via `ResizePseudoConsole`; per-session pipe pair; throughput adequate for interactive CLIs but must be tested at ≥6 concurrent sessions with heavy scrollback (Phase 1 spike metric). **[U: P1]**
- **Windows Terminal is not embeddable** as a reusable control; do not build around it. **[K]**
- Bindings: `node-pty` (Node/Electron; ConPTY backend; battle-tested by VS Code) **[K]**; `portable-pty` (Rust, for Tauri) **[K]**; direct Win32 ConPTY (C#/WinUI/Avalonia) — most work, most control. **[K]**

### 4.2 Desktop UI framework
| Option | Terminal path | Pros | Cons | Spike risk |
|---|---|---|---|---|
| **Electron + xterm.js + node-pty** | proven (VS Code lineage) | best-documented many-terminal stack; fastest to Phase 1; rich canvas UI | memory footprint; Chromium baggage | lowest |
| **Tauri 2 + xterm.js + portable-pty** | proven components, less integrated | small footprint; Rust core | IPC layer between webview and pty needs care at 6+ streams | medium |
| **WinUI 3 / WebView2 hybrid** | custom VT renderer or WebView2-hosted xterm.js | most native | most engineering for terminal rendering | high |
| **Avalonia** | community terminal controls, immature | single .NET codebase | terminal control maturity unproven | high |

### 4.3 Control-plane / MCP implementation language
- **Python 3.12+**: official MCP SDK; matches the existing Sovereign runtime codebase and its tested governance idioms (fail-closed gates, anchors, OBSERVE) **[K]**; adequate performance for a control plane whose bottleneck is model latency.
- TypeScript: shares language with an Electron shell; MCP SDK also first-class; but forfeits reuse of existing Sovereign Python patterns.
- Rust/Go: performance not needed at this concurrency; slower iteration.

### 4.4 MCP transport per profile
- `offline_airgapped`: **stdio or named-pipe/loopback socket only**, `network = none`. **[V/K]**
- `hybrid`/`cloud`: loopback HTTP (streamable) with per-node bearer credentials; optional LAN exposure is an operator decision, default OFF.
- CoWork attaches as a governed MCP client in networked modes only (D-COWORK-02, ratification pending).

### 4.5 Persistence
- **SQLite (WAL mode)** for: event log, memory entries, task graph, node registry, gate records, debate records, succession snapshots. Single-writer discipline via the Sovereign process; MCP reads through a mediated API, not raw DB access.
- **Content-addressed artifact store** (sha256-named files) for artifacts/evidence blobs; DB stores refs + provenance.
- Rationale: zero-dependency, offline-eligible, crash-safe, trivially snapshottable (baseline recovery requirement). Postgres is not justified at single-operator scale.

### 4.6 Local model serving
- **Ollama** (existing operator infrastructure; Qwen3 8–14B conductor default, Qwen2.5/Qwen3-Coder 7–14B coder default — D-COND-02/D-CODEX-03) **[V]**; llama.cpp direct as fallback. Model residency managed by the Scheduler (§13.3).

### 4.7 Voice (Track G scope)
- **Parakeet TDT 0.6B v2/v3 via NeMo in WSL2** (Windows 11 path; NVIDIA CC ≥ 8.0; driver ≥ 570) **[V]**; NIM/Riva as the cloud alternative **[V]**.
- Mic capture: capture PCM on the **Windows host** (WASAPI) and stream into the WSL service over loopback gRPC/WebSocket — avoids WSL microphone passthrough fragility. **[K/U: P12 spike]**
- v2 vs v3, batch vs streaming latency, VRAM under concurrency: unmeasured **[U: Track G]**.

### 4.8 Workspace isolation
- **Git worktrees** per coding node (baseline requirement); supervisor-enforced path ACLs; deny-by-default egress for node processes (Windows Filtering Platform / firewall rules per process, or job-object + proxy); WSL/containers optional hardening later. **[K]**

## 5. RECOMMENDED STACK `[OPERATOR — D-UI-01, D-LANG-01, D-PERSIST-01]`

| Layer | Recommendation | Status |
|---|---|---|
| Desktop shell | **Electron + xterm.js + node-pty (ConPTY)** | proposed; Phase 1 spike validates; Tauri is the named fallback |
| Control plane, MCP server, Debate Service, Scheduler | **Python 3.12** (separate processes; MCP via official Python SDK) | proposed |
| Shell ↔ control plane IPC | loopback WebSocket, schema-validated envelopes | proposed |
| Persistence | SQLite WAL + content-addressed artifact store | proposed |
| Local models | Ollama | operator-established |
| Coding harnesses | OpenCode (offline) / Codex CLI + Claude Code (subscription) / Aider (drop-in) behind one adapter | directed (I-CH1) |
| Voice | Parakeet via NeMo on WSL2; host-side WASAPI capture bridge | directed engine; integration pending Track G |
| Isolation | Git worktrees + supervisor ACL + deny-by-default egress | proposed |

Nothing above is vendor-load-bearing at the architecture layer: the shell renders VT streams from any node; the control plane sees only adapter contracts and capability descriptors.

---

## 6. RESEARCH FINDINGS AND UNKNOWNS

### 6.1 Findings carried from the handoff (verified 2026-07-15) **[V]**
Parakeet: ASR-only family (FastConformer + CTC/RNN-T/TDT); 0.6B v2 led the HF Open ASR leaderboard at citation time (drifts — re-verify); v3 multilingual (25 EU languages); CC-BY-4.0; offline via NeMo; NIM requires CC ≥ 8.0, Windows via WSL. Codex CLI: local agentic harness, cloud-only inference (GPT-5.x line; names low-confidence); `codex resume` + compaction; cloud parallel surface exists. OpenCode: open-source Go TUI harness, provider-agnostic, Ollama-capable, does not store code.

### 6.2 Research task matrix (directive §E → executable spikes)
| # | Track | Question | Method | Feeds | Blocker for |
|---|---|---|---|---|---|
| R1 | Terminal | ConPTY throughput/latency ≥6 sessions, resize storms, 10k-line scrollback | Phase 1 spike harness w/ metrics | D-UI-01 final | Phase 1 exit |
| R2 | UI | Electron vs Tauri memory/CPU at 8 panes | same spike, both stacks if Electron fails budget | D-UI-01 | Phase 1 exit |
| R3 | Adapters | Per-provider CLI automation surface: headless/programmatic session control, output structuring, auth lifetime | bench per CLI | adapter specs | Phase 4/6 |
| R4 | Codex | auth model, resume/compaction hooks, sandbox flags, `AGENTS.md`/MCP surface, cloud-only confirmation | vendor docs + bench | §9.8 | Phase 6 |
| R5 | Voice (G) | NeMo-on-WSL install; WASAPI→WSL bridge; batch vs streaming latency; VRAM concurrent w/ 14B model; command-vocabulary accuracy; PTT trigger; v2 vs v3; CC-BY-4.0 attribution | Track G spike rig | §9.9 | Phase 12 |
| R6 | MCP | SDK maturity; stdio vs socket vs HTTP per profile; CAS vs immutable-append benchmarks; event streaming | Phase 3A prototype | D-MCP-03 | Phase 3A exit |
| R7 | Isolation | worktree ACL enforcement on NTFS; per-process egress deny on Windows; WSL/container option | security spike | §11 | Phase 10 |
| R8 | Subscriptions | per-account concurrency allowance per provider (verify BEFORE ever raising I-X3 above 1); ToS automation clauses | doc review + support confirmation | §18 | Phase 6 |
| R9 | Local models (E) | Qwen3 8–14B conductor + Qwen2.5/3-Coder 7–14B benchmarks: tool-call reliability, long-context, structured output, recovery; VRAM sizing; 24B+ scale path | Track E harness | offline roster freeze | Phase 6 exit |
| R10 | Harnesses | OpenCode/Codex/Claude Code/Aider behind one contract: session model, tool exec, config-trust | comparative bench | Coding Node adapter | Phase 6/10 |

### 6.3 Declared unknowns (not assumed away)
Parakeet streaming latency + VRAM under concurrency; WSL mic bridge; Codex ToS for programmatic launch; CC-BY-4.0 attribution mechanics in a shipped product; provider per-account concurrency numbers; ConPTY behavior under pathological output (full-screen TUIs like OpenCode inside a pane); MCP SDK long-session stability; NTFS ACL granularity vs worktree churn. Each lives in the unresolved-issue register (§14.3) with an owner phase.

---

## 7. DETAILED IMPLEMENTATION PHASES (exit-criteria driven; each ends at a gate)

**Phase 0 — Canonical spec freeze.** Freeze baseline v1.x + amendment layer v2.1–v2.4 + this plan's schemas (§9) as the canonical spec set with hashes registered in MCP-precursor storage (flat files + manifest until 3A exists). *Exit:* operator signs the freeze manifest; decision/unresolved registers seeded (§14); all `[OPERATOR]` items either decided or explicitly deferred. *Proposed directive: §15.*

**Phase 1 — Terminal compositor spike.** Electron+xterm.js+node-pty rig hosting ≥6 concurrent interactive ConPTY sessions (mix: cmd, PowerShell, a TUI app, a mock streaming CLI). Measure: input latency p95 < 50 ms; sustained 1 MB/s aggregate output without drop; resize correctness; session survival across layout changes; RAM/CPU envelope. Kill criteria: if Electron fails budget → rerun rig on Tauri before any framework commitment. *Exit:* metrics report + framework recommendation → operator ratifies D-UI-01. *Proposed directive: §16.*

**Phase 2 — Node process manager.** Registry (identity, class, adapter, state machine: SPAWNING/READY/ASSIGNED/BUSY/PAUSED/DISCONNECTED/TERMINATED), heartbeat, structured event log (append-only), crash detection/restart policy. *Exit:* 8-node simulated fleet runs 24 h with induced kills; no orphan processes; event log complete and ordered.

**Phase 3 — Sovereign node runtime.** Directive/role/permission loaders; local gate harness; structured-output validation; workspace binding. *Exit:* a mock-model node loads role+permissions, produces a schema-valid artifact, fails its local gate on seeded defects, and cannot write outside its workspace.

**Phase 3A — MCP shared-memory foundation (MVP-foundational, D-MVP-01).** MCP server + node auth + resource/tool catalogs (§9.5) + memory schema/lifecycle (§9.6) + conductor-file resources + artifact/task/evidence resources + access control + event streaming + versioning + conflict handling + health checks. *Exit (verbatim from directive §I plus):* shared memory survives CLI restart; nodes retain independent local context; every shared write has provenance; candidate/accepted separated; canonical directive not worker-writable; CoWork access logged + permission-controlled; conductor replacement preserves memory; MCP disconnect does not corrupt state; **conflict-handling mechanism (D-MCP-03) demonstrated under concurrent-writer test**. *Proposed directive: §17.*

**Phase 4 — First model adapter.** Claude Code wrapped as the initial conductor-path adapter (subscription auth; I-X3 governor active from day one). *Exit:* adapter passes contract conformance suite (§12.2); one-terminal rule enforced; session resume surfaced.

**Phase 5 — Conductor prototype.** Conductor loads conductor files via MCP **before any assignment**; launches/assigns 2 workers via Sovereign+MCP; routes 1 artifact; capability-based assignment through the Scheduler; all transfers logged. *Exit:* end-to-end trace shows zero manual transcript routing; every hop has provenance; plan gate + acceptance packet produced.

**Phase 6 — Multi-model adapters.** ≥3 backends: Codex CLI (coding specialist), ≥1 local model via Ollama, plus the Phase 4 conductor path; Track E benchmarks finalize the offline roster checkpoints; Track R8 subscription verification lands here. *Exit:* capability-based selection demonstrably picks by descriptor, not name; offline roster frozen with benchmark evidence.

**Phase 7 — Debate Service.** Reusable service; any authorized node may request; ≤5 rounds, early stop, dissent preserved, per-debate token budget + cost governor; caller authorization via broker. *Exit:* §2.8 debate acceptance tests pass, including non-conductor caller and budget-exhaustion cutoff.

**Phase 8 — Gate engine.** Declarative gate definitions; verdicts referencing evidence/debate records; failed artifacts cannot advance; reasons traceable end-to-end. *Exit:* seeded-defect artifacts are blocked at every stage boundary; no bypass path exists including for the conductor.

**Phase 9 — Context compiler & routing.** Scoped context assembly from MCP (role+task+need-to-know); no default full-transcript forwarding. *Exit:* measured token reduction vs. naive forwarding on the reference project; workers demonstrably receive only scoped context.

**Phase 10 — Workspace isolation & coding support.** Worktree lifecycle, controlled merge path (worker branch → gate → operator-approved merge), R7 enforcement hardening. *Exit:* §2.8 Codex isolation tests pass; cross-node mutation attempts fail and are logged.

**Phase 11 — Persistence, recovery, conductor succession.** Snapshot/restore of full control-plane state; succession serialization cadence finalized (event-driven + ≤5 min interval, tunable); Resume→Select flow in UI. *Exit:* kill-the-conductor test (§2.8) passes with zero project loss; full workspace restart restores project; succession preserves I-X3/I-L1.

**Phase 12 — Voice control (post-MVP).** Track G spike then integration per §9.9: PTT capture → transcribe → confidence → propose → broker → approval queue → logged control event; node selection + dictation modes; transcript log. *Exit (directive verbatim):* voice cannot bypass permissions; ambiguous commands require clarification; text and voice produce equivalent control events; offline profile transcribes with `network = none`; plus D-VOICE-04 retention behavior verified (discard by default; TTL purge when diagnostic retention ON).

**Phase 13 — Evaluation & hardening.** Comparative harness: (a) single model; (b) conductor + raw workers; (c) Sovereign workers, no debate; (d) Sovereign workers + bounded debate — scored on total cost to accepted output, drift resistance, evidence quality, operator-correction burden, recovery (§12.4). *Exit:* evaluation report with explicit wins/losses; hardening backlog triaged; operator decides continuation scope.

**MVP boundary (per §17-as-amended + D-MVP-01):** Phases 0–5 + 3A constitute the MVP core (structured artifact passing and persistence delivered *through* MCP); Phases 6–11 complete the orchestration product; 12–13 are post-MVP. Voice explicitly excluded from MVP.

---

## 8. REPOSITORY PLAN

Adopting the directive §G structure verbatim, with three justified additions (marked +):

```text
sovereign-orchestration-workspace/
├── apps/desktop/                      # Electron shell (renderer + main), xterm.js panes
├── control_plane/{directives,tasks,nodes,routing,gates,permissions,artifacts,recovery,profiles}/
├── mcp_server/{resources,tools,auth,access_control,provenance,events,conflict}/
├── debate_service/{round_manager,evidence_manager,gate,cost_governor}/
├── scheduler/{capability_registry,resolver,queue}/
│                                      # + queue includes model-residency planner (§13.3)
├── node_runtime/{supervisor,debate_client,gate,context,workspace}/
├── adapters/{base,conductor,coding/{opencode,codex,claude_code,aider},local,frontier,voice_parakeet}/
├── conductor/                         # operator-created files (IDENTITY, ROLE, *_POLICY, CURRENT_PROJECT_STATE)
├── terminal/{conpty,compositor,session}/
├── schemas/                           # JSON Schemas — single source of truth, versioned (§9)
├── persistence/                       # + SQLite access layer + content-addressed artifact store (single-writer)
├── voice_bridge/                      # + Windows WASAPI capture host ↔ WSL NeMo service bridge (Phase 12)
├── tests/{unit,integration,security,recovery,evaluation}/
├── examples/
├── docs/
└── tools/                             # spike rigs (P1 compositor, Track E/G harnesses), manifest/hash tooling
```

Deviations justified: `persistence/` isolates the single-writer store behind one API so MCP and control plane cannot bypass mediation (I-M2 structural support); `voice_bridge/` keeps the Windows-host capture component out of the WSL adapter (different runtime, different trust zone); residency planner in `scheduler/queue` because VRAM is a scheduling input (§13.3), not an adapter concern. Monorepo, one `schemas/` root imported by both Python and TypeScript sides; schema version pinned in every envelope.

---

## 9. SCHEMA / INTERFACE DEFINITIONS

All schemas are JSON Schema-backed, versioned (`schema@semver`), identical across deployment profiles (I-D1). Sketches below are normative shapes; field-level JSON Schema files land in `schemas/` at Phase 0 freeze.

### 9.1 Node identity & registration
```json
{
  "node_id": "uuid", "class": "conductor|worker_reasoning|worker_coding_specialist|voice_input_service",
  "adapter": "claude_code|openai_codex_cli|opencode_local|gemini_cli|aider|ollama_direct|nvidia_parakeet",
  "harness": "string|null", "model_ref": "capability-resolved, recorded post-selection",
  "locality": "local|frontier", "subscription_ref": "sub-id|null",
  "capabilities": ["CapabilityDescriptor"], "workspace": {"type": "git_worktree|dir|none", "path": "..."},
  "permission_profile_id": "...", "auth": {"mcp_credential_id": "..."},
  "state": "SPAWNING|READY|ASSIGNED|BUSY|PAUSED|DISCONNECTED|TERMINATED",
  "offline_profile_eligible": true
}
```
Registration is refused if: adapter ineligible under active profile (TB-6); subscription already has an active terminal (I-X3); no permission profile; or the process was not spawned by the Node Runtime supervisor (no naked sessions, I-C1).

### 9.2 Message envelope (control protocol — never terminal text)
```json
{
  "msg_id": "uuid", "ts": "iso8601", "schema": "envelope@1.0",
  "from_node": "node_id", "to": ["node_id|service"],
  "type": "task_assign|artifact_publish|debate_request|debate_result|gate_verdict|control_event|heartbeat|succession_snapshot|permission_request|permission_verdict",
  "task_id": "t-...|null", "payload_schema": "name@ver", "payload": {},
  "auth": {"node_credential": "...", "scope": "project/task/role"},
  "integrity": "hmac-sha256(payload)"
}
```

### 9.3 Task graph & gates
```json
{ "task_id": "t-...", "parent": "t-...|null", "deps": ["t-..."],
  "capability_req": "CapabilityDescriptor", "assigned_node": "node_id|null",
  "state": "PENDING|READY|ASSIGNED|IN_PROGRESS|AWAITING_GATE|GATED_PASS|GATED_FAIL|BLOCKED|DONE",
  "artifacts": ["sha256:..."], "gate_id": "g-...", "budget": {"tokens": 0, "wallclock_s": 0} }
```
```json
{ "gate_id": "g-...", "kind": "local|stage|plan|acceptance", "criteria": ["declarative checks"],
  "verdict": "PASS|PASS_WITH_RESERVATIONS|FAIL|null", "evidence": ["entry_id|artifact"],
  "debate_ref": "d-...|null", "decided_by": "gate_engine|operator", "reasons": ["..."] }
```
Failed artifacts cannot advance: dependent tasks stay BLOCKED until a PASS verdict exists; the conductor has no override path (only the operator does, logged).

### 9.4 Memory entry (I-M3..M6) & lifecycle
```json
{ "entry_id": "m-...", "project_id": "...", "tier": "shared_project",
  "kind": "finding|decision|evidence|artifact_ref|directive|conductor_file|succession_state",
  "status": "CANDIDATE|UNDER_REVIEW|DISPUTED|ACCEPTED|ACCEPTED_WITH_RESERVATIONS|REJECTED|SUPERSEDED|ARCHIVED",
  "provenance": { "author_node": "...", "model": "...", "task_id": "...", "ts": "...",
    "directive_version": "v2.4", "source_artifacts": [], "evidence": [], "confidence": "high|medium|low",
    "reviewers": [], "gate_result": "g-...|null", "supersedes": "m-...|null" },
  "content_hash": "sha256:...", "version": 3, "prev_version_ref": "m-...@2" }
```
Transitions enforced server-side: workers may create CANDIDATE and move own entries to UNDER_REVIEW; only gate engine or operator decisions produce ACCEPTED*/REJECTED; SUPERSEDED requires a successor ref; nothing is deleted, only ARCHIVED.

### 9.5 MCP resource & tool catalogs (access, not authority — I-M2)
**Resources (read, scope-filtered):** `sovereign://directives/{id}` (canonical, never worker-writable), `sovereign://conductor_files/*` (operator-writable only), `sovereign://tasks/graph`, `sovereign://memory/{tier}/{status}/...`, `sovereign://artifacts/{hash}`, `sovereign://evidence/{id}`, `sovereign://decisions/{register}`, `sovereign://nodes/registry`, `sovereign://profile/active`, `sovereign://conductor/current`, `sovereign://succession/latest`, `sovereign://events/stream`.
**Tools (write, broker-checked):** `publish_artifact`, `publish_memory_entry` (lands CANDIDATE), `update_task_state` (own task only), `request_debate`, `submit_gate_evidence`, `checkpoint_local_state`, `propose_command` (voice service only), `serialize_succession_state` (conductor only), `register_heartbeat`.
Every call carries authenticated node identity + project + role + task + scope; the MCP server *asks Sovereign* for the authorization verdict (or evaluates a Sovereign-signed policy snapshot) — it never owns policy.

### 9.6 Conflict handling `[OPERATOR — D-MCP-03]`
**Recommendation: immutable append + CAS head pointers.** All memory entries and artifacts are immutable, content-addressed versions; each logical key has a head pointer advanced by compare-and-swap carrying the expected previous version. CAS failure ⇒ automatic conflict record + both versions preserved + review gate; no silent last-write-wins (§2.10.9). Rationale: append-only gives free provenance, audit, and SUPERSEDED semantics; CAS confines coordination to one tiny primitive. Pure CAS-on-mutable-rows loses history; pure append without heads makes "current" ambiguous. Decided in Phase 3A after the concurrent-writer test.

### 9.7 Capability descriptor & scheduling (I-SC1)
```json
{ "capability": "coding|reasoning|review|synthesis|research|voice_stt",
  "requirements": { "tool_use": true, "min_context": 32000, "structured_output": true,
    "locality": "any|local_only|frontier_ok", "harness_class": "coding_tui|chat_cli|api|null" },
  "cost_class": "local|subscription", "priority": 1 }
```
Resolver: filter registry by hard requirements → rank by (benchmark score from Track E/R10, current load, cost class per active profile, VRAM residency cost) → if no node, request spawn via supervisor (subject to I-X3 + VRAM budget) → else queue with reason surfaced on canvas. Vendor/model names never appear in task definitions.

### 9.8 Coding Node adapter contract (I-CH1; Codex/OpenCode symmetric)
```text
init(workspace, permission_profile, model_or_subscription)   # refuses naked launch
assign(task, scoped_context)                                  # context via MCP, not transcript
execute() -> stream of proposed_actions                       # every shell/fs/git/net action → Permission Broker
export_session_state() / get_context_status()                 # surfaces resume/compaction (Codex) or session file (OpenCode)
collect_artifacts() -> [artifact]                             # from worktree, hashed, published CANDIDATE
halt(reason)
```
Obligations (both harnesses): isolated Git worktree; broker mediation of the harness's own tool loop (enforced by supervisor sandbox, not harness goodwill); `AGENTS.md`/config treated as node-controlled untrusted input — Sovereign policy is never read from it; `offline_profile_eligible`: Codex false / OpenCode+local true.

### 9.9 Voice Input Service adapter (I-V1..V3; §2.4 adopted verbatim)
Interface: `start_capture / stop_capture / transcribe(audio_ref) / stream_transcribe / get_confidence / propose_command / get_usage / close`. Capability metadata as in handoff §2.4. Command safety flow: transcript+confidence → `propose_command` (never auto-executes) → broker → clarification (ambiguous) or approval queue (destructive/protected) → logged control event *identical in schema and effect to the typed form*. Audio retention: transcribe-then-discard default; `diagnostic_retention {enabled:false, ttl_days:7, local_only:true, auto_purge:true}` operator-toggled only; zero egress under offline profile.

### 9.10 Deployment profile object & fail-closed loader
Handoff §2.2 JSON adopted. Loader algorithm: read requested profile → enumerate requested adapters/clients → any `requires_network` or `offline_profile_eligible:false` member under `offline_airgapped` ⇒ **abort startup before any node spawns**, log violation event, surface on canvas. Schemas/enforcement identical across profiles; only eligibility + `network` differ. Mode is emergent (D-MIX-01): the loader validates eligibility, it does not pre-lock a roster.

### 9.11 Current-conductor record & succession state (I-CN1/I-CS1)
```json
{ "current_conductor": { "model": "claude", "adapter": "claude_code", "reason": "operator_selected",
    "since": "ts", "directive_version": "v2.4", "subscription_ref": "sub-anthropic-01" } }
```
```json
{ "snapshot_id": "s-...", "ts": "...", "trigger": "major_event|interval",
  "tasks": "task-graph version ref", "nodes": "registry version ref",
  "debates": ["d-... open"], "gates": ["g-... pending"], "memory_heads": {"key": "version"},
  "routing": "context-routing table ref", "outstanding_issues": ["..."],
  "directive_version": "v2.4", "conductor": "current_conductor ref", "integrity": "sha256" }
```

---

## 10. UI DESIGN SPECIFICATION

### 10.1 Canvas model
One dynamic terminal canvas. Pane = live ConPTY view bound to a node; session lifetime is independent of layout (compositor detaches/reattaches renderers; resize sends `ResizePseudoConsole`). Pane chrome shows: node id/class, adapter+model badge, locality badge (LOCAL/FRONTIER), task id, state, gate status, MCP connectivity dot, subscription tag (for I-X3 visibility).

### 10.2 Pane-layout algorithm
Priority classes: P0 operator-pinned (never auto-moved) → P1 awaiting-operator (approvals, clarifications, gate decisions) → P2 active-interactive (conductor, debating/working nodes) → P3 background-busy → P4 completed/idle → collapse to **status cards** on a right-hand rail. Layout: visible set = P0..P2 up to `max_visible` (default 6, operator-tunable); grid = near-square `ceil(sqrt(n)) × ceil(n/⌈√n⌉)` with P0/P1 given double cells; recompute debounced 250 ms on membership change only (state flips restyle chrome without reflow); maximize/restore/minimize/pin/pause/resume/terminate per pane; drag to reorder overrides auto-placement until unpinned. Operator-required panes (P1) can never be auto-collapsed — hard rule.

### 10.3 Always-visible surfaces
- **Approval queue drawer** (permission requests, destructive/ambiguous voice commands, gate decisions awaiting operator) — badge count in title bar.
- **Status bar:** active profile + `network` mode, MCP health, node counts by state, subscription terminals in use (n/1 per account), VRAM residency gauge (offline profile).
- **Routing/artifact inspector:** per-task view of context routed, artifacts published (hash, status, provenance), gate chain.
- **Succession control:** Resume → Select model dialog (Phase 11); shows last snapshot age.
- **Voice HUD (Phase 12):** PTT state, live transcript, confidence, proposed command preview with EXECUTE blocked until broker verdict.

### 10.4 Explicitly not built
No chat-style aggregate view replacing terminals (prohibited drift: opaque agents); no vendor desktop-app embedding; no TTS affordances.

---

## 11. THREAT AND FAILURE ANALYSIS

### 11.1 Threat table (agent = attacker or fault source)
| # | Threat | Boundary | Mitigation (design section) |
|---|---|---|---|
| T1 | Terminal text parsed as control | TB-2 | Only signed envelopes are control (§9.2); renderers never eval terminal output |
| T2 | Harness config injection (`AGENTS.md`, MCP config) | TB-4 | Node-controlled untrusted input; policy never read from harness config (§9.8); adversarial tests (§12.3) |
| T3 | Codex-class nested autonomy exceeding profile | TB-4 | Supervisor sandbox: worktree ACL, deny-by-default egress, broker-mediated exec; violations logged + node paused (§9.8, §4.8) |
| T4 | Naked model/agent session joins orchestration | TB-4 | Registration refused unless supervisor-spawned (§9.1); periodic process audit flags unmanaged CLIs |
| T5 | Worker self-canonization / memory contamination | TB-3 | Server-side lifecycle enforcement (§9.4); candidate quarantined from accepted; gates only path to ACCEPTED |
| T6 | Silent last-write-wins on canonical memory | TB-3 | Immutable append + CAS + conflict records (§9.6) |
| T7 | MCP server accumulates authority / is compromised | TB-3 | MCP holds no policy; Sovereign-signed authorization; separate process; read/append capability only (§3.2) |
| T8 | MCP outage mid-project | — | Fail-closed node behavior (F5); local checkpoints; reconciliation before resume |
| T9 | Voice mis-transcription → destructive action | TB-5 | Confidence threshold; propose-never-execute; clarification; approval queue; full transcript log (§9.9) |
| T10 | Ambient/replayed audio issues commands | TB-5 | PTT/explicit trigger only; operator-presence assumption; protected actions always queued |
| T11 | Cloud adapter under offline profile | TB-6 | Fail-closed profile loader aborts startup (§9.10); acceptance test §12.3 |
| T12 | Voice audio exfiltration | TB-5/6 | Transcribe-then-discard; local-only TTL retention; zero egress offline (D-VOICE-04) |
| T13 | Subscription over-concurrency (ToS breach) | — | I-X3 governor in supervisor + status-bar visibility; raise only after R8 verification (§18) |
| T14 | CoWork silently modifies canonical files | TB-3 | CoWork = governed client class; canonical resources read-only to it; every access logged (D-COWORK-01/02) |
| T15 | Stale conductor state after succession | — | Snapshot verification checklist before first assignment (F4, §9.11) |
| T16 | Debate as unbounded token sink | — | Cost governor: per-debate budget, per-caller quota, hard round cap ≤5 (§9.5, I-DS1) |

### 11.2 Failure modes & recovery
Control-plane crash → restart from SQLite WAL + last snapshots; nodes hold, reconcile, resume. Node crash → registry marks TERMINATED, task back to READY, worktree preserved for forensics, respawn per policy. Conductor loss → succession (F4). GPU OOM (offline) → residency planner evicts per policy, task queued with visible reason, never silent failure. Disk-full → event log write failure halts new writes fail-closed. WSL/Parakeet down → voice surface disabled, text path unaffected (voice is never load-bearing).

---

## 12. TESTING AND EVALUATION PLAN

### 12.1 Layers
Unit (schemas, lifecycle transitions, resolver, layout algorithm) → Integration (F1–F5 end-to-end on mock adapters) → Security (adversarial, §12.3) → Recovery (kill-matrix: each process × each phase of F1) → Evaluation (Phase 13 comparative harness).

### 12.2 Adapter contract conformance suite
Every adapter (conductor/worker/coding/voice) must pass one shared suite: schema-valid artifacts; broker mediation (attempted out-of-profile action is blocked + logged); context via MCP only; resume/state export; refusal to start naked; eligibility flags honored by profile loader. Run per-adapter in CI from Phase 4 onward.

### 12.3 Acceptance matrix (baseline §18 + handoff §2.8, adopted in full)
Voice: PTT transcription correctness; low-confidence ⇒ clarification; destructive ⇒ approval queue; typed/voice control-event equivalence; voice cannot instantiate nodes or expand permissions; offline transcription with `network=none`. Codex/coding: adapter-only launch (naked process refused); out-of-profile actions blocked; offline instantiation refused; worktree isolation holds; config changes never alter Sovereign policy. Profiles: offline end-to-end with zero cloud adapters; schema identity across profile switch; fail-closed startup. v2.4 maturation: conductor kill → Resume/Select → full state reconstruction, no loss; non-conductor debate request honored with bounds+dissent+cost cap; OpenCode↔Codex swap with no contract change; capability request resolves without naming a model; local-conductor/frontier-workers and inverse both function networked.

### 12.4 Phase 13 comparative evaluation
Fixed reference project (multi-file code + research task mix); four configurations (single model / conductor+raw workers / Sovereign no-debate / Sovereign+debate); metrics: total cost to accepted output (tokens+wallclock+subscription-seat time), drift incidents, evidence-quality rubric, operator interventions, recovery time from injected faults. Report includes losses honestly — the baseline's own success measure demands the comparison could favor simpler setups.

---

## 13. COST AND PERFORMANCE CONSIDERATIONS

### 13.1 Cost model (post-D-ACCESS-01)
Primary basis: **flat-rate subscription seats + local compute (GPU/energy)**; per-token API only as fallback. Scaling constraint is subscription concurrency/usage limits, not tokens — hence I-X3 and the Phase 13 "cost to accepted output" recomputation. Debate Service budgets denominated in tokens for local models and in provider-usage units for frontier CLIs; cost governor enforces both.

### 13.2 Performance envelopes (targets, validated in spikes)
Compositor: ≥6 live panes, p95 input latency <50 ms, 1 MB/s aggregate VT throughput (P1 spike). Control plane: <100 ms envelope processing p95 (SQLite WAL single-writer is not a bottleneck at this scale). MCP: <50 ms local-socket round-trip p95 for reads; writes bounded by CAS retry policy (R6).

### 13.3 VRAM residency planning (offline profile's binding constraint)
Planning figures **[K — Track E/G to measure]** on a 16 GB-class GPU: Qwen3-14B Q4 ≈ 9–11 GB; Qwen2.5-Coder-7B Q4 ≈ 5 GB; Parakeet 0.6B ≈ 2–3 GB loaded; KV cache grows with context. Consequence: conductor-14B + coder-7B + Parakeet do **not** reliably coexist ⇒ Scheduler owns a **model-residency planner**: sequential residency (swap conductor/coder around task phases), or drop conductor to 8B when coding is active, or PTT-triggered lazy-load for Parakeet. Residency changes are visible on the status bar; eviction is never silent. Scale-up path (24B+ hardware) removes pressure without contract change (I-A1: hardware recorded, not hidden).

### 13.4 Cost risks
Debate misuse (mitigated: cost governor, caller quotas); frontier-terminal idle burn (mitigated: pause/park policy in supervisor); Electron RAM at many panes (measured in P1; Tauri fallback named).

---

## 14. OPERATOR DECISION POINTS

### 14.1 Decisions requiring operator action before/at Phase 0
| ID | Question | Options | Recommendation | Status |
|---|---|---|---|---|
| I-D1/I-D2 ratification (D-PROFILE-01, D-CODEX-02) | Ratify deployment-profile model + offline cloud-exclusion | ratify / amend | Ratify as specified | **PENDING [OPERATOR]** |
| D-COWORK-02 | CoWork excluded from offline profile | ratify / amend | Ratify (cloud-dependent; consistency requirement) | **PENDING [OPERATOR]** |
| D-UI-01 (new) | Desktop framework | Electron / Tauri / WinUI3 / Avalonia | Electron + xterm.js + node-pty; Tauri fallback; final after P1 spike | **PENDING [OPERATOR]** (ratify after Phase 1) |
| D-LANG-01 (new) | Control-plane language | Python / TypeScript / Rust / Go | Python 3.12 (Sovereign reuse, MCP SDK) | **PENDING [OPERATOR]** |
| D-PERSIST-01 (new) | Persistence | SQLite WAL + CAS artifact store / Postgres / files | SQLite WAL + content-addressed store | **PENDING [OPERATOR]** |
| D-MCP-03 (new) | Conflict mechanism | immutable-append + CAS heads / mutable CAS / append-only | Immutable append + CAS heads (§9.6); confirm in Phase 3A test | **PENDING [OPERATOR]** (decide at 3A) |
| D-IPC-01 (new) | Shell↔control-plane IPC | loopback WebSocket / stdio / gRPC | Loopback WebSocket, schema-validated | **PENDING [OPERATOR]** (low stakes; may delegate) |

### 14.2 Decision register (carried, already decided — restated for the record)
D-VOICE-01 (Parakeet, provisional until Phase 12 gate) · D-VOICE-02 TTS=none (closed) · D-VOICE-03 service-not-node (proposed→adopt) · D-VOICE-04 transcribe-then-discard (accepted) · D-CODEX-01 include Codex (accepted) · D-COND-01/02/03 conductor interface/current=Claude/offline-default Qwen3 8–14B (accepted) · D-CODEX-03 OpenCode+Qwen coder offline (accepted) · D-MCP-01 MCP as access layer (accepted) · D-MCP-02 placement beside control plane (proposed→adopt, §3.2) · D-MVP-01 MCP is MVP-foundational (ruled) · D-ACCESS-01 subscription-CLI primary (accepted) · D-ACCESS-02 ToS mitigated by I-X3 (mitigated) · D-SUB-01 one terminal/subscription (accepted) · D-MIX-01 free locality mixing (accepted) · D-CODE-04 OpenCode harness (accepted) · D-ARCH-01 one architecture, modes=node selections (accepted) · D-CS-01 succession via MCP (accepted) · D-DS-01 debate service (accepted) · D-CH-01 harness-agnostic coding node (accepted) · D-SCHED-01 scheduler subsystem (accepted).

### 14.3 Unresolved-issue register (seeded per directive §K)
| # | Issue | Owner phase |
|---|---|---|
| U1 | Parakeet streaming latency + VRAM under concurrency (Track G) | P12 spike |
| U2 | Windows mic capture → WSL bridge design + PTT trigger mechanism | P12 spike |
| U3 | Codex automation/ToS constraints for programmatic session launch | P6 / R4+R8 |
| U4 | CC-BY-4.0 attribution mechanics if product ships | P12 |
| U5 | Provider per-account concurrency allowances (only if raising I-X3 above 1) | R8 |
| U6 | MCP transport final choice per profile | P3A / R6 |
| U7 | Conflict mechanism confirmation (D-MCP-03) | P3A |
| U8 | Conductor-file schema/versioning + per-file write authority | P0→P3A |
| U9 | ConPTY behavior hosting full-screen TUIs (OpenCode) in panes | P1 |
| U10 | NTFS ACL granularity vs worktree churn; per-process egress deny on Windows | R7/P10 |
| U11 | Succession snapshot cadence tuning (event set + interval) | P11 |
| U12 | Framework RAM envelope at 8+ panes (Electron vs Tauri) | P1 |

---

## 15. PROPOSED PHASE 0 EXECUTION DIRECTIVE (for operator issuance — not self-issued)

> **PHASE 0 — CANONICAL SPEC FREEZE.** Scope: assemble the canonical spec set = operator baseline v1.x + amendment layer v2.1–v2.4 + Architecture Plan v1.0 schemas (§9) + register states (§14). Actions: (1) compute sha256 for every canonical document; write `PHASE0_FREEZE_MANIFEST.json` (doc id, version, hash, authority, writable-by); (2) resolve or explicitly defer every §14.1 pending decision — deferrals recorded with owner phase; (3) fix schema versions at `@1.0` and freeze `schemas/` skeleton; (4) declare conductor-file list + write authority (U8 first pass); (5) no code beyond manifest tooling. Exit gate `[OPERATOR]`: operator signs the freeze manifest. Prohibited: any implementation, any scope amendment, any register deletion. Budget: documentation-only; zero model spend beyond assembly assistance.

## 16. PROPOSED PHASE 1 TERMINAL-COMPOSITOR DIRECTIVE (for operator issuance)

> **PHASE 1 — TERMINAL COMPOSITOR SPIKE.** Scope: throwaway rig (`tools/spike_compositor/`), Electron + xterm.js + node-pty. Must demonstrate: ≥6 concurrent interactive ConPTY sessions (cmd, PowerShell, one full-screen TUI, one 1 MB/s synthetic streamer, two idle CLIs); pane resize with correct reflow; session survival across layout changes/detach-reattach; maximize/minimize/pin/terminate; metrics capture (p95 input latency, dropped-output detection, RAM/CPU at 6 and 8 panes). Kill criteria: p95 input latency ≥ 50 ms sustained, or output loss, or RAM > operator-set budget ⇒ rerun identical rig on Tauri + portable-pty before any framework ratification. Deliverables: metrics report, U9/U12 answers, D-UI-01 recommendation. Exit gate `[OPERATOR]`: ratify framework. Prohibited: building product UI, control-plane code, or adapters inside the spike. Budget: spike-only; no subscription terminals required.

## 17. PROPOSED PHASE 3A MCP-FOUNDATION DIRECTIVE (for operator issuance)

> **PHASE 3A — MCP SHARED-MEMORY FOUNDATION (MVP-foundational per D-MVP-01).** Scope: implement `mcp_server/` + `persistence/` per §9.4–9.6, §9.10–9.11: node auth (per-node credentials issued by Sovereign at spawn); resource catalog + tool catalog (§9.5) with scope enforcement delegated to Sovereign policy; memory schema + full lifecycle state machine (server-enforced); conductor-file resources (operator-writable only); artifact/task/evidence resources; provenance stamping on every write; event streaming; versioning; conflict handling (implement §9.6 recommendation; run the concurrent-writer test; record D-MCP-03 verdict); health checks; fail-closed disconnect semantics. Exit gate (all must pass, per canonical §I): shared memory survives CLI restart; nodes retain independent local context; every shared write has provenance; candidate/accepted separated; canonical directive not worker-writable; CoWork access logged + permission-controlled; conductor replacement preserves memory; MCP disconnect does not corrupt state; concurrent-writer conflict test yields conflict records, never silent overwrite. Prohibited: authorization logic inside MCP (I-M2); network transport under offline profile; any schema divergence between profiles. Budget: local development; zero frontier spend required (mock nodes).

---

## 18. SUBSCRIPTION-CLI ACCESS AND TOS-COMPLIANCE PLAN

### 18.1 Access architecture (I-X1..X4)
Primary path: provider CLIs under the operator's subscription auth — Claude Code (Anthropic), Codex CLI (OpenAI/ChatGPT account), Gemini CLI (Google) — each wrapped by a frontier adapter and spawned only by the Node Runtime supervisor. API keys are an optional fallback behind the same adapter contract (adapter swap, no architecture change).

### 18.2 Concurrency governor (I-X3, enforced not advisory)
Supervisor maintains `subscription_registry: {subscription_ref → active_terminal_count, provider, verified_concurrency_allowance (default 1)}`. Spawn request for a subscription at its allowance ⇒ refused with visible reason; queue or operator override only after R8 verification raises the recorded allowance. Status bar shows n/allowance per subscription at all times. Succession respects the governor (a successor conductor on the same subscription first releases the predecessor terminal).

### 18.3 ToS-compliance checklist (execute in R8, re-verify each provider quarterly and before any allowance raise)
Per provider: (1) locate current consumer-subscription terms + usage policy; (2) confirm CLI programmatic/wrapped invocation is permitted under subscription auth (vs. API-only automation clauses); (3) record per-account concurrent-session allowance and rate/usage caps; (4) record session/auth lifetime (re-auth cadence, token expiry) for the supervisor's auth-lifecycle handling; (5) store findings as ACCEPTED memory entries with source links + retrieval dates; (6) any ambiguity ⇒ default stance stays 1 terminal, flag `[OPERATOR]`. The system never raises concurrency on inference or silence.

### 18.4 Auth lifecycle
Adapters surface auth state (`authenticated / expiring / expired / rate-limited`) as node states on the canvas; expired auth pauses the node fail-closed (no silent API-key fallback — fallback is an operator-visible adapter swap). Credentials never transit MCP; they stay in provider-native stores on the host.

---

## 19. CONDUCTOR-SUCCESSION, DEBATE-SERVICE, AND SCHEDULER SPECS

### 19.1 Conductor Succession (I-CS1; extends §9.11)
**Serialization cadence:** on every major event (task-graph mutation, gate verdict, debate close, node spawn/terminate, memory-head advance on ACCEPTED, profile change) **plus** a bounded interval (default 5 min, tunable; finalized P11). Snapshot is itself an immutable MCP entry with integrity hash.
**Resume→Select flow:** operator invokes succession (or system detects conductor loss) → UI lists eligible conductor adapters under active profile (I-CN1 registry, not hard-coded names) → operator selects → supervisor releases predecessor terminal (I-X3) → new adapter spawns, loads conductor files (IDENTITY→ROLE→policies→CURRENT_PROJECT_STATE) then latest snapshot → runs the **staleness checklist** (directive version match; task-graph version match; snapshot age vs event log tail; node registry liveness; unresolved-conflict scan) → any mismatch ⇒ reconciliation report to operator before first assignment → `current_conductor` record updated with reason. Target: succession as routine hot operation; acceptance test = kill mid-project, zero loss (§12.3).

### 19.2 Debate Service (I-DS1)
**Request API:** `request_debate{caller_node, topic, artifact_refs, participants: CapabilityDescriptor[], max_rounds ≤5, budget {tokens|usage_units}, gate_id?, early_stop_criteria}`.
**Authorization:** Permission Broker verifies caller's debate quota + budget availability; Scheduler resolves participant descriptors to nodes (never the caller alone judging itself).
**Round Manager:** structured rounds — claim → evidence-bound challenge → response; every assertion must cite artifacts/evidence entries (model votes are not evidence — prohibited drift); early stop on convergence or budget threshold.
**Evidence Manager:** validates citations resolve to real MCP entries; unsupported claims marked as such in the record.
**Result:** `{debate_id, rounds_used, positions[], convergence|dissent (preserved verbatim), evidence_map, cost_actual}` → immutable MCP record; gates reference it; **no consensus forcing** — unresolved disagreement flows to the gate/operator as first-class output.
**Cost Governor:** per-debate hard budget, per-caller period quota, global concurrent-debate cap; exhaustion ⇒ clean cutoff with partial record, never silent truncation.

### 19.3 Scheduler + capability registry (I-SC1)
**Registry:** capability descriptors per node (declared by adapter + refined by Track E/R10 benchmark scores stored as ACCEPTED evidence).
**Resolution (over the Task Graph, not replacing it):** Task Graph marks READY → Scheduler filters (hard requirements, profile eligibility, I-X3 headroom, permission compatibility) → ranks (benchmark fit, load, cost class, VRAM residency delta §13.3) → binds task→node or requests spawn → publishes assignment rationale to the event log (operator-inspectable "why this node").
**Queueing:** priority = task priority + age; starvation guard; blocked reasons always surfaced (no invisible waits).
**Residency planner (offline):** computes VRAM plan per assignment wave; sequential-residency swaps are scheduled operations with visible state, never mid-generation eviction.

---

## 20. FINAL CONFIDENCE STATEMENT

**High confidence:** the amended objective is coherent and buildable as specified; the six-subsystem decomposition with MCP-as-access/Sovereign-as-authority is sound and enforceable structurally; Electron/xterm.js/node-pty can host the terminal canvas (proven lineage); SQLite+content-addressed persistence satisfies recovery requirements at this scale; the phase plan's gate ordering (0→1→2→3→3A→4→5) puts the two highest risks (compositor, MCP) behind the earliest gates; deployment-profile fail-closure and the I-X3 governor are implementable exactly as specified.

**Medium confidence:** VRAM concurrency management will make the offline profile *operationally* smooth on current 8–14B hardware (the residency planner is the mitigation; Track E/G must confirm); provider CLIs expose enough programmatic surface for clean adapter wrapping without fragile terminal-scraping (R3/R4 verify); Electron's resource envelope at 8+ panes (P1 measures; Tauri named fallback).

**Low confidence / explicitly unverified:** Parakeet streaming latency and concurrent-VRAM behavior (Track G unmeasured); Windows-mic→WSL bridge ergonomics (U2); provider ToS interpretations for wrapped-CLI automation (R8 — the design's 1-terminal default is deliberately conservative pending verification); GPT-5.x model naming details (flagged low-confidence in the handoff itself).

**What would change this plan:** P1 spike failure on both Electron and Tauri (→ WinUI/custom renderer path, +schedule); R8 finding that a provider prohibits wrapped-CLI use entirely (→ API-key fallback becomes primary for that provider — architecture unchanged, cost model updated); Track E finding that no 8–14B model meets conductor tool-use reliability (→ offline conductor becomes a scale-up gate rather than a launch feature — offline *coding* path unaffected).

No scope was expanded, no implementation is authorized by this document, and every operator-reserved decision is enumerated in §14.1. Ready for operator review → Phase 0 issuance.

---

*End of Architecture and Phased Build Plan v1.0 — responds to canonical handoff v2.4 directive §M items (1)–(20) in order.*
