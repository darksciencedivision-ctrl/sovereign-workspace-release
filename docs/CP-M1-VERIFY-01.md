# CP-M1-VERIFY-01 — Reviewer verification of the D-1…D-4 ledger repair

| Field | Value |
|---|---|
| Scope | Independent on-disk verification of the builder's D-1…D-4 completion claims, 2026-08-25. Read-only. |
| Verdict | **D-1, D-2, D-3 and D-4 are confirmed on disk.** The STOP-class corruption is repaired and the repair is honestly recorded. |
| New findings | E-1 … E-5 below. None blocks the resume. E-2 and E-3 are guard defects and should be closed before the next ledger write. |
| Standing | Reviewer note. Authorizes the resume at G21 and nothing else. No gate is promoted to `PASS` here. |

---

## 1. What was verified, and how

Every value below was recomputed from disk by the reviewer, not read from the builder's report.

| Claim | Method | Result |
|---|---|---|
| Ledger sha256 `e5ae4224…54d9ad` | `sha256sum` | **MATCH** — `e5ae422407bde7f38bb78197114fc245a4000180f8fcf928c326b7bc0b54d9ad`, 74 327 bytes |
| Gate keys | JSON parse | **MATCH** — `[0,1,2,3,4,5,6,4b,4c,5b,7a,7b,8a,8b]` |
| Gate 4 restored full-length | byte read | **MATCH** — `659ff9b635a22ddbdc9065c56ac5fbb277dcce25d3110354acb5e9134fed9f6d`, 64 chars, `dc` present |
| Gate 5 restored | byte read | **MATCH** — `df4cc05394c0a7756ea4e48666661cd8041686dc712ee54931bd0d73fb2c07d7` |
| Both differ from live | hash of `shell/BUILD-MANIFEST.txt` | **CONFIRMED** — live is `dca3eb40b628e08a622bff99d579fc85853582b4eb3edcd6a93d3f6a50893562`; the only ledger entry carrying it is gate **8b**, which is legitimately current |
| Witnesses agree | parse of both snapshots | **CONFIRMED** — `loop5/ledger-snap-pre6.json` and `theme01/ledger-snap-pre7.json` both carry `659ff9b6…` for gate 4 and `df4cc053…` for gate 5 |
| No other drift | **independent** 406-row comparison of every `{path, sha256}` pair in gates 0–7b against **both** witnesses | **0 mismatches.** One row absent from `pre6` (`docs/REVIEW-BUILD-06.md` in gate 6) — expected, `pre6` predates gate 6 |
| No malformed hashes | length + charset scan of every evidence row in the ledger | **0 malformed.** The 63-character mis-transcription class is gone |
| Reviewer attribution intact | field read | **CONFIRMED** — reviewer ×9, operator ×1 (gate 6), `None` ×2 (7a, 7b `CANDIDATE`) |
| Audit completeness | row count | **CONFIRMED** — `evidence/cpm1/8b/ledger-corruption-audit.txt`, 236 pipe-delimited rows = 235 data rows + header; the two `MISMATCH->RESTORED` lines are at gate 4 and gate 5 |
| Guard exists and is wired | source read | **CONFIRMED** — `ledger_snapshot_ok()` at `evidence/cpm1/tools/goalcheck.py:1357`, enforcing all twelve historical keys |
| D-4 supersede | ledger note read | **CONFIRMED** — gate 8b's note carries the full two-hit account including the 63-character mis-transcription, and cites the audit by path and row count |

**The gate-4 audit line is honest in a way worth naming.** It reads `659ff9b635a2 | 659ff9b635a2 | MISMATCH->RESTORED` — the twelve-character display prefixes are identical, so a prefix-only comparison would have called it a match. The builder recorded it as a mismatch anyway. That is the correct behaviour and it is the reason the second corruption was caught.

## 2. Findings

### E-1 · Gates 7a and 7b are corroborated by no witness — "verified" overstates them

Neither `ledger-snap-pre6.json` nor `ledger-snap-pre7.json` contains a `7a` or `7b` key. Both snapshots predate the THEME-01 entries. The 235-row audit says so in its trailer, correctly.

The consequence is not recorded anywhere: **`evidence/cpm1/ledger-snapshot-verified.json` now freezes 7a and 7b at values that no independent artifact has ever attested.** Their `shell/BUILD-MANIFEST.txt` hash `6ebc420e…5235e` is *not* the live hash, so it does not carry the corruption signature that exposed gate 5 — that is evidence of absence of *this* fault, not evidence of correctness.

