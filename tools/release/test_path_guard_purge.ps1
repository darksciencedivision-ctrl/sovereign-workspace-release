[CmdletBinding()]
param()

# Regression for R04 (canonical containment of a not-yet-existing child of a junction) and F-040
# (fail-closed guard before the uninstall state-root purge). Runs entirely on disposable temp
# directories and real NTFS junctions; it never touches operator data.

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'path_guard.ps1')

$root = Join-Path ([IO.Path]::GetTempPath()) ('pathguard-test-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
$junctions = New-Object System.Collections.ArrayList
function New-Junction($link, $target) {
    New-Item -ItemType Junction -Path $link -Target $target | Out-Null
    [void]$junctions.Add((Split-Path -Path $link))  # remember the parent so cleanup can rmdir the link
    $link
}
function Assert-Throws($script, $because) {
    $threw = $false
    try { & $script } catch { $threw = $true }
    if (-not $threw) { throw "EXPECTED A REFUSAL: $because" }
}

try {
    New-Item -ItemType Directory -Path $root | Out-Null
    $allowed = New-Item -ItemType Directory -Path (Join-Path $root 'allowed') | Out-Null
    $allowed = Join-Path $root 'allowed'
    $outside = New-Item -ItemType Directory -Path (Join-Path $root 'outside') | Out-Null
    $outside = Join-Path $root 'outside'

    # --- R04: a junction in the EXISTING prefix must not smuggle a nonexistent child past containment
    $link = New-Junction (Join-Path $allowed 'link') $outside
    $smuggled = Join-Path $link 'newchild'          # does not exist; parent `link` is a junction out
    if (Test-CanonicalContained -Root $allowed -Candidate $smuggled) {
        throw "R04 FAIL: a nonexistent child under a junction was reported contained: $smuggled"
    }
    # ...and the positive control: a genuinely-contained nonexistent child still resolves as contained
    $realsub = New-Item -ItemType Directory -Path (Join-Path $allowed 'sub') | Out-Null
    $contained = Join-Path (Join-Path $allowed 'sub') 'newchild'
    if (-not (Test-CanonicalContained -Root $allowed -Candidate $contained)) {
        throw "R04 FAIL: a genuinely-contained nonexistent child was reported NOT contained: $contained"
    }

    # --- F-040: the purge guard
    # (a) a genuine, disposable SovereignWorkspace state root with plain contents is purgeable
    $stateOk = Join-Path $root 'SovereignWorkspace'
    New-Item -ItemType Directory -Path (Join-Path $stateOk 'sow') | Out-Null
    Set-Content -LiteralPath (Join-Path $stateOk 'sow\receipt.json') -Value '{}' -Encoding utf8
    $canon = Assert-PurgeableStateRoot -StateRoot $stateOk -InstallRoot (Join-Path $root 'installed-elsewhere')
    if ((Split-Path -Leaf $canon) -ne 'SovereignWorkspace') { throw "F-040 FAIL: valid root refused: $canon" }

    # (b) a filesystem root is refused
    Assert-Throws { Assert-PurgeableStateRoot -StateRoot ([IO.Path]::GetPathRoot($env:SystemDrive + '\')) } 'a filesystem root'

    # (c) a non-SovereignWorkspace leaf is refused (a mis-set variable pointing at an arbitrary dir)
    $wrongLeaf = New-Item -ItemType Directory -Path (Join-Path $root 'NotTheProduct') | Out-Null
    Assert-Throws { Assert-PurgeableStateRoot -StateRoot (Join-Path $root 'NotTheProduct') } 'a non-SovereignWorkspace leaf'

    # (d) a state tree that contains a reparse point is refused
    $stateJunc = Join-Path $root 'SovereignWorkspace-junc'
    # give it the product leaf so it passes the name check and fails specifically on the reparse rule
    $stateJunc = Join-Path $root 'withjunc\SovereignWorkspace'
    New-Item -ItemType Directory -Path $stateJunc | Out-Null
    New-Junction (Join-Path $stateJunc 'escape') $outside | Out-Null
    Assert-Throws { Assert-PurgeableStateRoot -StateRoot $stateJunc } 'a state tree containing a reparse point'

    # (e) a state root that overlaps the install root is refused (state under install)
    $inst = Join-Path $root 'inst'
    $stateUnderInstall = Join-Path $inst 'SovereignWorkspace'
    New-Item -ItemType Directory -Path $stateUnderInstall | Out-Null
    Assert-Throws { Assert-PurgeableStateRoot -StateRoot $stateUnderInstall -InstallRoot $inst } 'a state root under the install root'

    Write-Output 'path_guard: R04 junction containment + F-040 purge guard verified (5 refusals, 2 positives)'
}
finally {
    # Remove junctions as junctions (rmdir does NOT follow into the target) BEFORE the recursive
    # delete, so cleanup can never traverse a link into a sibling and delete unrelated content.
    Get-ChildItem -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 } |
        ForEach-Object { & cmd /c rmdir (('"{0}"') -f $_.FullName) 2>$null }
    if (Test-Path -LiteralPath $root) {
        Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
    }
}
