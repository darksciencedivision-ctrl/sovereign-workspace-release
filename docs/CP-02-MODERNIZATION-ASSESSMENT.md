# CP-02 ASSESSMENT — Local AI Modernization Directive, Reviewer Evaluation

| Field | Value |
|---|---|
| Document class | Reviewer assessment. **Authorizes nothing.** It classifies an operator-supplied directive against verified disk state, host hardware, and in-flight work. |
| Subject | "SOVEREIGN WORKSPACE + DISTILLERY LOCAL AI MODERNIZATION DIRECTIVE", 68 sections, supplied by the operator 2026-08-25, authored with an external LLM. |
| Prepared | 2026-08-25, against `D:\Product Software\`, `D:\Token Piggy Bank\`, and web verification of every named model, format, and runtime. |
| Standing | `SWS-UI-001` v1.2 + `ADDENDUM-01`; `OX-ALPHA-DIRECTIVE-CP-01` in flight at G0. |
| Reviewer verdict | **Do not adopt as written. Extract six ideas, reject four, defer the rest behind a hardware decision.** Reasons below, each with evidence. |

---

## 1. Summary

The directive is well-constructed and its architectural instincts are correct. Its problem is not reasoning — it is that it was written without reading the codebase or the hardware profile, and both contradict it.

Three findings govern everything else:

1. **The machine cannot run the plan.** The host GPU is a single **RTX 5060 Ti with 8151 MiB VRAM** (≈5.26 GiB free at capture). The directive's centre of gravity — 27B models at 64K context, an ExLlamaV3 performance lane, speculative decoding with a resident draft model, a quantization matrix, Unsloth fine-tuning — assumes 24–48 GB. The project's own accepted decision record already says so: `HG-3 = BLOCKED_HARDWARE_CAPACITY`, minimum usable VRAM **24 GiB**, preferred **32 GiB**, primary trainer **UNASSIGNED**. FACT[`SOVEREIGN_DISTILLERY_RAW_SOURCE_…\SOURCE\runs\sovereign\hardware_profile.json`], FACT[`…\SOURCE_TREE\docs\decisions\D-HW-01-grounded-primary-trainer-reality-rebaseline.md`]
2. **Roughly 80 % of the proposed architecture already exists**, schema-frozen and test-pinned, in `modules/sow/`. Capability metadata, capability-first routing, a vendor-blind resolver, a model-registry layer, and a six-state VRAM residency planner are all implemented. The directive proposes building them. FACT[`modules/sow/schemas/node.schema@1.1.json`], FACT[`modules/sow/scheduler/resolver/resolver.py`], FACT[`modules/sow/scheduler/residency_planner/residency_planner.py`], FACT[`modules/sow/adapters/roster.py`]
3. **Its core premise about the inference path is factually wrong.** §12 asserts Sovereign directly assumes `Ollama = inference` and must be given an abstraction. The abstraction exists: `Backend` is a Protocol, and `generate()` is an HTTP POST to `/api/generate` behind it. The real gap is that the Protocol has **one** method where it needs seven. FACT[`modules/sow/adapters/base/backend.py:26-29,82-92`]

Every model, format, and runtime the directive names is real and verifiable — that part holds up. What does not hold up is the match between those technologies and this machine.

---

## 2. The governing constraint — recorded host hardware

| Fact | Value | Source |
|---|---|---|
| GPU | `NVIDIA GeForce RTX 5060 Ti` | `hardware_profile.json`, captured 2026-08-19T23:45:42Z |
| VRAM total | `8151 MiB` | same |
| VRAM free at capture | `5383 MiB` (≈5.26 GiB) | same |
| Compute capability | `12.0` — **Blackwell, sm_120** | same |
| Driver | `610.74` | same |
| System RAM | `68,399,640,576 B` (63.7 GiB) | same |
| OS | `Windows-11-10.0.26200-SP0` | same |
| Python | `3.14.6`, `C:\Python314\python.exe` | same |
| torch / transformers / peft / trl / bitsandbytes / unsloth / llama_cpp | **all `null`** — `ModuleNotFoundError` | same |
| Verdict recorded in the capture | `"PyTorch not importable — no local training possible."` | same |
| CUDA toolkit version | **ABSENT** — never recorded anywhere on disk | searched all trees |
| llama.cpp | **ABSENT as an install.** Zero binaries, zero `.gguf` files, zero packages. Appears only as a documented future intention in four planning docs. | searched both mounts |
| ExLlamaV3 / EXL3 / vLLM / TensorRT / ONNX | **ABSENT.** Zero hits. | searched both mounts |
| Ollama | **The only working local runtime.** v0.32.6, 52 tags live, 43-entry registry, **768.4 GiB on disk**, every entry `source_runtime: ollama` | `evidence/gate5/preflight.json`, `DESIGN.md §B.2` |

### 2.1 What 8 GB means, concretely

| Model class | Q4_K_M weights | Fits 8 GiB VRAM? |
|---|---|---|
| 7–8B | ~4.5–5 GiB | Yes, with KV headroom |
| 12–14B | ~8–9 GiB | No — partial offload |
| 27B | ~16–17 GiB | No — heavy CPU offload |
| 32B | ~19–20 GiB | No |
| 70B | ~40 GiB | No |

The host runs 27B-class models today, but through **CPU/RAM offload from 63.7 GiB of system memory** — functional, slow, and bounded by memory bandwidth rather than by runtime choice. This is the single most important thing the directive does not know. Several of its phases would produce *worse* performance on this box, not better (§25–27 in particular — see §5.3).

### 2.2 The Distillery is already blocked, by its own accepted record

> "**NO DESIGNATED MACHINE CURRENTLY SATISFIES THE GND-TRAINER-PRIMARY CAPABILITY CONTRACT.**" — FACT[`D-HW-01`]

> "The working envelope is a **1B–3B student under QLoRA with gradient checkpointing**. A 7B student is an experiment to attempt and measure, not a dependency." — FACT[`ADR-0003-architecture-growth-deferred.md`]

> "The Distillery can begin generating corpora today and **cannot train anything today**." — FACT[`DESIGN.md §A.2 EF-4`]

> "5 of 39 teachers are comfortably viable and **18 of 39 are not viable at all on this machine**." — FACT[`DESIGN.md EF-3`]

Directive §12 (Distillery artifact pipeline), §13 (Unsloth), §14 (quantization matrix) all sit downstream of a canonical trained checkpoint that cannot be produced here. They are not wrong; they are **blocked on a hardware decision the operator has already deferred**.

---

## 3. What already exists — the duplication audit

The directive proposes five structural additions. Four exist.

| Proposed | Status | Evidence |
|---|---|---|
| Model registry with capability metadata | **EXISTS** — `RosterEntry(name, node_class, locality, cost_class, offline_profile_eligible, requires_network, subscription_backed, capability_descriptors, backend_kind, model, harness, notes)`; concrete model names deliberately confined to one file: *"The control plane sees only descriptors; the roster is the one place a concrete model is named."* | `adapters/roster.py:4-5,27-45` |
| Capability-based routing | **EXISTS** — *"Resolves a task's capability requirement to a node by DESCRIPTOR — filter by hard requirements, then rank. **Vendor/model names never enter this path.**"* Hard filters on tool_use, structured_output, min_context, harness_class, locality; ranking on `benchmark_score − 0.1·active_tasks − 0.05 if subscription` | `scheduler/resolver/resolver.py:1-8,35-71` |
| Capability vocabulary | **EXISTS, frozen** — `["coding","reasoning","review","synthesis","research","voice_stt"]`, with a `capability_descriptor` sub-schema carrying `tool_use`, `min_context`, `structured_output`, `locality`, `harness_class`, `cost_class`, `priority`; validated by `jsonschema` at registration | `schemas/node.schema@1.1.json:41-61`, `adapters/roster.py:116-128` |
| Model lifecycle / residency states | **EXISTS** — six states `NOT_LOADED · LOADING · RESIDENT · AWAITING_EVICTION · QUEUED · EVICTED` (+`UNKNOWN` display-only), governed by invariant 22: *"local concurrency is hardware-bounded (8–14B tier); VRAM residency is scheduled, visible, never mid-generation eviction."* LRU on a monotonic counter, fail-closed on unsized or over-budget models | `scheduler/residency_planner/residency_planner.py:3-7,33-47` |
| Inference abstraction | **EXISTS but thin** — `class Backend(Protocol): name: str; def generate(prompt, *, max_tokens=256) -> str`. Local path is an HTTP POST to `http://127.0.0.1:11434/api/generate`. OpenCode drives `http://127.0.0.1:11434/v1`. Frontier is headless one-shot CLI returning JSON — **not** an interactive TUI. | `adapters/base/backend.py:26-29,82-92`, `adapters/detect.py:12`, `adapters/coding/opencode/driver.py:72`, `adapters/frontier/claude_code.py:394-406` |
| Context as a routing constraint | **EXISTS** — `min_context` is a hard filter: `if reqs.get("min_context",0) > provided.get("min_context",0): return False`. Local nodes advertise 32000; frontier 128000. | `scheduler/resolver/resolver.py:39-40`, `adapters/roster.py:73,87,99` |
| Named reasoning roles | **ABSENT — by design.** `PRIMARY_REASONER`, `CRITIC`, `SYNTHESIZER`: zero hits in `modules/sow/`. Debate participants are typed as capability descriptors, *"never vendor names (I-SC1)"*. `synthesis` and `review` are already capabilities. | `schemas/debate.schema.json:19` |
| Node-aware hardware orchestration | **ABSENT — and actively prohibited.** A "node" here is a local supervised **process/pane** (`pid`, `incarnation`, `session_id: "pane-2#32696.1"`), not a machine. No host, address, gpu, or vram field exists in the schema. `_is_loopback_ollama_host` **fail-closed drops any non-loopback `OLLAMA_HOST`**, with a test pinning it. | `control_plane/nodes/registry.py:131-141`, `schemas/node.schema@1.1.json:8`, `adapters/coding/opencode/harness.py:21-24,90,124-133`, `tests/unit/test_opencode_harness.py:128` |

