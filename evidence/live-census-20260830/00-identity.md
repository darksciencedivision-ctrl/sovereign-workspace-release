# utc: 2026-08-30T03:31:33Z
# producer: grok-opencode LIVE-CENSUS-20260830
# host: DESKTOP-03PTABH

# LIVE-CENSUS-20260830 Phase 0 — identity

LIVE_WORKTREE: AMBIGUOUS

## 1. Host

- utc_captured: 2026-08-30T03:26:04.0747801Z
- utc_written: 2026-08-30T03:31:33Z
- COMPUTERNAME: DESKTOP-03PTABH
- USERNAME: Sslaw
- USERPROFILE: C:\Users\Sslaw
- OS Caption: Microsoft Windows 11 Home
- OS Version: 10.0.26200
- BuildNumber: 26200

## 2. Windows theme

- HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize AppsUseLightTheme = 0 (dark)

## 3. Python

- `py -3.12 --version`: Python 3.12.10
- `py -3.12` resolved executable: C:\Users\Sslaw\AppData\Local\Programs\Python\Python312\python.exe
- `py -0p`:
  - V:3.14 *        C:\Users\Sslaw\AppData\Local\Python\pythoncore-3.14-64\python.exe
  - V:3.13          C:\Users\Sslaw\AppData\Local\Programs\Python\Python313\python.exe
  - V:3.12          C:\Users\Sslaw\AppData\Local\Programs\Python\Python312\python.exe
  - V:3.10          C:\Users\Sslaw\AppData\Local\Programs\Python\Python310\python.exe
  - V:Astral/CPython3.11.16 C:\Users\Sslaw\AppData\Roaming\uv\python\cpython-3.11.16-windows-x86_64-none\python.exe
- bare `python --version`: Python 3.14.6
- `where python`:
  - C:\Python314\python.exe
  - C:\Users\Sslaw\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe
  - C:\Users\Sslaw\AppData\Local\Programs\Python\Python312\python.exe
  - C:\Users\Sslaw\AppData\Local\Python\bin\python.exe

## 4. Node / npm

- `node -v`: v24.16.0
- `npm -v`: 11.17.0
- `where node`: D:\Program Files\nodejs\node.exe
- `where npm`: D:\Program Files\nodejs\npm ; D:\Program Files\nodejs\npm.cmd ; C:\Users\Sslaw\AppData\Roaming\npm\npm ; C:\Users\Sslaw\AppData\Roaming\npm\npm.cmd

## 5. GPU

- nvidia-smi present
- name: NVIDIA GeForce RTX 5060 Ti
- memory.used: 2148 MiB
- memory.total: 8151 MiB
- driver_version: 610.74

## 6. Ollama

- `ollama --version`: client version is 0.33.2 ; warning: could not connect to a running Ollama instance
- GET http://127.0.0.1:11434/api/tags: not listening (Unable to connect to the remote server)
- no pull performed

## 7. Listening ports (Listen state)

All of the following had no Listen owner at capture:

- 5175 none
- 5180 none
- 5183 none
- 5184 none
- 8700 none
- 8765 none
- 11434 none
- 17890 none

No running module image path available to corroborate LIVE_WORKTREE.

## 8. Trees (§1)

### T-PW — D:\Product Software\Production Workspace

- exists: True (dir)
- dir LastWriteTimeUtc: 2026-08-27T19:27:50.1862193Z
- git: False
- git -C status verbatim: fatal: not a git repository (or any of the parent directories): .git
- shell\src\__main__.py: exists sha256=b64930cd673cdf4e37867b6667ea3b27c0d7aca92aef8d1a0aa759b1787df582 write=2026-08-21T05:14:03.0999138Z
- shell\src\supervisor.py: exists sha256=bb09c62b2388229fcd729381d4f10cd1eb307cf9e7a74fc935ce3c32a3ae1fc7 write=2026-08-21T05:10:16.6505350Z
- shell\src\server.py: exists sha256=743ecd47027ba88a95d03f6e9dd2b420fae620a8ad25f50e9a8068529aea7deb write=2026-08-25T19:20:26.3533209Z
- Start-Shell.ps1: exists sha256=44ec73ba5270fc022629c4e34d4b77a85864d9620fa29e0d8a3ed53e84b54914 write=2026-08-25T04:43:13.6249358Z size=5122
- newest files (exclude .venv/node_modules/__pycache__/.git): 2026-08-29T05:45:43.1848225Z modules\sovereign\runtime\sovereign.db

