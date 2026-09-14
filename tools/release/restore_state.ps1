[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Archive,

    # Where to restore to. Defaults to the workspace state root.
    [string] $StateRoot,

    # Restore over a state root that already holds files. Off by default: overwriting live
    # state with an older capture is the most destructive thing this tooling can do, and it
    # must be asked for rather than defaulted into.
    [switch] $Force,

    # Accept an archive that carries no v2 inventory. Such an archive CANNOT be verified: its
    # completeness and its contents are unchecked, and the result is labelled NOT VERIFIED.
    [switch] $AllowUnverifiedLegacyArchive,

    # F-043: restore an archive captured under a DIFFERENT product version. Off by default:
    # a state layout produced by another version may not be understood by the running product
    # (directive 4.2 requires version validation). Off => a mismatch is refused before anything
    # is displaced; on => the mismatch is stated and the restore proceeds anyway.
    [switch] $AllowVersionMismatch
)

# SWS-CORRECTIVE-01 workstream 1.2 - restore is staged, verified, then placed.
#
# THE DEFECT THIS REPLACES. The previous script extracted straight into the destination and
# only then compared a file COUNT against the inventory, so a short or tampered archive had
# already been written over the destination by the time it was detected. It also treated an
# archive with no inventory as a successful restore with a warning, and its count arithmetic
# assumed the inventory was one of the extracted files.
#
# THE ORDER NOW:
#
#   1. verify the archive against its .sha256 sidecar - integrity, not authenticity
#   2. read the inventory from inside the archive
#   3. validate every entry path: no escape, no absolute path, no duplicate, no case collision
#   4. check the entry SET against the inventory - missing, extra and duplicated all fail
#   5. extract to a STAGING directory beside the state root
#   6. re-hash every extracted file against the inventory
#   7. only now displace the existing state, and move the staged tree into place
#   8. if final placement fails, put the displaced state back and say so
#
# Nothing about the destination changes before step 7.

$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop

$INVENTORY_NAME = 'STATE-BACKUP-INVENTORY.json'
$STATE_PREFIX = 'state/'

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
Write-Output "restore: archive integrity verified against its sidecar ($actual)"
Write-Output '         (the sidecar proves the bytes are intact; it authenticates no publisher)'

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
$stateParent = Split-Path -Parent $stateRootFull
if (-not $stateParent) { throw "State root has no parent directory: $stateRootFull" }
if (-not (Test-Path -LiteralPath $stateParent -PathType Container)) {
    New-Item -ItemType Directory -Path $stateParent -Force | Out-Null
}

