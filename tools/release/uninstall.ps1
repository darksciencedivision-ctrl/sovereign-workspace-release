[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Dest,

    # EPC-01 P0-5. Uninstall used to compare the WHOLE install tree against the manifest and
    # refuse if anything had been added - and the product's own runtime state was an addition,
    # so uninstall worked only on an installation that had never been used. Relaxing the check
    # would have been the wrong repair: line ~71's recursive delete would then have taken all
    # operator data with no export and no prompt. Both branches were wrong.
    #
    # P4-4 moved runtime state out of the install root, so the strict path-set check can stay
    # exactly as strict as it was. What remains is the operator's decision about the state
    # that now lives elsewhere, and it is asked explicitly rather than assumed:
    #
    #   -KeepData   (default) the state root is left untouched
    #   -PurgeData            the state root is removed as well, after being named
    #
    # Neither branch deletes anything the manifest does not record inside the install root.
    [switch] $PurgeData,
    [switch] $KeepData
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'path_guard.ps1')
if ($PurgeData -and $KeepData) { throw 'Specify at most one of -PurgeData and -KeepData' }
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

# --- EPC-01 P0-5: the operator's state, which no longer lives in the install root -----------
#
# P4-4 moved runtime state to %LOCALAPPDATA%\SovereignWorkspace\<module>. Removing the install
# therefore does NOT remove the operator's work, which is the correct default - an uninstall
# that silently destroys data the operator spent months producing is a worse failure than one
# that refuses to run.
#
# The state root is NAMED either way. An operator who did not know it existed cannot be
# expected to clean it up later, and an operator who asked for it gone must be able to see
# exactly what went.
$stateRoot = $env:SOVEREIGN_WORKSPACE_STATE
if (-not $stateRoot) {
    $localAppData = $env:LOCALAPPDATA
    if (-not $localAppData) { $localAppData = Join-Path $env:USERPROFILE 'AppData\Local' }
    $stateRoot = Join-Path $localAppData 'SovereignWorkspace'
}

if (-not (Test-Path -LiteralPath $stateRoot)) {
    Write-Output "uninstall: no operator state found at $stateRoot"
}
elseif ($PurgeData) {
    # F-040: $stateRoot comes straight from the environment, so a mis-set SOVEREIGN_WORKSPACE_STATE
    # (a drive root, %USERPROFILE%, a junction into operator data) would otherwise be recursively
    # deleted verbatim. Validate canonically first; the guard throws on anything unsafe and returns
    # the canonical path to remove.
    $canonState = Assert-PurgeableStateRoot -StateRoot $stateRoot -InstallRoot $destRoot
    $doomed = @(Get-ChildItem -LiteralPath $canonState -Force -ErrorAction SilentlyContinue)
    Write-Output "uninstall: PURGING operator state at $canonState ($($doomed.Count) entries)"
    foreach ($entry in $doomed) { Write-Output "  removing $($entry.Name)" }
    Remove-Item -LiteralPath $canonState -Recurse -Force
    Write-Output 'uninstall: operator state removed'
}
else {
    Write-Output "uninstall: operator state KEPT at $stateRoot"
    Write-Output '  It was not touched. Re-run with -PurgeData to remove it, or delete it by hand.'
    Write-Output '  A later install of this product will find and reuse it.'
}
