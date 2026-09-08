<#
.SYNOPSIS
    Sovereign Workspace - the one supported launcher and preflight.

.DESCRIPTION
    THE SINGLE IMPLEMENTATION (SWS-CORRECTIVE-01 workstream 3.1). Preflight and launch used to
    exist twice, in two files that disagreed:

      * `Sovereign Workspace.bat` ran this script directly, so the outer preflight in
        `Start-Sovereign.ps1` never ran at all and no argument could reach either.
      * `Start-Sovereign.ps1` told the operator "Start-Shell.ps1 refuses in light mode".
        This script only printed advice and carried on. The blocking claim was false.
      * `-CheckOnly` exited 0 even after reporting a missing interpreter.
      * Readiness was "something is listening on the port", which any process satisfies.
      * `GIT_OPTIONAL_LOCKS` was set and then unconditionally deleted, destroying whatever the
        caller had.

    Preflight and launch now live here, once. `Start-Sovereign.ps1` and the batch file are thin
    delegators that forward their arguments to this file; neither carries a second copy.

    SUPPORTED SOURCES. This script supports BOTH a source checkout and an installed artifact:
    it needs `shell\src\__main__.py` beside it and nothing else, and both layouts provide that.
    It reports which one it detected. Candidate-identity reporting (commit, tree state) is
    checkout-only and is skipped, not faked, on an installed artifact.

    BLOCKING vs ADVISORY. A blocking condition stops the launch and sets a non-zero exit code.
    An advisory is printed and does not. The two are never mixed:

      blocking  : shell\src\__main__.py absent; the `py` launcher absent; Python 3.12
                  unavailable; the requested port already held.
      advisory  : Windows in light mode; no NVIDIA tooling; a module port held by something
                  else; an unreadable GPU census.

    Ctrl+C stops the shell, and because the shell holds its modules in a Windows Job Object,
    anything it launched stops too.

.PARAMETER Port
    Port to bind. Default 5180.

.PARAMETER NoBrowser
    Start the shell but do not open a browser window.

.PARAMETER CheckOnly
    Run the preflight and stop. Nothing is started, no module runs, and the exit code reports
    whether anything blocking was found: 0 clear, 1 blocked.

.EXAMPLE
    .\Start-Shell.ps1

.EXAMPLE
    .\Start-Shell.ps1 -Port 5181 -NoBrowser

.EXAMPLE
    .\Start-Shell.ps1 -CheckOnly
