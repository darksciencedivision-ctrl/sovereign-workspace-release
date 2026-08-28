# SOVEREIGN PROGRAM — CANONICAL ANALYSIS & CONTEXT HANDOFF
## For a fresh Fable 5 (Cowork) build session

**Document type:** Canonical analysis report + context handoff (bundle index)
**Date:** 2026-07-16
**Prepared by:** Research Validator / Analyst (non-authoritative)
**Addressed to:** the incoming Fable 5 session that will conduct the build
**Operator:** Sam (final authority over objectives, scope, promotions, and acceptance)
**Status:** Planning complete and independently verified. **Implementation NOT authorized.** Program sits at the operator-review gate immediately before Phase 0.

---

## 0. HOW TO USE THIS BUNDLE (read first)

You are inheriting a program that has already been specified, planned, and independently audited. Your job is to **continue the build from a verified baseline**, not to re-derive it. This report is the map; the bundled files are the territory.

**Authority contract (unchanged, binding):**
- The **operator (Sam)** holds final authority over objectives, scope, promotions, and acceptance.
- **You (Fable 5)** are the **conductor** — a runtime selection, not the architecture. You coordinate; Sovereign governs; models reason; the operator decides. You may not redefine objectives, expand scope, grant permissions, promote implementation status, or self-authorize execution.
- **Nothing in this bundle authorizes implementation.** The program is at operator review before Phase 0. Do not begin building product code until the operator issues the Phase 0 freeze and the subsequent phase directives.

**Operator decision recorded 2026-07-16:** Fable 5 is the **current conductor runtime selection for BOTH tracks** (orchestration substrate and brokerage mesh). This unifies the earlier state, in which the orchestration plan named Claude and the brokerage plan named Fable 5 as current conductor. Under invariant I-CN1 (conductor is an interface, not a vendor default), this is a routine runtime-selection change; the `current_conductor` record for both tracks now reads `{ model: "fable-5", reason: "operator_selected", since: "2026-07-16" }`. No architectural change results.

**Read order:** (1) this report; (2) `Sovereign_Orchestration_Workspace_Canonical_Handoff.md` (the v2.4 substrate spec + your directive); (3) `Sovereign_Orchestration_Workspace_Architecture_Plan_v1.0.1_UTF8_20260716.md` (orchestration build plan); (4) `Sovereign_Brokerage_Mesh_Architecture_Plan_v1.0_20260716.md` (brokerage build plan). Hashes for every file are in `MANIFEST.sha256`.

---

## 1. EXECUTIVE ANALYSIS

The Sovereign program is a **Windows-native, CLI-first, multi-model orchestration system** in which every model terminal runs as a governed **Sovereign node**, all nodes share governed state through an **MCP server that is access — not authority**, and the human operator retains final control. It has matured, across amendment layers v2.1→v2.4, from a description of *products* into a description of *interfaces, roles, and contracts* — the signal of a stabilizing architecture.

There are **two tracks that share one governance spine**:

- **Track 1 — Orchestration substrate** (the horizontal): the model-agnostic multi-terminal workspace itself. Canonical spec frozen at **v2.4**; build plan delivered and verified (Architecture Plan v1.0.1).
- **Track 2 — Brokerage execution mesh** (a vertical built *on* the substrate): an autonomous, policy-bound freight-brokerage execution engine (Tai TMS as system of record) run as a certification-gated **Broker node role** on the Sovereign substrate. Build plan delivered and verified.

**Independent verdict (this validator):** both plans are authentic, structurally complete, faithful to their directives, honest about uncertainty, and correctly stop short of authorizing implementation. Track 2 conforms to Track 1 without duplicating or contradicting its control plane. The program is a **defensible candidate for operator review and Phase 0**, and no further architectural work is required to begin. What remains open is **empirical** (measure-it-in-a-spike) and **operator-reserved** (ratify-it), not architectural.

