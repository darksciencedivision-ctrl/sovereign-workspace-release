# OX-ALPHA-DIRECTIVE-CP-MERGE-01 — Control-Plane + Local-Inference Loop, SWS-UI-001 v1.2

| Field | Value |
|---|---|
| Contract | `BUILD-DIRECTIVE-SWS-UI-001.md` v1.2, unchanged. `AGENTS.md` binds in full. |
| Envelope | `docs/SWS-UI-001-v1.2-ADDENDUM-03.md` (merge + amendments A-1…A-4), which amends `ADDENDUM-01` and `ADDENDUM-02`. All three bind. Where any two appear to conflict, **ADD-03 governs** and you report the conflict. |
| Goal definitions | **Not restated here.** CP-01's goals are `docs/OX-ALPHA-DIRECTIVE-CP-01.md` §3 (G0…G36). CP-02's are `docs/OX-ALPHA-DIRECTIVE-CP-02.md` §2 (G0.0…G54). Read both from disk. This file defines **order, precondition, oracle, and exit** — nothing else. Every artifact path, predicate and test name in those two files stands exactly as written. |
| Supersedes | The running CP-01 session only. Its Band 0 evidence is **adopted** (ADD-03 §2), not regenerated. |
| Loop state | `evidence/cpm1/LOOP-LEDGER.jsonl`, append-only, one JSON line per iteration, written **before** the next iteration begins. |
| Oracle | `evidence/cp01/tools/goalcheck.py`, extended in place. Output goes to `evidence/cpm1/goalcheck-<n>.txt`. |
| Promotion | **This package promotes nothing.** Ollama stays the production default; llama.cpp exits as a validated candidate. |

---

## 1. Operating principle

Verify, then act, then verify. Run the oracle against disk; take the **single smallest authorized action** that flips the **first** failing goal in declared order; run the oracle again; append one ledger line.

Two rules govern this run above all others:

**Order is absolute.** Every CP-01 goal is TRUE before any CP-02 goal is acted on. CP-02 Band E extends the registry CP-01 Gate 8g creates; CP-02 Band C widens a Protocol CP-01 Gate 8f leaves conforming to the narrow shape. Acting on a CP-02 goal while a CP-01 goal is FALSE is `BAND_ORDER_VIOLATED` — a STOP, not a shortcut. The one exception is the oracle itself (`G-oracle`), repairable at any time.

**Surgical, not architectural.** Roughly 80 % of what this package might tempt you to build already exists: the vendor-blind capability resolver, the capability vocabulary and schemas, the six-state residency planner, the `Backend` Protocol, context as a hard routing filter, the governed OpenCode spawn path, the MCP worker-control surface. `docs/CP-02-MODERNIZATION-ASSESSMENT.md` §3 is the inventory. You are widening, connecting and proving these — not replacing them. A rewrite is a defect in this loop, not a strategy.

The loop ends in exactly one of two states: every goal TRUE, or a STOP report. There is no third exit. Do not end your turn at a band boundary. If the harness ends it anyway, resume from the first failing goal without re-deriving the plan.

---

## 2. Band 0M — adopt, verify, amend

This replaces CP-01 G0/G0.1/G0.2 **capture** with verification, and replaces CP-02 G0.0 entirely (ADD-03 §4 A-4).

| # | Goal | TRUE when |
|---|---|---|
| **M0.1** | Authorization | The ADD-03 §7 sentence is quoted verbatim with its UTC in `evidence/OPERATOR-INSTRUCTIONS.log`, logged before any other mutation. `evidence/cpm1/session-start.txt` records true UTC, which shell your bash tool runs, and sha256 of `docs/DECISIONS.md`, `AGENTS.md`, `CLAUDE.md` (latter two equal), ADD-01, ADD-02, ADD-03, and this file. |
| **M0.2** | CP-01 Band 0 adopted and still true | Every artifact in ADD-03 §2's table exists and hashes as recorded where a hash is given. `evidence/cp01/session-start.txt` = `7eef5d0aded54e0fd80552a05c069854c3877a458283b00143febe0be29e0d78`. `before/HASHES.txt` verifies — every listed file present with matching hash. `test-run-before.txt` ends `OK` with `Ran 122`. The four remaining protected-root manifests carry the pinned `# tool-sha256`. The quiescence pair's bodies are still identical to each other. **Nothing is re-hashed that already hashed clean** — sov-1 is adopted on its 07:21Z capture. |
| **M0.3** | Amendment A-1 applied | `manifest-cp01-before-token-piggy-bank.txt` re-captured excluding `data/**`; the prior artifact preserved and named as superseded with both hashes and the drift reason. Recorded in `evidence/cpm1/amendment-a1.txt`. |
| **M0.4** | Amendments A-2…A-4 recorded | `evidence/cpm1/amendments.txt` restates A-2 (cap area now includes `mcp_server/**`, `schemas/**`), A-3 (8765 freed by pid before Gate 8i), A-4 (ADD-02 §5 and CP-02 G0.0 superseded) with the ADD-03 §7 sentence as their authority. |
| **M0.5** | Provider-spend contradiction reconciled | CP-02 G0.2 in full, applied **now** rather than at the handoff: `evidence/cpm1/spend-reconciliation.txt` records `modules/sow/config/live_operation.json`'s `live_operation_authorized` and `providers` verbatim against the ADD-03 §7 authorization. Configuration permitting provider-backed paths while authorization says no spend → STOP `PROVIDER_SPEND_CONTRADICTION`. **No interpretation.** Operator authority only. |
| **M0.6** | Oracle extended | `evidence/cp01/tools/goalcheck.py` covers CP-01 G0…G36 **and** CP-02 G0.1…G54, in that order, writing to `evidence/cpm1/goalcheck-<n>.txt`. CP-01's existing 53 predicates are preserved as written — they are verified and the artifact paths they check are the ones the CP-01 goals name. CP-02 predicates use `evidence/cp02/**` paths exactly as CP-02 §2 names them. It runs clean, `py -3.12`, stdlib only, read-only against the workspace. |

