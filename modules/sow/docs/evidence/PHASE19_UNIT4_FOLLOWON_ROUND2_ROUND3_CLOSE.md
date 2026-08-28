# Phase 19 — unit `phase-19.4-followon`: rounds 2 and 3, and the CLOSE

**Unit:** `phase-19.4-followon` — the follow-on unit 19.4's close named.
**This document closes it.** The predecessor is the WIP checkpoint
`PHASE19_UNIT4_FOLLOWON_U373_RESIDUAL_U363_VERDICT_CHECKPOINT.md`, which recorded exactly one owed
item: **round 2 of both mandatory reviewers**. That item is discharged, and so is the round 3 the
round-2 repairs made owed.

**Commits:** `3b1f654` → `17bfe06` → `6bf3ec0` → `52773f3`/`e88b127` (the checkpoint) →
**`fe149e5`** (the round-2 remediation, this document's work commit) → this evidence commit.
**Tag:** none. `gate/phase-19` is unit 19.10's; `product/multi-frontier-v2` is never moved.
**Register rows this document adds:** [[U398]]–[[U404]] (round 2), [[U405]]–[[U409]] (round 3).

---

## 1. Reconciliation at entry

`git tag -l` newest: `gate/phase-18e`, `product/multi-frontier-v2`. `LOOP_STATE.json`:
`phase-19.4-followon.round2`, iteration 129, HEAD `e88b127`, tree clean. **They agree** — Phase 19's
gate belongs to unit 19.10 — so no reconciliation commit was owed. No prior turn died mid-unit.

## 2. Round 2 — both reviewers, foreground and in-turn, over `6bf3ec0`

Neither returned FAIL.

| Reviewer | Verdict | Findings |
|---|---|---|
| gate-validator | **PASS WITH RESERVATIONS** | 0 BLOCKING, 1 MAJOR, 3 MEDIUM, 3 MINOR |
| spec-auditor | **PROHIBITED DRIFT: NONE** | 0 BLOCKING, 2 MAJOR, 4 MEDIUM, 7 MINOR |

The validator re-derived every measurement the checkpoint claimed and **every one reproduced
exactly** — 942/0/0 desktop, 216/0 terminal, 30+26+36+5 mutations CAUGHT with byte-identical
restores, the receipt's `source.commit`, all 9 legs, the 41-character separator, the 7-of-10 refusal
count replayed independently, freeze integrity `8E604CA3…` unchanged. It also re-established the
"MOVED, not rewritten" claim on its own terms: **1,620,000 comparisons** through old and new
`paneAcceptsTypedText`, **0 behavioural differences**.

### The three MAJORs, and why each was real

**[[U398]] — the only BEHAVIOUR change round 1 made was ungraded.** The validator deleted the
provider-controlled excerpt's whitespace collapse and watched all 942 tests stay green; then did it
again leaving only the newline. `control/modal-affordance.js` sat on the invariant-1 decision path
with **no pin and no mutation at all** — while `system_pane_write_mutations.js` had re-pinned both
files at that commit and **named the change by name** in its own note. A harness that records its
trigger and does not act on it is [[U397]]'s pattern recurring inside the unit that opened U397, and
it fails this harness's own stated standard: *a guard that has never been shown to fail is not a
guard.*

**Two false receipts, both inside instruments that GENERATE evidence.**
`readiness-window-selfcheck.js` claimed *"NOTHING in the shell reads it to decide anything any
more"* — the OPERATOR's voice path still does, through `main.js`'s `paneEmittedAll` →
`conductor-write.js` guard 3 → `paneAcceptsTypedText`. Stricter direction, but the absolute was
false, and it was the replacement for round 1's identical defect.
`system-pane-write-selfcheck.js` still described a whole-buffer denylist read and promised, in the
future tense, that *"unit 19.4 narrows it"* — for work that had already landed.

### What `fe149e5` changed

- **[[U398]] closed.** `[AFFORDANCE]` pinned; **P23/P24** grade both directions (excerpt verbatim; a
  space-only collapse leaving the newline); a behavioural assertion covers the forged log line.
- Both false receipt strings repaired, and the U328 `finding` widened to name `modalAffordance`.
- **[[U400]]** — U395's byte half, measured: a 30-row dense-SGR repaint is **32,596 raw bytes**,
  twice `TAIL_BYTES`, so a live modal at row 5 of a **spawn-default** pane is written into. A
  row-aware bound therefore does NOT close U395. The unmeasured *"maximized pane on this host"* is
  retracted.
- **[[U401]]** — 24 → 80 recorded as widening [[U372]]'s window 3.3× and [[U381]](a)'s conductor
  label (a pane showing `(y/n)` now badges the conductor `PROVIDER_SETUP_REQUIRED`), not only as the
  narrowing it was recorded as.
- **[[U402]]** — four fixtures derive from `TAIL_LINES` instead of a literal, at numerically
  identical values.
- **[[U399]]** — the register said OPEN where the unit had closed, and [[U373]]'s row asserted a test
  requirement that **inverted in this very unit**. Both reviewers found it independently. Corrected
  by appended rows; nothing edited in place.
- **[[U403]]/[[U404]]** — recorded, no action: the harnesses' exclusion from `product_paths` is a
  documented design decision, and the `Object.freeze` non-identity is a benign strengthening.

## 3. Round 3 — both reviewers again, foreground and in-turn, over the delta `e88b127..fe149e5`

Repairing after validation voids it, so round 3 ran. Scoped to the delta, because round 2 had already
swept the unit and its measurements reproduced exactly.

| Reviewer | Verdict | Findings |
|---|---|---|
| gate-validator | **PASS WITH RESERVATIONS** | **0 BLOCKING, 0 MAJOR**, 2 MEDIUM, 3 MINOR |
| spec-auditor | **PROHIBITED DRIFT: NONE** | 0 BLOCKING, 1 MAJOR, 6 MEDIUM, 5 MINOR |

**The builder's claim about the delta — *"no product BEHAVIOUR changed"* — was put to the validator
to falsify, and survived.** It read every hunk in `apps/desktop/control/` at `--unified=0`: every
changed byte in all three control modules is inside a comment. `TAIL_LINES + 40 = 120` and
`TAIL_LINES - 20 = 60`, evaluated by `require()` — the fixtures build identical scenarios. Declaration
order unchanged. Exactly three emitted strings changed, all deliberately.

**The new grading was checked adversarially, and this is the part worth reading.** The validator
applied P23 and P24 by hand and ran the full desktop suite **with only the new test skipped**:
**943 pass, 0 fail.** The new assertion is the *sole* grader of the collapse — a clean reproduction of
round 2's MAJOR-1 and a clean demonstration that the repair lands exactly on it. It also mutated the
receipt-disclosure clauses and confirmed the new pinning test goes red on each.

**It independently reproduced [[U400]]** rather than accepting the number: 30-row dense-SGR frames at
80/100/120 columns measure **27,057 / 33,849 / 40,477** raw bytes, all above the 16,384 budget, and
through the *production* window → gate chain a trust modal at row 5 **is permitted** at every width.
The register's 32,596 sits inside that band. U400 and U401 were judged *"accurate and NOT softened"*.

### The one MAJOR, and how it was discharged

The spec-auditor found that `fe149e5` repaired the U328 receipt STRING while the published U328
receipt — `PHASE19_3_SYSTEM_PANE_WRITE_SELFCHECK_phase-19.3.round2_…` — still carried the false one.
The repair existed only in source, in the unit that changed the write gate, against the 19.4 close's
own trigger. It flagged this as **not safe to carry as prose**.

**Discharged with evidence, not prose** ([[U405]]): the check was re-run in-Electron at HEAD —
`PHASE19_3_SYSTEM_PANE_WRITE_SELFCHECK_phase-19.4-followon.round3_20260811T024929Z.json`,
**ok: true, 4/4 legs**, `source.commit fe149e5`, `tracked_product_tree_clean: true`,
`live_exchanges: 0`, both strings correct at publication. Re-running a check changes no code, so it
does not void the reviewers who had just passed the code — which is precisely why this discharge was
available and a prose edit was not.

### Everything else is CARRIED, deliberately

Both reviewers were told in advance that findings at MEDIUM or below would be recorded rather than
repaired, and asked to grade accordingly and say which they considered safe to carry. Both did. The
carried set is [[U406]] (the U328 disclosure strings are ungraded and hardcode the bounds — the
genuine one, and it bites the moment U395's owner touches a constant), [[U407]] (the excerpt's length
bound is unreachable today, so nothing grades it), [[U408]] (four prose corrections *in the round-2
prose repairs*), [[U409]] (a fifth U402-class fixture; the anonymous receipt twin).

**This is the terminating discipline, stated plainly.** Repairing after round 3 would void round 3
and owe a round 4. This unit has now spent five rounds in that loop, and each round's repairs have
been prose that generated the next round's prose findings. Phase 19's exit criteria permit a finding
to be *"re-recorded with a reason it is not closing"*; that is what these five rows are. Nothing
carried is a defect in shipped behaviour — the validator's own summary is that the one live product
weakness in view (the byte-budget crop) **is pre-existing, is not introduced by this delta, and is now
disclosed in three places rather than one**.

## 4. Measurements on the closing tree (`fe149e5`), foreground, in-turn

| Instrument | Builder | Round-3 validator, independently |
|---|---|---|
| desktop suite | 944 / 0 / 0 | **944 pass, 0 fail, 0 skipped** |
| terminal suite | 216 / 0 | **216 / 0** |
| `system_pane_write_mutations.js` | 32 CAUGHT | **ALL 32 CAUGHT**, 4 files BYTE-IDENTICAL |
| `readiness_signal_mutations.js` | 26 CAUGHT | **ALL 26 CAUGHT**, BYTE-IDENTICAL |
| `pane_input_bypass_mutations.js` | ALL CAUGHT | **ALL CAUGHT**, BYTE-IDENTICAL |
| `orchestration_mutations.js` | 5/5 | **5/5 CAUGHT**, all restored |
| `disarm_authority_mutations.js` | not claimed | **ALL 11 CAUGHT** (run anyway) |
| stale `.mutation.lock` | none | **none** |
| surviving `electron.exe` | none | **none** |

**D-P16-0 receipts, both re-taken in-Electron at `fe149e5`:**

- `PHASE19_4_READINESS_WINDOW_SELFCHECK_phase-19.4-followon.round2_20260811T022637Z.json` —
  **ok: true, 9/9 legs**, tree clean, `live_exchanges: 0`. Leg **F** still inverted (gate permits,
  whole-buffer read of the same live pane says `AUTH_REQUIRED`, 2 prompts delivered, READY); leg
  **I** still refuses a menu the classifier says nothing about; leg **H** reproduces
  **byte-for-byte** against the round-1 receipt.
- `PHASE19_3_SYSTEM_PANE_WRITE_SELFCHECK_phase-19.4-followon.round3_20260811T024929Z.json` —
  **ok: true, 4/4 legs**, the [[U405]] discharge.

**Python suites not run, and the reason is not that they are slow:** no commit in this unit touches a
`.py` file. 19.10 owns that run ([[U339]]).

**D-LOOP-1:** three in-Electron runs this unit, every pane killed inside its run; `tasklist` reports
**zero** surviving `electron.exe`; no stale `.mutation.lock`; tree clean of product changes after
every harness. **No live provider call, no credential, `live_exchanges: 0` for the whole unit.**
**D-LOOP-2:** all four reviewer runs were foreground and synchronous, in-turn. Nothing was
backgrounded across a turn boundary and nothing was left "in flight".

**Scope and invariants:** no file under `docs/canonical/` or `schemas/` touched; freeze integrity
unchanged; nothing added under `mcp_server/` (invariant 7); the voice path is discussed in a comment
and untouched in code (invariants 25/26); every refusal still carries its reason (invariant 27); the
untouchable set undisturbed; registers appended, never edited in place; `.gitattributes` LF pin
honoured (0 CR bytes). The validator's judgement on invariant 1: the delta **strengthens** it, since
the write gate's one behaviour change is now graded in both directions.

## 5. What this unit closes, and what it hands on

**Closed:** [[U373]]'s residual, [[U380]], [[U396]], [[U398]], [[U399]], [[U402]], [[U405]], and the
[[U394]] carries. **Narrowed, not closed:** [[U363]] — 7 of 10 permission screens refuse where 1 did,
3 asserted as residual, positive-evidence half still owed.

**Carried to later units, unchanged:** [[U395]]/[[U400]] (the row-aware bound AND the byte budget —
U400 is the correction that a row-aware bound alone does not close it) and [[U406]] to the same
owner; [[U397]] (the settle-wait mutation and its fixture); [[U401]], [[U407]], [[U408]], [[U409]];
[[U386]](c) + [[U393]] MINOR-1 → 19.6; [[U335]]/F7 → 19.7; [[U382]] + F1/F2 → 19.9; [[U339]] and the
phase gate + tag → 19.10. [[U387]] is the operator's (a stale worktree outside the repo root,
prohibition §2.5).

**Next work unit: `phase-19.5`** — U330 + U332, the one write path and a gate that cannot be skipped,
including the genuinely concurrent two-process falsification the directive notes is *currently absent
everywhere in the repo*.