**Reviewer note.** The existing design already achieved the directive's stated end-state principle — *"requests capabilities rather than vendors"* — and enforces it in the resolver and the debate schema. §14 and §15 of the directive would partially undo that by reintroducing fixed role names as a routing axis.

---

## 4. Technology verification — every named item is real

I verified each externally rather than assuming. All exist. Applicability is the variable.

| Named | Real? | Relevant finding |
|---|---|---|
| **llama.cpp router mode** | Yes | Enabled by starting `llama-server` with **no** `-m`. `--models-dir PATH`, `--models-max N` (default 4), `--no-models-autoload`. Auto-discovers GGUF from `--models-dir` or `~/.cache/llama.cpp`. On-demand load on first request; **LRU unload** at the cap. OpenAI-compatible: `POST /v1/chat/completions`, `GET /models` returning `loaded` / `loading` / `unloaded`, `POST /models/load`, `POST /models/unload`. |
| **Qwen3.8-27B** | Yes | **Already installed here.** Ollama tags include `qwen3.8:27b`, `qwen3.8:latest`, `orcarouter/Qwen3.8-27B-Uncensored:latest`. |
| **Gemma 4 12B / 26B-A4B** | Yes | **Already installed.** Tags `gemma4:12b`, `gemma4:26b`, `gemma4:31b`. `26B-A4B` is MoE — 26B total, 4B active — which is why the directive's schema carries `active_parameter_count`. That field is well-judged. |
| **ExLlamaV3 / EXL3** | Yes | Active project, "early preview" framing. GPU-resident by design; no meaningful CPU offload. |
| **NVFP4** | Yes | Merged into llama.cpp ~Mar–Apr 2026; Blackwell-native accel in build b8967. Measured **+43–68 % prefill** on Blackwell, token generation unchanged. Qwen3.6-27B ≈17 GB Q4_K_M → **≈14 GB NVFP4** (~18 % weight reduction). |
| **DFlash** | Yes | arXiv 2602.06036, ICML 2026 poster, NVIDIA Blackwell blog claiming up to 15×, vLLM `speculators` support. Block-diffusion speculative decoding. |
| **MTP** | Yes | Multi-token prediction; already visible in this environment — a local Ollama tag carries `…-MTP-GGUF`. |
| **Unsloth on Windows** | Yes, partially | Official native-Windows install docs exist. **But vLLM — required for GRPO — is documented as Windows-unsupported, WSL or Linux only.** Directive §1.1 forbids WSL. That is a self-conflict. |
| **Muse Glimmer** (Meta) | Yes | Open-weight, on-device agentic, released ~2026-08-10. |
| **Nemotron 3.5 Lightning** (NVIDIA) | Yes | Open, positioned as a fast agent worker. |

