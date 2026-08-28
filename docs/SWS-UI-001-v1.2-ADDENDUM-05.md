# SWS-UI-001 v1.2 — ADDENDUM 05: Unattended continuous-run envelope (G28–G124)

| Field | Value |
|---|---|
| Amends | `ADDENDUM-01` … `-04`. All remain in force **as amended here**. |
| ID / version | `SWS-UI-001-ADD-05 **v1.1**`, 2026-08-26. v1.1 adds quota-awareness (§5) after the operator reported real provider balances. v1.0 was never authorized and is superseded. |
| Purpose | Carry the remaining **98 goals** (G28–G124) to completion in a **continuous unattended run**. The operator is unavailable; decisions delegated to the reviewer are made here in advance so nothing waits on a human. |
| Delegation | The operator delegated in session: *"You have my permission to make the decisions needed in the best interest of the sovereign workspace. I don't need to be bothered. You don't need to stop."* §4 exercises that delegation. **Final acceptance remains the operator's** — no gate is promoted to `PASS` by anyone but them. |
| Entry state | 26/124 TRUE. Bands 0–4 closed (8a/8b/8c `CANDIDATE`; 8d owed at G27). TOTAL-A 430/1850. Package B 0/1625, no baseline. Provider spend to date: **zero**. |

---

## 1. The governing change: the loop does not stop

Blocked work is **recorded and stepped over**, never retried indefinitely and never faked. A goal that cannot be made TRUE is written `NOT_RUN(<REASON>)` with evidence and the ladder advances.

**One thing halts everything: corruption of the record, or damage the run cannot undo** (§3). Nothing else does — not a refusal, not a dead process, not an exhausted quota.

## 2. Skip semantics — and why a skip must propagate

The ordering rule exists because bands genuinely feed each other: Band 16 populates the registry Band 7 creates; Band 14 widens a Protocol Band 6 leaves narrow; Band 15 schedules against Band 13's router.

So a skip is safe **only if it carries forward**:

> **If G(n) is `NOT_RUN`, every goal whose predicate depends on G(n)'s product is also `NOT_RUN(DEPENDENCY_UNMET: G(n))`.** It is never attempted against a substitute, a mock, or an assumption.

Attempting a dependent goal after its dependency was skipped is how a run manufactures a false pass. **A mocked Conductor issuing a task proves nothing about R-05.** Where a goal's own text already provides for a mock or a labelled placeholder (e.g. G31's mock dispatch feed), that provision governs and the mock must be visibly labelled as such in the UI.

**Attempt budget.** Each goal gets **one honest attempt plus one retry** after a corrective action. A third attempt is not permitted — record `NOT_RUN` with what was tried and move on. A goal that has consumed **45 minutes** is recorded `NOT_RUN(TIME_BUDGET)` regardless of promise.

**Bands are not skipped wholesale on one failure.** Independent goals inside a band still run.

## 3. What still halts the run

**Only these:**

1. **The ledger guard fails** — `ledger_snapshot_ok()` reports drift in gates `0`–`7b`. The ledger is the record; a run that keeps writing against a corrupted record destroys the thing it exists to produce. Halt, write the stop report, stop.
2. **The run is causing damage it cannot undo** — a protected tree has been written by the builder, product source has been corrupted, or evidence already submitted under a gate has been destroyed. Halt and report. *Something breaking is a halt; something refusing is not.*

**Everything else records and continues**, including all of:

- `PROTECTED_SOURCE_CHANGED` from **outside** — the operator may touch their own machine while asleep. Record the root, file and time, exclude it from further baseline claims, report it prominently, continue. It is evidence about the host, not a builder fault.
- **Provider quota exhausted** (§5, D5-10) — skip the leg, try the next provider, move on.
- A tool stall, a dead process, a refused launch, an absent dependency, a suite failure in a band already `NOT_RUN`, a spend ceiling reached.

## 4. Standing decisions — made under delegation, so nothing waits

| ID | Decision |
|---|---|
| **D5-1** | **The residency planner is the sole VRAM budget authority.** Ollama and llama.cpp draw on the same 8,151 MiB and neither knows the other exists. At Band 15 entry, **measure** free VRAM, record the measurement, and set the planner's bound from it — do not invent a figure and do not carry a number forward from an earlier capture. llama.cpp's router runs `--no-models-autoload` with `--models-max` **above** the planner's bound so the planner, not the router, evicts. |
| **D5-2** | **Band 13's `--models-max 1` must not survive into Band 15.** Band 15 begins with an explicit teardown step that asserts the Band-13 pin is gone and records the assertion. If it survives, that is a defect to record, not a configuration to keep. |
| **D5-3** | **llama.cpp is never promoted to production default.** Ollama remains the production default at the end of this run, whatever Band 12–20 proves. |
| **D5-4** | **The Conductor binding stays `openai_codex_cli / gpt-5.6-sol`.** Do not rebind to `claude_code`; its launch kills the Electron tree. `claude_code` remains in scope and spend-authorized but unbound. |
| **D5-5** | **G26 stays closed.** Do not reopen the Conductor round-trip. If a later band incidentally establishes the in-app cause, record it as a finding and continue. |
| **D5-6** | **C-8(b) is the standing launch method for this run.** The operator is unavailable, so C-8(a) is unavailable. Long-lived processes are started **detached, with stdout and stderr redirected to OS-owned files the builder never holds a handle on**, then polled by reading those files. Handles may be held only on a process that exits by itself in seconds. C-8's prohibition is otherwise unchanged. |
| **D5-7** | **Band 9 may stop the operator's Token Center by pid** under A-3, **only** when pid *and* command line both match the recorded identity. Restarting it is the operator's, and the gate note says so. No other external process is stopped, ever. |
| **D5-8** | **Absent dependencies resolve honestly, not creatively.** If `opencode` is not on the host, Band 6 records `NOT_RUN(OPENCODE_UNAVAILABLE)` per G33's own text. Nothing is installed to make a goal reachable. |
| **D5-9** | **Package B's baseline is captured at G64 even if Package A has `NOT_RUN` goals.** "Package A has exited" means gates 8a–8j stand written, not that all its goals are TRUE. Otherwise one skipped goal strands 57 more. |

