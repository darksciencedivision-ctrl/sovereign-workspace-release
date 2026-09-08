[CmdletBinding()]
param(
    # The OLD installation whose state lives beside its code. Read-only to this script.
    [Parameter(Mandatory = $true)]
    [string] $LegacyInstall,

    # Where state lives now. Defaults to the workspace state root.
    [string] $StateRoot,

    # Write the receipt here. Defaults to beside the state root.
    [string] $ReceiptPath,

    # Without this the script only PLANS: it reads, decides, prints and writes a receipt, and
    # changes nothing. Migration of the operator's only copy of their work is not a thing to
    # default into.
    [switch] $Apply,

    # What to do when the destination already holds a file. Default: keep what is there.
    [ValidateSet('KeepExisting', 'KeepBoth')]
    [string] $OnConflict = 'KeepExisting'
)

# SWS-CORRECTIVE-01 workstream 3.3 - the legacy-state migration plan.
#
# Before this release, runtime state lived INSIDE the install root. It now lives under
# %LOCALAPPDATA%\SovereignWorkspace\<module-id>, which is what made uninstall and upgrade
# possible. docs/LIMITATIONS.md recorded the consequence honestly and then stopped there:
# "Nothing migrates it automatically. Copy it into the new state root, or start fresh." That is
# an acknowledged gap, not a plan, and "copy it by hand" is the advice this whole programme
# exists to stop giving.
#
# THE CONTRACT.
#
#   NON-DESTRUCTIVE. This script COPIES. The legacy installation is opened read-only and is
#   never modified, moved or deleted, so a migration that goes wrong costs nothing: the original
#   is still there. Removing the old installation stays the operator's decision, made after they
#   have seen the result.
#
#   NO SILENT OVERWRITE. If the destination already holds a file, the default is to KEEP WHAT IS
#   THERE and record the conflict. -OnConflict KeepBoth writes the incoming copy alongside as
#   `<name>.legacy-<stamp><ext>` instead. Neither branch destroys anything. A migration that
#   overwrote current state with older state would be the worst outcome available here.
#
#   NO SILENT ABANDONMENT. Every legacy file is accounted for in the receipt: migrated,
#   conflicted, or skipped with a reason. A file that is not copied is REPORTED, never dropped.
#
#   A RECEIPT. One JSON document naming the source, the destination, the timestamp, the product
#   version, and every decision with the SHA-256 of what was read and what was written. It is
#   written whether or not -Apply was passed, so a plan can be reviewed before it is run and
#   compared against what actually happened afterwards.
#
#   PLAN FIRST. Without -Apply nothing is written except the receipt.

$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
$utf8NoBom = [Text.UTF8Encoding]::new($false)
. (Join-Path $PSScriptRoot 'path_guard.ps1')

