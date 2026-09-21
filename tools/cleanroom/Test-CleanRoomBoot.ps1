<#
.SYNOPSIS
    Clean-room install/boot gate (SWS-PUNCHLIST-DIRECTIVE-20260921 WS-0.2).

.DESCRIPTION
    Proves the distribution boots from a fresh, relocated directory rather than only on the build
    host. It:

      1. Extracts the exact shipped artifact (`git archive HEAD`, honouring export-ignore) into a
         temp directory whose path CONTAINS A SPACE and differs from the build tree — so spaced-path
         quoting is exercised too.
      2. Runs the distribution's own `Start-Shell.ps1 -CheckOnly` preflight and asserts exit 0.
      3. Runs the adapter RESOLUTION check (cleanroom_resolve_check.py): every module's resolved
         root / cwd / launch entry must exist INSIDE the extracted distribution, with no build-host
         path leaked. This is the WS-0.1 / WS-0.3 / WS-0.4-class gate.
      4. Unless -SkipLiveShell: boots the stdlib-only shell from the extracted copy (no venv needed)
         and asserts GET /api/state lists every module with no CONFIG_ERROR.

    Per-MODULE service readiness (starting sovereign/debate/llamacpp/etc. and probing their health
    endpoints) requires a provisioned venv + models + Electron and is reported PROVISION-PENDING
    here; it is proven in a provisioned lane, not in a source-only clean room.

    Exit code 0 = gate PASS. Non-zero = at least one gate failed (the failing gate is named).

.PARAMETER DistParent
    Parent directory for the extracted distribution. Default: "$env:TEMP\sws clean room".

.PARAMETER Port
    Loopback port for the live shell boot. Default 5199 (kept off the normal 5180).

.PARAMETER SkipLiveShell
    Do only the static gates (extract + CheckOnly + resolution). Use where no Python is available
    to bind a socket.

.PARAMETER KeepDist
    Do not delete the extracted distribution afterwards (for inspection).
#>
[CmdletBinding()]
param(
    [string] $DistParent = (Join-Path $env:TEMP 'sws clean room'),
    [int]    $Port = 5199,
    [switch] $SkipLiveShell,
    [switch] $KeepDist
)

$ErrorActionPreference = 'Stop'
$script:Failures = New-Object System.Collections.ArrayList
function Fail($gate, $msg) { [void]$script:Failures.Add("[$gate] $msg"); Write-Host "  FAIL [$gate] $msg" -ForegroundColor Red }
function Ok($gate, $msg)   { Write-Host "  OK   [$gate] $msg" -ForegroundColor Green }
function Info($msg)        { Write-Host "  ..   $msg" -ForegroundColor DarkGray }

# --- locate the repo (release worktree) from this script's location -----------------------------
$toolDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path (Join-Path $toolDir '..') '..')).Path
if (-not (Test-Path (Join-Path $repo 'shell\src\adapter.py'))) {
    throw "Repo root not found from $toolDir (expected shell\src\adapter.py under $repo)"
}
$resolver = Join-Path $toolDir 'cleanroom_resolve_check.py'

# --- pick a Python 3.12 -------------------------------------------------------------------------
$pyExe = $null; $pyArgs = @()
try { & py -3.12 --version *> $null 2>&1 } catch {}
if ($LASTEXITCODE -eq 0) { $pyExe = 'py'; $pyArgs = @('-3.12') }
else {
    try { & python --version *> $null 2>&1 } catch {}
    if ($LASTEXITCODE -eq 0) { $pyExe = 'python' } else { throw "No Python interpreter found (need 3.12 for the shell)." }
}

Write-Host "`n=== WS-0.2 Clean-Room Boot Gate ===" -ForegroundColor Cyan
Write-Host "repo: $repo"
Write-Host "python: $pyExe $($pyArgs -join ' ')  ($(& $pyExe @pyArgs --version 2>&1))"

