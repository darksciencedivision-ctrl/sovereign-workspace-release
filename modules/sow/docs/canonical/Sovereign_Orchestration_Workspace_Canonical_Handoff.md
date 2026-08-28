# SOVEREIGN MULTI-TERMINAL ORCHESTRATION WORKSPACE
## Canonical Document Handoff — Amendment Layer, Validation Report, and Fable 5 Build Directive

**Document type:** Combined canonical handoff (analysis report + canonical amendments + implementation directive)
**Document version:** v2.4 (amendment layer over operator baseline v1.x)
**Date:** 2026-07-15
**Prepared by:** Research Validator / Analyst (non-authoritative)
**Intended recipient:** Fable 5 (or another advanced engineering-analysis model) acting as candidate conductor-architect
**Operator authority:** The human operator retains final scope, architecture, implementation, promotion, and acceptance authority. Nothing in this document promotes implementation status or redefines the approved objective.

---

## 0. HANDOFF CONTROL

### 0.1 Purpose of this document
This handoff integrates the operator directives issued after the v1.x baseline:

1. **Voice model selected:** NVIDIA **Parakeet** as the speech engine, positioned as an offline-capable component consistent with Sovereign's "run local and/or cloud" intent.
2. **Operator clarification:** Text-to-speech (TTS) is **not required**. The requirement is one-directional: the operator talks to the system; the system does not talk back.
3. **Model roster addition:** **OpenAI Codex** (Codex CLI) is to be one of the models used in orchestration, as a worker adapter.

This document does three things, in one combined artifact as requested:

- **Part 1 — Validation Report:** verifies these directives against current evidence, separates fact from assumption, and records contradictions, risks, and gaps.
- **Part 2 — Canonical Architecture Amendments:** the specific, scoped changes to fold into the v1.x canonical architecture. This is an *amendment layer*. It does not replace or re-scope the baseline; where the baseline is silent or now inconsistent, the amendment states the delta explicitly.
- **Part 3 — Fable 5 Directive Prompt Plan:** a complete, paste-ready, guardrailed directive prompt instructing Fable 5 to analyze, plan, and build the system, including the new voice and Codex requirements.

### 0.2 What is NOT changed by this handoff
The following baseline invariants are explicitly preserved and are **not** modified here:

- The conductor coordinates; Sovereign governs; models reason; the human operator retains authority.
- Every conductor and worker terminal runs as a Sovereign-governed node.
- Conductor and worker models are interchangeable behind stable adapter contracts.
- Concurrence is preferred, not mandatory; unresolved disagreement is preserved.
- Debate is bounded (default max five rounds), evidence-based, and task-specific.
- Gates prevent weak intermediate artifacts from propagating.
- The system is judged by total cost to accepted output, resistance to drift, evidence quality, operator-correction burden, and recovery — not by terminal count.

### 0.3 Evidence status of this handoff
Claims about Parakeet and Codex below are drawn from vendor documentation and public model cards retrieved on 2026-07-15 (see Sources). Feasibility of integrating these components into the Sovereign runtime is **assumption pending prototype**, not established fact. This distinction is maintained throughout.

### 0.4 Revision history
- **v2.4 (2026-07-15):** Operator architecture-maturation refinements — reframed deployment profiles as **deployment modes = node selections over one Sovereign architecture** (D-ARCH-01); elevated **locality is a node property** to a canonical invariant (I-L1); made the **conductor an interface with a runtime selection**, not a vendor default (I-CN1, D-COND-03); added **conductor succession** via periodic state serialization to MCP + hot resume/select (I-CS1, D-CS-01); promoted **debate to a reusable service** any authorized node may request, cost-capped (I-DS1, D-DS-01); generalized coding to a **harness-agnostic Coding Node** (OpenCode/Codex/Claude Code/Aider, I-CH1, D-CH-01); added a **Scheduler** subsystem with **capability scheduling** (I-SC1, D-SCHED-01) and the six-subsystem decomposition (§2.13).
- **v2.3 (2026-07-15):** Operator refinements — corrected the offline model tier to current hardware (8B–14B; larger models are a future scale-up, D-COND-02/D-CODEX-03); added **OpenCode** as the open-source offline coding harness driving local models via Ollama (Codex CLI remains the online harness, D-CODE-04); made **local/frontier mixing** first-class (locality is per-node; any conductor may drive any mix when networked; only strict air-gapped forces all-local, D-MIX-01); and set **one terminal per subscription** as the default concurrency rule, mitigating the earlier ToS risk (D-SUB-01, D-ACCESS-02).
- **v2.2 (2026-07-15):** Resolved audit findings 6 and 8 under delegated operator judgment — offline-profile conductor default set to a local tool-use model (Qwen 3.6 / GLM-5.2-class, D-COND-02), offline coding worker to Qwen3-Coder-Next (D-CODEX-03), and a transcribe-then-discard voice-audio retention policy with optional bounded diagnostic retention (D-VOICE-04). Added §2.12: frontier models are integrated via provider CLIs under subscription auth (uniform node interface with local models), not metered API — with the clarification that CLI/subscription access does not make frontier models offline-capable (I-D2 stands). Added subscription concurrency/ToS to the risk register.
- **v2.1 (2026-07-15):** Validator self-audit corrections — fixed a broken cross-reference (Phase 11, not §11), standardized "Voice Input Service" terminology, removed certainty inflation ("byte-for-byte" → semantic identity), qualified time-sensitive Parakeet/Codex claims, and constrained the CoWork clause to hybrid/cloud profiles. Ruled MCP Phase 3A **MVP-foundational** (see §2.11). Audit findings 6 and 8 (offline conductor model; voice-audio retention policy) remain flagged in the unresolved registers.
- **v2.0 (2026-07-15):** Initial combined handoff (voice/Parakeet, Codex, deployment profiles, MCP shared-memory).

---

# PART 1 — VALIDATION REPORT

Prepared in the Research Validator role: verify, challenge, separate evidence from interpretation, and expose uncertainty. This part evaluates the operator directives; it does not accept them uncritically, but it also does not override them — the operator's objectives are preserved.

## 1.1 Review of the voice directive (NVIDIA Parakeet, STT-only)

### 1.1.1 Objective (restated, not expanded)
Add operator-to-system voice input. The operator speaks; the system transcribes and acts. No spoken output is required. The voice engine is NVIDIA Parakeet, selected in part for offline capability consistent with Sovereign's dual local/cloud posture.