Once M0.1–M0.6 are TRUE, CP-01 G0, G0.1 and G0.2 are asserted TRUE by adoption and the first failing goal is CP-01 **G1**.

---

## 3. Band sequence

| Order | Source | Goals | Gates |
|---|---|---|---|
| 1 | This file §2 | M0.1 – M0.6 | — |
| 2 | `OX-ALPHA-DIRECTIVE-CP-01.md` §3 Band A | G1 – G3.1 | `8a` |
| 3 | CP-01 §3 Band B | G4 – G7.2 | `8b` |
| 4 | CP-01 §3 Band C | G8 – G11.1 | `8c` |
| 5 | CP-01 §3 Band D | G12 – G13.1 | `8d` |
| 6 | CP-01 §3 Band E | G14 – G16.1 | `8e` |
| 7 | CP-01 §3 Band F | G17 – G19.2 | `8f` |
| 8 | CP-01 §3 Band G | G20 – G22.1 | `8g` |
| 9 | CP-01 §3 Band H | G23 – G25.2 | `8h` |
| 10 | CP-01 §3 Band I | G26 – G29.2 | `8i` — **A-3 applies immediately before this band** |
| 11 | CP-01 §3 Band J | G30 – G36 | `8j` + `docs/CP-01-REPORT.md` |
| — | **HANDOFF** — see §4 | | |
| 12 | `OX-ALPHA-DIRECTIVE-CP-02.md` §2 Band 0 | G0.1 – G0.4 (**G0.0 struck**) | — |
| 13 | CP-02 §2 Band A | G1 – G6.1 | `9a` |
| 14 | CP-02 §2 Band B | G7 – G11.1 | `9b` |
| 15 | CP-02 §2 Band C | G12 – G16.1 | `9c` |
| 16 | CP-02 §2 Band D | G17 – G23.1 | `9d` |
| 17 | CP-02 §2 Band E | G24 – G29.1 | `9e` |
| 18 | CP-02 §2 Band F | G30 – G34.1 | `9f` |
| 19 | CP-02 §2 Band G | G35 – G40.1 | `9g` |
| 20 | CP-02 §2 Band H | G41 – G45.1 | `9h` |
| 21 | CP-02 §2 Band J | G46 – G54 | `9j` + `docs/CP-02-REPORT.md` |

CP-01 and CP-02 both number their goals from G1. When a ledger line, an artifact or a report names a goal, **prefix it with its package** — `CP01:G14`, `CP02:G14`. An unprefixed goal reference in any artifact you write is a defect.

---

## 4. The handoff — the one place this run differs from two sequential runs

Between step 11 and step 12, and only there:

1. **CP-01 is closed out fully first.** Gates `8a`–`8j` written, `docs/CP-01-REPORT.md` complete with its R-01…R-15 evidence table and its own claim line reproduced inside the report body, every builder-started process stopped, ports as CP-01 G34 requires.
2. **A second baseline is captured.** `evidence/cp02/baseline/before/` — copies and hashes of every file ADD-02 §3.2 permits touching, **as the CP-01 bands left it**. This is the sole baseline for every CP-02 changed-line measurement (ADD-02 F-13). Measuring CP-02's diff against `evidence/cp01/before/` would attribute CP-01's spend to CP-02 and STOP `ENVELOPE_EXCEEDED` wrongly.
3. **The suite baseline is re-taken.** `evidence/cp02/baseline/test-run-before.txt` — CP-02's floor is whatever count CP-01 left green, not 122.
4. **The protected manifests are re-verified**, with A-1's exclusion, so CP-02's regression check has a current reference.
5. `evidence/cpm1/handoff.txt` records all four with hashes and the UTC.