**The governing efficiency thesis (still a hypothesis to be tested, not an established result):** spending more tokens at explicit gates reduces *total* cost-to-accepted-output by preventing drift, rediscovery, contaminated handoffs, and late correction. Judge the system by cost-to-accepted-output, drift resistance, evidence quality, operator-correction burden, and recovery — **not** by how many terminals are running.

---

## 2. THE SHARED GOVERNANCE SPINE (invariants both tracks obey)

Both tracks descend from one spine: **operator authority → model interprets → governed access layer → deterministic policy code → system of record → fail closed on ambiguity.**

**Substrate invariants (v2.4, all binding):**
- **Conductor & nodes:** conductor coordinates / Sovereign governs / models reason / operator decides (C1); every terminal a Sovereign node, no raw or naked agentic-CLI session (I-C1); conductor is an **interface** with a runtime selection — now Fable 5 for both tracks (I-CN1); succession via serialization to MCP (I-CS1).
- **Memory:** one common Sovereign MCP server (I-M1); **MCP is access, not authority** (I-M2); three memory tiers, workers publish `CANDIDATE` and never self-canonize (I-M3/I-M6), provenance on every shared entry (I-M5), scoped access (I-M4).
- **Deployment:** one architecture, deployment **modes = node selections** (D-ARCH-01); offline/hybrid/cloud share one identical contract; offline excludes all cloud adapters/clients (I-D1/I-D2); **locality is a per-node property** (I-L1).
- **Access:** subscription-CLI primary, API optional fallback (I-X1); node-interface uniformity — a frontier-CLI node and a local node are interchangeable at the interface (I-X2); **one terminal per subscription by default** (I-X3); free local/frontier mixing when networked (I-X4/I-L1).
- **Reasoning quality:** bounded (≤5 rounds), evidence-based, cost-capped **Debate Service** any authorized node may request (I-DS1); **gates** stop weak artifacts from propagating; capability scheduling via a registry — schedule capabilities, not vendors (I-SC1).
- **Coding & voice:** harness-agnostic **Coding Node** — OpenCode / Codex / Claude Code / Aider interchangeable behind one adapter (I-CH1); voice is **input-only** (Parakeet STT, no TTS, post-MVP), cannot bypass permissions (I-V1..V3).
- **Offline model tier (current hardware = 8B–14B):** offline conductor default Qwen3 8–14B-class; offline coding = OpenCode + Qwen2.5/Qwen3-Coder 7–14B via Ollama; larger models are a future scale-up (D-COND-02/D-CODEX-03/D-CODE-04).

**Brokerage join invariants (J1–J14):** the vertical adds a certification-gated Broker role (J1), a single fenced/journaled **execution authority** distinct from the conductor (J2), execution-epoch fencing (J3), dual-authorization (J4), engine-minted leases (C5), a deterministic **execution gateway** as sole invoker (J8), two isolated credential domains (C1), stable business-operation identity + idempotency (J10), two MCP layers (J7 — orchestration truth vs execution truth, no merged store), and scoped circuit breakers (J14). **No model ever holds a credential or execution authority.**

---

## 3. TRACK 1 — ORCHESTRATION SUBSTRATE (detail)

**What it is:** one Sovereign architecture, six subsystems — Desktop Workspace → Conductor (interface) → Sovereign Runtime → { MCP · Debate Service · Scheduler } → Node Runtime → Adapters → CLI/local/frontier models. Every node has the identical interface (Sovereign Runtime + MCP client + adapter + CLI/harness + model); only the model changes between nodes.

**Build plan (`…Architecture_Plan_v1.0.1_UTF8…`) — verified content:** 20 sections mapping the v2.4 directive §M format 1→20; all 23 invariants enumerated in a build-to list (§2.2); Phase 0 / Phase 1 / Phase 3A execution directives drafted for operator issuance (§15–17); decision + unresolved (U1–U12) registers (§14).