$legacyRoot = Get-CanonicalPath $LegacyInstall
if (-not (Test-Path -LiteralPath $legacyRoot -PathType Container)) {
    throw "Legacy installation not found: $legacyRoot"
}

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
$stateRootFull = Get-CanonicalPath $StateRoot
$volumeRoot = [IO.Path]::GetPathRoot($stateRootFull)
if ($stateRootFull.TrimEnd('\').Equals($volumeRoot.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing a filesystem-root state root: $stateRootFull"
}
if ($stateRootFull.StartsWith($legacyRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or
    $legacyRoot.StartsWith($stateRootFull + '\', [StringComparison]::OrdinalIgnoreCase) -or
    $legacyRoot.Equals($stateRootFull, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing overlapping legacy install and state root: $legacyRoot / $stateRootFull"
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
if (-not $ReceiptPath) {
    $ReceiptPath = "${stateRootFull}.migration-receipt-${stamp}.json"
}

# Where each module's state used to live INSIDE the install, and where it goes now. Enumerated
# explicitly, never by glob: a glob over an install root would sweep up product code.
$plan = @(
    @{ module = 'sovereign';   from = 'modules\sovereign\runtime';        to = 'sovereign\runtime' },
    @{ module = 'sovereign';   from = 'modules\sovereign\published';      to = 'sovereign\published' },
    @{ module = 'sovereign';   from = 'modules\sovereign\library\queues'; to = 'sovereign\library\queues' },
    @{ module = 'sovereign';   from = 'modules\sovereign\logs';           to = 'sovereign\logs' },
    @{ module = 'sow';         from = 'modules\sow\.recovery';            to = 'sow\.recovery' },
    @{ module = 'sow';         from = 'modules\sow\.runtime\receipts';    to = 'sow\receipts' },
    @{ module = 'sow';         from = 'modules\sow\store';                to = 'sow\store' },
    @{ module = 'debate';      from = 'modules\debate\config.json';       to = 'debate\config.json' },
    @{ module = 'debate';      from = 'modules\debate\logs';              to = 'debate\logs' },
    @{ module = 'distillery';  from = 'modules\distillery\logs';          to = 'distillery\logs' },
    @{ module = 'tokencenter'; from = 'modules\tokencenter\data';         to = 'tokencenter\data' }
)

function Get-Sha {
    param([string] $Path)
    try { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
    catch { return $null }
}

$decisions = New-Object System.Collections.Generic.List[object]
$counts = @{ migrate = 0; conflict = 0; skip = 0; identical = 0 }

foreach ($item in $plan) {
    $source = Join-Path $legacyRoot $item.from
    if (-not (Test-Path -LiteralPath $source)) {
        $decisions.Add([pscustomobject][ordered]@{
            module = $item.module; source = $item.from; destination = $item.to
            decision = 'skip'; reason = 'not present in the legacy installation'
            source_sha256 = $null; destination_sha256 = $null; written = $null
        })
        $counts.skip++
        continue
    }

    $sourceFiles = @()
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        $sourceFiles = @([pscustomobject]@{ Full = $source; Rel = '' })
    }
    else {
        $prefix = ([IO.Path]::GetFullPath($source).TrimEnd('\')) + '\'
        $sourceFiles = @(Get-ChildItem -LiteralPath $source -Force -Recurse -File -ErrorAction SilentlyContinue |
            ForEach-Object { [pscustomobject]@{ Full = $_.FullName; Rel = $_.FullName.Substring($prefix.Length) } })
    }

    foreach ($file in $sourceFiles) {
        $relTo = if ($file.Rel) { Join-Path $item.to $file.Rel } else { $item.to }
        $target = Join-Path $stateRootFull $relTo
        try {
            $canonFile = Get-CanonicalPath $file.Full
            if (-not ($canonFile.Equals($legacyRoot, [StringComparison]::OrdinalIgnoreCase) -or
                      $canonFile.StartsWith($legacyRoot + '\', [StringComparison]::OrdinalIgnoreCase))) {
                $decisions.Add([pscustomobject][ordered]@{
                    module = $item.module; source = $file.Full.Substring($legacyRoot.Length + 1)
                    destination = $relTo; decision = 'skip'
                    reason = 'source resolves outside the legacy installation (reparse point)'
                    source_sha256 = $null; destination_sha256 = $null; written = $null
                })
                $counts.skip++
                continue
            }
        }
        catch {
            $decisions.Add([pscustomobject][ordered]@{
                module = $item.module; source = $file.Full.Substring($legacyRoot.Length + 1)
                destination = $relTo; decision = 'skip'
                reason = 'source path could not be canonicalized'
                source_sha256 = $null; destination_sha256 = $null; written = $null
            })
            $counts.skip++
            continue
        }
        $sourceHash = Get-Sha $file.Full

        if ($null -eq $sourceHash) {
            $decisions.Add([pscustomobject][ordered]@{
                module = $item.module; source = $file.Full.Substring($legacyRoot.Length + 1)
                destination = $relTo; decision = 'skip'
                reason = 'could not be read (locked, or permission denied)'
                source_sha256 = $null; destination_sha256 = $null; written = $null
            })
            $counts.skip++
            continue
        }

        $decision = 'migrate'; $reason = ''; $written = $relTo
        $targetHash = $null
        if (Test-Path -LiteralPath $target -PathType Leaf) {
            $targetHash = Get-Sha $target
            if ($targetHash -eq $sourceHash) {
                $decision = 'identical'; $reason = 'destination already holds the same bytes'
                $written = $null
            }
            elseif ($OnConflict -eq 'KeepExisting') {
                $decision = 'conflict'
                $reason = 'destination already holds a DIFFERENT file; kept what is there'
                $written = $null
            }
            else {
                $ext = [IO.Path]::GetExtension($target)
                $base = [IO.Path]::GetFileNameWithoutExtension($target)
                $written = Join-Path (Split-Path -Parent $relTo) ("$base.legacy-$stamp$ext")
                $target = Join-Path $stateRootFull $written
                $decision = 'conflict'
                $reason = "destination already holds a DIFFERENT file; wrote the legacy copy alongside"
            }
        }

        if ($Apply -and ($decision -eq 'migrate' -or ($decision -eq 'conflict' -and $written))) {
            New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
            Copy-Item -LiteralPath $file.Full -Destination $target -Force
            $verify = Get-Sha $target
            if ($verify -ne $sourceHash) {
                throw "Migration copy did not reproduce its source: $($file.Full) -> $target"
            }
        }

        $decisions.Add([pscustomobject][ordered]@{
            module = $item.module; source = $file.Full.Substring($legacyRoot.Length + 1)
            destination = $relTo; decision = $decision; reason = $reason
            source_sha256 = $sourceHash; destination_sha256 = $targetHash; written = $written
        })
        if ($decision -eq 'migrate') { $counts.migrate++ }
        elseif ($decision -eq 'conflict') { $counts.conflict++ }
        elseif ($decision -eq 'identical') { $counts.identical++ }
    }
}

$productVersion = 'unknown'
$versionFile = Join-Path $PSScriptRoot '..\..\VERSION.json'
if (Test-Path -LiteralPath $versionFile -PathType Leaf) {
    try { $productVersion = [string](Get-Content -Raw -LiteralPath $versionFile | ConvertFrom-Json).version }
    catch { }
}

$decisionArray = $decisions.ToArray()
$receipt = [ordered]@{
    schema           = 'sovereign.state-migration.v1'
    created_utc      = (Get-Date).ToUniversalTime().ToString('o')
    applied          = [bool]$Apply
    product_version  = $productVersion
    legacy_install   = $legacyRoot
    state_root       = $stateRootFull
    on_conflict      = $OnConflict
    note             = 'The legacy installation is opened read-only and is never modified, moved or deleted. Nothing is overwritten: a conflicting destination is kept, or the legacy copy is written alongside. Every legacy file appears below exactly once.'
    counts           = $counts
    decisions        = $decisionArray
}
New-Item -ItemType Directory -Path (Split-Path -Parent ([IO.Path]::GetFullPath($ReceiptPath))) -Force | Out-Null
[IO.File]::WriteAllText([IO.Path]::GetFullPath($ReceiptPath),
                        ($receipt | ConvertTo-Json -Depth 8) + "`n", $utf8NoBom)

Write-Output ''
Write-Output $(if ($Apply) { 'migrate: APPLIED' } else { 'migrate: PLAN ONLY - nothing was written (pass -Apply to perform it)' })
Write-Output "  legacy installation  $legacyRoot   (read-only; untouched)"
Write-Output "  state root           $stateRootFull"
Write-Output "  to migrate           $($counts.migrate)"
Write-Output "  already identical    $($counts.identical)"
Write-Output "  conflicts            $($counts.conflict)   (on-conflict: $OnConflict)"
Write-Output "  skipped              $($counts.skip)"
Write-Output "  receipt              $([IO.Path]::GetFullPath($ReceiptPath))"
if ($counts.conflict -gt 0) {
    Write-Output ''
    Write-Output '  CONFLICTS - the destination already held a different file. Nothing was'
    Write-Output '  overwritten. Read the receipt and decide per file:'
    $decisionArray | Where-Object { $_.decision -eq 'conflict' } | Select-Object -First 10 |
        ForEach-Object { Write-Output "    $($_.destination)" }
}
Write-Output ''
Write-Output '  Nothing was removed from the legacy installation. Delete it yourself once you'
Write-Output '  have confirmed the migrated state works.'
exit 0
