# Shared cross-transaction lock for the state-mutating release tools (F-043).
#
# THE DEFECT THIS CLOSES. backup_state.ps1, restore_state.ps1 and upgrade.ps1 each move the state
# root aside and place a new tree. None of them excluded the others, so two transactions could
# interleave: a restore that displaced the state root (restore_state.ps1) and a concurrent writer
# or a second restore could recreate it between displacement and placement, making BOTH the
# placement and the put-back fail ("RECOVERY DID NOT COMPLETE"). The directive requires: "Prevent
# concurrent backup/restore/upgrade transactions from colliding."
#
# THE MECHANISM. A single lock FILE in the state PARENT, held open with FileShare.None for the
# life of the transaction. The lock is the exclusive HANDLE, never the file's mere existence:
#
#   - a second holder's OpenOrCreate with FileShare.None fails while the first holds the handle,
#     so only one transaction runs at a time;
#   - if the holder process dies, the OS releases the handle, so the next tool can take the lock
#     even though the file still sits on disk. There is therefore no stale-lock deadlock, which a
#     "the file's existence is the lock" scheme always has after a crash.
#
# The lock lives in the state PARENT (not the state root) so it is never captured by a backup of
# the state root and never displaced by a restore/upgrade cutover of the state root itself.
#
# REENTRANCY. upgrade.ps1 holds this lock for a whole transaction and then shells out to
# backup_state.ps1, which takes the same lock. A plain exclusive lock would deadlock that sub-tool
# against its own parent. So the holder records the held lock path in the SOVEREIGN_STATE_TX_LOCK
# environment variable, which child processes inherit: Enter- called for the SAME lock path that an
# ancestor in this process tree already holds returns a reentrant token that owns no handle and
# releases nothing. The env var lives only inside the holder's process tree, so it cannot leak a
# stale "already held" into an unrelated later invocation.

$ErrorActionPreference = 'Stop'

function Enter-StateTransactionLock {
    param(
        [Parameter(Mandatory = $true)] [string] $StateParent,
        [string] $Operation = 'state-transaction',
        [int] $TimeoutSeconds = 0
    )
    if (-not (Test-Path -LiteralPath $StateParent -PathType Container)) {
        New-Item -ItemType Directory -Path $StateParent -Force | Out-Null
    }
    $lockPath = Join-Path $StateParent '.sovereign-state-tx.lock'
    if ($env:SOVEREIGN_STATE_TX_LOCK -and
        $env:SOVEREIGN_STATE_TX_LOCK.Equals($lockPath, [StringComparison]::OrdinalIgnoreCase)) {
        # An ancestor transaction in this process tree already holds this exact lock. Reentrant: no
        # new handle, and Exit- on this token is a no-op so the ancestor stays the sole releaser.
        return [pscustomobject]@{ Path = $lockPath; Stream = $null; Reentrant = $true }
    }
    $deadline = (Get-Date).AddSeconds([Math]::Max(0, $TimeoutSeconds))
    $stream = $null
    while ($true) {
        try {
            $stream = [IO.FileStream]::new(
                $lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
            break
        }
        catch {
            if ((Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 250; continue }
            $holder = ''
            try { $holder = (Get-Content -Raw -LiteralPath $lockPath -ErrorAction SilentlyContinue).Trim() } catch { }
            $detail = if ($holder) { " Current holder: $holder." } else { '' }
            throw ("Another state transaction holds the lock at $lockPath. Refusing to run " +
                   "'$Operation' concurrently with backup/restore/upgrade.$detail")
        }
    }
    # Record who holds it, for a human reading a stuck lock. Best effort; the handle is the lock.
    try {
        $stream.SetLength(0)
        $info = [Text.Encoding]::UTF8.GetBytes(
            ("op={0} pid={1} utc={2}" -f $Operation, $PID, (Get-Date).ToUniversalTime().ToString('o')))
        $stream.Write($info, 0, $info.Length)
        $stream.Flush()
    }
    catch { }
    # Publish the held path so child processes (e.g. upgrade -> backup_state) reenter instead of
    # deadlocking. Inherited by processes started after this point.
    $env:SOVEREIGN_STATE_TX_LOCK = $lockPath
    return [pscustomobject]@{ Path = $lockPath; Stream = $stream; Reentrant = $false }
}

function Exit-StateTransactionLock {
    param($Lock)
    if (-not $Lock) { return }
    if ($Lock.Reentrant) { return }  # not ours: an ancestor transaction owns the real handle
    try { if ($Lock.Stream) { $Lock.Stream.Dispose() } } catch { }
    if ($env:SOVEREIGN_STATE_TX_LOCK -and
        $env:SOVEREIGN_STATE_TX_LOCK.Equals([string]$Lock.Path, [StringComparison]::OrdinalIgnoreCase)) {
        $env:SOVEREIGN_STATE_TX_LOCK = $null
    }
    # Remove the on-disk file too, so a stopped-and-restarted machine does not accumulate lock
    # files. Failure is harmless: the next Enter- reuses the same path.
    try { Remove-Item -LiteralPath $Lock.Path -Force -ErrorAction SilentlyContinue } catch { }
}