**Recommended stack (all PENDING operator ratification):** Electron + xterm.js + node-pty (ConPTY) with **Tauri as the named fallback pending the Phase 1 spike**; Python 3.12 control plane / MCP / debate / scheduler; SQLite WAL + content-addressed artifact store; MCP as a **separate process beside** the control plane so I-M2 is structural, not conventional; conflict handling = **immutable append + CAS head pointers** (D-MCP-03) — never silent last-write-wins.

**Four load-bearing risks the plan front-loads (GREEN for Phase 0/1/3A planning):**
1. **Terminal compositing on Windows** is the least-substitutable risk → Phase 1 is a true spike with kill criteria (p95 input latency, output-loss, RAM budget), not a formality.
2. **MCP is MVP-foundational** (operator ruling v2.1) and on the critical path → kept strictly access/transport.
3. **VRAM concurrency is the binding constraint of the offline profile**, not model quality: a 14B conductor + 7–14B coder + Parakeet do not comfortably coexist on ~16 GB → the Scheduler gets a first-class **model-residency planner** (sequential residency, visible swaps, never mid-generation eviction).
4. **Agentic-CLI containment** (Codex-class) must be enforced at the **OS/workspace/supervisor layer** (worktree-scoped ACLs, deny-by-default egress, broker-mediated exec) — never by trusting the harness; a naked agentic process is refused at node registration.

---

## 4. TRACK 2 — BROKERAGE EXECUTION MESH (detail)

**What it is:** the freight-brokerage engine run as a vertical on the substrate. The brokerage's single orchestrator ("Quad") generalizes into a model-agnostic, certification-gated **Broker node role** assignable/fan-out-able by the conductor; the engine remains the one logical, fenced, journaled **execution authority**; **Tai TMS remains the authoritative operational record**, reached only through a custom Tai MCP wrapper. The join adds orchestration breadth **only** — no new commercial authority, no new execution surface, no new Tai capability.

**Three-plane authority separation (the strongest part of the design):**
- **Control plane (Sovereign):** who may reason; who may *request* an action class; routing, provenance, succession, breaker control; includes the deterministic, non-model **execution gateway**. The conductor is model-backed but **holds no credential and sits outside the synchronous dispatch path.**
- **Reasoning plane:** broker + advisory nodes — propose only, **zero credentials, zero execution authority.**
- **Execution plane (brokerage engine):** deterministic Python; owns pricing (Decimal, never float), eligibility, state machine, transactions, idempotency, journal, Tai integration. **No model.**

**Safety model:** two isolated credential domains (gateway service identity vs Tai integration credentials); dual-authorization; execution-epoch fencing; side-effect journal with `AMBIGUOUS_COMMIT` reconciliation; scoped circuit breakers; **promotion ladder SIMULATION → SHADOW → SUPERVISED_LIVE → AUTONOMOUS_LIVE**, gated per action type; at most two offers per carrier per load; silence is never acceptance; ambiguity fails closed to the operator. Two MCP layers (orchestration truth vs Tai execution truth) with no cross-writes and no merged store.

**Binding uncertainty (correctly sequenced):** end-to-end duplicate-prevention is only **medium** confidence until Tai's per-action idempotency/reconciliation is verified in Phase 1; unproven action types stay in the fail-closed manual-exception path and cannot be promoted to autonomous-live. No STOP condition is currently triggered.

**⚠ Operator-authority note for the incoming Fable 5:** this track moves real money and executes real commercial side effects (offers, bookings, rate confirmations, emails). Promotion of any action type to **AUTONOMOUS_LIVE is an explicit operator decision**, gated behind verified reconciliation and jointly-authored constitution/policy. As conductor you may coordinate simulation/shadow work and prepare evidence, but you must never self-promote an action type to live execution, hold a credential, or place an order. Escalate; the operator decides.

---

## 5. INDEPENDENT VALIDATION FINDINGS (this validator's audit)