### T-PS — D:\Product Software

- exists: True (dir)
- dir LastWriteTimeUtc: 2026-08-27T23:02:20.1779656Z
- git: False
- git -C status verbatim: fatal: not a git repository (or any of the parent directories): .git
- Start-Sovereign.ps1 at this root: MISSING
- Sovereign Workspace.bat at this root: MISSING
- newest top-level file: 2026-08-27T23:29:04.2128013Z SOVEREIGN_RESET_BASELINE_20260827T193540Z.zip

### T-RW — D:\producttion software 2\release-worktree

- exists: True (dir)
- dir LastWriteTimeUtc: 2026-08-30T03:16:48.4020818Z
- git: True
- HEAD short: 8d9f5d2
- HEAD full: 8d9f5d2415599eeb0b71dc85a25a36469b41641e
- branch: main
- porcelain_count: 1
- dirty: ?? modules/sow/docs/evidence/receipts/SHELL-LIVE-READY.json
- log -1 subject: H: regenerate provenance, identity and release manifest (SEAL)
- log -1 date: 2026-08-29 22:07:31 -0500
- shell\src\__main__.py: exists sha256=b64930cd673cdf4e37867b6667ea3b27c0d7aca92aef8d1a0aa759b1787df582 write=2026-08-28T01:47:24.7500926Z
- shell\src\supervisor.py: exists sha256=acb266cf0c2461df0a1419e5ebc828a627be910a9b884fa0c70b706623c7f214 write=2026-08-30T02:40:28.1858095Z
- shell\src\server.py: exists sha256=18ef213e594692c8c0f513854d8826818c49b87eb0f58bc465182ed8ce9c151b write=2026-08-30T02:40:28.1641674Z
- Start-Shell.ps1: exists sha256=bd95eff8cb30d4d7914565d23ff75b78781de87ee38478a713b3412bf7b42e97 write=2026-08-29T15:42:10.1500473Z size=5163
- newest files (exclude .venv/node_modules/__pycache__/.git): 2026-08-30T03:18:10.0039420Z shell\BUILD-MANIFEST.txt

### T-R2 — D:\producttion software 2 (parent of T-RW)

- exists: True (dir)
- dir LastWriteTimeUtc: 2026-08-30T00:13:23.2652529Z
- git: False
- git -C status verbatim: fatal: not a git repository (or any of the parent directories): .git
- Start-Sovereign.ps1: EXISTS write=2026-08-30T00:18:37.1160831Z size=8387
- Sovereign Workspace.bat: EXISTS write=2026-08-29T05:55:54.3891357Z size=170
- newest top-level file: 2026-08-30T00:18:37.1160831Z Start-Sovereign.ps1

### T-SOW — D:\multi model terminal app\sovereign-orchestration-workspace

- exists: True (dir)
- dir LastWriteTimeUtc: 2026-08-24T03:52:49.2681104Z
- git: True
- HEAD short: e6fcb89
- HEAD full: e6fcb89984ba50f296a1f4debb6669bfef12f996
- branch: main
- porcelain_count: 4
- dirty: M docs/loop/LOOP_STATE.json ; M docs/registers/UNRESOLVED_ISSUE_REGISTER.md ; ?? docs/evidence/INDEPENDENT_REVIEW_WINDOWS_HOST_20260816.md ; ?? docs/evidence/PHASE19_UNIT10_U339_SUITE_AND_GATE.md
- newest (depth-capped): 2026-08-26T07:05:44.0136428Z .pytest_cache\v\cache\nodeids

### T-DIST-A — D:\Sovereign-Grounded-Distillery

- exists: True (dir)
- dir LastWriteTimeUtc: 2026-08-23T23:20:15.5765707Z
- git: True
- HEAD short: 6cd9886
- HEAD full: 6cd98862bfc28b7b8aef66b722620f3b42ab6eb7
- branch: remediation/release-baseline-v1
- porcelain_count: 0
- newest (depth-capped): 2026-08-23T23:46:33.0859609Z runs\release-baseline\SD_RBR_V1_1_FINAL_REPORT.json

### T-DIST-B — D:\Sovereign Distillery

