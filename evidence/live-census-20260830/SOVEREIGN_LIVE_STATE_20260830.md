# SOVEREIGN LIVE STATE — 20260830

```
LIVE_WORKTREE: AMBIGUOUS
GIT: T-RW 8d9f5d2 dirty=1 | T-PW none
SHELL_START: OK (T-RW) | T-PW NOT_RUN
SHELL_SUITE: Ran 188 tests in 149.913s OK (T-RW)
DEBATE_INSTALLED: T-RW v1.2.1-hardening | T-PW v1.2 Phase 1
SOVEREIGN_PROVENANCE: T-RW MATCH | T-PW CROSS_PRODUCT_HASH
ADAPTER_PORTABILITY: HOST_ABSOLUTE
TOKENCENTER_LISTENER: none
OLLAMA: down (disk tags present; API not listening)
VRAM_FREE_MIB: 6003
SAFE_TO_DEMO_SHELL: yes — T-RW Start-Shell.ps1 -NoBrowser served / and /static/app.js 200 on 127.0.0.1:5180 in dark mode after 188/188 tests OK; Ollama is down.
SAFE_TO_DISTRIBUTE: no
```

FACT[evidence/live-census-20260830/00-identity.md]

## 0. LIVE_WORKTREE declaration

LIVE_WORKTREE = AMBIGUOUS. FACT[evidence/live-census-20260830/00-identity.md]

T-RW `D:\producttion software 2\release-worktree` and T-PW `D:\Product Software\Production Workspace` both contain `shell\src\__main__.py` and `Start-Shell.ps1`. `shell\src\supervisor.py` hashes differ. FACT[evidence/live-census-20260830/00-identity.md]

On-disk launchers (`Sovereign Workspace.bat`, `Start-Sovereign.ps1`) cd/join to T-RW. FACT[evidence/live-census-20260830/00-identity.md]

T-PW still has runtime DB writes 2026-08-29 showing it was executed after its source freeze. FACT[evidence/live-census-20260830/00-identity.md]

No live module listener existed at identity capture to corroborate either tree. FACT[evidence/live-census-20260830/00-identity.md]

## 1. Host facts (python, node, gpu, theme, listeners)

FACT[evidence/live-census-20260830/00-identity.md]: host DESKTOP-03PTABH, user Sslaw, Windows 11 Home 10.0.26200, AppsUseLightTheme=0.

FACT[evidence/live-census-20260830/00-identity.md]: py -3.12 = Python 3.12.10 at `C:\Users\Sslaw\AppData\Local\Programs\Python\Python312\python.exe`. Bare python = 3.14.6.

FACT[evidence/live-census-20260830/00-identity.md]: node v24.16.0 at `D:\Program Files\nodejs\node.exe`; npm 11.17.0.

FACT[evidence/live-census-20260830/00-identity.md]: NVIDIA GeForce RTX 5060 Ti 2148/8151 MiB driver 610.74.

FACT[evidence/live-census-20260830/00-identity.md]: ollama client 0.33.2, daemon not listening on 11434.

FACT[evidence/live-census-20260830/00-identity.md]: ports 5175, 5180, 5183, 5184, 8700, 8765, 11434, 17890 all free at identity and after shell/distillery stop.

## 2. Tree census

| ID | Path | exists | git | note |
|---|---|---|---|---|
| T-PW | D:\Product Software\Production Workspace | yes | no | packaged workspace; older shell hashes |
| T-PS | D:\Product Software | yes | no | custody parent; reset zip hash MISMATCH vs cited |
| T-RW | D:\producttion software 2\release-worktree | yes | 8d9f5d2 dirty 1 | launch target |
| T-R2 | D:\producttion software 2 | yes | no | Start-Sovereign.ps1 + bat |
| T-SOW | D:\multi model terminal app\sovereign-orchestration-workspace | yes | e6fcb89 dirty 4 | |
| T-DIST-A | D:\Sovereign-Grounded-Distillery | yes | 6cd9886 clean | |
| T-DIST-B | D:\Sovereign Distillery | yes | no | |
| T-DEB | D:\Debate table | yes | d7be335 dirty 2 | |
| T-TPB | D:\Token Piggy Bank | yes | 6972194 dirty 4 | |
| T-SOV1 | D:\Sov 1 | yes | no | |
| T-BASE | D:\SOVEREIGN_BASELINE_20260827 | yes | no | |
| T-RESET | D:\SOVEREIGN_RESET_BASELINE_20260827T193540Z | yes | no | |

FACT[evidence/live-census-20260830/00-identity.md]

