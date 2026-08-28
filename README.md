# Sovereign Workspace Shell — SWS-UI-001 v1.2

A single, hardened, local-only workspace shell that gives the operator one front door to four
systems — SOVEREIGN, Multi-Model Terminal (SOW), Debate Table, and Sovereign Distillery.

Three commands: **Install**, **Run**, **Test**. Each is complete on its own; nothing below assumes
a previous session left anything in place.

## Install

From a clean extraction of `Production Workspace\`, with the working directory set to it. Every
module runtime instance is created here, under `modules\` (BUILD-DIRECTIVE §6, Option A).

```powershell
# 1. SOVEREIGN and Debate Table come from the packaged archives in D:\Product Software\.
Expand-Archive "D:\Product Software\SOVEREIGN_ENTERPRISE_PRODUCTION_20260813_142520.zip" -DestinationPath "modules\sovereign"
Expand-Archive "D:\Product Software\Debate_Table_v1.2_Phase1_Production_20260811_201116 - Copy.zip" -DestinationPath "modules\debate"

# 2. Verify each extraction against the manifest the archive ships with, before installing anything.
py -3.12 -c "import hashlib,json,pathlib,sys; r=pathlib.Path('modules/debate'); m=json.loads((r/'MANIFEST-SHA256.json').read_text(encoding='utf-8')); bad=[e['path'] for e in m['files'] if not (r/e['path']).is_file() or hashlib.sha256((r/e['path']).read_bytes()).hexdigest()!=e['sha256']]; print(len(m['files']),'checked',len(bad),'mismatches'); sys.exit(bool(bad))"
py -3.12 -c "import pathlib,sys; p=pathlib.Path('modules/sovereign/PACKAGE_MANIFEST.txt'); print('PACKAGE_MANIFEST.txt present' if p.is_file() else 'MISSING'); sys.exit(0 if p.is_file() else 1)"

# 3. Workspace-owned virtualenvs, installed from resolved locks only.
py -3.12 -m venv modules\sovereign\.venv
modules\sovereign\.venv\Scripts\python.exe -m pip install -r modules\sovereign\WORKSPACE-RESOLVED-LOCK.txt
py -3.12 -m venv modules\debate\.venv
modules\debate\.venv\Scripts\python.exe -m pip install -r modules\debate\requirements.lock.txt

# 4. SOW is a source copy of the live tree, excluding build and VCS artifacts.
robocopy "D:\multi model terminal app\sovereign-orchestration-workspace" "modules\sow" /E /XD .git node_modules __pycache__ .pytest_cache .sovereign_store

# 5. SOW dependency and Electron binary provisioning (ADR-005). Verifies the Electron zip's
#    SHA-256 against the vendor-shipped checksums.json before extracting it.
py -3.12 shell\tools\install_sow.py
```

`install_sow.py` runs `npm ci --ignore-scripts`, provisions `node_modules\electron\dist\` from a
hash-verified zip, writes `path.txt` and `dist\version`, and verifies that `node-pty` loads from
its `win32-x64` prebuild. It logs every step to `evidence\phase2-sow-install.txt` and exits
non-zero on any mismatch. Do not run `npm install` by hand — see ADR-005 for why.

## Run

```powershell
py -3.12 -m shell.src
```

Open <http://127.0.0.1:5180>. Override the port with `--port <n>` if 5180 is taken.

## Test

```powershell
py -3.12 -B -m unittest discover -s shell/tests -v
```

The suite starts and stops its own shell instance on an ephemeral loopback port, so no server
needs to be running and no port is assumed. It also regenerates `shell\BUILD-MANIFEST.txt` and the
artifacts under `evidence\hardening\`. `-B` keeps `__pycache__` out of `shell\`.

`shell\src\__main__.py` accepts `--selftest`, used only by the H-11 dependency proof: it serves
exactly one request to `/`, asserts that no loaded module came from `site-packages`, prints the
result and exits. It is a proof hook, not a feature, and adds no HTTP endpoint.

## Architecture

- **Backend:** Python 3.12 stdlib `ThreadingHTTPServer` on `127.0.0.1:5180`
- **Frontend:** Vanilla HTML/CSS/JS, < 41 KB
- **Process management:** Windows Job Objects with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`
- **Modules:** Defined by JSON adapters in `shell\modules\`, runtime instances in `modules\`

## Modules

| Module | Port | Type |
|---|---|---|
| SOVEREIGN 3.1.2 | 5175 | Flask web app |
| Debate Table v1.2 P1 | 8700 | FastAPI web app |
| Multi-Model Terminal (SOW) | — | Electron desktop app |
| Sovereign Distillery | — | File-driven status only |

## Security

- Binds `127.0.0.1` only
- `Host` and `Origin` exact-matched on every state-changing request; no CORS headers
- CSRF protection with a per-instance nonce, served only in the shell's own HTML
- CSP headers on all responses
- Path containment by canonical resolution, not prefix comparison
- Secret redaction before process output reaches any buffer, response, or file
- Windows Job Object containment, including grandchildren that attempt breakaway
- No third-party runtime dependencies

## Documentation

- `docs\DISCOVERY.md` — Phase 1 discovery findings
- `docs\THEME-BASELINE.md` — Visual token set
- `docs\DECISIONS.md` — Operator decisions
- `docs\ADR-*.md` — Architecture decision records, including ADR-005 (SOW install)
- `BUILD-DIRECTIVE-SWS-UI-001.md` — Full build directive
