[CmdletBinding()]
param(
    # Where the candidate is installed for this run. MUST be a disposable path.
    [Parameter(Mandatory = $true)]
    [string] $InstallRoot,

    # The install artifact to accept.
    [Parameter(Mandatory = $true)]
    [string] $Artifact,

    # The state root this run uses. MUST be disposable: this harness backs it up, restores over
    # it and purges it. It is never allowed to be the operator's real state root.
    [Parameter(Mandatory = $true)]
    [string] $StateRoot,

    # Where the evidence for this run is written.
    [Parameter(Mandatory = $true)]
    [string] $EvidenceDir,

    # FIXTURE (a temporary install on the development host) or CLEAN (a fresh VM/clean host).
    # A FIXTURE result proves the mechanism; it does NOT satisfy acceptance gate D, and this
    # harness stamps the distinction into every record so the two can never be confused.
    [ValidateSet('FIXTURE', 'CLEAN')]
    [string] $Environment = 'FIXTURE',

    # Steps to run. Default is the whole sequence from docs/ACCEPTANCE-WORKFLOW.md.
    [string[]] $Steps = @('1', '2', '4', '5', '6', '7', '8', '9')
)

# SWS-CORRECTIVE-01 workstream 4 - the acceptance sequence, executed and recorded.
#
# This harness runs the sequence in docs\ACCEPTANCE-WORKFLOW.md against a DISPOSABLE install and
# a DISPOSABLE state root. It refuses to touch the operator's real installation or state: the
# state root must be under the system temp directory or explicitly marked disposable, and the
# check is on the CANONICAL resolved path, not the string it was given.
#
# Step 3 - the frozen operator workflow through the assembled UI - is not automated here. It
# needs a human at the browser, and a harness that clicked through it would be proving that the
# harness can click, not that an operator can work. The runbook records how to perform it and
# what to capture; this script performs every step that can be performed without a person.
#
# Every step writes a JSON record with the environment label, the command, start and end time,
# the real exit code, a PASS/FAIL/SKIP/BLOCKED verdict, and where its evidence went. A step that
# cannot run is BLOCKED with the exact missing resource. Nothing is ever converted to a PASS.

$ErrorActionPreference = 'Stop'
$utf8NoBom = [Text.UTF8Encoding]::new($false)

