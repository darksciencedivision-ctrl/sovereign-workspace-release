[CmdletBinding()]
param(
    # Where to write the backup archive. Defaults to a timestamped file beside the state root.
    [string] $Out,

    # The state root to back up. Defaults to the workspace state root.
    [string] $StateRoot,

    # Capture state that is being written while the capture runs. The result is NOT a
    # consistent snapshot and is labelled as such in the inventory and on stdout.
    [switch] $AllowNonQuiescent,

    # Capture even though some required state could not be read. Off by default: a backup that
    # silently omits state is the defect this contract exists to close.
    [switch] $AllowIncomplete
)

# SWS-CORRECTIVE-01 workstream 1.2 - the snapshot contract.
#
# THE DEFECT THIS REPLACES (L2). The previous script counted entries with `-Force` and then
# archived with `Compress-Archive -Path <root>\*`, whose wildcard does not match Windows-hidden
# entries. Measured on this host:
#
#     FIXTURE files(-Force)=2
#     backup: capturing 2 file(s) from ...\state
#     backup: COMPLETE
#       ENTRY STATE-BACKUP-INVENTORY.json
#       ENTRY visible.txt
#     RESTORE_ERROR: Restore incomplete: inventory declares 2 file(s), 1 extracted
#
# It reported COMPLETE having lost a file. It also used the operator's LIVE state root as
# scratch space for its own inventory, recorded a file count and nothing else, and published
# the archive under its final name before anything had verified its contents.
#
# THE CONTRACT NOW - offline, verified, and stated rather than implied.
#
#   QUIESCENCE. This is an OFFLINE snapshot. Every relevant product writer must be stopped.
#   The script proves it rather than asking: each file is opened with FileShare.Read, which
#   fails while another process holds it for writing, and THOSE HANDLES ARE HELD through hash
#   and zip. Bytes are copied from the held streams, not by re-opening the path. A writer
#   that arrives after the probe therefore cannot mutate captured bytes, and a file created
#   after acquire is refused as "state changed during capture". -AllowNonQuiescent captures
#   anyway and labels the result honestly; it does not make the result consistent. Online
#   backup would need database-aware snapshots for every store, which this version
#   deliberately does not claim to provide.
#
#   COMPLETENESS. Enumeration is `-Force`, so hidden and system entries are included, and
#   directories are recorded as well as files so a required-but-empty directory survives.
#   Reparse points are refused rather than silently followed or dropped.
#
#   LAYOUT. Operator state is stored under a `state/` prefix inside the archive, and the
#   inventory sits at the archive root. Nothing the operator can name collides with the
#   inventory, so a user file called STATE-BACKUP-INVENTORY.json round-trips like any other.
#
#   INVENTORY. Normalised relative path, byte length, SHA-256, attributes and entry kind for
#   every item, plus schema, product version, captured modules and the snapshot method. A file
#   count is not an inventory.
#
#   ATOMICITY. The archive is built under a `.partial` name in a staging directory, reopened
#   and verified entry-by-entry against the inventory, and only then moved to the final name.
#   A capture that does not verify never occupies the successful-backup name.
#
#   INTEGRITY IS NOT AUTHENTICITY. The .sha256 sidecar proves the archive has not been
#   corrupted or truncated. It does NOT prove who produced it: anyone who can rewrite the
#   archive can rewrite the sidecar. This tooling ships no signing infrastructure and does not
#   claim any.
#
# This script READS the state root and writes elsewhere. It never modifies state.

$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop

$INVENTORY_NAME = 'STATE-BACKUP-INVENTORY.json'
$STATE_PREFIX = 'state/'
$utf8NoBom = [Text.UTF8Encoding]::new($false)

