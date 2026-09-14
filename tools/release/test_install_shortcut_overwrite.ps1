[CmdletBinding()]
param()

# F-063 regression. install_shortcut.ps1 unconditionally overwrote "Sovereign Workspace.lnk",
# so a clean-room CI run / upgrade / fixture acceptance run silently repointed the operator's real
# launcher shortcut. It must now REFUSE to overwrite an existing shortcut unless -Force is given.
#
# Runs against a disposable -TargetDir fixture (never the real Desktop/Start Menu).

$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'install_shortcut.ps1'
if (-not (Test-Path -LiteralPath $script)) { throw "install_shortcut.ps1 not found at $script" }

$fixture = Join-Path ([System.IO.Path]::GetTempPath()) ("sws-shortcut-test-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture -Force | Out-Null
try {
    # (1) first creation succeeds and writes the two links under the fixture.
    $links = & $script -TargetDir $fixture
    $desktopLink = Join-Path $fixture 'Desktop\Sovereign Workspace.lnk'
    if (-not (Test-Path -LiteralPath $desktopLink)) {
        throw "F-063 FAIL: first run did not create $desktopLink"
    }

    # (2) a second run WITHOUT -Force must refuse rather than silently overwrite.
    $refused = $false
    try { & $script -TargetDir $fixture | Out-Null }
    catch { $refused = $true }
    if (-not $refused) {
        throw 'F-063 FAIL: install_shortcut overwrote an existing shortcut without -Force'
    }

    # (3) -Force replaces it deliberately.
    $forcedThrew = $false
    try { & $script -TargetDir $fixture -Force | Out-Null }
    catch { $forcedThrew = $true }
    if ($forcedThrew) { throw 'F-063 FAIL: -Force did not permit replacing the shortcut' }
}
finally {
    Remove-Item -LiteralPath $fixture -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Output 'install_shortcut: refuses to overwrite an existing shortcut unless -Force (F-063)'
