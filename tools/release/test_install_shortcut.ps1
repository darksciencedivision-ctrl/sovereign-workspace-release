[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$installer = Join-Path $PSScriptRoot 'install_shortcut.ps1'
$testRoot = [IO.Path]::GetFullPath((Join-Path $workspaceRoot '.runtime\shortcut-test'))
$workspacePrefix = [IO.Path]::GetFullPath($workspaceRoot).TrimEnd('\') + '\'
if (-not $testRoot.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing test cleanup outside workspace: $testRoot"
}
if (Test-Path -LiteralPath $testRoot) {
    Remove-Item -LiteralPath $testRoot -Recurse -Force
}

try {
    # Two executions prove replacement is idempotent and remain redirected inside the worktree.
    & $installer -TargetDir $testRoot | Out-Null
    & $installer -TargetDir $testRoot | Out-Null

    $expectedTarget = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $expectedArguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f (Join-Path $workspaceRoot 'Start-Shell.ps1')
    $expectedIcon = (Join-Path $workspaceRoot 'shell\static\sovereign.ico') + ',0'
    $links = @(
        (Join-Path $testRoot 'Desktop\Sovereign Workspace.lnk'),
        (Join-Path $testRoot 'Start Menu\Programs\Sovereign Workspace.lnk')
    )
    $wsh = New-Object -ComObject WScript.Shell
    foreach ($link in $links) {
        if (-not (Test-Path -LiteralPath $link -PathType Leaf)) {
            throw "Shortcut missing: $link"
        }
        $shortcut = $wsh.CreateShortcut($link)
        if (-not $shortcut.TargetPath.Equals($expectedTarget, [StringComparison]::OrdinalIgnoreCase)) {
            throw "TargetPath mismatch: $($shortcut.TargetPath)"
        }
        if ($shortcut.Arguments -ne $expectedArguments) {
            throw "Arguments mismatch: $($shortcut.Arguments)"
        }
        if (-not $shortcut.WorkingDirectory.Equals($workspaceRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw "WorkingDirectory mismatch: $($shortcut.WorkingDirectory)"
        }
        if ($shortcut.WindowStyle -ne 1) {
            throw "WindowStyle mismatch: $($shortcut.WindowStyle)"
        }
        if (-not $shortcut.IconLocation.Equals($expectedIcon, [StringComparison]::OrdinalIgnoreCase)) {
            throw "IconLocation mismatch: $($shortcut.IconLocation)"
        }
    }
    if (@(Get-ChildItem -LiteralPath $testRoot -Filter '*.lnk' -Recurse).Count -ne 2) {
        throw 'Idempotence failure: expected exactly two redirected shortcuts'
    }
    Write-Output 'install_shortcut: 2 redirected links verified by COM; idempotent; no user folders touched'
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
