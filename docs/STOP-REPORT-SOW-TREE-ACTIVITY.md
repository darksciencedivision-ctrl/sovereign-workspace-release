# STOP REPORT — protected SOW tree changed externally during REM-03 T3
#
# utc: 2026-08-22T23:15:56.3766075Z
# producer: ox-alpha REM03

## 1. Condition (FACT)

While running the full README suite after applying the operator-approved v2 tokens (T2, 34 changed
lines), 	est_zz_evidence.TestZZFilesystemWatch.test_no_writes_to_protected_roots FAILED:
4 events inside the PROTECTED tree D:\multi model terminal app\...sovereign-orchestration-workspace
during the suite window - .orchestration-mutation.lock ADDED / dir MODIFIED / lock REMOVED /
dir MODIFIED under 	ools\mutation\.
FACT[evidence/rem03/suite-run1-failed-h12-external-write.txt] preserves the full run (sha256
ed1644bfe9010b7dd72ff902f573db2beb9e972d0dd01df2109c2591b3388fab; test-run.txt NOT overwritten).
Read-only git inspection afterwards (FACT[evidence/rem03/sow-git-external-change.txt], sha256
d0e11b801a024ddfbd6c6e07bf0102912c61af4d517dfa1bca1fc6a3693ac4d3):
HEAD is now 6d23a81082836778ffd46c70151821b467dc7432 where the contract (§3.1), the SOW
INSTALL-PROVENANCE and the Gate 2/3/5 captures record ad029e7; tracked files
	ools/mutation/orchestration_mutations.js (+7/-1, mtime 2026-08-22T23:12:05Z) and
docs/loop/LOOP_STATE.json are modified; two untracked docs appeared. None of this was written by
this session: the builder's writes are confined to Production Workspace\; the session fs-watch
window (19:33:13Z..21:41:36Z) closed with events=0 before these host changes.

## 2. Exact requirement conflict

Gate 5 closing evidence requires the three manifest diffs and the SOW git-body comparison to be
empty against the Phase-0/Gate-era baselines (v1.2 §12 A-1, directive C-3/C-4). The baselines no
longer describe this tree: HEAD moved and tracked content changed. Re-running the suite cannot fix
this - any closeout comparison will report differences for as long as the external state stands,
and re-baselining a protected root is an operator decision, never a builder inference.
AGENTS.md section 13 makes this a mandatory STOP ("protected-source write required or integrity
changed"); the Gate 5 work order names it PROTECTED_GIT_STATE_CHANGED.

## 3. What DID complete before the stop

- Operator decision applied: --text-muted #9aa7bd per option 1 (FACT[evidence/OPERATOR-INSTRUCTIONS.log]
  entry 2026-08-22T23:01:33.2358027Z). T1 pinned docs/THEME-BASELINE-v2.md (sha256
  35311af375186654820866119ac6bfbbaeb8cfe88c8803ad5a86130204e1ba5b); T2 applied to
  shell/static/app.css (34 lines +17/-17, FACT[evidence/rem03/linecount.txt], new sha256
  329a52a175da7ccb37909b5fbfa009dd2f444a9f4d2a1b748ee86c2080ecb8ab; baseline copy in
  evidence/rem03/before/app.css).
- H-16 PASSES on v2: single-module render probe ran all five render tests OK, including
  	est_light_theme_contrast. The suite failure is NOT theme-related.
- H-17 also passed (its Edge lookup uses
  HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe, which exists; an earlier
  "key absent" reading was this builder's probe error omitting CurrentVersion - recorded as a
  superseded draft observation, no artifact ever cited it).

## 4. Bounded operator options

1. **Quiesce and restore**: pause whichever agent/tooling is writing the SOW live tree, restore it
   to ad029e7 state as captured at Phase 0 (or confirm the current dirty set is acceptable),
   then order resumption; I re-run the suite and the C-3/C-4 comparisons unchanged.
2. **Re-baseline by new order**: authorize fresh manifest-before-* / sow-git-before captures of
   the CURRENT tree as the new comparison base for Gates 5/6 going forward (an explicit operator
   decision; the old baselines stay on disk as history).
3. **Park REM-03/Gate 5**: leave the approved v2 tokens applied (workspace-owned files, unaffected
   by the protected-tree problem) and resume the visual steps once options 1 or 2 land.

## 5. State on disk

Helpers: none running (stopped at the previous closeout; none restarted since). Ports free. No
builder process touches the SOW tree. Ledger key "4c" remains STOP (updated note). Gate 5 remains
at its reviewer STOP entry; "5b" not written. No PASS asserted anywhere.

BUILDER CLAIM: No gate is submitted for reviewer evaluation. No PASS status is asserted by the builder.