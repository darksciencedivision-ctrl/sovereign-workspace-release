<#
.SYNOPSIS
    Sovereign Workspace - one-command local provisioning (SWS-PUNCHLIST-DIRECTIVE-20260921 WS-3.1).

.DESCRIPTION
    Sets up THIS machine to run the workspace from the folder, without bundling any machine-specific
    binaries or multi-GB model weights into the sealed product. It:

      1. Provisions a per-module Python virtual environment for every module with a Python runtime
         and installs its declared dependencies deterministically. An existing .venv is verified
         against the declared lock (not assumed current): drift is reported, and reconciled by a
         deterministic reinstall.
             - modules\sovereign\.venv on 3.12  (hash-locked requirements.lock.txt)
             - modules\debate\.venv    on 3.14  (hash-locked requirements.lock.txt; Debate is on 3.14)
             - modules\sow\.venv       on 3.12  (requirements.txt)
      2. Runs `npm install` for the SOW desktop app (Electron), so the Multi-Model Terminal can open.
      2b. Builds the Sovereign operator UI (`npm ci && npm run build` in ui\ui_shell) and validates
         its assets; the built dist is not shipped, so without this the product serves 503 at `/`.
      3. Locates the llama.cpp server binary and records it - with its models and the optional SOW
         coding repo - in `release-worktree\workspace.env`, which Start-Shell.ps1 loads at startup.
         Nothing large is copied into the tree; the sealed product stays free of any one machine's
         absolute paths.
      4. Checks Ollama (the other supported backend) and reports how many models are installed.
      5. Prints a readiness report: what is provisioned, and exactly what remains (models to pull).

    Re-runnable. Each step is independent; a missing prerequisite (an interpreter, npm, a binary) is
    reported and skipped, never fatal, so a partial environment still gets as far as it can.

.PARAMETER LlamaCppExe
    Full path to your `llama-server.exe`. If omitted, PATH and a few common locations are searched.

.PARAMETER LlamaModelsDir
    Directory holding your GGUF model files, recorded for the supervisor. Optional.

.PARAMETER SowCodingRepo
    Repository the SOW coding pane cuts worktrees from. Optional; left unset means the coding pane
    cleanly reports "worktree_unavailable" rather than pointing at a path that does not exist.

.PARAMETER ReportOnly
    Detect and report only. Creates no venvs, installs nothing, writes no workspace.env.

.PARAMETER SkipVenvs
    Skip the Python virtual environments / dependency install.

.PARAMETER SkipElectron
    Skip the SOW `npm install`.

.EXAMPLE
    .\Provision-Workspace.ps1
.EXAMPLE
    .\Provision-Workspace.ps1 -LlamaCppExe "C:\tools\llama.cpp\llama-server.exe" -LlamaModelsDir "D:\models"
.EXAMPLE
    .\Provision-Workspace.ps1 -ReportOnly
#>
[CmdletBinding()]
param(
    [string] $LlamaCppExe,
    [string] $LlamaModelsDir,
    [string] $SowCodingRepo,
    [switch] $ReportOnly,
    [switch] $SkipVenvs,
    [switch] $SkipElectron
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Head($t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }
function Ok($t)   { Write-Host "  [ok]    $t" -ForegroundColor Green }
function Warn($t) { Write-Host "  [warn]  $t" -ForegroundColor Yellow }
function Miss($t) { Write-Host "  [todo]  $t" -ForegroundColor Yellow }
function Info($t) { Write-Host "  $t" -ForegroundColor DarkGray }

# --- locate the distribution (release worktree) ------------------------------------------------
# Works whether this script sits INSIDE the distribution (beside Start-Shell.ps1) or one level
# above it (beside the `release-worktree` folder, next to the other launchers).
function Test-Worktree([string] $d) {
    return (Test-Path -LiteralPath (Join-Path $d 'Start-Shell.ps1') -PathType Leaf) -and
           (Test-Path -LiteralPath (Join-Path $d 'shell') -PathType Container)
}
$worktree = $null
if (Test-Worktree $root) { $worktree = $root }
else {
    foreach ($cand in @('release-worktree') + (Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })) {
        $d = Join-Path $root $cand
        if (Test-Worktree $d) { $worktree = $d; break }
    }
}
if (-not $worktree) { throw "No Sovereign Workspace source tree found (need one with Start-Shell.ps1 and shell\)." }