### 4.1 The one genuinely hardware-matched opportunity, and its caveat

The host is **Blackwell sm_120**, the exact architecture with native FP4 tensor cores. NVFP4 is therefore the one exotic item in the directive that actually matches this machine. But:

- 27B NVFP4 ≈ 14 GB — **still does not fit 8 GiB.** The saving does not cross the threshold that matters here.
- 12B-class at NVFP4 ≈ 6 GB — **does** fit, with KV headroom. That is the real target.
- Quality vs Q4_K_M is **unsettled**: *"No independent benchmark suite has run NVFP4 GGUFs against Q4_K_M."* Reported failure modes include *"looping output, broken tool-calling, or degraded instruction-following."*
- GGML has an **open correctness discussion**: `block_nvfp4` does not fully capture the tensor, the F32 scale is stored separately, and *"current `quantize_nvfp4`/`dequantize_row_nvfp4` functions inside GGML are incorrect when F32 != 1.0."* The compute graph needs an extra `GGML_OP_MUL` that is *"currently undocumented in GGML."*
- The conversion script PR is **open and unreleased**; Ollama and LM Studio integration pending.

**Recommendation: research lane with evidence gates, not a phase.** It is the highest-upside item and the least settled. Treating it as a deliverable would import an unresolved upstream correctness question into a governed production baseline.

