# BUILD DIRECTIVE SWS-UI-001 v1.2 — Sovereign Workspace Shell

| Field | Value |
|---|---|
| Directive ID / version | SWS-UI-001 **v1.2 "Contract Closure"** (supersedes v1.0, v1.1; 2026-08-21). Architecture frozen at this version. |
| Issuer / final authority | Human operator (sam) — owns objectives, scope, acceptance, promotion |
| Assigned builder | DeepSeek V4 Pro |
| Reviewer of record | Claude (Research Validator / Reviewer) — evaluates against this document; does not approve |
| Build root | `D:\Product Software\Production Workspace\` |
| v1.2 change class | Contract closure. No product scope added. Option A made mandatory (B/C removed as unsatisfiable against HC-1/H-12); H-8 restated as a behavioral requirement; `--no-deps` escape hatch removed; EXTERNAL lifecycle completed; Job Object, git-inspection, dependency-proof, header-revision, and gate-ledger corrections. |

```
GATE 0 — DIRECTIVE AUTHORIZATION (operator fills before any builder action)
  SWS-UI-001 v1.2 approved for Phase 0/1:   ☐ yes      date ________  by ________

§6 MODULE INSTALL AUTHORIZATION (required before Phase 2; empty box = Phase 2 is illegal)
  Only Option A (workspace-owned runtime instances) exists under this directive.
  ☐ Option A authorized      Recorded in docs/DECISIONS.md on ________  by ________
  SHA-256 of DECISIONS.md captured at Gate 2: ________________________________
  Recommendation by the reviewer does not constitute authorization.
```

---

## 0. Mission

Build a **single, hardened, local-only workspace shell** that gives the operator one front door to four systems — **SOVEREIGN**, the **Multi-Model Terminal App** (Sovereign Orchestration Workspace, "SOW"), the **Debate Table**, and the **Sovereign Distillery** — without modifying any of them. The shell launches each runnable module from a workspace-owned runtime instance, runs a bounded startup test, reports health, and opens the module's own UI. It does **not** re-implement, wrap, restyle, proxy, or patch their UIs. The Distillery has no runtime and no UI; its slot is a truthful, file-driven status surface. The shell's visual language is SOVEREIGN's existing token set (§5), not a new design.

---

## 1. Authority and decision rights

1. **Operator** owns objectives, scope, acceptance, promotion, and every change to this directive. **Only the operator promotes the shell.** This is an invariant, not a header note.
2. **Builder** owns implementation choices *inside* the constraints below. Each non-trivial choice gets an ADR (§10.3) ending with an explicit `Reversible: yes|no` line.
3. **Reviewer** inspects output against this document, the manifests (§4), and the evidence (§9). Unsupported claims are rejected.
4. If a constraint proves impossible or contradictory, **stop and report** (§11). Do not interpret around it.

### 1.1 Forbidden interpretations (the builder may not rationalize any of these)

- Starting Phase 2 because "Option A was recommended" — the §6 box must be filled.
- Using any live source tree (including the live SOW tree at `D:\multi model terminal app\...`) as a launch target. Live trees are sources to copy from, never runtime targets.
- Using `--no-deps`, floating resolution, or a self-generated lock to get past an incomplete dependency closure (§6.1).
- Presenting the Distillery card in any state other than `NOT_STARTED` / `CONFIG_ERROR`, or adding "coming soon" language or disabled-but-decorative controls beyond those in §7.4.
- Softening, defaulting, or "temporarily" omitting `SOW_CONDUCTOR_AUTOLAUNCH=0`.
- Classifying an occupied port as `EXTERNAL` without a passed identity fingerprint.
- Launching anything through `cmd.exe`, PowerShell, `.cmd`/`.bat` wrappers, or `shell=True`.
- Treating a Phase-1 unknown (SOW readiness mode, SOVEREIGN launch vector) as settled because an example in this document shows one option.
- Adding a feature not listed in §7.3 because it is "small" or "obviously useful".

---

## 2. Hard constraints — violation = build rejected

| # | Constraint |
|---|---|
| HC-1 | **Zero modification of protected sources.** Protected set: everything under `D:\Product Software\` **except** `Production Workspace\`; `D:\multi model terminal app\sovereign-orchestration-workspace\`; `D:\Sovereign Distillery\`. No create / edit / rename / delete / attribute change. Module code executes only with `PYTHONDONTWRITEBYTECODE=1`. Enforced by before/after manifests (§4.2). |
| HC-2 | **No UI for Sovereign Distillery.** Read-only, file-driven status panel only (§7.4). |
| HC-3 | **No restyling, injecting, proxying, or iframing of module UIs.** Web modules open in a new browser tab at their own origin; Electron modules own their windows. |
| HC-4 | **Startup test is the ceiling of interaction.** Launch, readiness, health, stop/restart of *shell-owned* processes, log tail of *shell-owned* processes. Nothing else. |
| HC-5 | **Localhost only.** Shell listener binds `127.0.0.1`. No tunnels, telemetry, or outbound calls from the shell. |
| HC-6 | **No secrets.** Never read, store, display, or forward credentials. Child env is allowlist + explicit `env_set` only. |
| HC-7 | **No provider-quota spend.** SOW auto-launches a billed `claude` session on start unless `SOW_CONDUCTOR_AUTOLAUNCH=0` (`apps/desktop/RUN_ON_WINDOWS.md`; `main.js:2629`). Enforced at two layers (H-10). A startup test that opens a provider session is a failed build. |
| HC-8 | **Zero runtime third-party dependencies.** Shell runtime = Python 3.12 standard library only (`http.server`, `subprocess`, `threading`, `queue`, `urllib.request`, `json`, `pathlib`, `ctypes`, `socket`, `secrets`, `webbrowser`, `hashlib`). Frontend = vanilla HTML/CSS/JS, no bundler, no CDN. Tests use `unittest`. Any deviation requires an ADR and operator approval before use. |
| HC-9 | **Reproducible.** One documented command each to install, run, and test; all three listed in README and in A-8. |
| HC-10 | **Every report claim is labeled** `FACT[evidence-path]`, `ASSUMPTION`, `INTERPRETATION`, or `RECOMMENDATION`. Unlabeled = unverified. |
| HC-11 | **Process ownership invariant.** A process is controllable only if it was created during the *current* shell process lifetime **and** successfully assigned to the shell's Windows Job Object (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`). After a shell restart, anything already listening is at most `EXTERNAL`, even if a previous shell instance started it. No PID files, no PID-based reattachment. |

