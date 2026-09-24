<#
.SYNOPSIS
    Clean-room install/boot gate (SWS-PUNCHLIST-DIRECTIVE-20260921 WS-0.2).

.DESCRIPTION
    Proves the distribution boots from a fresh, relocated directory rather than only on the build
    host. It:

      1. Extracts the exact shipped artifact (`git archive HEAD`, honouring export-ignore) into a
         temp directory whose path CONTAINS A SPACE and differs from the build tree - so spaced-path
         quoting is exercised too.
         1b. (SW-25) Hashes every extracted file and marks the whole distribution READ-ONLY; every
         later step runs against a read-only install, and the summary re-hashes the tree
         ('readonly-install': nothing may be changed, removed or added).
      2. Runs the distribution's own `Start-Shell.ps1 -CheckOnly` preflight and asserts exit 0.
      3. Runs the adapter RESOLUTION check (cleanroom_resolve_check.py): every module's resolved
         root / cwd / launch entry must exist INSIDE the extracted distribution, with no build-host
         path leaked. This is the WS-0.1 / WS-0.3 / WS-0.4-class gate.
         3b. (SW-25) cleanroom_state_lifecycle.py runs SOVEREIGN's state lifecycle from the
         read-only install against a scratch external state root: launch-state, model
         assignment, state write, backup, refusal of newer-build state (rollback), restore.
      4. Unless -SkipLiveShell: boots the stdlib-only shell from the extracted copy (no venv needed)
         and asserts GET /api/state lists every module with no CONFIG_ERROR. This is the FAST,
         resolution-only live check - it launches `python -m shell.src` directly, so it proves the
         package boots but NOT the supported operator entry point.
      5. Only with -Live (SW-17): boots the SUPPORTED entry point - the shipped `Start-Shell.ps1`
         itself - in a clean env, and proves RESPONSE OWNERSHIP via the launcher nonce, not merely
         that something answers the port. `Start-Shell.ps1` exits non-zero on a nonce/identity
         mismatch (F-006) and only stays alive after `/api/shell-info` echoes ITS OWN launch nonce,
         so: launcher still running + `/api/shell-info` returning a stable pid+nonce + that pid a
         live process together prove the launcher accepted THIS shell as the process it started and
         owns. The lane then asserts per-module `/api/state` outcomes through that same shell and
         verifies teardown (the shell stops and its port is released). Kept behind -Live because it
         drives a real launcher (timing/teardown sensitive) and the standing gate must stay steady.

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

.PARAMETER Live
    SW-17: additionally run the supported-entry-point lane - boot the shipped Start-Shell.ps1 and
    prove response ownership via the launcher nonce, per-module /api/state outcomes, and teardown.
    Off by default so the standing gate stays fast and steady; the fast checks (1-4) still run.

.PARAMETER KeepDist
    Do not delete the extracted distribution afterwards (for inspection).
