# SW-JOURNAL-002-A3-LOOP — builder report (re-run, executed start to finish)

- Run: SW-JOURNAL-002-A3-LOOP, re-run per operator instruction recorded at 2026-09-07T05:25:32Z
  in `evidence/OPERATOR-INSTRUCTIONS.log` (first attempt STOPPED at entry, HOST_NOT_QUIESCENT;
  operator confirmed the stop was correct and re-issued the loop unchanged).
- Builder: qwen3.8-max (deepseek harness). Worktree: `D:\production software 3\release-worktree`.
- Report written: 2026-09-07T07:25Z (UTC). This file replaces the stop-run REPORT.md of 05:17Z.
- CORRECTED in a later pass (host clock 2026-09-07T16Z; the timestamp `hashes-correction.txt`
  carries) under explicit operator authorization. Three things changed and nothing else:
  (1) the two stale tests named below were edited — exactly the two revoked assertions, nothing
  else in either file, both titles kept — so the JS suite is now 1313/1313/0;
  (2) the "store round-trip mojibake" finding is WITHDRAWN on measurement; its section is kept
  below, not silently deleted, with the reason;
  (3) the summary table, the stale-test section, "What was NOT done", "Exit integrity" and the
  evidence index were updated to the post-fix re-run captured in this directory. Read-only
  integrity was re-verified: all 9 snapshotted files (incl. `main.js`) still MATCH byte-for-byte
  (`hashes-correction.txt`); git tracking state is unchanged (`git-status-correction.txt`).
- Entry conditions (re-verified at Step 0): ports 5175/8700/5180 free, pid 10208 gone
  (`quiescence-rerun.txt`); all three A3 entry pins MATCH + 9 read-only files snapshotted
  (`entry-pins-rerun.txt`); baselines green: JS 1274/1274/0, Python 2746 passed + 3 skipped,
  shell 323 passed, text integrity 4 passed (`baseline-*.txt`).

## Result summary (all numbers from captured suite output; see evidence index)

| Suite | Baseline (pre-edit) | Final (post-edit) | Evidence |
|---|---|---|---|
| JS `node --test test/*.test.js` | 1274 tests / 1274 pass / 0 fail | **1313 tests / 1313 pass / 0 fail** | `baseline-js.txt`, `js.txt` |
| Python `modules/sow/tests/unit` | 2746 passed, 3 skipped | **2746 passed, 3 skipped** | `baseline-python.txt`, `python.txt` |
| Shell `shell/tests` | 323 passed | **323 passed** | `baseline-shell.txt`, `shell.txt` |
| Text integrity | 4 passed | **4 passed** | `baseline-text.txt`, `text.txt` |

JS accounting: 1313 = 1274 baseline + 39 new tests (all 39 pass). On the first re-run two
PRE-EXISTING tests failed — stale assertions the A3 charter itself revokes (attributed below).
The operator has since authorized editing exactly those two assertions, and both now pass, so
the suite is 1313/1313/0. No other existing test changed behavior; Python/shell/text counts
are unchanged.

**The instructed hold "JS 1,274 + new tests / 0 fail" is now met.** What was wrong was the
TESTS, not the change: each of the two asserted the exact pre-A3 behavior that items 5 and 6
order removed. They are fixed below under the operator's narrow authorization — the two
assertions and nothing else in either file, both titles kept.

## The two stale tests — FIXED under operator authorization (rule 7: say which was wrong)

