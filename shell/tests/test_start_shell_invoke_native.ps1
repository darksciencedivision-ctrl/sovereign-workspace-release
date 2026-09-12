[CmdletBinding()]
param()

# F-001 regression. Under Windows PowerShell 5.1, a native command that writes to stderr while the
# script's $ErrorActionPreference is 'Stop' and stderr is redirected is promoted to a terminating
# error. Start-Shell.ps1 (EAP=Stop) probes py -3.12 / -3.14, git and nvidia-smi with `2>$null` /
# `> $null 2>&1`, so a missing interpreter or absent GPU crashed the one supported launcher.
#
# This extracts the REAL Invoke-Native function from Start-Shell.ps1 (by AST, so the shipped body is
# under test, not a copy) and proves that a stderr-writing native command run through it does NOT
# throw under EAP=Stop and that $LASTEXITCODE still reports the real code -- while the same call made
# directly DOES throw (the fail-before control).

$ErrorActionPreference = 'Stop'
$launcher = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'Start-Shell.ps1'
if (-not (Test-Path -LiteralPath $launcher)) { throw "Start-Shell.ps1 not found at $launcher" }

$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($launcher, [ref]$tokens, [ref]$errors)
if ($errors -and $errors.Count) { throw "Start-Shell.ps1 has parse errors: $($errors[0].Message)" }
$fn = $ast.FindAll({ param($n)
    $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Invoke-Native'
}, $true) | Select-Object -First 1
if (-not $fn) { throw 'Invoke-Native is not defined in Start-Shell.ps1 (F-001 wrapper missing)' }
Invoke-Expression $fn.Extent.Text   # define the real function in this session

# (1) fail-before control: a stderr-writing native command under EAP=Stop, redirected, throws.
$directThrew = $false
try { & cmd /c "echo boom 1>&2 & exit 2" 2>$null | Out-Null }
catch { $directThrew = $true }
if (-not $directThrew) {
    Write-Warning 'the direct native call did not throw here; the 5.1 promotion may not apply on this host'
}

# (2) pass-after: the same call through Invoke-Native does NOT throw, and reports the real exit code.
$threw = $false
$code = $null
try {
    Invoke-Native { & cmd /c "echo boom 1>&2 & exit 2" 2>$null | Out-Null }
    $code = $LASTEXITCODE
} catch { $threw = $true }
if ($threw) { throw 'F-001 FAIL: Invoke-Native still let a native stderr write terminate under EAP=Stop' }
if ($code -ne 2) { throw "F-001 FAIL: Invoke-Native lost the real exit code (got $code, expected 2)" }

# (3) EAP is restored after the call (the wrapper must not leak Continue into the rest of preflight).
if ($ErrorActionPreference -ne 'Stop') {
    throw "F-001 FAIL: Invoke-Native did not restore ErrorActionPreference (now $ErrorActionPreference)"
}

Write-Output 'Start-Shell Invoke-Native: native stderr no longer terminates under EAP=Stop; exit code preserved; EAP restored'