#>
[CmdletBinding()]
param(
    [string] $DistParent = (Join-Path $env:TEMP 'sws clean room'),
    [int]    $Port = 5199,
    [switch] $SkipLiveShell,
    [switch] $Live,
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

# --- SW-16: never recursively delete a caller-supplied path. Guard the parent against the
# catastrophic cases, then confine ALL writes and the ONLY recursive delete to a freshly created,
# uniquely named directory this tool owns under it. An unrelated folder passed as -DistParent is
# never touched beyond the child we create. -----------------------------------------------------
$DistParent = [IO.Path]::GetFullPath($DistParent)
$repoFull = [IO.Path]::GetFullPath($repo)
function Test-Ancestor([string]$ancestor, [string]$descendant) {
    $a = $ancestor.TrimEnd('\', '/') + '\'
    $d = $descendant.TrimEnd('\', '/') + '\'
    return $d.StartsWith($a, [StringComparison]::OrdinalIgnoreCase)
}
if ($DistParent -eq [IO.Path]::GetPathRoot($DistParent) -or
    $DistParent -ieq $repoFull -or (Test-Ancestor $DistParent $repoFull)) {
    throw "Refusing '$DistParent' as the clean-room parent: it is a drive root or contains the repository. Pass a dedicated -DistParent."
}

# --- 1. extract the shipped artifact into a spaced, relocated path -------------------------------
$work = Join-Path $DistParent ("cleanroom-" + [guid]::NewGuid().ToString('N'))
$dist = Join-Path $work 'dist'
New-Item -ItemType Directory -Force -Path $dist | Out-Null
$tar = Join-Path $work 'artifact.tar'
Info "extracting git archive HEAD -> `"$dist`""
& git -C $repo archive --format=tar -o $tar HEAD
if ($LASTEXITCODE -ne 0) { throw "git archive failed" }
& tar -xf $tar -C $dist
if ($LASTEXITCODE -ne 0) { throw "tar extract failed" }
Remove-Item -Force $tar
if ($dist -notmatch ' ') { Fail 'extract' "dist path has no space; spaced-path quoting not exercised" }
if (Test-Path (Join-Path $dist 'shell\src\adapter.py')) { Ok 'extract' "distribution extracted to a spaced path" }
else { Fail 'extract' "shell\src\adapter.py missing from extract"; }

# --- 1b. SW-25: the install is READ-ONLY from here on -------------------------------------------
# Every shipped file is hashed, then marked read-only, so every later step (preflight, resolution,
# the state lifecycle, both shell boots) runs against a read-only install. The summary re-hashes
# the tree: a single changed, added or removed file fails the gate ('readonly-install').
function Get-DistHashes([string]$root) {
    $map = @{}
    Get-ChildItem -LiteralPath $root -Recurse -File -Force | ForEach-Object {
        $map[$_.FullName.Substring($root.Length)] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
    }
    return $map
}
$distHashesBefore = Get-DistHashes $dist
Get-ChildItem -LiteralPath $dist -Recurse -File -Force | ForEach-Object { $_.IsReadOnly = $true }
Info "SW-25: $($distHashesBefore.Count) shipped files hashed and marked read-only"

# --- 2. Start-Shell.ps1 -CheckOnly --------------------------------------------------------------
$startShell = Join-Path $dist 'Start-Shell.ps1'
if (Test-Path $startShell) {
    # The source-only distribution ships no llama.cpp binary, and SW-01 now makes CheckOnly block a
    # missing SELECTED runtime. Select Ollama (needs no shipped binary) so this exercises a valid
    # preflight; a dedicated negative case (llama selected, binary absent) is asserted below.
    Info "running Start-Shell.ps1 -CheckOnly (backend=ollama)"
    $prevBackend = $env:SOVEREIGN_INFERENCE_BACKEND
    $env:SOVEREIGN_INFERENCE_BACKEND = 'ollama'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $startShell -CheckOnly *> (Join-Path $work 'checkonly.log')
    $checkExit = $LASTEXITCODE
    # SW-01 negative case: with llama.cpp selected and no provisioned binary, CheckOnly must BLOCK.
    $env:SOVEREIGN_INFERENCE_BACKEND = 'llama.cpp'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $startShell -CheckOnly *> (Join-Path $work 'checkonly-llama.log')
    $checkLlamaExit = $LASTEXITCODE
    $env:SOVEREIGN_INFERENCE_BACKEND = $prevBackend
    if ($checkLlamaExit -ne 0) { Ok 'checkonly-negative' "llama.cpp selected + no binary correctly BLOCKED preflight" }
    else { Fail 'checkonly-negative' "llama.cpp selected + no binary but preflight passed (SW-01 regression)" }
    if ($checkExit -eq 0) { Ok 'checkonly' "preflight exit 0" }
    else { Fail 'checkonly' "preflight exit $checkExit (see checkonly.log)" }
} else { Fail 'checkonly' "Start-Shell.ps1 not found in distribution" }

# --- 3. adapter resolution check ----------------------------------------------------------------
Info "running adapter resolution check"
$reportJson = Join-Path $work 'resolution-report.json'
& $pyExe @pyArgs $resolver --dist $dist --json $reportJson
$resolveExit = $LASTEXITCODE
if ($resolveExit -eq 0) { Ok 'resolution' "every module entry resolves inside the distribution" }
else { Fail 'resolution' "one or more modules failed resolution (see resolution-report.json)" }

# --- 3b. SW-25: state lifecycle of the read-only install against an external state root ---------
# Stdlib-only (system Python 3.12, no venv): launch-state, model assignment, state write, backup,
# refusal of newer-build state (rollback), restore. The state root is a scratch dir under $work,
# never the operator's real %LOCALAPPDATA%.
Info "SW-25: read-only install state lifecycle (external state root under the work dir)"
$lifecycle = Join-Path $PSScriptRoot 'cleanroom_state_lifecycle.py'
$lifecycleLog = Join-Path $work 'state-lifecycle.json'
& $pyExe @pyArgs $lifecycle --root (Join-Path $dist 'modules\sovereign') --work (Join-Path $work 'state-lifecycle') *> $lifecycleLog
$lifecycleExit = $LASTEXITCODE
if ($lifecycleExit -eq 0) { Ok 'state-lifecycle' "read-only install: external state launch, assign, backup, rollback refusal, restore" }
else { Fail 'state-lifecycle' "state lifecycle failed (see state-lifecycle.json): $((Get-Content -Raw $lifecycleLog) -replace '\s+', ' ')" }

# --- 4. FAST live stdlib-shell boot + /api/state (resolution-only; NOT the supported entry) -----
if (-not $SkipLiveShell) {
    Info "booting stdlib shell on 127.0.0.1:$Port (fast check: python -m shell.src)"
    $proc = Start-Process -FilePath $pyExe -ArgumentList (@($pyArgs) + @('-m','shell.src','--port',"$Port")) `
        -WorkingDirectory $dist -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $work 'shell.out.log') `
        -RedirectStandardError (Join-Path $work 'shell.err.log')
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

# --- 5. SW-17: supported-entry-point boot via Start-Shell.ps1 (ownership + teardown) ------------
# Only with -Live. This is the lane that proves the path an operator actually invokes, not the fast
# `python -m shell.src` boot above. Ownership is proven WITHOUT guessing the launcher's private
# nonce: Start-Shell.ps1 exits non-zero on a nonce/identity mismatch and only stays alive (blocked
# waiting on the shell) after /api/shell-info echoed its own launch nonce - so a launcher that is
# still running while /api/shell-info returns a stable pid+nonce, whose pid is a live process, has
# already confirmed this shell is the one it started and owns.
if ($Live -and -not $SkipLiveShell) {
    $livePort = $Port + 1
    Info "SW-17: booting SUPPORTED entry Start-Shell.ps1 on 127.0.0.1:$livePort (backend=ollama)"
    if (-not (Test-Path $startShell)) {
        Fail 'live-supported' "Start-Shell.ps1 not found in distribution"
    } else {
        $prevBackendLive = $env:SOVEREIGN_INFERENCE_BACKEND
        $env:SOVEREIGN_INFERENCE_BACKEND = 'ollama'
        $liveOut = Join-Path $work 'live-shell.out.log'
        $liveErr = Join-Path $work 'live-shell.err.log'
        # Run the launcher in its own hidden powershell so the whole tree is ours to observe/stop.
        # The dist path (hence $startShell) contains a space; Start-Process -ArgumentList does NOT
        # auto-quote array elements in PS 5.1, so -File must carry the quoted path itself - the same
        # ('"{0}"' -f ...) form Start-Shell.ps1 uses for its own script argument.
        $launcher = Start-Process -FilePath 'powershell' `
            -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $startShell), '-Port', "$livePort", '-NoBrowser') `
            -WorkingDirectory $dist -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput $liveOut -RedirectStandardError $liveErr
        # F-002-style: cache the Handle while alive so ExitCode is populated on exit (PS 5.1 reports
        # $null otherwise), making a startup-failure diagnostic show the real code.
        $null = $launcher.Handle
        $shellInfo = $null
        try {
            $liveHost = @{ Host = "127.0.0.1:$livePort" }
            for ($i = 0; $i -lt 60; $i++) {
                Start-Sleep -Milliseconds 500
                if ($launcher.HasExited) { break }
                try {
                    $shellInfo = Invoke-RestMethod -Uri "http://127.0.0.1:$livePort/api/shell-info" -TimeoutSec 2 -Headers $liveHost
                    if ($shellInfo -and $shellInfo.pid -and $shellInfo.nonce) { break }
                } catch { $shellInfo = $null }
            }
            if ($launcher.HasExited) {
                Fail 'live-supported' "Start-Shell.ps1 exited during startup (code $($launcher.ExitCode)); see live-shell.out.log"
            } elseif (-not $shellInfo -or -not $shellInfo.nonce -or -not $shellInfo.pid) {
                Fail 'live-supported' "Start-Shell.ps1 did not bring up /api/shell-info with a pid+nonce"
            } else {
                # Give the launcher a beat to run its own nonce check against the same endpoint; a
                # mismatch would make it exit 1 here rather than stay blocked on the shell.
                Start-Sleep -Milliseconds 750
                $info2 = $null
                try { $info2 = Invoke-RestMethod -Uri "http://127.0.0.1:$livePort/api/shell-info" -TimeoutSec 2 -Headers $liveHost } catch {}
                $pidLive = $null; try { $pidLive = Get-Process -Id ([int]$shellInfo.pid) -ErrorAction Stop } catch {}
                if ($launcher.HasExited) {
                    Fail 'live-supported' "launcher exited after shell answered (code $($launcher.ExitCode)) - nonce/identity ownership NOT confirmed"
                } elseif (-not $info2 -or [string]$info2.nonce -ne [string]$shellInfo.nonce -or [string]$info2.pid -ne [string]$shellInfo.pid) {
                    Fail 'live-supported' "shell identity not stable across probes (pid/nonce changed) - a flapping/foreign responder"
                } elseif (-not $pidLive) {
                    Fail 'live-supported' "/api/shell-info pid $($shellInfo.pid) is not a live process"
                } else {
                    Ok 'live-supported' "Start-Shell.ps1 owns shell pid $($shellInfo.pid) (launcher alive + stable nonce = nonce ownership confirmed)"
                    # Per-module outcomes through the SAME supported-path shell.
                    try {
                        $liveState = Invoke-RestMethod -Uri "http://127.0.0.1:$livePort/api/state" -TimeoutSec 2 -Headers $liveHost
                        $liveMods = $liveState.modules.PSObject.Properties.Name
                        $liveErrs = @()
                        foreach ($m in $liveMods) { if ($liveState.modules.$m.state -eq 'FAILED' -or $liveState.modules.$m.error) { $liveErrs += $m } }
                        if ($liveErrs.Count -gt 0) { Fail 'live-supported-modules' "modules reporting error at load: $($liveErrs -join ', ')" }
                        elseif ($liveMods.Count -lt 5) { Fail 'live-supported-modules' "expected the full module set, got $($liveMods.Count)" }
                        else { Ok 'live-supported-modules' "/api/state lists $($liveMods.Count) modules through the supported path, no load errors" }
                    } catch { Fail 'live-supported-modules' "GET /api/state failed on the supported-path shell" }
                }
            }
        } finally {
            # Teardown: stop the shell the launcher started; its Wait-Process then returns and the
            # launcher exits. Then confirm the port is released and the pid is gone.
            if ($shellInfo -and $shellInfo.pid) { Stop-Process -Id ([int]$shellInfo.pid) -Force -ErrorAction SilentlyContinue }
            if ($launcher -and -not $launcher.HasExited) {
                if (-not $launcher.WaitForExit(15000)) { Stop-Process -Id $launcher.Id -Force -ErrorAction SilentlyContinue }
            }
            $env:SOVEREIGN_INFERENCE_BACKEND = $prevBackendLive
            # Only assert teardown when WE actually brought a shell up. If startup failed (no
            # shell-info pid), there is nothing of ours to tear down - the failure is already
            # recorded by live-supported, and a port held by a foreign/occupying process is not
            # our teardown to prove.
            if ($shellInfo -and $shellInfo.pid) {
                Start-Sleep -Milliseconds 750
                $stillListening = Get-NetTCPConnection -LocalPort $livePort -State Listen -ErrorAction SilentlyContinue
                $pidGone = $true
                try { Get-Process -Id ([int]$shellInfo.pid) -ErrorAction Stop | Out-Null; $pidGone = $false } catch {}
                if ($stillListening -or -not $pidGone) { Fail 'live-teardown' "supported-path shell did not fully stop (port held or pid alive)" }
                else { Ok 'live-teardown' "supported-path shell and its port $livePort released after teardown" }
            }
        }
    }
} elseif ($Live -and $SkipLiveShell) {
    Info "SW-17 supported-path lane skipped (-SkipLiveShell overrides -Live)"
}

# --- SW-25: no step changed a shipped file -----------------------------------------------------
$distHashesAfter = Get-DistHashes $dist
$changed = @($distHashesBefore.Keys | Where-Object { $distHashesAfter[$_] -ne $distHashesBefore[$_] })
$added = @($distHashesAfter.Keys | Where-Object { -not $distHashesBefore.ContainsKey($_) })
if ($changed.Count -eq 0 -and $added.Count -eq 0) {
    Ok 'readonly-install' "all $($distHashesBefore.Count) shipped files unchanged; nothing written into the install tree"
} else {
    Fail 'readonly-install' "install tree modified: changed/removed=$($changed.Count) [$(($changed | Select-Object -First 5) -join ', ')] added=$($added.Count) [$(($added | Select-Object -First 5) -join ', ')]"
}

# --- summary ------------------------------------------------------------------------------------
$failCount = $script:Failures.Count
Write-Host "`n--- WS-0.2 result ---" -ForegroundColor Cyan
if (-not $KeepDist) { Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue }
else { Write-Host "dist kept at: $dist" }
if ($failCount -eq 0) {
    Write-Host "PASS - distribution boots from a clean, relocated, spaced path." -ForegroundColor Green
    exit 0
} else {
    Write-Host "FAIL - $failCount gate(s):" -ForegroundColor Red
    $script:Failures | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    exit 1
}
