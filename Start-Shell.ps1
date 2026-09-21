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

# Local provisioning values. `workspace.env` (created by Provision-Workspace.ps1; gitignored, never
# shipped) carries THIS machine's paths — the llama.cpp server binary, its models, the SOW coding
# repo — so the sealed product stays free of any one machine's absolute paths. KEY=VALUE lines;
# blank lines and lines starting with `#` are ignored; an already-set environment variable is never
# overwritten, so an operator's own environment still wins.
$envFile = Join-Path $root 'workspace.env'
if (Test-Path -LiteralPath $envFile -PathType Leaf) {
    foreach ($line in Get-Content -LiteralPath $envFile) {
        $t = $line.Trim()
        if (-not $t -or $t.StartsWith('#')) { continue }
        $eq = $t.IndexOf('=')
        if ($eq -lt 1) { continue }
        $name = $t.Substring(0, $eq).Trim()
        $value = $t.Substring($eq + 1).Trim()
        if ($name -and -not [Environment]::GetEnvironmentVariable($name, 'Process')) {
            Set-Item -Path ("Env:" + $name) -Value $value
        }
    }
}

# Workspace-wide local inference authority. These values are inherited by the
# shell and every module process it owns, so picker enumeration, conductor
# selection, and worker panes all attach to the same supervised loopback router.
$llamaSupervisorRoot = if ($env:SOVEREIGN_LLAMA_SUPERVISOR_ROOT) {
    [IO.Path]::GetFullPath($env:SOVEREIGN_LLAMA_SUPERVISOR_ROOT)
} else {
    # Default into the bundled Sovereign module, not a build-host path. The supervisor resolves its
    # server binary under <root>\runtime\llama.cpp\current\ (or SOVEREIGN_LLAMACPP_SERVER_EXE from
    # workspace.env). Provision-Workspace.ps1 sets these; the default keeps everything inside the
    # distribution so it is correct on any machine.
    Join-Path $root 'modules\sovereign'
}
$llamaSupervisorLauncher = Join-Path $llamaSupervisorRoot 'Start-LlamaCppSupervisor.ps1'
$llamaApiKeyPath = Join-Path $llamaSupervisorRoot 'runtime\llamacpp_supervisor\api_key'
$env:SOVEREIGN_LLAMA_SUPERVISOR_ROOT = $llamaSupervisorRoot
$env:SOVEREIGN_INFERENCE_BACKEND = 'llama.cpp'
$env:SOVEREIGN_LLAMACPP_HOST = 'http://127.0.0.1:18080'
$env:SOVEREIGN_LLAMA_CPP_BASE_URL = 'http://127.0.0.1:18080'
if (Test-Path -LiteralPath $llamaApiKeyPath -PathType Leaf) {
    $env:SOVEREIGN_LLAMA_CPP_API_KEY = (Get-Content -LiteralPath $llamaApiKeyPath -Raw).Trim()
}

# The repository an OpenCode CODING pane cuts its worktree from. It has to be named: the only
# repository enclosing the workspace is this product checkout, and `coding_worktrees.resolve_base_repo`
# deliberately refuses to cut node/* branches and working trees into the shipped tree (F-131f — that
# refusal is where the orphan `worktrees/worker-pane-2` records came from). No containment means no
# coding pane, so an unset value here is a `worktree_unavailable` refusal, not a silent fallback.
# An operator-set value wins: this launcher only defaults it when nothing else already has.
# SOW_CODING_BASE_REPO is deliberately NOT defaulted to any machine's path. If workspace.env or the
# operator's own environment set it, that value is used; otherwise it stays unset and the coding
# pane reports `worktree_unavailable` (a clean refusal, per the note above) rather than pointing at
# a repository that exists on no other machine.

$blocking = New-Object System.Collections.Generic.List[string]
$advisory = New-Object System.Collections.Generic.List[string]

