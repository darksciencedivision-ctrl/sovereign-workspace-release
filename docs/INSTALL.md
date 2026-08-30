# Installing Sovereign Workspace

**Version 1.0.0-rc.1** · Windows only · EPC-01 P1-9

`tools\release\install.ps1` is the **only** supported install path. If you find another
procedure written down anywhere, it is out of date — this document is authoritative.

---

## Before you start

| Requirement | Check it with | Expected |
|---|---|---|
| Windows 10 or 11, x64 | — | — |
| Python 3.12 via the launcher | `py -3.12 --version` | `Python 3.12.x` |
| Python 3.14 via the launcher | `py -3.14 --version` | `Python 3.14.x` |
| Node.js 24 | `node --version` | `v24.x` |
| npm 11 | `npm --version` | `11.x` |
| Ollama | `ollama --version` | any recent version |

Both Python versions are needed and that is deliberate — SOVEREIGN and SOW are provisioned on
3.12, the Debate Table on 3.14, each from its own pinned lock. See `docs/SUPPORT-POLICY.md`.

You also need the install archive and its `.sha256` sidecar, together in one directory.

### Point Ollama at your model library

The workspace uses whatever models Ollama can see. If you have set `OLLAMA_MODELS`, make sure
it points at a real library:

```powershell
[Environment]::GetEnvironmentVariable('OLLAMA_MODELS','User')
```

If it names a directory with no `manifests\` folder in it, the workspace will start and report
every configured model missing. Unset it to use Ollama's default, or point it at your library.
**A running Ollama service does not pick up a change to this variable until it is restarted.**

---

## Install

```powershell
.\tools\release\install.ps1 -Dest "C:\SovereignWorkspace"
```

Add `-TargetDir` if you want desktop and Start Menu shortcuts. It refuses to overwrite an
existing shortcut.

The destination must be empty and must not be a drive root; the installer refuses both rather
than merging into whatever is already there.

### What it does, in order

1. **Verifies the archive against its sidecar** before reading a byte of its contents.
2. **Extracts it**, rejecting any entry whose path would escape the destination.
3. **Rewrites the configuration to your machine** — `shell\config\install.json`, every module
   adapter in `shell\modules\`, and the MCP registration in
   `modules\sow\.codex\config.toml` — so the installed copy refers to itself.
4. **Provisions three Python environments** from exact pinned locks: SOVEREIGN and SOW on
   3.12, Debate on 3.14. It then **proves the SOW gateway imports** in the environment it just
   built, and fails the install if it does not.
5. **Runs `npm ci`** for the SOVEREIGN UI.
6. **Provisions SOW through `install_sow.py`**, which installs with `--ignore-scripts` and
   fetches Electron as a **hash-verified** zip rather than letting a postinstall script
   download it unchecked. See `docs/ADR-005-...` for why.
7. **Writes `install-manifest.json`** — a per-file SHA-256 record of everything it placed.

Any step failing stops the install. There is no partial-success path.

---

## Verify

```powershell
.\tools\release\verify_install.ps1 -Dest "C:\SovereignWorkspace"
```

Re-hashes every path in the install manifest and reports anything that moved.

---

## Run

```powershell
py -3.12 -m shell.src
```

Then open <http://127.0.0.1:5180>. Use `--port <n>` if 5180 is taken.

The shell binds loopback only and refuses anything else. That is enforced in code, not
configuration.

### Expected service ports

| Module | Port | Health endpoint |
|---|---|---|
| SOVEREIGN | 5175 | `/v1/health` |
| Debate Table | 8700 | `/ready` |
| Sovereign Distillery | 5184 | `/health` |
| Token Center | 8765 | `/healthz` |
| Shell | 5180 | — |
| Ollama | 11434 | `/api/tags` |

`llama.cpp` on 5183 is an optional adapter. It ships declared but not installed, and the shell
shows it as **"Runtime not installed"** with the path it expects. That is the correct state,
not an error.

---

## Upgrade

```powershell
.\tools\release\upgrade.ps1 -Dest "C:\SovereignWorkspace"
```

Verifies the incoming artifact against its sidecar before touching anything, backs up your
state, moves the outgoing installation aside rather than deleting it, installs the new
version, and verifies it. **Nothing is removed** — rollback is moving the previous
installation back.

## Remove

```powershell
.\tools\release\uninstall.ps1 -Dest "C:\SovereignWorkspace"
```

Removes exactly the paths its manifest records. **Your state is kept by default** and its
location is printed; add `-PurgeData` to remove it as well, which lists what it deletes first.

## Your state

Runtime state lives under `%LOCALAPPDATA%\SovereignWorkspace\<module-id>`, outside the install
root, so it survives uninstall and upgrade. Back it up on its own with:

```powershell
.\tools\release\backup_state.ps1
```

See `docs/OPERATIONS.md` for what each module keeps there.

---

## If the install fails

See `docs/TROUBLESHOOTING.md`. The installer logs every step it takes, and the step that
failed is the one to read first.
