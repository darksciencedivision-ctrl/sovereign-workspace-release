[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Dest
)

$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
$destRoot = [IO.Path]::GetFullPath($Dest).TrimEnd('\')
$destPrefix = $destRoot + '\'
if ($destRoot -eq [IO.Path]::GetPathRoot($destRoot)) { throw 'Refusing filesystem-root destination' }
$manifestPath = Join-Path $destRoot 'install-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'install-manifest.json is missing' }
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.schema -ne 'sovereign.install-manifest.v1') { throw 'Unknown install manifest schema' }
if (-not ([string]$manifest.install_root).Equals($destRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Install manifest root does not match -Dest'
}

$expectedInstall = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($entry in $manifest.paths) {
    if ($entry.scope -eq 'install') { [void]$expectedInstall.Add([string]$entry.path) }
}
$actualInstall = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
Get-ChildItem -LiteralPath $destRoot -Force -Recurse | ForEach-Object {
    [void]$actualInstall.Add($_.FullName.Substring($destPrefix.Length).Replace('\', '/'))
}
if (-not $actualInstall.SetEquals($expectedInstall)) {
    $missing = @($expectedInstall | Where-Object { -not $actualInstall.Contains($_) })
    $extra = @($actualInstall | Where-Object { -not $expectedInstall.Contains($_) })
    throw "Install path-set mismatch; missing=$($missing -join ','); extra=$($extra -join ',')"
}

$verifiedFiles = 0
foreach ($entry in $manifest.paths) {
    $path = if ($entry.scope -eq 'install') { Join-Path $destRoot ([string]$entry.path) } else { [string]$entry.path }
    if ($entry.kind -eq 'directory') {
        if (-not (Test-Path -LiteralPath $path -PathType Container)) { throw "Directory missing: $path" }
        continue
    }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "File missing: $path" }
    if ($entry.kind -ne 'manifest') {
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
        if ($actual -ne [string]$entry.sha256) { throw "Hash mismatch: $path" }
        $verifiedFiles++
    }
}

$config = Get-Content -Raw -LiteralPath (Join-Path $destRoot 'shell\config\install.json') | ConvertFrom-Json
if (-not ([string]$config.modules_root).Equals($destRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Installed modules_root is not destination-correct'
}
$env:PYTHONDONTWRITEBYTECODE = '1'
$sovereignRoot = Join-Path $destRoot 'modules\sovereign'
Push-Location $sovereignRoot
try {
    & (Join-Path $sovereignRoot '.venv\Scripts\python.exe') -B -c "import flask,requests,chromadb; import system_manifest; print('verify sovereign import: OK')"
    if ($LASTEXITCODE -ne 0) { throw 'SOVEREIGN import verification failed' }
}
finally { Pop-Location }
$debateRoot = Join-Path $destRoot 'modules\debate'
$debateLogScratch = Join-Path ([IO.Path]::GetTempPath()) ("sovereign-verify-debate-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $debateLogScratch | Out-Null
$priorDebateLogDir = $env:DEBATE_LOG_DIR
Push-Location $debateRoot
try {
    $env:DEBATE_LOG_DIR = $debateLogScratch
    & (Join-Path $debateRoot '.venv\Scripts\python.exe') -B -c "import fastapi,httpx,pydantic; import app; print('verify debate import: OK')"
    if ($LASTEXITCODE -ne 0) { throw 'Debate import verification failed' }
}
finally {
    Pop-Location
    if ($null -eq $priorDebateLogDir) { Remove-Item Env:DEBATE_LOG_DIR -ErrorAction SilentlyContinue }
    else { $env:DEBATE_LOG_DIR = $priorDebateLogDir }
    $resolvedScratch = [IO.Path]::GetFullPath($debateLogScratch)
    $tempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if (-not $resolvedScratch.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing verification scratch cleanup outside temp: $resolvedScratch"
    }
    Remove-Item -LiteralPath $resolvedScratch -Recurse -Force
}
Push-Location (Join-Path $destRoot 'modules\sow\apps\desktop')
try {
    & node -e "require('ws');require('node-pty');console.log('verify SOW desktop import: OK')"
    if ($LASTEXITCODE -ne 0) { throw 'SOW desktop import verification failed' }
}
finally { Pop-Location }
Write-Output "verify_install: $verifiedFiles file hashes and exact path set verified"