### 1.1.2 Facts (verified against vendor sources, 2026-07-15)
- Parakeet is an **automatic speech recognition (ASR / speech-to-text) family**, built on a FastConformer encoder with CTC, RNN-T, or TDT decoders. It is a transcription engine, not a text-to-speech engine.
- `parakeet-tdt-0.6b-v2` (0.6B parameters) topped the Hugging Face Open ASR Leaderboard *as of the cited source (2026-07-15); leaderboard standings change — re-verify at build time.* `parakeet-tdt-0.6b-v3` (0.6B) is multilingual, extending coverage to 25 European languages.
- Licensed **CC-BY-4.0**, which permits commercial use of the model checkpoints. This is compatible with a self-hosted, operator-owned deployment.
- **Offline operation is supported** via the NeMo toolkit (local checkpoint, batch/offline transcription). A cloud path also exists via NVIDIA NIM / Riva microservices.
- **Hardware:** an NVIDIA GPU with CUDA is required for training and recommended for inference; the ASR NIM microservice requires **Compute Capability ≥ 8.0 (Ampere or newer)**. On **Windows 11**, the supported path is via **WSL** (Build 23H2+, driver ≥ 570). Minimum ~2 GB RAM to load the model; long-audio inference (up to ~11 hours) is documented on an A100 80 GB using local attention.

### 1.1.3 Effect of the "no TTS" clarification
The gap previously flagged (Parakeet performs no speech synthesis) is **closed by operator directive**. Because voice output is explicitly out of scope, Parakeet's STT-only nature fully satisfies the requirement. No TTS engine needs to be selected, and none should be added — adding one would be scope drift.

**Finding:** The voice directive is internally coherent and satisfiable by Parakeet. Confidence: **high** on capability match; **medium** on Windows integration effort (WSL + microphone capture pipeline is unvalidated here).

### 1.1.4 Challenges to the "offline… agnostic and scalable" framing
The operator's framing — "a powerful offline system… agnostic and scalable… the ability to do both" — is **mostly supportable, with two qualifications that must be recorded rather than assumed away**:

- **"Offline" — supported, but conditional.** Parakeet runs fully offline via NeMo, but only on suitable **NVIDIA hardware**, and on Windows only **through WSL**. Offline ≠ hardware-free. This aligns with the baseline's existing WSL assumption, so it introduces no new architectural surprise, but the hardware dependency must be stated in the deployment requirements.
- **"Agnostic" — true at the architecture layer, false at the hardware layer.** Parakeet is not portable across arbitrary hardware; it is NVIDIA-bound. The *agnosticism* the operator wants must live in the **Voice Input Service abstraction** (the `VoiceAdapter` interface, §2.4), exactly as conductor/worker model-agnosticism lives in the model-adapter contract. With that abstraction, a future CPU-friendly or non-NVIDIA STT engine (e.g., whisper.cpp-class) can be substituted without touching Sovereign. Without it, the system is silently welded to NVIDIA.
- **"Scalable" — supported in two independent directions.** Local scaling (batch, long-audio, larger checkpoints) and cloud scaling (NIM/Riva). "The ability to do both" is real, but "both" here means *NVIDIA-local or NVIDIA-cloud*, not truly vendor-plural. This is fine for the stated goal; it should just not be overstated as universal portability.

### 1.1.5 Architectural correction: Parakeet is not a reasoning node
This is the single most important validation point on the voice directive.

A Sovereign node in the baseline is a reasoning unit: it has a role, a directive, a debate loop, a local gate, and produces artifacts for downstream reasoning. **Parakeet does none of that.** It is an **input transducer** — it converts operator speech into text commands that enter the control plane.

Modeling Parakeet as a normal worker node would be a category error: it has no meaningful debate, no acceptance gate over "reasoning," and no downstream artifact in the reasoning sense. It should instead be a distinct adapter class — a **Voice Input Service** — that still runs *under* Sovereign governance (permissioned, logged, sandboxed) but is **not** subjected to the debate/gate machinery. Its output (a transcript + a proposed control action) is what enters the operator-command path, and destructive or protected actions derived from voice must still pass the existing Permission Broker and operator-approval queue.

**Finding:** Add a Voice Input Service adapter class; do not model Parakeet as a conductor/worker reasoning node. Confidence: **high**.

### 1.1.6 Uncertainties requiring the Phase 12 spike (do not assert as fact)
- Real-time / streaming latency for push-to-talk versus batch transcription.
- VRAM footprint of Parakeet running concurrently with local reasoning models on one GPU.
- Windows microphone capture into WSL, and the wake-word / push-to-talk trigger mechanism.
- Accuracy on operator-specific technical vocabulary (model names, command verbs, file paths).
- Command safety: mis-transcription that maps onto a destructive command — mitigated by the existing "voice cannot bypass permissions; destructive commands require approval; ambiguous commands require clarification" requirements, which must be preserved verbatim.

## 1.2 Review of the Codex roster addition

### 1.2.1 Facts (verified against vendor sources, 2026-07-15)
- **Codex CLI** is OpenAI's terminal coding agent (a Claude Code-class tool): it reads the codebase, runs tests, edits files, and executes shell commands locally.
- Model family is the **GPT-5.x** line (e.g., GPT-5.6 variants "Sol / Terra / Luna"; GPT-5.4 remains available across CLI, app, IDE, and cloud surfaces). *Specific model names are per secondary sources as of 2026-07-15 — treat as low-confidence and re-verify.* Exact model-to-task mapping is a provider detail that will drift; adapters must query capability rather than hard-code model names.
- Supports **session resume** (`codex resume`) and **context compaction** as the session approaches the context-window limit — relevant to the `session_resume` and `get_context_status` adapter capabilities.
- Offers a **cloud surface** for long-running and **parallel** async tasks in OpenAI-managed environments, in addition to the local CLI.

### 1.2.2 Where Codex fits
Codex is a strong fit as a **coding-specialist worker adapter**: architecture-to-code, patch generation, test authoring/execution inside an isolated Git worktree. Its native session-resume and compaction align with the baseline's node persistence and context-status requirements.

### 1.2.3 Contradiction against the offline narrative (must be recorded)
**Codex model inference is cloud-dependent.** The Codex CLI runs locally, but reasoning requires OpenAI connectivity. Therefore:

- Codex **does not contribute to** and in fact **is incompatible with** a fully-offline / air-gapped deployment.
- If Codex were treated as *mandatory*, it would contradict the operator's "powerful offline system" goal.

