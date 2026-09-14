# EPC-01 P1-6 - the whole verification suite, as one script.
#
# The point of this file is that CI and a developer run THE SAME THING. A lane definition that
# inlines its own list of steps drifts from what anyone runs locally, and the drift is only
# discovered when the lane goes green on a tree that is broken. .github/workflows/windows.yml
# invokes this script and does almost nothing else.
#
# Every stage prints a PASS/FAIL/SKIP line and the script exits non-zero if any stage failed,
# after running the rest. Stopping at the first failure would hide the other four.
#
# Stages that mutate the machine - installing packages, writing outside the repo - are OPT-IN
# via -IncludeCleanRoom. They are skipped by default and the skip is REPORTED, never silent:
# a suite that quietly does less than it claims is worse than one that does less loudly.

[CmdletBinding()]
param(
    # Run the clean-room install (V-1). Installs Python and Node packages into a temporary
    # destination, so it is off unless asked for.
    [switch]$IncludeCleanRoom,
    # Skip the Node suites when node_modules has not been provisioned.
    [switch]$SkipNode,
    [string]$Python = 'py',
    [string]$PythonVersion = '-3.12',
    # The commit the release artifact is cut from. SWS-CORRECTIVE-01 workstream 2.5: the
    # version, the manifest and the packaged bytes must all come from ONE candidate, so the
    # commit is named once here and the summary reports which one it was.
    [string]$BuildCommit = 'HEAD'
)

$ErrorActionPreference = 'Continue'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
# F-064(d): the gates are invoked with repo-relative arguments (--file modules/..., --registry
# tools/...) and the scripts default to `--root .`, but only the pytest stage used to Push-Location
# to the repo root. Run the whole suite from the repo root so gates resolve their inputs the same
# way no matter what CWD invoked this script. Child processes (Invoke-Script) inherit this CWD.
Set-Location -LiteralPath $repoRoot
$results = New-Object System.Collections.Generic.List[object]

function Invoke-Stage {
    param(
        [string]$Name,
        [scriptblock]$Body,
        [string]$SkipReason
    )
    if ($SkipReason) {
        Write-Host ("SKIP  {0} - {1}" -f $Name, $SkipReason)
        $results.Add([pscustomobject]@{ Stage = $Name; Result = 'SKIP'; Detail = $SkipReason })
        return
    }
    Write-Host ("---- {0}" -f $Name)
    $started = Get-Date
    $script:StageExit = $null
    try {
        & $Body
        # SWS-CORRECTIVE-01 workstream 2. `& script.ps1` does NOT set $LASTEXITCODE, so a stage
        # that invoked a PowerShell script read whatever the PREVIOUS external command had left
        # there - the same stale-status defect as L1 in upgrade.ps1. A stage body that runs a
        # .ps1 now sets $script:StageExit itself through Invoke-Script; only bodies that end in
        # a genuine external command fall through to $LASTEXITCODE.
        if ($null -ne $script:StageExit) { $code = $script:StageExit }
        elseif ($null -eq $LASTEXITCODE) { $code = 0 }
        else { $code = $LASTEXITCODE }
    }
    catch {
        Write-Host ("      terminating error: {0}" -f $_.Exception.Message)
        $code = 1
    }
    $seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
    if ($code -eq 0) {
        Write-Host ("PASS  {0} ({1}s)" -f $Name, $seconds)
        $results.Add([pscustomobject]@{ Stage = $Name; Result = 'PASS'; Detail = "${seconds}s" })
    } else {
        Write-Host ("FAIL  {0} (exit {1}, {2}s)" -f $Name, $code, $seconds)
        $results.Add([pscustomobject]@{ Stage = $Name; Result = 'FAIL'; Detail = "exit $code" })
    }
}

function Invoke-Py {
    param([string[]]$ScriptArgs)
    & $Python $PythonVersion @ScriptArgs
}

