# Sovereign Workspace Shell — SWS-UI-001 v1.2

A single, hardened, local-only workspace shell that gives the operator one front door to four
systems — SOVEREIGN, Multi-Model Terminal (SOW), Debate Table, and Sovereign Distillery.

Three commands: **Install**, **Run**, **Test**. Each is complete on its own; nothing below assumes
a previous session left anything in place.

## Requirements

- Windows 10/11
- Python 3.12, reachable as `py -3.12`
- Node 24 and npm 11
- [Ollama](https://ollama.com) for the local model slate

## Install

`tools\release\install.ps1` is the **only** supported install path. It takes the release
install archive and an empty destination, and does everything else itself.

```powershell
.\tools\release\install.ps1 -Dest "C:\SovereignWorkspace"
```

It refuses a non-empty destination and refuses a filesystem root, so it cannot overwrite an
existing install or scatter files into a drive root. What it does, in order:

1. Verifies the install archive against its `.sha256` sidecar before reading a byte of it.
2. Extracts it, rejecting any entry whose path would escape the destination.
3. Rewrites `shell\config\install.json` and every module adapter to the destination, so the
   installed copy refers to itself and not to the machine it was built on.
4. Provisions the Python environments from exact pinned locks — SOVEREIGN, Debate and SOW —
   and proves the SOW gateway imports before declaring success.
5. Runs `npm ci` for the SOVEREIGN UI and the SOW desktop app.
6. Writes `install-manifest.json`, a per-file SHA-256 record of everything it placed.

Add `-TargetDir` to create desktop and Start Menu shortcuts; it refuses to overwrite an
existing shortcut.

### Verify and remove

```powershell
.\tools\release\verify_install.ps1 -Dest "C:\SovereignWorkspace"
.\tools\release\uninstall.ps1      -Dest "C:\SovereignWorkspace"
```

`verify_install.ps1` re-hashes every path in the install manifest. `uninstall.ps1` removes
exactly what the manifest records.

> **Known limitation.** `uninstall.ps1` currently compares the whole install tree against the
> manifest and refuses to run if anything was added — which includes the runtime state the
> product itself writes. It therefore succeeds only on an installation that has not been used.
> Tracked as P0-5; see `docs\RELEASE-ASSURANCE.md`.

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
| Debate Table v1.2.1-hardening | 8700 | FastAPI web app |
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
