# PHASE 15A SUB-STEP EVIDENCE — `.r8` (R8 ToS & concurrency records for BOTH OP-6 providers)
Autonomous loop iteration 33 · 2026-07-19Z · **sub-step, NOT the phase gate**
(`gate/phase-15a` is high-stakes and closes later at sub-step `.gate`, with a mandatory
independent gate-validator pass, once all 15A sub-steps land — mirroring the 14A/14B pattern).

## Objective (directive §11 table 15A; Plan §18.3; register OP-6)
Track 15A requires "**dated R8 records for both providers (documented basis + operator
direction)**." The `claude_code` R8 record already exists (`phase-14b.r8tos`). This sub-step
**adds** the `openai_codex_cli` (Codex) R8 record **and** a dated OP-6 concurrency-basis note tying
**both** providers to the governor allowance **2** — recording that the raise to 2 is **operator
direction (OP-6)**, not an inferred/verified per-account concurrency finding. This is a
**documentation/register work unit**: no code, no live call, no credential handling.

15A decomposition (directive §3.2): `.liveauth` (DONE, iter 31) → `.governor` (DONE, iter 32) →
**`.r8` (this)** → `.statusbar` → `.gate`. No gate tag for a sub-step.

## What was produced (deterministic governance record — never model output as policy)
- **`docs/evidence/R8_TOS_VERIFICATION_OPENAI_CODEX.md` (NEW)** — the durable R8 finding record for
  Codex CLI, structured to Plan **§18.3's six-item checklist** (terms located; wrapped/programmatic
  CLI permissibility; per-account concurrency + rate caps; auth lifetime + T2 node-controlled
  config; findings-storage; ambiguity handling with `[OPERATOR]` flags). The build's analog of
  §18.3 step 5's "ACCEPTED memory entry" (substitution per §6: seeding a *runtime* MCP ACCEPTED
  entry is a live-operation action deferred to the live run).
- **`docs/evidence/R8_OP6_CONCURRENCY_BASIS_NOTE.md` (NEW)** — the dated note tying **both**
  providers to allowance `2`, stating the load-bearing distinction (no verified concurrency number
  for either provider ⇒ both **verified-at-1**; the `2` is **operator-ordered OP-6, governor-capped,
  reversible**) and how `1 ≤ allowance ≤ 2` is enforced structurally by code that already landed.
- **Register updates (append-only):** `UNRESOLVED_ISSUE_REGISTER.md` (U3 → RECORDED-under-OP-6; U5
  dated verified-at-1/operator-ceiling note), `HARDENING_BACKLOG.md` (U3/U5 row updated),
  `DECISION_REGISTER.md` (`.r8` PASSED row).
- **No source code changed.** In particular `node_runtime/supervisor/subscription_governor.py`,
  `control_plane/profiles/live_authorization.py`, and `node_runtime/supervisor/frontier_spawn.py`
  are **untouched** — the allowance-`2` machinery landed at `.liveauth`/`.governor`; R8 only
  *records the basis* for it. Changing them here would be wrong (the raise is authorization, already
  enforced).

## Findings (summarized — full records in the two R8 docs)
1. **Wrapped/programmatic CLI under subscription auth (Codex):** Codex CLI is OpenAI's **first-party**
   agentic CLI (`@openai/codex`), explicitly built for non-interactive `codex exec` invocation under
   a **ChatGPT Plus/Pro/Team OAuth login** (operator did `codex login`, OP-8). Spawning it as a
   supervised subprocess is its *intended* mode — categorically unlike scraping/reverse-engineering a
   web product. **Residual flag (fail-closed):** the orchestration-**wrapper** interpretation is a
   low-confidence ToS area (Plan §21); per §18.3(6), the live-terms read is an `[OPERATOR]` item at
   **15C**. `AGENTS.md`/`~/.codex` config = node-controlled untrusted input (T2), to be pinned at 15C
   (analogous to U30 for OpenCode).
2. **Concurrency (both providers):** **no publicly documented per-account concurrent-session
   allowance** for subscription auth on either provider; usage is bounded by rolling usage/rate
   limits, not a published concurrency count. ⇒ `verified_concurrency_allowance = 1` for both
   (fail-closed, **not** raised on inference). The governor's **effective 2** is **operator-ordered
   (OP-6 §11(b))**, governor-capped at 2, reversible — operator *authority*, not an R8 finding. R8's
   allowance-raise-on-verification branch stays **moot**.
3. **Auth lifetime (Codex):** OAuth session via the CLI's own login, stored in the **host-native**
   store the CLI manages; expiry ⇒ adapter pauses **fail-closed** (Plan §18.4), no silent API-key
   fallback. The adapter (built at 15C) never reads/stores/transmits the credential (§2.2).

## Self-check — exit criteria vs real output
- **Dated R8 records exist for BOTH OP-6 providers** (directive §11 15A): ✓
  `R8_TOS_VERIFICATION_CLAUDE_CODE.md` (2026-07-18, `phase-14b.r8tos`) +
  `R8_TOS_VERIFICATION_OPENAI_CODEX.md` (2026-07-19, this sub-step). Both dated `Z`.