**Resolution (proposed, operator to ratify):** Codex is **one optional adapter among interchangeable adapters**, not a required dependency. The system defines explicit **deployment profiles**; the offline/air-gapped profile **excludes** Codex (and all cloud adapters) and substitutes a local coding model. This preserves both the operator's desire to use Codex *and* the offline capability, without either overriding the other. Confidence: **high** that this resolves the contradiction; **operator ratification required**.

### 1.2.4 Nested-autonomy risk (Codex is itself an agent)
Codex is not a passive completion endpoint — it is an **agentic CLI** with its own tool-calling, sandboxing, and configuration surface (e.g., an `AGENTS.md` project file and MCP integration). This creates two specific risks the baseline's invariants already anticipate but which must be explicitly enforced for Codex:

- **Permission leakage / bypass:** Codex's *own* sandbox and shell access must be subordinated to the Sovereign **Permission Broker**. The adapter must not allow Codex to perform filesystem/network/git actions that Sovereign has not authorized. Codex's autonomy is constrained to its assigned worktree and permission profile.
- **Directive-injection surface:** Codex's `AGENTS.md` / MCP configuration is a channel through which instructions could enter the node. This must be treated as node-controlled configuration under the canonical directive, not as operator-trusted input — consistent with the baseline's "terminal text vs. control protocol" and "tool-output injection" trust boundaries.

**Finding:** Codex satisfies the "no raw model session outside Sovereign" invariant only if the adapter actively mediates Codex's agent loop. A naked `codex` process is a raw session and is prohibited. Confidence: **high**.

### 1.2.5 Codex adapter capability metadata (proposed)
```json
{
  "adapter": "openai_codex_cli",
  "class": "worker_coding_specialist",
  "streaming": true,
  "tool_calling": true,
  "agentic_loop": true,
  "session_resume": true,
  "context_compaction": true,
  "usage_reporting": true,
  "computer_use": "sandboxed_shell_and_files",
  "multimodal_input": "partial",
  "local_runtime": false,
  "requires_network": true,
  "offline_profile_eligible": false
}
```

## 1.3 Consolidated model roster (interchangeable, behind adapters)

| Role class | Named candidate adapters | Runtime | Offline-profile eligible |
|---|---|---|---|
| Conductor (interface; runtime-selected) | current: **Claude**; any of Fable 5, GPT, Grok, Gemini, OpenCode+local, other | cloud or local | only if a local model is selected |
| Worker — general reasoning | Claude, GPT, Grok, Gemini, local model | cloud or local | local only |
| Worker — coding specialist (harness + model) | online: **Codex CLI** / Claude Code (subscription); offline: **OpenCode** + local coder (Qwen2.5/Qwen3-Coder 7–14B via Ollama) | cloud or local | online harness: **no**; OpenCode + local model: **yes** |
| Voice input service (not a reasoning node) | **NVIDIA Parakeet** (TDT 0.6B v2/v3) | local (NeMo) or cloud (NIM/Riva) | yes (local NeMo) |

Interpretation: the roster is intentionally plural. No single vendor is load-bearing. The offline capability is delivered by the *subset* of adapters that run locally; cloud adapters (Codex, cloud frontier models) are additive, not foundational.

**Access model (operator clarification, v2.2):** frontier models are reached through their **provider CLI under subscription authentication** (Claude Code, Codex CLI, Gemini CLI, etc.), launched as terminal nodes — not through metered API keys (API is an optional fallback). Because every node presents the same Sovereign interface, **a frontier-CLI node and a local-model node are interchangeable at the node layer** — frontier models "run just as the local ones." This is an interface-uniformity property, **not** a connectivity one: frontier CLIs still require network to reach the provider and remain excluded from the strict offline profile (I-D2). See §2.12.

## 1.4 Findings summary (Part 1)

1. Voice directive is coherent; Parakeet (STT-only) satisfies it; TTS correctly excluded.
2. "Offline/agnostic/scalable" holds **if** agnosticism is implemented as a Voice Input Service abstraction (the `VoiceAdapter` interface) and the NVIDIA/WSL hardware dependency is recorded.
3. Parakeet must be a Voice Input Service class, **not** a reasoning node.
4. Codex fits as a coding-specialist worker but is **cloud-dependent** and therefore **excluded from the offline profile**.
5. The offline/hybrid/cloud contradiction is resolved by explicit **deployment profiles**, pending operator ratification.
6. Codex must be wrapped so its agent loop is mediated by the Permission Broker; a naked Codex process is prohibited.
7. None of the above expands the baseline scope. Voice remains Phase 12 (post-MVP); Codex enters at the multi-model adapter phase.

---

# PART 2 — CANONICAL ARCHITECTURE AMENDMENTS

These amendments fold into the v1.x canonical architecture. They **amend**; they do not re-scope. Each amendment cites the baseline section it extends. Where an amendment could be read as changing an approved objective, it is marked **[OPERATOR RATIFICATION REQUIRED]** and treated as a proposal, not a fact.

## 2.1 New canonical invariants (extends §5)

- **I-V1 (Voice Input Service class).** Speech-to-text is provided by a Voice Input Service adapter class that runs under Sovereign governance but is **not** a reasoning node and is **not** subject to debate or reasoning gates. Its output enters the operator-command path, not the worker-artifact path.
- **I-V2 (One-directional voice).** The system accepts voice **input** only. Text-to-speech / spoken output is out of scope. No TTS component may be added without a new operator directive.
- **I-V3 (Voice cannot escalate authority).** Actions derived from transcribed voice are subject to the same Permission Broker and operator-approval queue as any other action. Voice never bypasses permissions; ambiguous commands require clarification; destructive commands require explicit approval.
- **I-A1 (Adapter-level agnosticism).** Provider/model/engine agnosticism is a property of the **adapter contract**, not of any specific engine. Hardware dependencies (e.g., NVIDIA GPU for Parakeet or local models) are recorded as deployment requirements, not hidden.
- **I-D1 (Deployment profiles).** The system defines explicit deployment profiles (offline/air-gapped, hybrid, cloud). The Sovereign control contract is **identical** across profiles; only the set of eligible adapters differs. **[OPERATOR RATIFICATION REQUIRED]**
- **I-D2 (Offline exclusion rule).** Cloud-inference adapters (including OpenAI Codex and any cloud frontier model) are **excluded** from the offline/air-gapped profile. The offline profile must be satisfiable entirely by local adapters.
- **I-C1 (No naked agentic CLI).** Agentic worker CLIs (e.g., Codex) run only through an adapter that subordinates their internal tool loop, sandbox, and configuration to the Permission Broker. A raw agent process outside Sovereign mediation is prohibited — this is the existing "no raw model session" invariant applied to agentic CLIs.