$installRoot = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
$stateRoot = [IO.Path]::GetFullPath($StateRoot).TrimEnd('\')
$evidenceDir = [IO.Path]::GetFullPath($EvidenceDir).TrimEnd('\')
$artifactPath = [IO.Path]::GetFullPath($Artifact)

# --- refuse to operate on anything that is not disposable ------------------------------------
$tempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
foreach ($guard in @(@{ p = $installRoot; n = 'InstallRoot' }, @{ p = $stateRoot; n = 'StateRoot' })) {
    if ($guard.p -eq [IO.Path]::GetPathRoot($guard.p)) {
        throw "$($guard.n) may not be a filesystem root: $($guard.p)"
    }
    if (-not $guard.p.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw ("$($guard.n) must live under the system temp directory so this harness cannot " +
               "back up, restore over, upgrade or purge anything the operator relies on. " +
               "Given: $($guard.p); required prefix: $tempPrefix")
    }
}
$defaultState = Join-Path $env:LOCALAPPDATA 'SovereignWorkspace'
if ($stateRoot.Equals([IO.Path]::GetFullPath($defaultState).TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to run acceptance against the operator's real state root: $stateRoot"
}

New-Item -ItemType Directory -Path $evidenceDir -Force | Out-Null
$recordPath = Join-Path $evidenceDir 'acceptance-record.jsonl'
$logDir = Join-Path $evidenceDir 'logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$candidate = (& git -C $repoRoot rev-parse HEAD).Trim()
$artifactHash = if (Test-Path -LiteralPath $artifactPath) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $artifactPath).Hash.ToLowerInvariant()
} else { $null }

function Write-Record {
    param([string]$Step, [string]$Name, [string]$Verdict, [string]$Reason,
          $ExitCode, [string]$Command, [string]$Evidence, [datetime]$Started)
    $record = [ordered]@{
        workflow      = 'SWS-ACCEPT-01'
        environment   = $Environment
        step          = $Step
        name          = $Name
        candidate_sha = $candidate
        artifact      = [IO.Path]::GetFileName($artifactPath)
        artifact_sha256 = $artifactHash
        command       = $Command
        started_utc   = $Started.ToUniversalTime().ToString('o')
        ended_utc     = (Get-Date).ToUniversalTime().ToString('o')
        exit_code     = $ExitCode
        verdict       = $Verdict
        reason        = $Reason
        evidence      = $Evidence
    }
    [IO.File]::AppendAllText($recordPath, ($record | ConvertTo-Json -Compress -Depth 6) + "`n", $utf8NoBom)
    $colour = switch ($Verdict) {
        'PASS' { 'Green' } 'FAIL' { 'Red' } 'BLOCKED' { 'Yellow' } default { 'DarkGray' }
    }
    Write-Host ("{0,-8} step {1,-2} {2}" -f $Verdict, $Step, $Name) -ForegroundColor $colour
    if ($Reason) { Write-Host ("           {0}" -f $Reason) -ForegroundColor DarkGray }
}

function Invoke-Child {
    param([string]$Script, [string[]]$ScriptArgs, [string]$LogName)
    $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if (-not (Test-Path -LiteralPath $psExe -PathType Leaf)) { $psExe = 'powershell.exe' }
    $quoted = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $Script + '"'))
    foreach ($a in $ScriptArgs) {
        if ($a -match '[\s"]') { $quoted += '"' + ($a -replace '"', '\"') + '"' } else { $quoted += $a }
    }
    $out = Join-Path $logDir "$LogName.log"
    $err = Join-Path $logDir "$LogName.err.log"
    $p = Start-Process -FilePath $psExe -ArgumentList $quoted -NoNewWindow -Wait -PassThru `
                       -RedirectStandardOutput $out -RedirectStandardError $err
    return @{ ExitCode = [int]$p.ExitCode; Log = $out }
}

$env:SOVEREIGN_WORKSPACE_STATE = $stateRoot
$release = Join-Path $repoRoot 'tools\release'

Write-Host ""
Write-Host "  SWS-ACCEPT-01  environment=$Environment" -ForegroundColor Cyan
Write-Host "  candidate  $candidate"
Write-Host "  artifact   $artifactPath"
Write-Host "  install    $installRoot"
Write-Host "  state      $stateRoot"
Write-Host "  evidence   $evidenceDir"
if ($Environment -eq 'FIXTURE') {
    Write-Host ""
    Write-Host "  FIXTURE run. This proves the mechanism on the development host." -ForegroundColor Yellow
    Write-Host "  It does NOT satisfy acceptance gate D, which requires a fresh machine." -ForegroundColor Yellow
}
Write-Host ""

# --- step 1: install ---------------------------------------------------------------------------
if ($Steps -contains '1') {
    $started = Get-Date
    if (-not (Test-Path -LiteralPath $artifactPath -PathType Leaf)) {
        Write-Record '1' 'install the candidate artifact' 'BLOCKED' `
            "the install artifact does not exist at $artifactPath" $null 'install.ps1' '' $started
    }
    else {
        $r = Invoke-Child (Join-Path $release 'install.ps1') @('-Dest', $installRoot, '-Artifact', $artifactPath) 'step1-install'
        Write-Record '1' 'install the candidate artifact' `
            $(if ($r.ExitCode -eq 0) { 'PASS' } else { 'FAIL' }) `
            $(if ($r.ExitCode -eq 0) { '' } else { "install.ps1 exited $($r.ExitCode)" }) `
            $r.ExitCode 'install.ps1' $r.Log $started
    }
}

# --- step 2: launch and prove source-tree independence -----------------------------------------
if ($Steps -contains '2') {
    $started = Get-Date
    $launcher = Join-Path $installRoot 'Start-Shell.ps1'
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        Write-Record '2' 'launch through the supported entry point' 'BLOCKED' `
            'no installation to launch' $null 'Start-Shell.ps1 -CheckOnly' '' $started
    }
    else {
        # -CheckOnly proves the installed launcher runs from the installed tree and reports its
        # own prerequisites, without starting a module. Step 3 covers the real launch.
        $r = Invoke-Child $launcher @('-CheckOnly') 'step2-launch-checkonly'
        $text = Get-Content -Raw -LiteralPath $r.Log -ErrorAction SilentlyContinue
        $independent = $text -match 'installed artifact'
        $verdict = if ($r.ExitCode -eq 0 -and $independent) { 'PASS' } else { 'FAIL' }
        $reason = if (-not $independent) {
            'the installed launcher did not identify the tree as an installed artifact'
        } elseif ($r.ExitCode -ne 0) { "preflight reported a blocking problem (exit $($r.ExitCode))" } else { '' }
        Write-Record '2' 'launch through the supported entry point' $verdict $reason `
            $r.ExitCode 'Start-Shell.ps1 -CheckOnly' $r.Log $started
    }
}

# --- step 4/5: cancellation and crash recovery -------------------------------------------------
# Both require a live workflow to interrupt, which is step 3's territory. They are recorded as
# BLOCKED here rather than approximated, because cancelling nothing proves nothing.
foreach ($pending in @(
    @{ n = '4'; t = 'cancel real in-progress work, then restart and complete another task' },
    @{ n = '5'; t = 'crash an owned instance at a checkpoint and recover' })) {
    if ($Steps -contains $pending.n) {
        $started = Get-Date
        Write-Record $pending.n $pending.t 'BLOCKED' `
            ('requires the live operator workflow of step 3, which needs a person at the ' +
             'browser; see docs\ACCEPTANCE-WORKFLOW.md and the runbook') $null '' '' $started
    }
}

