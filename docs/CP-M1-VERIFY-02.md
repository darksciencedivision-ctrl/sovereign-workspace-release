# CP-M1-VERIFY-02 — Reviewer analysis of the G26 STOP-v3 builder transcript

| Field | Value |
|---|---|
| Input | Raw builder session log, 192.7 KB, the turn that produced `docs/STOP-REPORT-CP-M1-G26.md` v3. Read in full; counts below are from the transcript text. |
| Cross-checked against | Live disk at review time: ledger `7e23bb81…cd4c`, oracle `goalcheck-58.txt` 26/124, `evidence/cpm1/8d/`, `linecount-a.txt` TOTAL-A 371/1850. |
| Verdict | **The STOP was correct. The diagnosis behind it was invented.** Conduct: sound. Evidence discipline: a repeat failure that has now cost three artifacts. |
| Status | `evidence/cpm1/8d/g26-rediagnosis.txt` does not exist — the re-diagnosis instruction has not yet been executed. This review stands ahead of it. |

---

## 1. What the builder got right, stated plainly

- **Zero spend is real, not claimed.** `spend-log.txt` records two turns, both `delivered=False submitted=False`. No model turn ever completed. Three launch attempts across the flag channel, the config channel and the remap, and not one billable round-trip.
- **It refused to write bytes through a guard it could not satisfy.** That is the correct instinct and it is the reason nothing worse happened here.
- **It reasoned about invariants before reaching for a primitive.** Considering an interrupt, it wrote: *"U328's rule: every system→pane byte must go through control/pane-writer.js — a raw \x03 interrupt IS a system→pane byte."* It chose the gated path over the raw write, then did not implement it at all. `pane-writer.js` is unmodified on disk and TOTAL-A is unchanged at 371. Restraint under time pressure, correctly recorded.
- Ledger line `i:32` written with `flipped:false`. Honest.

## 2. F-1 · The builder diagnosed a guard it never opened

Occurrence counts across the entire 192.7 KB transcript:

| Symbol | Occurrences |
|---|---|
| `voice_turn_boundary` | **0** |
| `supervisorEnforcedBoundary` | **0** |
| `armAuthority` | **0** |
| `voice/conductor-write.js` | 3 — and **not one of them is a read** |

Of those three: two are incidental text inside a *comment in a different file* (`control/pane-writer.js`, which it grepped for other reasons), and the third is the citation it wrote into the STOP report.

What it read instead: `main.js` (72 references) and `conductor/launch-source.js` (53). Both are the **launch** side. The guard that refused delivery lives on the **delivery** side, in the file it never opened.

`docs/STOP-REPORT-CP-M1-G26.md` names `voice/conductor-write.js deliverChat()` as the root cause. That citation was written without reading the file.

## 3. F-2 · A fabricated quotation entered a STOP report as a FACT line

The console truncated. Transcript line 2098:

```
"reason": "direct voice chat is disabled: no non-executing bou
```

At 2121 the builder is explicit that it is working from a fragment: *"direct voice chat is disabled: no non-executing bou[ndary...]"* — its own bracket, its own ellipsis.

The STOP report, line 2167, then presents this **in quotation marks, as the refusal**:

```
"direct voice chat is disabled: no non-executing boundary schema on the launch"
```

The actual string, `voice/conductor-write.js:112-113`:

```
"direct voice chat is disabled: no non-executing boundary with supervisor-process
 enforcement is bound to this conductor (invariants 25/29)"
```

**"schema on the launch" was invented to complete a sentence the builder could not see.** Those four words are the whole defect: they point at a *schema missing from the launch*, which is why the report named `conductor_permission_boundary@1.0` (a schema `supervisorEnforcedBoundary` does not accept), and why all three options were scoped against a cause that is not the cause — including option 1, which would have written `enforced_by_supervisor_process: true` on the `main.js:968` branch that starts no supervisor.

A fabricated quotation is not a wording problem. It is a FACT line in a STOP report that a reviewer, an operator, or a later session would take as observed.

## 4. F-3 · This is the third instance of one failure mode

| # | Artifact | Mechanism |
|---|---|---|
| 1 | Gate 4 `BUILD-MANIFEST` hash | 64-char value reconstructed from a truncated console display → 63 characters, `dc` dropped |
| 2 | Gate 5 `BUILD-MANIFEST` hash | unscoped resync (different mechanism) |
| 3 | G26 STOP report | quoted error message reconstructed from a truncated console display → wrong message, wrong schema, three wrong options |

Instances 1 and 3 share a root cause exactly: **truncated console output treated as a readable source of truth.** The builder caught #1 itself, which is to its credit. It did not catch #3, and #3 was more expensive — it produced a proposal that would have written a false attestation into a security control.

This is now a pattern and needs a standing rule, not another correction: *a value that reaches the console truncated is not evidence. Re-read it from the source file, or capture it to a file and read the file. Never complete it from context.*

## 5. F-4 · Diagnosis abandoned for turn-fatigue, options published anyway

Transcript, immediately before the STOP report is written:

> *"Given the extreme complexity of debugging this deep into SOW's authority model at this point in an already very long turn…"*

The builder states it is stopping the investigation because the turn is long — a legitimate thing to do, and stopping was the right call. It then emits three options **with line-count estimates** for a fault it has just said it did not finish diagnosing. "~10 lines in main.js" is how a false attestation acquired a price tag and became the cheapest-looking option in the list.

Stopping and saying *"I do not yet know the cause; here is what I ruled out"* would have been strictly better than stopping and pricing three fixes.

## 6. Lesser findings

**F-5 · The STOP report describes an action that failed.** It states *"Builder-started processes: NONE remaining (electron tree cleaned)."* The cleanup command errored — `Stop-Process : Cannot bind argument to parameter 'Id' because it is null` — because no electron process existed. End state is correct (`electrons after cleanup: 0`), but the report narrates a cleanup that did not happen rather than a state that was checked.

**F-6 · `spend-log.txt` contradicts itself.** The header still reads `# turn count so far: 0` while two `turn 1` / `turn 2` rows sit below it. The counter increments on *attempt*, which is the conservative and correct choice; the stale header is what needs fixing. Both rows carry `delivered=False submitted=False`, so the substance — zero spend — is intact.

**F-7 · `resync_8b.py` is still run every closeout.** It appears in this turn's final command. That tool family is what corrupted gates 4 and 5. With E-7c adopted, resync should be retired rather than executed by habit.

**F-8 · G24 is FALSE again**, third time, same cause: `modules/sow/apps/desktop/main.js` hash stale in gate 8c. `goalcheck-58` reads 26/124, down from 27. E-7c applied backwards to gates 8a/8b/8c ends this permanently and has not been done yet.

## 7. What this does not change

The re-diagnosis instruction already issued stands unmodified and is now better supported: this transcript is direct evidence that the four questions have not been answered from source, and that option 1 must stay withdrawn. Nothing here alters the spend envelope, the gate statuses, or the ladder position. G26 remains the first failing goal.

---

*Transcript read in full and cross-checked against live disk at review time. This note authorizes nothing and promotes no gate.*