## 2.2 Deployment profiles (extends §20.1, §12)

The baseline treats "local and cloud" informally. This amendment makes it explicit.

```json
{
  "deployment_profile": {
    "id": "offline_airgapped | hybrid | cloud",
    "network": "none | egress_controlled | open",
    "eligible_adapters": ["..."],
    "excluded_adapters": ["openai_codex_cli", "cloud_frontier_*"],
    "voice_service": "parakeet_local_nemo",
    "conductor_constraint": "must_be_local_only_in_airgapped; free local/frontier mixing whenever network is available",
    "sovereign_contract_version": "unchanged_across_profiles"
  }
}
```

| Profile | Conductor | Reasoning workers | Coding worker | Voice | Network |
|---|---|---|---|---|---|
| Offline / air-gapped | local model only (default: Qwen3 8–14B-class — D-COND-02) | local models (8–14B current HW) | OpenCode + local coder (Qwen2.5/Qwen3-Coder 7–14B — D-CODEX-03/D-CODE-04) | Parakeet (NeMo, local) | none |
| Hybrid (free mixing) | any (local or frontier) | any mix of local + frontier | Codex (online) or OpenCode+local (offline) | Parakeet (local or NIM) | egress-controlled |
| Cloud | any cloud | cloud | Codex or cloud | Parakeet (NIM/Riva) or local | open |

**Invariant across profiles:** directive semantics, message/artifact schemas, task states, permission enforcement, gate behavior, and operator authority are **semantically identical (identical schemas and enforcement)**. Only adapter/client eligibility and the profile object itself change.

**Mode is emergent, mixing is free (operator clarification, v2.3 — D-MIX-01):** the active mode follows from which models are loaded, not a rigid pre-selected profile. **Locality is a per-node property.** Whenever the network is available, any conductor (local or frontier) may drive any mix of local and frontier worker nodes — offline conductor + online workers, or online conductor + offline workers, are both valid. The only hard constraint is the strict **air-gapped** profile (`network = none`), which necessarily forces all nodes local (you cannot reach a frontier provider with no network). This follows from I-X2 (node-interface uniformity): a node is a node regardless of what backs it.

## 2.3 Precise definitions (extends §4.3 Interpretations)

- **Offline** — the system can complete an end-to-end orchestration with `network = none`, using only local adapters and a local Parakeet checkpoint, on operator-owned NVIDIA-capable hardware (Windows 11 + WSL, or Linux). Current operator hardware runs **8B–14B-parameter** local models; larger local models (24B+) are a future scale-up as hardware grows. Offline coding uses the **OpenCode** harness driving a local coder via Ollama.
- **Agnostic** — model-, provider-, and engine-replaceable at the adapter contract level. **Not** hardware-agnostic. Hardware constraints are first-class recorded requirements.
- **Scalable** — scales along three independent axes: (a) node count within the control plane; (b) per-adapter scaling (Codex cloud-parallel tasks; Parakeet batch/long-audio; local models bounded by VRAM); (c) deployment profile (offline single-box → cloud fan-out) without changing the Sovereign contract.

## 2.4 Voice Input Service adapter (new component; extends §6, §8.2, §10)

**Placement:** a first-class adapter class alongside model adapters, but flagged `class: voice_input_service`. It is registered in the Node Registry as a service, not as a reasoning node, and is exempt from debate/gate lifecycles.

**Proposed interface:**
```text
start_capture()          # begin listening (push-to-talk or wake trigger)
stop_capture()
transcribe(audio_ref)    # batch/offline transcription of an audio artifact
stream_transcribe()      # streaming partial transcripts (if latency permits)
get_confidence()         # per-utterance confidence for ambiguity handling
propose_command()        # maps transcript -> candidate control action (never auto-executes)
get_usage()
close()
```

**Capability metadata:**
```json
{
  "adapter": "nvidia_parakeet",
  "class": "voice_input_service",
  "engine": "parakeet-tdt-0.6b-v2 | v3",
  "license": "CC-BY-4.0",
  "runtime": "nemo_local | nim_cloud",
  "offline_capable": true,
  "requires_gpu": "nvidia_cc>=8.0",
  "windows_path": "wsl",
  "tts": false,
  "streaming": "unverified_pending_phase12",
  "multilingual": "v3: 25 European languages"
}
```

**Governance flow (control, not reasoning):**
```text
Operator speech
  -> Voice Input Service (Parakeet, transcribe)
  -> transcript + confidence
  -> propose_command()  (maps to a candidate control action)
  -> Permission Broker  (authorize? destructive? protected?)
  -> if ambiguous OR destructive: Operator Approval Queue
  -> Control plane executes as an ordinary, logged control event
```
Text and voice control paths must produce **equivalent control events** (baseline §16 Phase 12 exit criteria), so voice is a second input surface over the same command bus, never a privileged one.

**Audio retention policy (operator decision, v2.2 — D-VOICE-04):** default is **transcribe-then-discard** — raw captured audio is deleted immediately after transcription; only the transcript persists, as a logged control event with provenance. An optional **diagnostic-retention** flag (default OFF) may retain raw audio as a classified multimodal artifact (baseline §11) with a bounded TTL (default 7 days), local-only, access-controlled, never egressed under the offline profile, and auto-purged at TTL. Retention is operator-toggled, never a node decision.

## 2.5 Codex worker adapter (extends §7.7, §8.2, §16 Phase 6)

Codex is integrated as `worker_coding_specialist` with these mandatory adapter obligations:

- Runs in an **isolated Git worktree** owned by the node (baseline §8.4, §16 Phase 10).
- All Codex shell/filesystem/git/network actions pass through the **Permission Broker**; the adapter denies anything outside the node's permission profile even if Codex attempts it.
- Codex configuration surfaces (`AGENTS.md`, MCP config) are **node-controlled** and treated as untrusted-input trust boundary, not operator-trusted directives.
- Codex `session_resume` / compaction are surfaced through `export_session_state` / `get_context_status`; project state still lives **outside** the model context (baseline §9.4).
- Marked `offline_profile_eligible: false`; the profile loader refuses to instantiate Codex under the offline profile.

