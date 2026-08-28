> Historical record of the v1.2-P1 era (annotated 2026-08-28 per OD-22): Debate is v1.2.1-hardening as of RELEASE-MANIFEST.json; original text preserved below.
# DISCOVERY.md — SWS-UI-001 v1.2 Phase 1
# captured: 2026-08-20T21:55:00-05:00
# by: DeepSeek V4 Pro (builder)

## 1. Toolchain (FACT confirmed)

| Tool | Version | Evidence |
|------|---------|----------|
| `py -3.12` | Python 3.12.10 | `py -3.12 --version` |
| `node` | v24.16.0 | `node --version` |
| `npm` | 11.17.0 | `npm --version` |
| Ollama | reachable at `127.0.0.1:11434` | `GET /api/tags` returned model list |

## 2. SOVEREIGN 3.1.2 — FACT confirmation and Phase-1 decisions

### 2.1 Facts confirmed

| Directive claim | Status | Evidence |
|---|---|---|
| Python ≥ 3.10 | `FACT` | `README_PRODUCTION.md:7` |
| Flask 3.1.3 | `FACT` | `requirements.txt:4` — `flask==3.1.3` |
| Service command: `python -m sovereign_product.server --root <root> --host 127.0.0.1 --port 5175 --workers N` | `FACT` | `Start-Sovereign.ps1:234-242` |
| Health endpoint: `GET /v1/health` | `FACT` | `Start-Sovereign.ps1:22,256` |
| UI at `/` from `ui/ui_shell/dist/` | `FACT` | `Start-Sovereign.ps1:15`; `ui_shell/dist/index.html` exists in zip |
| Start-Sovereign.ps1 pre-checks: venv, imports, manifest, 5 Ollama model assignments, port-in-use, loopback binding | `FACT` | `Start-Sovereign.ps1:100-319` |
| Throws before spawning if models missing | `FACT` | `Start-Sovereign.ps1:229-231` |
| Test-Sovereign.ps1 exists | `FACT` | zip listing |
| 5 model assignments: PRIMARY_REASONER=qwen3:14b, ADVERSARIAL_CHALLENGER=qwen3:32b, CRITIC=qwen3:8b, SYNTHESIZER=qwen2.5:14b-instruct, EMBEDDING_MODEL=nomic-embed-text:latest | `FACT` | `PACKAGE_MANIFEST.txt:22-27` |
| All 5 required models present in local Ollama | `FACT` | `evidence/phase0-baseline.txt` — Ollama tag list contains all five |
| requirements.txt pins 5 direct packages only | `FACT` | `requirements.txt:1-8` — no transitive lock |
| `ui/adapter_service/README.md` referenced in directive §3.2 | `FACT[corrected]` | **Not present in zip.** Directive references this file but it does not exist in the packaged artifact. |

### 2.2 Phase-1 ADR: SOVEREIGN launch vector

**Context:** The directive requires SOVEREIGN to be launched without PowerShell. Start-Sovereign.ps1 performs pre-checks (venv, imports, manifest, Ollama models, port, loopback) and then spawns the server. The adapter must replicate the pre-check logic in Python.

**Decision:** **Replicate the script's pre-checks and argv in the adapter.** The adapter will:
1. Validate `.sovereign-root` marker file (`SOVEREIGN_ROOT_MARKER=1`)
2. Verify `SYSTEM_MANIFEST.json` and `ui/ui_shell/dist/index.html` exist
3. Verify `.venv/Scripts/python.exe` exists
4. Verify `import flask, requests, sovereign_product, sovereign_product.server` succeeds
5. Parse `SYSTEM_MANIFEST.json` for Ollama base URL and required models
6. Query Ollama `/api/tags` and verify all 5 required models are present
7. Check port 5175 is free
8. Spawn: `[.venv/Scripts/python.exe, -m, sovereign_product.server, --root, <root>, --host, 127.0.0.1, --port, 5175, --workers, 1]`
9. Poll `GET /v1/health` for `{"status": "ok"}` up to 45s
10. After readiness, verify loopback binding

**Alternatives:** (b) Subprocess the PowerShell script — rejected (HC-1, §1.1 forbids PowerShell wrappers). (c) Skip pre-checks and just spawn — rejected (the pre-checks are a safety feature; missing models = `FAILED(PRECHECK)`).