# --- step 6: back up, verify, restore into a SEPARATE state location ---------------------------
if ($Steps -contains '6') {
    $started = Get-Date
    if (-not (Test-Path -LiteralPath $stateRoot -PathType Container)) {
        New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
    }
    # A marker whose bytes are checked after the round trip - not a file count.
    $marker = Join-Path $stateRoot 'sovereign\acceptance-marker.txt'
    New-Item -ItemType Directory -Path (Split-Path -Parent $marker) -Force | Out-Null
    $payload = "SWS-ACCEPT-01 $candidate " + [Guid]::NewGuid().ToString()
    [IO.File]::WriteAllText($marker, $payload, $utf8NoBom)
    $markerHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $marker).Hash.ToLowerInvariant()

    $archive = Join-Path $evidenceDir 'state-backup.zip'
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    if (Test-Path -LiteralPath "$archive.sha256") { Remove-Item -LiteralPath "$archive.sha256" -Force }
    if (Test-Path -LiteralPath "$archive.inventory.json") { Remove-Item -LiteralPath "$archive.inventory.json" -Force }

    $b = Invoke-Child (Join-Path $release 'backup_state.ps1') @('-StateRoot', $stateRoot, '-Out', $archive) 'step6-backup'
    $restoreRoot = Join-Path ([IO.Path]::GetTempPath()) ("sovereign-accept-restore-" + [Guid]::NewGuid().ToString('N').Substring(0, 8))
    $r = @{ ExitCode = 1; Log = '' }
    if ($b.ExitCode -eq 0) {
        $r = Invoke-Child (Join-Path $release 'restore_state.ps1') @('-Archive', $archive, '-StateRoot', $restoreRoot) 'step6-restore'
    }

    $restoredMarker = Join-Path $restoreRoot 'sovereign\acceptance-marker.txt'
    $ok = $false
    $reason = ''
    if ($b.ExitCode -ne 0) { $reason = "backup exited $($b.ExitCode)" }
    elseif ($r.ExitCode -ne 0) { $reason = "restore exited $($r.ExitCode)" }
    elseif (-not (Test-Path -LiteralPath $restoredMarker -PathType Leaf)) { $reason = 'the marker file was not restored' }
    else {
        $restoredHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $restoredMarker).Hash.ToLowerInvariant()
        if ($restoredHash -ne $markerHash) { $reason = "restored marker hash $restoredHash != $markerHash" }
        else { $ok = $true }
    }
    Write-Record '6' 'back up, verify, restore into a separate state location' `
        $(if ($ok) { 'PASS' } else { 'FAIL' }) $reason $r.ExitCode `
        'backup_state.ps1 + restore_state.ps1' $evidenceDir $started
    if (Test-Path -LiteralPath $restoreRoot) { Remove-Item -LiteralPath $restoreRoot -Recurse -Force -ErrorAction SilentlyContinue }
}

