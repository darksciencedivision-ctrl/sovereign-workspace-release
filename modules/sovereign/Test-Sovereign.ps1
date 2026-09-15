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

# CR-030: the source-only tree intentionally removed the Sovereign Python and UI unit-test suites.
# The retained validation must be TRUTHFUL: run the lanes that exist, and record any intentionally
# removed lane as UNSUPPORTED (non-qualifying) rather than throwing a false failure or claiming a
# pass it never ran. The final banner reflects whether any lane was unsupported.
$script:unsupportedLanes = @()

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

    # F-120. Compile-check to a TEMP bytecode cache, not into the install tree (the plain
    # compileall wrote __pycache__ under the installation, which verify_install/uninstall's
    # exact-path-set check then flagged).
    $previousPycachePrefix = $env:PYTHONPYCACHEPREFIX
    $env:PYTHONPYCACHEPREFIX = Join-Path ([System.IO.Path]::GetTempPath()) "sovereign-compileall"
    try {
        & $pythonPath -m compileall -q $compileTargets
    } finally {
        $env:PYTHONPYCACHEPREFIX = $previousPycachePrefix
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Python compile check failed."
    }

    # CR-030: run only the Python test dirs that actually EXIST in this source-only tree. The
    # Sovereign unit-test suite was intentionally removed, so `pytest tests` would always fail on a
    # missing directory. If a test dir exists, run it and fail closed on a real failure; otherwise
    # record the lane as intentionally unsupported (non-qualifying) instead of inventing a failure.
    $testTargets = @()
    foreach ($dir in @("tests", "tests_product")) {
        if (Test-Path -LiteralPath (Join-Path $rootPath $dir) -PathType Container) {
            $testTargets += $dir
        }
    }
    if ($testTargets.Count -gt 0) {
        & $pythonPath -m pytest -q @testTargets
        if ($LASTEXITCODE -ne 0) {
            throw "Python test suite failed."
        }
    } else {
        Write-Host "  Sovereign Python unit tests: INTENTIONALLY UNSUPPORTED in the source-only tree (non-qualifying)." -ForegroundColor Yellow
        $script:unsupportedLanes += "sovereign-python-unit"
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

# CR-030: never claim a clean "validation passed" when a lane was intentionally unsupported — that
# would be a release-qualifying claim without executable coverage. Report the honest outcome.
if ($script:unsupportedLanes.Count -gt 0) {
    Write-Host ("SOVEREIGN validation completed; the executed lanes passed, but " +
        "$($script:unsupportedLanes.Count) lane(s) are intentionally unsupported (non-qualifying): " +
        ($script:unsupportedLanes -join ", ")) -ForegroundColor Yellow
} else {
    Write-Host "SOVEREIGN validation passed."
}
