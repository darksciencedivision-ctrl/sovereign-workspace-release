[CmdletBinding()]
param(
    # Where to write the backup archive. Defaults to a timestamped file beside the state root.
    [string] $Out,

    # The state root to back up. Defaults to the workspace state root.
    [string] $StateRoot
)

# EPC-01 P4-5 - back up the operator's state as one verifiable archive.
#
# There was no backup or restore tooling and no documented state inventory, while uninstall
# could not run on a used installation (P0-5) and no upgrade path existed (P1-1). The only
# advice that could honestly be given was "copy some directories by hand", with no way to
# check the copy afterwards.
#
# P4-4 gave state a single home, so it can now be captured as one thing. The archive carries a
# SHA-256 sidecar in the same form the release artifacts use, so a restore can verify what it
# is about to consume rather than trusting the file it was handed.
#
# This script READS the state root and writes elsewhere. It never modifies state.

$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop

if (-not $StateRoot) {
    $StateRoot = $env:SOVEREIGN_WORKSPACE_STATE
    if (-not $StateRoot) {
        $localAppData = $env:LOCALAPPDATA
        if (-not $localAppData) { $localAppData = Join-Path $env:USERPROFILE 'AppData\Local' }
        $StateRoot = Join-Path $localAppData 'SovereignWorkspace'
    }
}
$stateRootFull = [IO.Path]::GetFullPath($StateRoot).TrimEnd('\')

if (-not (Test-Path -LiteralPath $stateRootFull -PathType Container)) {
    throw "No state to back up: $stateRootFull does not exist"
}

$entries = @(Get-ChildItem -LiteralPath $stateRootFull -Force -Recurse -File)
if ($entries.Count -eq 0) {
    Write-Output "backup: state root $stateRootFull is empty - nothing to back up"
    exit 0
}

if (-not $Out) {
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
    $Out = "${stateRootFull}.backup-${stamp}.zip"
}
$outFull = [IO.Path]::GetFullPath($Out)
if (Test-Path -LiteralPath $outFull) {
    throw "Refusing to overwrite an existing backup: $outFull"
}

# An inventory travels INSIDE the archive, so a restore can say what it holds without
# extracting it first, and so a reader can see what was captured years later.
$inventory = [ordered]@{
    schema      = 'sovereign.state-backup.v1'
    created_utc = (Get-Date).ToUniversalTime().ToString('o')
    state_root  = $stateRootFull
    file_count  = $entries.Count
    total_bytes = ($entries | Measure-Object -Property Length -Sum).Sum
    modules     = @(Get-ChildItem -LiteralPath $stateRootFull -Force -Directory |
                    ForEach-Object { $_.Name })
}
$inventoryPath = Join-Path $stateRootFull 'STATE-BACKUP-INVENTORY.json'
$utf8NoBom = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText($inventoryPath, ($inventory | ConvertTo-Json -Depth 6) + "`n", $utf8NoBom)

try {
    Write-Output "backup: capturing $($entries.Count) file(s) from $stateRootFull"
    Compress-Archive -Path (Join-Path $stateRootFull '*') -DestinationPath $outFull -Force
}
finally {
    # The inventory is a product of the backup, not part of the operator's state.
    Remove-Item -LiteralPath $inventoryPath -Force -ErrorAction SilentlyContinue
}

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $outFull).Hash.ToLowerInvariant()
[IO.File]::WriteAllText("$outFull.sha256", "$hash  $([IO.Path]::GetFileName($outFull))`n", $utf8NoBom)

Write-Output ''
Write-Output 'backup: COMPLETE'
Write-Output "  archive  $outFull"
Write-Output "  sha256   $hash"
Write-Output "  sidecar  $outFull.sha256"
Write-Output "  modules  $($inventory.modules -join ', ')"
Write-Output ''
Write-Output '  Restore with: tools\release\restore_state.ps1 -Archive <path>'