if (-not $StateRoot) {
    $StateRoot = $env:SOVEREIGN_WORKSPACE_STATE
    if (-not $StateRoot) {
        $localAppData = $env:LOCALAPPDATA
        if (-not $localAppData) { $localAppData = Join-Path $env:USERPROFILE 'AppData\Local' }
        $StateRoot = Join-Path $localAppData 'SovereignWorkspace'
    }
}
if ($StateRoot -match '^[A-Za-z]:\\?$') {
    throw "Refusing a filesystem-root state root: $StateRoot"
}
$stateRootFull = [IO.Path]::GetFullPath($StateRoot).TrimEnd('\')
$volumeRoot = [IO.Path]::GetPathRoot($stateRootFull)
if ($stateRootFull.TrimEnd('\').Equals($volumeRoot.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing a filesystem-root state root: $stateRootFull"
}
if (-not (Test-Path -LiteralPath $stateRootFull -PathType Container)) {
    throw "No state to back up: $stateRootFull does not exist"
}
$statePrefixFs = $stateRootFull + '\'

if (-not $Out) {
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
    $Out = "${stateRootFull}.backup-${stamp}.zip"
}
$outFull = [IO.Path]::GetFullPath($Out)
# R08/F-046. The output (and therefore the staging directory beside it) must be OUTSIDE the state
# root. An -Out inside the state root made the backup capture its own staging directory as operator
# state and wrote the archive + sidecars into the supposedly read-only source, so repeated backups
# nested. Canonical containment catches direct descendants AND junction aliases.
. (Join-Path $PSScriptRoot 'path_guard.ps1')
if ((Test-CanonicalContained -Root $stateRootFull -Candidate $outFull) -or
    $outFull.TrimEnd('\').Equals($stateRootFull, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to write the backup inside the state root: $outFull"
}
if (Test-Path -LiteralPath $outFull) {
    throw "Refusing to overwrite an existing backup: $outFull"
}
$outDir = Split-Path -Parent $outFull
if (-not (Test-Path -LiteralPath $outDir -PathType Container)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
}
# The staging area is beside the OUTPUT, never inside the state root. The previous script used
# the operator's live state as scratch space; that is what this separation exists to prevent.
$staging = Join-Path $outDir ('.sovereign-backup-staging-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
New-Item -ItemType Directory -Path $staging -Force | Out-Null

function Get-RelativePath {
    param([string] $Full)
    return $Full.Substring($statePrefixFs.Length).Replace('\', '/')
}

function Get-StreamSha256 {
    param([IO.Stream] $Stream)
    $Stream.Position = 0
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return [BitConverter]::ToString($sha.ComputeHash($Stream)).Replace('-', '').ToLowerInvariant()
    }
    finally { $sha.Dispose() }
}

# F-043: take the shared state-transaction lock so a restore/upgrade cannot displace the state
# root while this backup is reading it. Held for the whole capture, released in the finally.
. (Join-Path $PSScriptRoot 'state_lock.ps1')
$stateParent = Split-Path -Parent $stateRootFull
$txLock = Enter-StateTransactionLock -StateParent $stateParent -Operation 'backup'

$held = New-Object System.Collections.Generic.List[object]
try {
    # --- enumerate ------------------------------------------------------------------------
    $all = @(Get-ChildItem -LiteralPath $stateRootFull -Force -Recurse -ErrorAction Stop)
    $files = @($all | Where-Object { -not $_.PSIsContainer })
    $dirs = @($all | Where-Object { $_.PSIsContainer })

    $refusals = @()
    foreach ($item in $all) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            $refusals += ("reparse point (junction or symbolic link) at '{0}' - this contract " +
                          "captures files and directories, and following or dropping a link " +
                          "would both be wrong" -f (Get-RelativePath $item.FullName))
        }
    }

    # --- quiescence: acquire FileShare.Read on every file and HOLD the handles ------------
    $busy = @()
    foreach ($file in $files) {
        try {
            $stream = [IO.File]::Open($file.FullName, [IO.FileMode]::Open,
                                      [IO.FileAccess]::Read, [IO.FileShare]::Read)
            $held.Add([pscustomobject]@{
                Rel        = (Get-RelativePath $file.FullName)
                FullName   = $file.FullName
                Stream     = $stream
                Attributes = [string]$file.Attributes
                LastWrite  = $file.LastWriteTime   # F-044: preserved on the zip entry so mtime round-trips
            })
        }
        catch {
            $busy += (Get-RelativePath $file.FullName)
        }
    }
    $method = 'offline-quiesced'
    if ($busy.Count -gt 0) {
        if (-not $AllowNonQuiescent) {
            Write-Output ''
            Write-Output "backup: REFUSED - the state root is not quiescent."
            Write-Output "  $($busy.Count) file(s) are held open by another process:"
            $busy | Select-Object -First 20 | ForEach-Object { Write-Output "    $_" }
            Write-Output ''
            Write-Output '  This is an OFFLINE snapshot contract. Stop the shell and every module'
            Write-Output '  (close the Sovereign Workspace window, or Ctrl+C the launcher) and re-run.'
            Write-Output '  -AllowNonQuiescent captures anyway and labels the archive as inconsistent;'
            Write-Output '  it does not make the capture consistent.'
            exit 3
        }
        $method = 'online-uncoordinated (NOT a consistent snapshot)'
        Write-Output "backup: WARNING - $($busy.Count) file(s) could not be opened denying writers."
        Write-Output '  The archive is labelled online-uncoordinated and is NOT a consistent snapshot.'
    }

    # Test-only barrier: after acquire, before re-enum/hash/zip. Production never sets this.
    $barrierDir = $env:SOVEREIGN_BACKUP_TEST_BARRIER_DIR
    if ($barrierDir) {
        New-Item -ItemType Directory -Path $barrierDir -Force | Out-Null
        [IO.File]::WriteAllText((Join-Path $barrierDir 'acquired'), 'acquired')
        $continue = Join-Path $barrierDir 'continue'
        $deadline = [datetime]::UtcNow.AddSeconds(30)
        while (-not (Test-Path -LiteralPath $continue)) {
            if ([datetime]::UtcNow -gt $deadline) { throw 'backup test barrier timed out waiting for continue' }
            Start-Sleep -Milliseconds 50
        }
    }

    # Re-enumerate. FileShare.Read cannot stop CREATE of a new WAL/log; a changed set is
    # not an offline snapshot of the tree that was acquired.
    $all2 = @(Get-ChildItem -LiteralPath $stateRootFull -Force -Recurse -ErrorAction Stop)
    $files2 = @($all2 | Where-Object { -not $_.PSIsContainer })
    $heldRels = @($held | ForEach-Object { $_.Rel })
    $known = @{}
    foreach ($rel in $heldRels) { $known[$rel] = $true }
    foreach ($b in $busy) { $known[$b] = $true }
    $newFiles = @()
    foreach ($file in $files2) {
        $rel = Get-RelativePath $file.FullName
        if (-not $known.ContainsKey($rel)) { $newFiles += $rel }
    }
    if ($newFiles.Count -gt 0) {
        Write-Output ''
        Write-Output 'backup: REFUSED - state changed during capture.'
        Write-Output '  file(s) appeared after quiescence handles were acquired:'
        $newFiles | Select-Object -First 20 | ForEach-Object { Write-Output "    $_" }
        Write-Output ''
        Write-Output '  Nothing was written. Stop writers and re-run.'
        exit 3
    }

    if ($refusals.Count -gt 0 -and -not $AllowIncomplete) {
        Write-Output ''
        Write-Output 'backup: REFUSED - the state root holds entries this contract cannot capture:'
        $refusals | ForEach-Object { Write-Output "    $_" }
        Write-Output ''
        Write-Output '  Nothing was written. Resolve them, or pass -AllowIncomplete to capture the'
        Write-Output '  rest and record the omission in the inventory.'
        exit 4
    }

    # --- inventory from held streams (never re-open the path) -----------------------------
    $entries = New-Object System.Collections.Generic.List[object]
    foreach ($dir in ($dirs | Sort-Object FullName)) {
        # [pscustomobject], not [ordered]: Windows PowerShell 5.1 raises "Argument types do
        # not match" when an OrderedDictionary is nested inside an [ordered] literal.
        $entries.Add([pscustomobject][ordered]@{
            kind       = 'directory'
            path       = (Get-RelativePath $dir.FullName)
            attributes = [string]$dir.Attributes
        })
    }
    $captured = 0
    $omitted = @()
    $heldByRel = @{}
    foreach ($h in $held) { $heldByRel[$h.Rel] = $h }
    foreach ($file in ($files | Sort-Object FullName)) {
        $rel = Get-RelativePath $file.FullName
        $h = $heldByRel[$rel]
        if (-not $h) {
            $omitted += $rel
            continue
        }
        try {
            $hash = Get-StreamSha256 $h.Stream
            $length = [int64]$h.Stream.Length
        }
        catch {
            $omitted += $rel
            continue
        }
        $entries.Add([pscustomobject][ordered]@{
            kind       = 'file'
            path       = $rel
            length     = $length
            sha256     = $hash
            attributes = $h.Attributes
        })
        $captured++
    }
    if ($omitted.Count -gt 0 -and -not $AllowIncomplete) {
        Write-Output ''
        Write-Output 'backup: REFUSED - could not read the following required state:'
        $omitted | ForEach-Object { Write-Output "    $_" }
        exit 4
    }

    $productVersion = 'unknown'
    $versionFile = Join-Path $PSScriptRoot '..\..\VERSION.json'
    if (Test-Path -LiteralPath $versionFile -PathType Leaf) {
        try { $productVersion = [string](Get-Content -Raw -LiteralPath $versionFile | ConvertFrom-Json).version }
        catch { }
    }

    # `@($genericList)` inside an [ordered] literal raises "Argument types do not match" in
    # Windows PowerShell 5.1. Materialise the arrays first and bind plain values.
    $entryArray = $entries.ToArray()
    $moduleNames = @(Get-ChildItem -LiteralPath $stateRootFull -Force -Directory |
                     ForEach-Object { $_.Name })
    $omittedArray = @($omitted)
    $refusedArray = @($refusals)
    $totalBytes = [int64]0
    foreach ($entry in $entries) {
        if ($entry.kind -eq 'file') { $totalBytes += [int64]$entry.length }
    }

    $inventory = [ordered]@{
        schema           = 'sovereign.state-backup.v2'
        created_utc      = (Get-Date).ToUniversalTime().ToString('o')
        state_root       = $stateRootFull
        product_version  = $productVersion
        snapshot_method  = $method
        archive_layout   = 'operator state under state/; this inventory at the archive root'
        integrity_note   = 'The .sha256 sidecar proves integrity, not authenticity. No publisher is authenticated.'
        file_count       = $captured
        directory_count  = $dirs.Count
        total_bytes      = $totalBytes
        modules          = $moduleNames
        omitted          = $omittedArray
        refused          = $refusedArray
        entries          = $entryArray
    }
    $inventoryJson = ($inventory | ConvertTo-Json -Depth 8) + "`n"
    $inventoryStaged = Join-Path $staging $INVENTORY_NAME
    [IO.File]::WriteAllText($inventoryStaged, $inventoryJson, $utf8NoBom)

    # --- build under a partial name -------------------------------------------------------
    Write-Output ("backup: capturing {0} file(s) and {1} director(y/ies) from {2}" -f `
                  $captured, $dirs.Count, $stateRootFull)
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $partial = Join-Path $staging 'archive.partial.zip'
    $zip = [IO.Compression.ZipFile]::Open($partial, [IO.Compression.ZipArchiveMode]::Create)
    try {
        [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $zip, $inventoryStaged, $INVENTORY_NAME,
            [IO.Compression.CompressionLevel]::Optimal)
         foreach ($entry in $entries) {
             if ($entry.kind -eq 'directory') {
                 # A directory entry keeps a required-but-empty directory alive across the trip.
                 [void]$zip.CreateEntry($STATE_PREFIX + $entry.path + '/')
                 continue
             }
             $h = $heldByRel[$entry.path]
             $zipEntry = $zip.CreateEntry($STATE_PREFIX + $entry.path,
                                          [IO.Compression.CompressionLevel]::Optimal)
             # F-044: stamp the real last-write time on the entry (ZipArchive otherwise defaults to
             # "now"); ExtractToFile then restores it on the file, so mtime survives the round-trip.
             if ($h.LastWrite) { try { $zipEntry.LastWriteTime = [DateTimeOffset]$h.LastWrite } catch { } }
             $dest = $zipEntry.Open()
             try {
                 $h.Stream.Position = 0
                 $h.Stream.CopyTo($dest)
             }
             finally { $dest.Dispose() }
         }
    }
    finally { $zip.Dispose() }

    # --- verify what was written, before it takes the final name --------------------------
    $problems = @()
    $zip = [IO.Compression.ZipFile]::OpenRead($partial)
    try {
        $present = @{}
        foreach ($e in $zip.Entries) { $present[$e.FullName] = $e }
        foreach ($entry in $entries) {
            $name = $STATE_PREFIX + $entry.path + $(if ($entry.kind -eq 'directory') { '/' } else { '' })
            if (-not $present.ContainsKey($name)) {
                $problems += "missing from the archive: $($entry.path)"
                continue
            }
            if ($entry.kind -eq 'directory') { continue }
            $stream = $present[$name].Open()
            try {
                $sha = [Security.Cryptography.SHA256]::Create()
                try { $digest = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
                finally { $sha.Dispose() }
            }
            finally { $stream.Dispose() }
            if ($digest -ne $entry.sha256) {
                $problems += "content differs for $($entry.path): inventory $($entry.sha256), archive $digest"
            }
        }
        if (-not $present.ContainsKey($INVENTORY_NAME)) { $problems += 'the archive carries no inventory' }
    }
    finally { $zip.Dispose() }

    if ($problems.Count -gt 0) {
        Write-Output ''
        Write-Output 'backup: FAILED verification - the capture did not reproduce the state root.'
        $problems | Select-Object -First 20 | ForEach-Object { Write-Output "    $_" }
        Write-Output ''
        Write-Output "  Nothing was published. $outFull was not created."
        exit 5
    }

    # --- publish atomically ---------------------------------------------------------------
    Move-Item -LiteralPath $partial -Destination $outFull
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $outFull).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText("$outFull.sha256", "$hash  $([IO.Path]::GetFileName($outFull))`n", $utf8NoBom)
    # The inventory is published beside the archive too, so an operator can read what a backup
    # holds without opening it.
    [IO.File]::WriteAllText("$outFull.inventory.json", $inventoryJson, $utf8NoBom)

    Write-Output ''
    Write-Output 'backup: COMPLETE'
    Write-Output "  archive    $outFull"
    Write-Output "  sha256     $hash"
    Write-Output "  sidecar    $outFull.sha256   (integrity only - it authenticates no publisher)"
    Write-Output "  inventory  $outFull.inventory.json"
    Write-Output "  captured   $captured file(s), $($dirs.Count) director(y/ies), $($inventory.total_bytes) byte(s)"
    Write-Output "  method     $method"
    if ($inventory.modules) { Write-Output "  modules    $($inventory.modules -join ', ')" }
    Write-Output ''
    Write-Output '  Restore with: tools\release\restore_state.ps1 -Archive <path>'
    exit 0
}
finally {
    Exit-StateTransactionLock $txLock
    foreach ($h in $held) {
        if ($h.Stream) {
            try { $h.Stream.Dispose() } catch { }
        }
    }
    if (Test-Path -LiteralPath $staging) {
        $resolved = [IO.Path]::GetFullPath($staging)
        # Never recurse-delete anything that is not the staging directory this run created.
        if ($resolved.StartsWith([IO.Path]::GetFullPath($outDir).TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) -and
            (Split-Path -Leaf $resolved).StartsWith('.sovereign-backup-staging-')) {
            Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