**Offline coding counterpart — OpenCode (v2.3, D-CODE-04):** offline/open coding work uses **OpenCode** (open-source, Go, terminal TUI; provider-agnostic; runs local models via Ollama at zero API cost; does not store code — privacy-suitable), wrapped as a `worker_coding_specialist` adapter driving a local coder (default Qwen2.5/Qwen3-Coder 7–14B). OpenCode is a *harness*, not a model — the adapter pairs the harness with a local model and enforces the same Permission-Broker mediation, worktree isolation, and config-trust boundary as the Codex adapter. `offline_profile_eligible: true` when paired with a local model. Codex (online, subscription) and OpenCode (offline, local) are symmetric coding harnesses behind one adapter contract.

## 2.6 Threat-model additions (extends §13.1)

- **Voice mis-transcription → unintended action.** A misheard command maps onto a valid but unintended (possibly destructive) control action. *Mitigation:* confidence thresholds, `propose_command` never auto-executes, mandatory clarification on ambiguity, operator approval on destructive/protected actions, full transcript logging.
- **Voice as an injection surface.** Ambient audio or replayed audio issues commands. *Mitigation:* push-to-talk / explicit trigger, operator-presence assumption, approval queue for anything protected.
- **Codex nested autonomy / permission bypass.** Codex's internal agent loop attempts actions beyond the node's profile. *Mitigation:* adapter-level mediation, worktree isolation, deny-by-default broker, event logging of every Codex-initiated action.
- **Codex config injection.** Malicious/stale `AGENTS.md` or MCP config alters node behavior. *Mitigation:* node-controlled config, directive precedence, sanitization, adversarial testing.
- **Cloud adapter in offline profile.** A cloud adapter (Codex, cloud model) is instantiated under an air-gapped profile, breaking the offline guarantee. *Mitigation:* profile loader hard-excludes cloud adapters; startup validation fails closed.

## 2.7 Research-program additions (extends §15)

- **Track B (model adapters) — add Codex:** launch/auth model (ChatGPT account vs API key), session-resume/compaction behavior, parallel-session limits, sandbox model, `AGENTS.md`/MCP surface, automation/ToS constraints, cloud-only inference confirmation.
- **New Track G — Voice (Parakeet):** NeMo local install on Windows 11 + WSL; NVIDIA GPU/driver/CUDA requirements; microphone capture into WSL; batch vs streaming latency; VRAM under concurrency with local reasoning models; accuracy on operator/technical vocabulary; push-to-talk vs wake trigger; command-mapping safety; v2 vs v3 selection; NeMo-local vs NIM-cloud trade-off; CC-BY-4.0 attribution obligations in a shipped product.

## 2.8 Acceptance-matrix additions (extends §18)

**Voice tests**
- Push-to-talk transcribes an operator command correctly.
- Low-confidence transcript triggers clarification, not execution.
- A transcribed destructive command routes to the approval queue, not direct execution.
- Voice and typed forms of the same command produce identical control events.
- Voice cannot instantiate a node or expand permissions.
- Offline profile: Parakeet transcribes with `network = none`.

**Codex tests**
- Codex runs only via its adapter (naked `codex` process is refused/flagged).
- Codex actions outside the node profile are blocked by the broker.
- Codex is refused instantiation under the offline profile.
- Codex worktree isolation prevents cross-node file mutation.
- `AGENTS.md`/MCP config changes do not alter Sovereign policy.

**Deployment-profile tests**
- Offline profile boots with zero cloud adapters and completes a task end-to-end.
- Profile switch does not change directive/message/artifact/gate schemas.
- Startup fails closed if a cloud adapter is requested under offline profile.

**Architecture-maturation tests (v2.4)**
- Conductor succession: kill the conductor mid-project; Resume→Select a different model; verify full state (tasks/nodes/debates/gates/memory/routing/issues) reconstructs from MCP with no loss.
- Debate service: a non-conductor node requests a debate; bounded rounds, dissent preservation, and cost cap all hold.
- Coding node harness swap: swap OpenCode↔Codex behind the coding adapter with no contract change.
- Capability scheduling: conductor requests a capability (not a named model); the Scheduler resolves it to an available node.
- Locality mixing: local conductor drives frontier workers, and frontier conductor drives local workers (networked).

## 2.9 Register updates (extends §22 registers)

**Decision register**

| ID | Question | Recommendation | Operator approval | Status |
|---|---|---|---|---|
| D-VOICE-01 | STT engine? | NVIDIA Parakeet (TDT 0.6B v2/v3) behind the Voice Input Service (`VoiceAdapter` interface) | Required (Phase 12) | Provisional |
| D-VOICE-02 | TTS engine? | None — voice input only per operator directive | Ratified by directive | Closed |
| D-VOICE-03 | Parakeet as node or service? | Voice Input Service class, not a reasoning node | Recommended | Proposed |
| D-CODEX-01 | Include Codex? | Yes, as coding-specialist worker adapter | Directed by operator | Accepted |
| D-CODEX-02 | Codex in offline profile? | No — cloud inference; excluded from offline profile | Required | Proposed |
| D-PROFILE-01 | Formalize deployment profiles? | Yes — offline/hybrid/cloud with identical Sovereign contract | Required | Proposed |
| D-COND-02 | Offline conductor model? | Local tool-use model at current HW tier (**Qwen3 8–14B-class**); larger (24B+) as future scale-up; checkpoint finalized in Phase 6/Track E | Judgment (v2.2, revised v2.3) | Accepted |
| D-CODEX-03 | Offline coding worker (Codex substitute)? | **OpenCode + Qwen2.5/Qwen3-Coder 7–14B** via Ollama at current HW; scale to Qwen3-Coder-27B/Devstral-24B/Kimi-K2.6 later | Judgment (v2.2, revised v2.3) | Accepted |
| D-VOICE-04 | Voice audio retention? | Transcribe-then-discard by default; optional bounded local diagnostic retention (off) | Judgment (v2.2) | Accepted |

**Unresolved-issue register**
- Parakeet streaming latency and VRAM footprint under concurrency — unmeasured (Track G).
- Windows/WSL microphone capture and push-to-talk trigger mechanism — undesigned.
- Local coding-model substitute for Codex in offline profile — RESOLVED v2.2 (D-CODEX-03): Qwen3-Coder-Next default.
- Codex automation/ToS constraints for programmatic session launch — unverified.
- CC-BY-4.0 attribution mechanics for a shipped product — unconfirmed.
- Operator ratification of deployment-profile model (I-D1) and offline exclusion (I-D2) — pending.