Write-Host "`n############ Sovereign Workspace provisioning ############" -ForegroundColor Cyan
Write-Host "distribution: $worktree"
if ($ReportOnly) { Write-Host "MODE: report only (no changes will be made)" -ForegroundColor Yellow }

$report = [ordered]@{}

# --- helper: resolve a py launcher for a given version ------------------------------------------
function Resolve-Py([string] $ver) {
    try { & py "-$ver" --version *> $null 2>&1; if ($LASTEXITCODE -eq 0) { return @('py', "-$ver") } } catch {}
    return $null
}

# --- 1. Python venvs ----------------------------------------------------------------------------
Head "Python virtual environments"
# SW-03: every module with a Python runtime gets its OWN provisioned interpreter (including SOW), and
# an existing .venv is NEVER assumed current - its installed distributions are compared against the
# declared lock and drift is reported (ReportOnly) or reconciled (a deterministic reinstall).
$venvTargets = @(
    @{ id = 'sovereign'; dir = (Join-Path $worktree 'modules\sovereign'); ver = '3.12'; lock = 'requirements.lock.txt'; hashed = $true },
    @{ id = 'debate';    dir = (Join-Path $worktree 'modules\debate');    ver = '3.14'; lock = 'requirements.lock.txt'; hashed = $true },
    @{ id = 'sow';       dir = (Join-Path $worktree 'modules\sow');        ver = '3.12'; lock = 'requirements.txt';      hashed = $false }
)

function Get-DeclaredPins([string] $lockPath) {
    $pins = @{}
    foreach ($line in Get-Content -LiteralPath $lockPath) {
        $m = [regex]::Match($line.Trim(), '^([A-Za-z0-9_.-]+)==([^\s\\;]+)')
        if ($m.Success) { $pins[$m.Groups[1].Value.ToLower().Replace('_', '-')] = $m.Groups[2].Value }
    }
    return $pins
}

function Get-VenvDrift([string] $venvPy, [string] $lockPath) {
    # Declared pins whose installed version differs or is missing. Empty = the venv matches the lock.
    $declared = Get-DeclaredPins $lockPath
    if ($declared.Count -eq 0) { return @() }
    $installed = @{}
    $listing = & $venvPy -m pip list --format=json 2>$null
    try {
        foreach ($p in ($listing | ConvertFrom-Json)) {
            $installed[$p.name.ToLower().Replace('_', '-')] = $p.version
        }
    } catch {}
    $drift = @()
    foreach ($name in $declared.Keys) {
        $have = $installed[$name]
        if ($have -ne $declared[$name]) {
            $shown = 'MISSING'
            if ($have) { $shown = $have }
            $drift += ("{0} want {1} have {2}" -f $name, $declared[$name], $shown)
        }
    }
    return $drift
}

