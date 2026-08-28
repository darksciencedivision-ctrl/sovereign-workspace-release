# OX-ALPHA-DIRECTIVE-LOOP-01 — Goal-State Completion Loop, SWS-UI-001 v1.2

| Field | Value |
|---|---|
| Contract | SWS-UI-001 v1.2, unchanged. `AGENTS.md` binds in full — this directive adds a control loop, it does not widen any envelope. |
| Basis | Operator instruction in session: all modules are at production baseline, none are being worked on, the SOW-loop writer is stopped, and the remaining SWS-UI work is to run to completion under a goal-state loop with no stage pauses. |
| Authorization | The operator's kickoff sentence, logged verbatim with UTC in `evidence/OPERATOR-INSTRUCTIONS.log`. It carries: STOP-REPORT-SOW-TREE-ACTIVITY **option 2** (fresh REM-03 baselines), stage-pause waiver, and loop authorization. |
| Supersedes | Nothing. `docs/REMEDIATION-03.md` and the Gate 5 directive remain the work definition; this file only sequences them. |
| Loop state | `evidence/loop5/LOOP-LEDGER.jsonl`, append-only, one JSON line per iteration. A fresh session resumes by reading it and the goal check — never from memory. |

## 1. Operating principle

Verify, then act, then verify. Every iteration: run the goal check against the disk, take the **single smallest authorized action** that flips the **first** failing goal, run the goal check again, append one loop-ledger line. No action is ever taken that a currently-failing goal does not require. No goal is ever marked done by recollection — only by the check re-run. The loop ends in exactly one of two states: all goals TRUE (submit candidates, report, claim line) or a STOP report (reason per §5). There is no third exit.

## 2. Goal state — all predicates must be TRUE on disk

| # | Goal | TRUE when (machine-checkable) |
|---|---|---|
| G0 | Session precondition | Gate 5 directive §1 capture written for this session; DECISIONS.md sha256 `bb911905…4869a`; ports 5175/8700/5180 free at start; helpers (watcher, poller, shell) running detached; kickoff logged verbatim in `evidence/OPERATOR-INSTRUCTIONS.log`. |
| G1 | Quiescent tree + REM-03 baselines | SOW HEAD and `status --porcelain` byte-identical across two read-only inspections ≥ 60 s apart; `evidence/manifests/manifest-rem03-before-*.txt` (three roots) and `evidence/rem03/sow-git-rem03-before.*` captured, headers naming the superseded originals. Originals byte-untouched. |
| G2 | Suite green on v2 | `evidence/test-run.txt` from the README command ends `OK`, ≥ 121 tests, run after G1. `shell/BUILD-MANIFEST.txt` regenerated; its entries equal live file hashes; `app.css` = `329a52a1…b8ab` (v2, unchanged — any drift is a STOP, not a fix). |
| G3 | Ledger 4c | `"4c"`: `CANDIDATE`, evidence list with full lowercase sha256 for THEME-BASELINE-v2.md, app.css, linecount, contrast artifacts, test-run.txt, BUILD-MANIFEST.txt. All reviewer-evaluated entries byte-identical. |
| G4 | Visual set on v2 | All exist, non-blank (≠ `f7744eb4…`), taken from the live shell on the v2 theme: `shell-grid-initial` grid PNG; four card PNGs with filename state = live `/api/state` at capture (sovereign READY via keep-run, debate READY via keep-run, sow STOPPED never launched, distillery NOT_STARTED); side-by-side pair (shell grid + SOVEREIGN UI, SOVEREIGN then stopped through the shell); `shell-light-mode` PNG whose background pixel decodes light, exact Edge command recorded; B-7 DOM artifact (four cards, six actions, Distillery Start/Stop/Open/Test disabled); fresh Ollama tag check preceding the sovereign run. |
| G5 | Clean closeout | Shell stopped via its own path; poller/watcher sentinels honoured; fs-watch artifact: `events: 0`, window brackets G1→G4; orphans artifact: no module processes, three ports free. |
| G6 | Ledger 5b | `"5b"`: `CANDIDATE`, listing every G4/G5 artifact plus standing non-visual evidence, hashes full and lowercase. Reviewer entries byte-identical. |
| G7 | Report | `docs/REM-03-REPORT.md` covering 4c and 5b, every substantive sentence tagged, ending with the exact §14 claim line. |

## 3. The loop

```
i = 0
while i < 40:
    i += 1
    state = goalcheck()                      # reads disk only; writes evidence/loop5/goalcheck-i.txt
    if all TRUE: break
    g = first failing goal
    act(g)                                   # the ONE smallest authorized action for g (see §4)
    state2 = goalcheck()
    append LOOP-LEDGER.jsonl: {i, utc, goal: g, action, flipped: state2[g], notes}
    if g unchanged for 2 consecutive iterations with the same action class:
        STOP LOOP_NO_PROGRESS (§5)
submit: report + claim line
```

`goalcheck()` is a builder tool at `evidence/loop5/tools/goalcheck.py` (py -3.12, stdlib only, read-only against the workspace; PNG background decode included). Write it once at G0; it is the loop's only oracle. If goalcheck itself errors, fixing goalcheck is a permitted action and is logged as `goal: G-oracle`.

## 4. Action envelope per goal — nothing outside it

G0: evidence writes + detached helper starts only. G1: read-only inspections + new capture files. G2: run the suite; regenerate BUILD-MANIFEST via the suite's own rule; **no source edits** — a failing product test is a STOP (`LOOP_PRODUCT_DEFECT`), not a repair. G3/G6: the one new ledger key each, all other entries asserted byte-identical before write. G4: HTTP calls through the shell's own routes (H-2 headers), headless-Edge captures, keep-runs stopped through `/api/stop`; SOW never launched; module launches only via the startup-test path. G5: sentinel files + verification reads. G7: the report. All evidence files: `# utc:` + `# producer: ox-alpha LOOP-01` headers, full lowercase hashes, append-only supersession. Retry rule: any transient failure (HTTP timeout, Edge non-zero exit) gets exactly one retry; the second failure is logged and counts toward no-progress.

## 5. STOP conditions — unchanged from AGENTS.md §13, plus

`LOOP_NO_PROGRESS` (same goal, same action class, no flip, twice) · `LOOP_PRODUCT_DEFECT` (any test in the suite fails for a product reason) · `PROTECTED_GIT_STATE_CHANGED` / `PROTECTED_SOURCE_CHANGED` (the tree moves again — name the files, do not rebaseline a second time without a new operator instruction) · iteration 40 reached. A STOP writes `docs/STOP-REPORT-LOOP-01.md` with the loop ledger tail, 2–3 bounded options, closes helpers per §14, and ends with the no-gate claim line.

## 6. What this loop may never do

Write `PASS` anywhere. Edit `shell/**`, any directive, any review, `DECISIONS.md`, `AGENTS.md`/`CLAUDE.md`. Touch the four protected trees except read-only. Launch SOW. Re-interpret a goal to make it pass ("close enough" is FALSE). Exceed one rebaseline. Treat its own goalcheck output as evidence of anything goalcheck did not actually read from disk this iteration.

## 7. Exit

On all-goals-TRUE: `docs/REM-03-REPORT.md`, then the final message — iteration count, goals table with the artifact+hash that proves each, deviations, open risks (carried: light-theme dot ratios; H-15 nested keys) — ending:

`BUILDER CLAIM: Gate 4c and Gate 5b are CANDIDATEs for reviewer evaluation. No PASS status is asserted by the builder.`

(On any STOP: the no-gate claim line instead. The reviewer evaluates 4c and 5b together; the operator's Gate 6 promotion follows the reviewer's verdict.)