## 2.10 MCP shared-memory and conductor-file layer (extends §7.4, §7.5, §7.6; new operator amendment)

The operator has designated an **MCP server** as the canonical shared-memory and shared-artifact interface between the conductor CLI, all worker CLIs, the Sovereign control plane, and Claude CoWork. This subsection validates and integrates that amendment.

### 2.10.1 Validation (Research Validator)
- **Coherence — high.** MCP is a natural fit for the baseline's already-specified Artifact Registry (§7.5), Message Router (§7.4), Context Compiler (§7.6), and Event Log (§7.8). It supplies the *access and transport layer* those components implied but did not name. This is an implementation-shaping addition, not a scope change.
- **Authority boundary preserved — critical and correct.** The amendment explicitly states MCP is the protocol/access layer and **Sovereign retains authorization, canonical state, access policy, gate state, node identity, and human-reserved decisions**. This preserves invariant §5.1 (Sovereign is the invariant) and §5.2 (conductor is not sovereign). **Do not** let the MCP server accumulate authority; it exposes state, it does not own it.
- **Risk — single point of failure / bottleneck.** Baseline §20.1 already flags this for a central control plane. The MCP server inherits it. *Mitigation:* local-first transport, fail-closed disconnect behavior (§14.1 of the amendment), local node checkpoints, and no assumption that stale memory is current.
- **Risk — expanded attack/injection surface.** MCP tool results and resources are a channel through which content enters a node; this is the baseline's **tool-output injection** trust boundary (§13). *Mitigation:* every request carries authenticated node identity + role + scope; resources are classified; candidate memory is quarantined from accepted memory; MCP payloads are untrusted input, not directives.

### 2.10.2 New canonical invariants (extends §5, §2.1 above)
- **I-M1 (Common governed memory).** Every Sovereign node connects to a common Sovereign MCP server for governed access to shared project memory, directives, artifacts, task state, evidence, and decisions. Manual transcript/clipboard routing between sessions is prohibited.
- **I-M2 (MCP is access, not authority).** The MCP server exposes state and tools; Sovereign owns authorization, canonical state, identity, gates, and human-reserved decisions. The MCP server is never an independent source of authority.
- **I-M3 (Three memory tiers).** Local conversational memory (per node, isolated), shared project memory (durable, governed, in MCP), and private node memory (scratch, not project truth) are distinct. Private/model-generated text becomes project truth **only** by publishing through a structured MCP resource/artifact and passing the applicable gate or operator decision.
- **I-M4 (Scoped memory access).** MCP enforces role-, task-, and project-based access, read/write separation, private/shared separation, candidate/accepted separation, protected operator files, and credential restriction. Shared memory is governed, never globally writable.
- **I-M5 (Provenance on every shared entry).** Every shared-memory entry records author node, model, task, timestamp, directive version, source artifacts, evidence, confidence, status, reviewers, gate result, and superseded entries.
- **I-M6 (No worker self-canonization).** A worker may publish a `CANDIDATE` finding; it may not declare its own finding `ACCEPTED`. Promotion requires the applicable gate or operator decision.

### 2.10.3 Memory-state lifecycle (from amendment §9)
`CANDIDATE → UNDER_REVIEW → DISPUTED → ACCEPTED | ACCEPTED_WITH_RESERVATIONS | REJECTED → SUPERSEDED → ARCHIVED`. These states are enforced by the MCP memory schema and referenced by gate verdicts.

### 2.10.4 Conductor files (from amendment §5; extends §9.3, §9.4)
Conductor files are **operator-created, model-independent assets** loaded by the conductor at startup via MCP (`IDENTITY.md`, `ROLE.md`, `CONDUCTOR_DIRECTIVE.md`, `ORCHESTRATION_RULES.md`, `TASK_DECOMPOSITION_RULES.md`, `CONTEXT_ROUTING_POLICY.md`, `DEBATE_POLICY.md`, `GATE_POLICY.md`, `MODEL_SELECTION_POLICY.md`, `OPERATOR_RESERVED_AUTHORITY.md`, `STOP_CONDITIONS.md`, `CURRENT_PROJECT_STATE.md`). Because the conductor role is defined by these files rather than by the model, **conductor interchangeability (§9.3) is strengthened**: a different model becomes conductor by loading the same files. This directly serves the baseline invariant that project intelligence lives outside model context (§9.4).

### 2.10.5 Current conductor selection = Claude (runtime, not architectural default; see §2.14)
The conductor is an **interface**; the **current runtime selection** is Claude (operator-selected), recorded in MCP and replaceable at runtime (§2.14). Claude loads the operator's conductor files like any other model would, and can be replaced mid-project (§18.3, Phase 11) or on failure via succession (§2.14.2) without changing the Sovereign contract. **No model is the architectural default conductor** (I-CN1).

### 2.10.6 Claude CoWork as a client class (from amendment §11)
CoWork is treated as **another Sovereign client/node class**, not an unrestricted backdoor. It obeys the same directive hierarchy, project boundaries, file permissions, provenance, operator-reserved authority, write restrictions, and event logging. It must not silently modify canonical files.

**Validator caveat [OPERATOR RATIFICATION REQUIRED]:** CoWork is **cloud-dependent** (Claude inference is remote). By invariant I-D2 (offline exclusion), a cloud-dependent client cannot participate in a strict **offline/air-gapped** profile. Therefore: the MCP **server** runs locally and satisfies the offline profile, but **CoWork (and any cloud conductor/worker) is unavailable under the offline profile**. In hybrid/cloud profiles CoWork is available. This is a consistency requirement, not a limitation of CoWork itself — flag for operator ratification.

### 2.10.7 Voice service ↔ MCP integration
The Voice Input Service (Parakeet, §2.4) registers with and publishes transcripts/command-events and heartbeats through MCP for logging and provenance, but is **exempt** from the memory-state lifecycle (§2.10.3) and debate/gate machinery — consistent with I-V1 (it is a transducer, not a reasoning node).

### 2.10.8 Offline-profile consistency for MCP
Under the offline/air-gapped profile the MCP server must run **local-only** (loopback / stdio / local socket, `network = none`). No amendment content requires external connectivity for the MCP layer itself; only cloud *adapters/clients* (Codex, cloud models, CoWork) are excluded. This reinforces, rather than weakens, the offline capability.