---

## 3. Established facts (reviewer evidence, 2026-08-21) and Phase-1 unknowns

### 3.1 Contents of `D:\Product Software\`

`FACT` Packaged snapshots (zips + sha256 + PDF reports), one review folder, and the empty `Production Workspace\`. No installed runnable trees, no virtual environments.

| Module | Artifact | Live tree |
|---|---|---|
| SOVEREIGN 3.1.2 | `SOVEREIGN_ENTERPRISE_PRODUCTION_20260813_142520.zip` | Unknown — **operator to state in DECISIONS.md** |
| Debate Table v1.2.1-hardening | `Debate_Table_v1.2.1_Hardening_20260823_143520.zip` | sha256 d03ba417914e1465898f5144cc5735afb92f7f6da5e846e0a968fe48c531d265 — VERIFIED |
| SOW | `SOW_CONTINUATION_BASELINE_20260815_210626.candidate.zip` + `SOW_REVIEW_ROUND2_RAW\` | `D:\multi model terminal app\sovereign-orchestration-workspace` (HEAD `bad029e7`) |
| Sovereign Distillery | `SOVEREIGN_DISTILLERY_ENTERPRISE_20260821T011825Z_5ff6f56e.zip` + folder | `D:\Sovereign Distillery\` — **no product runtime** |

### 3.2 Per-module facts and what Phase 1 must still decide

**SOVEREIGN** — `FACT[Start-Sovereign.ps1, README_PRODUCTION.md, ui/adapter_service/README.md]` Python ≥ 3.10, Flask 3.1.3; service `python -m sovereign_product.server --root <root> --host 127.0.0.1 --port 5175 --workers N`; health `GET /v1/health`; UI at `/` from `ui/ui_shell/dist/`. `Start-Sovereign.ps1` pre-checks venv, imports, manifest, five Ollama model assignments, port-in-use, loopback binding, and **throws before spawning** if models are missing. `Test-Sovereign.ps1` exists.
**Phase 1 must decide (ADR):** launch vector = (a) replicate the script's pre-checks and argv in the adapter, or (b) something else that is not a PowerShell invocation. The adapter example in §7.2 is **provisional**.
**Behavior to encode:** missing Ollama/models → the module never spawns → `FAILED` with the pre-check message. Not `DEGRADED`.

**Debate Table** — `FACT[README.md, PRODUCTION-README.md, config.json:3, app.py:1338-1462]` Python ≥ 3.10 (tested 3.14.6); `app.py`; port **8700** from `config.json`; localhost-bound; `GET /` and `/api/models`, `/api/topic`, `/api/brief`, `/api/seat_model`, `/api/seat_thesis`; **no `/health` route**. Starts without Ollama by design (controls disable, turns fail safely).
**Phase 1 must decide:** the identity fingerprint (§7.5) — candidate: `GET /api/models` response shape plus a stable marker in `GET /` HTML. `/ → 200` alone is **not** readiness and **not** identity.
**Behavior to encode:** Ollama absent → module still `READY` if fingerprint passes; the pre-flight panel shows Ollama unreachable. That is the module's truthful state, not the shell's problem.

**SOW** — `FACT[apps/desktop/package.json, RUN_ON_WINDOWS.md, main.js:349-357,2416-2448,2629, control_plane/ipc/run_gateway.py:54]` Electron 31 + xterm + node-pty; `npm start` → `electron .`; spawns `py -3.12 -m control_plane.ipc.run_gateway` (prints `IPC_PORT=<n>`); auto-launches billed `claude` unless `SOW_CONDUCTOR_AUTOLAUNCH=0`; `SHELL_SELFCHECK=<mode>` isolates recovery store; selfcheck scripts under `apps/desktop/selfcheck/`; `npm audit` 32 Electron GHSAs (review R-16; not yours to fix). Host toolchain `py -3.12`, Node 24, npm 11; **`python` is 3.14 — do not use for SOW.**
**Phase 1 must decide (ADR), exactly one of:** (i) process + `MainWindowTitle` probe; (ii) selfcheck receipt file only; (iii) hybrid — selfcheck for the startup test, process probe for normal start. Also: the provider-free selfcheck name, the exact `SHELL_SELFCHECK` value, and the **absolute executable chain** (`node.exe` / Electron binary path under `modules\sow\apps\desktop\node_modules\`) so the adapter never touches `npm.cmd`.

**Sovereign Distillery** — `FACT[D:\Sovereign Distillery\README.md, CANONICAL-HANDOFF.md]` "Specification and review only. No pipeline code exists." No entry point, no UI. Startup test not applicable.

### 3.3 Theme facts — unchanged from v1.0

SOVEREIGN `ui_shell/dist/assets/index-*.css` defines the complete token set (dark: bg `#0e1116`, panel `#151a21`, sidebar `#10141a`, input `#1a2029`, border `#262d38`, text `#e6e9ee`, muted `#8b94a3`, faint `#5c6674`, accent `#c9a86a`, accent-dim `#8a744a`, ok `#6ac98a`, warning `#d0aa62`, danger `#c96a6a`, radius 8px, font `"Segoe UI", system-ui, -apple-system, sans-serif`, mono `"Cascadia Code", Consolas, monospace`; light: bg `#f4f5f7`, panel `#fff`, sidebar `#eceef1`, border `#d3d8e0`, text `#1b2027`, muted `#58616e`, faint `#8a93a1`, accent `#8a744a`, accent-dim `#a68b58`). Debate Table shares the slate/gold family; SOW uses a terminal palette. **Decision: SOVEREIGN tokens verbatim.**

