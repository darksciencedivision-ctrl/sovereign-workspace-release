[CmdletBinding()]
param(
    [string]$Root = $PSScriptRoot,
    [string]$Profile = "qwen3-0.6b"
)

$ErrorActionPreference = "Stop"
$rootPath = [System.IO.Path]::GetFullPath($Root)
$pythonPath = Join-Path $rootPath ".venv\Scripts\python.exe"
& $pythonPath -m sovereign_product.freetoken_service --root $rootPath --profile $Profile recover
if ($LASTEXITCODE -ne 0) {
    throw "FreeToken supervisor recover failed."
}