The file's name asserts more than its contents support. **Fix:** add a provenance header to `ledger-snapshot-verified.json` naming which keys are witness-corroborated (`0,1,2,3,4,4b,4c,5,5b,6`) and which are self-attested (`7a,7b`), and state it in the gate note. Nothing needs to be re-restored.

### E-2 · The guard compares two fields, not the entry

`ledger_snapshot_ok()` compares `status` and the `evidence` set. It does not compare `evaluated_by`, `reviewer_note`, `utc`, `basis`, or `superseded_ledger_sha256`.

A write that flipped `evaluated_by` from `reviewer` to `builder`, or rewrote a reviewer's note, passes the guard silently. *"Never alter `evaluated_by: reviewer` entries"* is a standing constraint of this package; the guard built to enforce that constraint does not enforce that field.

**Fix, and it is free today:** the reviewer compared the *whole* gate object for all twelve keys against the snapshot and found **zero differing fields**. Tightening the comparison to the full object costs nothing now and closes the hole permanently.

### E-3 · The guard is invoked from exactly one predicate

`ledger_snapshot_ok()` is called once, at `goalcheck.py:541`, inside `g19()`. Its coverage is therefore incidental — it holds only because the oracle happens to evaluate every goal on every run. `g124()` has a *separate*, weaker check: a hardcoded status map with no hashes at all.

The D-3 analysis correctly identified that the original hole was "no whole-ledger anchor after the first insertion." The repair reintroduces an anchor but binds it to one goal's predicate rather than to the act of writing.

**Fix:** call it from the per-iteration preamble so it gates every ledger write, and replace `g124()`'s hardcoded map with the same call.

### E-4 · `LOOP-LEDGER.jsonl` has a hole at index 15

16 lines, indices `1…14, 16, 17`. **`i:15` is absent.** The report's "16 ledger lines" is true; the sequence is not contiguous.

An append-only ledger with a gap cannot distinguish *a counter that skipped* from *an entry that was removed*. This needs an account, not a repair — do **not** renumber, and do **not** synthesise a line 15.

### E-5 · Gate 8b's note carries a line count that no longer matches its own artifact

The 8b note states `TOTAL-A 129+test files`. `evidence/cpm1/linecount-a.txt` now reads `TOTAL-A | 166 | 1850` — G20 added 37 lines after the note was written.

Accurate at authoring time; misleading to a reviewer reading the `CANDIDATE` gate later. **Fix:** qualify it as *"as of Band 2 close"*, or amend the figure. Either is a note edit, not a gate change.

### Observation · Two oracle-count regressions, unaccounted

`goalcheck-8` 17/124 → `goalcheck-9` 16/124, and `goalcheck-13` 21/124 → `goalcheck-14` 20/124. A goal that was TRUE became FALSE, twice. Both are plausibly legitimate (a refreshed canonical artifact invalidating a predicate that cited the old one), and the count recovered both times. But a goal-state loop whose count moves backwards without a ledger line naming the goal is exactly the shape of the defect class this package exists to catch. One line each in the resume report.

## 3. Not verifiable by the reviewer

The reviewer reads the filesystem, not the Windows process table. **Unverified, and carried to the operator:**

- whether fs-watch driver pid **47684** is still alive
- the current owner of port **8700** (the oracle reports `busy:[8700]`, consistent with the retained external Debate pid 82344)

`evidence/cpm1/tools/fswatch.stop` does **not** exist and `evidence/cpm1/fs-watch-cpm1.txt` has **not** been written — the window opened at 16:30 is still open, which matches `G117: FALSE  replacement fs-watch artifact absent (window still open?)`.

The driver on disk is the corrected four-root version (C-1 applied): `D:\Product Software`, `D:\multi model terminal app`, `D:\Sovereign Distillery`, `D:\Sov 1`, with Token Piggy Bank deliberately excluded and the exclusion reasoned in the file header. That is correct.

**A-7 disposition:** the builder paused; it did not end its session. If the operator resumes in the **same** OpenCode session, the window stays open — one continuous window from G5 is strictly better evidence than two with a gap. Close and re-open only if a **new** session is started, and then record the gap in the A-7 table.

## 4. Resume

Bands 0–2 stand closed. Gates 8a and 8b stand `CANDIDATE`. 22 of 124 goals TRUE. 166 of 1 850 Package-A changed lines used; every area within cap.

**The first failing goal is G21.** The resume is authorized subject to E-2, E-3, E-4 and E-5 being addressed in the same turn, before any further ledger write — E-2 and E-3 because the guard is the thing standing between this package and a third corruption, and it is weaker than its own incident note claims.

---

*All values recomputed on disk 2026-08-25 by the reviewer. This note authorizes the resume at G21 and nothing further. No gate is promoted here.*
