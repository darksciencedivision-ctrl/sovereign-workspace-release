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

    if ($Full) {
        $statePath = Join-Path $rootPath "runtime\service_state.json"
        if (Test-Path -LiteralPath $statePath -PathType Leaf) {
            $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
            & $pythonPath "ui\adapter_service\smoke_test.py" --base (
                ([string]$state.url).TrimEnd("/")
            )
            if ($LASTEXITCODE -ne 0) {
                throw "Live unified-service compatibility smoke failed."
            }
        }
    }
} finally {
    Pop-Location
}

Write-Host "SOVEREIGN validation passed."
