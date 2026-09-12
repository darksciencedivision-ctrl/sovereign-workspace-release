[CmdletBinding()]
param()

# F-002 / F-003 / F-005 regression for Start-Shell.ps1.
#
# F-002: Start-Process -PassThru reports ExitCode = $null in PS 5.1 unless the process Handle was
#        touched while it was alive; `exit $proc.ExitCode` then silently became exit 0.
# F-003: the normal (post Wait-Process) and "did not answer" paths ended with no `exit`, so the
#        caller read a stale $LASTEXITCODE.
# F-005: the finally block force-killed the shell immediately, TerminateProcess-ing DB/WAL writers
#        instead of letting the shell (which shares this console and got the same Ctrl+C) shut down.
#
# This extracts the REAL Get-SafeExitCode from Start-Shell.ps1 by AST (shipped body under test) and
# proves it never returns $null, then asserts the launcher's structure: the Handle is cached right
# after Start-Process, the finally waits for graceful exit before forcing, and every path ends at a
# deterministic `exit`.

$ErrorActionPreference = 'Stop'
$launcher = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'Start-Shell.ps1'
if (-not (Test-Path -LiteralPath $launcher)) { throw "Start-Shell.ps1 not found at $launcher" }

$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($launcher, [ref]$tokens, [ref]$errors)
if ($errors -and $errors.Count) { throw "Start-Shell.ps1 has parse errors: $($errors[0].Message)" }

# --- F-002: Get-SafeExitCode behaviour -------------------------------------------------------------
$fn = $ast.FindAll({ param($n)
    $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Get-SafeExitCode'
}, $true) | Select-Object -First 1
if (-not $fn) { throw 'Get-SafeExitCode is not defined in Start-Shell.ps1 (F-002 helper missing)' }
Invoke-Expression $fn.Extent.Text

# A process that exited cleanly, Handle cached, yields its real code (not $null).
$p = Start-Process -FilePath $env:ComSpec -ArgumentList '/c','exit 7' -NoNewWindow -PassThru
$null = $p.Handle
$p.WaitForExit(5000) | Out-Null
$code = Get-SafeExitCode $p
if ($code -ne 7) { throw "F-002 FAIL: Get-SafeExitCode lost the real code (got $code, expected 7)" }

# A still-running process maps to a non-zero failure, never $null / 0.
$live = Start-Process -FilePath $env:ComSpec -ArgumentList '/c','ping -n 6 127.0.0.1 > nul' -NoNewWindow -PassThru
try {
    $liveCode = Get-SafeExitCode $live
    if ($null -eq $liveCode) { throw 'F-002 FAIL: Get-SafeExitCode returned $null for a live process' }
    if ($liveCode -eq 0) { throw 'F-002 FAIL: a live (not-yet-exited) process was reported as success' }
}
finally { Stop-Process -Id $live.Id -Force -ErrorAction SilentlyContinue }

# --- F-002/F-005/F-003: launcher structure ---------------------------------------------------------
$text = Get-Content -LiteralPath $launcher -Raw

$startIdx  = $text.IndexOf('Start-Process -FilePath $py')
$handleIdx = $text.IndexOf('$null = $proc.Handle')
$waitIdx   = $text.IndexOf('Wait-Process -Id $proc.Id')
if ($startIdx -lt 0 -or $handleIdx -lt 0) { throw 'F-002 FAIL: the Handle cache after Start-Process is missing' }
if (-not ($startIdx -lt $handleIdx -and $handleIdx -lt $waitIdx)) {
    throw 'F-002 FAIL: $proc.Handle is not cached between Start-Process and Wait-Process'
}

$graceIdx = $text.IndexOf('WaitForExit($gracefulStopTimeoutMs)')
$forceIdx = $text.IndexOf('Stop-Process -Id $proc.Id -Force')
if ($graceIdx -lt 0) { throw 'F-005 FAIL: the finally block does not wait for graceful shutdown' }
if (-not ($graceIdx -lt $forceIdx)) {
    throw 'F-005 FAIL: Stop-Process -Force is not preceded by the graceful WaitForExit'
}

# F-003: the finally ends with a deterministic exit (no stale $LASTEXITCODE leak).
if ($text -notmatch 'exit \$script:launcherExit') {
    throw 'F-003 FAIL: the launcher does not exit with a determinate code'
}

Write-Output 'Start-Shell exit/shutdown: Handle cached (F-002), graceful stop precedes force (F-005), deterministic exit on every path (F-003)'