function Line($label, $value, $color = 'Gray') {
    Write-Host ("  {0,-22}" -f $label) -NoNewline -ForegroundColor DarkGray
    Write-Host $value -ForegroundColor $color
}

function Invoke-Native([scriptblock] $Command) {
    # F-001: run a NATIVE command with a LOCAL ErrorActionPreference of 'Continue'. Under Windows
    # PowerShell 5.1 a native process that writes to stderr while the script's EAP is 'Stop' and
    # stderr is redirected (2>$null, > $null 2>&1) is promoted to a TERMINATING error and throws --
    # so a probe for a MISSING Python, an absent GPU, or a git warning on stderr aborted the whole
    # preflight (an advisory check crashing the one supported launcher). Restoring EAP means the
    # probe's stderr is ordinary output again; $LASTEXITCODE still reports the real exit code, which
    # is what every caller below actually gates on. Cmdlet errors elsewhere keep failing closed.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Command } finally { $ErrorActionPreference = $prev }
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
        $head = Invoke-Native { git -C $root rev-parse --short HEAD 2>$null }
        $gitOk = ($LASTEXITCODE -eq 0)
        $dirty = Invoke-Native { git -C $root status --porcelain 2>$null }
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
    $ver = Invoke-Native { & $py -3.12 --version 2>$null }
    if ($LASTEXITCODE -ne 0 -or -not $ver) {
        Line 'python 3.12' 'NOT AVAILABLE - the shell cannot start' Red
        $blocking.Add('py -3.12 is not available; the shell is pinned to Python 3.12') | Out-Null
    }
    else { Line 'python 3.12' ([string]$ver).Trim() Green }

    # 3.14 runs the Debate module. Its absence does not stop the shell, so it is advisory here
    # and blocking only in the installer, which needs it to build a venv.
    Invoke-Native { & $py -3.14 --version > $null 2>&1 }
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
# String keys are intentional: OrderedDictionary treats an integer index as a
# positional lookup, which rendered the module label blank for a held port.
$modulePorts = [ordered]@{ '5175' = 'sovereign'; '18080' = 'llamacpp'; '5184' = 'distillery'; '8700' = 'debate'; '8765' = 'tokencenter' }
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
# F-007: Get-Process.Path is the interpreter image. `py -3.12` and venvs whose
# python.exe lives outside the tree would otherwise be invisible even when their
# CommandLine targets this checkout (`-m shell.src` / the tree path).
$treePrefix = $root.TrimEnd('\') + '\'
$treeNeedle = $root.TrimEnd('\')
$stray = @(Get-Process python, pythonw, node, electron -ErrorAction SilentlyContinue | Where-Object {
    $p = $null
    try { $p = $_.Path } catch { $p = $null }
    if ($p -and $p.StartsWith($treePrefix, 'OrdinalIgnoreCase')) { return $true }
    $cmd = $null
    try {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
    } catch { $cmd = $null }
    if (-not $cmd) { return $false }
    if ($cmd.IndexOf($treeNeedle, [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    return [bool]($cmd -match '-m\s+shell\.src')
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
    $rows = @(Invoke-Native { nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader,nounits 2>$null })
    if ($LASTEXITCODE -ne 0 -or $rows.Count -eq 0) {
        Line 'vram' 'UNREADABLE - GPU state unobservable, not assumed free' Yellow
        $advisory.Add('nvidia-smi did not answer; GPU state is unknown rather than clear') | Out-Null
    }
    else {
        foreach ($row in $rows) {
            $parts = @($row -split ',' | ForEach-Object { $_.Trim() })
            if ($parts.Count -lt 3) { continue }
            # F-004: memory.used/total can be "[N/A]" (probe E) on some GPUs; `[int]"[N/A]"` throws
            # and terminated this ADVISORY check as a launcher crash. Parse defensively and report
            # the row as unreadable rather than dying.
            $used = 0; $total = 0
            if (-not [int]::TryParse($parts[1], [ref]$used) -or -not [int]::TryParse($parts[2], [ref]$total)) {
                Line "vram gpu $($parts[0])" 'UNREADABLE - values not numeric ([N/A])' Yellow
                continue
            }
            $pct = if ($total -gt 0) { [math]::Round(100 * $used / $total) } else { 0 }
            $col = if ($pct -ge 60) { 'Yellow' } else { 'Green' }
            Line "vram gpu $($parts[0])" "$used MiB of $total MiB ($pct%)" $col
        }
    }

    # Per-process attribution: on a consumer GPU nvidia-smi lists every process holding a
    # graphics context and reports used_memory as [N/A]. That is normal desktop usage, not a
    # finding, so only workspace-relevant holders are reported.
    $relevant = 'ollama', 'llama-server', 'python', 'pythonw', 'node', 'electron'
    $apps = @(Invoke-Native { nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader 2>$null })
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

if (-not (Test-Path -LiteralPath $llamaSupervisorLauncher -PathType Leaf)) {
    throw "The configured local llama.cpp supervisor launcher is missing: $llamaSupervisorLauncher"
}
& $llamaSupervisorLauncher -Root $llamaSupervisorRoot -Port 18080
if ($LASTEXITCODE -ne 0) {
    throw "The local llama.cpp supervisor did not become ready."
}

# F-002/F-003. A deterministic exit code on every path. In Windows PowerShell 5.1 a
# Start-Process -PassThru object reports $null for ExitCode unless its Handle was touched while
# the process was alive (see the Handle cache below); a $null exit code silently becomes 0. This
# helper never returns $null: a process still running (forced-kill in progress) or a null code
# both map to a non-zero failure, so a shell that died is never reported as success.
function Get-SafeExitCode {
    param($Process)
    try {
        if (-not $Process.HasExited) { return 1 }
        $code = $Process.ExitCode
        if ($null -eq $code) { return 1 }
        return [int]$code
    }
    catch { return 1 }
}

# F-005. How long to let the shell shut its modules down cleanly (SIGBREAK/named-event graceful
# path, DB/WAL writers flushing) before this launcher forces it. The shell shares this console, so
# Ctrl+C already reached it; the launcher's job is to WAIT for that graceful stop, not to race it
# with TerminateProcess.
$gracefulStopTimeoutMs = 30000

$url = "http://127.0.0.1:$Port"
$prevDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE
$prevShellNonce = $env:SWS_SHELL_NONCE
$env:PYTHONDONTWRITEBYTECODE = '1'
# F-006: a per-launch nonce, inherited by the shell we start and echoed back by /api/shell-info.
# Readiness then confirms it is THIS process answering, not another SWS shell (a second
# checkout/install) that grabbed the port between preflight and bind - which the version-prefix
# check alone would have accepted while our own process was still coming up or had died.
$launchNonce = [Guid]::NewGuid().ToString('N')
$env:SWS_SHELL_NONCE = $launchNonce
Write-Host "  Starting on $url. Ctrl+C to stop." -ForegroundColor Cyan
Write-Host "  Modules run inside the shell's Job Object, so they stop with it." -ForegroundColor DarkGray
Write-Host ""

# CR-016: launch through the ISOLATED interpreter form, not `-m shell.src`. `-m` runs full site
# initialization, so a machine-global site-packages hook (the review saw `_distutils_hack`) entered
# the process despite the product's zero-site-packages runtime boundary. `-I -S` runs with no site
# module and an isolated environment; `__main__.py` derives and inserts the workspace root itself
# (its documented H-11 isolated-interpreter form), so intra-package imports still resolve. `-B`
# keeps bytecode out of the (immutable) install tree.
$mainScript = Join-Path $root 'shell\src\__main__.py'
$proc = Start-Process -FilePath $py `
                      -ArgumentList @('-3.12', '-I', '-B', '-S', ('"{0}"' -f $mainScript), '--port', "$Port") `
                      -WorkingDirectory $root -NoNewWindow -PassThru
# F-002. Cache the process Handle while it is alive so ExitCode is populated when it exits;
# without this, PS 5.1 reports ExitCode = $null and `exit $proc.ExitCode` becomes exit 0.
$null = $proc.Handle
$script:launcherExit = $null

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
                # F-006: bind to OUR launch via the nonce. A shell that echoes our nonce is the one
                # we started; one with the right version but a different (or absent) nonce is a
                # different SWS shell holding the port, and readiness must not accept it as ours.
                if ([string]$info.nonce -eq $launchNonce) {
                    $ready = $true
                    break
                }
                $identityProblem = "the service on port $Port is a different SWS shell (nonce mismatch); this launcher's process did not bind the port"
            }
            else {
                $identityProblem = "the service on port $Port is not this shell (version '$($info.version)')"
            }
        }
        catch { }
        Start-Sleep -Milliseconds 250
    }

    if ($proc.HasExited) {
        $script:launcherExit = Get-SafeExitCode $proc
        Write-Host "  The shell exited during startup (code $script:launcherExit)." -ForegroundColor Red
        Write-Host ""
        exit $script:launcherExit
    }

    if ($ready) {
        Write-Host "  Ready at $url" -ForegroundColor Green
        if (-not $NoBrowser) { Start-Process $url }
    }
    elseif ($identityProblem) {
        # F-003. An identity mismatch is a launcher failure regardless of the foreign process's own
        # exit code; pin it so the finally block does not overwrite it with that process's code.
        $script:launcherExit = 1
        Write-Host "  $identityProblem" -ForegroundColor Red
        Write-Host "  Not opening a browser. Stopping the process this launcher started." -ForegroundColor Red
        exit 1
    }
    else {
        Write-Host "  The shell did not answer /api/shell-info within the readiness window (~90s: 40 tries, each a 2s probe plus 250ms)." -ForegroundColor Yellow
        Write-Host "  Leaving it running; check the output above for the reason." -ForegroundColor Yellow
    }

    Wait-Process -Id $proc.Id
    # F-003. The shell exited on its own; carry its real code out (this path previously fell off
    # the end of the script with no `exit`, leaking a stale $LASTEXITCODE from an earlier probe).
    $script:launcherExit = Get-SafeExitCode $proc
}
finally {
    if (-not $proc.HasExited) {
        Write-Host ""
        Write-Host "  Stopping the shell (waiting up to $([int]($gracefulStopTimeoutMs/1000))s for graceful shutdown)..." -ForegroundColor Cyan
        # F-005. Ctrl+C reached the shell too (shared console); let it shut its modules down
        # cleanly before forcing, so DB/WAL writers are not TerminateProcess'd mid-write.
        if (-not $proc.WaitForExit($gracefulStopTimeoutMs)) {
            Write-Host "  Graceful shutdown did not complete in time; forcing." -ForegroundColor Yellow
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            $proc.WaitForExit(5000) | Out-Null
        }
    }
    # F-002/F-003. Always exit with a determinate code: an explicitly pinned launcher result if a
    # path set one (startup failure, identity mismatch, clean shell exit), otherwise the shell's
    # own code after the stop above. Never leave a stale $LASTEXITCODE.
    if ($null -eq $script:launcherExit) {
        $script:launcherExit = Get-SafeExitCode $proc
    }
    Write-Host "  Stopped (exit $script:launcherExit)." -ForegroundColor Cyan
    Write-Host ""
    if ($null -eq $prevDontWriteBytecode) { Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue } else { $env:PYTHONDONTWRITEBYTECODE = $prevDontWriteBytecode }
    if ($null -eq $prevShellNonce) { Remove-Item Env:SWS_SHELL_NONCE -ErrorAction SilentlyContinue } else { $env:SWS_SHELL_NONCE = $prevShellNonce }
    exit $script:launcherExit
}
