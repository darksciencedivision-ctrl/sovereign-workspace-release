# PHASE 14B SUB-STEP EVIDENCE — `.r8tos` (R8 ToS & concurrency verification, Claude Code)
Autonomous loop iteration 21 · 2026-07-18Z · **sub-step, NOT the phase gate**
(`gate/phase-14b` is high-stakes and closes later at sub-step `.gate`, with a mandatory
independent gate-validator pass, once all 14B sub-steps land — mirroring the 14A pattern).

## Objective (directive §9 table 14B, §10.1; Plan §18.3; register OP-4/OP-5)
Before any live call, **record the R8 ToS verification for the one authorized live provider —
Claude Code** — and record the **subscription-concurrency finding** that would raise the
`SubscriptionGovernor` allowance above the default `1` **only if** the provider's per-account
concurrency is *actually verified* (else it stays `1`, I-X3). This is a **documentation/register
work unit**: no code, no live call, no credential handling.

14B decomposition (directive §3.2): `.liveflag` (DONE, iter 20) → **`.r8tos` (this)** →
`.adapter` (claude CLI adapter, mock-first then one live smoke) → `.gate`. No gate tag for a
sub-step.

## What was produced (deterministic governance record — never model output as policy)
- **`docs/evidence/R8_TOS_VERIFICATION_CLAUDE_CODE.md` (NEW)** — the durable R8 finding record for
  Claude Code, structured to Plan **§18.3's six-item checklist** (terms located; wrapped/programmatic
  CLI permissibility; per-account concurrency + rate caps; auth lifetime; findings-storage; ambiguity
  handling with `[OPERATOR]` flags). It is the build's analog of §18.3 step 5's "ACCEPTED memory
  entry" (substitution per §6: seeding a *runtime* MCP ACCEPTED entry is a live-operation action
  deferred to `.adapter`/operator run).
- **Register updates (append-only):** `DECISION_REGISTER.md` (R8-recorded row for `.r8tos`),
  `UNRESOLVED_ISSUE_REGISTER.md` (U5 dated note; U3 out-of-scope note), `HARDENING_BACKLOG.md`
  (U3/U5 row dated note pointing to the R8 record).
- **No source code changed.** In particular `node_runtime/supervisor/subscription_governor.py` is
  **untouched** — its allowance default is already `1` and R8 finds **no verified basis** to raise
  it, so raising it would violate §18.3 ("never on inference or silence"). Not changing it is the
  correct action.

## Findings (summarized — full record in R8_TOS_VERIFICATION_CLAUDE_CODE.md)
1. **Wrapped/programmatic CLI under subscription auth:** Claude Code is Anthropic's **first-party**
   agentic CLI, explicitly built for headless/non-interactive/programmatic invocation (`claude -p`,
   `--output-format json`, Claude Agent SDK) under a **Pro/Max OAuth subscription login**. Spawning
   it as a supervised subprocess is its *intended* mode — categorically unlike scraping/reverse-
   engineering a web product. **Residual flag (fail-closed):** the orchestration-**wrapper**
   interpretation is a low-confidence ToS area the Plan itself flags (§21); per §18.3(6),
   ambiguity ⇒ **stay at 1 terminal**, confirm live terms as an `[OPERATOR]` item at `.adapter`.
2. **Concurrency:** **no publicly documented per-account concurrent-session allowance** for
   subscription auth; usage is bounded by rolling usage limits, not a published concurrency count.
   ⇒ `verified_concurrency_allowance(claude_code) = 1` (fail-closed default, **not raised**). Matches
   I-X3 and OP-4/OP-5 (`terminals: 1`). R8's allowance-raise branch is **moot** for this build.
3. **Auth lifetime:** OAuth session via the CLI's own login, stored in the **host-native** store the
   CLI manages; expiry ⇒ adapter pauses **fail-closed** (Plan §18.4). The adapter never reads/stores/
   transmits the credential (§2.2).

## Self-check — exit criteria vs real output
- **R8 verification recorded BEFORE any live call** (directive §10.1 / §9-14B entry cond. 2):
  ✓ `docs/evidence/R8_TOS_VERIFICATION_CLAUDE_CODE.md` exists; **no** live call was made this
  sub-step. Verified no process spawns / network egress were introduced:
  `git status --porcelain` shows only doc/register additions (no `.py`/`.js`), and no code path
  invokes `claude`, `subprocess`, or any client here.