function Invoke-Script {
    <#
      Run a PowerShell script as a CHILD PROCESS and record its REAL exit code.

      A stage body cannot use `& script.ps1` and then read $LASTEXITCODE: that variable belongs
      to the last external command, and a .ps1 invoked with `&` never sets it. A child
      powershell.exe does.
    #>
    param([string]$Script, [string[]]$ScriptArgs)
    $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if (-not (Test-Path -LiteralPath $psExe -PathType Leaf)) { $psExe = 'powershell.exe' }
    $quoted = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $Script + '"'))
    foreach ($a in $ScriptArgs) {
        if ($a -match '[\s"]') { $quoted += '"' + ($a -replace '"', '\"') + '"' }
        else { $quoted += $a }
    }
    $p = Start-Process -FilePath $psExe -ArgumentList $quoted -NoNewWindow -Wait -PassThru
    $script:StageExit = [int]$p.ExitCode
}

Write-Host ("Sovereign Workspace CI - {0}" -f $repoRoot)
$headCommit = (& git -C $repoRoot rev-parse HEAD).Trim()
$resolvedBuildCommit = (& git -C $repoRoot rev-parse $BuildCommit).Trim()
Write-Host ("working checkout: {0}" -f $headCommit)
Write-Host ("build commit:     {0}" -f $resolvedBuildCommit)
$commitMismatch = ($resolvedBuildCommit -ne $headCommit)
if ($commitMismatch) {
    # Workstream 2.5 / F-061: the artifact and the tests must describe ONE candidate. Every stage
    # (including the boundary gate, hard-wired to --from-commit HEAD) runs against the working
    # checkout, so a -BuildCommit other than HEAD means this run cannot qualify that artifact. It
    # is a release BLOCKER, not merely a warning: previously the run still printed
    # "RELEASE-QUALIFYING: yes, for commit <BuildCommit>" although nothing tested that commit.
    Write-Host ""
    Write-Host ("WARNING: the artifact will be cut from {0} while these tests run against the " -f $resolvedBuildCommit)
    Write-Host  "         working checkout. Those are different candidates; this run cannot"
    Write-Host  "         qualify the artifact. Check out the build commit and re-run."
}
Write-Host ""

# --- 1. release gates -------------------------------------------------------------------------
# These are the checks the build itself must pass, and they are cheap, so they run first: a
# manifest that does not describe the tree makes every later result questionable.
# SWS-CORRECTIVE-01 workstream 2.6: the list is the WHOLE set of release gates, not the subset
# that happened to be here. generate_build_manifest and sync_release_manifest are new and close
# R2 at its source - the first fails when shell/BUILD-MANIFEST.txt stops describing the tracked
# tree, the second when its pin in RELEASE-MANIFEST.json stops describing the manifest. The
# provenance, innerhtml and model-projection gates existed and were simply never run here.
$gates = @(
    'tools\release\generate_build_manifest.py --check',
    'tools\release\sync_release_manifest.py --check',
    'tools\release\release_manifest_check.py',
    'tools\release\generate_model_projection.py --check',
    'tools\release\check_model_consistency.py',
    'tools\release\check_governance_bom.py',
    'tools\release\generate_sbom.py --check',
    'tools\release\generate_notice.py --check',
    'tools\release\provenance_cross_hash_check.py --registry tools/release/module_source_registry.json',
    'tools\release\generate_module_provenance.py --check',
    # F-071: every Python lock the installer or this lane consumes carries --hash pins, so pip can
    # verify downloaded bytes. install.ps1 refuses an unhashed lock; this gate fails the build first.
    'tools\release\hash_python_locks.py --check',
    'tools\release\innerhtml_sink_audit.py --file modules/sow/apps/desktop/renderer/renderer.js --file modules/tokencenter/static/app.js --ledger tools/release/innerhtml_audit.json'
)
foreach ($gate in $gates) {
    $parts = $gate -split ' '
    $script = Join-Path $repoRoot $parts[0]
    $rest = @($parts | Select-Object -Skip 1)
    Invoke-Stage -Name ("gate: {0}" -f (Split-Path $parts[0] -Leaf)) -Body {
        Invoke-Py (@($script) + $rest)
    }
}

# npm audit against both Node trees, threshold zero.
Invoke-Stage -Name 'gate: check_node_advisories' -Body {
    Invoke-Py @((Join-Path $repoRoot 'tools\release\check_node_advisories.py'))
}

