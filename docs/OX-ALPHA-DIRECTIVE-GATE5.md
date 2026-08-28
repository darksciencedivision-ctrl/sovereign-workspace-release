# DIRECTIVE FOR OX ALPHA (OpenCode) — Gate 5 Execution and Gate 6 Packaging, SWS-UI-001 v1.2

Paste this file verbatim as the first message of a fresh OpenCode session whose working
directory is `D:\Product Software\Production Workspace\`. `AGENTS.md` at that root carries the
standing rules and is loaded automatically; this file is the work order. Read both before any
tool call.

---

## 0. Who you are, what exists, what is left

You are the **builder** for the final verification stage of SWS-UI-001 v1.2. You are not the
operator (sam), not the reviewer (Claude, separate session), and not authorized to decide
whether anything passed.

State on entry (`FACT`, from `evidence/GATE-LEDGER.json`):

| Gate | Status | Meaning |
|---|---|---|
| 0, 1 | `STOP` | `docs/DECISIONS.md` is the void builder-authored file (sha256 `bb911905c68b85f2c8abd5d3d2db8176cbd7a6999f8ed93fd815b4185c14869a`). Operator signature absent. |
| 2, 3, 4 | `PASS` (reviewer) | Install, protected-source integrity, and Gate 4 engineering are accepted. 116 tests, `OK`. Do not re-open them. |
| 5 | `NOT_REACHED` | **Your work.** Real-module verification. |
| 6 | `NOT_REACHED` | Operator promotion. You prepare the package; you do not promote. |

What you must read, in order, before step 1: `BUILD-DIRECTIVE-SWS-UI-001.md` (§7.3, §7.4, §9,
§10, §12), `docs/REVIEW-BUILD-03.md`, `docs/REM-01-STAGE-R3-ROUND2-REPORT.md`,
`shell/src/server.py` (to learn the real route names — do not assume them from this document),
`shell/src/startup_test.py`, `shell/modules/*.json`.

### 0.1 Absolute prohibitions — one violation ends the session

1. Do not create, edit, or delete `docs/DECISIONS.md`. Do not write `sam` or `operator` as author, signer, or approver anywhere.
2. Do not write `"status": "PASS"` into `evidence/GATE-LEDGER.json`. You write `CANDIDATE`, `NOT_REACHED`, or `STOP`. Do not alter the entries for Gates 0–4.
3. Do not modify anything under `D:\Product Software\` outside `Production Workspace\`, nor under `D:\multi model terminal app\`, `D:\Sovereign Distillery\`, or `D:\Sov 1\` (the operator's production SOVEREIGN — see §1a). Reads there use `GIT_OPTIONAL_LOCKS=0` and `PYTHONDONTWRITEBYTECODE=1`.
4. Do not edit `shell/src/**`, `shell/static/**`, `shell/modules/**`, or `shell/tests/**` except as §6 (defect protocol) allows. Gate 5 is verification, not development.
5. Do not install, pull, or delete Ollama models. Do not run `pip`, `npm`, or `install_sow.py`. Do not touch `modules/**` except the runtime-write paths each adapter declares, and only via the shell itself.
6. Do not launch any module by hand. Every module launch in this session goes through the shell's own startup-test path so the evidence is the product's, not yours. Exception: none.
7. Do not open a provider session. `SOW_CONDUCTOR_AUTOLAUNCH=0` is enforced by the adapter; if you ever see a SOW launch without `SHELL_SELFCHECK` in its env keys, stop and report.
8. Do not `git init/commit/push`. Do not run `cmd.exe`, `.cmd`, `.bat`, or `shell=True` from any code you write. PowerShell as your *inspection* tool is fine.
9. Do not resolve ambiguity by guessing. Write `docs/STOP-REPORT-GATE5.md` and stop.

### 0.2 Mandatory closing line of every report and of your final message

```
BUILDER CLAIM: Gate 5 is a CANDIDATE for reviewer evaluation. No PASS status is asserted by the builder.
```

Any summary saying a gate "passed", is "complete", or "done" is a violation. Say "candidate".

---

## 1. Session start — run before anything else

```powershell
Set-Location "D:\Product Software\Production Workspace"
$PSVersionTable.PSVersion                       # record it
(Get-Date).ToUniversalTime().ToString("o")       # every evidence header uses this form
Get-FileHash docs\DECISIONS.md -Algorithm SHA256
py -3.12 --version
Get-NetTCPConnection -State Listen -LocalPort 5175,8700,5180 -ErrorAction SilentlyContinue
Get-Process python,electron,node -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,Path
```

Record all outputs in `evidence/gate5/session-start.txt`.

**Authorization note (this is an operator instruction embedded in the directive, not your
inference):** the operator has waived stage pauses for this session and instructs you to run
Gate 5 even though `DECISIONS.md` is unsigned. You therefore proceed, but you record in every
report that Gates 0/1 remain `STOP` and that the Gate 5 candidate inherits an unsigned
authorization root. If `DECISIONS.md` hash is *not* `bb911905…`, read the file and report the
structural check from `docs/CLAUDE-CODE-DIRECTIVE-REM-01.md` §1 — still without editing it.

If any port 5175/8700/5180 is already listening, or any `python.exe` under `modules\*\.venv`
or any `electron.exe` under `modules\sow` is running, **stop** with `HOST_NOT_QUIESCENT` and
list the PIDs. Do not kill them — they are not yours.

---

## 1a. Session facts established by the operator immediately before this run

`FACT` A production SOVEREIGN instance was running from `D:\Sov 1\SOVEREIGN_PRODUCT_COMPLETION_WORK\` on 127.0.0.1:5175 (PID 9960, started 2026-08-19 16:08 local, argv `…\.venv\Scripts\python.exe -m sovereign_product.server --root "D:\Sov 1\SOVEREIGN_PRODUCT_COMPLETION_WORK" --host 127.0.0.1 --port 5175 --workers 1`). The operator stopped it with its own `Stop-Sovereign.ps1` to free the port for this run. Consequences for you:

- `D:\Sov 1\` is a **protected source**: never read into evidence beyond this paragraph, never write, never launch. It is not the Gate 5 SOVEREIGN; the workspace-owned instance under `modules\sovereign\` is.
- Record in `GATE5-REPORT.md` §2 and `BUILD-REPORT.md` "Contradictions": the builder-authored `docs/DECISIONS.md` states no live SOVEREIGN tree exists on this host; that statement is false. Cite this section. Do not edit `DECISIONS.md`.
- If 5175 is listening at session start, it is most likely that instance restarted; STOP `HOST_NOT_QUIESCENT` as §1 says. Never stop it yourself.
- After C-1 confirms 5175 is free, state that explicitly in your final message so the operator knows it is safe to restart their instance.

## 2. Gate 5 — what must exist when you finish

```
evidence/gate5/
  session-start.txt
  preflight.json                 shell's own pre-flight output (§3)
  model-inventory.txt            Ollama tags vs SOVEREIGN SYSTEM_MANIFEST.json requirements
  startup-sovereign.json         copied from evidence/startup-tests/sovereign-<ts>.json
  startup-debate.json            copied from evidence/startup-tests/debate-<ts>.json
  startup-sow.json               the existing sow-20260821T052050.534Z.json (already valid)
  states-timeline.txt            polled /api state for each module, timestamped, through the run
  orphans-after.txt              proof no managed process survived the session
  theme-contrast.txt             computed contrast ratios for every badge/text token pair
  screenshots/
    shell-grid-initial.png
    card-sovereign-<STATE>.png
    card-debate-<STATE>.png
    card-sow-<STATE>.png
    card-distillery-NOT_STARTED.png
    side-by-side-sovereign.png   (only if SOVEREIGN reached READY — see §4.4)
    shell-light-mode.png
  fs-watch-gate5.txt             H-12 watch covering the whole Gate 5 run
evidence/manifests/
  manifest-final-{product-software,sow,distillery}.txt
  manifest-diff-final-*.txt      (all three must report no differences)
evidence/
  sow-git-final.body, sow-git-final.meta.json, sow-git-body-diff-final.txt
docs/
  GATE5-REPORT.md
  BUILD-REPORT.md                v1.2 §10.2 format, executive summary first, ≤ 12 pages
  AGENTS.md (root)               already present; do not edit
evidence/GATE-LEDGER.json        Gate 5 → CANDIDATE with every file above, full hashes
```

Every evidence file starts with `# utc: <ISO-8601 Z>` and `# producer: ox-alpha GATE5`.

---

## 3. Step A — Pre-flight (read-only, through the shell)

A-1. Start the H-12 watcher for the whole session: `py -3.12 -B shell\tests\_fswatch.py --standalone --out evidence\gate5\fs-watch-gate5.txt` if `_fswatch.py` exposes a standalone mode; if it does not, run it as a small driver script you write under `evidence/gate5/tools/fswatch_driver.py` that imports `FsWatch` from `shell.tests._fswatch`, starts it on the three protected roots, and writes the report on `SIGINT`/exit. Do not modify `_fswatch.py`.

A-2. Start the shell exactly as the README says: `py -3.12 -m shell.src` (port 5180). Capture stdout/stderr to `evidence/gate5/shell-stdout.txt`. Confirm `Get-NetTCPConnection -LocalPort 5180` shows `127.0.0.1` only.

A-3. Read `shell/src/server.py` and write down, in `GATE5-REPORT.md` §1, the exact routes for: shell info, module state list, pre-flight, start, stop, startup test, logs, Distillery status. Cite `server.py:<line>` for each. Use only those.

A-4. `GET` the pre-flight route → `evidence/gate5/preflight.json`. Separately `GET http://127.0.0.1:11434/api/tags` (plain `urllib`, read-only) and compare installed tags against the model assignments in `modules/sovereign/SYSTEM_MANIFEST.json` → `model-inventory.txt` with a line per required tag: `PRESENT` / `MISSING`. Do not pull anything.

A-5. Screenshot the grid before any action → `shell-grid-initial.png`. Screenshot method: `msedge.exe` or `chrome.exe` (whichever `Get-Command` finds) with `--headless=new --disable-gpu --window-size=1600,1000 --screenshot=<abs path> http://127.0.0.1:5180/`. The browser is your tool, not a module launch. Also `--force-dark-mode` off and on for `shell-light-mode.png` later (or emulate `prefers-color-scheme: light` via `--enable-features=WebContentsForceDark` inverse — use whichever flag the installed version honors; record the exact command).

---

## 4. Step B — Real-module startup tests (through the shell, one module at a time)

Run them in this order: **Debate Table, SOVEREIGN, then re-read SOW's existing record.** Never two modules starting concurrently.

For each of Debate and SOVEREIGN:

B-1. Begin polling the module-state route every 2 s into `states-timeline.txt` (append `utc  module  state  reason`).
B-2. Invoke the shell's startup-test route for the module with the "stop after" behavior (default). Send the CSRF nonce and exact `Host`/`Origin` headers the server requires (`server.py` H-2). Record the HTTP status and body.
B-3. Wait until the record file appears in `evidence/startup-tests/<id>-<ts>.json` or the adapter's `timeout_s + grace_s + 10` elapses. Copy it to `evidence/gate5/startup-<id>.json`.
B-4. Screenshot the card in the terminal state reached → `card-<id>-<STATE>.png` (file name carries the actual state, e.g. `card-sovereign-FAILED_PRECHECK.png`).
B-5. Confirm via the state route that the module returned to `STOPPED` (or was never spawned) and via `Get-Process` that no `python.exe` from that module's venv remains.

**Acceptable terminal outcomes** (per v1.2 §7.4 and §9):

| Module | Acceptable | Not acceptable |
|---|---|---|
| Debate | `READY` (fingerprint passed) — with or without Ollama, since it starts without it | `DEGRADED`, `FAILED(TIMEOUT)`, `FAILED(IDENTITY)` — these are shell or adapter defects unless the log proves a module fault |
| SOVEREIGN | `READY`, **or** `FAILED(PRECHECK:<message>)` when `model-inventory.txt` shows a required tag `MISSING` or Ollama unreachable | `FAILED(PRECHECK…)` while all models are `PRESENT` and Ollama reachable; `DEGRADED`; `FAILED(TIMEOUT)` |
| SOW | existing record: `READY` via `receipt_file`, identity `process_image`, `quota_guard.verified_before_spawn: true` | anything else → re-run exactly once through the same path |

A `FAILED` with a clear, honest reason is valid Gate 5 evidence. A doctored `READY` is a session-ending violation. If an outcome lands in the "not acceptable" column, go to §6.

B-6. SOW: verify the existing `sow-20260821T052050.534Z.json` still parses, hash it, copy it. Do not re-run unless B-table says so. Screenshot its card in whatever state the shell reports for SOW with no process (expected `STOPPED`) → `card-sow-STOPPED.png`.

B-7. Distillery: `GET` the Distillery route; assert `NOT_STARTED`, the verbatim line, the derived OQ count **and** the matched IDs, and the parsed-file hashes. Screenshot → `card-distillery-NOT_STARTED.png`. Confirm Start/Stop/Open/Test controls are present in the DOM and `disabled` (read the served HTML/`app.js` behavior; do not click).

B-8. Side-by-side (§4.4): only if SOVEREIGN reached `READY`, take `--screenshot` of `http://127.0.0.1:5175/` and of the shell, and compose them into `side-by-side-sovereign.png` with a stdlib-only script (no PIL — write a minimal PNG concatenation or save two files named `side-by-side-sovereign-{shell,module}.png`; two files are acceptable). If SOVEREIGN did not reach `READY`, write `side-by-side-sovereign.SKIPPED.txt` stating the reason and rely on §5 C-2 for theme evidence.

---

## 5. Step C — Closing evidence

C-1. **Orphans.** Stop the shell (its own shutdown path). Then `Get-Process python,electron,node | Where-Object Path -like "*Production Workspace\modules*"` → must be empty → `orphans-after.txt`. Also `Get-NetTCPConnection -State Listen -LocalPort 5175,8700,5180` → must be empty.

C-2. **Theme contrast.** Parse `docs/THEME-BASELINE.md` tokens and `shell/static/app.css` (stdlib `re`), compute WCAG contrast ratios for: `--text`/`--bg`, `--text`/`--bg-panel`, `--text-muted`/`--bg-panel`, each of `--ok`/`--warning`/`--danger` against `--bg-panel`, dark and light blocks. Write `theme-contrast.txt` with the numbers; flag any pair < 4.5:1. Also `grep` `app.css` for any hex color not in the baseline token set → list (expected: none, or only the baseline values themselves).

C-3. **Final manifests.** `py -3.12 evidence\tools\manifest.py` for the three roots with the same exclusions as the before files (read them from the before-file headers) → `manifest-final-*.txt`; `fc.exe /b` against `manifest-before-*.txt` → `manifest-diff-final-*.txt`. All three must say `no differences`. If not → §6, reason `PROTECTED_SOURCE_CHANGED`, stop.

C-4. **Final git body.** From the SOW live tree with `$env:GIT_OPTIONAL_LOCKS=0`: `rev-parse HEAD`, `status --porcelain=v1 -z`, `diff --binary`, `diff --cached --binary` → `sow-git-final.body` (LF, no BOM, four `### ` sections, no timestamps) + `sow-git-final.meta.json`. Compare to `sow-git-after.body` after normalizing both (LF, no BOM, four sections) → `sow-git-body-diff-final.txt`. Differences in HEAD, status entries, or diff payload hash → `PROTECTED_GIT_STATE_CHANGED`, stop.

C-5. Stop the H-12 watcher; `fs-watch-gate5.txt` must show `events: 0` and a window that brackets A-2 through C-1.

C-6. Run the README test command once more, fresh shell, no `__pycache__` → overwrite `evidence/test-run.txt` only if it ends `OK`; if it does not, keep the old file and go to §6.

---

## 6. Defect protocol (the only way `shell/**` may change this session)

If a real-module test lands in the "not acceptable" column or any Gate 4 proof regresses:

1. Write `docs/GATE5-DEFECT-<n>.md`: observed state, log excerpt (`FACT[path:line]`), hypothesis (`INTERPRETATION`), the smallest change that would fix it.
2. The fix must be ≤ 40 changed lines across `shell/src`, must add or modify exactly one test that fails before and passes after, and must not add a route, a dependency, a feature, or a UI element.
3. Re-run the full README test command → must end `OK`. Regenerate `shell/BUILD-MANIFEST.txt`.
4. Re-run the affected module's startup test (§4) from B-1.
5. List every defect file in `GATE5-REPORT.md` §5 "Deviations".

Anything larger than this → `docs/STOP-REPORT-GATE5.md` with reason `DEFECT_EXCEEDS_GATE5_ENVELOPE`, stop.

---

## 7. Reports and packaging

7.1 `docs/GATE5-REPORT.md` sections, in order: 1 Routes used (with `server.py` line cites) · 2 Pre-flight facts · 3 Per-module outcome table (module · state reached · reason · latency · record path · screenshot path) · 4 Closing evidence table (C-1 … C-6 with paths) · 5 Deviations · 6 Unsigned-root statement (Gates 0/1 `STOP`, hash of `DECISIONS.md` as found) · 7 Open risks (carry forward: two npm advisories in the SOW tree; any `MISSING` model). Every sentence in 2–7 tagged `FACT[path]` / `ASSUMPTION` / `INTERPRETATION` / `RECOMMENDATION`.

7.2 `docs/BUILD-REPORT.md` per v1.2 §10.2: one-page executive summary first, then Objectives (restated, unchanged) · Scope delivered vs §7.3 (item · delivered · evidence) · Evidence index (every file under `evidence/` with sha256) · Assumptions with falsifiers · Contradictions with the directive (carry the four already recorded in REVIEW-BUILD-02 §5) · Risks/limitations · Missing information (the operator signature) · Findings/recommendations. Hard cap 12 pages before appendices.

7.3 Ledger: add Gate 5 `{"status":"CANDIDATE","claimed_by":"builder","evaluated_by":null,"authorized_by":null,"utc":…,"evidence":[{path,sha256}…]}` listing every file in §2. Leave Gates 0–4 and 6 byte-identical; assert that before writing, as the previous builder did.

7.4 Final message: the per-module outcome table, the four closing-evidence verdicts (manifests, git, orphans, fs-watch), the unsigned-root statement, and the §0.2 line.

---

## 8. Stop conditions → `docs/STOP-REPORT-GATE5.md`, then stop

`HOST_NOT_QUIESCENT` · `PROTECTED_SOURCE_CHANGED` · `PROTECTED_GIT_STATE_CHANGED` · `DEFECT_EXCEEDS_GATE5_ENVELOPE` · `ROUTE_UNKNOWN` (a needed route does not exist in `server.py` — do not add one) · `SCREENSHOT_TOOL_ABSENT` (no Edge/Chrome found — list what `Get-Command` returned) · `SOW_ENV_MISSING_SELFCHECK` · `ORPHAN_PROCESS` (a managed process survived C-1 — record the PID, do not kill it, stop) · any instruction here that would require violating §0.1.

---

## 9. What the reviewer will do

Read every file in §2 against v1.2 §9/§12; check that each screenshot's filename state matches the JSON record's state; recompute the three manifest diffs; confirm the timeline shows no `DEGRADED`; grep your reports for unlabeled claims and for the word "passed"; confirm Gates 0–4 are byte-identical to the prior ledger. Write for that reader: short, labeled, traceable.
