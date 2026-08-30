[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Archive,

    # Where to restore to. Defaults to the workspace state root.
    [string] $StateRoot,

    # Restore over a state root that already holds files. Off by default: overwriting live
    # state with an older capture is the most destructive thing this tooling can do, and it
    # must be asked for rather than defaulted into.
    [switch] $Force
)

# EPC-01 P4-5 - restore operator state from a verified archive.
#
# The archive is checked against its SHA-256 sidecar BEFORE anything is written. A restore
# that trusts the file it was handed is not a restore, it is a hope.
#
# The existing state root is never deleted. If it holds files and -Force is given, it is MOVED
# aside first, so a mistaken restore is recoverable by moving it back.

$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop

$archiveFull = [IO.Path]::GetFullPath($Archive)
if (-not (Test-Path -LiteralPath $archiveFull -PathType Leaf)) {
    throw "Backup archive not found: $archiveFull"
}

$sidecar = "$archiveFull.sha256"
if (-not (Test-Path -LiteralPath $sidecar -PathType Leaf)) {
    throw "Backup sidecar not found: $sidecar - refusing to restore an unverifiable archive"
}
$expected = ((Get-Content -Raw -LiteralPath $sidecar).Trim() -split '\s+')[0].ToLowerInvariant()
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $archiveFull).Hash.ToLowerInvariant()
if ($expected -ne $actual) {
    throw "Backup archive SHA-256 mismatch - refusing to restore. expected $expected, measured $actual"
}
Write-Output "restore: archive verified against its sidecar ($actual)"

if (-not $StateRoot) {
    $StateRoot = $env:SOVEREIGN_WORKSPACE_STATE
    if (-not $StateRoot) {
        $localAppData = $env:LOCALAPPDATA
        if (-not $localAppData) { $localAppData = Join-Path $env:USERPROFILE 'AppData\Local' }
        $StateRoot = Join-Path $localAppData 'SovereignWorkspace'
    }
}
$stateRootFull = [IO.Path]::GetFullPath($StateRoot).TrimEnd('\')
if ($stateRootFull -eq [IO.Path]::GetPathRoot($stateRootFull)) {
    throw "Refusing a filesystem-root state root: $stateRootFull"
}

$displaced = $null
if (Test-Path -LiteralPath $stateRootFull -PathType Container) {
    $existing = @(Get-ChildItem -LiteralPath $stateRootFull -Force -Recurse -File)
    if ($existing.Count -gt 0) {
        if (-not $Force) {
            throw "State root $stateRootFull already holds $($existing.Count) file(s). Re-run with -Force to restore over it; the existing state will be moved aside, not deleted."
        }
        $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
        $displaced = "${stateRootFull}.displaced-${stamp}"
        Write-Output "restore: moving existing state aside to $displaced"
        Move-Item -LiteralPath $stateRootFull -Destination $displaced
    }
}

New-Item -ItemType Directory -Path $stateRootFull -Force | Out-Null
Write-Output "restore: extracting to $stateRootFull"
Expand-Archive -LiteralPath $archiveFull -DestinationPath $stateRootFull -Force

$inventoryPath = Join-Path $stateRootFull 'STATE-BACKUP-INVENTORY.json'
$restored = @(Get-ChildItem -LiteralPath $stateRootFull -Force -Recurse -File)
if (Test-Path -LiteralPath $inventoryPath -PathType Leaf) {
    $inventory = Get-Content -Raw -LiteralPath $inventoryPath | ConvertFrom-Json
    $expectedCount = [int]$inventory.file_count
    # The inventory itself was added by the backup and is not one of the captured files.
    $actualCount = $restored.Count - 1
    if ($actualCount -ne $expectedCount) {
        throw "Restore incomplete: inventory declares $expectedCount file(s), $actualCount extracted"
    }
    Write-Output "restore: inventory verified - $expectedCount file(s), captured $($inventory.created_utc)"
    Remove-Item -LiteralPath $inventoryPath -Force
}
else {
    Write-Output 'restore: WARNING - archive carries no inventory; extracted contents were not cross-checked'
}

Write-Output ''
Write-Output 'restore: COMPLETE'
Write-Output "  state root  $stateRootFull"
if ($displaced) {
    Write-Output "  previous state moved to $displaced   (nothing was deleted)"
}
