[CmdletBinding()]
param(
    [string]$Root = $PSScriptRoot
)

$ErrorActionPreference = "Stop"
$rootPath = [System.IO.Path]::GetFullPath($Root)
$pythonPath = Join-Path $rootPath ".venv\Scripts\python.exe"
$env:PYTHONPATH = $rootPath + [IO.Path]::PathSeparator + [string]$env:PYTHONPATH
& $pythonPath -m sovereign_product.supervisor_service --root $rootPath status
if ($LASTEXITCODE -ne 0) {
    throw "llama.cpp supervisor status failed."
}