foreach ($t in $venvTargets) {
    $venvPy = Join-Path $t.dir '.venv\Scripts\python.exe'
    $lockPath = Join-Path $t.dir $t.lock
    $exists = Test-Path -LiteralPath $venvPy
    if ($SkipVenvs) { Miss "$($t.id): venv provisioning skipped (-SkipVenvs)"; $report[$t.id + ' venv'] = 'skipped'; continue }
    if (-not (Test-Path -LiteralPath $lockPath)) { Warn "$($t.id): no $($t.lock); cannot provision deterministically"; $report[$t.id + ' venv'] = 'no lock'; continue }

    if (-not $exists) {
        $py = Resolve-Py $t.ver
        if (-not $py) { Miss "$($t.id): Python $($t.ver) not found (install it, then re-run)"; $report[$t.id + ' venv'] = "needs py -$($t.ver)"; continue }
        if ($ReportOnly) { Miss "$($t.id): .venv MISSING - would create on py -$($t.ver) and install $($t.lock)"; $report[$t.id + ' venv'] = 'would create'; continue }
        Info "$($t.id): creating .venv on $($py -join ' ')"
        & $py[0] $py[1] -m venv (Join-Path $t.dir '.venv')
    }

    if (Test-Path -LiteralPath $venvPy) { $drift = Get-VenvDrift $venvPy $lockPath } else { $drift = @('venv interpreter not present') }
    if ($exists -and $drift.Count -eq 0) { Ok "$($t.id): venv present and matches $($t.lock)"; $report[$t.id + ' venv'] = 'present + matches lock'; continue }
    if ($ReportOnly) {
        $sample = [string]::Join('; ', ($drift | Select-Object -First 4))
        Miss "$($t.id): $($drift.Count) dependency drift(s) vs $($t.lock): $sample"
        $report[$t.id + ' venv'] = "$($drift.Count) drift(s)"
        continue
    }
    Info "$($t.id): installing $($t.lock) to reconcile $($drift.Count) drift(s)"
    if ($t.hashed) { & $venvPy -m pip install --require-hashes -r $lockPath }
    else { & $venvPy -m pip install -r $lockPath }
    if ($LASTEXITCODE -ne 0) { Warn "$($t.id): pip install reported errors (see output above)"; $report[$t.id + ' venv'] = 'deps FAILED'; continue }
    $after = Get-VenvDrift $venvPy $lockPath
    if ($after.Count -eq 0) { Ok "$($t.id): venv reconciled to $($t.lock)"; $report[$t.id + ' venv'] = 'installed + matches lock' }
    else { Warn "$($t.id): $($after.Count) drift(s) remain after install"; $report[$t.id + ' venv'] = "$($after.Count) drift(s) remain" }
}

# --- 2. SOW Electron ----------------------------------------------------------------------------
Head "SOW desktop app (Electron)"
$sowDesktop = Join-Path $worktree 'modules\sow\apps\desktop'
$electronExe = Join-Path $sowDesktop 'node_modules\electron\dist\electron.exe'
if (Test-Path -LiteralPath $electronExe) { Ok "Electron already installed"; $report['sow electron'] = 'present' }
elseif ($SkipElectron) { Miss "Electron missing (skipped: -SkipElectron)"; $report['sow electron'] = 'skipped' }
elseif (-not (Test-Path -LiteralPath (Join-Path $sowDesktop 'package.json'))) { Warn "no apps\desktop\package.json; cannot npm install"; $report['sow electron'] = 'no package.json' }
else {
    $npm = try { (Get-Command npm -ErrorAction Stop).Source } catch { $null }
    if (-not $npm) { Miss "npm not found (install Node.js, then re-run)"; $report['sow electron'] = 'needs npm' }
    elseif ($ReportOnly) { Miss "would run 'npm install' in $sowDesktop"; $report['sow electron'] = 'would install' }
    else {
        Info "running npm install in apps\desktop (this can take a few minutes)"
        Push-Location -LiteralPath $sowDesktop
        try { & npm install } finally { Pop-Location }
        if (Test-Path -LiteralPath $electronExe) { Ok "Electron installed"; $report['sow electron'] = 'installed' }
        else { Warn "npm install ran but electron.exe not found"; $report['sow electron'] = 'install incomplete' }
    }
}

