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
| Debate | `SovereignWorkspace\debate` | `config.json`, `logs\` |
| Distillery | `SovereignWorkspace\distillery` | `logs\` |
| Token Center | `SovereignWorkspace\tokencenter` | `data\` (the SQLite database) |

Each module is told where its own state root is through `SOVEREIGN_WORKSPACE_STATE`, and the
shell creates the declared directories before launching it. A module may write only inside the
install root or inside **its own** state root; a declaration naming anywhere else is refused
as a configuration error, so one module cannot reach another's state.

**Nothing the product writes at runtime is inside the install tree.** The Debate Table's
`config.json` is the interesting case: the application rewrites it when seats are edited, and
it used to live beside the code — a git-tracked file the product writes to, so merely using
the Debate Table dirtied the release candidate. The shipped copy is now a **seed**: it is
copied into the state root the first time the module starts and read from there afterwards.
Your edits are never overwritten by the shipped one, and the shipped one is never written to.

If you want to reset the Debate Table's configuration to the shipped defaults, delete
`SovereignWorkspace\debate\config.json` and start it again.

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

Every module's output is captured and **persisted**, one log per module, outside the install
root:

```
%LOCALAPPDATA%\SovereignWorkspace\<module>\logs\<module>.log
%LOCALAPPDATA%\SovereignWorkspace\shell\logs\shell.log
```

Each rotates at 2 MB and keeps five generations, so one chatty module cannot fill a disk;
the ceiling is 10 MB per module. The live file always holds the most recent output.

**Module output is redacted before it is written.** The persistence point is inside the same
buffer that serves `/api/logs`, after redaction has run - so a secret the API hides is not
sitting in the file in the clear. There is no second, unredacted copy anywhere.

Set the shell's own verbosity with `SOVEREIGN_LOG_LEVEL` (`DEBUG`, `INFO`, `WARNING`,
`ERROR`); it defaults to `INFO`, and a name it does not recognise falls back to `INFO` with a
warning rather than failing to start. The shell logs to its file and to stderr together.

```powershell
$env:SOVEREIGN_LOG_LEVEL = 'DEBUG'
Get-Content "$env:LOCALAPPDATA\SovereignWorkspace\shell\logs\shell.log" -Tail 50 -Wait
```

If the log directory cannot be written, the shell still starts and still logs to the console -
losing the record is a degradation, not an outage - and says so in a warning.

What is still missing, so the absence is not read as completeness: the modules themselves
write unstructured text rather than levelled or structured records, so what lands in a
module's log is whatever that module chose to print. Filtering by severity within a module's
log is not possible. The shell's own records are levelled; its modules' are not.

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

### Attribution files

`SBOM.json` is generated from the six lock files, and `NOTICE` from the SBOM. Neither is
edited by hand. `build_release.ps1` checks both before it cuts a single archive and fails the
build if either has drifted from its sources.

```powershell
py -3.12 tools\release\generate_sbom.py      # then always:
py -3.12 tools\release\generate_notice.py
```

Run them in that order after any dependency change, then re-sync `RELEASE-MANIFEST.json`.
`--check` on either reports drift without writing anything.

The SBOM records each lock file's path and SHA-256, so its provenance is checkable rather
than asserted. It is generated from locks and not from this machine's virtual environments,
which matters for more than tidiness: the previous version listed 62 packages the product does
not contain, and an over-reporting SBOM produces vulnerability findings against software that
is not there.

`check_node_advisories` runs `npm audit` against both Node dependency trees with a threshold
of zero. `package_boundary_gate --from-commit` scans the **distribution**, not the working
tree — a working tree also holds `.venv`, `node_modules` and caches that no recipient receives,
and scanning it produces tens of thousands of meaningless violations.

### Comparing two releases

Every release artifact carries the commit it was cut from — a pax global header in a tar, the
archive comment in a zip. That is deliberate provenance, and it means **two archives of
identical content cut at different commits have different sha256**. Diffing whole-file hashes
between releases therefore shows every artifact as changed when most have not.

To ask the other question:

```powershell
py -3.12 tools\release\archive_content_hash.py --compare <old.zip> <new.zip>
```

It reports both whole-file and content digests, names the commit each was cut from, and says
`SAME CONTENT` or `DIFFERENT CONTENT`. The content digest covers entry names and bodies only —
no timestamps, no compression metadata, no commit stamp. Exit code 1 means the contents really
differ.

Without an argument pair it prints a content digest per archive, which is the value to record
if you want to track what actually changed between releases.

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
