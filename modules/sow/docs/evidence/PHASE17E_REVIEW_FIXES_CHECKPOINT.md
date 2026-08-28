# PHASE 17E — WORK-IN-PROGRESS CHECKPOINT: the composition's reviewers came back with findings

**Unit:** `phase-17e.review-fixes` (iteration 100) · **Status: THE GATE IS NOT CLOSED. NO TAG.**
**Date:** 2026-07-31 · **Directive:** AUTONOMOUS_BUILD_DIRECTIVE.md §16 track 17E (high-stakes gate)
**Work commit:** `8919a1f` (composition build: `b292783`, `f470533`) · **Predecessor tag:** `gate/phase-17d`

This is a checkpoint, not an evidence report. `gate/phase-17e` and `product/fully-live` are
**not** created by this unit and the loop stays RUNNING. The reason is in §1.

---

## 1. What happened

Iteration 99 tagged `gate/phase-17d`. Iteration 100 built the 17E composition (work commits
`b292783`, `f470533`) and produced a fully-live receipt on this host that came back **`ok:true`** —
every DONE leg green in one Electron process. Before closing a high-stakes gate on it, the mandatory
**gate-validator** and the **spec-auditor** were run in the foreground against that receipt and its
source. Neither cleared it:

| Reviewer | Verdict | Findings |
|---|---|---|
| gate-validator (isolated context) | **PASS_WITH_RESERVATIONS** — "3 must-fix defects before the evidence commit / `product/fully-live` tag" | D1–D3 must-fix, D4–D6 minor, D7 process |
| spec-auditor (30 invariants + drift list) | **FINDINGS (14)** | F1 high, F2–F6 moderate, F7–F14 minor |