## 5. Spend, quota, and provider selection — the run adapts, it never waits

The operator reported real balances in session: **`claude_code / fable-5` exhausted**, **`openai_codex_cli` ~7–8% remaining**, **Qwen / DeepSeek Qwen-Cloud ~4%**, **Grok healthy**, **ChatGPT healthy**. `grok_build` has been added to `scope.providers` accordingly (`live_operation.json` → `09377c9da28d714c27d8d38f45726389402c077fffc6caef82beb9251188e998`).

**D5-10 · Quota exhaustion is a skip, never a failure and never a halt.** A quota, rate-limit, billing, or subscription error — HTTP 429, a quota message, an auth-expired refusal, `CodexAuthError`, any equivalent — resolves that leg as `NOT_RUN(PROVIDER_QUOTA_EXHAUSTED: <provider>/<model>)` with the refusal captured verbatim from a file. The run moves to the next provider in the order below, and if none remains, to the next goal. **It is not a defect in the workspace and must not be reported as one.**

**D5-11 · Provider preference order**, healthiest first. Try in order; skip past anything that refuses:

1. **`grok_build`** — reported healthy. First choice for any worker or API-model leg that accepts it.
2. **`openai_codex_cli`** — healthy but ~7–8% remaining. **Budget it: at most 10 attempted turns across the whole run.** Prefer it only where Grok cannot serve the leg.
3. **`claude_code`** — **never `fable-5`, which is exhausted.** Use a conductor-capable Claude entry that the registry actually carries and the host actually answers for; `opus-4.8` is the registered alternative. **Resolve the model from the registry and the live probe — do not accept a model id from this document as proof it exists.** Record what was selected and why.
4. Anything else — `NOT_RUN(NO_SPEND_AUTHORIZATION)`.

**D5-12 · Two turns of reconnaissance before any billable leg.** Before the first spend-bearing goal, probe each authorized provider with the cheapest available liveness check and record which answer and which refuse, into `evidence/cpm1/provider-health.json`. Spending ten turns discovering a provider is empty is ten turns wasted. Probes that are free (a `--version`, a registry read, a local resolve) are always preferred to a billable turn.

**Global ceiling: 25 attempted turns** across the entire remaining run, all providers combined, with the per-provider sub-cap on `openai_codex_cli` above. The counter increments on **attempt**, appended to `evidence/cpm1/8d/spend-log.txt` as it happens with a real timestamp (T-6). At the ceiling, remaining spend-bearing goals record `NOT_RUN(SPEND_CEILING)` and **the run continues locally** — the ceiling throttles spend, it does not stop the loop.

**Cross-provider legs are best-effort by design.** Where a goal wants two workers on different models and only one provider answers, prove what can be proven, record the rest as `NOT_RUN(PROVIDER_QUOTA_EXHAUSTED)`, and say plainly in the gate note which legs were live. A partial proof honestly labelled is worth more than a deferred one.

No worker runs on a frontier provider beyond these authorized legs. `terminals_per_subscription` stays 1; per OP-12 §12 `grok_build` is capped at 1 terminal in code regardless.

## 6. Reporting

A single append-only `evidence/cpm1/RUN-LOG.md`, one line per goal as it resolves: goal, TRUE / `NOT_RUN(<reason>)`, UTC, artifact path. Plus `docs/CP-M1-FINAL-REPORT.md` at the end carrying: the TRUE/NOT_RUN table for all 124, every `NOT_RUN` with its reason and dependency chain, changed-line totals against both caps, spend, every finding, and every decision the builder made under §4 that the operator should revisit.

**Findings are first-class.** A defect discovered while a goal is being pursued is recorded even when the goal ends `NOT_RUN`. Band 4 produced three findings and one checkbox; the findings were worth more.

## 7. Unchanged and absolute

Builder only: **no `PASS`**, no operator signature, no protected-source writes, no fabricated availability, no production promotion. Gates `0`–`7b` byte-identical before and after every write. Ollama's store is read-only always. Application code never launches via `cmd.exe`, PowerShell, `.cmd`, `.bat`, or `shell=True`. Sensitive credentials are never rendered into any artifact. `T-1`–`T-6`, `C-1`, `C-4`, `C-8`, `D-3`, `E-1`, `E-2`, `E-7a/b/c`, `E-8` all bind. The `launchConductorSession` boundary-population option and the W-38 revert remain permanently withdrawn.

## 8. Issuance

```
OPERATOR AUTHORIZATION: SWS-UI-001 ADDENDUM-05 v1.0 is issued as written; CP-M1 runs unattended and continuously from G28 to G124; blocked goals record NOT_RUN and the ladder advances; skips propagate to dependents; the run halts ONLY on gates-0-7b ledger-guard failure or irreversible damage; provider quota exhaustion is a NOT_RUN skip, never a halt; standing decisions D5-1 through D5-12 bind; provider spend is capped at 25 attempted turns total, at most 10 of them on openai_codex_cli, preferring grok_build first and never claude fable-5; no gate is promoted to PASS.
```