---

## 4. Isolation and integrity

### 4.1 Layout

```
Production Workspace/
  shell/        application (src/, static/, modules/*.json, modules/schema.json, tests/)
  modules/      Option A runtime instances, each with INSTALL-PROVENANCE.json
  docs/         DISCOVERY.md THEME-BASELINE.md DECISIONS.md ADR-*.md BUILD-REPORT.md [STOP-REPORT.md]
  evidence/     manifests, tools/, startup-tests/, screenshots/, hardening/, phase logs
```

### 4.2 Manifest format (fixed — not builder's choice)

File `evidence/manifest-before.txt` and `manifest-after.txt`, UTF-8, LF, generated by **the same script**, which is copied to `evidence/tools/manifest.py`:

```
# SWS-MANIFEST v1
# root: <absolute root>
# excluded: <glob>[, <glob>...]
SHA256<TAB>SIZE<TAB>MTIME_UTC_NS<TAB>RELATIVE_PATH
```

Entries sorted lexicographically by normalized relative path (forward slashes, NFC, original case preserved). SHA-256 lowercase hex. One manifest per protected root: `D:\Product Software\` (excluding `Production Workspace/**`), `D:\multi model terminal app\sovereign-orchestration-workspace\` (excluding `node_modules/**`, `.git/**`), `D:\Sovereign Distillery\`.
The generator's own SHA-256 is recorded in the header of every manifest it writes and in `evidence/GATE-LEDGER.json`; before and after captures must be produced by the byte-identical script.
For the SOW git tree additionally capture, before and after, with `GIT_OPTIONAL_LOCKS=0` set in the environment (so inspection cannot refresh the index of a protected checkout): `git rev-parse HEAD`, `git status --porcelain=v1 -z`, `git diff --binary`, `git diff --cached --binary` → `evidence/sow-git-{before,after}.txt`, plus a derived classification `CLEAN | DIRTY_TRACKED | DIRTY_UNTRACKED`. All captures must be byte-identical before/after.
`manifest-diff.txt` **must be empty** at Gates 2, 3, and 5.

### 4.3 Read-only discipline

Discovery is read-only. No installers, `pip install`, `npm install`/`ci`, bootstrap scripts, or migrations inside protected trees — ever.

---

## 5. Theme baseline — pinned

`docs/THEME-BASELINE.md` = the §3.3 token set with evidence path, plus: tokens only, no new hues; dark default, honor `prefers-color-scheme: light` with SOVEREIGN's light block, no switcher; `--font` for UI, `--mono` for logs/commands, 14px/1.45; spacing 4/8/12/16/24; radius 8px; one elevation (1px `--border`); no gradients/glow; ≤150 ms transitions; state badges use `--ok/--warning/--danger/--text-muted` + text + glyph. Copying `ui_shell/dist/icon.svg` *out* to `shell/static/` is permitted.

---

## 6. Module install location — Option A only

**SWS-UI-001 v1.2 permits exactly one configuration: A — workspace-owned runtime instances.** Options B (live trees) and C (hybrid) from v1.1 are withdrawn: launching from a live source tree writes runtime state into a protected tree, which cannot satisfy Mission §0, HC-1, or H-12 simultaneously. Using any live source tree as a runtime target requires an operator-approved revision of this directive before implementation. Gate 1 records the operator's **authorization** of A; the reviewer's recommendation is not authorization.

Pipeline: protected source artifact → hash-verified extraction/copy to `modules\<id>\` → lockfile-governed install → shell supervision. Sources: SOVEREIGN and Debate Table from their zips in `D:\Product Software\` (verified against `MANIFEST-SHA256.json` / `PACKAGE_MANIFEST.txt`); SOW copied from the live tree excluding `.git` and `node_modules`, with HEAD, dirty-state classification (§4.2), and a content manifest of what was actually copied recorded in provenance.

**Permitted mutating actions, inside `Production Workspace\modules\` only:** `py -3.12 -m venv .venv` (or the module's declared interpreter ≥ 3.10); `python -m pip install -r <lockfile>`; `npm ci` in `modules\sow\apps\desktop\` (`npm install` only if no valid lockfile exists, with ADR). Native-build steps (node-pty) get an ADR with the captured build log.

### 6.1 Dependency closure rule

A runtime instance may be installed only when its dependency closure can be reproduced deterministically. If the source artifact contains a complete lock (Debate: `requirements.lock.txt`; SOW: `package-lock.json`), use it. If it contains only direct requirements (SOVEREIGN: `requirements.txt` pins five direct packages; transitive closure is **not** locked — `FACT[README_PRODUCTION.md:10]`), **STOP before installation** with `STOP-REPORT.md`, `reason = MODULE_DEPENDENCY_LOCK_INCOMPLETE`. Do not use `--no-deps`, do not resolve floating versions silently, do not generate an unreviewed replacement lock, do not modify the source artifact. The operator may authorize, in `DECISIONS.md`, creation of a workspace-owned resolved lock (`modules\<id>\WORKSPACE-RESOLVED-LOCK.txt`) produced by a recorded `pip freeze` from a clean resolve; that lock then becomes the install input and is hashed into provenance.

`RECOMMENDATION` The operator should expect this STOP for SOVEREIGN and may pre-authorize the workspace-owned lock in `DECISIONS.md` at Gate 1 to avoid a round-trip.

Each instance gets `INSTALL-PROVENANCE.json`:

```json
{ "module": "sow",
  "source": "D:/multi model terminal app/sovereign-orchestration-workspace",
  "source_kind": "git_worktree_copy",
  "git_head": "bad029e7...", "working_tree_state": "DIRTY_UNTRACKED",
  "source_copy_exclusions": [".git", "node_modules"],
  "source_content_manifest_sha256": "...",
  "lockfiles": [{ "path": "apps/desktop/package-lock.json", "sha256": "..." }],
  "installed_utc": "...", "install_commands_evidence": "evidence/phase2-install.txt",
  "integrity_verified": true }
```

For zip sources: `source_kind: "archive"`, `source_sha256`, `source_revision` (from the package manifest), and `lockfiles` with hashes of every lock actually consumed.

---

## 7. Build specification

### 7.1 Architecture (ADR-001)

Local web shell. Backend: Python 3.12 stdlib `ThreadingHTTPServer` on `127.0.0.1:5180` (CLI flag override only; 5175/8700/11434 and SOW's dynamic IPC port are taken). Frontend: `index.html` + `app.css` + `app.js`, < 300 KB, no framework. Backend does: adapter compile/validate, Job-Object supervision, readiness + fingerprint probing, startup-test records, log ring buffers, pre-flight probes, Distillery parsing. Nothing else. Rejected: proxies, in-process modules, Electron wrapper, admin rights.

### 7.2 Adapter contract

One `shell/modules/<id>.json` per module, validated at load against `schema.json`, then **compiled** to absolute canonical paths. Schema rules: `additionalProperties:false` at every level; `id` matches `^[a-z][a-z0-9_-]{0,31}$`; strict enums `state_class ∈ {runnable, not_started}`, `readiness.kind ∈ {http, process_window, receipt_file}`, `open.kind ∈ {browser, none}`, `stop.kind ∈ {job_object}`; bounds `timeout_s 5–120`, `poll_ms 250–5000`, `grace_s 1–30`; `argv` ≤ 32 items, each ≤ 1024 chars; only `${root}` substitution, any other `${...}` → `CONFIG_ERROR`; no env-var expansion; `root`, `cwd`, `argv[0]` absolute after compile; no UNC, no `\\?\`/`\\.\` device paths; `argv[0]` must end in `.exe`; adapter files are hashed at load and treated immutable while a child runs.

```json
{
  "id": "sovereign",
  "display_name": "SOVEREIGN",
  "description": "Operator product service and UI (Flask, :5175)",
  "state_class": "runnable",
  "root": "D:/Product Software/Production Workspace/modules/sovereign",
  "runtime_writes": ["${root}/published", "${root}/library/queues", "${root}/logs"],
  "launch": {
    "cwd": "${root}",
    "argv": ["${root}/.venv/Scripts/python.exe", "-m", "sovereign_product.server", "--root", "${root}",
             "--host", "127.0.0.1", "--port", "5175", "--workers", "1"],
    "env_allowlist": ["SYSTEMROOT", "PATH", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA"],
    "env_set": { "PYTHONDONTWRITEBYTECODE": "1" }
  },
  "readiness": { "kind": "http", "url": "http://127.0.0.1:5175/v1/health", "expect_status": 200,
                 "timeout_s": 45, "poll_ms": 500 },
  "identity":  { "kind": "http_json", "url": "http://127.0.0.1:5175/v1/health",
                 "required_keys": ["<PHASE-1-VERIFIED>"] },
  "open": { "kind": "browser", "url": "http://127.0.0.1:5175/" },
  "stop": { "kind": "job_object", "grace_s": 10 }
}
```

**This example is PROVISIONAL** (`runtime_writes` and `identity` are Phase-1 outputs; argv depends on ADR per §3.2). Per-module table — every `<PHASE-1-VERIFIED>` must be replaced before Phase 3 adapter finalization; an adapter containing that literal fails schema validation:

| id | argv[0] (Option A) | env_set | readiness | identity | open |
|---|---|---|---|---|---|
| `sovereign` | `${root}/.venv/Scripts/python.exe` | `PYTHONDONTWRITEBYTECODE=1` | http `/v1/health` 200 | `<PHASE-1-VERIFIED>` JSON keys | browser |
| `debate` | `${root}/.venv/Scripts/python.exe app.py` | `PYTHONDONTWRITEBYTECODE=1` | http `/` 200 **and** identity | `<PHASE-1-VERIFIED>` (e.g., `/api/models` shape + HTML marker) | browser |
| `sow` | **absolute** `${root}/apps/desktop/node_modules/electron/dist/electron.exe` (or `node.exe` for selfcheck) — `<PHASE-1-VERIFIED>`; never `npm.cmd` | `SOW_CONDUCTOR_AUTOLAUNCH=0` **always**; `SHELL_SELFCHECK=<PHASE-1-VERIFIED-MODE>` startup test only; `PYTHONDONTWRITEBYTECODE=1` | `<PHASE-1-VERIFIED>` one of (i)/(ii)/(iii) | process path under `${root}` | none |
| `distillery` | — (`not_started`) | — | — | — | file links |

`runtime_writes` is declared per adapter (may be empty) and is an **audit specification for the workspace-owned instance**: after each startup test the shell diffs the instance tree and any write outside the declared paths is recorded in the startup record as `undeclared_writes` (a finding, not a failure — the instance is workspace-owned). It never authorizes writes to protected sources.

### 7.3 Feature list — complete

1. Module grid, fixed order: SOVEREIGN · Multi-Model Terminal (SOW) · Debate Table · Sovereign Distillery. Card: name, description, state badge + reason code, last-check time, port/URL, action row.
2. Actions: Start · Stop · Restart (own processes only) · Open (enabled in `READY`, `EXTERNAL`) · Run startup test · View logs.
3. Startup test: launch → readiness → identity → record → stop (default) or keep (toggle). Record path `evidence/startup-tests/<id>-<YYYYMMDDTHHMMSS.mmmZ>.json` (no colons); body holds full RFC 3339. Contents: adapter hash, compiled argv, env key names, start/end, exit code, readiness + identity outcomes and latencies, last 200 sanitized log lines, manifest-diff status, and for SOW the `quota_guard` block (§7.6 H-10).
4. Log pane: shell-owned processes only; 2,000-line ring; each line ≤ 4 KB, each read ≤ 64 KB; bytes decoded UTF-8 with replacement; ANSI/CSI sequences and C0/C1 controls stripped (never interpreted); NUL removed; redaction (H-8) applied before buffering; rendered as text nodes.
5. Header: SWS version, build ID, source revision (git commit if `Production Workspace\` is a repository, otherwise the first 12 hex of the SHA-256 of `shell/BUILD-MANIFEST.txt` — a sorted hash list of all shell source files generated by the test command), host, clock, links to DISCOVERY / THEME-BASELINE / this directive. This directive does **not** require git for the shell.
6. Pre-flight panel (read-only facts with timestamps): Ollama `GET 127.0.0.1:11434/api/tags`; `py -3.12`, `node`, `npm` present; ports 5175/8700/5180 free. No fix buttons.
7. Keyboard: Tab order, `Enter`, `Esc`.

Out of scope: accounts, settings pages, notifications, auto-update, plugins, theme switcher, dashboards/metrics, chat, any module feature, embedding.

### 7.4 State machine (normative — UI and tests implement exactly this)

States: `NOT_STARTED` · `STOPPED` · `STARTING` · `READY` · `DEGRADED` · `FAILED(reason)` · `EXTERNAL` · `CONFIG_ERROR(reason)`.

```
STOPPED   -> STARTING         Start accepted; process created and assigned to Job Object
STARTING  -> READY            initial readiness AND identity pass within timeout_s
STARTING  -> FAILED(EXIT)     process exits before readiness
STARTING  -> FAILED(TIMEOUT)  readiness deadline expires (process then terminated)
STARTING  -> FAILED(IDENTITY) readiness passed, identity failed (process then terminated)
STARTING  -> STOPPED          operator cancels
READY     -> DEGRADED         periodic readiness fails, process alive
READY     -> FAILED(EXIT)     process exits unexpectedly
READY     -> STOPPED          operator stops
DEGRADED  -> READY            readiness recovers
DEGRADED  -> FAILED(EXIT)     process exits
DEGRADED  -> STOPPED          operator stops
(any, no managed process) -> EXTERNAL                     endpoint answers AND identity passes
(any, no managed process) -> FAILED(PORT_OCCUPIED_UNRECOGNIZED)  endpoint occupied, identity fails/absent; Start refused
EXTERNAL  -> EXTERNAL         periodic probe: endpoint answers and identity still passes
EXTERNAL  -> STOPPED          endpoint no longer occupied
EXTERNAL  -> FAILED(PORT_OCCUPIED_UNRECOGNIZED)  endpoint still occupied, identity no longer passes
FAILED(PORT_OCCUPIED_UNRECOGNIZED) -> STOPPED    endpoint released (re-probed on the STOPPED cadence)
Distillery                -> NOT_STARTED                  invariant; CONFIG_ERROR only if source files unreadable
invalid adapter / root / parser -> CONFIG_ERROR(reason)
Job Object assignment fails at spawn -> process terminated immediately -> FAILED(JOB_ASSIGN)
```

Pre-check failures that prevent spawn (e.g., SOVEREIGN's missing Ollama models, when the adapter replicates the script's checks) → `FAILED(PRECHECK:<message>)`. `DEGRADED` is reserved for post-`READY` loss of readiness.

### 7.5 Distillery slot — truthful status only

`NOT_STARTED`; panel parsed on open from `D:\Sovereign Distillery\CANONICAL-HANDOFF.md` (`Status`, `Supersedes` rows, raw text) and `docs\02-OPEN-QUESTIONS.md` (rows matching `OQ-\d+` not struck-through/CLOSED → count **and** the matched IDs, rule shown on hover); snapshot id from `SOVEREIGN_DISTILLERY_ENTERPRISE_*` in `D:\Product Software\`; links to the three docs; verbatim line *"No runtime, entry point, or UI exists for Sovereign Distillery. Startup test not applicable."*; Start/Stop/Open/Test disabled-not-hidden with tooltip. Deterministic failure rules: zero matching snapshot folders → `CONFIG_ERROR`; more than one → `CONFIG_ERROR(AMBIGUOUS_SNAPSHOT)` unless DECISIONS.md names a selection rule; duplicate `Status`/`Supersedes` rows → `CONFIG_ERROR`; invalid UTF-8 → `CONFIG_ERROR`; returned status includes SHA-256 of each parsed file. Never fabricate.

### 7.6 Hardening — each item needs a proof artifact in `evidence/hardening/`

| ID | Requirement | Proof |
|---|---|---|
| H-1 | `127.0.0.1` bind only | `Get-NetTCPConnection -State Listen` capture |
| H-2 | State-changing endpoints: `POST` only; `Host` and `Origin` exact-match the shell origin; `Content-Type: application/json`; `Content-Length` ≤ 16 KB; body validated against a per-endpoint schema with no extra fields; per-instance CSRF nonce (generated with `secrets`, served only in the shell's own HTML, never persisted) required in a header | tests: each rule's negative case → 403/400 |
| H-3 | Headers on every response: CSP `default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; object-src 'none'; base-uri 'none'`; `X-Content-Type-Options: nosniff`; `Referrer-Policy: no-referrer`; `Permissions-Policy: camera=(), microphone=(), geolocation=()`; `Cache-Control: no-store`; no inline script/style | header capture |
| H-4 | No `eval`/`Function`/`innerHTML`/`insertAdjacentHTML` with dynamic data; logs as text nodes | grep + test |
| H-5 | Path containment by **canonical resolution**: `os.path.realpath` after resolving junctions/reparse points/symlinks via `GetFinalPathNameByHandle`, case-insensitive comparison, `os.path.commonpath` containment against compiled allowlisted roots. Prefix-string comparison is forbidden. Tests: `..`, junction escape, case variant, UNC, device path | tests |
| H-6 | **Windows Job Object mandatory**: every managed process created suspended, assigned to a per-shell Job with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` set and **both** `JOB_OBJECT_LIMIT_BREAKAWAY_OK` and `JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK` cleared, then resumed; Stop = graceful signal → `grace_s` → `TerminateJobObject`. Fixture spawns child → grandchild (grandchild attempts `CREATE_BREAKAWAY_FROM_JOB`); all must die on Stop and on shell crash (`os._exit`), and the breakaway attempt must fail | tests |
| H-7 | Rate limit one Start per module per 2 s; max 4 managed processes | test |
| H-8 | Secret-bearing output sanitization — behavioral requirement stated in §7.6.1 below | sentinel test (§7.6.1) |
| H-9 | Shell exit stops only Job-owned processes; `EXTERNAL` never touched | test |
| H-10 | Two-layer quota guard: (1) static — `sow` adapter without `env_set.SOW_CONDUCTOR_AUTOLAUNCH == "0"` → `CONFIG_ERROR`; (2) spawn — assert compiled env contains it immediately before `CreateProcess`, else abort; record `{"quota_guard":{"required":true,"autolaunch_value":"0","verified_before_spawn":true}}` in the startup record | tests for both layers |
| H-11 | Shell has zero runtime third-party deps (HC-8). Proof is four-part: (1) no runtime dependency declaration exists (`requirements.txt` absent or empty, no `pyproject` deps); (2) a static import inventory of `shell/src` resolves only to stdlib and shell-local modules; (3) the shell starts and serves `/` under `py -3.12 -I -S <entrypoint>`; (4) a test asserts no loaded module originates from `site-packages`. `pip freeze` is not accepted as proof | `evidence/hardening/deps-proof.txt` |
| H-12 | No runtime writes outside `Production Workspace\` | manifest diff + filesystem watch during tests |

#### 7.6.1 H-8 — secret-bearing output sanitization (normative)

Redaction MUST occur before process output enters any of: the in-memory log ring, any API response, any startup-test record, any evidence file derived from process output. Never only at presentation time. At minimum, detect case-insensitively: `api_key` / `api-key` / `apikey` assignments; `token`, `secret`, `password`, `passwd` assignments (`=` or `:` separated); `Authorization` header values; `Bearer` credential values; credential-bearing URL query parameters including `api_key`, `token`, `key`, `secret`, `password`, `access_token`. Replacement value is the literal `[REDACTED]`. The implementation may use one expression or several. **Test:** a fixture emits a unique sentinel secret in every supported form; PASS requires the sentinel to be absent from the ring buffer, the rendered/API log output, the startup-test JSON, and all persisted evidence.

### 7.7 Performance and quality

Cold start < 2 s; idle CPU ≈ 0 (poll 5 s `READY`, 30 s `STOPPED`, none `NOT_STARTED`); payload < 300 KB; contrast ≥ 4.5:1; visible focus rings; badges text + glyph; current Edge and Chrome.

---

## 8. Phases and gates

| Gate | Name | Passes when |
|---|---|---|
| 0 | Directive authorization | Operator fills the Gate 0 box. |
| — | **Phase 0 Baseline** | `manifest-before.txt` per root, `sow-git-before.txt`, `evidence/phase0-baseline.txt` (toolchain versions, Ollama reachability). |
| — | **Phase 1 Discovery** | `docs/DISCOVERY.md`: every §3 `FACT` confirmed/corrected with `path:line`; SOVEREIGN launch vector ADR; Debate identity fingerprint; SOW readiness mode (i/ii/iii) ADR, selfcheck name, `SHELL_SELFCHECK` value, absolute executable chain; `runtime_writes` per module; `docs/THEME-BASELINE.md`. |
| 1 | Discovery authorization | Operator reviews DISCOVERY.md, authorizes Option A in the §6 box, writes `docs/DECISIONS.md` (optionally pre-authorizing the SOVEREIGN workspace-owned lock, §6.1). |
| 2 | Install authorization | Builder records SHA-256 of `DECISIONS.md` in `evidence/phase2-install.txt` **before** the first mutating command; manifest diff empty; dependency-closure rule (§6.1) satisfied or STOP. Then **Phase 2 Install** with provenance files. |
| 3 | Protected-source integrity | Post-install manifests identical to baseline. |
| — | **Phase 3 Build** | Shell per §7; ADRs. Adapter finalization blocked while any `<PHASE-1-VERIFIED>` literal remains. |
| 4 | Build verification | §9 automated suite and H-1…H-12 proofs pass. |
| 5 | Real-module verification | §9 manual evidence, truthful states; final manifests identical. |
| 6 | Promotion | Reviewer verifies; **operator promotes**. |

**Gate ledger.** `evidence/GATE-LEDGER.json` is created at Phase 0 and updated at every gate transition; it does not replace human approvals — it makes their sequence auditable:

```json
{ "directive": "SWS-UI-001", "version": "1.2", "manifest_tool_sha256": "...",
  "gates": { "0": { "status": "PASS", "utc": "...", "evidence": ["docs/DECISIONS.md#gate0"] },
             "1": { "status": "PASS", "utc": "...", "evidence": ["docs/DISCOVERY.md", "docs/DECISIONS.md"], "evidence_sha256": ["...", "..."] },
             "2": { "status": "NOT_REACHED" }, "3": { "status": "NOT_REACHED" },
             "4": { "status": "NOT_REACHED" }, "5": { "status": "NOT_REACHED" }, "6": { "status": "NOT_REACHED" } } }
```

Allowed statuses: `NOT_REACHED | PASS | STOP`. A gate may not be `PASS` while any earlier gate is not `PASS`.

---

## 9. Verification

**Automated** (`py -3.12 -m unittest discover shell/tests`), using fixture processes under `shell/tests/fixtures/`: adapter schema (valid / invalid / placeholder literal / outside allowlist / traversal / junction / UNC / device path); every transition in §7.4 including `IDENTITY`, `PORT_OCCUPIED_UNRECOGNIZED`, `JOB_ASSIGN`; H-2 … H-10; Distillery parser (real file, missing, corrupt, duplicate rows, two snapshot folders); startup-record schema and Windows-safe filename.

**Manual, evidence-captured, against Option A instances:** one startup test per runnable module with JSON + card screenshot in the state honestly reached (a `FAILED(PRECHECK:...)` for SOVEREIGN without models is valid evidence); Distillery card `NOT_STARTED`; shell beside SOVEREIGN UI for token consistency; SOW proof of no provider session (status bar `0/2` or autolaunch-disabled log line) plus the `quota_guard` block.

---

## 10. Deliverables and reporting

### 10.1 Tree — as §4.1, plus `README.md` with exactly three commands (install / run / test).

### 10.2 BUILD-REPORT.md — one-page executive summary first, then: 1 Objectives (unchanged) · 2 Scope delivered vs §7.3 (item · delivered · evidence) · 3 Evidence index · 4 Assumptions (+ falsifier) · 5 Contradictions with this directive · 6 Risks/limitations · 7 Missing information · 8 Findings/recommendations. Every sentence in 2–8 tagged per HC-10. Hard cap 12 pages excluding appendices.

### 10.3 ADRs — Context · Decision · Alternatives · Consequences · Evidence · `Reversible: yes|no`. Required: architecture; SOVEREIGN launch vector; Debate fingerprint; SOW readiness mode and executable chain; each install deviation; any token deviation.

---

## 11. Stop conditions → `docs/STOP-REPORT.md` (condition, evidence, 2–3 options), then stop

Module unlaunchable without modifying a protected tree or supplying secrets · §6 box empty at Phase 2 · `MODULE_DEPENDENCY_LOCK_INCOMPLETE` without an operator-authorized workspace lock (§6.1) · any SOW path that would open a provider session · unresolvable port collision · non-empty manifest diff at any gate · Job Object unavailable or assignment/breakaway test fails in the fixture · no `.exe` launch chain can be established for SOW without a `.cmd`/`.bat`/PowerShell wrapper · admin elevation required.

---

## 12. Acceptance (operator decides; reviewer verifies evidence)

| # | Criterion | Evidence |
|---|---|---|
| A-1 | All manifest diffs empty at Gates 2, 3, 5; SOW git captures identical | files |
| A-2 | Startup records for SOVEREIGN, Debate, SOW with honest terminal states and Windows-safe names | JSON |
| A-3 | SOW opened no provider session; `quota_guard` present | log/screenshot/JSON |
| A-4 | Distillery `NOT_STARTED`, file-driven, controls disabled-not-hidden, parser failure rules tested | screenshot + tests |
| A-5 | Automated suite passes; output shipped | `evidence/test-run.txt` |
| A-6 | H-1 … H-12 each proven | `evidence/hardening/` |
| A-7 | Styling traceable to THEME-BASELINE only | screenshot + CSS grep |
| A-8 | README's three commands work from a clean checkout | reviewer reproduction |
| A-9 | BUILD-REPORT fully labeled; executive summary present | reviewer read |
| A-10 | No feature beyond §7.3; no `<PHASE-1-VERIFIED>` literal remains | reviewer read + grep |
| A-11 | `DECISIONS.md` SHA-256 recorded in `phase2-install.txt` before the first install command and matches the file | file |
| A-12 | Shell runtime has zero third-party dependencies per the four-part H-11 proof | `evidence/hardening/deps-proof.txt` |
| A-13 | Every ADR has a `Reversible:` line | reviewer read |
| A-14 | Every compiled adapter `argv[0]` is an absolute `.exe`; no `.cmd`, `.bat`, `.ps1`, `cmd.exe`, or `powershell.exe` appears anywhere in any compiled argv | compiled-adapter dump + grep |
| A-15 | Manifest generator byte-identical before/after (hash in every manifest header and in the gate ledger); SOW git captures taken with `GIT_OPTIONAL_LOCKS=0` | files |
| A-16 | Every `INSTALL-PROVENANCE.json` lists the SHA-256 of each lockfile consumed; `GATE-LEDGER.json` shows gates 0–6 `PASS` in order | files |

---

## 13. Reviewer's notes to the operator

- `FACT` v1.2 closes three P0 defects found by independent review of v1.1: (1) Options B/C could never satisfy H-12 and are withdrawn; (2) the H-8 row was corrupted by an unescaped `|` inside a Markdown table — my formatting error — and is restated as a behavioral requirement in §7.6.1; (3) the `--no-deps` fallback is removed in favor of a dependency-closure rule. P1 corrections: `GIT_OPTIONAL_LOCKS=0` and dirty-tree classification for SOW inspection, `-I -S` dependency proof replacing `pip freeze`, both Job Object breakaway flags cleared with a breakaway test, complete `EXTERNAL` lifecycle, header revision without forcing git, manifest-tool hash, lockfile hashes in provenance, gate ledger, and A-14 for the `.exe`-only launch chain.
- `FACT` v1.1 incorporated twelve P0 corrections and the hardening items from two independent reviews (ChatGPT, Grok) of v1.0. Each was verified against v1.0's text and the module sources before acceptance.
- `RECOMMENDATION` Expect `MODULE_DEPENDENCY_LOCK_INCOMPLETE` for SOVEREIGN at Gate 2 — its `requirements.txt` pins only five direct packages. Pre-authorize the workspace-owned resolved lock in `DECISIONS.md` at Gate 1 if you want Phase 2 to run without a round-trip.
- `FACT` One reviewer suggestion was **not** adopted as stated: "missing Ollama model → `FAILED`, never `DEGRADED`" as a universal rule. SOVEREIGN's launcher throws pre-spawn, so `FAILED(PRECHECK)` is correct there; Debate Table starts without Ollama by design and is honestly `READY`. §3.2 and §7.4 now state the per-module behavior rather than a blanket rule.
- `FACT` Module facts still derive from the packaged snapshots and the SOW review reports, not from inspected live installs of SOVEREIGN or Debate Table.
- `ASSUMPTION` `Production Workspace` is the intended build root.
- `RECOMMENDATION` Fill Gate 0 and hand the builder v1.2 only. Retire v1.0 and v1.1; they differ from v1.2 on whether live trees are permitted runtime targets and on the dependency rule. The architecture is frozen at v1.2; remaining judgment lives in the three Phase-1 ADRs (SOVEREIGN launch vector, Debate identity fingerprint, SOW readiness mode + `.exe` chain). Further polishing of this document has lower expected value than letting it meet actual software.