Both found the same class of defect, and it is the class this whole track exists to prevent: **a
green leg that the wrong producer could also have satisfied, and a receipt that claims more than it
measured.** The validator reproduced the worst one — it rendered the complete 16D demonstration trio
(17D's F2 defect) in the drawer and the leg stayed green, because the rule read one row and named
itself "only". So the receipt at `f470533` is **superseded**: the code it measured has changed, and
the composition re-runs against the fixed tree before any tag exists.

Nothing was softened and no finding was deferred to make the gate closable. The receipt that
produced `ok:true` is committed as-is, marked superseded, so the history shows what was believed
and when.

## 2. What shipped in this unit

### The high finding: U111, and it was 17E's to close

`docs/registers/UNRESOLVED_ISSUE_REGISTER.md` U111 (opened at 17B `.spawn`, **owner: 17E**) says the
in-Electron live legs consume a real subscription terminal against a SCRATCH ledger, and names the
fix: *"a governor that can tell a DIAGNOSTIC holder from a product one and count both — owed to 17E,
where the assembled run needs exactly that distinction anyway."* The composition did not close it,
doubled the exposure to two live terminals, and then presented the redirection as a **safety**
property in its scope note. True in one direction; in the other it was the reason the enforcing
governor counted zero, so an operator shell at its own allowance of 2 could have brought the real
total to 4.

`node_runtime/supervisor/terminal_lease.py` now implements what U111 asked for. A ledger whose path
comes from the env override is a **diagnostic scope**: it writes only its own records — a check must
never adopt or release a terminal the operator's shell holds, which is why the redirection exists —
and it counts the durable ledger's live leases as a **read-only baseline** in `in_use`, in every
`acquire` admission decision, and in `seed_governor` (so a bounded emitter's in-process gate chain
inherits the same refusal). The refusal message names the baseline holders it cannot see.
`snapshot()` separates the classes (`own_in_use` / `baseline_in_use` / per-holder `scope`), because
a total nobody can attribute is no more readable than the dishonest zero. An unreadable durable
ledger raises rather than counting a reassuring zero. Product (non-redirected) behaviour is unchanged
by construction and pinned by a test. Nine new tests in `tests/unit/test_terminal_lease.py`.

### The must-fix verdict defects

* **D1 — "only" read one row.** `approvalDrawerIsRealSessionEvents` validated the first
  `protected_action` and left every other row unexamined, under the name
  `approval_drawer_shows_only_real_session_events`. The validator's repro put a genuine row first and
  the entire demo trio behind it: green. Every row now needs provenance (a recorded event id and a
  real channel — `unknown` is the fold's own default and is not one), and the reproduction is a test
  that fails without the fix. A multi-row drawer whose rows all carry provenance still passes: the
  rule is provenance, not row count.
* **D4 — a mixed pool passed as live.** `liveDispatchIsHonest` examined only the rows already
  claiming `leg: "live"`, so a pool of one live and one mock worker satisfied `legs.workers: "live"`.
  `live` is a claim about the pool; a row that does not carry it makes the label an overstatement.
* **D3/U216 — `synthesized_by` never discriminated.** It is a hard-coded adapter literal
  (`live_succession.py` says so itself), identical on mock and live feeds, so the verdict's non-empty
  check on it could not fail and a reader beside a live Fable-5 pane would read it as Fable 5. The
  discriminating field is `legs.conductor`, which says `mock`. The receipt now carries
  `dispatch.synthesized_by_note` and the scope note states it.
* **F6 — the launch-path guard scoped to the wrong block.** It anchored on the FIRST
  `if (process.env.SHELL_SELFCHECK)` in `main.js` (the renderer console-logging block), which put the
  **product** conductor auto-launch inside the "self-check only" region — a `liveWorkers: true` added
  there, the exact scenario the test exists for, would have passed. It anchors on the unique
  dispatcher now and asserts the boundary contains the auto-launch. Falsified: adding
  `liveWorkers: true` to the auto-launch turns it red (`fail 1`), and `main.js` restored
  byte-identically.

### The disclosures the composition had dropped

Each of these was gated in an earlier receipt of this same phase and lost when the legs were composed
— which is its own lesson about composition receipts.

* **F3/D2** — the protected-verb utterance is a scripted stand-in through the visible mock engine (a
  protected verb must be refused before anything is delivered; that needs no microphone and no live
  exchange). 17D recorded the engine descriptor; 17E had dropped it while its own `voice.engine`
  block says `mock:false` about a different leg. Recorded again, plus a substitution entry.
* **F2** — 17B made `scratch_ledger_removed` and `real_ledger_unchanged` conjuncts of `ok`; the
  composition kept neither, and removed the scratch ledger without reading the result. Both are
  checks again, measured by digest across the run.
* **F4** — the pinned VRAM budget is disclosed in the receipt (`worker.budget_source`), not only in
  the code comment above it, and says plainly that it is not this host's GPU capacity.
* **D5** — `feed.live_run` (the emitter's own dating and bounding of its live call) is carried into
  the receipt, so the live dispatch is datable from the receipt alone.
* **F7** — `model_available` is tri-state; folding `null` into `false` made "the CLI accepted the
  operator's slug" and "nobody asked" the same record. `model_probe_state` is recorded, and the run
  may assert a `--model` slug only where the probe confirmed it.
* **F13** — the I-X3 leg no longer hard-codes `allowance === 2`. A config that narrows to 1 is
  legitimate (`live_authorization` permits it), and the old check went red on it for a reason that is
  not a defect. The rule moved into the pure verdict module, where it is falsifiable.
* **F9** — the session-approval log is isolated under `SHELL_SELFCHECK` exactly as `RECOVERY_DIR` is.
  `begin()` truncates, so a diagnostic run launched beside a live operator shell would have wiped
  that session's drawer log — and its own "the drawer was empty until this run caused something" leg
  would have been satisfied by the truncation rather than by an absence.
* **F5/U214** — the OWED check is renamed for what it measures
  (`every_known_unevidenced_leg_is_named_with_its_reference`); the list is authored and cannot
  discover a leg nobody wrote down. `diagnostic_ledger_scope` (U111) is now a required OWED key, so
  the receipt cannot drop the disclosure.
* **F12** — `dispatch-source.js`'s owed note no longer says the live-worker leg is owed to 16F.

## 3. Test output, this host, after the changes

| Suite | Command | Result |
|---|---|---|
| Python | `py -3.12 -m pytest tests/ -q` | **1478 passed**, 0 failed, in 380.18s (baseline before this unit: 1470) |
| Desktop | `cd apps/desktop && npm test` | **634 passed, 0 failed** (was 623 — 11 new) |
| Terminal | `cd terminal && node --test test/*.test.js` | **212 passed, 0 failed** |
| Mutation (pane input) | `npm run test:falsify` | **ALL MUTATIONS CAUGHT**, `main.js` restored byte-identically |
| Mutation (disarm authority) | `npm run test:falsify:authority` | **ALL 11 MUTATIONS CAUGHT**, all five files restored byte-identically |

`tools/mutation/pane_input_bypass_mutations.js`'s `PINNED_BASELINE` was re-pinned deliberately: the
one `main.js` edit in this unit (the F9 log-path isolation) touches no `pane:input`, no supervision
gate and no delivery path those mutations target, each mutation was re-read against the new tree, and
the harness reports ALL CAUGHT on it.

**Note on the interpreter.** Plain `python` on this host is 3.14 and has no `jsonschema`: `python -m
pytest tests/` produces 76 collection errors that are an environment artifact, not a regression. The
project's recorded interpreter (D-LANG-01) is 3.12 — `py -3.12`. Recorded here because the first
command this unit ran was the wrong one.

## 4. What remains before `gate/phase-17e` can close

Exactly this, as the next unit's first act:

1. **Re-run the composition** in the packaged Electron runtime on this host
   (`SHELL_SELFCHECK=fully-live`) against the fixed tree, producing a new
   `docs/evidence/receipts/PHASE17E_FULLY_LIVE_SELFCHECK.json` whose `source.commit` is the fixed
   tree's. This spends one governed live exchange per prompt — §16's minimal-live discipline —
   and D-LOOP-1 teardown is measured inside the check.
2. **Re-run both reviewers in the foreground** against the new receipt. Neither prior verdict
   carries over: they reviewed superseded code.
3. Only then: `PHASE17E_EVIDENCE_REPORT.md`, the FINAL report addendum, the two-commit convention,
   `gate/phase-17e`, `product/fully-live`, and the operator addressed once.

## 5. Honest limitations of this checkpoint

* The receipt in the tree is the **superseded** one. Nothing in this unit re-measured the composition
  — the fixes are covered by unit tests and by the mutation harnesses, not by an in-Electron run.
  D-P16-0 is satisfied only by step 1 above.
* The gate-validator did not re-execute the in-Electron composition either (it spends the operator's
  subscription); it corroborated the mock producer, the demo trio, the host picker/residency numbers,
  the lease allowance, the surviving-process check and the mutation harnesses independently.
* U111 is **narrowed, not closed**: the baseline is read before the scratch lock is taken, so a
  terminal the operator's shell acquires inside that window is uncounted (U215). Strictly closer to
  the cap than the zero it replaces.
* Registers: U111 narrowed; U213–U218 opened; F11 and F14 answered without rows. All in
  `docs/registers/UNRESOLVED_ISSUE_REGISTER.md`.
