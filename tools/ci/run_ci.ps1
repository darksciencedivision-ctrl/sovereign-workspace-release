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
    [string]$PythonVersion = '-3.12'
)

$ErrorActionPreference = 'Continue'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
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
    & $Body
    $code = $LASTEXITCODE
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

Write-Host ("Sovereign Workspace CI - {0}" -f $repoRoot)
Write-Host ("commit: {0}" -f (& git -C $repoRoot rev-parse HEAD))
Write-Host ""

# --- 1. release gates -------------------------------------------------------------------------
# These are the checks the build itself must pass, and they are cheap, so they run first: a
# manifest that does not describe the tree makes every later result questionable.
$gates = @(
    'tools\release\release_manifest_check.py',
    'tools\release\check_model_consistency.py',
    'tools\release\check_governance_bom.py',
    'tools\release\generate_sbom.py --check',
    'tools\release\generate_notice.py --check'
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

# --- 5. the clean-room install (V-1) -----------------------------------------------------------
# Installs into a temporary destination and re-hashes every path in the resulting manifest.
# OFF by default because it provisions packages; the lane turns it on.
$cleanRoomSkip = $null
if (-not $IncludeCleanRoom) {
    $cleanRoomSkip = 'not requested; pass -IncludeCleanRoom (installs Python and Node packages)'
}
$destination = Join-Path ([IO.Path]::GetTempPath()) ("sovereign-cleanroom-" + [Guid]::NewGuid().ToString('N').Substring(0, 8))
Invoke-Stage -Name 'clean-room install' -SkipReason $cleanRoomSkip -Body {
    & (Join-Path $repoRoot 'tools\release\install.ps1') -Dest $destination
}
Invoke-Stage -Name 'clean-room verify' -SkipReason $cleanRoomSkip -Body {
    & (Join-Path $repoRoot 'tools\release\verify_install.ps1') -Dest $destination
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

if ($failed.Count -gt 0) { exit 1 }
exit 0