# --- step 7: upgrade, then rollback with an injected candidate failure --------------------------
if ($Steps -contains '7') {
    $started = Get-Date
    if (-not (Test-Path -LiteralPath (Join-Path $installRoot 'install-manifest.json'))) {
        Write-Record '7' 'upgrade the exercised installation, then exercise rollback' 'BLOCKED' `
            'no exercised installation to upgrade' $null 'upgrade.ps1' '' $started
    }
    else {
        # Rollback FIRST, with an injected post-cutover failure: the installation must come back.
        $r = Invoke-Child (Join-Path $release 'upgrade.ps1') `
            @('-Dest', $installRoot, '-Artifact', $artifactPath, '-InjectFailureAt', 'postcheck') 'step7-rollback'
        $survived = Test-Path -LiteralPath (Join-Path $installRoot 'install-manifest.json')
        $verdict = if ($r.ExitCode -eq 4 -and $survived) { 'PASS' } else { 'FAIL' }
        $reason = if (-not $survived) { 'the installation did not survive an injected post-cutover failure' }
                  elseif ($r.ExitCode -ne 4) { "expected exit 4 (failed and rolled back), got $($r.ExitCode)" }
                  else { '' }
        Write-Record '7' 'upgrade rollback with an injected candidate failure' $verdict $reason `
            $r.ExitCode 'upgrade.ps1 -InjectFailureAt postcheck' $r.Log $started
    }
}

# --- step 8: uninstall preserving state by default ----------------------------------------------
if ($Steps -contains '8') {
    $started = Get-Date
    if (-not (Test-Path -LiteralPath (Join-Path $installRoot 'install-manifest.json'))) {
        Write-Record '8' 'uninstall, preserving state by default' 'BLOCKED' `
            'no installation to uninstall' $null 'uninstall.ps1' '' $started
    }
    else {
        $stateBefore = @(Get-ChildItem -LiteralPath $stateRoot -Force -Recurse -File -ErrorAction SilentlyContinue).Count
        $r = Invoke-Child (Join-Path $release 'uninstall.ps1') @('-Dest', $installRoot) 'step8-uninstall'
        $stateAfter = @(Get-ChildItem -LiteralPath $stateRoot -Force -Recurse -File -ErrorAction SilentlyContinue).Count
        $verdict = if ($r.ExitCode -eq 0 -and $stateAfter -eq $stateBefore) { 'PASS' } else { 'FAIL' }
        $reason = if ($stateAfter -ne $stateBefore) {
            "uninstall changed the state root: $stateBefore file(s) before, $stateAfter after"
        } elseif ($r.ExitCode -ne 0) { "uninstall exited $($r.ExitCode)" } else { '' }
        Write-Record '8' 'uninstall, preserving state by default' $verdict $reason `
            $r.ExitCode 'uninstall.ps1' $r.Log $started
    }
}

# --- step 9: non-writable installation ----------------------------------------------------------
if ($Steps -contains '9') {
    $started = Get-Date
    if (-not (Test-Path -LiteralPath $installRoot -PathType Container)) {
        Write-Record '9' 'launch with a non-writable installation directory' 'BLOCKED' `
            'no installation present (step 8 removed it, or step 1 did not run)' $null '' '' $started
    }
    else {
        # Deny write to the current user on the install tree, run the preflight, then restore the
        # ACL. Only this disposable tree is touched.
        $acl = Get-Acl -LiteralPath $installRoot
        $me = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $deny = New-Object Security.AccessControl.FileSystemAccessRule(
            $me, 'Write', 'ContainerInherit,ObjectInherit', 'None', 'Deny')
        $ok = $false; $reason = ''; $code = $null
        try {
            $acl.AddAccessRule($deny)
            Set-Acl -LiteralPath $installRoot -AclObject $acl
            $r = Invoke-Child (Join-Path $installRoot 'Start-Shell.ps1') @('-CheckOnly') 'step9-readonly'
            $code = $r.ExitCode
            $ok = ($r.ExitCode -eq 0)
            if (-not $ok) { $reason = "preflight reported a blocking problem under a non-writable install (exit $($r.ExitCode))" }
        }
        catch { $reason = $_.Exception.Message }
        finally {
            $restore = Get-Acl -LiteralPath $installRoot
            $restore.RemoveAccessRuleAll($deny)
            Set-Acl -LiteralPath $installRoot -AclObject $restore
        }
        Write-Record '9' 'launch with a non-writable installation directory' `
            $(if ($ok) { 'PASS' } else { 'FAIL' }) $reason $code 'Start-Shell.ps1 -CheckOnly' $logDir $started
    }
}

# --- summary --------------------------------------------------------------------------------------
Write-Host ""
Write-Host "  record: $recordPath" -ForegroundColor Cyan
$records = @(Get-Content -LiteralPath $recordPath | ForEach-Object { $_ | ConvertFrom-Json })
$counts = $records | Group-Object verdict | ForEach-Object { "$($_.Name)=$($_.Count)" }
Write-Host ("  {0}" -f ($counts -join '  '))
Write-Host ""
if ($Environment -ne 'CLEAN') {
    Write-Host "  ACCEPTANCE GATE D: NOT SATISFIED - this was a $Environment run." -ForegroundColor Yellow
    Write-Host "  Gate D requires a fresh Windows VM or clean host." -ForegroundColor Yellow
    Write-Host ""
}
if (@($records | Where-Object { $_.verdict -eq 'FAIL' }).Count -gt 0) { exit 1 }
exit 0