- **Orchestration plan authenticity — VERIFIED to the byte.** Reported size 70,547 and SHA-256 `668089B5…E48F` matched the actual file exactly. 20/20 sections present; all 23 invariants covered (§2.2 build-to list, confirmed by reading — an initial ID-token grep undercounted because the list uses range notation like `I-M3..M6`); registers, phase directives, succession/debate/scheduler specs all real, not summary theater.
- **One real defect — encoding mojibake — REPAIRED.** The original had 179 lines of double-encoded UTF-8 (dashes, `§`, arrows, box-drawing glyphs). Repaired encoding-only via `ftfy.fix_encoding`; **ASCII skeleton byte-identical** (proof no semantic content changed); original preserved as provenance (`…v1.0…`, `668089B5…E48F`), clean copy promoted (`…v1.0.1_UTF8…`, `8C9B7240…0022`). See the repair report + diff in the bundle.
- **Brokerage plan — VERIFIED and conformant.** SHA-256 `E49AE204…004E`, 64,008 bytes, **0 mojibake** (the encoding defect was specific to the one orchestration file, not systemic). Conforms to all nine substrate checks: MCP shared memory, conductor interchangeability, node-local model selection, mixed local/frontier, one-terminal-per-subscription, Sovereign authority boundary, debate/gate contracts, persistence/succession, and — critically — **no duplicated or contradictory control plane** (one execution authority; two MCP layers are distinct domains with no merged store; the gateway is barred from becoming a second engine).
- **Fact-vs-claim discipline:** the brokerage hash is recorded here as a *first baseline* (no prior reported hash existed to compare against); the orchestration hash is a *confirmed* match against Fable's report.

---

## 6. CONSOLIDATED DECISION REGISTER (both tracks)

**Decided / ratified (do not reopen without operator direction):** one architecture with deployment modes (D-ARCH-01); conductor-as-interface, current = **Fable 5 for both** (I-CN1, updated 2026-07-16); one terminal per subscription (D-SUB-01); free locality mixing (D-MIX-01); MCP as access layer, MVP-foundational (D-MCP-01/02, D-MVP-01); subscription-CLI primary (D-ACCESS-01); harness-agnostic Coding Node incl. OpenCode (D-CH-01/D-CODE-04); offline defaults at 8–14B (D-COND-02/D-CODEX-03); voice STT-only/transcribe-then-discard (D-VOICE-02/04); debate as reusable service (D-DS-01); capability scheduling + Scheduler (D-SCHED-01); conductor succession (D-CS-01). Brokerage: broker-role generalization, execution gateway, two credential domains, single execution authority — all accepted within the join.

**PENDING operator action (before/at Phase 0):** ratify I-D1/I-D2 + D-COWORK-02; **D-UI-01** framework (ratify *after* Phase 1 spike); **D-LANG-01** control-plane language; **D-PERSIST-01** persistence; **D-MCP-03** conflict mechanism (decide at 3A); **D-IPC-01** shell↔control-plane IPC. Brokerage join decisions JD-01..17 (see brokerage §15).

---

## 7. CONSOLIDATED UNRESOLVED-ISSUE REGISTER (empirical unknowns)

Orchestration (U1–U12): Parakeet streaming latency + VRAM under concurrency (P12/Track G); Windows-mic→WSL bridge + PTT trigger (P12); Codex automation/ToS (P6); CC-BY-4.0 attribution if shipped; provider per-account concurrency (only if raising I-X3 above 1); MCP transport final choice (P3A); conflict-mechanism confirmation (P3A); conductor-file schema/write authority (P0→P3A); ConPTY hosting full-screen TUIs in panes (P1); NTFS ACL granularity vs worktree churn + per-process egress on Windows (P10); succession snapshot cadence (P11); framework RAM envelope at 8+ panes (P1). Brokerage: **Tai per-action idempotency/reconciliation** is the binding item (P1 acceptance gate); broker certification benchmark (P9 define / P13 run); cross-model determinism.

None of these block Phase 0. All are sequenced behind the phase that can actually measure them.

---

