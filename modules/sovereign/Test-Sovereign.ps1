[CmdletBinding()]
param(
    [string]$Root = $PSScriptRoot,
    [switch]$Full
)

$ErrorActionPreference = "Stop"
$rootPath = [System.IO.Path]::GetFullPath($Root)
$markerPath = Join-Path $rootPath ".sovereign-root"
$pythonPath = Join-Path $rootPath ".venv\Scripts\python.exe"
$uiPath = Join-Path $rootPath "ui\ui_shell"

if (
    -not (Test-Path -LiteralPath $markerPath -PathType Leaf) -or
    (Get-Content -LiteralPath $markerPath -Raw).Trim() -ne "SOVEREIGN_ROOT_MARKER=1"
) {
    throw "The selected directory is not a marker-validated SOVEREIGN root: $rootPath"
}
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Missing SOVEREIGN virtual environment: $pythonPath"
}
if (-not (Test-Path -LiteralPath (Join-Path $uiPath "package.json") -PathType Leaf)) {
    throw "Missing UI package manifest: $uiPath\package.json"
}
if ($null -eq (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is required for UI validation."
}

$compileTargets = @(
    (Join-Path $rootPath "sovereign_product"),
    (Join-Path $rootPath "runtime_integrity"),
    (Join-Path $rootPath "synthesis"),
    (Join-Path $rootPath "tools"),
    (Join-Path $rootPath "ui\adapter_service")
)
$compileTargets += @(
    Get-ChildItem -LiteralPath $rootPath -File -Filter "*.py" |
        Select-Object -ExpandProperty FullName
)

Push-Location $rootPath
try {
    & $pythonPath -c (
        "import sys; " +
        "from system_manifest import load_system_manifest; " +
        "load_system_manifest(manifest_path=sys.argv[1])"
    ) (Join-Path $rootPath "SYSTEM_MANIFEST.json")
    if ($LASTEXITCODE -ne 0) {
        throw "SYSTEM_MANIFEST validation failed."
    }

    & $pythonPath -m compileall -q $compileTargets
    if ($LASTEXITCODE -ne 0) {
        throw "Python compile check failed."
    }

    & $pythonPath -m pytest -q tests tests_product
    if ($LASTEXITCODE -ne 0) {
        throw "Python test suite failed."
    }

    & $pythonPath "ui\adapter_service\adapter.py" --help *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Legacy adapter compatibility handoff failed."
    }

    Push-Location $uiPath
    try {
        & npm run typecheck
        if ($LASTEXITCODE -ne 0) {
            throw "UI type check failed."
        }
        & npm run build
        if ($LASTEXITCODE -ne 0) {
            throw "UI production build failed."
        }
    } finally {
        Pop-Location
    }

    Write-Host "STATIC_PASS: marker, venv, manifest, compileall, tests, adapter handoff, UI typecheck+build."

    if ($Full) {
        $statePath = Join-Path $rootPath "runtime\service_state.json"
        if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
            throw "LIVE_FAIL: -Full requires a running SOVEREIGN service but no service state exists at $statePath. Start SOVEREIGN with Start-Sovereign.ps1 and retry."
        }

        try {
            $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        } catch {
            throw "LIVE_FAIL: service state at $statePath is not valid JSON: $($_.Exception.Message)"
        }

        if (-not $state.url) {
            throw "LIVE_FAIL: service state at $statePath has no url field."
        }

        $servicePid = 0
        if (-not [int]::TryParse([string]$state.pid, [ref]$servicePid) -or $servicePid -le 0) {
            throw "LIVE_FAIL: service state at $statePath has no usable pid field."
        }

        $recordedProcess = Get-Process -Id $servicePid -ErrorAction SilentlyContinue
        if ($null -eq $recordedProcess) {
            throw "LIVE_FAIL: recorded service PID $servicePid is not running; runtime\service_state.json is stale. Restart with Start-Sovereign.ps1."
        }

        if ($state.process_started_at) {
            try {
                $recordedStart = [DateTimeOffset]::Parse([string]$state.process_started_at)
            } catch {
                throw "LIVE_FAIL: process_started_at is not a parseable timestamp: $($_.Exception.Message)"
            }
            $actualStart = [DateTimeOffset]$recordedProcess.StartTime.ToUniversalTime()
            if ([Math]::Abs(($actualStart - $recordedStart).TotalMilliseconds) -gt 100) {
                throw "LIVE_FAIL: PID $servicePid is running but its start time does not match the recorded process_started_at; runtime\service_state.json is stale."
            }
        }

        $base = ([string]$state.url).TrimEnd("/")
        try {
            Invoke-WebRequest -Uri "$base/v1/health" -UseBasicParsing -TimeoutSec 10 | Out-Null
        } catch {
            throw "LIVE_FAIL: health endpoint $base/v1/health did not respond: $($_.Exception.Message)"
        }

        & $pythonPath "ui\adapter_service\smoke_test.py" --base $base
        if ($LASTEXITCODE -ne 0) {
            throw "LIVE_FAIL: live unified-service compatibility smoke failed against $base."
        }

        Write-Host "LIVE_PASS: live smoke executed and passed against $base (PID $servicePid)."
    } else {
        Write-Host "LIVE_SKIPPED: static-only run; pass -Full to require live validation."
    }
} finally {
    Pop-Location
}

Write-Host "SOVEREIGN validation passed."