---

## 5. Section triage

### 5.1 ADOPT — six extractions worth the work

| § | Idea | Why it is worth it |
|---|---|---|
| **8–11** | **llama.cpp router mode as a second runtime, beside Ollama** | The strongest idea in the document, and cheaper than it looks: a pinned binary and a config file, not code. It delivers §10 and §11 outright. **And it closes a real hole**: the residency planner *"holds NO GPU handle and makes NO real VRAM measurement — the total budget and each model's footprint are injected inputs."* Router mode's `GET /models` (`loaded`/`loading`/`unloaded`) plus `POST /models/{load,unload}` is exactly the missing measurement-and-actuation source the planner was written to consume. FACT[`residency_planner.py:10-14`] |
| **7** | **Model identity ≠ deployment artifact** | A genuine architectural gap. Today the registry keys on an Ollama tag, which fuses identity, quantization, and runtime into one string. One model with four GGUF quants plus an EXL3 is currently five unrelated entries. Cheap now, expensive to retrofit. Same class of correction as `model ≠ execution backend` in ADDENDUM-01 §4.2 — and for the same reason. |
| **19–20** | **Advertised context vs validated context** | A truthfulness defect of exactly the kind this governance framework exists to catch. `min_context` is a hard routing filter, but its values (32000 / 128000) are **declared constants, never measured**. Routing therefore makes promises nothing has verified. The tiering (STANDARD/DEEP/EXTENDED/ULTRA) is the right shape; validation evidence per model/context pair is the substance. |
| **51** | **Per-role fallback, reported and never silent** | Cheap, fits the existing filter-then-rank resolver, and the *"SHALL NOT silently hide it"* clause matches the house rule against fake state. |
| **56–57** | **Deployment manifest + automatic registry ingestion** | Eliminates manual transcription between Distillery output and registry. Fits the existing provenance discipline (`teachers.json` already carries `gguf_metadata`, hashes, `machine_local_paths: REMOVED_AND_HASHED`). Adopt the *manifest schema and ingestion contract* now even though artifact generation is hardware-blocked — the contract is free and de-risks later work. |
| **23** | **Speculative-decoding metadata fields only** | The directive itself says add the fields now and validate later. Correct. Free, forward-compatible, no runtime cost. **Do not** implement speculative execution here — see 5.3. |

