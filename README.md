# Sovereign Workspace Shell — SWS-UI-001 v1.2

A single, hardened, local-only workspace shell that gives the operator one front door to four
systems — SOVEREIGN, Multi-Model Terminal (SOW), Debate Table, and Sovereign Distillery.

Three commands: **Install**, **Run**, **Test**. Each is complete on its own; nothing below assumes
a previous session left anything in place.

## Requirements

- Windows 10/11
- Python 3.12, reachable as `py -3.12` — the shell and the SOVEREIGN and SOW modules
- Python 3.14, reachable as `py -3.14` — the Debate module, which `tools\release\install.ps1`
  provisions from its own lock. The installer fails without it. The split is deliberate and
  recorded in `docs\SUPPORT-POLICY.md`; both interpreters are required for an install.
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

`uninstall.ps1` keeps the operator's state by default. State lives outside the install root
(under `%LOCALAPPDATA%\SovereignWorkspace`, or `SOVEREIGN_WORKSPACE_STATE` if set), so removing
the installation does not remove your work:

- `-KeepData` (the default) leaves the state root untouched.
- `-PurgeData` removes it as well, after naming exactly what it will delete.

The install-tree path-set check remains strict: uninstall refuses if anything inside the
installation differs from the manifest, and it never deletes a path the manifest does not
record. Reinstall-then-restore is the supported recovery route; see `docs\OPERATIONS.md`.

> Historical note: the README previously described P0-5 — uninstall refusing on any
> installation that had been used, because the product's own runtime state counted as an
> unexpected addition. That was fixed when runtime state moved out of the install root; the
> record is in `docs\RELEASE-ASSURANCE.md`. The limitation above is the current behaviour.

## Run

```powershell
py -3.12 -m shell.src
```

Open <http://127.0.0.1:5180>. Override the port with `--port <n>` if 5180 is taken.

## Test

The supported run is the whole product, from the repository root:

```powershell
py -3.12 -m pytest -q
```

`tools\ci\run_ci.ps1` runs that plus every release gate, the boundary gate, the Node suites,
and — with `-IncludeCleanRoom` — a release build followed by a clean-room install and verify.
CI invokes the same script, so a developer run and the lane check the same things.

To run only the shell's own suite:

```powershell
py -3.12 -m pytest shell/tests -q
```

The suite starts and stops its own shell instance on an ephemeral loopback port, so no server
needs to be running and no port is assumed. It writes the artifacts under `evidence\hardening\`
and a run-stamped copy of the build manifest into the gitignored `.runtime\` lane.

It does **not** rewrite `shell\BUILD-MANIFEST.txt`. That is a tracked release input, generated
deliberately by `tools\release\generate_build_manifest.py --write` and pinned by
`tools\release\sync_release_manifest.py --write`; running the tests leaves the tree clean.

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
