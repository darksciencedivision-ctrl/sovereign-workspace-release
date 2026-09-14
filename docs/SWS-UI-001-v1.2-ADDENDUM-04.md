# SWS-UI-001 v1.2 — ADDENDUM 04: CP-M1 fresh-session resume envelope

| Field | Value |
|---|---|
| Amends | `ADDENDUM-01`, `-02`, `-03`. All remain in force **as amended here**. `BUILD-DIRECTIVE-SWS-UI-001.md` v1.2 unchanged. |
| ID / version | `SWS-UI-001-ADD-04 v1.0`, 2026-08-26 |
| Purpose | Carry the CP-M1 run into a **fresh OpenCode session** with every correction issued during the first session consolidated in one place, and with three new standing evidence rules the run's failures earned. |
| Work order | `docs/OX-ALPHA-DIRECTIVE-CP-M1.md` — unchanged, goals G1–G124, gates 8a–8j then 9a–9j. **This addendum amends it; it does not replace it.** |
| Issuer | Human operator (sam). No authority until the §8 sentence is logged verbatim with UTC in `evidence/OPERATOR-INSTRUCTIONS.log`. |

---

## 1. Entry state — verified on disk at issuance

| Fact | Value |
|---|---|
| Gate ledger keys | `0,1,2,3,4,5,6,4b,4c,5b,7a,7b,8a,8b,8c` |
| Reviewer/operator-evaluated | `0-6, 4b, 4c, 5b` — **never writable by the builder** |
| Builder CANDIDATEs | `7a, 7b, 8a, 8b, 8c` |
| Oracle | 26/124 TRUE |
| First failing goal | **G3** (midnight expiry — see §4 T-4), then **G26** |
| Package A spend | TOTAL-A **371 / 1850** |
| Package B | not started; `before-b/` not captured; `linecount-b.txt` does not exist |
| Loop ledger | 35 lines, index 15 absent by accounted cause |
| Bands closed | 0, 1, 2, 3. G25 TRUE. |
| Provider spend to date | **ZERO.** Three G26 launch attempts, two delivery attempts, `delivered=False` on both. |

Gates 0–7b are byte-faithful to `evidence/cpm1/ledger-snapshot-verified.json`, enforced by `ledger_snapshot_ok()` in the oracle's per-iteration preamble.

## 2. Amendment register — everything binding, in one place

Prior addenda carry A-1…A-5. The first session added the following; **all bind and none is waivable by the builder.**