#>
[CmdletBinding()]
param(
    [int] $Port = 5180,
    [switch] $NoBrowser,
    [switch] $CheckOnly
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root

$blocking = New-Object System.Collections.Generic.List[string]
$advisory = New-Object System.Collections.Generic.List[string]

function Line($label, $value, $color = 'Gray') {
    Write-Host ("  {0,-22}" -f $label) -NoNewline -ForegroundColor DarkGray
    Write-Host $value -ForegroundColor $color
}

Write-Host ""
Write-Host "  SOVEREIGN WORKSPACE" -ForegroundColor Cyan
Write-Host "  $root" -ForegroundColor DarkGray
Write-Host ""

# --- what kind of tree is this ---------------------------------------------
if (-not (Test-Path -LiteralPath (Join-Path $root 'shell\src\__main__.py'))) {
    Write-Host "  shell\src\__main__.py not found." -ForegroundColor Red
    Write-Host "  Put this script in the folder that CONTAINS shell\, and run it from there."
    Write-Host ""
    exit 1
}
$isInstall = Test-Path -LiteralPath (Join-Path $root 'install-manifest.json')
$isCheckout = Test-Path -LiteralPath (Join-Path $root '.git')
if ($isInstall) { Line 'tree' 'installed artifact' }
elseif ($isCheckout) { Line 'tree' 'source checkout' }
else { Line 'tree' 'source layout (no install manifest, no git metadata)' }

$verPath = Join-Path $root 'VERSION.json'
if (Test-Path -LiteralPath $verPath) {
    try { Line 'version' ((Get-Content -Raw -LiteralPath $verPath | ConvertFrom-Json).version) }
    catch { Line 'version' 'VERSION.json is unreadable' Yellow }
}

# --- candidate identity: a checkout property, absent rather than faked elsewhere ---
if ($isCheckout -and (Get-Command git -ErrorAction SilentlyContinue)) {
    # The caller's GIT_OPTIONAL_LOCKS is RESTORED, not deleted. The previous launcher called
    # Remove-Item on it unconditionally, so a caller that had set it lost it.
    $hadOptionalLocks = Test-Path Env:\GIT_OPTIONAL_LOCKS
    $priorOptionalLocks = if ($hadOptionalLocks) { $env:GIT_OPTIONAL_LOCKS } else { $null }
    try {
        $env:GIT_OPTIONAL_LOCKS = '0'
        $head = (& git -C $root rev-parse --short HEAD 2>$null)
        $gitOk = ($LASTEXITCODE -eq 0)
        $dirty = (& git -C $root status --porcelain 2>$null)
        $statusOk = ($LASTEXITCODE -eq 0)
    }
    finally {
        if ($hadOptionalLocks) { $env:GIT_OPTIONAL_LOCKS = $priorOptionalLocks }
        else { Remove-Item Env:\GIT_OPTIONAL_LOCKS -ErrorAction SilentlyContinue }
    }
    if ($gitOk) { Line 'candidate commit' $head }
    if (-not $statusOk) {
        Line 'tree state' 'UNKNOWN (git did not complete - not a clean-tree result)' Yellow
        $advisory.Add('git status did not complete; tree state unknown') | Out-Null
    }
    elseif ($dirty) {
        $n = ($dirty | Measure-Object).Count
        Line 'tree state' "$n uncommitted change(s)" Yellow
        $advisory.Add("worktree has $n uncommitted change(s)") | Out-Null
    }
    else { Line 'tree state' 'clean' Green }
}

# --- interpreter: BLOCKING --------------------------------------------------
$pyCmd = Get-Command py -ErrorAction SilentlyContinue
$py = $null
if ($null -eq $pyCmd) {
    Line 'py launcher' 'NOT FOUND - the shell cannot start' Red
    $blocking.Add("the 'py' launcher is not on PATH; install Python 3.12") | Out-Null
}
else {
    $py = $pyCmd.Source
    $ver = & $py -3.12 --version 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $ver) {
        Line 'python 3.12' 'NOT AVAILABLE - the shell cannot start' Red
        $blocking.Add('py -3.12 is not available; the shell is pinned to Python 3.12') | Out-Null
    }
    else { Line 'python 3.12' ([string]$ver).Trim() Green }

    # 3.14 runs the Debate module. Its absence does not stop the shell, so it is advisory here
    # and blocking only in the installer, which needs it to build a venv.
    & $py -3.14 --version > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        Line 'python 3.14' 'not available - the Debate module will not install' Yellow
        $advisory.Add('py -3.14 is not available; Debate requires it (see docs/INSTALL.md)') | Out-Null
    }
    else { Line 'python 3.14' 'present' Green }
}

# --- the shell port: BLOCKING ------------------------------------------------
$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($null -ne $busy) {
    $owner = Get-Process -Id $busy[0].OwningProcess -ErrorAction SilentlyContinue
    $who = if ($owner) { "$($owner.ProcessName) (pid $($busy[0].OwningProcess))" } else { "pid $($busy[0].OwningProcess)" }
    Line "port $Port" "HELD by $who - the shell cannot bind" Red
    $blocking.Add("port $Port is already in use by $who") | Out-Null
}
else { Line "port $Port" 'free' Green }

# --- module ports: ADVISORY --------------------------------------------------
$modulePorts = [ordered]@{ 5175 = 'sovereign'; 5183 = 'llamacpp'; 5184 = 'distillery'; 8700 = 'debate'; 8765 = 'tokencenter' }
$held = @()
foreach ($p in $modulePorts.Keys) {
    $conn = Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue
    if ($conn) {
        $owner = Get-Process -Id $conn[0].OwningProcess -ErrorAction SilentlyContinue
        $name = if ($owner) { $owner.ProcessName } else { 'unknown' }
        Line "port $p ($($modulePorts[$p]))" ("HELD by {0} (pid {1})" -f $name, $conn[0].OwningProcess) Yellow
        $held += "$p ($($modulePorts[$p]))"
    }
}
if (-not $held) { Line 'module ports' 'all free' Green }
else { $advisory.Add("module port(s) already held: $($held -join ', ')") | Out-Null }