# --- 1. extract the shipped artifact into a spaced, relocated path -------------------------------
$dist = Join-Path $DistParent 'dist'
if (Test-Path $DistParent) { Remove-Item -Recurse -Force $DistParent }
New-Item -ItemType Directory -Force -Path $dist | Out-Null
$tar = Join-Path $DistParent 'artifact.tar'
Info "extracting git archive HEAD -> `"$dist`""
& git -C $repo archive --format=tar -o $tar HEAD
if ($LASTEXITCODE -ne 0) { throw "git archive failed" }
& tar -xf $tar -C $dist
if ($LASTEXITCODE -ne 0) { throw "tar extract failed" }
Remove-Item -Force $tar
if ($dist -notmatch ' ') { Fail 'extract' "dist path has no space; spaced-path quoting not exercised" }
if (Test-Path (Join-Path $dist 'shell\src\adapter.py')) { Ok 'extract' "distribution extracted to a spaced path" }
else { Fail 'extract' "shell\src\adapter.py missing from extract"; }

# --- 2. Start-Shell.ps1 -CheckOnly --------------------------------------------------------------
$startShell = Join-Path $dist 'Start-Shell.ps1'
if (Test-Path $startShell) {
    Info "running Start-Shell.ps1 -CheckOnly"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $startShell -CheckOnly *> (Join-Path $DistParent 'checkonly.log')
    $checkExit = $LASTEXITCODE
    if ($checkExit -eq 0) { Ok 'checkonly' "preflight exit 0" }
    else { Fail 'checkonly' "preflight exit $checkExit (see checkonly.log)" }
} else { Fail 'checkonly' "Start-Shell.ps1 not found in distribution" }

# --- 3. adapter resolution check ----------------------------------------------------------------
Info "running adapter resolution check"
$reportJson = Join-Path $DistParent 'resolution-report.json'
& $pyExe @pyArgs $resolver --dist $dist --json $reportJson
$resolveExit = $LASTEXITCODE
if ($resolveExit -eq 0) { Ok 'resolution' "every module entry resolves inside the distribution" }
else { Fail 'resolution' "one or more modules failed resolution (see resolution-report.json)" }

# --- 4. live stdlib-shell boot + /api/state -----------------------------------------------------
if (-not $SkipLiveShell) {
    Info "booting stdlib shell on 127.0.0.1:$Port"
    $proc = Start-Process -FilePath $pyExe -ArgumentList (@($pyArgs) + @('-m','shell.src','--port',"$Port")) `
        -WorkingDirectory $dist -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $DistParent 'shell.out.log') `
        -RedirectStandardError (Join-Path $DistParent 'shell.err.log')
    try {
        $state = $null
        for ($i = 0; $i -lt 40; $i++) {
            Start-Sleep -Milliseconds 250
            try {
                $state = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/state" -TimeoutSec 2 `
                    -Headers @{ Host = "127.0.0.1:$Port" }
                if ($state) { break }
            } catch {}
        }
        if (-not $state) { Fail 'live-shell' "shell did not answer /api/state (see shell.err.log)" }
        else {
            $mods = $state.modules.PSObject.Properties.Name
            $errs = @()
            foreach ($m in $mods) { if ($state.modules.$m.state -eq 'FAILED' -or $state.modules.$m.error) { $errs += $m } }
            if ($errs.Count -gt 0) { Fail 'live-shell' "modules reporting error at load: $($errs -join ', ')" }
            else { Ok 'live-shell' "shell booted; /api/state lists $($mods.Count) modules, no load errors" }
        }
    } finally {
        if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
    }
} else { Info "live shell boot skipped (-SkipLiveShell)" }

# --- summary ------------------------------------------------------------------------------------
$failCount = $script:Failures.Count
Write-Host "`n--- WS-0.2 result ---" -ForegroundColor Cyan
if (-not $KeepDist) { Remove-Item -Recurse -Force $DistParent -ErrorAction SilentlyContinue }
else { Write-Host "dist kept at: $dist" }
if ($failCount -eq 0) {
    Write-Host "PASS - distribution boots from a clean, relocated, spaced path." -ForegroundColor Green
    exit 0
} else {
    Write-Host "FAIL - $failCount gate(s):" -ForegroundColor Red
    $script:Failures | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    exit 1
}