- exists: True (dir)
- dir LastWriteTimeUtc: 2026-08-28T23:08:13.9148891Z
- git: False
- git -C status verbatim: fatal: not a git repository (or any of the parent directories): .git
- newest (depth-capped): 2026-08-28T23:08:13.9108856Z SOV-CPI-BUILD-DIRECTIVE-v1.0.md

### T-DEB — D:\Debate table

- exists: True (dir)
- dir LastWriteTimeUtc: 2026-08-19T21:20:10.0564885Z
- git: True
- HEAD short: d7be335
- HEAD full: d7be33579c0f986db74c0b221b5bdf06a9d280df
- branch: master
- porcelain_count: 2
- dirty: M config.json ; ?? scripts/run-debate.ps1
- newest (depth-capped): 2026-08-19T21:20:09.9974808Z config.json

### T-TPB — D:\Token Piggy Bank

- exists: True (dir)
- dir LastWriteTimeUtc: 2026-08-27T04:04:46.6431373Z
- git: True
- HEAD short: 6972194
- HEAD full: 6972194cd5613627db3943732028c54d69bf5893
- branch: main
- porcelain_count: 4
- dirty: M Start-SovereignTokenCenter.ps1 ; M Start-TokenPiggyBank.ps1 ; ?? AI-BUILD-HANDOFF.md ; ?? Start-SovereignTokenCenter-Full-Source.md
- newest (depth-capped): 2026-08-28T22:17:51.1505798Z data\piggybank.sqlite

### T-SOV1 — D:\Sov 1

- exists: True (dir)
- dir LastWriteTimeUtc: 2026-08-14T13:17:09.5835213Z
- git: False
- git -C status verbatim: fatal: not a git repository (or any of the parent directories): .git
- newest (depth-capped): 2026-08-24T06:07:04.6036647Z SOVEREIGN_PRODUCT_COMPLETION_WORK\Test-Sovereign.ps1

### T-BASE — D:\SOVEREIGN_BASELINE_20260827

- exists: True (dir)
- dir LastWriteTimeUtc: 2026-08-27T23:07:01.5939348Z
- git: False
- git -C status verbatim: fatal: not a git repository (or any of the parent directories): .git
- newest (depth-capped): 2026-08-27T23:07:00.5541011Z VERIFICATION\PACKAGING_RECORD.json

### T-RESET — D:\SOVEREIGN_RESET_BASELINE_20260827T193540Z

- exists: True (dir)
- dir LastWriteTimeUtc: 2026-08-27T19:47:32.7346331Z
- git: False
- git -C status verbatim: fatal: not a git repository (or any of the parent directories): .git
- newest (depth-capped): 2026-08-27T19:49:02.1249738Z SOURCE_MANIFEST.sha256

### T-HOME — C:\Users\Sslaw + Desktop + Downloads

- profile exists; Desktop exists; Downloads exists
- none are git repos
- directive on disk: C:\Users\Sslaw\Downloads\OX-GROK-DIRECTIVE-LIVE-CENSUS-20260830.md write=2026-08-30T03:25:23.0406739Z size=20793
- paste file: C:\Users\Sslaw\Downloads\OX-GROK-LIVE-CENSUS-PASTE.txt write=2026-08-30T03:25:41.0066704Z size=1013
- Desktop: no SOVEREIGN/OX-GROK/Start-Sovereign/BASELINE filenames at top level
- Start-Sovereign.ps1 not found at Desktop or Downloads top-level

## 9. Launch-script search (N-03)

Unbounded `Get-ChildItem -Path D:\,C:\Users\Sslaw -Filter Start-Sovereign.ps1 -Recurse` timed out at 120s. Recorded as incomplete. Targeted recurse on T-PS, T-R2, T-SOV1, T-BASE, T-RESET, Desktop, Downloads, Documents completed.

### Start-Sovereign.ps1 hits (targeted; not exhaustive on all of D:\)

Custody-root launcher (T-R2):

- 2026-08-30T00:18:37.1160831Z 8387 D:\producttion software 2\Start-Sovereign.ps1

Module copies (not custody-root):

- D:\Product Software\Production Workspace\modules\sovereign\Start-Sovereign.ps1
- D:\producttion software 2\release-worktree\modules\sovereign\Start-Sovereign.ps1
- additional copies under release-planning\audit-codex, release-planning\bundles, D:\Sov 1\RELEASE_*, D:\SOVEREIGN_RESET_BASELINE_20260827T193540Z\...