# --- processes from THIS tree: ADVISORY --------------------------------------
# Only processes running out of this tree are this launcher's business.
$treePrefix = $root.TrimEnd('\') + '\'
$stray = @(Get-Process python, pythonw, node, electron -ErrorAction SilentlyContinue | Where-Object {
    $p = $null
    try { $p = $_.Path } catch { $p = $null }
    $p -and $p.StartsWith($treePrefix, 'OrdinalIgnoreCase')
})
if ($stray.Count -gt 0) {
    $stray | ForEach-Object { Line 'process from this tree' ("{0} (pid {1})" -f $_.ProcessName, $_.Id) Yellow }
    $advisory.Add("$($stray.Count) process(es) from a previous run are still alive") | Out-Null
}
else { Line 'processes' 'none from this tree' Green }

# --- GPU: ADVISORY, and unobservable is never rendered as clean --------------
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    # One CSV row PER GPU. The previous launcher split a single row on ',' and indexed [0]/[1],
    # so a second GPU changed the shape of the answer.
    $rows = @(& nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader,nounits 2>$null)
    if ($LASTEXITCODE -ne 0 -or $rows.Count -eq 0) {
        Line 'vram' 'UNREADABLE - GPU state unobservable, not assumed free' Yellow
        $advisory.Add('nvidia-smi did not answer; GPU state is unknown rather than clear') | Out-Null
    }
    else {
        foreach ($row in $rows) {
            $parts = @($row -split ',' | ForEach-Object { $_.Trim() })
            if ($parts.Count -lt 3) { continue }
            $used = [int]$parts[1]; $total = [int]$parts[2]
            $pct = if ($total -gt 0) { [math]::Round(100 * $used / $total) } else { 0 }
            $col = if ($pct -ge 60) { 'Yellow' } else { 'Green' }
            Line "vram gpu $($parts[0])" "$used MiB of $total MiB ($pct%)" $col
        }
    }

    # Per-process attribution: on a consumer GPU nvidia-smi lists every process holding a
    # graphics context and reports used_memory as [N/A]. That is normal desktop usage, not a
    # finding, so only workspace-relevant holders are reported.
    $relevant = 'ollama', 'llama-server', 'python', 'pythonw', 'node', 'electron'
    $apps = @(& nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader 2>$null)
    if ($LASTEXITCODE -ne 0) {
        Line 'gpu holders' 'UNREADABLE - not reported as none' Yellow
        $advisory.Add('the GPU process census could not be read; holders are unknown') | Out-Null
    }
    else {
        $hits = @()
        foreach ($a in $apps) {
            if (-not $a) { continue }
            $name = ($a -split ',')[-1].Trim()
            $leaf = [IO.Path]::GetFileNameWithoutExtension($name)
            if ($relevant -contains $leaf.ToLower()) { $hits += $a.Trim() }
        }
        if ($hits) {
            $hits | ForEach-Object { Line 'gpu holder' $_ Yellow }
            $advisory.Add('a model runtime or module process is already holding the GPU') | Out-Null
        }
        else { Line 'gpu holders' 'none (desktop and browser usage not counted)' Green }
    }
}
else {
    Line 'nvidia-smi' 'not present - GPU state unobservable' DarkGray
    $advisory.Add('no NVIDIA tooling on PATH; GPU state is unknown rather than clear') | Out-Null
}

# --- theme: INFORMATIONAL ONLY -----------------------------------------------
# The shell follows prefers-color-scheme. Light mode gives the light variant, which is a
# legitimate theme. Nothing here refuses to start, and nothing claims to: the previous outer
# preflight told the operator this script "refuses in light mode", which was never true.
# Windows' own theme setting is never modified.
$themeKey = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize'
$appsLight = $null
if (Test-Path $themeKey) {
    $appsLight = (Get-ItemProperty -Path $themeKey -ErrorAction SilentlyContinue).AppsUseLightTheme
}
if ($appsLight -eq 1) {
    Line 'windows theme' 'light - you will get the light variant (this does not block startup)' DarkGray
}
elseif ($null -eq $appsLight) { Line 'windows theme' 'not readable' DarkGray }
else { Line 'windows theme' 'dark' Green }

