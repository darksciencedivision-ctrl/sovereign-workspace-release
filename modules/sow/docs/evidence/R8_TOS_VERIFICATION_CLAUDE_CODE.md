# R8 — ToS & CONCURRENCY VERIFICATION RECORD — provider: **Claude Code (Anthropic)**
Append-only finding record. Produced by autonomous loop sub-step `phase-14b.r8tos`, 2026-07-18Z.
This document is the build's durable analog of the Plan §18.3 step-5 requirement ("store
findings as ACCEPTED memory entries with source links + retrieval dates"): the live system
would hold this as an ACCEPTED MCP memory entry; in the staged build it is recorded here in the
append-only governance record (substitution per directive §6 — recording a runtime MCP ACCEPTED
entry is a live-operation action deferred to `.adapter`/operator run).

**Scope of this record:** exactly one provider — **Claude Code**, the only provider the operator
authorized for a live path (register OP-4/OP-5, directive §10). No other provider is verified or
authorized here. Re-verify per provider **quarterly and before any allowance raise** (§18.3).

---

## 0. Retrieval provenance (honest)

- **Basis:** Anthropic's published Claude Code documentation and the structure of Anthropic's
  Consumer Terms of Service + Usage Policy, as documented and stable to the assistant's
  **knowledge cutoff of January 2026**.
- **Live-page retrieval status:** In this non-interactive autonomous session a live fetch of the
  legal/doc pages was **not completed** — `WebFetch` (permitted in principle under directive §2.7
  as a vendor-doc read) was **not granted** in this session. Therefore this record carries **no
  dated verbatim quotation** of the current live legal text.
- **Consequence (fail-closed):** the operational conclusions below are written **conservatively**
  and **do not depend on** any un-retrieved page. The one action R8 must license for this build —
  spawning the **first-party** `claude` CLI as **one** supervised terminal under the operator's
  own already-authenticated subscription — rests on Claude Code's *documented first-party design*,
  not on a fresh legal reading. The **live-terms confirmation** (a dated read + support
  confirmation) is flagged **`[OPERATOR]`** and is an explicit entry condition of the `.adapter`
  live smoke (§18.3 step 6; see §6 below). Nothing live runs in `.r8tos`.

---

## 1. §18.3(1) — Current consumer-subscription terms + usage policy (located)

The operator's authenticated Claude Code access runs under a **consumer Claude subscription
(Pro/Max) OAuth login**, governed by:
- **Anthropic Consumer Terms of Service** (`anthropic.com/legal/consumer-terms`) — the agreement
  for Claude.ai / Claude subscription consumer use.
- **Anthropic Usage Policy / Acceptable Use** (`anthropic.com/legal/aup`) — prohibited-use
  categories applying across products.
- **Claude Code documentation** (`docs.anthropic.com/en/docs/claude-code/…` — overview, CLI
  reference, headless/SDK, IAM/authentication) — the product's own supported-usage description.
- (Commercial API use would instead fall under the **Commercial Terms**; **not** the path here —
  this build uses subscription auth via the CLI, never an API key. §2.2/§2.4 as amended by §10.1.)

`[OPERATOR]` retrieval-date fields are intentionally left for the operator/host confirmation at
`.adapter` (the assistant did not fetch the live pages this session — see §0).

## 2. §18.3(2) — Is wrapped / programmatic CLI invocation permitted under subscription auth?

**Finding — supported as designed for the ONE authorized path, with a residual interpretation
flag for the wrapper.**

- **Claude Code is Anthropic's official, first-party agentic coding CLI.** It is explicitly built
  for terminal and **non-interactive / headless / programmatic** invocation: print mode
  (`claude -p "<prompt>"`), machine-readable `--output-format json|stream-json`, and the first-party
  **Claude Agent SDK** — all documented and marketed for scripting, CI, and agent/subagent
  orchestration. **Spawning `claude` as a supervised subprocess is therefore its *intended*
  operating mode**, categorically different from reverse-engineering or scraping a web product
  (the behaviour automation/anti-circumvention clauses typically target).
- **Subscription login is a supported auth mode.** Claude Code authenticates via either a
  **Claude Pro/Max OAuth login** *or* an Anthropic Console API key (plus enterprise Bedrock/Vertex).
  This project uses the **already-authenticated subscription login** exclusively.