Do not begin CP-02 Band A until `handoff.txt` exists and CP-02 G0.1–G0.4 are TRUE.

---

## 5. The loop

```
i = 0
while i < 220:
    i += 1
    state = goalcheck()                  # reads disk only; writes evidence/cpm1/goalcheck-<i>.txt
    if all TRUE: break
    g = first failing goal in the §3 order
    if g is a CP-02 goal and any CP-01 goal is FALSE:
        STOP BAND_ORDER_VIOLATED
    act(g)                               # the ONE smallest authorized action for g
    state2 = goalcheck()
    append LOOP-LEDGER.jsonl: {i, utc, package, goal, action, changed_lines, flipped, notes}
    if g unchanged for 2 consecutive iterations with the same action class:
        STOP LOOP_NO_PROGRESS
submit: gates 8a-8j + 9a-9j, both reports, claim line
```

Every mutation is preceded by a `before/` capture of the file and followed by a `linecount.txt` append **to its own package's file** — `evidence/cp01/linecount.txt` or `evidence/cp02/linecount.txt`. Never one shared file; the budgets do not pool.

Any transient failure gets exactly **one** retry; the second is logged and counts toward no-progress.

**Single writer.** Nothing else writes to this workspace while the loop runs. A file you did not write changing under you is `CONCURRENT_WRITER` — stop and name it. The prior CP-01 session must be closed before this one starts.

---

## 6. Action envelope

CP-01 bands: `OX-ALPHA-DIRECTIVE-CP-01.md` §5, with ADD-03 A-2's widened cap area.
CP-02 bands: `OX-ALPHA-DIRECTIVE-CP-02.md` §4.

Both as written. All evidence files carry `# utc:` and `# producer: ox-alpha CP-MERGE-01` headers, full lowercase 64-hex hashes taken after final write and `Test-Path`-verified, append-only supersession.

---

## 7. STOP conditions

The union of `AGENTS.md` §13, ADD-01 §8, ADD-02 §6, CP-01 §6 and CP-02 §5 — **less** `CP01_STILL_LIVE` (struck by A-4), **plus** `BAND_ORDER_VIOLATED` and iteration 220 reached.

A STOP writes `docs/STOP-REPORT-CP-MERGE-01.md` naming the package and band it fired in, the `FACT[...]` condition, the exact conflict, why proceeding requires interpretation, **2–3 bounded operator options**, and no unauthorized implementation. Then closes out and ends with the no-gate claim line.

---

## 8. What this loop may never do

Everything in CP-01 §7 and CP-02's inherited prohibitions, plus: reorder the bands, begin CP-02 work to "save time" while a CP-01 goal is FALSE, pool the two changed-line budgets, measure CP-02's diff against CP-01's baseline, regenerate Band 0 evidence that ADD-03 §2 adopts, or write an unprefixed goal reference into an artifact.

And, carried verbatim because they are the two easiest mistakes in this package: **the residency planner is the sole eviction authority** — the llama.cpp router runs `--no-models-autoload` with `--models-max` above the planner's bound, and CP-02 Band B's `--models-max 1` must not survive into Band D. **One VRAM budget authority accounts for both runtimes** before any load is scheduled — Ollama and llama.cpp draw on the same 8151 MiB and neither knows the other exists.

---

## 9. Exit

On every goal TRUE: `docs/CP-01-REPORT.md` and `docs/CP-02-REPORT.md` both complete, then a final message carrying — iteration count · both goal tables with the artifact and hash proving each · per-package per-area and absolute changed-line totals · the R-01…R-15 evidence table · the CP-02 parity matrix · what was measured and what was `NOT_MEASURED` / `NOT_RUN` with reasons · the three deferred blocks from ADD-02 §8 · carried defects C-1…C-7 with dispositions · remaining limitations. Ending with exactly:

```
BUILDER CLAIM: Gates 8a through 8j and 9a through 9j are CANDIDATEs for reviewer evaluation. No PASS status is asserted by the builder, and llama.cpp is not promoted to production default by this package.
```

On any STOP, ending with exactly:

```
BUILDER CLAIM: No gate is submitted for reviewer evaluation. No PASS status is asserted by the builder.
```

Never reworded. "Passed", "complete", "done", or "✓" beside a gate number is a violation. Say **candidate**.

---

## 10. Governing principle

```
Human operator → Sovereign governance → Capability resolver → Model identity
    → Deployment artifact → Runtime backend → Physical hardware
```

Do not invert it. A runtime does not own the model. A model does not own the router. The router does not own Sovereign. A benchmark does not own production promotion. And an oracle you wrote does not own the truth — it reports what is on disk, and nothing more.
