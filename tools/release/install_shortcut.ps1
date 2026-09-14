[CmdletBinding()]
param(
    [string] $TargetDir,
    # F-063. Refuse to overwrite an existing shortcut in BOTH branches (real Desktop/Start Menu AND
    # a -TargetDir fixture). Overwriting the operator's real launcher shortcut silently -- as a
    # clean-room CI run, an upgrade or a fixture acceptance run used to -- repoints it at a %TEMP%
    # or clean-room install. Pass -Force only when replacing a shortcut is explicitly intended.
    [switch] $Force
)

$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$launcher = Join-Path $workspaceRoot 'Start-Shell.ps1'
$icon = Join-Path $workspaceRoot 'shell\static\sovereign.ico'

if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "Launcher not found: $launcher"
}
if (-not (Test-Path -LiteralPath $icon -PathType Leaf)) {
    throw "Shortcut icon not found: $icon"
}

if ($TargetDir) {
    $redirectRoot = [IO.Path]::GetFullPath($TargetDir)
    $desktopDir = Join-Path $redirectRoot 'Desktop'
    $startMenuDir = Join-Path $redirectRoot 'Start Menu\Programs'
}
else {
    $desktopDir = [Environment]::GetFolderPath('Desktop')
    $startMenuDir = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs'
}

$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $launcher
$wsh = New-Object -ComObject WScript.Shell

foreach ($destination in @($desktopDir, $startMenuDir)) {
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    $linkPath = Join-Path $destination 'Sovereign Workspace.lnk'
    if ((Test-Path -LiteralPath $linkPath) -and -not $Force) {
        throw "Refusing to overwrite existing shortcut: $linkPath (pass -Force to replace)"
    }
    $shortcut = $wsh.CreateShortcut($linkPath)
    $shortcut.TargetPath = $powershell
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $workspaceRoot
    $shortcut.WindowStyle = 1
    $shortcut.IconLocation = "$icon,0"
    $shortcut.Description = 'Launch Sovereign Workspace Shell'
    $shortcut.Save()
    Write-Output $linkPath
}
