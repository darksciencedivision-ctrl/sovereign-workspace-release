[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Dest
)

$ErrorActionPreference = 'Stop'
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
    if ($entry.scope -eq 'install') {
        [void]$expectedInstall.Add([string]$entry.path)
        continue
    }
    $targetRoot = [string]$manifest.shortcut_target_root
    if (-not $targetRoot) {
        if ($entry.kind -ne 'file' -or -not ([string]$entry.path).EndsWith('Sovereign Workspace.lnk', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Unsafe external manifest entry: $($entry.path)"
        }
    }
    else {
        $targetPrefix = [IO.Path]::GetFullPath($targetRoot).TrimEnd('\') + '\'
        $external = [IO.Path]::GetFullPath([string]$entry.path)
        if ($external -ne $targetPrefix.TrimEnd('\') -and -not $external.StartsWith($targetPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "External manifest entry escapes shortcut target: $external"
        }
    }
}
$actualInstall = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
Get-ChildItem -LiteralPath $destRoot -Force -Recurse | ForEach-Object {
    [void]$actualInstall.Add($_.FullName.Substring($destPrefix.Length).Replace('\', '/'))
}
if (-not $actualInstall.SetEquals($expectedInstall)) {
    $missing = @($expectedInstall | Where-Object { -not $actualInstall.Contains($_) })
    $extra = @($actualInstall | Where-Object { -not $expectedInstall.Contains($_) })
    throw "Refusing uninstall because exact installed path set changed; missing=$($missing -join ','); extra=$($extra -join ',')"
}

$externalFiles = @($manifest.paths | Where-Object { $_.scope -eq 'shortcut' -and $_.kind -eq 'file' } | Sort-Object { ([string]$_.path).Length } -Descending)
$externalDirs = @($manifest.paths | Where-Object { $_.scope -eq 'shortcut' -and $_.kind -eq 'directory' } | Sort-Object { ([string]$_.path).Length } -Descending)
foreach ($entry in $externalFiles) {
    if (Test-Path -LiteralPath ([string]$entry.path) -PathType Leaf) {
        Remove-Item -LiteralPath ([string]$entry.path) -Force
    }
}
foreach ($entry in $externalDirs) {
    $path = [string]$entry.path
    if (Test-Path -LiteralPath $path -PathType Container) {
        if (Get-ChildItem -LiteralPath $path -Force | Select-Object -First 1) {
            throw "Recorded shortcut directory is not empty after file removal: $path"
        }
        Remove-Item -LiteralPath $path -Force
    }
}

if ([bool]$manifest.install_root_created) {
    $resolved = [IO.Path]::GetFullPath($destRoot)
    if ($resolved -ne $destRoot -or -not $resolved.StartsWith([IO.Path]::GetPathRoot($resolved), [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Destination resolution changed before recursive removal'
    }
    Remove-Item -LiteralPath $destRoot -Recurse -Force
}
else {
    Get-ChildItem -LiteralPath $destRoot -Force | Remove-Item -Recurse -Force
}

$remaining = @()
foreach ($entry in $manifest.paths) {
    $path = if ($entry.scope -eq 'install') { Join-Path $destRoot ([string]$entry.path) } else { [string]$entry.path }
    if (Test-Path -LiteralPath $path) { $remaining += $path }
}
if ($remaining) { throw "Uninstall manifest was not fully consumed: $($remaining -join ',')" }
Write-Output (@{ removed_recorded_paths = @($manifest.paths).Count; remaining_recorded_paths = 0; claim = 'removed exactly the recorded paths' } | ConvertTo-Json -Compress)
