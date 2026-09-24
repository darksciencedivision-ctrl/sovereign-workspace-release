[CmdletBinding()]
param(
    [string]$Root = $PSScriptRoot,
    [ValidateRange(1, 65535)]
    [int]$Port = 18080
)

$ErrorActionPreference = "Stop"
$rootPath = [System.IO.Path]::GetFullPath($Root)
$pythonPath = Join-Path $rootPath ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Missing SOVEREIGN virtual environment: $pythonPath"
}
# The launcher may be invoked from any working directory (HKCU Run, Startup,
# or an operator shell).  Make the package importable without requiring the
# caller to cd into the repository first.
$env:PYTHONPATH = $rootPath + [IO.Path]::PathSeparator + [string]$env:PYTHONPATH
# An explicit operator start must work even after Stop has disabled autostart.
# Check first so the command remains repeatable without asking the service to
# create a duplicate instance.
$statusJson = & $pythonPath -m sovereign_product.supervisor_service --root $rootPath status
if ($LASTEXITCODE -ne 0) {
    throw "llama.cpp supervisor status check failed."
}
$status = $statusJson | ConvertFrom-Json
if ($status.running) {
    $statusJson | Write-Output
    return
}
& $pythonPath -m sovereign_product.supervisor_service --root $rootPath --port $Port start
if ($LASTEXITCODE -ne 0) {
    throw "llama.cpp supervisor failed to start or confirm readiness."
}
