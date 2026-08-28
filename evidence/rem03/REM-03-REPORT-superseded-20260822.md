# REM-03 REPORT — v2 theme applied and verified; session STOPPED on external protected-tree writes

# utc: 2026-08-22T23:25:22.1066972Z
# producer: ox-alpha REM03
# supersedes: docs/REM-03-REPORT.md sha256 a69a40e0d72822e76be27779fd3d19447a52ef48fcac5fd4cebc7710edf81c07
#             (that version documented the contrast stop only; it is preserved in no gate entry and
#              its content is carried forward and extended here)

## 1. Authorization chain

FACT[evidence/OPERATOR-INSTRUCTIONS.log] three verbatim entries govern this session: 2026-08-22T21:15:09Z
(REM-03 authorized, apply before visual steps, helpers detached), 2026-08-22T23:01:33Z (option 1
selected: --text-muted #9aa7bd, every other v2 value per the extraction), plus the earlier
19:24:02Z visual-re-run authorization. INTERPRETATION With the stop below, neither "4c"
CANDIDATE nor "5b" exists; the operator-named keys were not reached.

## 2. T1 — THEME-BASELINE-v2 pinned (complete)

FACT[docs/THEME-BASELINE-v2.md] (sha256 35311af375186654820866119ac6bfbbaeb8cfe88c8803ad5a86130204e1ba5b)
pins the shell to SOW's renderer palette (pps\desktop\renderer\index.html embedded style block,
sha256 bcb30769491a928f74ace92519cd97848a387f7efa09e39434b01b934f9ba4a3; full extraction with
file:line cites in FACT[evidence/rem03/sow-token-extraction.txt]). The muted substitution is
recorded there as an OPERATOR DECISION (#9aa7bd, sb-prov/.ins-sum secondary text, index.html:90,107;
7.08:1 panel / 7.94:1 bg) replacing SOW's canonical dim-label #6b7687 (3.75:1 - below H-16's 4.5:1,
FACT[evidence/rem03/contrast-preview.txt]), chosen by the operator after
docs/STOP-REPORT-REM-03.md; not a builder invention. Light block carried forward unchanged.
Radius recorded as SOW's actual 6px (the order guessed 2-4px); --font becomes ui-monospace,
monospace; --mono untouched.

## 3. T2 — token swap applied within envelope (complete)

FACT[evidence/rem03/linecount.txt]: 34 changed lines (+17/-17) of <= 40 permitted - fifteen :root
token lines plus the two header contrast-figure comment lines; nothing else in shell/** changed;
shell/tests/test_render.py untouched. Baseline copy FACT[evidence/rem03/before/app.css]
(sha256 13875bf113d8a0e68e97303fafb674d9ddd89d773dca6f30b8738ad59f505037 = the Gate-4b PASS value);
new app.css sha256 329a52a175da7ccb37909b5fbfa009dd2f444a9f4d2a1b748ee86c2080ecb8ab.

## 4. T3 — render proofs pass; full suite blocked by external writes; STOP

Single-module probe first: all five render tests OK - including 	est_light_theme_contrast (H-16
PASSES on v2: dark text pairs 12.51 / 11.16 / 7.08 / 9.42 / 8.61 / 6.51) and
	est_rendered_dom (H-17; its Edge lookup reads
HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe which EXISTS - an interim
"key absent" reading was this builder's own probe omitting CurrentVersion; that observation was a
superseded draft, never cited). The FULL README suite then ran 121 tests and FAILED exactly one -
not theme-related: 	est_zz_evidence.test_no_writes_to_protected_roots caught 4 filesystem events
inside the PROTECTED SOW live tree during its window (.orchestration-mutation.lock created and
removed under tools\mutation). Read-only git inspection (FACT[evidence/rem03/sow-git-external-change.txt],
sha256 d0e11b801a024ddfbd6c6e07bf0102912c61af4d517dfa1bca1fc6a3693ac4d3): HEAD has moved
bad029e7 -> 6d23a81082836778ffd46c70151821b467dc7432 and tracked files are modified
(tools/mutation/orchestration_mutations.js +7/-1, mtime 2026-08-22T23:12:05Z; docs/loop/LOOP_STATE.json).
None of this was written by this session (session fs-watch window closed at 21:41:36Z with events=0).
Consequences: test-run.txt NOT overwritten (FACT[evidence/rem03/suite-run1-failed-h12-external-write.txt]
preserves the failed run, sha256 ed1644bfe9010b7dd72ff902f573db2beb9e972d0dd01df2109c2591b3388fab);
Gate 5 C-3/C-4 manifest/git comparisons cannot pass against baselines that no longer describe the
tree -> PROTECTED_GIT_STATE_CHANGED, mandatory stop per AGENTS.md s13. Full analysis:
docs/STOP-REPORT-SOW-TREE-ACTIVITY.md (sha256 5cfa1fd4f70a4cea53586b12a18234ca2d57d0f6b7ac1b9dee813b48157c2726).

## 5. Ledger

evidence/GATE-LEDGER.json key "4c" updated (builder-authored, never reviewer-evaluated): status
STOP with both episodes, eight evidence artifacts, prior_stop_reason retained, superseded ledger
sha256 recorded. Prior file sha256 24da02bd861c8d91c7403a530333b2d4fb6a890c3561b79ebb686ddf3c881052;
new sha256 b2ee9910457916116cb4f786a9d4d308f86f8037daf94438a77e12d36374866e. All other gate entries
byte-preserved (prefix assertion + JSON re-parse + key-order check).

## 6. Closeout state

No builder helpers running (all stopped at the previous closeout; none restarted since this stop).
Ports 5175/8700/5180 free; zero workspace processes at 2026-08-22T23:25:22.1066972Z. No builder process touches any
protected tree. Nothing was reverted: the operator-approved v2 tokens remain applied to the
workspace-owned shell/static/app.css.

## 7. Deviations

- D-a: docs/THEME-BASELINE-v2.md written only AFTER the operator resolved episode 1; during
  episode 1 the extraction stood alone as evidence rather than pinning a self-failing baseline
  (INTERPRETATION).
- D-b: one suite run left FAILED on disk as evidence instead of retrying until green: the failure
  is an external integrity event, not flakiness, and retrying would launder it
  (FACT[evidence/rem03/suite-run1-failed-h12-external-write.txt]).
- D-c: builder probe error (App Paths path missing CurrentVersion) briefly suggested a host fact
  change; corrected before any artifact or claim cited it; recorded here for completeness.

## 8. Open items (operator)

Choose a path in docs/STOP-REPORT-SOW-TREE-ACTIVITY.md section 4: quiesce/restore the SOW tree
and I re-run suite + C-3/C-4 unchanged; or authorize fresh baseline captures of the current tree by
new order; or park REM-03/Gate 5 with v2 tokens applied. Until then Gates 4c/5 stay STOP and no
gate is submitted.

BUILDER CLAIM: No gate is submitted for reviewer evaluation. No PASS status is asserted by the builder.