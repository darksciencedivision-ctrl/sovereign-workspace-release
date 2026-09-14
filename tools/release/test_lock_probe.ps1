[CmdletBinding()]
param([Parameter(Mandatory = $true)] [string] $StateParent)

# Test helper for test_lifecycle_p2.ps1: try to take the shared state-transaction lock in a FRESH
# process (so it does not inherit the parent's SOVEREIGN_STATE_TX_LOCK reentrancy env var) with no
# wait. Exit 0 if acquired, 3 if another holder blocks it.

$ErrorActionPreference = 'Stop'
$env:SOVEREIGN_STATE_TX_LOCK = $null
. (Join-Path $PSScriptRoot 'state_lock.ps1')
try {
    $lock = Enter-StateTransactionLock -StateParent $StateParent -Operation 'probe' -TimeoutSeconds 0
}
catch {
    exit 3
}
Exit-StateTransactionLock $lock
exit 0
