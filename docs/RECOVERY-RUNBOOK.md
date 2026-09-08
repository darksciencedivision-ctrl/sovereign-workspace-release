# Recovery runbook

**Version 1.0.0-rc.1** · SWS-CORRECTIVE-01 workstream 4

What to do when something has gone wrong. Every procedure here has been exercised by
`tools\acceptance\run_acceptance.ps1` or by the test suites named beside it; none of it is
advice that has never been run.

Read the first section before you need it. The rest is reference.

---

## 0. Before anything else

1. **Stop the shell.** Ctrl+C in the launcher window, or close it. The shell holds every module
   in a Windows Job Object, so its modules stop with it.
2. **Do not delete anything.** None of the product's own recovery tooling deletes: upgrade moves
   the previous installation aside, restore moves the displaced state aside, uninstall keeps your
   state by default. If you delete by hand first, those routes stop working.
3. **Find your state root.** It is `%LOCALAPPDATA%\SovereignWorkspace` unless
   `SOVEREIGN_WORKSPACE_STATE` is set. Your work is there, not in the installation.

---

## 1. An upgrade failed

The upgrade is a transaction and reports which phase it reached. **Read its exit code** — it
tells you what state the machine is in:

| Exit | Meaning | What is on disk |
|---|---|---|
| 0 | upgraded and verified | new install at `-Dest`; previous kept beside it |
| 2 | **refused before any change** | nothing moved; your installation is untouched |
| 3 | failed before the cutover | nothing moved; your installation is untouched |
| 4 | failed and **rolled back** | your previous installation is back at `-Dest`; the failed incoming tree is kept as evidence |
| 5 | **rollback itself failed** | see below — the script printed the exact paths |

**Exit 2 or 3.** Nothing to recover. Fix what it named and re-run.

**Exit 4.** Already recovered. The transaction root holds `failed-incoming-<stamp>` and the
journal; keep them if you want to know why, delete them when you are done. Verify with:

```powershell
.\tools\release\verify_install.ps1 -Dest "C:\SovereignWorkspace"
```

**Exit 5 — rollback did not complete.** The script printed the exact surviving locations. Do
this, substituting the paths it named:

```powershell
# 1. Confirm the previous installation is intact.
Get-ChildItem "C:\SovereignWorkspace.previous-<version>-<stamp>" | Select-Object -First 5

# 2. Move anything still sitting at the destination out of the way (do not delete it).
Move-Item "C:\SovereignWorkspace" "C:\SovereignWorkspace.failed-<stamp>"

# 3. Put the previous installation back.
Move-Item "C:\SovereignWorkspace.previous-<version>-<stamp>" "C:\SovereignWorkspace"

# 4. Prove it.
.\tools\release\verify_install.ps1 -Dest "C:\SovereignWorkspace"
```

**If the state schema changed.** The upgrade says so on completion, and refuses without
`-AcceptStateSchemaChange` when it would. Moving the binaries back does **not** reverse a state
migration. To go back you must also restore the pre-upgrade snapshot the transaction took:

```powershell
.\tools\release\restore_state.ps1 -Archive "<transaction root>\state-pre-upgrade-<stamp>.zip" -Force
```

**Diagnosing an interrupted upgrade.** `upgrade-journal.jsonl` in the transaction root records
every phase with its outcome, so you never have to guess which move completed:

```powershell
Get-Content "<transaction root>\upgrade-journal.jsonl" | ForEach-Object { $_ | ConvertFrom-Json } |
    Format-Table utc, phase, status -AutoSize
```

---

## 2. A backup refused

**"the state root is not quiescent".** Something is still writing. This is an offline snapshot
contract and it proved the state was live rather than copying it mid-write. Stop the shell and
every module, then re-run. The refusal names the files that were held open.

`-AllowNonQuiescent` captures anyway and labels the archive
`online-uncoordinated (NOT a consistent snapshot)` in its inventory. That removes the refusal,
not the inconsistency: a SQLite database captured that way may need repair.

**"the state root holds entries this contract cannot capture".** A junction or symbolic link is
present. It is refused rather than silently followed or dropped — following it would copy
something from outside your state, and dropping it would lose data while reporting success.
Resolve it, or pass `-AllowIncomplete` to capture the rest with the omission recorded in the
inventory.

