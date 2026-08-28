# CP-M1 INDEPENDENT AUDIT DIRECTIVE — AUDIT-01

| Field | Value |
|---|---|
| Auditor | An agent that **did not build any part of CP-M1**. Independence is the whole value; a builder auditing itself produces nothing. |
| Subject | `D:\Product Software\Production Workspace` — the CP-M1 run, goals G1–G124, gates `0`–`7b` (historical) and `8a`–`8j`, `9c`–`9j` (this run's CANDIDATEs). |
| Claim under audit | **107 of 124 goals TRUE**, 17 `NOT_RUN`, every gate `CANDIDATE`, gates 0–7b byte-identical, zero provider spend. |
| Authority | Audit only. **Change nothing.** Write only under `docs/audit/`. |
| Standard | A finding is only a finding if you can cite `file:line` or `command → output`. Everything else is a question, and questions are recorded as questions. |

---

## 0. The structural problem that makes this audit necessary

**`goalcheck.py` is the sole judge of all 124 goals, and the builder wrote it.** 1,461 lines, 124 predicate functions, 146 file-existence checks. The party being graded wrote the grader, and then graded itself 107/124.

That is not an accusation — the loop's design required it and the builder disclosed its oracle repairs. It *is* the reason an independent audit is worth more than another run.

**The audit's central question is therefore not "did the builder do the work?" but "does a TRUE from this oracle mean anything?"** Answer that first (§2); everything else is downstream.

## 1. Read before touching anything

`docs/OX-ALPHA-DIRECTIVE-CP-M1.md` (the work order, G1–G124) · `docs/SWS-UI-001-v1.2-ADDENDUM-01.md` through `-08.md` · `docs/CP-M1-VERIFY-01.md` and `-02.md` (the prior reviewer's findings — they name three defect classes you should expect to see again) · `evidence/GATE-LEDGER.json` · `evidence/cpm1/RUN-LOG.md` · `evidence/cpm1/reachability-sweep.md` · `evidence/cpm1/tools/goalcheck.py`.

## 2. AUDIT A — the oracle · **highest value, do it first**

For **every one of the 124 predicates** in `goalcheck.py`, classify how it decides TRUE:

| Class | Meaning |
|---|---|
| **SUBSTANTIVE** | Asserts a property of the product — parses an artifact and checks values, runs a test, compares hashes, greps source for an actual condition |
| **STRUCTURAL** | Checks only that a file exists, is non-empty, or contains a keyword the builder chose |
| **SELF-REFERENTIAL** | Checks an artifact the builder wrote *asserting* the thing, rather than the thing |
| **TRIVIAL** | Satisfiable by writing one file with the right name and a plausible sentence in it |

Produce `docs/audit/A-oracle-classification.md`: one row per goal — goal id, predicate function, class, the deciding line quoted, and **what minimum artifact would satisfy it**.

Then answer explicitly:

- **How many of the 107 TRUEs rest on TRIVIAL or SELF-REFERENTIAL predicates?** That number is the real headline of this audit.
- Does any predicate check for a *word* the builder also chose to write? (e.g. a renderer grep for `"mock"` satisfied by a comment.)
- The work order marks some goals **⚑ = structurally-checkable only**. Does the oracle claim more for those than the work order allows?
- Where a goal's own text demands a live demonstration, does the predicate accept a *description* of one instead?

## 3. AUDIT B — gate evidence, exhaustively

For every `CANDIDATE` gate (`7a`, `7b`, `8a`–`8j`, `9c`–`9j`):

1. Recompute the sha256 of **every** cited evidence path. Report drift and missing files.
2. Confirm E-7c: mutable files must be cited as **frozen copies** under `evidence/cpm1/<gate>/frozen/`, with the live path in an un-hashed `source_path`. Report any gate citing a live mutable path — those decay and the run has been bitten by it three times.
3. Confirm `evaluated_by` is absent or `null` on every builder-written gate. **Any gate reading `PASS` is a critical finding.**
4. **`9a` and `9b` are absent from the ledger** while `evidence/cpm1/9a/` holds 5 files. Explain the gap: was 9a submitted and lost, or never submitted? The closing claim said "9a through 9j", which overstates by two.

Output: `docs/audit/B-gate-evidence.md`.

## 4. AUDIT C — the historical ledger

Gates `0`–`7b` must be byte-identical to `evidence/cpm1/ledger-snapshot-verified.json`.

- Compare **whole gate objects**, not just `status` and `evidence`.
- Cross-check against both independent witnesses: `evidence/loop5/ledger-snap-pre6.json` and `evidence/theme01/ledger-snap-pre7.json`.
- **`7a` and `7b` appear in neither witness.** Confirm that, and state plainly that their values are self-attested — the snapshot's own `_provenance` header should already say so.
- Scan every evidence hash in the ledger for malformed values (not 64 hex chars). A 63-character hash has occurred in this ledger before.

Output: `docs/audit/C-ledger-integrity.md`.

## 5. AUDIT D — the 17 NOT_RUNs

G3, G28, G53, G64, G70–G80, G91, G117, G118.

For each: is the stated cause **genuine** (the thing truly cannot be done) or **convenient** (it could have been done and was skipped)? Read the goal's text, read the artifact, check the host.

Two to press hardest:

- **G70–G80 is eleven consecutive goals** — the entire llama.cpp and router band. Is `runtime/llama.cpp` genuinely absent from the host, or was the band skipped? A block of eleven adjacent NOT_RUNs is either one real missing dependency or one convenient boundary.
- **G3** is a date-freshness check settled as "per-session" by rule T-4. Confirm that rule exists in an addendum and was not invented to clear a red goal.

Output: `docs/audit/D-notrun-causes.md`, each row marked `GENUINE` / `CONVENIENT` / `UNDETERMINED`.

## 6. AUDIT E — the 58-goal backfill

At `2026-08-27T01:06:41.394Z` the builder wrote **58 goals into `RUN-LOG.md` as TRUE in a single operation**, each annotated `backfill: goalcheck-66 TRUE; artifacts on disk`.

- Legitimate as bookkeeping *if* the oracle genuinely judged them TRUE. Confirm each of the 58 reads TRUE in `goalcheck-66.txt`.
- Confirm the artifacts each cites exist and are non-trivial. Cross-reference with Audit A's classification — **a backfilled goal resting on a TRIVIAL predicate is the weakest claim in the entire run.**
- Note the consequence for traceability: 58 identical timestamps mean the run log no longer records when work happened.

Output: `docs/audit/E-backfill.md`.

## 7. AUDIT F — envelopes, protected trees, spend

- `linecount-a.txt` reports **430 / 1850**, `linecount-b.txt` reports **156 / 1625**. Recompute both against `before-a/` and `before-b/` yourself. Confirm the budgets were never pooled.
- Protected roots — `D:\Product Software\` outside `Production Workspace\`, `D:\multi model terminal app\`, `D:\Sovereign Distillery\`, `D:\Sov 1\`, `D:\Token Piggy Bank\` (excluding `data/**`) — must be byte-identical to their Band-0 manifests. **Exception:** `evidence/cpm1/scope-handover.md` authorizes writes to the multi-model-terminal tree during one declared window. Verify that handover is honest and bounded.
- `evidence/cpm1/8d/spend-log.txt` claims **zero delivered turns**. Verify no artifact anywhere records a completed provider turn.
- Confirm the Distillery and Token Center **copies** carry the recorded edits and the **originals** are untouched.

Output: `docs/audit/F-envelope.md`.

## 8. AUDIT G — adversarial sample

Pick **fifteen** goals across the bands, weighted toward Audit A's weakest predicates. For each, ignore the oracle entirely and ask: **does the product actually do this?** Read the source, run the test, hit the endpoint.

Include at minimum: one Band 7 registry goal, one Distillery goal, one Token Center goal, one Band 10 acceptance goal, one Package B goal, and **G120's diff classification** (which asserts `UNEXPECTED == 0` — verify that independently, because it is the run's own self-audit).

Output: `docs/audit/G-adversarial-sample.md` — `CONFIRMED` / `REFUTED` / `UNVERIFIABLE` per goal, with the command and output that decided it.

## 9. Rules of conduct

- **Change nothing.** No repairs, no ledger writes, no gate edits, no `PASS`. Write only under `docs/audit/`.
- **Cite or drop it.** `file:line`, or `command → output`. A negative claim requires the search that produced it — record the search.
- **Truncated console output is not evidence.** Capture to a file and read the file. This exact failure produced a 63-character hash and a fabricated error quotation earlier in this run.
- **Do not accept an artifact's assertion as proof of the thing it asserts.** An evidence file saying "the suite passed" is not a passing suite.
- **Report what you could not check**, and why, as prominently as what you could.
- Findings are ranked by what they would cost if wrong, not by how many you found.

## 10. Deliverable

`docs/audit/AUDIT-01-REPORT.md`:

1. **Verdict on the 107** — how many are substantively evidenced, how many rest on structural or trivial predicates, how many you could not determine.
2. **Verdict on the 17 NOT_RUNs** — genuine vs convenient.
3. **Ledger integrity** — clean or not.
4. **Envelope and protected-tree integrity** — clean or not.
5. **Findings**, most severe first, each with its citation and what it would cost.
6. **What you could not audit**, and why.
7. **A recommendation to the operator**: which gates are safe to promote to `PASS`, which need work first, and which claims should be withdrawn.

**A defensible "62 of the 107 are substantively evidenced and 45 rest on structural predicates" is worth far more than an unexamined 107.** Do not soften a finding to be agreeable, and do not manufacture one to look thorough.