# --- 2. the boundary gate ----------------------------------------------------------------------
# --from-commit scans the DISTRIBUTION, not the working tree. A working tree also holds .venv,
# node_modules and caches that no recipient receives, and scanning it produces tens of thousands
# of meaningless violations.
Invoke-Stage -Name 'boundary gate (distribution)' -Body {
    Invoke-Py @((Join-Path $repoRoot 'tools\release\package_boundary_gate.py'), '--from-commit', 'HEAD')
}

# --- 3. the Python suites ----------------------------------------------------------------------
# From the REPOSITORY ROOT, deliberately. Several defects appear only in the whole-product run,
# because that is the only invocation where the modules share a process and a PYTHONPATH.
Invoke-Stage -Name 'pytest (whole product, from repo root)' -Body {
    Push-Location $repoRoot
    try { Invoke-Py @('-m', 'pytest', '-q') } finally { Pop-Location }
}

# --- 4. the Node suites ------------------------------------------------------------------------
$nodeTrees = @(
    @{ Path = 'modules\sow\apps\desktop'; Commands = @(, @('test')) },
    @{ Path = 'modules\sovereign\ui\ui_shell'; Commands = @(@('test'), @('run', 'typecheck')) }
)
foreach ($tree in $nodeTrees) {
    $full = Join-Path $repoRoot $tree.Path
    $skip = $null
    if ($SkipNode) {
        $skip = '-SkipNode was passed'
    } elseif (-not (Test-Path -LiteralPath (Join-Path $full 'node_modules'))) {
        $skip = 'node_modules is not provisioned; run npm ci in this tree first'
    }
    foreach ($command in $tree.Commands) {
        $label = 'npm {0} ({1})' -f ($command -join ' '), $tree.Path
        Invoke-Stage -Name $label -SkipReason $skip -Body {
            Push-Location $full
            try { & npm @command } finally { Pop-Location }
        }
    }
}

# --- 5. the release artifact, then the clean-room install (V-1) ---------------------------------
#
# SWS-CORRECTIVE-01 workstream 2.4. The clean-room stage ran `install.ps1 -Dest <temp>` with no
# -Artifact, so install.ps1 resolved `release-artifacts\sovereign-workspace-<version>-install.zip`
# - a path nothing in this script or in .github/workflows/windows.yml ever produced, and one that
# `release-artifacts/` being untracked build output guarantees is absent on a fresh checkout. The
# stage consumed an artifact its own run never built. It is built here first, from the SAME
# commit the rest of the run verified, and the install is pointed at it explicitly so it can
# never silently pick up a stale archive left in the output directory.
$cleanRoomSkip = $null
if (-not $IncludeCleanRoom) {
    $cleanRoomSkip = 'not requested; pass -IncludeCleanRoom (builds the artifact, installs Python and Node packages)'
}

$artifactDir = Join-Path ([IO.Path]::GetTempPath()) ("sovereign-artifacts-" + [Guid]::NewGuid().ToString('N').Substring(0, 8))
$version = (Get-Content -Raw -LiteralPath (Join-Path $repoRoot 'VERSION.json') | ConvertFrom-Json).version
$artifact = Join-Path $artifactDir "sovereign-workspace-$version-install.zip"

Invoke-Stage -Name 'build the release artifact' -SkipReason $cleanRoomSkip -Body {
    Invoke-Script (Join-Path $repoRoot 'tools\release\build_release.ps1') `
                  @('-OutputDir', $artifactDir, '-Commit', $BuildCommit)
}

$installSkip = $cleanRoomSkip
if (-not $installSkip -and -not (Test-Path -LiteralPath $artifact)) {
    # A release-required stage that cannot run is NOT a pass. It is recorded as a skip with the
    # exact reason, and the summary refuses to qualify the run.
    $installSkip = "the release artifact was not produced at $artifact"
}
$destination = Join-Path ([IO.Path]::GetTempPath()) ("sovereign-cleanroom-" + [Guid]::NewGuid().ToString('N').Substring(0, 8))
Invoke-Stage -Name 'clean-room install' -SkipReason $installSkip -Body {
    Invoke-Script (Join-Path $repoRoot 'tools\release\install.ps1') `
                  @('-Dest', $destination, '-Artifact', $artifact)
}
Invoke-Stage -Name 'clean-room verify' -SkipReason $installSkip -Body {
    Invoke-Script (Join-Path $repoRoot 'tools\release\verify_install.ps1') @('-Dest', $destination)
}