### 5.2 MODIFY — right instinct, wrong shape for this system

| § | Issue | Correction |
|---|---|---|
| **12** | Premise is wrong — the abstraction already exists. | Do not build `InferenceBackend`. **Widen the existing `Backend` Protocol** from one method to the seven that matter: `list_models · load_model · unload_model · generate · cancel · health · capabilities`. Add `metrics` only once something consumes it. Far smaller and less disruptive than the directive implies. |
| **14–15** | Capability routing already exists; named roles would regress it. | Keep the descriptor-based resolver. Do not add `PRIMARY_REASONER`/`CRITIC`/`SYNTHESIZER` as a routing axis — `reasoning`, `review`, `synthesis` are already capabilities and the debate schema pins participants to descriptors *"never vendor names (I-SC1)"*. If the operator wants named roles for **display and configuration**, add them as labels over descriptor bundles, not as a second routing key. |
| **16–18** | Duplicates CP-01 Gate 8f, currently in flight. | Drop the duplicate. **Extract one thing:** the `SAFE` / `STANDARD` / `FULL_LOCAL_AGENT` permission-profile tiers. `permission_profile_id` already exists in the node schema; the tiers give it a vocabulary. Small and worth folding into 8f. |
| **32** | NVFP4/FP8 listed as routine "optional experimental" quantization targets. | Promote NVFP4 to its own **research lane with an explicit correctness gate**, tied to the open GGML discussion. Demote FP8 — no evidence it helps at this VRAM tier. |
| **40–42** | Model/runtime/resource screens proposed as separate phases. | Fold into CP-01's main-UI work rather than opening a parallel UI programme. Resource accounting (§42) is the highest-value part and pairs naturally with the router's `/models` data. |
| **45–46** | Unified logging and metrics — good, but greenfield as written. | The shell already has `LogRing` + a four-surface redaction layer, and the token meter already records *which* counting method it used. Extend those. Do not create a parallel `logs/` hierarchy that bypasses redaction. |

### 5.3 REJECT — for this machine, now

