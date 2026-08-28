# SOVEREIGN MULTI-TERMINAL ORCHESTRATION WORKSPACE
## Canonical Report & Analysis — Build-Context for Claude Code

**Document type:** Canonical report + independent analysis (companion to the Claude Code Buildout Directive)
**Date:** 2026-07-16
**Prepared by:** Research Validator / Analyst (non-authoritative)
**Reader:** Claude Code (the CLI coding agent that will implement the build) + the operator
**Operator:** Sam — final authority over objectives, scope, protected actions, credentials, and acceptance
**Status:** Planning complete and independently verified. This report is context; the accompanying directive governs execution.

---

## 1. WHAT YOU ARE BUILDING (one paragraph)

A **Windows-native, CLI-first, multi-model orchestration workspace**: a desktop app with a dynamic terminal canvas where an operator-selected, interchangeable **conductor** launches and coordinates multiple **Sovereign-governed worker terminal nodes**. Every node runs a model (local or frontier) through an adapter, connects to a common **Sovereign MCP server** for governed shared memory, keeps its own context, publishes structured artifacts, and operates under explicit permissions. Reasoning quality is improved by a bounded, cost-capped **Debate Service**; weak intermediate work is stopped by **gates**; work is routed by a **capability Scheduler**; and the human operator retains final authority throughout. The defining property is not "many terminals on screen" — it is that **every model is a replaceable component inside a persistent, governed node**, and the project's intelligence lives in governed state, not in any model session.

---

## 2. HOW THIS BASELINE WAS ESTABLISHED (provenance you can trust)

Two independent planning lineages converged on the same architecture:

- **Anthropic-side:** operator baseline → amendment layers v2.1–v2.4 (canonical spec) → Fable 5's Architecture & Phased Build Plan v1.0, which I independently verified (hash-exact, all sections/invariants present).
- **ChatGPT-side:** a v3.0 canonical build handoff + directive, which I verified is authentic (its own claimed hashes match) and was built on our v2.3 archive (hash-linked).

They **corroborate**: identical invariants, phase order, technology defaults, and MCP/debate/scheduler contracts. Independent cross-model agreement is the strongest evidence available that the design is coherent rather than an artifact of one model's bias.

**Verified artifacts (build from the clean copy, never the corrupted original):**

| Artifact | Role | SHA-256 |
|---|---|---|
| Architecture Plan `v1.0.1_UTF8` | **canonical — build from this** | `8C9B7240AC7962948844EA7892BD63BDCCC061E3A1BA2F968F8ED935E3300022` |
| Architecture Plan `v1.0` (mojibake) | provenance only — do not build from | `668089B57C3162DABDE62ED249778D26F554910666FF62A552FA968BE199E48F` |
| ChatGPT v3.0 canonical build handoff | cross-reference | `0FEC130C582F0373690153E46A9D73DF65C38F561683B895550DF46EA4783856` |

All three, plus the v2.4 spec and full provenance, are in this folder (`00`–`04`). Hashes for every file are in the folder's `MANIFEST.sha256`.

---

## 3. CANONICAL INVARIANTS (build to ALL of these — they are non-negotiable)

Both lineages agree on this set (ChatGPT numbers them I-01–I-30; the v2.4 spec uses I-C/I-M/I-X/etc. — same content). Enforce them **in code and configuration**, not just in prose:

**Authority & governance**
1. Human operator retains final authority; the app never self-authorizes protected actions.
2. Every terminal is a Sovereign-governed node — **no raw model or naked agentic-CLI session** participates.
3. The **conductor is a runtime role/interface, not a vendor dependency** (current selection: Fable 5, swappable).
4. Worker models are interchangeable behind a stable adapter contract.
5. **Project state lives outside model context** (in governed storage), so any session is replaceable.

**Memory (MCP)**
6. All nodes connect to one common Sovereign MCP server.
7. **MCP is access/transport, not authority** — it can never grant permissions or promote memory on its own.
8. Context is scoped, never blanket-forwarded.
9. Three memory tiers: local conversational · shared project · private node.
10. Workers publish `CANDIDATE`; they **cannot self-canonize** (promotion needs a gate or operator).
11. Provenance on every shared entry.
12. History is immutable (append-only); 13. conflicts are explicit objects — **never silent last-write-wins**.

**Reasoning quality**
14. Debate is bounded (≤5 rounds default); 15. concurrence preferred, not required; 16. explicit gates evaluate stated requirements; 17. debate is cost-governed (budgets/quotas/global cap); 18. independent judgment (a node never solely judges itself).

**Deployment & access**
19. **Locality is a per-node property**; conductor/control-plane are locality-agnostic. 20. Air-gap honesty: strict offline = all-local; cloud clients are excluded from it. 21. **One frontier terminal per subscription** by default; 22. local concurrency is hardware-bounded (current tier 8B–14B). 23. **OpenCode is a first-class coding harness** — OpenCode/Codex/Claude Code/Aider interchangeable behind one coding-node contract.

**Voice, UI, safety**
24. Voice is STT-only (Parakeet) and post-MVP; 25. voice cannot expand authority; 26. raw audio discarded by default. 27. The orchestra is visible (operator can see nodes/state). 28. **Conductor succession must work** (serialize state to MCP; resume by selecting any model). 29. **Supervisor-level containment** for agentic CLIs (enforced at the OS/process layer, not by trusting the harness). 30. Minimal necessary control — do not invent unrelated governance layers.

