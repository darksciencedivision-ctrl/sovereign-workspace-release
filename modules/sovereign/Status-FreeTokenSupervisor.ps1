[CmdletBinding()]
param(
    [string]$Root = $PSScriptRoot
)

$ErrorActionPreference = "Stop"
$rootPath = [System.IO.Path]::GetFullPath($Root)
$pythonPath = Join-Path $rootPath ".venv\Scripts\python.exe"
& $pythonPath -m sovereign_product.freetoken_service --root $rootPath status
if ($LASTEXITCODE -ne 0) {
    throw "FreeToken supervisor status failed."
}