- **Residual interpretation flag (fail-closed):** the Plan itself records that provider ToS
  interpretations for **wrapped-CLI automation under a third-party governance orchestrator** are a
  low-confidence area (Plan §21 "Low confidence / explicitly unverified": *"provider ToS
  interpretations for wrapped-CLI automation (R8 — the design's 1-terminal default is deliberately
  conservative pending verification)"*). Invoking the first-party CLI is well-supported; wrapping
  it in an external orchestrator is the part that only the operator can authoritatively confirm
  against the **current** live terms. Per §18.3(6): **ambiguity ⇒ default stance stays 1 terminal,
  flag `[OPERATOR]`.**

**Net:** the single supervised `claude`-CLI terminal this build runs is a first-party,
as-designed programmatic invocation; the orchestration-wrapper interpretation is flagged
`[OPERATOR]` for live-terms confirmation at `.adapter`. No API-only-automation clause is invoked
because no API key / API path is used.

## 3. §18.3(3) — Per-account concurrent-session allowance + rate/usage caps

**Finding — NO verified per-account concurrency number; allowance STAYS 1 (I-X3). No raise.**

- Anthropic **does not publicly document a specific "N concurrent Claude Code sessions per
  account" allowance** for consumer subscription auth. A consumer subscription is a single-seat
  entitlement; concurrent-session behaviour is not published as a guaranteed number.
- Usage under a subscription is bounded by **rolling usage limits** (documented as time-windowed
  limits on Pro/Max; Claude Code usage draws from the same subscription limits) rather than by a
  published concurrency count. Exact current numbers are plan- and time-dependent and are **not**
  asserted here.
- **Because no per-account concurrency allowance is *verified* (§18.3: "record per-account
  concurrent-session allowance … The system never raises concurrency on inference or silence"),
  the recorded `verified_concurrency_allowance` for Claude Code REMAINS the fail-closed default
  of `1`.** This exactly matches I-X3 and the operator's OP-4/OP-5 scope (`terminals: 1`).
- **`SubscriptionGovernor` is therefore UNCHANGED** (`node_runtime/supervisor/subscription_governor.py`
  already defaults `allowance = 1` and documents "only raised after a provider's per-account
  concurrency is verified (R8) — never on inference or silence"). R8's allowance-**raise** branch
  is **moot** for this build: the operator authorized exactly one terminal, and R8 verifies no
  basis to exceed it. **No code change is made by this sub-step.**

## 4. §18.3(4) — Session / auth lifetime (for the supervisor's auth-lifecycle handling)

- **Credential:** obtained by the operator via the `claude` CLI's own login (OAuth for
  subscription auth), and **stored in the host-native credential store the CLI manages** — never in
  this repo, never in MCP. The Sovereign adapter (built in `.adapter`) **invokes** the authenticated
  CLI and **never reads, extracts, stores, or transmits the credential** (prohibition §2.2 stands
  in full; §10.1 reaffirms).
- **Expiry / re-auth:** OAuth sessions expire and require periodic re-authentication; the CLI
  surfaces auth failures on invocation. Per Plan §18.4, the adapter must surface auth state
  (`authenticated / expiring / expired / rate-limited`) as a node state and **pause fail-closed on
  expiry** (no silent API-key fallback; any fallback is an operator-visible adapter swap). Exact
  token-lifetime values are provider-internal and not asserted here; the design handles expiry by
  fail-closed pause, so a specific number is not required to proceed safely.

## 5. §18.3(5) — Findings stored with source links + retrieval dates

- **Stored as:** this append-only record (`docs/evidence/R8_TOS_VERIFICATION_CLAUDE_CODE.md`) — the
  build's ACCEPTED-memory-entry analog (§0 substitution). Source links: §1 above. **Retrieval
  dates:** `[OPERATOR]` — the assistant did not fetch the live pages this session (§0); the
  operator/host records the dated retrieval at the `.adapter` live-terms confirmation.
- The live system would additionally seed this as an ACCEPTED MCP memory entry when it operates
  live; that write is deferred to `.adapter`/operator run (a live-operation action).

## 6. §18.3(6) — Ambiguity handling + `[OPERATOR]` flags

- **Default stance held:** **1 terminal** for Claude Code — unchanged, fail-closed, matches I-X3
  and OP-4/OP-5. Concurrency is **not** raised on inference or silence.
- **`[OPERATOR]` confirmation items — explicit entry conditions for `.adapter`'s live smoke:**
  1. Complete the **dated live-terms retrieval** (Consumer Terms + Usage Policy + Claude Code
     IAM/headless docs) on the authenticated host and record retrieval dates + any quotations that
     bear on wrapped-CLI automation under a governance orchestrator.
  2. Confirm nothing in the current terms **prohibits** running the first-party `claude` CLI under
     the operator's own subscription from a supervising process for the operator's own use. If any
     clause is found that does prohibit it, **do not run the live smoke** — record and
     skip-with-record (directive §10.4); the rest of Phase 14 is unaffected.
  3. Keep concurrency at **1** unless a provider **support confirmation** of a specific per-account
     concurrent-session allowance is obtained (§18.3) — none is asserted here.

---

## 7. Disposition & register linkage

- **R8 verification for Claude Code: RECORDED (this document), before any live call.** Directive
  §10.1 / §9-table-14B entry condition (2) is satisfied for the `.r8tos` sub-step.
- **Concurrency finding:** `verified_concurrency_allowance(claude_code) = 1` (unverified above 1);
  `SubscriptionGovernor` default unchanged; I-X3 intact.
- **Unresolved items:** U5 (per-account concurrency allowance) — dated note appended:
  *no verified allowance for Claude Code; stays 1*. U3 (Codex automation/ToS) — **remains OPEN and
  out of scope**: Codex is not an authorized provider (only Claude Code is, OP-5); its R8 is not
  performed here.
- **Still ahead in Phase 14B:** `.adapter` (mock-first, then exactly ONE live smoke, gated on the
  §6 `[OPERATOR]` confirmations) → `.gate` (high-stakes `gate/phase-14b`, mandatory gate-validator,
  including the subscription-governor deep re-inspection).
- **No live call and no credential handling occurred in `.r8tos`.**

---
## OPERATOR CONFIRMATION — R8 §6 item 2 (appended 2026-07-19, OP-9)
The operator (Sam) has determined and confirmed, via explicit in-session decision
("Go live — run it"), that their **current** consumer subscription terms for this provider
permit a supervised local process (the Sovereign conductor node) to invoke the provider's
**first-party CLI** under the operator's **own subscription**, for the operator's **own
use**. This is the same invocation pattern the build loop itself has used continuously
(the runner spawns the provider CLI under the operator's subscription). This confirmation
**discharges the R8 §6 item-2 [OPERATOR] entry condition** and authorizes the Phase 15D
live smoke and live legs. Recorded as decision-register OP-9. Credentials remain in the
provider's host-native store and never enter the repo or MCP.