| ID | Rule |
|---|---|
| **A-6** | `G26`'s "runs on a **local** model" predicate is **unsatisfiable** and is replaced. `CONDUCTOR_MODEL_REGISTRY` holds only `openai_codex_cli/gpt-5.6-sol`, `claude_code/fable-5`, `claude_code/opus-4.8`, all `locality: frontier`. The Conductor leg runs on whichever conductor-capable model the spend authorization permits, **recorded by name and provider in the artifact**. The work order file stays unamended so this amendment remains traceable. |
| **A-7** | The fs-watch window is **per session**, with gaps recorded in a gap table. **A fresh session opens a fresh window and records the gap since the prior one closed.** |
| **A-8** | A mid-run pause uses the pause claim line, not the completion claim line. |
| **C-1** | The fs-watch driver passes **four roots explicitly**. Token Piggy Bank is excluded (its `data/**` sqlite ring makes `events: 0` unreachable); its integrity proof is the A-1 manifest comparison. |
| **C-4** | **The operator owns the fs-watch helper. The builder never starts it.** `Start-Process` with redirected handles stalled the first session twice. |
| **D-3** | The oracle enforces every gate `0–7b` **status and evidence entry** against `ledger-snapshot-verified.json`, in the **per-iteration preamble**, short-circuiting to `GUARD-FAIL — no goal evaluated`. |
| **E-1** | `ledger-snapshot-verified.json` carries a `_provenance` header separating witness-corroborated keys (`0–6, 4b, 4c, 5b`) from **self-attested** keys (`7a, 7b`), which no witness contains. |
| **E-2** | The guard compares the **full gate object**, not `status` + `evidence` alone. `evaluated_by` is inside the comparison. |
| **E-7a** | **A submitted gate's evidence artifact is frozen.** Never append to one. New material goes in a new file cited by the gate that owns it. |
| **E-7b** | A hash that moved for a legitimate reason is re-pointed with `as_of_utc` **and** `mutated_by` naming the goal that changed it. A bare hash swap is indistinguishable from corruption. |
| **E-7c** | A gate never cites a still-editable file by hash. It cites a **frozen copy** under `evidence/cpm1/<gate>/frozen/<name>`, with the live path in an un-hashed `source_path` field. |
| **E-8** | Any goal going `TRUE → FALSE` is named **with its cause, in the current report, on the same line as the count.** |
| **T-6** | **No placeholder timestamps in evidence. Ever.** A literal x is not a time. Every timestamp in an evidence artifact is a real captured value, or the line names `UNRECOVERABLE-APPROXIMATE` with its bounding events; digits are never silently invented. An UNINTERPOLATED expression (literal `.ToUniversalTime()` text) is the same defect class and is corrected to the real bounded interval or marked APPROXIMATE with its bounding events named. Earned 2026-08-26: spend-log and config-verification lines carried `03:4xZ`/`04:5xZ`/`03:0xZ`; corrected from artifact mtimes and log headers under the operator order, with provenance suffixed in place and an append-only recovery index added to `evidence/OPERATOR-INSTRUCTIONS.log` for that file's own six failed-interpolation headers. |
| **C-8** | **The builder never spawns a long-lived child with redirected stdout or stderr** — not Electron, not a driver, not a watcher, not a server, not a shell; nothing that does not exit on its own. A long-lived process is started either (a) by the operator, and the builder attaches, or (b) fully detached by the builder, its output going to a file the OS owns that the builder never holds a handle to, then polls that file. The builder may hold handles only on a process that exits by itself in seconds. Earned 2026-08-26: the G26 Electron launch reproduced the C-4 failure mode a third time (builder stalled 30+ min holding the child stdout handle; tree survived, driver healthy, zero spend). |

## 3. Withdrawn permanently

**The G26 "populate minimal boundary fields inside `launchConductorSession()`" option is withdrawn and may not be re-proposed in any form** — including as "test-only", "temporary", or "to unblock".

`voice/conductor-write.js:57` `supervisorEnforcedBoundary()` requires `schema === "voice_turn_boundary@1.0"` with `enforced_by_supervisor_process: true` and `broker_schema === "supervisor_voice_turn_authority@1.0"`. `main.js:932` sets `isClaudeHookBoundary` **only** for that schema; its branch calls `conductorVoiceAuthority.start()`. The `else` branch at `main.js:968` — which every codex flag-boundary ticket takes — **starts no supervisor and clears the pinned policy bytes.**

Populating those fields on that branch asserts a supervisor is enforcing turns when none was started. That is a **false attestation inside a security control**, and it fails silently forever after: the guard would return "enforced" for every future turn of every future session. It is fabricated availability under CP-M1 §9.

## 4. New standing rules — earned by this run's failures

### T-1 · Truncated console output is not evidence

**A value that reaches the console truncated must never be completed from context.** Re-read it from the source file, or capture it to a file and read the file.

This rule exists because the same mechanism failed twice:

- Gate 4's `BUILD-MANIFEST` hash was reconstructed from a truncated display and lost two characters — a 63-character hash in a reviewer-evaluated ledger entry.
- The G26 STOP report quoted `"…no non-executing boundary schema on the launch"`. The console had shown `"…no non-executing bou"` and the builder completed the sentence itself. The real string is `"…no non-executing boundary with supervisor-process enforcement is bound to this conductor (invariants 25/29)"`. **Those invented words produced the wrong schema, the wrong root cause, and three options scoped against a fault that did not exist.**

### T-2 · Cite only what you read, in the turn you read it

A file named as a **root cause** in a STOP report must have been **opened in that turn**, and the report must quote the deciding line with its `file:line`. The G26 STOP report named `voice/conductor-write.js` as the cause without ever opening it — the transcript contains zero occurrences of `voice_turn_boundary`, `supervisorEnforcedBoundary` or `armAuthority`.

### T-3 · No priced options for an unfinished diagnosis