### 2.10.9 Failure-mode integration (from amendment §14; extends §13)
- MCP unavailable → nodes stop shared-memory-dependent work, retain local state, checkpoint, show disconnected, resume only after reconciliation (fail closed).
- Conflicting writes → immutable entries, versioned updates, compare-and-swap, conflict records, review gates. **No silent last-write-wins** on canonical memory.
- Stale conductor state → conductor verifies directive version, task-graph version, checkpoint timestamp, node registry, unresolved-conflict state before assigning work.
- Memory contamination → candidate memory quarantined from accepted; model text is never auto-truth.
- Unauthorized access → every request authenticated with node identity + project + role + scope + operation.

### 2.10.10 Register updates (MCP)

| ID | Question | Recommendation | Operator approval | Status |
|---|---|---|---|---|
| D-MCP-01 | Shared-memory interface? | MCP server as canonical access/transport layer; Sovereign retains authority | Directed by operator | Accepted |
| D-MCP-02 | MCP placement? | Inside/beside the control plane; not an independent authority | Recommended | Proposed |
| D-COND-01 | Initial conductor? | Claude, loading operator conductor files; remains interchangeable | Directed by operator | Accepted |
| D-COWORK-01 | CoWork access? | Governed client class under same permissions/provenance | Directed by operator | Accepted |
| D-COWORK-02 | CoWork in offline profile? | Excluded (cloud-dependent); MCP server itself remains local | Required | Proposed |

**Unresolved-issue additions**
- CoWork/offline consistency (D-COWORK-02) — operator ratification pending.
- MCP transport choice (stdio vs local socket vs networked) per profile — undesigned.
- Conflict-resolution mechanism (CAS vs immutable-append) — to be selected in Phase 3A.
- Conductor-file schema/versioning and who may write each file — to be specified.
- **Offline conductor model (audit v2.1, finding 6) — RESOLVED v2.2, revised v2.3 (D-COND-02):** offline-profile conductor defaults to a local tool-use model at the current hardware tier (Qwen3 8–14B-class; larger as scale-up) served via Ollama/llama.cpp; final checkpoint benchmarked in Phase 6/Track E. Claude remains the hybrid/cloud initial conductor.
- **Voice audio retention/privacy (audit v2.1, finding 8) — RESOLVED v2.2 (D-VOICE-04):** transcribe-then-discard by default; optional bounded, local-only, off-by-default diagnostic retention (see §2.4).

## 2.11 MVP definition update (extends §17; operator ruling v2.1)

Per operator ruling, the **MCP shared-memory foundation (Phase 3A) is MVP-foundational**. Baseline §17 is amended: the MVP now additionally requires a functioning Sovereign MCP server providing governed shared memory, conductor-file loading, scoped artifact/task/evidence access, provenance on every entry, access control, and fail-closed disconnect. Consequences:

- The MVP's "structured artifact passing" and "project persistence" (baseline §17) are delivered **through** the MCP layer, not as ad-hoc file passing.
- Phase 3A is a hard prerequisite of the conductor prototype (Phase 5) and cannot be deferred to post-MVP.
- MVP exclusions (voice, many providers, computer-use automation, etc.) are unchanged; voice remains post-MVP (Phase 12).

| ID | Question | Recommendation | Operator approval | Status |
|---|---|---|---|---|
| D-MVP-01 | Is MCP (Phase 3A) MVP-foundational? | Yes — MCP shared-memory is a core MVP deliverable | Ruled by operator (v2.1) | Accepted |

## 2.12 Model access model — subscription-CLI over API (operator clarification, v2.2; extends §8.2, §12)

**Decision:** frontier models are integrated through their **provider CLI authenticated by the operator's subscription** (e.g., Claude Code, OpenAI Codex CLI, Gemini CLI), launched as Sovereign-governed terminal nodes. Metered **API keys are an optional fallback**, not the primary integration path. This is why the workspace opens *multiple terminals* — each is a subscription-backed CLI session, not an API client.