# --- verdict -----------------------------------------------------------------
Write-Host ""
if ($blocking.Count -gt 0) {
    Write-Host "  $($blocking.Count) blocking problem(s) - the shell will not be started:" -ForegroundColor Red
    $blocking | ForEach-Object { Write-Host "    - $_" -ForegroundColor Red }
}
if ($advisory.Count -gt 0) {
    Write-Host "  $($advisory.Count) thing(s) to know (not blocking):" -ForegroundColor Yellow
    $advisory | ForEach-Object { Write-Host "    - $_" -ForegroundColor Yellow }
}
if ($blocking.Count -eq 0 -and $advisory.Count -eq 0) {
    Write-Host "  Preflight clear." -ForegroundColor Green
}
Write-Host ""

if ($CheckOnly) {
    # No module is started, and the exit code reports the blocking result rather than the mere
    # fact that the check ran.
    if ($blocking.Count -gt 0) {
        Write-Host "  -CheckOnly: nothing started. BLOCKED." -ForegroundColor Red
        Write-Host ""
        exit 1
    }
    Write-Host "  -CheckOnly: nothing started. Preflight would allow a launch." -ForegroundColor DarkGray
    Write-Host ""
    exit 0
}

if ($blocking.Count -gt 0) { exit 1 }

# --- run ---------------------------------------------------------------------
$url = "http://127.0.0.1:$Port"
$env:PYTHONDONTWRITEBYTECODE = '1'
Write-Host "  Starting on $url. Ctrl+C to stop." -ForegroundColor Cyan
Write-Host "  Modules run inside the shell's Job Object, so they stop with it." -ForegroundColor DarkGray
Write-Host ""

$proc = Start-Process -FilePath $py `
                      -ArgumentList @('-3.12', '-B', '-m', 'shell.src', '--port', "$Port") `
                      -WorkingDirectory $root -NoNewWindow -PassThru

try {
    # READINESS IS SERVICE IDENTITY, NOT A LISTENER. The previous launcher accepted any
    # process listening on the port and announced "Listening on ..." for it. This waits for
    # the process WE started to answer /api/shell-info with the shell's own payload.
    $ready = $false
    $identityProblem = $null
    for ($i = 0; $i -lt 40; $i++) {
        if ($proc.HasExited) { break }
        try {
            $info = Invoke-RestMethod -Uri "$url/api/shell-info" -TimeoutSec 2 -ErrorAction Stop
            if ($info -and $info.version -and ([string]$info.version).StartsWith('SWS-UI-001')) {
                $ready = $true
                break
            }
            $identityProblem = "the service on port $Port is not this shell (version '$($info.version)')"
        }
        catch { }
        Start-Sleep -Milliseconds 250
    }

    if ($proc.HasExited) {
        Write-Host "  The shell exited during startup (code $($proc.ExitCode))." -ForegroundColor Red
        Write-Host ""
        exit $proc.ExitCode
    }

    if ($ready) {
        Write-Host "  Ready at $url" -ForegroundColor Green
        if (-not $NoBrowser) { Start-Process $url }
    }
    elseif ($identityProblem) {
        Write-Host "  $identityProblem" -ForegroundColor Red
        Write-Host "  Not opening a browser. Stopping the process this launcher started." -ForegroundColor Red
        exit 1
    }
    else {
        Write-Host "  The shell did not answer /api/shell-info within 10s." -ForegroundColor Yellow
        Write-Host "  Leaving it running; check the output above for the reason." -ForegroundColor Yellow
    }

    Wait-Process -Id $proc.Id
}
finally {
    if (-not $proc.HasExited) {
        Write-Host ""
        Write-Host "  Stopping the shell..." -ForegroundColor Cyan
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        $proc.WaitForExit(5000) | Out-Null
    }
    Write-Host "  Stopped." -ForegroundColor Cyan
    Write-Host ""
}