## 3. Module pins (table)

| module | T-RW | T-PW |
|---|---|---|
| sovereign | provenance MATCH 150e518e…; SPA src+dist; db 81920 B | provenance CROSS_PRODUCT 620e8459…; dist only; db 90112 B |
| debate | v1.2.1-hardening | v1.2 Phase 1 |
| sow | package.json electron ^43.4.1 | package.json electron ^31.0.0 (= T-SOW hash) |
| distillery | serve.py 3605 B present | serve.py 2217 B present |
| tokencenter | piggybank.py 38935 B CSRF | piggybank.py 36059 B CSRF nonce |

FACT[evidence/live-census-20260830/00-identity.md] FACT[evidence/live-census-20260830/06-zip-hashes.md]

## 4. Answers that changed the Aug 30 ZIP handoff

Do not treat the ZIP handoff as live-disk fact. Re-derived deltas:

FACT[evidence/live-census-20260830/00-identity.md]: two live trees, not one; supervisor hashes differ.

FACT[evidence/live-census-20260830/06-zip-hashes.md]: T-PS reset zip is a03baa10… not 00ae9eef….

FACT[evidence/live-census-20260830/06-zip-hashes.md]: 620e8459… is Distillery enterprise; T-RW sovereign provenance was corrected to 150e518e…; T-PW still has the Distillery hash.

FACT[evidence/live-census-20260830/29-shell-start-T-RW-retry.txt]: `/static/app.js` 200 — DEFECT-G5-1 is not live on T-RW.

FACT[evidence/live-census-20260830/21-adapters.md]: T-RW adapter roots already point at T-RW, not T-PW.

FACT[evidence/live-census-20260830/30-shell-suite-T-RW.txt]: suite is 188 OK, not the stale 129 OK in evidence/test-run.txt.

INTERPRETATION: T-RW is the operator launch path; T-PW is the older packaged workspace that still holds runtime state. Falsifier: a running module image path under T-PW.

## 5. Still broken on this host

FACT[evidence/live-census-20260830/00-identity.md]: Ollama not running.

FACT[D:\Product Software\Start-SovereignTokenCenter.ps1]: custody Token Center launcher has no sibling piggybank.py.

FACT[evidence/live-census-20260830/00-identity.md]: T-PW INSTALL-PROVENANCE still CROSS_PRODUCT_HASH.

FACT[evidence/live-census-20260830/21-adapters.md]: distillery/tokencenter argv hard-code C:\Users\Sslaw python.

FACT[evidence/live-census-20260830/00-identity.md]: SYSTEM_MANIFEST vs PACKAGE_MANIFEST model-role mismatch (challenger/synthesizer).

FACT[evidence/GATE-LEDGER.json]: gate 5 STOP; 19 CANDIDATE; G26 NOT_RUN(CONDUCTOR_LAUNCH_PROCESS_DEATH).

FACT[evidence/live-census-20260830/00-identity.md]: README still names Debate v1.2 Phase1 zip while T-RW debate is v1.2.1-hardening.

FACT[evidence/live-census-20260830/00-identity.md]: llamacpp on T-RW is a placeholder path; 5183 empty.

FACT[evidence/live-census-20260830/00-identity.md]: Expand-Archive of Debate/Sovereign zips would nest.

NOT_RUN: T-PW shell start; T-PW and T-RW debate pytest NOT_RUN(TIME).

## 6. Safe to start vs not safe to start

SAFE to start T-RW shell with `.\Start-Shell.ps1 -NoBrowser` from `D:\producttion software 2\release-worktree` (or custody `Start-Sovereign.ps1 -NoBrowser`). FACT[evidence/live-census-20260830/29-shell-start-T-RW-retry.txt]

NOT safe to start: Distillery compute/training; live conductor against a paid provider; Ollama pull; T-PS Token Center bat/ps1 cold-start (missing piggybank.py); treating T-PW as the same generation as T-RW.

SAFE_TO_DISTRIBUTE remains no.

## 7. Exact next command for the operator

From an elevated-not-required prompt, dark mode already set:

```
cd /d "D:\producttion software 2"
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-Sovereign.ps1 -NoBrowser
```

RECOMMENDATION: start Ollama before any model-backed module demo. Falsifier: `GET http://127.0.0.1:11434/api/tags` succeeds.

RECOMMENDATION: pick one LIVE_WORKTREE in a signed operator line before mutating product source. Falsifier: operator names T-PW or T-RW.

BUILDER CLAIM: No gate is submitted for reviewer evaluation. No PASS status is asserted by the builder.
