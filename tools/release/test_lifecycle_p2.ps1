[CmdletBinding()]
param()

# P2 lifecycle regression (F-043, F-047, F-048, F-049 and the shared state-transaction lock).
#
# Every script under test ends in `exit`, so each is run as a CHILD powershell.exe and its exit
# code / output inspected. Nothing here touches a real installation or the operator state root:
# every path is a disposable fixture under the temp directory.

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not (Test-Path -LiteralPath $psExe)) { $psExe = 'powershell.exe' }

$failures = @()
function Check($name, [scriptblock] $body) {
    try { & $body; Write-Output "  ok   $name" }
    catch { $script:failures += "$name : $($_.Exception.Message)"; Write-Output "  FAIL $name : $($_.Exception.Message)" }
}

function Invoke-Script($script, [string[]] $ScriptArgs) {
    $quoted = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + (Join-Path $here $script) + '"'))
    foreach ($a in $ScriptArgs) {
        if ($a -match '[\s"]') { $quoted += '"' + ($a -replace '"', '\"') + '"' } else { $quoted += $a }
    }
    $out = Join-Path ([IO.Path]::GetTempPath()) ('lc-' + [Guid]::NewGuid().ToString('N') + '.out')
    $err = "$out.err"
    $p = Start-Process -FilePath $psExe -ArgumentList $quoted -NoNewWindow -Wait -PassThru `
                       -RedirectStandardOutput $out -RedirectStandardError $err
    $text = ''
    foreach ($f in @($out, $err)) { if (Test-Path -LiteralPath $f) { $text += (Get-Content -Raw -LiteralPath $f) } }
    Remove-Item -LiteralPath $out, $err -Force -ErrorAction SilentlyContinue
    return [pscustomobject]@{ Code = [int]$p.ExitCode; Text = $text }
}

$root = Join-Path ([IO.Path]::GetTempPath()) ('sws-lifecycle-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root -Force | Out-Null
try {

    # ---- shared state-transaction lock: exclusive, reentrant-by-env, released ----------------
    Check 'state_lock: exclusive, reentrant via env, released' {
        . (Join-Path $here 'state_lock.ps1')
        $parent = Join-Path $root 'lockparent'
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        $env:SOVEREIGN_STATE_TX_LOCK = $null
        $lock = Enter-StateTransactionLock -StateParent $parent -Operation 'test'
        if (-not $lock.Stream) { throw 'first Enter should own a real handle' }
        if ($lock.Reentrant) { throw 'first Enter should not be reentrant' }
        # A reentrant Enter for the same path (env var set) must own no new handle.
        $re = Enter-StateTransactionLock -StateParent $parent -Operation 'test-reentrant'
        if (-not $re.Reentrant) { throw 'nested Enter for the same lock path should be reentrant' }
        Exit-StateTransactionLock $re          # reentrant release is a no-op
        if (-not $env:SOVEREIGN_STATE_TX_LOCK) { throw 'reentrant Exit must not clear the holder env var' }
        # A separate process cannot take the lock while we hold it.
        $probe = Invoke-Script 'test_lock_probe.ps1' @('-StateParent', $parent)
        if ($probe.Code -eq 0) { throw "a second process acquired the held lock (exit 0): $($probe.Text)" }
        Exit-StateTransactionLock $lock
        if ($env:SOVEREIGN_STATE_TX_LOCK) { throw 'real Exit must clear the holder env var' }
        # Now a fresh process CAN take it.
        $probe2 = Invoke-Script 'test_lock_probe.ps1' @('-StateParent', $parent)
        if ($probe2.Code -ne 0) { throw "lock not released: a fresh process still could not acquire it: $($probe2.Text)" }
    }

    # ---- backup -> restore round-trip (F-043 lock in both; v2 inventory; version match) ------
    Check 'backup/restore: verified round-trip into an empty target' {
        $state = Join-Path $root 'state'
        New-Item -ItemType Directory -Path (Join-Path $state 'sub') -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $state 'a.txt') -Value 'alpha' -NoNewline -Encoding ascii
        Set-Content -LiteralPath (Join-Path $state 'sub\b.txt') -Value 'bravo' -NoNewline -Encoding ascii
        $archive = Join-Path $root 'cap.zip'
        $b = Invoke-Script 'backup_state.ps1' @('-StateRoot', $state, '-Out', $archive)
        if ($b.Code -ne 0) { throw "backup failed ($($b.Code)): $($b.Text)" }
        if (-not (Test-Path -LiteralPath $archive)) { throw 'backup produced no archive' }
        $restored = Join-Path $root 'restored'
        $r = Invoke-Script 'restore_state.ps1' @('-Archive', $archive, '-StateRoot', $restored)
        if ($r.Code -ne 0) { throw "restore failed ($($r.Code)): $($r.Text)" }
        if ((Get-Content -Raw -LiteralPath (Join-Path $restored 'a.txt')) -ne 'alpha') { throw 'a.txt not restored' }
        if ((Get-Content -Raw -LiteralPath (Join-Path $restored 'sub\b.txt')) -ne 'bravo') { throw 'sub/b.txt not restored' }
    }

    # ---- restore refuses a populated target without -Force -----------------------------------
    Check 'restore: refuses to overwrite a populated state root without -Force' {
        $state = Join-Path $root 'state2'
        New-Item -ItemType Directory -Path $state -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $state 'c.txt') -Value 'charlie' -NoNewline -Encoding ascii
        $archive = Join-Path $root 'cap2.zip'
        $b = Invoke-Script 'backup_state.ps1' @('-StateRoot', $state, '-Out', $archive)
        if ($b.Code -ne 0) { throw "backup failed: $($b.Text)" }
        $target = Join-Path $root 'occupied'
        New-Item -ItemType Directory -Path $target -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $target 'existing.txt') -Value 'keepme' -NoNewline -Encoding ascii
        $r = Invoke-Script 'restore_state.ps1' @('-Archive', $archive, '-StateRoot', $target)
        if ($r.Code -eq 0) { throw 'restore into a populated target should have refused without -Force' }
        if ((Get-Content -Raw -LiteralPath (Join-Path $target 'existing.txt')) -ne 'keepme') { throw 'existing file was disturbed' }
    }

    # ---- migrate: PLAN writes a receipt and copies nothing; APPLY copies and completes -------
    Check 'migrate: plan then apply, receipt always written (F-047)' {
        $legacy = Join-Path $root 'legacy'
        New-Item -ItemType Directory -Path (Join-Path $legacy 'modules\debate') -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $legacy 'modules\debate\config.json') -Value '{"x":1}' -NoNewline -Encoding ascii
        $stateM = Join-Path $root 'statem'
        $receipt = Join-Path $root 'receipt.json'

        $plan = Invoke-Script 'migrate_legacy_state.ps1' @('-LegacyInstall', $legacy, '-StateRoot', $stateM, '-ReceiptPath', $receipt)
        if ($plan.Code -ne 0) { throw "plan failed: $($plan.Text)" }
        if (-not (Test-Path -LiteralPath $receipt)) { throw 'plan wrote no receipt' }
        if (Test-Path -LiteralPath (Join-Path $stateM 'debate\config.json')) { throw 'plan copied a file (should be plan-only)' }
        $doc = Get-Content -Raw -LiteralPath $receipt | ConvertFrom-Json
        if ($doc.applied) { throw 'plan receipt should have applied=false' }
        if (-not $doc.completed) { throw 'plan receipt should have completed=true' }

        $apply = Invoke-Script 'migrate_legacy_state.ps1' @('-LegacyInstall', $legacy, '-StateRoot', $stateM, '-ReceiptPath', $receipt, '-Apply')
        if ($apply.Code -ne 0) { throw "apply failed: $($apply.Text)" }
        if ((Get-Content -Raw -LiteralPath (Join-Path $stateM 'debate\config.json')) -ne '{"x":1}') { throw 'apply did not copy the file' }
        $doc2 = Get-Content -Raw -LiteralPath $receipt | ConvertFrom-Json
        if (-not $doc2.applied) { throw 'apply receipt should have applied=true' }
        if (-not $doc2.completed) { throw 'apply receipt should have completed=true' }
    }

    # ---- migrate: never overwrites a different existing destination file ----------------------
    Check 'migrate: keeps an existing different destination (no silent overwrite)' {
        $legacy = Join-Path $root 'legacy2'
        New-Item -ItemType Directory -Path (Join-Path $legacy 'modules\debate') -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $legacy 'modules\debate\config.json') -Value 'LEGACY' -NoNewline -Encoding ascii
        $stateM = Join-Path $root 'statem2'
        New-Item -ItemType Directory -Path (Join-Path $stateM 'debate') -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $stateM 'debate\config.json') -Value 'CURRENT' -NoNewline -Encoding ascii
        $receipt = Join-Path $root 'receipt2.json'
        $apply = Invoke-Script 'migrate_legacy_state.ps1' @('-LegacyInstall', $legacy, '-StateRoot', $stateM, '-ReceiptPath', $receipt, '-Apply')
        if ($apply.Code -ne 0) { throw "apply failed: $($apply.Text)" }
        if ((Get-Content -Raw -LiteralPath (Join-Path $stateM 'debate\config.json')) -ne 'CURRENT') { throw 'existing destination was overwritten' }
    }

    # ---- upgrade -Recover: restores an install left displaced after cutover (F-049) ----------
    Check 'upgrade -Recover: puts a post-cutover-interrupted install back' {
        $install = Join-Path $root 'install'
        New-Item -ItemType Directory -Path $install -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $install 'install-manifest.json') -Value '{"schema":"sovereign.install-manifest.v1"}' -NoNewline -Encoding ascii
        Set-Content -LiteralPath (Join-Path $install 'VERSION.json') -Value '{"version":"9.9.9"}' -NoNewline -Encoding ascii
        $backup = Join-Path $root 'install.previous'
        # Simulate the interruption: the outgoing install was moved aside and never settled.
        Move-Item -LiteralPath $install -Destination $backup
        $tx = Join-Path $root 'tx'
        New-Item -ItemType Directory -Path $tx -Force | Out-Null
        $journal = Join-Path $tx 'upgrade-journal.jsonl'
        $rec1 = @{ utc = 'x'; phase = 'resolve'; status = 'BEGIN'; dest = $install; rollback = $backup; transaction = $tx } | ConvertTo-Json -Compress
        $rec2 = @{ utc = 'x'; phase = 'cutover'; status = 'MOVED' } | ConvertTo-Json -Compress
        Set-Content -LiteralPath $journal -Value ($rec1 + "`n" + $rec2 + "`n") -Encoding ascii
        if (Test-Path -LiteralPath $install) { throw 'precondition: install should be absent' }
        $rec = Invoke-Script 'upgrade.ps1' @('-Recover', $tx)
        if (-not (Test-Path -LiteralPath (Join-Path $install 'install-manifest.json'))) {
            throw "recover did not restore the install (exit $($rec.Code)): $($rec.Text)"
        }
        if (Test-Path -LiteralPath $backup) { throw 'recover left the backup behind instead of moving it back' }
    }

    # ---- upgrade: refuses a transaction root that overlaps the destination (F-048) -----------
    Check 'upgrade: refuses -TransactionRoot inside -Dest (canonical overlap)' {
        $install = Join-Path $root 'ov-install'
        New-Item -ItemType Directory -Path $install -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $install 'install-manifest.json') -Value '{"schema":"sovereign.install-manifest.v1"}' -NoNewline -Encoding ascii
        Set-Content -LiteralPath (Join-Path $install 'VERSION.json') -Value '{"version":"9.9.9"}' -NoNewline -Encoding ascii
        $inside = Join-Path $install 'sub-tx'
        $u = Invoke-Script 'upgrade.ps1' @('-Dest', $install, '-Artifact', (Join-Path $root 'nope.zip'), '-TransactionRoot', $inside)
        if ($u.Code -eq 0) { throw 'upgrade should have refused an overlapping transaction root' }
        if ($u.Text -notmatch 'overlap') { throw "expected an overlap refusal, got: $($u.Text)" }
    }

}
finally {
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
    $env:SOVEREIGN_STATE_TX_LOCK = $null
}

Write-Output ''
if ($failures.Count -gt 0) {
    Write-Output "lifecycle P2: $($failures.Count) FAILURE(S)"
    $failures | ForEach-Object { Write-Output "  - $_" }
    exit 1
}
Write-Output 'lifecycle P2: all checks passed (F-043, F-047, F-048, F-049, state lock)'
exit 0
