# SWS-CORRECTIVE-01 — baseline defect reproductions

**Run ID:** `SWS-CORRECTIVE-01-20260908T151625Z`
**Candidate at reproduction:** `52bcc931e6ebb0db24155758cf19d1cf592731fa` (clean tree)
**Host:** Windows 11 Home 10.0.26200, PowerShell 5.1.26100.9168, Python 3.12/3.14 via `py`, Node v24.20.0
**Executor model:** Opus 5 (`claude-opus-5`) — the model the operator requested.

Every reproduction below was executed on this host during this run, before any correction was
written. Fixtures live under `%TEMP%`; the operator's own installation and state were never
touched.

---

## L1 — upgrade displaces the controller it is still running from

`tools/release/upgrade.ps1:41` binds `$here = $PSScriptRoot`. Line 110 moves `$destRoot` — which
contains `$here` when the operator upgrades the installed copy — and line 117 then invokes
`install.ps1` through that former path.

Fixture: an installation holding the real `upgrade.ps1` plus fast stand-ins for the two
network-bound steps (L1 is a path-displacement defect, not an install defect), a verified
artifact outside the install, and a state root.

```
upgrade: moving the outgoing installation to ...\Sovereign Workspace.previous-1.0.0-...
upgrade: installing the new version
The term '...\Sovereign Workspace\tools\release\install.ps1' is not recognized as the name of a
cmdlet, function, script file, or operable program.
EXITCODE=
install dir exists: False
```

**Outcome: REPRODUCED.** The operator's launch path no longer exists, no automatic rollback ran,
and `$LASTEXITCODE` is empty — so the `if ($LASTEXITCODE -ne 0)` guards at lines 118 and 125
could not have reported the failure either.

Adjacent defects established by the same inspection:
- `& install.ps1` / `& verify_install.ps1` never set `$LASTEXITCODE`; those guards are inert.
- No dependency, disk-space, permission, or quiescence check precedes the move.
- An artifact stored under `$Dest` is moved away with the installation before it is consumed.
- No durable transaction record, so an interrupted upgrade cannot be diagnosed.

## L2 — backup reports COMPLETE while dropping a Windows-hidden file

`tools/release/backup_state.ps1:40` counts entries with `-Force`; line 72 archives with
`Compress-Archive -Path <root>\*`, whose wildcard does not match hidden entries.

```
FIXTURE files(-Force)=2
backup: capturing 2 file(s) from ...\state
backup: COMPLETE
  ENTRY STATE-BACKUP-INVENTORY.json
  ENTRY visible.txt
RESTORE_ERROR: Restore incomplete: inventory declares 2 file(s), 1 extracted
```

**Outcome: REPRODUCED** exactly as recorded: backup COMPLETE, `.hidden-config` absent from the
archive, restore found 1 captured file against an inventory of 2.

Adjacent defects established by the same inspection:
- The inventory is written into, and deleted from, the operator's live state root (line 66/76).
- The inventory carries a file count only: no per-file paths, lengths, or hashes.
- The archive is published under its final name before its contents are verified.
- Restore extracts into the destination before it can detect that the archive is short.

## L3 — a cancelled start publishes READY over the cancellation

`shell/src/states.py` `ModuleRunner.start()` runs `_readiness()` (up to `timeout_s`, 90 s for
SOW) and then unconditionally `self._set(READY)`. `cancel()` sets STOPPED but has no way to
invalidate the outstanding operation: there is no operation identity, and process ownership is
bound to the reusable module id.

`shell/tests/test_lifecycle_serialization.py` drives a real `ModuleRunner` with the slow probe
gated on a `threading.Event`, so the interleaving is deterministic rather than timing-dependent.

```
5 failed, 2 passed in 0.22s
FAILED ...::test_cancel_before_spawn_never_spawns
FAILED ...::test_cancel_during_readiness_cannot_publish_ready
FAILED ...::test_cancelled_start_does_not_publish_failed
FAILED ...::test_cancelled_start_does_not_stop_a_later_instance
FAILED ...::test_stop_during_startup_is_terminal
AssertionError: 'READY' != 'STOPPED'
```

**Outcome: REPRODUCED.** `test_cancel_during_readiness_cannot_publish_ready` is the recorded
STOPPED-to-stale-READY case.

## Q1 — an unrelated "unknown" exempts an unsupported factual assertion

`modules/sovereign/sovereign_product/quality.py:93` gates the no-evidence refusal on
`UNKNOWN_LANGUAGE.search(text)`, a regex that matches the bare word `unknown` anywhere in the
answer.

```
>>> validate_quick_response(
...     'The configured model is imaginary-model:999b. Its release date is unknown.',
...     None, query='What model is configured?')
(True, None)
```

**Outcome: REPRODUCED** exactly as recorded.

## R1 — model consistency gate fails

```
check_model_consistency: FAIL (2026-09-08T15:13:53Z)
  PROBLEM README: Primary reasoner says `qwen3:8b` but SYSTEM_MANIFEST MODELS.PRIMARY_REASONER = `qwen2.5:3b-instruct`
  PROBLEM README: Adversarial challenger says `granite4.2:8b` but ... = `granite4.2:3b`
  PROBLEM README: Critic says `dolphin3:8b` but ... = `sam860/dolphin3-llama3.2:3b`
  PROBLEM README: Synthesizer says `deepseek-r1:8b` but ... = `llama3.2:3b`
  PROBLEM hierarchy: king_synthesizer.model = `deepseek-r1:8b` but ... = `llama3.2:3b`
  PROBLEM hierarchy: cross_channel.critique.model = `dolphin3:8b` but ... = `sam860/dolphin3-llama3.2:3b`
EXIT=1
```