# F-043: take the shared state-transaction lock before any staging or displacement, so a
# concurrent backup/restore/upgrade cannot recreate the state root between displacement and
# placement (the "RECOVERY DID NOT COMPLETE" race). Held to process exit; every path below ends
# in `exit`, which frees the exclusive handle. The outer finally also releases it explicitly.
. (Join-Path $PSScriptRoot 'state_lock.ps1')
$txLock = Enter-StateTransactionLock -StateParent $stateParent -Operation 'restore'

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$staging = Join-Path $stateParent ('.sovereign-restore-staging-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
# R03: whether the finally block may delete the staged, verified restore. It is cleared the moment
# staging is either consumed (moved into place) or preserved for the operator to recover from, so a
# placement/recovery failure can never delete the exact copy the operator was told to recover from.
$cleanupStaging = $true

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$legacy = $false
$inventory = $null
$problems = @()

$zip = [IO.Compression.ZipFile]::OpenRead($archiveFull)
try {
    $names = @($zip.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })

    # --- path validation, before anything is written ---------------------------------------
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($name in $names) {
        if ($name -match '^(?:[A-Za-z]:|/|\\)') { $problems += "absolute archive path: $name" }
        $segments = $name.Split('/')
        if ($segments -contains '..') { $problems += "archive path escapes the state root: $name" }
        if (-not $seen.Add($name)) {
            $problems += "duplicate or case-colliding archive entry: $name"
        }
    }

    $inventoryEntry = $zip.GetEntry($INVENTORY_NAME)
    if ($null -eq $inventoryEntry) {
        if (-not $AllowUnverifiedLegacyArchive) {
            Write-Output ''
            Write-Output 'restore: REFUSED - this archive carries no inventory.'
            Write-Output '  Its completeness and its contents cannot be checked, so a restore from it'
            Write-Output '  cannot be reported as verified. Re-run with -AllowUnverifiedLegacyArchive'
            Write-Output '  to restore it anyway; the result will be labelled NOT VERIFIED.'
            exit 3
        }
        $legacy = $true
    }
    else {
        $reader = New-Object IO.StreamReader($inventoryEntry.Open())
        try { $inventory = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
        if ($inventory.schema -ne 'sovereign.state-backup.v2') {
            if (-not $AllowUnverifiedLegacyArchive) {
                Write-Output ''
                Write-Output "restore: REFUSED - unsupported inventory schema '$($inventory.schema)'."
                Write-Output '  This build verifies sovereign.state-backup.v2. Re-run with'
                Write-Output '  -AllowUnverifiedLegacyArchive to restore without verification.'
                exit 3
            }
            $legacy = $true
            $inventory = $null
        }
    }

    # --- entry-set check against the inventory ---------------------------------------------
    if (-not $legacy) {
        $declared = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        foreach ($e in $inventory.entries) {
            $suffix = if ($e.kind -eq 'directory') { '/' } else { '' }
            [void]$declared.Add($STATE_PREFIX + $e.path + $suffix)
        }
        foreach ($name in $names) {
            if ($name -eq $INVENTORY_NAME) { continue }
            if (-not $declared.Contains($name)) { $problems += "archive holds an entry the inventory does not declare: $name" }
        }
        foreach ($want in $declared) {
            if ($names -notcontains $want) { $problems += "the inventory declares an entry the archive does not hold: $want" }
        }
    }

    if ($problems.Count -gt 0) {
        Write-Output ''
        Write-Output "restore: REFUSED - the archive does not agree with its inventory ($($problems.Count) problem(s)):"
        $problems | Select-Object -First 20 | ForEach-Object { Write-Output "    $_" }
        Write-Output ''
        Write-Output "  Nothing was written. $stateRootFull is untouched."
        exit 3
    }

    # --- extract to STAGING ----------------------------------------------------------------
    New-Item -ItemType Directory -Path $staging -Force | Out-Null
    $stagingPrefix = [IO.Path]::GetFullPath($staging).TrimEnd('\') + '\'
    foreach ($e in $zip.Entries) {
        $name = $e.FullName.Replace('\', '/')
        if ($name -eq $INVENTORY_NAME) { continue }
        $relative = if ($legacy) { $name } else { $name.Substring($STATE_PREFIX.Length) }
        if (-not $relative) { continue }
        $target = [IO.Path]::GetFullPath((Join-Path $staging ($relative -replace '/', '\')))
        if (-not $target.StartsWith($stagingPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Archive path escapes the staging root: $name"
        }
        if ($name.EndsWith('/')) {
            New-Item -ItemType Directory -Path $target -Force | Out-Null
            continue
        }
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        [IO.Compression.ZipFileExtensions]::ExtractToFile($e, $target, $true)
    }
}
finally { $zip.Dispose() }

try {
    # --- verify the staged tree ------------------------------------------------------------
    if (-not $legacy) {
        $verifyProblems = @()
        foreach ($e in $inventory.entries) {
            $target = Join-Path $staging ($e.path -replace '/', '\')
            if ($e.kind -eq 'directory') {
                if (-not (Test-Path -LiteralPath $target -PathType Container)) {
                    $verifyProblems += "directory not restored: $($e.path)"
                }
                continue
            }
            if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
                $verifyProblems += "file not restored: $($e.path)"
                continue
            }
            $item = Get-Item -LiteralPath $target -Force
            if ([int64]$item.Length -ne [int64]$e.length) {
                $verifyProblems += ("length differs for {0}: inventory {1}, restored {2}" -f $e.path, $e.length, $item.Length)
                continue
            }
            $digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLowerInvariant()
            if ($digest -ne [string]$e.sha256) {
                $verifyProblems += ("content differs for {0}: inventory {1}, restored {2}" -f $e.path, $e.sha256, $digest)
            }
        }
        if ($verifyProblems.Count -gt 0) {
            Write-Output ''
            Write-Output "restore: REFUSED - the extracted contents do not match the inventory ($($verifyProblems.Count) problem(s)):"
            $verifyProblems | Select-Object -First 20 | ForEach-Object { Write-Output "    $_" }
            Write-Output ''
            Write-Output "  Nothing was placed. $stateRootFull is untouched."
            exit 3
        }
        Write-Output ("restore: verified {0} file(s) and {1} director(y/ies) against the inventory captured {2}" -f `
                      $inventory.file_count, $inventory.directory_count, $inventory.created_utc)
        if ($inventory.snapshot_method -notlike 'offline-quiesced*') {
            Write-Output "restore: NOTE - this archive was captured with method '$($inventory.snapshot_method)'."
            Write-Output '        It is not a consistent snapshot; a database inside it may need repair.'
        }
    }
    else {
        Write-Output 'restore: this archive carries no usable inventory. Its contents are NOT VERIFIED.'
    }

    # --- F-043: product-version compatibility, BEFORE anything is displaced ----------------
    # The inventory records the product version that produced the capture. Restoring a state
    # layout from a different version into the running product may hand it a schema it does not
    # understand; the directive requires this be validated rather than assumed. Legacy archives
    # carry no version and are already labelled NOT VERIFIED, so this applies to v2 only.
    if (-not $legacy) {
        $currentVersion = 'unknown'
        $versionFile = Join-Path $PSScriptRoot '..\..\VERSION.json'
        if (Test-Path -LiteralPath $versionFile -PathType Leaf) {
            try { $currentVersion = [string](Get-Content -Raw -LiteralPath $versionFile | ConvertFrom-Json).version } catch { }
        }
        $archiveVersion = [string]$inventory.product_version
        if (-not $archiveVersion) { $archiveVersion = 'unknown' }
        if ($archiveVersion -ne $currentVersion) {
            if (-not $AllowVersionMismatch) {
                Write-Output ''
                Write-Output 'restore: REFUSED - product-version mismatch.'
                Write-Output "  archive captured under : $archiveVersion"
                Write-Output "  product installed here : $currentVersion"
                Write-Output '  The state layout may not be understood by this version. Re-run with'
                Write-Output '  -AllowVersionMismatch to restore anyway (after taking your own backup),'
                Write-Output "  or install matching product version $archiveVersion first."
                Write-Output "  Nothing was displaced. $stateRootFull is untouched."
                exit 3
            }
            Write-Output "restore: WARNING - restoring a $archiveVersion capture into product $currentVersion (version mismatch accepted)."
        }
    }

    # --- displace the existing state, then place -------------------------------------------
    $displaced = $null
    if (Test-Path -LiteralPath $stateRootFull -PathType Container) {
        $existing = @(Get-ChildItem -LiteralPath $stateRootFull -Force -Recurse -File)
        if ($existing.Count -gt 0) {
            if (-not $Force) {
                Write-Output ''
                Write-Output "restore: REFUSED - $stateRootFull already holds $($existing.Count) file(s)."
                Write-Output '  Re-run with -Force to restore over it; the existing state will be moved'
                Write-Output '  aside, not deleted. Nothing has been written.'
                exit 3
            }
            $displaced = "${stateRootFull}.displaced-${stamp}"
            Write-Output "restore: moving existing state aside to $displaced"
            Move-Item -LiteralPath $stateRootFull -Destination $displaced
        }
        else {
            Remove-Item -LiteralPath $stateRootFull -Force
        }
    }

    try {
        Move-Item -LiteralPath $staging -Destination $stateRootFull
        $cleanupStaging = $false  # placed (moved); there is nothing left to clean
    }
    catch {
        # R03: a placement OR recovery failure must PRESERVE the verified staged restore so the
        # operator can recover from it by hand. Clear the cleanup flag for every failure exit from
        # this block, and name only the recovery paths that STILL EXIST.
        $cleanupStaging = $false
        $placementError = $_.Exception.Message
        Write-Output ''
        Write-Output "restore: FAILED to place the verified state at $stateRootFull - $placementError"
        if ($displaced) {
            try {
                Move-Item -LiteralPath $displaced -Destination $stateRootFull
                Write-Output "restore: the previous state has been put back at $stateRootFull"
            }
            catch {
                Write-Output '  RECOVERY DID NOT COMPLETE. Recover by hand from these exact locations:'
                if (Test-Path -LiteralPath $displaced) { Write-Output "    previous state   $displaced" }
                if (Test-Path -LiteralPath $staging) { Write-Output "    verified restore $staging" }
                exit 5
            }
        }
        # Rollback succeeded, or there was nothing to roll back: the verified restore is retained.
        if (Test-Path -LiteralPath $staging) {
            Write-Output "  The verified restore is staged at $staging and was not discarded."
        }
        exit 5
    }

    Write-Output ''
    if ($legacy) {
        Write-Output 'restore: COMPLETE (NOT VERIFIED - the archive carried no inventory)'
    }
    else {
        Write-Output 'restore: COMPLETE (verified against the archive inventory)'
    }
    Write-Output "  state root  $stateRootFull"
    if ($displaced) {
        Write-Output "  previous state moved to $displaced   (nothing was deleted)"
    }
    exit 0
}
finally {
    if ($cleanupStaging -and $staging -and (Test-Path -LiteralPath $staging)) {
        $resolved = [IO.Path]::GetFullPath($staging)
        if ((Split-Path -Leaf $resolved).StartsWith('.sovereign-restore-staging-')) {
            Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    Exit-StateTransactionLock $txLock
}