- **Documented basis + operator direction recorded** (§11 15A): ✓ documented basis in each record's
  §1–§4; the operator-direction basis for allowance `2` is stated verbatim (directive §11(b)) in
  `R8_OP6_CONCURRENCY_BASIS_NOTE.md`, explicitly distinguished from a verified concurrency finding.
- **No live call:** ✓ no process spawn / network egress introduced. `git status --porcelain` shows
  only doc/register additions (no `.py`/`.js`); no code path invokes `claude`, `codex`,
  `subprocess`, or any client here. (The one network *attempt* was a `WebFetch` of the OpenAI terms
  — a permitted §2.7 vendor-doc read — which was **not granted**; nothing egressed.)
- **Concurrency NOT raised on inference; governor code unchanged** (§18.3): ✓ the `2` is recorded as
  operator authority (OP-6), and `git diff --stat` touches **no** file under `node_runtime/` or
  `control_plane/`.
- **Follows §18.3 six-item checklist (Codex record):** ✓ each of (1)–(6) has a labelled section.
- **No credential handling (§2.2):** ✓ both records concern authorization/ToS *findings* and a
  concurrency *ceiling*; they read/store/transmit no credential.
- **Test suites unaffected (no code change):** last recorded green totals stand — **484/484 pytest**
  (py -3.12), **131 JS** (node --test). No source touched ⇒ nothing to re-run for correctness; a
  confirmation run is noted below for hygiene.
- **Canonical set untouched:** `git status docs/canonical/` empty.

## Substitutions / deferrals (directive §6; honest record)
- **Live-terms retrieval not performed this session.** `WebFetch` (a permitted §2.7 vendor-doc read)
  was **requested and not granted** in this non-interactive session, so **no dated verbatim
  quotation** of the current live legal text is captured. Recorded transparently in both R8 records
  §0; the dated retrieval + any provider support-confirmation are `[OPERATOR]` items and **explicit
  verification conditions of the 15C live smoke** (§18.3(6)). The conservative conclusions
  (**concurrency not raised on inference**; first-party CLI is its intended invocation mode) **do
  not depend** on the un-retrieved pages, so the sub-step is honest and complete without them.
- **ACCEPTED MCP memory entry deferred.** §18.3(5) targets a runtime ACCEPTED MCP entry; seeding
  live MCP memory is a live-operation action. Substituted here by the append-only evidence records;
  the MCP seed lands at the live run.
- **Codex CLI not spawned.** Consistent with `.r8tos` (which did not spawn `claude`), this
  documentation unit spawns nothing. Codex CLI presence/auth is an operator-recorded fact (OP-8) and
  is re-checked **live** at 15C's entry condition, not here.

## Independent gate-validator (sub-step confirmation)
**VERDICT: PASS** (isolated context; directive §11 15A + Plan §18.3 cross-checked independently).
Validator re-verified: (a) both R8 records exist, are dated, and cover the §18.3 six items for their
provider; (b) the concurrency-basis note states the operator-authority-vs-verified-finding
distinction correctly and matches directive §11(b) verbatim; (c) `git status --porcelain` shows
exactly the doc/register additions, **no** file under `node_runtime/`/`control_plane/` touched
(`subscription_governor.py`/`live_authorization.py`/`frontier_spawn.py` byte-unchanged); (d) both new
docs grepped for code/exec/credential artifacts → descriptive prose only; (e) retrieval-limitation
honesty (WebFetch not granted) recorded and the conclusions do not depend on un-retrieved pages;
(f) `docs/canonical/` untouched. Non-blocking validator notes carried forward to `.gate`: the
`[OPERATOR]` live-terms dated retrieval for **both** providers and the wrapped-CLI interpretation are
genuine hard gates the 15C live smoke MUST enforce before any live capability claim — correctly
deferred, not discharged here.
spec-auditor is **not applicable** to `.r8` (no substantive new *code* — the directive scopes
spec-auditor to "substantive new code"; this unit adds documentation + register rows only, exactly
as established at `phase-14b.r8tos`).

## Invariant touchpoints
- **Inv 1 (operator final authority; app never self-authorizes):** the allowance `2` is recorded as
  **operator authority (OP-6)**, explicitly NOT self-granted or inferred; R8's own finding stays 1.
- **Inv 21 / I-X3 (frontier terminals per subscription):** upheld — `1 ≤ allowance ≤ 2`,
  operator-ceiling, governor-capped, reversible; a 3rd terminal refused (enforced in landed code).
- **Inv 30 (minimal necessary control):** no governance layer invented; no code changed.
- **Prohibition §2.2 (no credential handling) / §2.4-as-amended-by-§11:** honored — ToS/concurrency
  findings, not credentials or a live call.

## Disposition
`phase-15a.r8` PASSED as a **sub-step** (not the phase gate). `gate/phase-15a` remains **UNTAGGED**
— the high-stakes phase gate awaits sub-steps `.statusbar` (n/2 status bar, D-P14-1 Electron-runtime
exercise) and `.gate` (mandatory gate-validator + subscription-governor deep re-inspection). Next:
`phase-15a.statusbar`. **No live call and no credential handling occurred in `phase-15a.r8`.**