# --- 2b. Sovereign operator UI (SW-04) ----------------------------------------------------------
# The built UI (ui_shell/dist) is gitignored, so a fresh archive has none and the product serves
# 503 at `/`. Build it here and validate its assets before the module is considered usable.
Head "Sovereign operator UI"
$uiDir = Join-Path $worktree 'modules\sovereign\ui\ui_shell'
$uiDist = Join-Path $uiDir 'dist'
$uiIndex = Join-Path $uiDist 'index.html'
$uiAssets = Join-Path $uiDist 'assets'
if (-not (Test-Path -LiteralPath (Join-Path $uiDir 'package.json'))) {
    Warn "no ui_shell\package.json; cannot build the Sovereign UI"; $report['sovereign ui'] = 'no package.json'
}
elseif ((Test-Path -LiteralPath $uiIndex) -and (Test-Path -LiteralPath $uiAssets)) {
    Ok "Sovereign UI already built (dist\index.html + assets)"; $report['sovereign ui'] = 'built'
}
else {
    $npm = try { (Get-Command npm -ErrorAction Stop).Source } catch { $null }
    if (-not $npm) { Miss "npm not found (install Node.js, then re-run) - the Sovereign UI cannot be built"; $report['sovereign ui'] = 'needs npm' }
    elseif ($ReportOnly) { Miss "Sovereign UI not built; would run npm ci + npm run build in ui_shell"; $report['sovereign ui'] = 'would build' }
    else {
        Info "building Sovereign UI (npm ci + npm run build) - this can take a few minutes"
        Push-Location -LiteralPath $uiDir
        try {
            if (Test-Path -LiteralPath (Join-Path $uiDir 'package-lock.json')) { & npm ci } else { & npm install }
            if ($LASTEXITCODE -eq 0) { & npm run build }
        } finally { Pop-Location }
        if ((Test-Path -LiteralPath $uiIndex) -and (Test-Path -LiteralPath $uiAssets)) {
            Ok "Sovereign UI built (dist\index.html + assets)"; $report['sovereign ui'] = 'built'
        }
        else { Warn "UI build ran but dist\index.html or assets not found"; $report['sovereign ui'] = 'build incomplete' }
    }
}

