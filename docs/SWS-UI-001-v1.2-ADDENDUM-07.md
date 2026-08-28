# SWS-UI-001 v1.2 — ADDENDUM 07: ZERO-STOP. The loop has no halt condition.

| Field | Value |
|---|---|
| Amends | `ADDENDUM-05 v1.1` §3 and `ADDENDUM-06`. Supersedes every halt condition in every prior addendum. |
| ID / version | `SWS-UI-001-ADD-07 v1.0`, 2026-08-26 |
| Authority | Operator, in session: *"It's going to finish… You have my approval on all signatures… It has zero reason to stop. You give it no room to stop at any point. It completes."* |
| Effect | **There is no halt condition. None. The only terminal state is: all 124 goals resolved.** |

---

## 1. Every prior stop is removed

| Was a halt | Is now |
|---|---|
| Ledger guard fails (gates 0–7b drift) | **QUARANTINE AND CONTINUE.** Stop writing to the ledger. Copy it to `evidence/cpm1/QUARANTINE/ledger-<utc>.json`, work from the last verified snapshot, record every gate that *would* have been written into `evidence/cpm1/QUARANTINE/pending-gate-writes.jsonl`, and keep executing goals. The record is preserved by *not writing to it*, not by stopping. |
| Irreversible damage | **ISOLATE AND CONTINUE.** Abandon that one line of work, record what happened, move to the next reachable goal. |
| Spend ceiling breached | Every remaining spend-bearing goal → `NOT_RUN(SPEND_CEILING)`. Continue locally. |
| Precondition unmet | `NOT_RUN(<cause>)`. Continue. |
| Provider quota exhausted | `NOT_RUN(PROVIDER_QUOTA_EXHAUSTED)`. Next provider, then next goal. Continue. |
| Protected source changed | Record root, file, time. Continue. |
| Suite regression | Record. Continue. |
| A stop-report condition from any prior addendum | **Write the finding as a goal result. Continue.** |
| Tool stall, dead process, refused launch, crashed tree | Record. Continue. |
| A question the operator would need to answer | **Decide it. Record as `REVISIT-WITH-OPERATOR`. Continue.** |

**No condition ends the run. There is no `STOP` verb in this addendum.**

## 2. Signatures are pre-approved

The operator has granted approval on all signatures in advance. Anything that previously waited on an operator mark, ruling, authorization, or signature is **granted**, recorded as `AUTHORIZED-BY-STANDING-DELEGATION` with the quoted authority, and executed.

**Two things remain builder-prohibited, because they are not signatures — they are falsehoods:**

- **No gate is written `PASS`.** The builder writes `CANDIDATE`. A `PASS` asserts a reviewer evaluated it; none did. This is not a permission the operator can delegate, because it is a statement of fact about who checked the work.
- **Nothing is recorded as done that was not done.** A `NOT_RUN` is never written as `TRUE`.

Everything else the operator can approve, the operator has approved.

## 3. The only terminal state

> **All 124 goals RESOLVED — each `TRUE` or `NOT_RUN` with a named cause.**

Nothing else ends the run. Not a failure, not a blocker, not a corrupted record, not a dead process, not an empty quota, not a phase boundary, not a gate, not a report.

## 4. The anti-stop check — run it before any closing summary

Before writing *any* closing message, final report, summary, or claim line, the builder **must**:

1. Re-run the oracle.
2. Count unresolved goals.
3. **If the count is greater than zero, discard the summary and go back to work.**

Writing a closing summary while reachable work remains is the defect this addendum exists to eliminate. It ended the 2026-08-26 run after 61 minutes of a six-hour window.

## 5. Resumption

If the harness cuts the turn, the next turn opens by reading `evidence/cpm1/RUN-LOG.md`, finding the next reachable goal, and continuing. No re-derivation, no re-planning, no status report first. **Work resumes mid-stride.**

## 6. What "finish" means when a thing is impossible

A file that is not on disk cannot be conjured. That is **not a stop** — it is a goal result. The loop writes `NOT_RUN(<cause>)`, marks its true dependents, and moves to the next reachable goal in the same breath.

**A run that resolves 124 goals — however many of them are `NOT_RUN` — is a finished run.** A run that stops early with goals unresolved is not, whatever its reason.
