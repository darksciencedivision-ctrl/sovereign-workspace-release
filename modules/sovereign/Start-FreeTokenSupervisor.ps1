[CmdletBinding()]
param(
    [string]$Root = $PSScriptRoot,
    [ValidateRange(1, 65535)]
    [int]$Port = 1919,
    [string]$Profile = "qwen3-0.6b",
    [string]$Workload = ""
)

$ErrorActionPreference = "Stop"
$rootPath = [System.IO.Path]::GetFullPath($Root)
$pythonPath = Join-Path $rootPath ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Missing SOVEREIGN virtual environment: $pythonPath"
}
if ($Workload) {
    # Designated FreeToken workload: profile/port come from
    # runtime\backend_selection.json; starts on demand with GPU transition.
    & $pythonPath -m sovereign_product.freetoken_service --root $rootPath --workload $Workload ensure-runtime
} else {
    & $pythonPath -m sovereign_product.freetoken_service --root $rootPath --port $Port --profile $Profile start
}
if ($LASTEXITCODE -ne 0) {
    throw "FreeToken supervisor failed to start."
}