**"FAILED verification".** The archive did not reproduce the state root and was **not**
published. Nothing occupies the successful-backup name. Investigate the files it listed.

---

## 3. A restore refused

Restore validates in this order and stops at the first failure, **before writing anything**:

1. archive vs its `.sha256` sidecar
2. the inventory is present and is schema `sovereign.state-backup.v2`
3. every archive path is relative, non-escaping, non-duplicate, non-case-colliding
4. the entry set matches the inventory exactly
5. every extracted file re-hashes to its inventory entry

Only then is the existing state displaced — moved aside, never deleted.

**"this archive carries no inventory".** It predates the v2 contract. Its completeness cannot be
checked, so a restore from it cannot be called verified. `-AllowUnverifiedLegacyArchive`
restores it and labels the result `NOT VERIFIED`.

**"already holds N file(s)".** Restoring over live state needs `-Force`. The existing state is
moved to `<state root>.displaced-<stamp>`; move it back if you change your mind.

**"FAILED to place the verified state".** The verified restore is staged and was not discarded;
the previous state has been put back. Both paths are printed. Nothing was lost.

---

## 4. The shell will not start

Run the preflight, which starts nothing:

```powershell
.\Start-Shell.ps1 -CheckOnly
```

Exit **0** means nothing blocking; exit **1** means it found something and named it. Blocking
conditions are only these four:

- `shell\src\__main__.py` not beside the launcher — you are in the wrong folder.
- No `py` launcher on PATH — install Python 3.12.
- `py -3.12` unavailable — the shell is pinned to it.
- The port is already held — the preflight names the process and pid. Use `-Port <n>`.

Everything else it prints is advisory and does not stop a launch. In particular **light mode has
never blocked startup**; you get the light theme variant.

**"the service on port N is not this shell".** Something else answered `/api/shell-info`. The
launcher refuses to hand you a browser tab pointed at it. Stop that process or use another port.

---

## 5. A module is stuck, or shows a stale state

- **STARTING that never becomes READY.** Press Stop. Stop supersedes the outstanding start, so
  the module cannot later publish READY over your cancellation, and the process that start
  created is stopped rather than left behind.
- **FAILED with a reason you want to keep reading.** Polling no longer erases it. A diagnostic
  failure — `HEALTH_CHECK_FAILED`, `IDENTITY_MISMATCH`, `PROCESS_START_FAILED` — survives until
  you start the module again. Only `EXTERNAL` and `PORT_OCCUPIED_UNRECOGNIZED` clear on their
  own, because those are statements about the port rather than about the last start.
- **`PORT_UNAVAILABLE (owned by pid N)`.** Something else holds the port. The shell names the
  pid rather than timing out and blaming the module.
- **Processes left behind.** They should not be: modules run inside the shell's Job Object.
  `.\Start-Shell.ps1 -CheckOnly` lists any process still running out of this tree.

---

## 6. Recovering after a crash

The recovery contract, stated so you know what to expect:

- **Durable:** any job whose record reached `completed`, `accepted`, `rejected`, `failed` or
  `cancelled`, together with its persisted answer and raw provenance.
- **May be lost:** a job that was still `running`, its partial output, and streamed progress. It
  must come back as a terminal failure or be absent — never stuck in `running` with no owner.
- **Never acceptable:** a corrupt or truncated database, a duplicated committed answer, or a
  committed answer whose bytes changed. If you see one, restore from your last verified backup
  and keep the damaged state root for diagnosis.

To check the store yourself, without asking the product whether it is happy:

```powershell
py -3.12 -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('PRAGMA integrity_check').fetchone())" "$env:LOCALAPPDATA\SovereignWorkspace\sovereign\runtime\sovereign.db"
```

`ok` means the database is structurally sound.

---

## 7. Starting over without losing your work

```powershell
.\tools\release\uninstall.ps1 -Dest "C:\SovereignWorkspace"          # keeps your state
.\tools\release\install.ps1   -Dest "C:\SovereignWorkspace" -Artifact <artifact>
.\tools\release\restore_state.ps1 -Archive <your backup> -Force      # only if you need it
```

Uninstall keeps state by default. `-PurgeData` removes it as well, and names exactly what it
will delete before doing so. There is no undo for `-PurgeData` other than a backup.