If the investigation stops before the cause is established — including for turn length, which is a legitimate reason to stop — the report says **"cause not established; here is what was ruled out and what remains unread."** It does **not** publish remedies with line-count estimates. A "~10 lines" price tag is what made a false attestation look like the cheap option.

### T-4 · `G3`'s freshness window is **per session**, not per calendar day

The host-hardware capture is fresh **for the session that captured it**. It expired at UTC midnight and would expire every midnight for the rest of the package. Amend the goal note to say so and stop re-capturing.

### T-5 · `resync_8b.py` and the resync pattern are retired

That tool family corrupted gates 4 and 5. With E-7c in force nothing needs resyncing. Do not run it; do not write a replacement.

## 5. Envelope — unchanged

| Package | Areas and caps | Absolute | Used |
|---|---|---|---|
| A (bands 1–10) | `ADDENDUM-01` §3.2 as amended by A-2 | 1,850 | **371** |
| B (bands 11–20) | `ADDENDUM-02` §3.2 | 1,625 | 0 |

**The budgets never pool.** Package A measures against `evidence/cpm1/before-a/`; Package B against `evidence/cpm1/before-b/`, captured at the handoff (G64). A line Package A changed is Package B's **baseline**, not its spend.

Protected trees, install rules and network rules are unchanged. `D:\Token Piggy Bank\data\**` stays excluded from the baseline (A-1).

## 6. Spend envelope — unchanged and exact

Authorized: **`openai_codex_cli` only**, for (a) the Conductor leg of G25/G26 and (b) the API-model leg of the G58 proof chain. Nothing else. `claude_code`, `grok_build` and `google_antigravity` legs record `NOT_RUN(NO_SPEND_AUTHORIZATION)` naming the registry entries examined. `terminals_per_subscription` stays 1. No worker on a frontier provider.

Every turn appends to `evidence/cpm1/8d/spend-log.txt` **as it happens** — timestamp, provider, model, running count — never batched. The counter increments on **attempt**, not on delivery. Exceeding the envelope is `STOP SPEND_REQUIRED` with no interpretation permitted.

> **Amended 2026-08-26 (Option C decision, logged verbatim in `evidence/OPERATOR-INSTRUCTIONS.log`; record: `docs/CP-M1-G26-CONFIG-AUTHORIZATION.md` sha256 `0c7d177b224135b199879367c24465a87d1e1a9095e79c6a3b3c9d717bf90177`):** the authorized set is now **`openai_codex_cli` AND `claude_code`**, for (a) the G25/G26 Conductor leg and (b) the G58 API-model leg only; `claude_code` moves out of the `NOT_RUN` list; every other limit of this section stands unchanged. Verified on disk this session: `live_operation.json` sha256 `dcc7f449762849b1ce721a64a55e4fe04bf7b8eff1c2ba508426effc2f8d3629`, `scope.providers` `[openai_codex_cli, claude_code]`, conductor `claude_code/fable-5`.

## 7. Session handover

This is a **fresh session**. Under A-7 the operator closes the prior fs-watch window and opens a new one; the builder records the gap in the A-7 table and **starts nothing** (C-4).

The prior session's evidence under `evidence/cpm1/` is **adopted, not regenerated**. Re-hashing what is already proven costs time to learn nothing.

## 8. Issuance

No authority until the operator sends this sentence in session and the builder logs it verbatim with the UTC of receipt into `evidence/OPERATOR-INSTRUCTIONS.log` before any other mutation:

```
OPERATOR AUTHORIZATION: SWS-UI-001 ADDENDUM-04 v1.0 is issued as written; CP-M1 resumes in a fresh session under docs/OX-ALPHA-DIRECTIVE-CP-M1.md, goals G1-G124; amendments A-1 through A-8, C-1, C-4, D-3, E-1, E-2, E-7a/b/c, E-8 and standing rules T-1 through T-5 bind; the launchConductorSession boundary-population option is permanently withdrawn; the prior session's evidence is adopted; provider spend is limited to openai_codex_cli for the G25/G26 Conductor leg and the G58 API-model leg; llama.cpp is not promoted to production default.
```

Absent → STOP `PRECONDITION_UNSIGNED`.
