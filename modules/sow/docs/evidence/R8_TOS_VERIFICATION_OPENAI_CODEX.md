# R8 — ToS & CONCURRENCY VERIFICATION RECORD — provider: **Codex CLI (OpenAI)**
Append-only finding record. Produced by autonomous loop sub-step `phase-15a.r8`, 2026-07-19Z.
This document is the build's durable analog of the Plan §18.3 step-5 requirement ("store
findings as ACCEPTED memory entries with source links + retrieval dates"): the live system
would hold this as an ACCEPTED MCP memory entry; in the staged build it is recorded here in the
append-only governance record (substitution per directive §6 — recording a runtime MCP ACCEPTED
entry is a live-operation action deferred to the live `.adapter`/operator run).

**Scope of this record:** exactly one provider — **Codex CLI (OpenAI)**, schema adapter id
`openai_codex_cli` — one of the **two** providers the operator authorized for a live path under
register **OP-6** (directive §11), the other being Claude Code (recorded separately in
`R8_TOS_VERIFICATION_CLAUDE_CODE.md`, sub-step `phase-14b.r8tos`). No provider beyond these two is
verified or authorized. Re-verify per provider **quarterly and before any allowance raise** (§18.3).

The concurrency question (why the governor allowance is **2**, not 1) is answered in §3 below and,
tying both OP-6 providers together, in `docs/evidence/R8_OP6_CONCURRENCY_BASIS_NOTE.md`.

---

## 0. Retrieval provenance (honest)

- **Basis:** OpenAI's published Codex CLI documentation and the structure of OpenAI's consumer
  **Terms of Use** + **Usage Policies**, as documented and stable to the assistant's **knowledge
  cutoff of January 2026**; plus the operator's own recorded action (register OP-8, 2026-07-19):
  the operator installed and authenticated the Codex CLI on this host (`npm install -g
  @openai/codex`, `codex login`).
- **Live-page retrieval status:** In this non-interactive autonomous session a live fetch of the
  legal/doc pages was **not completed** — `WebFetch` (permitted in principle under directive §2.7
  as a vendor-doc read) was **requested and not granted** in this session. Therefore this record
  carries **no dated verbatim quotation** of the current live legal text. (Identical limitation to
  the Claude Code R8 record §0 — recorded transparently, not hidden.)
- **Consequence (fail-closed):** the operational conclusions below are written **conservatively**
  and **do not depend on** any un-retrieved page. R8 for this build must license one thing:
  spawning the **first-party** `codex` CLI as a supervised terminal under the operator's own
  already-authenticated ChatGPT subscription — which rests on Codex CLI's *documented first-party
  design* and the operator's OP-6 authorization, not on a fresh legal reading. The **live-terms
  confirmation** (a dated read +, for any support-based concurrency claim, provider confirmation)
  is flagged **`[OPERATOR]`** and is an explicit entry/verification condition of the 15C live smoke
  (§6 below). Nothing live runs in `phase-15a.r8`.

---

## 1. §18.3(1) — Current consumer-subscription terms + usage policy (located)

The operator's authenticated Codex CLI access runs under a **consumer ChatGPT subscription
(Plus/Pro/Team) OAuth login** (`codex login` → "Sign in with ChatGPT"), governed by:
- **OpenAI Terms of Use** (`openai.com/policies/terms-of-use`) — the agreement for consumer
  ChatGPT / OpenAI product use.
- **OpenAI Usage Policies** (`openai.com/policies/usage-policies`) — prohibited-use categories
  applying across products.
- **Codex CLI documentation / repository** (the open-source `@openai/codex` CLI, its README and
  `codex --help` / `codex exec` reference, and OpenAI's Codex product docs) — the product's own
  supported-usage description, including non-interactive invocation.
- (API-platform use under an OpenAI API key would instead fall under the **API/Business/Service
  Terms**; **not** the path here — this build uses the ChatGPT-subscription sign-in via the CLI,
  never an API key. §2.2/§2.4 as amended by §10/§11.)

`[OPERATOR]` retrieval-date fields are intentionally left for the operator/host confirmation at the
15C live smoke (the assistant did not fetch the live pages this session — see §0).

## 2. §18.3(2) — Is wrapped / programmatic CLI invocation permitted under subscription auth?

**Finding — supported as designed for the ONE authorized path, with the same residual wrapper
interpretation flag noted for Claude Code.**

- **Codex CLI is OpenAI's official, first-party agentic coding CLI** (open-source, distributed as
  `@openai/codex`). It is explicitly built for terminal and **non-interactive / programmatic**
  invocation: an interactive TUI **and** a headless `codex exec "<prompt>"` mode intended for
  scripting, CI, and agent automation, with machine-readable output options. **Spawning `codex` as
  a supervised subprocess is therefore its *intended* operating mode**, categorically different from
  reverse-engineering or scraping a web product (the behaviour-automation / anti-circumvention
  clauses typically target the latter).