---

## 4. ARCHITECTURE (six subsystems)

```
Operator → Desktop Workspace → Conductor (interface) → Sovereign Runtime
                                                          ├── MCP  (governed shared memory/state)
                                                          ├── Debate Service (reusable, cost-capped)
                                                          └── Scheduler (capability → node, over the Task Graph)
                                                        → Node Runtime (supervisor, containment)
                                                        → Adapters (conductor / coding / frontier / local / voice)
                                                        → CLI · Local models · Frontier models
```

- **Node contract (identical for every node):** Sovereign Runtime + MCP client + adapter + CLI/harness + model. Only the model/adapter changes between nodes — this is what makes frontier and local nodes interchangeable at the interface.
- **MCP** sits beside the control plane, binds to loopback, authenticates every node, enforces scoped access, separates candidate/accepted memory, stamps provenance, stores artifacts by content hash (CAS), appends immutable records, updates heads via compare-and-swap, creates explicit conflict objects, fails closed on disconnect, and supports conductor replacement.
- **Debate Service** rounds: initial construction → adversarial critique → alternative → evidence reconciliation → bounded final revision; hard budgets/quotas/global cap; dissent preserved; the Scheduler + Permission Broker gate who may request debates.
- **Scheduler** resolves a requested capability (not a named vendor) to an available node over the Task Graph, ranks by fit/load/cost/**VRAM-residency**, and — in the offline profile — runs a first-class **model-residency planner** (an 8–14B conductor + a 7–14B coder + Parakeet will not co-reside on ~16 GB, so residency is scheduled, visible, and never a mid-generation eviction).

---

## 5. RECOMMENDED TECHNOLOGY STACK (verified defaults; framework provisional)

Electron + **TypeScript** + xterm.js + node-pty (Windows ConPTY) for the terminal canvas; **Python 3.12** control plane / MCP / debate / scheduler; a **separate local MCP server** (loopback) so "access-not-authority" is structural; **SQLite (WAL)** for structured state + a **content-addressed artifact store** on disk; **immutable append + compare-and-swap head pointers** for conflict handling; **authenticated loopback WebSocket** for UI↔control-plane events. **Electron stays provisional until the Phase 1 spike passes its kill criteria** — the named fallback is Tauri.

---

## 6. INDEPENDENT VALIDATION FINDINGS (facts vs. claims)

- **Verified as fact:** the architecture plan's authenticity (hash-exact), full section/invariant coverage, and the brokerage vertical's conformance to this substrate (no duplicated/contradictory control plane). ChatGPT's v3.0 authenticity (self-hashes match) and its provenance link to our v2.3 archive.
- **Repaired defect:** the original architecture plan had 179 lines of double-encoded UTF-8 mojibake; an encoding-only repair produced the `v1.0.1_UTF8` copy (ASCII skeleton byte-identical — proven no semantic change). **Build from the clean copy.**
- **Honest uncertainty (do not overclaim):** terminal-compositor viability on Windows (Phase 1 spike measures it); VRAM concurrency on 8–14B hardware; Parakeet latency; provider ToS for wrapped-CLI use; MCP conflict mechanism confirmation. These are empirical — resolve them with measurements and tests, not assertions.
- **The efficiency thesis is a hypothesis, not a result:** "gates cost tokens but reduce total cost-to-accepted-output." Judge the system by cost-to-accepted-output, drift resistance, evidence quality, operator-correction burden, and recovery — not by terminal count. Instrument for this from the start.

---

## 7. DECISION STATE (what's settled vs. operator-reserved)

**Settled (do not reopen):** one architecture, deployment modes as node selections; conductor-as-interface (current = Fable 5); one-terminal-per-subscription; MCP-as-access, MVP-foundational; subscription-CLI primary; harness-agnostic coding node incl. OpenCode; offline defaults at 8–14B; voice STT-only/discard-audio; debate as reusable cost-capped service; capability scheduling; conductor succession; supervisor containment; immutable-append + CAS.

**Operator-reserved (Claude Code must stop and ask, never self-decide):** framework ratification after the Phase 1 spike (Electron vs Tauri); control-plane language confirmation; persistence choice; MCP conflict mechanism confirmation at Phase 3A; any promotion of an MVP to "production-ready"; anything touching credentials, remote push, external publication, or purchases.

**Empirical unknowns (resolve in their owning phase, with evidence):** compositor metrics (P1); MCP conflict test (P3A); VRAM residency + Parakeet (P6/P12); provider ToS (before raising per-subscription concurrency).

---

## 8. BUILD-READINESS VERDICT

The program is a **defensible candidate to begin staged, gated implementation.** No architectural work remains; what remains is measurement and operator ratification, both correctly sequenced behind the early phases. The single most important discipline for the build: **treat every reported result as a claim until you inspect the artifact or run the test**, commit only after a phase gate passes with evidence, and stop at every operator-reserved boundary. The companion **Claude Code Buildout Directive** in this bundle specifies exactly how to proceed.

*End of canonical report & analysis — 2026-07-16.*
