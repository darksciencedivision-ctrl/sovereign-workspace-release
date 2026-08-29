[CmdletBinding()]
param(
    [string] $OutputDir,
    [string] $Commit = 'HEAD'
)

$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
$workspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if (-not $OutputDir) {
    $OutputDir = Join-Path $workspaceRoot 'release-artifacts'
}
$outputRoot = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

$trackedStatus = & git -C $workspaceRoot status --porcelain=v1 --untracked-files=no
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect git status' }
if ($trackedStatus) { throw 'Refusing release build with tracked modifications' }
$resolvedCommit = (& git -C $workspaceRoot rev-parse $Commit).Trim()
if ($LASTEXITCODE -ne 0 -or $resolvedCommit -notmatch '^[0-9a-f]{40}$') {
    throw "Unable to resolve release commit: $Commit"
}

$versionDoc = Get-Content -Raw -LiteralPath (Join-Path $workspaceRoot 'VERSION.json') | ConvertFrom-Json
$version = [string]$versionDoc.version
if (-not $version) { throw 'VERSION.json does not contain a version' }
$sourceName = "sovereign-workspace-$version-source.zip"
$installName = "sovereign-workspace-$version-install.zip"
$sourcePath = Join-Path $outputRoot $sourceName
$installPath = Join-Path $outputRoot $installName

& git -C $workspaceRoot archive --format=zip --output=$sourcePath $resolvedCommit
if ($LASTEXITCODE -ne 0) { throw 'git archive failed for source artifact' }
& git -C $workspaceRoot archive --format=zip --prefix='sovereign-workspace/' --output=$installPath $resolvedCommit
if ($LASTEXITCODE -ne 0) { throw 'git archive failed for install artifact' }

$utf8NoBom = [Text.UTF8Encoding]::new($false)
$artifacts = @()
foreach ($path in @($sourcePath, $installPath)) {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    $sidecar = $path + '.sha256'
    [IO.File]::WriteAllText($sidecar, "$hash  $([IO.Path]::GetFileName($path))`n", $utf8NoBom)
    $artifacts += [ordered]@{
        name = [IO.Path]::GetFileName($path)
        bytes = (Get-Item -LiteralPath $path).Length
        sha256 = $hash
        sidecar = [IO.Path]::GetFileName($sidecar)
    }
}
$manifest = [ordered]@{
    schema = 'sovereign.release-build.v1'
    version = $version
    source_commit = $resolvedCommit
    archive_basis = 'git archive of the named source commit; ignored host state excluded'
    artifacts = $artifacts
}
$manifestPath = Join-Path $outputRoot 'release-build-manifest.json'
[IO.File]::WriteAllText(
    $manifestPath,
    (($manifest | ConvertTo-Json -Depth 8) + "`n"),
    $utf8NoBom
)
Write-Output "build_release: $resolvedCommit"
foreach ($artifact in $artifacts) {
    Write-Output ("{0} {1} {2}" -f $artifact.sha256, $artifact.bytes, $artifact.name)
}