| § | Proposal | Reason |
|---|---|---|
| **25–27** | ExLlamaV3 as a "performance lane" | EXL3 is GPU-resident with no meaningful CPU offload. At 8 GiB it caps out around **7–8B at 4bpw**. The host's production models are 14–32B and run via RAM offload. This is not a performance lane on this box — it is a **capability-ceiling lane**. Revisit only if a ≥24 GB GPU is designated. |
| **24** | Speculative decoding **execution** | Requires target **and** draft resident simultaneously. With a 27B already spilling to system RAM, adding a second resident model is net-negative. DFlash's 15× figure is measured on datacentre Blackwell, not an 8 GB consumer card. Keep §23's metadata; skip the execution. |
| **30–31** | Unsloth as a Distillery backend | torch is not installed; `HG-3 = BLOCKED_HARDWARE_CAPACITY`; primary trainer `UNASSIGNED`. Building an adapter to a trainer that does not exist is building an adapter to nothing. Additionally: Unsloth's GRPO path needs vLLM, which is Windows-unsupported — and §1.1 forbids WSL. **The directive conflicts with itself here.** |
| **32–33** | Quantization matrix generation | Downstream of a canonical checkpoint this host cannot produce. Blocked by the same constraint. Adopt the *provenance fields* (§32's linkage requirements) without the generation pipeline. |
| **37–39** | Node-aware orchestration / remote nodes | **This is not a gap — it is an enforced invariant.** `build_env` deliberately *"drops a non-loopback `OLLAMA_HOST` (which would route the 'local' model to a remote/paid endpoint)"*, justified as a sovereignty guarantee and pinned by a test. Implementing §39 would require deleting that refusal. Also: **§39 and §54 of the same directive contradict each other** — one requires LAN listeners, the other requires 127.0.0.1 binding. This needs an **operator ruling**, not an implementation. |
| **43–44** | Module lifecycle states | §43's intent (nothing runs because the UI is open) is already CP-01 Gate 8b — and reconnaissance shows nothing autostarts today anyway. §44's proposed six states would **replace** the shell's normative v1.2 §7.4 machine (`NOT_STARTED · STOPPED · STARTING · READY · DEGRADED · FAILED · EXTERNAL · CONFIG_ERROR`), which is schema-frozen, test-pinned, and reviewer-`PASS` at Gate 4. Adopting it would invalidate Gates 2–6. Reject outright. |

### 5.4 ALREADY TRUE — no work required

§43's premise (modules consuming resources because the UI is open), §35's principle (experimental models must not silently replace roles — the resolver is descriptor-driven and cannot), §54's loopback binding (`OLLAMA_HOST` non-loopback already refused; Token Center already binds `127.0.0.1:8765`; shell already enforces Host/Origin/CSRF), §64's anti-drift list (already the standing house rule, and ADDENDUM-01 §7 states it in stricter terms).

---

## 6. Conflicts to resolve before any of this is scheduled

| # | Conflict | Consequence |
|---|---|---|
| K-1 | **Two writers on one registry.** §63 puts "02 Model registry" second in its order. CP-01 Gate 8g is doing exactly that right now. | Running both is `CONCURRENT_WRITER` — a CP-01 STOP condition. CP-02 must start **after** 8g is a reviewed candidate, not beside it. |
| K-2 | **Provider-spend exposure.** `config/live_operation.json` carries `"live_operation_authorized": true` with providers `["openai_codex_cli","claude_code","grok_build","google_antigravity"]`. The CP-01 authorization says **"no provider spend authorized."** | A worker spawn on the live path could bill against a subscription while a directive says spend is unauthorized. Reconcile explicitly — either narrow the config or widen the authorization. |
| K-3 | **§39 vs §54 within the supplied directive.** | Remote-node LAN listeners vs mandatory loopback binding. Unresolvable without an operator decision on whether multi-machine routing is wanted at all. |
| K-4 | **§1.1 (no WSL) vs §30–31 (Unsloth/GRPO).** | GRPO requires vLLM; vLLM is Windows-unsupported. The training lane as specified cannot be built under the stated constraint. |
| K-5 | **§44 vs contract §7.4.** | Adopting the proposed lifecycle states breaks a reviewer-PASSed, schema-frozen state machine. |

### 6.1 Incidental observation on the in-flight loop

CP-01 has written `evidence/cp01/session-start.txt` and nothing else; `evidence/cp01/tools/` is empty, so `goalcheck.py` — the loop's declared sole oracle — does not yet exist, and `LOOP-LEDGER.jsonl` is absent. At last check there had been no write for roughly eight minutes. It may have stalled at G0. Worth a `continue`.

Two useful G0 facts it did capture: ports 5175/8700/5180 are **free** (so the external-Debate case at G5 is not currently reproducible — the shell will need one started deliberately, or the goal recorded `NOT_RUN`), and 8765 is **LISTENING** (pid 30608, `piggybank.py`), which is the Token Center running from its original location. Also worth noting the loop caught and superseded its own bug: a capture function named `H` collided with PowerShell's `Get-History` alias and silently produced empty hashes. That is the evidence discipline working as designed.

---

## 7. What a CP-02 should actually contain

Ordered by dependency, scoped to what this hardware supports, and starting only after CP-01 Gate 8g is reviewed.

| Band | Work | Depends on |
|---|---|---|
| **A** | Install a pinned native-Windows llama.cpp beside Ollama. Nothing wired. Validate in the directive's own §9 order, starting with a small model — CPU-only, then CUDA, then offload, then server, then OpenAI API, then streaming, then cancellation, then shutdown. | CP-01 8g reviewed |
| **B** | Router mode: `--models-dir`, `--models-max`, `GET /models`, `POST /models/{load,unload}`. Prove on-demand load and LRU unload with recorded VRAM before/after. | A |
| **C** | Widen the `Backend` Protocol to seven methods. Add `LlamaCppBackend` beside the existing Ollama path. **Ollama stays the default** until C's suite is green. | B |
| **D** | Wire the router's `/models` into the residency planner as its real measurement and actuation source — the hole the planner was written around. | B, C |
| **E** | Split model identity from deployment artifact in the registry. Add the artifact record, the deployment-manifest schema (§56), and the ingestion contract (§57). | CP-01 8g |
| **F** | Context validation: measure, per model and per tier, what §20 lists. Replace declared `min_context` constants with validated values, and record the evidence. | C |
| **G** | Per-role fallback with visible reporting. Resource accounting surfaced in the UI. | C, D |
| **H** | Speculative-decoding and NVFP4 **metadata fields only**, plus an NVFP4 research lane gated on the upstream GGML correctness question. | E |

Deferred behind a hardware decision, not scheduled: ExLlamaV3, speculative execution, Unsloth, quantization matrix generation, remote nodes.

**Estimated envelope**: comparable to CP-01's 1,850 lines for bands A–E; F–H smaller. This is a second directive, not an extension of CP-01.

---

## 8. Open decisions — operator only

1. **Is a ≥24 GB GPU going to be designated?** This single answer determines whether §12–14, §25–27, and §30–33 are deferred work or dead work. The Distillery's D-HW-01 already asked it and it is still open.
2. **Is multi-machine routing wanted?** If yes, the loopback refusal in `opencode/harness.py` needs an explicit, evidenced repeal — it is currently a deliberate sovereignty guarantee with a test behind it. If no, §37–39 should be struck so they stop reappearing.
3. **Reconcile K-2**: narrow `live_operation.json`, or widen the spend authorization. Leaving both as-is is the kind of contradiction that produces an unintended charge.
4. **Do you want named roles as display labels?** They have real operator value; they should just not become a routing key.
5. **Does the Token Center move under `modules/`** (CP-01 Gate 8i) while it is running from its original location on 8765? A stale second copy is the predictable failure here.

---

## 9. Reviewer's bottom line

The document's own §66 states the invariant it should have been judged against: *"Models are assets. Runtimes are replaceable execution engines."* Sovereign already implements that — the resolver is vendor-blind, the roster is the single place a model is named, and the debate schema refuses vendor names outright. The directive's most valuable contribution is not the architecture it proposes but the **six specific gaps** it happens to expose: no second runtime, no artifact/identity split, unvalidated context claims, a residency planner with no measurement source, no fallback reporting, and no deployment-manifest contract.

Those are worth doing. The other 62 sections are either already done, blocked on a GPU that has not been bought, or in direct conflict with an invariant someone deliberately put there.

Adopting it whole would be the rewrite that both ADDENDUM-01 §7 and the directive's own §64 forbid.

*Every substantive statement above is tagged `FACT[path]` where an artifact supports it, or marked ABSENT where a search returned nothing. Hardware figures are read from a machine-written capture dated 2026-08-19, not from a live probe; a re-capture is advisable before any hardware-dependent decision. Recommendations authorize nothing.*
