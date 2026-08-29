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
foreach ($path in @($sourcePath, $installPath)) {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    $sidecar = $path + '.sha256'
    [IO.File]::WriteAllText($sidecar, "$hash  $([IO.Path]::GetFileName($path))`n", $utf8NoBom)
}

# CLOSEOUT-01 X-1 (A-1 / OD-24): this manifest is the SOLE authority for release-artifact
# hashes, so it must enumerate every artifact in the output directory -- not only the two
# composite ZIPs built above. The six per-module archives are cut by the C3 tooling and
# previously had no authoritative hash record anywhere. Each sidecar is hashed in its own
# right, and each sidecar's recorded hash is cross-checked against its artifact.
# This file cannot enumerate itself: writing its own hash into it would change that hash.
$artifacts = @()
foreach ($item in (Get-ChildItem -LiteralPath $outputRoot -Filter '*.zip' -File | Sort-Object Name)) {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $item.FullName).Hash.ToLowerInvariant()
    $sidecarPath = $item.FullName + '.sha256'
    if (-not (Test-Path -LiteralPath $sidecarPath)) {
        throw "Release artifact has no .sha256 sidecar: $($item.Name)"
    }
    $sidecarItem = Get-Item -LiteralPath $sidecarPath
    $sidecarText = [IO.File]::ReadAllText($sidecarPath)
    $recorded = ($sidecarText.Trim() -split '\s+')[0].ToLowerInvariant()
    if ($recorded -ne $hash) {
        throw "Sidecar disagrees with artifact for $($item.Name): sidecar $recorded, measured $hash"
    }
    $artifacts += [ordered]@{
        name = $item.Name
        bytes = $item.Length
        sha256 = $hash
        sidecar = [ordered]@{
            name = $sidecarItem.Name
            bytes = $sidecarItem.Length
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $sidecarPath).Hash.ToLowerInvariant()
        }
    }
}
if ($artifacts.Count -lt 2) { throw 'Release build produced fewer than the two composite archives' }
$manifest = [ordered]@{
    schema = 'sovereign.release-build.v2'
    version = $version
    source_commit = $resolvedCommit
    archive_basis = 'git archive of the named source commit; ignored host state excluded'
    hash_authority_note = 'Sole authority for release-artifact and sidecar hashes. RELEASE-MANIFEST.json is tracked, therefore archived, therefore cannot carry these hashes (CLOSEOUT-01 A-1). This file is untracked and excludes itself by construction.'
    artifact_count = $artifacts.Count
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