**Outcome: REPRODUCED** — four README and two hierarchy mismatches, as recorded.

## R2 — release manifest rejects the committed bytes

```
release_manifest_check: FAIL (1 problems)
  PROBLEM batch_files: content hash mismatch at shell/BUILD-MANIFEST.txt
    (enumerated 6d713ad1..., measured 30b1ed90...)
EXIT=1
```

**Outcome: REPRODUCED** on committed bytes, with the checker already hashing the file
content-only (its `# utc:` stamp stripped), so the drift is real content drift.

### R2 root cause (established this run, not assumed)

1. `shell/BUILD-MANIFEST.txt` is a **tracked release input that a test regenerates**:
   `shell/tests/test_zz_evidence.py::TestBuildManifest::test_generate_build_manifest` walks
   `shell/` and rewrites the file on every suite run. Routine verification therefore mutates a
   tracked release input — the condition §5.3 forbids.
2. Tracing every revision of the file against the pin:

   | revision | entries | content hash | note |
   |---|---|---|---|
   | `715ce7f8` (HEAD~2) | 102 | `30b1ed90…` | committed suite output |
   | `7c37b3f3` | 102 | `1b31270d…` | committed suite output |
   | `27bfc848` | 99 | `6d713ad1…` | **the revision the pin still names** |

   The pin in `RELEASE-MANIFEST.json` was last regenerated at `27bfc848`. The two later
   `chore(evidence): …regenerated…` commits committed the test's fresh output **without
   regenerating the release identity**, so the manifest has described a superseded file ever
   since.
3. The committed 102-entry manifest additionally enumerates five files that are not part of the
   product and are not tracked by git — `shell/modules/{debate,distillery,sovereign,sow,tokencenter}.json.pre-rebase`,
   build residue left by `tools/release/rebase_adapters.py` and `export-ignore`d by
   `.gitattributes:38`. The manifest therefore describes a developer working tree rather than
   the candidate.

The repair is consequently: stop the suite writing a tracked release input, exclude untracked
residue from the enumeration, and regenerate the pin through the legitimate generator — not a
hand-edited hash.

## C1 — the launch paths disagree

Direct comparison of `Sovereign Workspace.bat`, `Start-Sovereign.ps1`, and `Start-Shell.ps1`:

- The batch file `cd`s into the worktree and invokes `Start-Shell.ps1` directly, so the outer
  preflight in `Start-Sovereign.ps1` never runs, and neither `-Port`, `-NoBrowser` nor
  `-CheckOnly` can be reached through it.
- `Start-Sovereign.ps1:15,177` state that "Start-Shell.ps1 refuses in light mode".
  `Start-Shell.ps1:83-94` only prints advice and continues. The blocking claim is false.
- `Start-Sovereign.ps1:69,73` sets `GIT_OPTIONAL_LOCKS` and then unconditionally
  `Remove-Item`s it, destroying a pre-existing caller value.
- `Start-Shell.ps1:115` treats *any* listener on the port as the shell being up; no service
  identity is checked.
- `Start-Sovereign.ps1:193` exits 0 from `-CheckOnly` even when it has just reported a
  blocking failure such as a missing interpreter.
- `Start-Sovereign.ps1:110` splits a single `nvidia-smi` CSV row on `,` and indexes `[0]`/`[1]`;
  a second GPU changes the shape. When `--query-compute-apps` fails or returns nothing the
  script reports "workspace holders none" — an unobservable state rendered as a clean one.

## C2 — the Python prerequisite disagrees across surfaces

- `README.md:12` — "Python 3.12, reachable as `py -3.12`". No mention of 3.14.
- `docs/INSTALL.md:15-16` — requires both 3.12 and 3.14.
- `tools/release/install.ps1:113` — `py -3.14 -m venv` for Debate; a missing 3.14 aborts the install.
- `.github/workflows/windows.yml:45-48` — provisions **3.12 only**.

## C3 — the SOW readiness receipt is written where nothing declares it

- `modules/sow/apps/desktop/main.js:3301` writes
  `<install>/modules/sow/.runtime/receipts/SHELL-LIVE-READY.json` on every normal launch.
- `shell/modules/sow.json` `runtime_writes` declares only `${state_root}/.recovery` and
  `${state_root}/receipts`; `${root}/.runtime/receipts` is declared nowhere.
- The write therefore lands **inside the installation**, so declared writes do not match
  observed writes and normal startup cannot survive a non-writable installation directory.

## Additional finding established this run — CI cannot pass its own clean-room stage

`tools/ci/run_ci.ps1:135` runs `install.ps1 -Dest <temp>` with **no `-Artifact`**, so
`install.ps1:19` resolves `release-artifacts/sovereign-workspace-<version>-install.zip`. Nothing
in `.github/workflows/windows.yml` or `run_ci.ps1` ever builds that artifact, and
`release-artifacts/` is untracked build output. The lane's clean-room stage consumes an artifact
that its own run never produces. `run_ci.ps1:44` additionally reads `$LASTEXITCODE` after `&`-ing
a `.ps1`, which does not set it — the same stale-status defect as L1.