# --- 3. llama.cpp binary + models (recorded to workspace.env) ------------------------------------
Head "llama.cpp inference backend"
function Find-LlamaExe {
    if ($LlamaCppExe) { return $LlamaCppExe }
    if ($env:SOVEREIGN_LLAMACPP_SERVER_EXE) { return $env:SOVEREIGN_LLAMACPP_SERVER_EXE }
    $onPath = try { (Get-Command llama-server.exe -ErrorAction Stop).Source } catch { $null }
    if ($onPath) { return $onPath }
    foreach ($p in @(
        (Join-Path $worktree 'modules\sovereign\runtime\llama.cpp\current\llama-server.exe'),
        'C:\tools\llama.cpp\llama-server.exe',
        "$env:LOCALAPPDATA\llama.cpp\llama-server.exe")) {
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}
$llamaExe = Find-LlamaExe
# Only the keys we actually resolve this run; merged into workspace.env below (existing keys and
# operator additions are preserved).
$generated = [ordered]@{}
if ($llamaExe -and (Test-Path -LiteralPath $llamaExe)) {
    Ok "llama-server.exe: $llamaExe"
    $generated['SOVEREIGN_LLAMACPP_SERVER_EXE'] = $llamaExe
    # Trust-on-first-use: pin THIS binary's hash so the supervisor accepts your own build and rejects
    # a later silent swap (the launch path enforces it). Delete the pin to fall back to the vetted hash.
    try {
        $generated['SOVEREIGN_LLAMACPP_SERVER_SHA256'] = (Get-FileHash -LiteralPath $llamaExe -Algorithm SHA256).Hash.ToLower()
        Info "pinned server hash $($generated['SOVEREIGN_LLAMACPP_SERVER_SHA256'])"
        $impl = Join-Path (Split-Path -Parent $llamaExe) 'llama-server-impl.dll'
        if (Test-Path -LiteralPath $impl) { $generated['SOVEREIGN_LLAMACPP_IMPL_SHA256'] = (Get-FileHash -LiteralPath $impl -Algorithm SHA256).Hash.ToLower() }
    } catch { Warn "could not hash the binary: $_" }
    $report['llama.cpp binary'] = 'found + hash-pinned'
} else {
    Miss "llama-server.exe not found. Install/build llama.cpp, then re-run with -LlamaCppExe <path> (or set SOVEREIGN_LLAMACPP_SERVER_EXE)."
    $report['llama.cpp binary'] = 'NOT FOUND (set -LlamaCppExe)'
}
if ($LlamaModelsDir) {
    if (Test-Path -LiteralPath $LlamaModelsDir) { Ok "models dir recorded (informational): $LlamaModelsDir"; $generated['SOVEREIGN_LLAMACPP_MODELS_DIR'] = $LlamaModelsDir; $report['llama.cpp models'] = 'recorded (informational)' }
    else { Warn "models dir not found: $LlamaModelsDir"; $report['llama.cpp models'] = 'path missing' }
} else {
    Info "no -LlamaModelsDir given; place your GGUF models and select them through the supervisor."
    $report['llama.cpp models'] = 'operator-supplied'
}
if ($SowCodingRepo) { $generated['SOW_CODING_BASE_REPO'] = $SowCodingRepo; Ok "SOW coding repo: $SowCodingRepo" }

# --- 4. Ollama (the other backend) --------------------------------------------------------------
Head "Ollama backend"
try {
    $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3 -ErrorAction Stop
    $count = @($tags.models).Count
    Ok ('Ollama reachable on :11434 - ' + $count + ' model(s) installed')
    $report['ollama'] = ('reachable, ' + $count + ' models')
} catch {
    Miss 'Ollama not reachable on 127.0.0.1:11434 (start it, or use the llama.cpp backend). Use "ollama pull <tag>" to add models.'
    $report['ollama'] = 'not running'
}

# --- write workspace.env (MERGE, do not clobber operator settings) ------------------------------
$envPath = Join-Path $worktree 'workspace.env'
if ($ReportOnly) { Info "would merge $($generated.Count) generated key(s) into $envPath" }
else {
    # Start from the existing file so operator-added keys and previously-provisioned values survive;
    # only the keys resolved THIS run are updated. (Audit N2: a rerun must not drop prior settings.)
    $merged = [ordered]@{}
    if (Test-Path -LiteralPath $envPath) {
        foreach ($line in Get-Content -LiteralPath $envPath) {
            $t = $line.Trim()
            if (-not $t -or $t.StartsWith('#')) { continue }
            $eq = $t.IndexOf('='); if ($eq -lt 1) { continue }
            $merged[$t.Substring(0, $eq).Trim()] = $t.Substring($eq + 1).Trim()
        }
        Copy-Item -LiteralPath $envPath -Destination "$envPath.bak" -Force
        Info "existing workspace.env backed up to workspace.env.bak, then merged"
    }
    foreach ($k in $generated.Keys) { $merged[$k] = $generated[$k] }
    $out = New-Object System.Collections.Generic.List[string]
    $out.Add("# workspace.env - per-machine provisioning, written by Provision-Workspace.ps1.")
    $out.Add("# Loaded by Start-Shell.ps1. Gitignored; never shipped. An already-set env var wins.")
    $out.Add("# Rerun-safe: regenerated keys update; every other key you add here is preserved.")
    foreach ($k in $merged.Keys) { $out.Add("$k=$($merged[$k])") }
    Set-Content -LiteralPath $envPath -Value $out -Encoding utf8
    Ok "wrote $envPath ($($merged.Count) key(s))"
}

# --- 5. readiness report ------------------------------------------------------------------------
Head "Readiness"
foreach ($k in $report.Keys) { Write-Host ("  {0,-18} {1}" -f $k, $report[$k]) }
Write-Host ""
Write-Host "Next:" -ForegroundColor Cyan
Write-Host '  1. Install model weights for whichever backend you use:' -ForegroundColor Gray
Write-Host '       Ollama:    ollama pull <tag>        llama.cpp: place GGUF files, point the supervisor at them' -ForegroundColor DarkGray
Write-Host ('  2. Start the workspace:  ' + (Join-Path $worktree 'Start-Shell.ps1') + '   (or Start-Sovereign.ps1 beside the folder)') -ForegroundColor Gray
Write-Host ('  3. Check readiness:      ' + (Join-Path $worktree 'Start-Shell.ps1') + ' -CheckOnly') -ForegroundColor Gray
$gate = Join-Path $worktree 'tools\cleanroom\Test-CleanRoomBoot.ps1'
if (Test-Path -LiteralPath $gate) { Write-Host ('     (source checkout also has the clean-room gate: ' + $gate + ')') -ForegroundColor DarkGray }
Write-Host ""