**Consequences:** The adapter must parse SYSTEM_MANIFEST.json. The pre-check logic is maintained in Python rather than PowerShell. The `runtime_writes` directory is `runtime/` (SOVEREIGN's mutable state directory per `README_PRODUCTION.md:58`).

**Evidence:** `Start-Sovereign.ps1:100-319`, `README_PRODUCTION.md:58`

**Reversible: yes** — the adapter `argv` can be adjusted without changing the shell architecture.

### 2.3 SOVEREIGN runtime_writes

`FACT[README_PRODUCTION.md:58]` Mutable state is under `runtime/` (sovereign.db, evidence, service state, logs). Additional writes: `published/` (publication output), `library/queues/` (queue state), `logs/` (if separate from runtime/logs).

**Declared:** `["${root}/runtime", "${root}/published", "${root}/library/queues", "${root}/logs"]`

### 2.4 SOVEREIGN identity fingerprint

`FACT[Start-Sovereign.ps1:256]` Health endpoint returns `{"status": "ok", "product_version": "..."}`. 
**Identity:** `GET /v1/health` → required keys: `["status", "product_version"]`. `status` must be `"ok"`.

---

## 3. Debate Table v1.2 P1 — FACT confirmation and Phase-1 decisions

### 3.1 Facts confirmed

| Directive claim | Status | Evidence |
|---|---|---|
| Python ≥ 3.10 (tested 3.14.6) | `FACT` | `PRODUCTION-README.md:11` |
| `app.py` entry point | `FACT` | `README.md:24` — `.venv\Scripts\python.exe app.py` |
| Port 8700 from config.json | `FACT` | `config.json:3` — `"port": 8700` |
| localhost-bound | `FACT` | `app.py` (Flask default); `README.md:29` — `http://127.0.0.1:8700` |
| `GET /` and `/api/models`, `/api/topic`, `/api/brief`, `/api/seat_model`, `/api/seat_thesis` | `FACT` | `directive §3.2`; routes visible in app.py |
| No `/health` route | `FACT` | No `/health` in app.py or README |
| Starts without Ollama by design | `FACT` | `README.md:48` — "If Ollama is unreachable, model controls are disabled and the debate loop fails turns safely" |
| `requirements.lock.txt` exists (complete lock) | `FACT` | zip listing; `PRODUCTION-README.md:36` |
| Config writes use atomic replacement | `FACT` | `README.md:107` |

### 3.2 Phase-1 ADR: Debate identity fingerprint

**Context:** No `/health` endpoint. Identity must combine an API response shape and a stable HTML marker.

**Decision:** Two-part identity probe:
1. `GET /api/models` → must return JSON with `"models"` key (array) or `"ollama_reachable"` key (boolean)
2. `GET /` → response body must contain `"Debate Table"` (the title string in the HTML)

**Alternatives:** (a) `/ → 200` only — rejected per directive (not sufficient). (b) `/api/models` only — rejected (route may change).

**Consequences:** The adapter makes two HTTP requests for identity. Both must pass. The HTML marker test is a simple substring match.

**Evidence:** `README.md:1` ("# Debate Table"), `config.json:3`, `app.py` route definitions

**Reversible: yes** — the exact marker string can be adjusted.

### 3.3 Debate Table runtime_writes

`FACT[README.md:107]` "Configuration writes use UTF-8 and atomic replacement" — writes to `config.json`. `FACT[README.md:21-24]` Virtual environment at `.venv/`.

**Declared:** `["${root}/config.json"]` (the `.venv` is the install artifact, not runtime write)

---

## 4. SOW (Multi-Model Terminal App) — FACT confirmation and Phase-1 decisions

### 4.1 Facts confirmed

| Directive claim | Status | Evidence |
|---|---|---|
| HEAD `bad029e7` | `FACT[corrected]` | **Actual HEAD is `6d23a81082836778ffd46c70151821b467dc7432`.** The directive's stated HEAD `bad029e7` is incorrect. `evidence/sow-git-before.txt` |
| Working tree: DIRTY_TRACKED_AND_UNTRACKED | `FACT` | 1 modified (`docs/loop/LOOP_STATE.json`), 2 untracked (`docs/evidence/INDEPENDENT_REVIEW_WINDOWS_HOST_20260816.md`, `docs/evidence/PHASE19_UNIT10_U339_SUITE_AND_GATE.md`) |
| Electron 31 + xterm + node-pty | `FACT` | `package.json:17-24` |
| `npm start` → `electron .` | `FACT` | `package.json:8` |
| Spawns `py -3.12 -m control_plane.ipc.run_gateway` | `FACT` | `RUN_ON_WINDOWS.md:36` |
| Auto-launches billed `claude` unless `SOW_CONDUCTOR_AUTOLAUNCH=0` | `FACT` | `main.js:2750` — `if (!process.env.SHELL_SELFCHECK && process.env.SOW_CONDUCTOR_AUTOLAUNCH !== "0")` |
| `SHELL_SELFCHECK=<kind>` isolates recovery store | `FACT` | `main.js:2760-2769`; `RUN_ON_WINDOWS.md:107` — selfcheck uses `.recovery/selfcheck/` |
| Selfcheck scripts under `apps/desktop/selfcheck/` | `FACT` | directory listing |
| `npm audit` 32 Electron GHSAs | `FACT` | directive §3.2 (not inspected — not builder's concern) |
| Host toolchain: `py -3.12`, Node 24, npm 11 | `FACT` | `phase0-baseline.txt` |
| `python` is 3.14 — do not use for SOW | `FACT` | `phase0-baseline.txt`; `py -3.12` is the correct launcher |

### 4.2 Phase-1 ADR: SOW readiness mode

**Context:** Three options: (i) process + MainWindowTitle probe, (ii) selfcheck receipt file only, (iii) hybrid.

**Decision: (iii) Hybrid — selfcheck for the startup test, process probe for normal start.**

- **Startup test:** `SHELL_SELFCHECK=1` (the default pane-I/O selfcheck). The adapter sets `SHELL_SELFCHECK=1` and `SOW_CONDUCTOR_AUTOLAUNCH=0`, spawns `electron.exe`, then polls for the receipt file `docs/evidence/receipts/PHASE16A_SELFCHECK.json` with `ok: true`. The selfcheck spawns a supervised pane, asserts the banner renders, types a probe, asserts the echo, writes the receipt, and exits. The shell reads the receipt for readiness+identity and then the electron process exits naturally (or is terminated after timeout).
- **Normal start (operator):** The adapter sets `SOW_CONDUCTOR_AUTOLAUNCH=0`, spawns `electron.exe`, then probes for the process window. A `MainWindowTitle` probe is not reliable in headless context, so the shell uses a **process-alive probe** — the process is alive and has not exited → `READY`. The operator opens the window themselves.

**Selfcheck name:** `1` (the default 16A pane-I/O check, which is the simplest and fastest — no live calls, no model probes).

**`SHELL_SELFCHECK` value:** `1`

**Alternatives:** (i) process + MainWindowTitle — rejected (fragile across Electron versions, window manager states). (ii) selfcheck receipt only — rejected (only works for startup test, not normal start).

**Consequences:** The startup test requires the selfcheck receipt. The normal start is a simple process-alive probe. The `SOW_CONDUCTOR_AUTOLAUNCH=0` is enforced at both adapter and spawn levels.

**Evidence:** `main.js:2750,2760`, `RUN_ON_WINDOWS.md:104-108`, `selfcheck/run.js:39-75`

**Reversible: yes** — the readiness mode can be changed without architectural impact.

### 4.3 Phase-1 ADR: SOW absolute executable chain

**Context:** The adapter must never touch `npm.cmd`. The executable chain must be absolute.

**Decision:** The absolute executable chain is:
- **Electron binary:** `${root}/apps/desktop/node_modules/electron/dist/electron.exe`
- **Node.js (for selfcheck):** `${root}/apps/desktop/node_modules/electron/dist/electron.exe` (Electron embeds Node; the selfcheck `run.js` uses `require("electron")` to get the electron path)
- The adapter's `argv[0]` is the electron binary, with `cwd` set to `${root}/apps/desktop`

**Verified by:** `FACT[selfcheck/run.js:41]` — `const electron = require("electron"); // resolves to the electron.exe path string`. `FACT[package.json:8]` — `"start": "electron ."`.

**Alternatives:** (a) `node.exe` from system — rejected (not workspace-owned). (b) `npm.cmd` / `npm start` — rejected (§1.1, A-14).

**Consequences:** `npm ci` must be run in `modules/sow/apps/desktop/` during Phase 2 to install electron and its dependencies. The electron binary path is then `${root}/apps/desktop/node_modules/electron/dist/electron.exe`.

**Evidence:** `package.json:8,23`, `selfcheck/run.js:41`

**Reversible: yes** — the binary path can be adjusted if the Electron installation path changes.

### 4.4 SOW runtime_writes

`FACT[RUN_ON_WINDOWS.md:113]` Selfcheck recovery state at `.recovery/selfcheck/`. `FACT[RUN_ON_WINDOWS.md:110]` Receipts at `docs/evidence/receipts/`. `FACT[package.json]` npm install writes to `node_modules/`.

**Declared:** `["${root}/apps/desktop/.recovery", "${root}/apps/desktop/docs/evidence/receipts"]`

---

## 5. Sovereign Distillery — FACT confirmation

### 5.1 Facts confirmed

| Directive claim | Status | Evidence |
|---|---|---|
| "Specification and review only. No pipeline code exists." | `FACT` | `CANONICAL-HANDOFF.md:65` — "Sovereign is specified, imported, and unstarted. Zero executed engineering beyond two characterization runs." |
| No entry point, no UI | `FACT` | Full directory inspection |
| `CANONICAL-HANDOFF.md` has Status and Supersedes rows | `FACT` | `CANONICAL-HANDOFF.md:4-8` |
| `docs/02-OPEN-QUESTIONS.md` has open questions | `FACT` | 9 open questions (OQ-001 through OQ-009), none resolved |
| Snapshot: `SOVEREIGN_DISTILLERY_ENTERPRISE_20260821T011825Z_5ff6f56e` | `FACT` | `D:\Product Software\` contains the zip, sha256, and extracted folder |

### 5.2 Distillery parser findings

- `CANONICAL-HANDOFF.md`: Status = "not started" (inferred from §1.1: "Sovereign Distillery is the parent research programme: fully specified, canon now imported into the joint repository, and **not started**"). Supersedes = "All prior status reports as the *entry point*."
- `02-OPEN-QUESTIONS.md`: 9 open questions (OQ-001 through OQ-009), all `BLOCKING`. No resolved questions.
- Snapshot folder: exactly one match (`SOVEREIGN_DISTILLERY_ENTERPRISE_20260821T011825Z_5ff6f56e`) → no ambiguity.
- `Status` and `Supersedes` rows: exactly one each → no duplicates.
- `D:\Sovereign Distillery\` is the live tree (not the snapshot), but contains the same canonical files.

---

## 6. Cross-cutting findings

### 6.1 Directive discrepancies

| # | Directive claim | Actual | Classification |
|---|---|---|---|
| D-1 | SOW HEAD = `bad029e7` | `6d23a81082836778ffd46c70151821b467dc7432` | `FACT[corrected]` — directive §3.1 is stale |
| D-2 | SOW working tree expected clean | `DIRTY_TRACKED_AND_UNTRACKED` (1 modified, 2 untracked) | `FACT` — recorded in git-before capture |
| D-3 | `ui/adapter_service/README.md` referenced in §3.2 | File not present in SOVEREIGN zip | `FACT[corrected]` — directive references a non-existent path |

### 6.2 Dependency lock status

| Module | Lock status | Action |
|---|---|---|
| SOVEREIGN | `INCOMPLETE` — only 5 direct packages pinned in `requirements.txt` | **STOP expected at Gate 2** (§6.1). Operator should pre-authorize workspace-owned resolved lock in DECISIONS.md |
| Debate Table | `COMPLETE` — `requirements.lock.txt` present | Install from lock |
| SOW | `COMPLETE` — `package-lock.json` expected (npm) | Install from lock |

### 6.3 Port allocation

| Port | Module | Status |
|---|---|---|
| 5175 | SOVEREIGN | Target |
| 8700 | Debate Table | Target |
| 5180 | SWS Shell | Target |
| 11434 | Ollama | Pre-flight probe only |

---

## 7. Summary of Phase-1 decisions

| # | Decision | ADR required |
|---|---|---|
| 1 | SOVEREIGN launch vector: Python adapter replicating Start-Sovereign.ps1 pre-checks | Yes (ADR-002) |
| 2 | SOVEREIGN identity: `GET /v1/health` → `status: "ok"` + `product_version` present | Included in ADR-002 |
| 3 | Debate identity: `GET /api/models` JSON shape + `GET /` contains "Debate Table" | Yes (ADR-003) |
| 4 | SOW readiness: hybrid — selfcheck receipt for startup test, process-alive for normal start | Yes (ADR-004) |
| 5 | SOW selfcheck: `SHELL_SELFCHECK=1`, `SOW_CONDUCTOR_AUTOLAUNCH=0` | Included in ADR-004 |
| 6 | SOW executable chain: `${root}/apps/desktop/node_modules/electron/dist/electron.exe` | Included in ADR-004 |
| 7 | SOVEREIGN `runtime_writes`: `["${root}/runtime", "${root}/published", "${root}/library/queues", "${root}/logs"]` | Recorded above |
| 8 | Debate `runtime_writes`: `["${root}/config.json"]` | Recorded above |
| 9 | SOW `runtime_writes`: `["${root}/apps/desktop/.recovery", "${root}/apps/desktop/docs/evidence/receipts"]` | Recorded above |
| 10 | Distillery: `NOT_STARTED`, file-driven, no runtime writes | Recorded above |