- **Concurrency finding recorded; allowance stays 1 unless verified** (§18.3): ✓ documented as
  `1` (unverified above 1); governor code left at default `1` (unchanged) — verified by `git diff
  --stat` touching **no** file under `node_runtime/`.
- **Follows §18.3 six-item checklist:** ✓ each of (1)–(6) has a labelled section in the R8 record.
- **No credential handling (§2.2):** ✓ the record concerns an authorization/ToS *finding*; it
  reads/stores/transmits no credential.
- **Test suites unaffected (no code change):** last recorded green totals stand — **387/387 pytest**
  (py -3.12), **131 JS** (node --test). No source touched ⇒ nothing to re-run for correctness; a
  confirmation run is noted below for hygiene.
- **Canonical set untouched:** `git status docs/canonical/` empty.

## Substitutions / deferrals (directive §6; honest record)
- **Live-terms retrieval not performed this session.** `WebFetch` (a permitted §2.7 vendor-doc read)
  was **not granted** in this non-interactive session, so **no dated verbatim quotation** of the
  current live legal text is captured. Recorded transparently in the R8 record §0; the dated
  retrieval + provider **support confirmation** are `[OPERATOR]` items and **explicit entry
  conditions of `.adapter`'s live smoke** (§18.3(6)). The conservative conclusion (**stay at 1
  terminal**; first-party CLI is its intended invocation mode) **does not depend** on the
  un-retrieved pages, so the sub-step is honest and complete without them.
- **ACCEPTED MCP memory entry deferred.** §18.3(5) targets a runtime ACCEPTED MCP entry; seeding
  live MCP memory is a live-operation action. Substituted here by the append-only evidence record;
  the MCP seed lands at `.adapter`/operator run.
- **U3 (Codex) not verified.** Only Claude Code is authorized (OP-5); Codex R8 is **out of scope**,
  stays OPEN.

## Independent gate-validator (sub-step confirmation)
**VERDICT: PASS** (isolated context; canonical §18.3 text and directive §9/§10.1 cross-checked
independently; `git status` run by the validator confirmed exactly five changed paths, all under
`docs/`; `subscription_governor.py` read directly — allowance default still `1`, unchanged; both
new docs grepped for code/exec/credential artifacts → descriptive prose only; retrieval-limitation
honesty and no-overclaim confirmed; `docs/canonical/` untouched). Non-blocking validator notes: (1)
the two-commit evidence/register commit had not yet landed when validated (expected pre-commit
state — landed by this report's commit); (2) the `[OPERATOR]` live-terms retrieval + residual
wrapped-CLI interpretation are genuine hard gates the `.adapter`/`.gate` validator MUST enforce
before the single live smoke — correctly deferred, not discharged here.
spec-auditor is **not applicable**
to `.r8tos` (no substantive new *code* — the directive scopes spec-auditor to "substantive new
code"; this unit adds documentation + register rows only). The load-bearing claims that were
independently checkable — governor untouched, no live call, no credential path, §18.3 coverage,
fail-closed 1-terminal default — are what the validator confirmed.

## Invariant touchpoints
- **Inv 1 (operator final authority; app never self-authorizes):** R8 does **not** self-grant any
  concurrency; the raise branch stays closed absent operator/verified confirmation.
- **Inv 21 / I-X3 (one frontier terminal per subscription):** upheld — allowance stays `1`.
- **Inv 30 (minimal necessary control):** no governance layer invented; governor code unchanged.
- **Prohibition §2.2 (no credential handling) / §2.4-as-amended-by-§10.1:** honored — a ToS finding,
  not a credential or a live call.

## Disposition
`phase-14b.r8tos` PASSED as a **sub-step** (not the phase gate). `gate/phase-14b` remains
**UNTAGGED** — the high-stakes phase gate awaits sub-steps `.adapter` and `.gate` (the latter
includes the subscription-governor deep re-inspection). Next: `phase-14b.adapter`.
