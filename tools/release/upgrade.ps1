[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Dest,

    [string] $Artifact,

    # Where the outgoing installation is moved to rather than deleted. Defaults to a sibling
    # of $Dest stamped with the version being replaced. An upgrade that destroys the only copy
    # of the previous install has no rollback, so this is not optional behaviour.
    [string] $BackupTo,

    # Skip the pre-upgrade state backup. Off by default and deliberately awkward to reach.
    [switch] $NoStateBackup
)

# EPC-01 P1-1 - side-by-side upgrade with state carried forward.
#
# There was no upgrade path at all. `install.ps1` refuses a non-empty destination by design,
# and uninstall refused to run on any installation that had been used (P0-5), so there was no
# supported route from one version to the next: the only option was to delete the install
# directory by hand and lose whatever was inside it.
#
# Both halves of that are now tractable because P4-4 moved runtime state out of the install
# root. State survives the install being replaced, because it is no longer inside it.
#
# The model is REPLACE-AND-KEEP, not in-place mutation:
#
#   1. verify the new artifact against its sidecar BEFORE touching anything
#   2. back up the state root (unless refused explicitly)
#   3. move the outgoing installation aside - never delete it
#   4. install the new version into the now-empty destination
#   5. verify the new installation against its own manifest
#   6. leave BOTH the previous installation and the state backup in place, and say where
#
# Nothing is deleted by this script. Rollback is moving the previous installation back.

$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop

$here = $PSScriptRoot
$destRoot = [IO.Path]::GetFullPath($Dest).TrimEnd('\')
if ($destRoot -eq [IO.Path]::GetPathRoot($destRoot)) {
    throw "Refusing filesystem-root destination: $destRoot"
}
if (-not (Test-Path -LiteralPath $destRoot -PathType Container)) {
    throw "Nothing to upgrade: $destRoot does not exist. Use install.ps1 for a first install."
}

$manifestPath = Join-Path $destRoot 'install-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Not an installation produced by install.ps1: $manifestPath is missing"
}

$outgoingVersion = 'unknown'
$versionPath = Join-Path $destRoot 'VERSION.json'
if (Test-Path -LiteralPath $versionPath -PathType Leaf) {
    $outgoingVersion = [string](Get-Content -Raw -LiteralPath $versionPath | ConvertFrom-Json).version
}
Write-Output "upgrade: outgoing installation is version $outgoingVersion at $destRoot"

# --- 1. verify the incoming artifact BEFORE anything is moved -------------------------------
if (-not $Artifact) {
    $workspaceRoot = [IO.Path]::GetFullPath((Join-Path $here '..\..'))
    $incoming = (Get-Content -Raw -LiteralPath (Join-Path $workspaceRoot 'VERSION.json') | ConvertFrom-Json).version
    $Artifact = Join-Path $workspaceRoot "release-artifacts\sovereign-workspace-$incoming-install.zip"
}
$artifactPath = [IO.Path]::GetFullPath($Artifact)
if (-not (Test-Path -LiteralPath $artifactPath -PathType Leaf)) {
    throw "Install artifact not found: $artifactPath"
}
$sidecarPath = $artifactPath + '.sha256'
if (-not (Test-Path -LiteralPath $sidecarPath -PathType Leaf)) {
    throw "Install artifact sidecar not found: $sidecarPath"
}
$expectedHash = ((Get-Content -Raw -LiteralPath $sidecarPath).Trim() -split '\s+')[0].ToLowerInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $artifactPath).Hash.ToLowerInvariant()
if ($expectedHash -ne $actualHash) { throw 'Install artifact SHA-256 mismatch - refusing to upgrade' }
Write-Output 'upgrade: incoming artifact verified against its sidecar'

# --- 2. back up the state root ---------------------------------------------------------------
$stateRoot = $env:SOVEREIGN_WORKSPACE_STATE
if (-not $stateRoot) {
    $localAppData = $env:LOCALAPPDATA
    if (-not $localAppData) { $localAppData = Join-Path $env:USERPROFILE 'AppData\Local' }
    $stateRoot = Join-Path $localAppData 'SovereignWorkspace'
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
if ($NoStateBackup) {
    Write-Output "upgrade: state backup SKIPPED at explicit operator request"
}
elseif (Test-Path -LiteralPath $stateRoot) {
    $stateBackup = "${stateRoot}.pre-upgrade-${stamp}"
    Write-Output "upgrade: backing up operator state to $stateBackup"
    Copy-Item -LiteralPath $stateRoot -Destination $stateBackup -Recurse -Force
    Write-Output 'upgrade: state backup complete'
}
else {
    Write-Output "upgrade: no operator state at $stateRoot - nothing to back up"
}

# --- 3. move the outgoing installation aside - never delete it ------------------------------
if (-not $BackupTo) { $BackupTo = "${destRoot}.previous-${outgoingVersion}-${stamp}" }
$backupRoot = [IO.Path]::GetFullPath($BackupTo).TrimEnd('\')
if (Test-Path -LiteralPath $backupRoot) {
    throw "Refusing to overwrite an existing backup location: $backupRoot"
}
Write-Output "upgrade: moving the outgoing installation to $backupRoot"
Move-Item -LiteralPath $destRoot -Destination $backupRoot
if (Test-Path -LiteralPath $destRoot) {
    throw "Destination is still present after the move: $destRoot"
}

# --- 4. install the new version ---------------------------------------------------------------
Write-Output 'upgrade: installing the new version'
& (Join-Path $here 'install.ps1') -Dest $destRoot -Artifact $artifactPath
if ($LASTEXITCODE -ne 0) {
    throw "Install failed during upgrade. The previous installation is intact at $backupRoot - move it back to $destRoot to roll back."
}

# --- 5. verify the new installation ----------------------------------------------------------
Write-Output 'upgrade: verifying the new installation'
& (Join-Path $here 'verify_install.ps1') -Dest $destRoot
if ($LASTEXITCODE -ne 0) {
    throw "Verification failed after upgrade. The previous installation is intact at $backupRoot."
}

# --- 6. report, and leave both copies in place ------------------------------------------------
$newVersion = 'unknown'
if (Test-Path -LiteralPath (Join-Path $destRoot 'VERSION.json') -PathType Leaf) {
    $newVersion = [string](Get-Content -Raw -LiteralPath (Join-Path $destRoot 'VERSION.json') | ConvertFrom-Json).version
}
Write-Output ''
Write-Output "upgrade: COMPLETE  $outgoingVersion -> $newVersion"
Write-Output "  installed at        $destRoot"
Write-Output "  previous version at $backupRoot   (nothing was deleted; move it back to roll back)"
if (-not $NoStateBackup -and (Test-Path -LiteralPath "${stateRoot}.pre-upgrade-${stamp}")) {
    Write-Output "  state backup at     $stateRoot.pre-upgrade-$stamp"
}
Write-Output "  operator state at   $stateRoot   (carried forward, not copied into the install)"
Write-Output ''
Write-Output '  Nothing was removed by this upgrade. Delete the previous installation and the'
Write-Output '  state backup yourself once you are satisfied the new version works.'