No `D:\Product Software\Start-Sovereign.ps1`.

### Sovereign*.bat hits (targeted)

- 2026-08-29T05:55:54.3891357Z 170 D:\producttion software 2\Sovereign Workspace.bat
- on-disk content: `cd /d "D:\producttion software 2\release-worktree"` then `powershell ... .\Start-Shell.ps1`

### SOVEREIGN_*BASELINE*.zip hits (targeted; hashes deferred to Q06)

- D:\Product Software\SOVEREIGN_RESET_BASELINE_20260827T193540Z.zip
- D:\producttion software 2\SOVEREIGN_RAW_SOURCE_BASELINE_20260827.zip
- D:\producttion software 2\SOVEREIGN_RESET_BASELINE_20260827T193540Z.zip
- D:\producttion software 2\SOVEREIGN_RESET_BASELINE_20260827T193540Z - Copy.zip
- D:\producttion software 2\SOVEREIGN_SYSTEM_BASELINE_20260827.zip
- D:\SOVEREIGN_BASELINE_20260827\SOVEREIGN_RAW_SOURCE_BASELINE_20260827.zip
- D:\SOVEREIGN_BASELINE_20260827\SOVEREIGN_SYSTEM_BASELINE_20260827.zip
- D:\SOVEREIGN_RESET_BASELINE_20260827T193540Z.zip
- C:\Users\Sslaw\Downloads\SOVEREIGN_v3.1.1_baseline_20260715(1).zip

## 10. LIVE_WORKTREE declaration

Rule applied:

- T-RW exists and contains shell\src\__main__.py and Start-Shell.ps1: True
- T-PW also exists with the same two files: True
- shell\src\supervisor.py SHA-256 T-PW vs T-RW: DIFFER
  - T-PW: bb09c62b2388229fcd729381d4f10cd1eb307cf9e7a74fc935ce3c32a3ae1fc7
  - T-RW: acb266cf0c2461df0a1419e5ebc828a627be910a9b884fa0c70b706623c7f214
- shell\src\server.py hashes also DIFFER
- Start-Shell.ps1 hashes also DIFFER
- shell\src\__main__.py hashes EQUAL

Launch-path evidence (not a silent pick):

- Most recently written Start-* next to a worktree: D:\producttion software 2\Start-Sovereign.ps1 (2026-08-30T00:18:37Z). `$worktree = Join-Path $root 'release-worktree'` → T-RW. Start-Shell.ps1 exists there.
- Sovereign Workspace.bat (only bat found) cds to T-RW.
- T-RW Start-Shell.ps1 write 2026-08-29T15:42:10Z is newer than T-PW Start-Shell.ps1 write 2026-08-25T04:43:13Z.
- T-RW source (supervisor.py / server.py) write 2026-08-30T02:40:28Z is newer than T-PW copies.
- T-PW runtime artifacts were written later than T-PW source: sovereign.db 2026-08-29T05:45:43Z — T-PW was executed after its source freeze.
- No live listener image path to corroborate either tree.

Because both trees look live and supervisor.py hashes differ: LIVE_WORKTREE = AMBIGUOUS.

Census continues on both T-PW and T-RW. Every later answer is labeled with the tree id.

This identity file is written to both:

- D:\producttion software 2\release-worktree\evidence\live-census-20260830\00-identity.md
- D:\Product Software\Production Workspace\evidence\live-census-20260830\00-identity.md

Single authorized append to OPERATOR-INSTRUCTIONS.log: T-RW copy only (`D:\producttion software 2\release-worktree\evidence\OPERATOR-INSTRUCTIONS.log`), because the mutation envelope allows one append and T-RW is the path the on-disk bat/ps1 launchers name.

## 11. Search commands actually run

```
Get-ChildItem -Path D:\,C:\Users\Sslaw -Filter Start-Sovereign.ps1 -Recurse  → TIMEOUT 120s
Get-ChildItem targeted roots -Filter Start-Sovereign.ps1 -Recurse → completed (hits listed §9)
Get-ChildItem targeted roots -Filter Sovereign*.bat -Recurse → 1 hit
Get-ChildItem targeted roots + D:\ + Downloads -Filter SOVEREIGN_*BASELINE*.zip → hits listed §9
```
