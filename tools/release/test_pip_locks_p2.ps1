[CmdletBinding()]
param()

# F-071 regression for Install-LockedRequirements (tools/release/pip_locks.ps1). Uses a stub
# interpreter (a .cmd that records the pip arguments it was handed) so no network or real pip is
# touched. Asserts: an unhashed lock is refused by default; -AllowUnhashed installs it WITHOUT
# --require-hashes; a hashed lock installs WITH --require-hashes.

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'pip_locks.ps1')

$failures = @()
function Check($name, [scriptblock] $body) {
    try { & $body; Write-Output "  ok   $name" }
    catch { $script:failures += "$name : $($_.Exception.Message)"; Write-Output "  FAIL $name : $($_.Exception.Message)" }
}

$root = Join-Path ([IO.Path]::GetTempPath()) ('pip-locks-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root -Force | Out-Null
try {
    $capture = Join-Path $root 'args.txt'
    $stub = Join-Path $root 'stub-python.cmd'
    # Record every argument (one per line) and succeed.
    # Record the whole argument line, then succeed. Redirection is written BEFORE `echo` so cmd
    # does not read a trailing digit as a file-descriptor redirect. Tokens have no embedded spaces
    # (temp path is a GUID; pip flags are space-free), so the test splits the line on whitespace.
    # The concatenation is parenthesised: PowerShell's comma binds TIGHTER than +, so an unwrapped
    # 'a' + $x + 'b' inside @(..., ...) splinters into separate array elements (separate lines).
    Set-Content -LiteralPath $stub -Encoding ascii -Value @(
        '@echo off',
        ('>>"' + $capture + '" echo %*'),
        'exit /b 0'
    )
    function Get-CapturedArgs { (Get-Content -Raw -LiteralPath $capture) -split '\s+' | Where-Object { $_ } }

    $hashedLock = Join-Path $root 'hashed.txt'
    Set-Content -LiteralPath $hashedLock -Encoding ascii -Value @(
        'flask==3.1.3 --hash=sha256:0000000000000000000000000000000000000000000000000000000000000000'
    )
    $unhashedLock = Join-Path $root 'unhashed.txt'
    Set-Content -LiteralPath $unhashedLock -Encoding ascii -Value @('flask==3.1.3')

    Check 'unhashed lock is refused by default' {
        $threw = $false
        try { Install-LockedRequirements -PythonExe $stub -LockPath $unhashedLock -Label 'T' | Out-Null }
        catch { $threw = $true }
        if (-not $threw) { throw 'an unhashed lock was installed without -AllowUnhashed' }
    }

    Check 'unhashed lock installs with -AllowUnhashed and WITHOUT --require-hashes' {
        Remove-Item -LiteralPath $capture -ErrorAction SilentlyContinue
        Install-LockedRequirements -PythonExe $stub -LockPath $unhashedLock -Label 'T' -AllowUnhashed | Out-Null
        $args = Get-CapturedArgs
        if ($args -contains '--require-hashes') { throw 'unhashed install must NOT pass --require-hashes' }
        if (-not ($args -contains '--only-binary=:all:')) { throw 'expected the pinned pip flags' }
    }

    Check 'hashed lock installs WITH --require-hashes' {
        Remove-Item -LiteralPath $capture -ErrorAction SilentlyContinue
        Install-LockedRequirements -PythonExe $stub -LockPath $hashedLock -Label 'T' | Out-Null
        $args = Get-CapturedArgs
        if (-not ($args -contains '--require-hashes')) { throw 'a hashed lock MUST be installed with --require-hashes' }
    }

    # A lock where only SOME pins carry hashes must still go to pip in --require-hashes mode, which
    # then refuses the unhashed pin (verified against real pip in the F-071 acceptance record). It
    # must never be treated as an unhashed lock that an -AllowUnhashed caller could slip through.
    $partialLock = Join-Path $root 'partial.txt'
    Set-Content -LiteralPath $partialLock -Encoding ascii -Value @(
        'flask==3.1.3 --hash=sha256:0000000000000000000000000000000000000000000000000000000000000000',
        'requests==2.34.2'
    )
    Check 'partially hashed lock installs WITH --require-hashes even under -AllowUnhashed' {
        Remove-Item -LiteralPath $capture -ErrorAction SilentlyContinue
        Install-LockedRequirements -PythonExe $stub -LockPath $partialLock -Label 'T' -AllowUnhashed | Out-Null
        $args = Get-CapturedArgs
        if (-not ($args -contains '--require-hashes')) { throw 'a partially hashed lock MUST be installed with --require-hashes' }
    }
}
finally {
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Output ''
if ($failures.Count -gt 0) {
    Write-Output "pip_locks P2: $($failures.Count) FAILURE(S)"
    $failures | ForEach-Object { Write-Output "  - $_" }
    exit 1
}
Write-Output 'pip_locks P2: all checks passed (F-071 --require-hashes enforcement)'
exit 0