- **Subscription login is a supported auth mode.** Codex authenticates via either a **ChatGPT
  Plus/Pro/Team OAuth login** ("Sign in with ChatGPT") *or* an OpenAI API key. This project uses the
  **already-authenticated subscription login** exclusively (operator performed `codex login`,
  OP-8).
- **Residual interpretation flag (fail-closed):** the Plan records provider ToS interpretations for
  **wrapped-CLI automation under a third-party governance orchestrator** as a low-confidence area
  (Plan §21). Invoking the first-party CLI is well-supported; wrapping it in an external
  orchestrator is the part only the operator can authoritatively confirm against the **current**
  live terms. Per §18.3(6): ambiguity ⇒ the design stance stays **conservative** and the live-terms
  read is an `[OPERATOR]` item at 15C.

**Net:** the supervised `codex`-CLI terminal(s) this build runs are a first-party, as-designed
programmatic invocation under the operator's own subscription; the orchestration-wrapper
interpretation is flagged `[OPERATOR]` for live-terms confirmation at 15C. No API-only-automation
clause is invoked because no API key / API path is used.

## 3. §18.3(3) — Per-account concurrent-session allowance + rate/usage caps

**Finding — NO verified per-account concurrency NUMBER from OpenAI; the governor allowance of
`2` is OPERATOR-ORDERED (OP-6), not an inferred/verified concurrency finding, and stays
governor-capped + reversible.**

- OpenAI **does not publicly document a specific "N concurrent Codex sessions per account"**
  allowance for consumer subscription auth. A consumer ChatGPT subscription is a single-seat
  entitlement; usage is bounded by **rolling/time-windowed usage limits** (and Codex-specific rate
  limits) rather than by a published concurrency count. Exact current numbers are plan- and
  time-dependent and are **not** asserted here.
- **Because no per-account concurrency allowance is *verified* by provider documentation or support
  confirmation**, R8's empirical finding for `openai_codex_cli` is the same fail-closed
  **verified-at-1** as Claude Code (§18.3: "never raises concurrency on inference or silence").
- **The governor's effective allowance of `2` for this build does NOT derive from an inferred
  concurrency verification.** It derives from **explicit operator direction (register OP-6,
  directive §11(b)):** *"I-X3 allowance is raised to 2 terminals per subscription by explicit
  operator direction … the raise is operator-ordered, cap stays governor-enforced and reversible;
  never exceed 2 without a new ruling."* This is operator **authority**, not an R8 concurrency
  *finding* — the distinction is load-bearing for honesty and is recorded verbatim in
  `R8_OP6_CONCURRENCY_BASIS_NOTE.md`.
- **`SubscriptionGovernor` state (already landed at `phase-15a.governor`, not changed by this
  documentation sub-step):** `MAX_ALLOWANCE = 2` hard cap; default still `1`; the live-spawn path
  reads `allowance = live_auth.terminals_per_subscription` (the code-pinned OP-6 scope), never a
  self-granted number; `register_subscription(allowance > 2)` raises and registers nothing. R8's
  allowance-**raise-on-verification** branch remains **moot** — the raise here is by ruling, capped
  at 2, and a support-confirmed number (if ever obtained) would be an `[OPERATOR]` item, still
  bounded by the cap.

## 4. §18.3(4) — Session / auth lifetime (for the supervisor's auth-lifecycle handling)

