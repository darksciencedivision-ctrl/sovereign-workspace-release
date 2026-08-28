# Audit F — change/spend/protected-source envelope

## Changed-line budgets

The builder's own files claim Package A 430/1850 and Package B 156/1625 (`evidence/cpm1/linecount-a.txt:33`; `linecount-b.txt:11`). They are not independent computations. The counter has a material blind spot: combined areas use `base=None` (`linecount_cpm1.py:22-27,31-37`), and `spend()` then assigns zero to new files when no baseline is configured (`:71-91`). G121 merely parses those reported files (`goalcheck.py:1338-1341`).

I recomputed added+removed lines with `difflib.unified_diff`, tests/node_modules/pycache excluded, Package A against `before-a` with its endpoint captured by `before-b`, and Package B against `before-b`. Copied modules were compared with the provenance source; copy metadata was excluded.

```text
PACKAGE A
shell/src             79   (adapter.py 8; server.py 2; states.py 69)
shell/static          46   (app.css 4; app.js 42)
shell/modules        111   (distillery.json 49; sow.json 8; tokencenter.json 54)
sow-desktop          368   (including 4 lines of .recovery runtime drift)
sow-control-plane    143   (canonical_registry.py)
distillery            51   (serve.py)
tokencenter            16   (piggybank.py)
TOTAL-A               814 / 1850
```

Excluding the four `.recovery` runtime-state lines gives 810 product lines. Either total is far from 430 but below the aggregate and every per-area cap.

```text
PACKAGE B
sow-adapters          108   (backend.py 42; llamacpp.py 66)
sow-scheduler           5
sow-control+schemas    69   (canonical_registry.py 42; schema 27)
sow-tools+config        0
shell                  44   (logring.py 16; BUILD-MANIFEST 28)
llamacpp.json          53
runtime                 0
TOTAL-B               279 / 1625
```

Package B is below its aggregate cap but **violates the 45-line `llamacpp.json` area cap by 8 lines**. Budgets were kept in separate files/baselines and were not pooled; the defect is undercounting, not pooling.

## Protected trees

I parsed each Band-0 manifest and independently rehashed each listed file, also reporting new/removed paths. For `D:\multi model terminal app`, I used the handover manifest authorized by `evidence/cpm1/scope-handover.md:19-37`; it incorporates exactly the three declared handover changes.

```text
ROOT=D:\Product Software (excluding Production Workspace) baseline=226 seen=226 changed=0 new=0 removed=0 errors=0
ROOT=D:\multi model terminal app                    baseline=9727 seen=9727 changed=0 new=0 removed=0 errors=0
ROOT=D:\Sovereign Distillery                       baseline=227 seen=227 changed=0 new=0 removed=0 errors=0
ROOT=D:\Sov 1                                      baseline=134462 seen=134462 changed=0 new=0 removed=0 errors=0
ROOT=D:\Token Piggy Bank (excluding data/.git)     baseline=60 seen=60 changed=2 new=0 removed=0 errors=0
CHANGED=Start-SovereignTokenCenter.ps1
CHANGED=Start-TokenPiggyBank.ps1
```

The Token manifest pinned both launcher hashes to `0d806419…` (`manifest-cp01-before-token-piggy-bank.excl-data.txt:51-52`). They now both hash to `50e56fe687f2b4a92c40d2d904cfd2ad27c86bbf7ae4b66d04da225de0146f97`, are 2,078 bytes, and have mtimes `2026-08-26T21:48:03Z`. `git -C "D:\Token Piggy Bank" status --porcelain=v1 -uall` reports both as modified; diff summary is 92 insertions/18 deletions. These changes are not declared by the multi-model-terminal handover. I cannot attribute who made them, but the claim “original untouched” is false at audit time.

## Copies and originals

Distillery provenance names `D:\Product Software\SOVEREIGN_DISTILLERY_ENTERPRISE_20260821T011825Z_5ff6f56e\SOURCE_TREE`; independent comparison finds only the copy additions `INSTALL-MANIFEST.txt`, `INSTALL-PROVENANCE.json`, and the recorded 51-line `serve.py`. Both the broader Product Software source baseline and protected `D:\Sovereign Distillery` are clean.

Token provenance (`modules/tokencenter/INSTALL-PROVENANCE.json`) records two copy-only edits. Independent diff shows exactly 14 additions/2 removals in `piggybank.py`: loopback pin plus Host/Origin/CSRF guards. The original `piggybank.py` remains at the Band-0 hash `102fdc6f…` (`manifest…excl-data.txt:56`); the copy hashes `66215be2…`. The *original tree overall* is nevertheless not untouched because of the two launcher modifications above. The copied launchers retain the Band-0 hash and therefore do not carry those later original changes.

## Provider delivery/spend

I scanned 298 non-source run artifacts (`.txt/.json/.jsonl/.md/.log`), excluding baselines, frozen duplicates, tools, and tests, for positive `delivered=true/yes` or `submitted=true/yes`. Output:

```text
FILES_SCANNED 298
POSITIVE_DELIVERY_OR_SUBMISSION_MATCHES 0
```

`evidence/cpm1/8d/spend-log.txt:14-15` records two attempts with `delivered=False submitted=False`; later launch attempts are recorded as pre-turn failures (`:22-24`). This verifies **zero recorded delivered provider turns**. I could not inspect provider billing/account records, so “zero monetary provider spend anywhere” remains unverified outside the workspace record.

**Envelope verdict:** budgets were not pooled and both aggregate caps are met, but claimed totals are materially wrong, Package B breaches a per-area cap, E-7c is violated (Audit B), and one protected original tree is not byte-identical. Envelope integrity therefore fails.