1. `test/conductor-view.test.js:78` (test "F-28: nondelegated panes go through journal
   observation; view delivery gets a receipt") asserted `receipts[1].answer === result.context.view`.
   Item 5 (F-46d) orders receipts to record entry ids, counts, truncation, notice — and NEVER
   the view text. The test WAS stale; the change is correct. It is now FIXED under the operator's
   authorization (the new assertion pins both halves of F-46d — see "Both now pass" below). The
   original first-re-run failure is kept below as the historical record (the receipt carries the
   structured facts, 178 chars, instead of a 453-char view copy):

   ```
   ✖ F-28: nondelegated panes go through journal observation; view delivery gets a receipt
     AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
     + actual - expected
     + '{"entry_ids":["ec495fe8-..."],"entries":1,"panes":["pane-3"],"view_chars":453,
        "truncated":false,"state":"attached","notice":"Worker view attached: 1 entries
        from terminal #3 (pane-3). View not truncated."}'
     - 'WORKSPACE VIEW — observed_pane_output; self_published: false; U58 OWED.\n...'
       (the full view text)
         at TestContext.<anonymous> (test\conductor-view.test.js:78:10)
   ```

2. `test/workspace-journal.test.js:35` (test "F-27: completed delegation is stored and
   projected with both honesty fields") asserted `e.prompt.includes("compare facts")` on the
   `answered` row. Item 6 (F-46e) orders: delegation_requested records objective+task_id
   (not the prompt), prompt_written records the prompt, answered records the ANSWER. The
   objective still rides the answered row in its own `objective` field; only the third
   prompt copy is gone. The test WAS stale; the change is correct. It is now FIXED under the
   operator's authorization (assertion moved to the `objective` field plus `prompt === ""`).
   The original first-re-run failure is kept below as the historical record:

   ```
   ✖ F-27: completed delegation is stored and projected with both honesty fields
     AssertionError [ERR_ASSERTION]: The expression evaluated to a falsy value:
       assert.ok(e.prompt.includes("compare facts"))
         at TestContext.<anonymous> (test\workspace-journal.test.js:35:49)
   ```

Both now pass — the post-fix re-run is `js.txt` (1313 tests / 1313 pass / 0 fail). The two
authorized replacement assertions, exactly as written into the files, are:

   ```
   // test/conductor-view.test.js:78 — replaces receipts[1].answer === result.context.view
   const receipt=JSON.parse(receipts[1].answer);
   assert.deepEqual(receipt.entry_ids,result.context.entry_ids);
   assert.equal(receipt.view_chars,result.context.view.length);
   assert.ok(!receipts[1].answer.includes("WORKSPACE VIEW"));

   // test/workspace-journal.test.js:35 — replaces e.prompt.includes("compare facts")
   assert.ok(e.objective.includes("compare facts"));
   assert.equal(e.prompt,"");
   ```

Nothing else changed in either file and both test titles are unchanged. The two failure blocks
above are the historical first-re-run failures (also in `fastcheck-items3456.txt`), kept not deleted.

## What was done, per item

### Item 1 — F-47: narrow the cleanText POSIX-path redactor
`control/workspace-journal.js`, `cleanText`: the POSIX rule gained one lookahead —
`/(^|[\s("'])\/(?!\/)(?=[^\s"'<>?])[^\s"'<>]*/g`. A path must now carry at least one
path character after the slash, and that character may not be `?`. Decisions: the exclusion
set is minimal (`?` and nothing-after-slash only) — no other punctuation excluded, so no
real path can escape; `/etc/passwd`, `/home/user/x.txt`, `/var/log`, `(/usr/bin/env)`,
line-start `/opt/app/run`, dot-initial `/.config/...` all still redact (tested); Windows
and credential-name branches untouched (tested); over-redaction elsewhere (e.g. `/;`)
remains as the safe failure for a privacy control. Tests: `test/journal-redaction-a3.test.js`
(7 tests, incl. mutation control that restores the broad rule and re-redacts the hint).

### Item 2 — F-45: conductor's own entries out of the worker view; no empty "terminal #"
`control/conductor-view.js`: new exported `viewEligible(e)` — excludes null, `view_*`
(pre-existing), `status === "conductor_reasoning"`, `pane_id === "conductor"` (any status),
and `content_free === true` (item 3); used in `selectEntries` and `compactRoster`.
Labels: roster renders `terminal #N "pane-N"` for numbered panes and just the quoted id for
non-numbered; the delivery notice renders `terminal #N (pane-N)` or the id alone; the view
entry label renders `terminal=#N` or `terminal=<id>`; `composeOwnDigest` in
`control/workspace-journal.js` likewise. Numbered forms are byte-identical to before
(`terminal-identity.test.js`, amendment roster/notice regexes still pass). Conductor rows
remain in the journal (append-only) — only the VIEW leaves them out. Tests:
`test/conductor-view-f45-a3.test.js` (7 tests, incl. mutation control removing the exclusion).

### Item 3 — F-46a: content-free observations marked, excluded from the view
`control/workspace-journal.js`: `observe()` marks `content_free: true` when an ANSWERABLE
capture reduces to nothing but chrome (or its budget slice was empty); the row is still
recorded (status stays `observed`, honesty markers untouched — it IS an observation), with
a reason distinguishing chrome-caused from budget-empty. `prepareEntry` copies `content_free`,
`chrome_removed`, `chrome_kinds` ONLY when present/non-default, and `validEntry` accepts them
as optional typed fields — every pre-A3 entry stays valid and every already-rendered
projection byte-identical (repeat-render and prefix-stability tested; `projectNow`'s
append-only prefix check passes). Unreadable rows are never trimmed and never marked.
View exclusion lives in `viewEligible` (item 2). Tests: in `test/journal-chrome-a3.test.js`.

### Item 4 — F-46b/c: trim only spinner runs, the REPL idle line, exact echoed prefixes — counted
`control/workspace-journal.js`: new exported `trimPaneChrome(text, { writtenPrompt })` with
exactly three rules, measured against the operator's session projection:
- spinner runs: ≥2 characters from the exact closed set of the ten classic "dots" braille
  frames (U+280B,2819,2839,2838,283C,2834,2826,2827,2807,280F — the 1,944 measured chars),
  adjacent or separated only by CR/space/tab. A newline ends a run (never joins lines); a
  LONE frame is model text and stays (tested).
- echoed prompt prefix: removed only when the capture BEGINS with the EXACT text this
  application wrote to that pane (`writtenPrompt`). Exact `startsWith` or nothing — never
  partial, wrapped or fuzzy. The measured ollama wrapped-echo shape (`... ` continuations)
  therefore honestly stays (tested and declared).
- the REPL idle line: the exact whole string `>>> Send a message (/? for help)` (103 measured
  occurrences), removed only in leading runs at the start of a display line, behind at most
  carriage returns (CR = same-line repaint). Mid-line and space-indented occurrences stay.
Rule order spinner → echoed prefix → idle, because removing a spinner run or an echo can
expose an idle prompt to its line start, exactly as the measured captures show.
Every removal is counted: `spinner_chars`, `idle_lines`, `echoed_prefix_chars`,
`removed_chars`, `chrome_kinds` — declared on the entry like `redactions` already are.
Wired into `observe()` (with the pane's newest `prompt_written.prompt` from the store as the
authored text; store failures leave the rule inert, never fatal) and into
`control/conductor-delegation.js` `answerIn` (so a spinner-only pane reads as NO ANSWER
instead of a braille blob — mutation-controlled) with `result.chrome` declared on the
`answered` row. "Thinking..." and any other chrome: NOT removed — not authorized.
Tests: `test/journal-chrome-a3.test.js` (17 tests incl. 3 mutation controls).

### Item 5 — F-46d: view receipts record facts, never the view text
`control/conductor-view.js` `retrieveAndDeliver.record()`: the receipt answer is now
`JSON.stringify({ entry_ids, entries, panes, view_chars, truncated, state, notice })` for
view_prepared / view_delivered / view_refused alike. `prompt: message` (the operator's own
turn) is kept; redaction roll-ups kept; the `log()` main-log channel is pre-existing
deliberate design for the durable app log and was left alone (receipts = journal rows).
The ~30.9k stored answer chars/turn measured in A0.2 drop to ~200–600. Tests:
`test/view-receipt-a3.test.js` (4 tests incl. mutation control restoring the view copy).

### Item 6 — F-46e: each fact recorded once
`control/conductor-delegation.js`: `delegation_requested` now records `prompt: ""` — the
objective and task_id ride every row via the base fields and are what that row states
before any write happens; `prompt_written` records the prompt (its purpose); `answered`
records `prompt: ""` and the answer. The dead `rawPrompt` computation was removed. A
REFUSED write keeps its prompt copy on `write_refused` — for a refusal that row is the only
record of what was attempted (tested). Tests: `test/delegation-record-once-a3.test.js`
(4 tests incl. 2 mutation controls proving each restored copy is caught by the once-rule).

## WITHDRAWN finding: "store round-trip mojibake" (not real — withdrawn on measurement)

This section previously reported a "store round-trip mojibake" defect and an ASCII-only caveat
on the echoed-prefix rule. BOTH ARE WITHDRAWN: the finding was not real. It was the same
PowerShell console CP1252 decoding artifact correctly identified for `OPERATOR-INSTRUCTIONS.log`,
then mis-attributed to the store. Measured by the reviewer: the projection holds 62 correct
U+2014 em dashes, zero U+00E2, zero U+00A0; and an em dash, "é", braille and an emoji written
through `journal-store.py` and read back are byte-identical. The original "evidence" — NBSP-family
chars summing exactly to the braille count — is simply what a clean UTF-8 file looks like through
a CP1252 console, because each braille char carries one A0 byte.

The stated consequence was also wrong: the echoed-prefix rule was tested against the real em-dash
prompt and removed all 81 characters correctly, so it does NOT fire only for ASCII and the
ASCII-only caveat is struck. This section is kept (not silently deleted) so the withdrawal and the
measurement behind it stay on the record.

## What was NOT done (plainly)

- The two stale tests WERE edited — but only after the operator lifted the no-edit rule for
  exactly those two assertions and nothing else in either file (see "The two stale tests — FIXED"
  above). The "0 fail" hold is now met: 1313/1313/0.
- The "store mojibake defect" was NOT fixed because it was NOT a defect — that finding is
  withdrawn on measurement (see "WITHDRAWN finding" above).
- "Thinking..." status lines, ANSI sequences (none observed), and wrapped echoes were NOT
  removed — only the three authorized rules were implemented.
- The `log()` main-log view copy was NOT changed (pre-existing design, not a journal receipt).
- No gate is submitted; no reviewer evaluation is requested; no PASS status is asserted anywhere.

## Exit integrity

- Read-only: all 9 snapshotted files MATCH entry hashes byte-for-byte, incl.
  `main.js` 218,002 B sha256=43d79f5c…95d2b35 (never opened at any point) — `hashes.txt`.
- Changed (authorized): `control/workspace-journal.js` 22,820 B sha256=acbf56ab…528107;
  `control/conductor-view.js` 19,197 B sha256=6e1bcc39…3171c; `control/conductor-delegation.js`
  16,332 B sha256=5fe9c13d…3bc8a. New test files: 5, hashed in `hashes.txt`.
- `git status` entry→exit delta (`git-status-exit.txt` vs `git-status-rerun.txt`): EXACTLY
  the 5 new test files. Nothing else appeared, disappeared, or changed tracking state.
- Correction pass (this file's later amendment, under operator authorization): the two stale
  tests named above were edited — exactly the two revoked assertions, nothing else in either
  file. Both are UNTRACKED, so this is a content-only change with ZERO git tracking-state delta:
  `git-status-correction.txt` is line-for-line identical to the prior `git-status-exit.txt`
  (both files were already `??`, so editing content moves neither `git status --short` nor
  `git diff --stat`). New hashes for the two edited files — and re-verification that all 9
  read-only files (incl. `main.js`) and the 3 A3-changed control files still MATCH byte-for-byte
  — are in `hashes-correction.txt`. The single diffstat byte difference,
  `evidence/gate5/screenshots/shell-grid-rendered.png` 264437 -> 264523, is the documented render
  artifact that `shell/tests/test_render.py` (H-17) rewrites on every successful shell-suite run;
  re-running the suite (as instructed) regenerated it. It is not source, not in the read-only set,
  and its tracking state is unchanged. (The operator's message cited 12 read-only files; the set
  pinned in `hashes.txt`/`hashes-correction.txt` is these 9 — incl. `main.js` and both mutation
  baselines `control/workspace-journal-before-f46b.js` and `control/conductor-delegation-before-f46e.js`.)

## Evidence index (all under `evidence/A3-LOOP/`)

`quiescence.txt`, `entry-pins.txt`, `git-status.txt`, `REPORT.md` (first attempt, stopped —
superseded by this file); `quiescence-rerun.txt`, `entry-pins-rerun.txt`,
`git-status-rerun.txt`, `baseline-js.txt`, `baseline-python.txt`, `baseline-shell.txt`,
`baseline-text.txt`, `fastcheck-item1.txt` (19/19), `fastcheck-item2.txt` (112/112),
`fastcheck-items3456.txt` (prior-run intermediate: 135 pass / 2 attributed stale fails —
superseded by the post-fix `js.txt`), `fastcheck-text-integrity.txt` (4 passed).
Post-fix re-run (this correction pass; pytest with `-q` to match the baselines byte-for-byte):
`js.txt` (1313 tests / 1313 pass / 0 fail), `python.txt` (2746 passed, 3 skipped, 12 subtests
passed), `shell.txt` (323 passed, 34 subtests passed), `text.txt` (4 passed),
`hashes-correction.txt` (read-only re-verification + the 2 edited test files),
`git-status-correction.txt`. The prior-run `hashes.txt` and `git-status-exit.txt` are kept.
Environment: node v24.20.0; `py -3.12` = Python 3.12.10, pytest 9.0.2, pytest-subtests 0.15.0,
anyio 4.12.1.
Operator instructions: `evidence/OPERATOR-INSTRUCTIONS.log` (both run instructions verbatim, UTC).

BUILDER CLAIM: no gate is submitted for reviewer evaluation and no PASS status is asserted.