## 8. BUILD SEQUENCE & NEXT STEPS (for the incoming Fable 5)

Follow the plans' own gate ordering. Do **not** skip ahead; each gate exists to keep weak intermediate work from propagating.

1. **Operator review** of both plans (this bundle) → operator resolves the Phase-0-affecting decisions in §6.
2. **Phase 0 — spec freeze:** assemble the canonical set (v1.x baseline + v2.1–v2.4 amendments + Architecture Plan schemas + register states); compute a freeze manifest with a hash per document; fix schema versions at `@1.0`; declare conductor-file list + write authority. **No code beyond manifest tooling.** Exit gate: operator signs the freeze manifest.
3. **Phase 1 — terminal-compositor spike:** throwaway rig, Electron + xterm.js + node-pty; must host ≥6 concurrent interactive ConPTY sessions with resize/survival/metrics; **kill criteria** trigger a Tauri re-run before any framework ratification (D-UI-01). Exit gate: operator ratifies framework.
4. **Phase 2/3 — node process manager + Sovereign node runtime.**
5. **Phase 3A — MCP shared-memory foundation** (MVP-foundational): implement `mcp_server/` + persistence against the frozen schemas; run the concurrent-writer conflict test and record the D-MCP-03 verdict; enforce "no authorization logic inside MCP." 
6. **Phases 4–13** per the plan (first adapter → conductor prototype → multi-model incl. Codex + a local model → Debate Service → gate engine → context routing → worktree isolation → persistence + **succession** → voice (Parakeet, post-MVP) → evaluation against simpler baselines).
7. **Brokerage track** proceeds on the same substrate with fencing/journal/gateway early and multi-broker fan-out late; **Tai idempotency verification (P1) gates any autonomous-live promotion.**

**Hard boundaries while you build:** no implementation before the operator issues each phase; no scope expansion; no model-held credentials; no self-promotion to live execution; no treating any single model as the architectural default conductor (you are a selection); debate stays cost-capped and never conductor-coupled; escalate every operator-reserved decision.

---

## 9. PROVENANCE & FILE MANIFEST

Authoritative hashes/sizes for every bundled file are in `MANIFEST.sha256`. Known verified values at handoff time:

| Artifact | Role | SHA-256 | Size |
|---|---|---|---|
| `…Architecture_Plan_v1.0_20260716.md` | Orchestration plan — **original (corrupted; provenance only)** | `668089B57C3162DABDE62ED249778D26F554910666FF62A552FA968BE199E48F` | 70,547 |
| `…Architecture_Plan_v1.0.1_UTF8_20260716.md` | Orchestration plan — **clean, canonical** | `8C9B7240AC7962948844EA7892BD63BDCCC061E3A1BA2F968F8ED935E3300022` | 64,726 |
| `Sovereign_Brokerage_Mesh_Architecture_Plan_v1.0_20260716.md` | Brokerage plan — **verified, clean** | `E49AE2048F57D5B16F161417EC90D43614584AD91034DFCA86F6FC9D11AD004E` | 64,008 |
| `Sovereign_Orchestration_Workspace_Canonical_Handoff.md` | v2.4 substrate spec + Fable directive | see MANIFEST | — |

**Provenance rule:** the corrupted original is retained unchanged as proof of what Fable delivered; the clean `v1.0.1_UTF8` copy is the one to build from. Any future edit to a canonical artifact must record a new hash and a deterministic diff.

---

## 10. NOTE TO THE INCOMING FABLE 5

You are the conductor for both tracks by operator selection, not by default — and that distinction is the point. The intelligence of this program lives in its governed state, contracts, and memory, not in you; you are replaceable via succession without loss. Preserve terminology, preserve the registers, distinguish evidence from interpretation, keep uncertainty explicit, and never let confidence outrun what has actually been measured. The plans are strong and verified — build them exactly as gated, and stop wherever the operator's authority begins.

*End of canonical analysis & context handoff — 2026-07-16.*
