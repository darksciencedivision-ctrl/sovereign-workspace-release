# F-071: install a pinned Python lock with pip, verifying downloaded bytes against pinned hashes.
#
# `==` pins in a lock guarantee package NAMES and VERSIONS, not the bytes: a newly uploaded wheel
# for an existing version (a better platform tag), or a mirror/proxy substitution, is accepted
# silently. `pip install --require-hashes` refuses any requirement whose bytes do not match a
# pinned --hash= entry. A lock that carries no hashes cannot be verified, so this REFUSES it unless
# the caller explicitly opts into the (transitional) unverified install.

function Install-LockedRequirements {
    param(
        [Parameter(Mandatory = $true)] [string] $PythonExe,
        [Parameter(Mandatory = $true)] [string] $LockPath,
        [Parameter(Mandatory = $true)] [string] $Label,
        # Transitional escape for a lock not yet regenerated with hashes
        # (pip-compile --generate-hashes). Installs WITHOUT byte verification and says so loudly.
        [switch] $AllowUnhashed
    )
    if (-not (Test-Path -LiteralPath $LockPath -PathType Leaf)) { throw "$Label lock not found: $LockPath" }
    # pip's own auto_decode reads a UTF-8 or BOM-marked UTF-16 lock; Select-String detects hashes
    # across those encodings the same way.
    $hasHashes = $false
    try { $hasHashes = [bool](Select-String -LiteralPath $LockPath -Pattern '--hash=' -SimpleMatch -Quiet) } catch { }

    $pipArgs = @('-m', 'pip', 'install', '--disable-pip-version-check',
                 '--index-url', 'https://pypi.org/simple', '--only-binary=:all:', '--no-deps')
    if ($hasHashes) {
        $pipArgs += '--require-hashes'
        Write-Output "install: $Label lock carries hashes; installing with --require-hashes (bytes verified)"
    }
    elseif ($AllowUnhashed) {
        Write-Output "install: WARNING - $Label lock carries NO hashes; installing WITHOUT byte verification (-AllowUnhashedLocks)."
        Write-Output "         Regenerate it with pip-compile --generate-hashes before a real release."
    }
    else {
        throw ("$Label lock has no --hash= entries, so pip cannot verify the downloaded bytes " +
               "(F-071). Regenerate it with pip-compile --generate-hashes, or pass " +
               "-AllowUnhashedLocks to install without byte verification during transition.")
    }
    $pipArgs += @('-r', $LockPath)
    & $PythonExe @pipArgs
    if ($LASTEXITCODE -ne 0) { throw "$Label lock install failed" }
}
