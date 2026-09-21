[CmdletBinding()]
param(
    [string]$Root = $PSScriptRoot,
    [ValidateRange(1, 65535)]
    [int]$Port = 18080
)

$ErrorActionPreference = "Stop"
$rootPath = [System.IO.Path]::GetFullPath($Root)
$pythonPath = Join-Path $rootPath ".venv\Scripts\python.exe"
$env:PYTHONPATH = $rootPath + [IO.Path]::PathSeparator + [string]$env:PYTHONPATH
& $pythonPath -m sovereign_product.supervisor_service --root $rootPath --port $Port install-persistence
if ($LASTEXITCODE -ne 0) {
    throw "llama.cpp supervisor persistence install failed."
}