# --- summary -----------------------------------------------------------------------------------
Write-Host ""
Write-Host "================ CI SUMMARY ================"
$results | ForEach-Object { Write-Host ("{0,-6} {1}" -f $_.Result, $_.Stage) }
$failed = @($results | Where-Object { $_.Result -eq 'FAIL' })
$skipped = @($results | Where-Object { $_.Result -eq 'SKIP' })
Write-Host ("{0} stage(s): {1} passed, {2} failed, {3} skipped" -f `
    $results.Count, @($results | Where-Object { $_.Result -eq 'PASS' }).Count, $failed.Count, $skipped.Count)

if ($skipped.Count -gt 0) {
    Write-Host ""
    Write-Host "SKIPPED-WITH-RECORD (these did NOT run, and this run does not vouch for them):"
    $skipped | ForEach-Object { Write-Host ("  {0}: {1}" -f $_.Stage, $_.Detail) }
}

# --- release qualification, stated separately from the exit code --------------------------------
# SWS-CORRECTIVE-01 workstream 2.7. A skipped release-required stage prevents release
# qualification even when an optional developer run may legitimately finish with recorded skips.
# The two verdicts are printed separately so a green developer run is never mistaken for one.
$releaseRequired = @(
    'gate: generate_build_manifest.py', 'gate: sync_release_manifest.py',
    'gate: release_manifest_check.py', 'gate: generate_model_projection.py',
    'gate: check_model_consistency.py', 'gate: check_governance_bom.py',
    'gate: generate_sbom.py', 'gate: generate_notice.py',
    'gate: provenance_cross_hash_check.py', 'gate: generate_module_provenance.py',
    'gate: hash_python_locks.py', 'gate: innerhtml_sink_audit.py',
    'gate: check_node_advisories', 'boundary gate (distribution)',
    'pytest (whole product, from repo root)',
    # F-064(c): the Node suites are release-required. Previously they were absent from this list,
    # so a run with no node_modules SKIPPED them and still printed RELEASE-QUALIFYING: yes - the
    # product ships an Electron app whose tests and typecheck never gated a release. A SKIP of any
    # of these (node_modules not provisioned) is now a release blocker; the CI lane must run
    # `npm ci` in each tree first (see .github/workflows/windows.yml).
    'npm test (modules\sow\apps\desktop)',
    'npm test (modules\sovereign\ui\ui_shell)',
    'npm run typecheck (modules\sovereign\ui\ui_shell)',
    'build the release artifact', 'clean-room install', 'clean-room verify'
)
$blockers = @($results | Where-Object {
    $releaseRequired -contains $_.Stage -and $_.Result -ne 'PASS'
})
$missing = @($releaseRequired | Where-Object { $name = $_; -not ($results | Where-Object { $_.Stage -eq $name }) })

Write-Host ""
if ($blockers.Count -eq 0 -and $missing.Count -eq 0 -and -not $commitMismatch) {
    Write-Host ("RELEASE-QUALIFYING: yes, for commit {0}" -f $resolvedBuildCommit)
} else {
    Write-Host "RELEASE-QUALIFYING: NO. This run does not qualify a release."
    if ($commitMismatch) {
        Write-Host ("  MISMATCH: tests ran against working checkout {0} but the artifact is cut from {1}" -f $headCommit, $resolvedBuildCommit)
    }
    $blockers | ForEach-Object { Write-Host ("  {0} {1}: {2}" -f $_.Result, $_.Stage, $_.Detail) }
    $missing | ForEach-Object { Write-Host ("  ABSENT {0}: the stage did not run at all" -f $_) }
}

# F-064(e): the clean-room artifact and destination trees live in %TEMP% and were never removed.
# Clean them up now that qualification has been decided (existence was only needed for the skip
# reasoning above). Best-effort; a leftover temp tree is not a CI failure.
foreach ($tmp in @($artifactDir, $destination)) {
    if ($tmp -and (Test-Path -LiteralPath $tmp)) {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if ($failed.Count -gt 0) { exit 1 }
exit 0