- **Credential:** obtained by the operator via the `codex` CLI's own login (OAuth for
  ChatGPT-subscription auth), and **stored in the host-native credential store the CLI manages**
  (e.g. the CLI's own config/auth file under the user profile) — never in this repo, never in MCP.
  The Sovereign adapter (built live at 15C) **invokes** the authenticated CLI and **never reads,
  extracts, stores, or transmits the credential** (prohibition §2.2 stands in full; §11(d)
  reaffirms).
- **Expiry / re-auth:** OAuth sessions expire and require periodic re-authentication; the CLI
  surfaces auth failures on invocation. Per Plan §18.4, the adapter must surface auth state
  (`authenticated / expiring / expired / rate-limited`) as a node state and **pause fail-closed on
  expiry** (no silent API-key fallback; any fallback is an operator-visible adapter swap). Exact
  token-lifetime values are provider-internal and not asserted here; the design handles expiry by
  fail-closed pause, so a specific number is not required to proceed safely.
- **Node-controlled untrusted config (T2):** the Codex CLI reads project config (e.g. `AGENTS.md`,
  `~/.codex/config`) that a node/worktree can influence; 15C must treat that config as
  **node-controlled untrusted input** (directive §11 track 15C) and scope/pin it — analogous to the
  OpenCode `OPENCODE_CONFIG` isolation discharged at U30. Recorded here as a 15C entry condition,
  not discharged by this documentation sub-step.

## 5. §18.3(5) — Findings stored with source links + retrieval dates

- **Stored as:** this append-only record (`docs/evidence/R8_TOS_VERIFICATION_OPENAI_CODEX.md`) — the
  build's ACCEPTED-memory-entry analog (§0 substitution). Source links: §1 above. **Retrieval
  dates:** `[OPERATOR]` — the assistant did not fetch the live pages this session (§0); the
  operator/host records the dated retrieval at the 15C live-terms confirmation.
- The live system would additionally seed this as an ACCEPTED MCP memory entry when it operates
  live; that write is deferred to the live run (a live-operation action).

## 6. §18.3(6) — Ambiguity handling + `[OPERATOR]` flags

- **Default stance held (fail-closed):** concurrency is **not** raised on inference or silence; the
  effective `2` is operator-ordered and governor-capped (§3). The wrapped-CLI interpretation stays
  conservative pending a live-terms read.
- **`[OPERATOR]` confirmation items — verification conditions for the 15C live smoke:**
  1. Complete the **dated live-terms retrieval** (OpenAI Terms of Use + Usage Policies + Codex CLI
     docs) on the authenticated host and record retrieval dates + any quotations bearing on
     wrapped-CLI automation under a governance orchestrator.
  2. Confirm nothing in the current terms **prohibits** running the first-party `codex` CLI under
     the operator's own subscription from a supervising process for the operator's own use. If any
     clause is found that does prohibit it, **do not run the live smoke** — record and
     skip-with-record (directive §10.4); the rest of Phase 15 is unaffected.
  3. Any claim of a **specific verified per-account concurrent-session number** requires a provider
     **support confirmation** (§18.3). None is asserted here; the effective `2` rests on OP-6, not
     on such a number, and stays capped at 2.

---

## 7. Disposition & register linkage

- **R8 verification for Codex CLI (OpenAI): RECORDED (this document), before any live call.**
  Directive §11 track 15A ("dated R8 records for both providers") is satisfied for the
  `openai_codex_cli` provider by this record; the `claude_code` provider was recorded at
  `phase-14b.r8tos`. The dated OP-6 concurrency-basis note tying both to allowance `2` is
  `docs/evidence/R8_OP6_CONCURRENCY_BASIS_NOTE.md`.
- **Concurrency finding:** `verified_concurrency_allowance(openai_codex_cli) = 1` (no verified
  per-account number); the **effective governor allowance = 2 is operator-ordered (OP-6)**,
  governor-capped, reversible — not an R8 verification. `SubscriptionGovernor` already carries this
  (landed at `phase-15a.governor`); **no code changed by this sub-step.**
- **Register updates (append-only):** U3 (Codex ToS) moves from "out of scope" to **RECORDED under
  OP-6**; U5 (per-account concurrency) dated note: verified-at-1 for both providers, the =2 is
  operator authority not verification.
- **Still ahead in Phase 15:** `phase-15a.statusbar` (n/2 status bar, D-P14-1 Electron exercise) →
  `phase-15a.gate` (high-stakes `gate/phase-15a`, mandatory gate-validator, subscription-governor
  deep re-inspection); the live Codex adapter + its one live smoke per available model land at
  **15C** (entry-gated on the operator-installed/authenticated `codex` CLI — OP-8 records login
  done; 15C re-checks presence live).
- **No live call and no credential handling occurred in `phase-15a.r8`.**

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