**New invariants:**
- **I-X1 (Subscription-CLI primary).** The adapter contract wraps provider CLIs under subscription auth as the primary path; API adapters are optional and interchangeable behind the same contract.
- **I-X2 (Node-interface uniformity).** A Sovereign node exposes the same interface whether backed by a local runtime or a provider CLI. Frontier and local models are interchangeable *at the node layer* — this is the mechanism behind "frontier models run just as the local ones."
- **I-X3 (One terminal per subscription).** Each subscription-backed frontier CLI is limited to **one active terminal per subscription/account by default** (configurable only up to the provider's actual per-account concurrency allowance). Multiple frontier models require multiple subscriptions — one terminal each (e.g., a Claude terminal, a ChatGPT/Codex terminal, a Grok terminal). Local-model terminals have no per-subscription limit and are bounded only by hardware.
- **I-X4 (Free locality mixing).** Locality is a per-node property; when the network is available any conductor may drive any mix of local and frontier worker nodes. Only the strict air-gapped profile forces all-local (see §2.2, D-MIX-01).

**Validator clarification (keep the offline story honest):** I-X2 is an **interface** property, not a **connectivity** one. A frontier CLI still sends prompts to a remote provider and requires network; subscription-CLI access changes *how you authenticate and pay*, not *where inference happens*. Therefore frontier CLIs (Claude Code, Codex, Gemini CLI, CoWork) remain **excluded from the strict offline profile** (I-D2). Offline capability is delivered solely by local-runtime nodes.

**Cost-model update (extends §12):** the primary cost basis shifts from per-token API billing to **flat-rate subscription seats + local compute (GPU/energy)**. "Total cost to accepted output" is recomputed accordingly. The new scaling constraint is **subscription concurrency and usage limits**: opening many CLI terminals against one account may hit per-account rate/concurrency caps.

**Risk (mitigated by design, v2.3):** the earlier multi-session ToS/concurrency risk is mitigated by **I-X3 (one terminal per subscription)** — the system does not open multiple concurrent sessions against a single account by default. Residual: confirm each provider's *per-account* concurrency allowance if the operator ever raises the per-subscription terminal count above one (e.g., a Claude conductor terminal plus an Opus worker terminal on the same Anthropic subscription requires that subscription to permit two concurrent sessions).

| ID | Question | Recommendation | Operator approval | Status |
|---|---|---|---|---|
| D-ACCESS-01 | Primary model access path? | Subscription-CLI adapters primary; API optional fallback | Directed by operator (v2.2) | Accepted |
| D-ACCESS-02 | Subscription ToS/concurrency for multi-terminal CLI use? | Mitigated by 1-terminal-per-subscription (D-SUB-01); verify per-account concurrency only if raising above 1 | Directed by operator (v2.3) | Mitigated |
| D-SUB-01 | Terminals per subscription? | One active terminal per subscription/account by default; local terminals hardware-bounded | Directed by operator (v2.3) | Accepted |
| D-MIX-01 | Mix local + frontier nodes freely? | Yes when networked; only air-gapped forces all-local | Directed by operator (v2.3) | Accepted |
| D-CODE-04 | Offline coding harness? | OpenCode (open-source, Ollama-local) + local coder; symmetric to Codex online | Directed by operator (v2.3) | Accepted |

## 2.13 Architecture maturation (operator refinements, v2.4)

These refinements move the spec from *products* to *interfaces, roles, and contracts*. They consolidate scope; they do not expand it.

### 2.13.1 Deployment modes, not architecture modes (reframes §2.2, D-ARCH-01)
There is **one Sovereign architecture**. "Offline / hybrid / cloud" are **deployment modes = node selections**, not separate architectures. Every node has the identical interface:

```
Node
├── Sovereign Runtime
├── MCP Client
├── Adapter
├── CLI / harness
└── Model
```

Only the model (and its adapter/harness) changes: `Claude CLI → node`, `Codex CLI → node`, `OpenCode → Qwen3 → node`, `OpenCode → GLM → node`. Nothing else changes. "Profile" and "mode" are synonymous here; the mode is emergent from which nodes are selected.

### 2.13.2 New canonical invariants
- **I-L1 (Locality is a node property).** Local vs frontier is a property of an individual node, not of the orchestration system. The conductor and control plane are locality-agnostic. (Elevates/supersedes I-X4.)
- **I-CN1 (Conductor is an interface, not a vendor).** The architecture knows only the Conductor interface. The current conductor is a runtime selection recorded in MCP (today: Claude, operator-selected), replaceable at runtime with no architectural change. **No model is the architectural default conductor.**
- **I-SC1 (Capability scheduling).** The conductor schedules by required *capability*, not by named vendor/model. A capability registry resolves a requested capability (e.g., "coding worker, tool-use, ≥128k ctx") to an available node.

### 2.13.3 Six-subsystem decomposition
```
Operator
    │
    ▼
Desktop Workspace
    │
    ▼
Conductor  (interface; current selection recorded in MCP)
    │
    ▼
Sovereign Runtime
    │
 ┌──────┼───────────┐
 ▼      ▼           ▼
MCP   Debate     Scheduler
 │      │           │
 └──────┼───────────┘
    │
    ▼
Node Runtime
    │
    ▼
Adapters
    │
    ▼
CLI / Local Models / Frontier Models
```
Responsibilities: **MCP** (governed shared state/memory), **Debate** (reusable reasoning-improvement service), **Scheduler** (capability→node scheduling). The Scheduler works *over* the Task Graph Manager (§7.3) — Task Graph tracks dependencies/state, Scheduler assigns ready work to capable nodes; it does not replace it.

## 2.14 Conductor as runtime selection + succession (extends §9.3, §9.4, §16 Phase 11)

### 2.14.1 Conductor is the current selection, not the default
A **current-conductor record** lives in MCP:
```json
{ "current_conductor": { "model": "claude", "reason": "operator_selected", "since": "timestamp", "directive_version": "v2.4" } }
```
Tomorrow it may be `{ "model": "gpt", "reason": "operator_selected" }` or `{ "model": "opencode+qwen3", "reason": "offline_mode" }`. Only the Conductor interface is fixed; the architecture is vendor-neutral.

### 2.14.2 Conductor succession (I-CS1)
The conductor periodically **serializes its full operating state to MCP**:
```
Current Tasks · Current Nodes · Current Debates · Current Gates ·
Current Memory refs · Current Routing · Outstanding Issues ·
Directive version · Current conductor selection + reason
```
On conductor loss the operator: **Resume → Select model (Claude / GPT / OpenCode / …)**. The new conductor reconstructs state from MCP — no project loss, no conversation loss, no context rebuild. Conductor replacement becomes a routine hot operation, not a recovery emergency. Cadence: after every major event and on a bounded interval (finalized in Phase 11). Succession preserves the one-terminal-per-subscription (I-X3) and locality (I-L1) invariants.

## 2.15 Debate as a reusable service (extends §7, §8.5)

Debate is promoted from a conductor-owned loop to a **control-plane Debate Service** any authorized node may request:
```
Debate Service
  Input → Workers → Round Manager → Evidence Manager → Gate → Result
```
Guarantees enforced regardless of caller: **≤5 rounds default, evidence-based, dissent preserved, early stop, cost caps**. The **Permission Broker + Scheduler gate who may request a debate and enforce cost budgets** so a shared service cannot become an unbounded token sink. **I-DS1** applies.

## 2.16 Coding Node is harness-agnostic (extends §2.5, §2.12)

A **Coding Node** is defined by the coding-worker adapter contract; the harness and model are interchangeable behind it:
```
Coding Node  =  { OpenCode | Codex | Claude Code | Aider | … }  ×  { local | frontier model }
```
- **I-CH1 (Coding Node harness-agnostic).** The adapter exposes coding capability; the specific harness is a runtime choice. OpenCode+local (offline) and Codex/Claude Code (online, subscription) are the same node class with different backings; Aider and future harnesses drop in without contract changes.

**Register (v2.4)**

| ID | Question | Recommendation | Operator approval | Status |
|---|---|---|---|---|
| D-ARCH-01 | Profiles vs one architecture? | One architecture; profiles are deployment modes (node selections) | Directed by operator (v2.4) | Accepted |
| D-COND-03 | Conductor default or selection? | Interface + current runtime selection (no vendor default); Claude is current | Directed by operator (v2.4) | Accepted |
| D-CS-01 | Conductor succession? | Periodic state serialization to MCP + resume/select hot succession | Directed by operator (v2.4) | Accepted |
| D-DS-01 | Debate ownership? | Reusable control-plane Debate Service any authorized node may request (cost-capped) | Directed by operator (v2.4) | Accepted |
| D-CH-01 | Coding harness scope? | Harness-agnostic Coding Node (OpenCode/Codex/Claude Code/Aider) | Directed by operator (v2.4) | Accepted |
| D-SCHED-01 | Scheduler subsystem? | Capability→node Scheduler over the Task Graph | Directed by operator (v2.4) | Accepted |

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
