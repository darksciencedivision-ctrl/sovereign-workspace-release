# Operating Sovereign Workspace

**Version 1.0.0-rc.1** · EPC-01 P4-9

Day-to-day operation, and where to look when you need to know what the system is doing.

The product transmits nothing about itself (`docs/ADR-006-no-telemetry.md`), so **everything
below is the whole of what exists.** There is no dashboard elsewhere and no support channel
watching for problems.

---

## Checking that the system is healthy

Each service answers a health endpoint on loopback. These are the exact probes and the exact
shapes they return.

```powershell
Invoke-RestMethod http://127.0.0.1:5175/v1/health   # SOVEREIGN
Invoke-RestMethod http://127.0.0.1:8700/ready       # Debate Table
Invoke-RestMethod http://127.0.0.1:5184/health      # Distillery
Invoke-RestMethod http://127.0.0.1:8765/healthz     # Token Center
```

**SOVEREIGN** returns `status: "ok"` when healthy, along with `configured_models_ready`,
`missing_configured_models`, `model_service_reachable`, and the `deep_model_slate` it will
actually use. If `missing_configured_models` is non-empty, the models named in it are not in
your Ollama library — that is the first thing to check when a cycle will not start.

**Debate** returns one of three states, and the distinction matters:

| `status` | HTTP | Meaning |
|---|---|---|
| `ready` | 200 | Every seat's model is installed and within the ceiling |
| `degraded` | 503 | A seat cannot take its turn — either its model is missing, **or** it is installed but above the operator's 8B ceiling |
| `unavailable` | 503 | Ollama itself could not be reached |

`degraded` with an empty `missing_models` means the ceiling refused a model that is installed.
The `seats` array names which one and gives a `ceiling_reason`.

**Distillery** returns `{"ok": true, "status": "idle", "compute": false}`. It is
status-only in this release and does no compute on open.

---

## The model ceiling

The operator's ruling caps local models at the **8B nameplate class**. A model above it stays
installed and visible but is refused for selection, with the reason stated rather than the
model silently hidden.

This is reported, never silently applied. Both the Debate `/ready` seats array and the SOW
pane picker name the model and say why it cannot run.

To see what Ollama has:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags | Select-Object -ExpandProperty models |
  Select-Object name, @{n='GB';e={[math]::Round($_.size/1GB,2)}}
```

---

## Where state lives

Runtime state lives **outside the install root**, under
`%LOCALAPPDATA%\SovereignWorkspace\<module-id>` — one directory per module, never shared.

| Module | State directory | Holds |
|---|---|---|
| SOVEREIGN | `SovereignWorkspace\sovereign` | `runtime\`, `published\`, `library\queues\`, `logs\` |
| SOW | `SovereignWorkspace\sow` | `.recovery\`, `receipts\`, `store\` |
| Debate | `SovereignWorkspace\debate` | `logs\` |
| Distillery | `SovereignWorkspace\distillery` | `logs\` |
| Token Center | `SovereignWorkspace\tokencenter` | `data\` (the SQLite database) |

Each module is told where its own state root is through `SOVEREIGN_WORKSPACE_STATE`, and the
shell creates the declared directories before launching it. A module may write only inside the
install root or inside **its own** state root; a declaration naming anywhere else is refused
as a configuration error, so one module cannot reach another's state.

**One exception, stated because it is one:** the Debate Table's `config.json` still lives
beside its code. It is a seeded document the application rewrites in place rather than pure
runtime state, so relocating it requires the installer to place a copy in the state root
first. It is the only declared write still inside the install tree.

### Backing it up

```powershell
.\tools\release\backup_state.ps1
```

Writes one archive with a SHA-256 sidecar and prints both paths. Restore with
`restore_state.ps1 -Archive <path>`, which verifies the sidecar before writing anything and
never deletes the state it replaces.

`upgrade.ps1` takes a state backup automatically before it does anything else.

---

## Logs

Logging is thin in this release and you should know that going in: four files use Python's
`logging` module and most diagnostic output is `print()` to the process's stdout. There is no
structured logging, no log levels you can configure, no rotation, and no single destination.
Tracked as P4-6.

In practice this means: **run the services where you can see their console output**, and
capture it when reproducing a problem. Once a service's stdout is gone, so is the record.

The install itself is the exception — `install_sow.py` logs every step to a file and exits
non-zero on any mismatch, so a failed install leaves a readable trail.

---

## Verifying an installation has not drifted

```powershell
.\tools\release\verify_install.ps1 -Dest "C:\SovereignWorkspace"
```

Re-hashes every path recorded in `install-manifest.json`. Run it if behaviour changes and you
do not know why.

---

## Release-integrity checks

These run against the repository rather than an installation, and are what the build itself
must pass. All five exit 0 on a good tree:

```powershell
py -3.12 tools\release\release_manifest_check.py
py -3.12 tools\release\check_model_consistency.py
py -3.12 tools\release\check_governance_bom.py
py -3.12 tools\release\check_node_advisories.py
py -3.12 tools\release\package_boundary_gate.py --from-commit HEAD
```

`check_node_advisories` runs `npm audit` against both Node dependency trees with a threshold
of zero. `package_boundary_gate --from-commit` scans the **distribution**, not the working
tree — a working tree also holds `.venv`, `node_modules` and caches that no recipient receives,
and scanning it produces tens of thousands of meaningless violations.

---

## Running the tests

The whole product, from the repository root:

```powershell
py -3.12 -m pytest -q
```

A single module, from its own directory:

```powershell
cd modules\sow
py -3.12 -m pytest -q
```

Both work, and they are not equivalent — several defects appear **only** in the whole-product
run, because that is the only invocation where modules share a process and a `PYTHONPATH`.
Run the whole product before believing a change is safe.

The Node suites are separate:

```powershell
cd modules\sow\apps\desktop
npm test

cd modules\sovereign\ui\ui_shell
npm test
npm run typecheck
```

---

## Stopping cleanly

Stop services through the shell where you started them through the shell. If you started one
by hand, stop it by its PID — the shell's containment covers what it launched, not what you
launched beside it.

```powershell
Get-NetTCPConnection -State Listen -LocalPort 5175,8700,5184,8765 -ErrorAction SilentlyContinue |
  Select-Object LocalPort, OwningProcess
```
