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
    #
    # NOTE THE ORDER. The workflow numbers uninstall as 8 and the non-writable launch as 9, but
    # step 8 REMOVES the installation that step 9 needs. Running them in numeric order left step 9
    # BLOCKED with "no installation present" - observed on the first execution of this harness.
    # The steps keep their numbers, which are the workflow's, and 9 is executed before 8.
    [string[]] $Steps = @('1', '2', '3', '4', '5', '6', '7', '9', '8')
)

# SWS-CORRECTIVE-01 workstream 4 - the acceptance sequence, executed and recorded.
#
# This harness runs the sequence in docs\ACCEPTANCE-WORKFLOW.md against a DISPOSABLE install and
# a DISPOSABLE state root. It refuses to touch the operator's real installation or state: the
# state root must be under the system temp directory, checked on the CANONICAL path after
# resolving reparse points. A junction under temp that targets operator data is refused.
#
# Step 3 drives the frozen HTTP workflow (shell + SOVEREIGN APIs). Automated UI operation is
# legitimate end-to-end evidence; human usability acceptance stays separate.
#
# Every step writes a JSON record with the environment label, the command, start and end time,
# the real exit code, a PASS/FAIL/SKIP/BLOCKED verdict, and where its evidence went. A step that
# cannot run is BLOCKED with the exact missing resource. Nothing is ever converted to a PASS.

$ErrorActionPreference = 'Stop'
$utf8NoBom = [Text.UTF8Encoding]::new($false)
. (Join-Path $PSScriptRoot '..\release\path_guard.ps1')

$installRoot = Get-CanonicalPath $InstallRoot
$stateRoot = Get-CanonicalPath $StateRoot
$evidenceDir = Get-CanonicalPath $EvidenceDir
$artifactPath = [IO.Path]::GetFullPath($Artifact)

# --- refuse to operate on anything that is not disposable ------------------------------------
$tempRoot = Get-CanonicalPath ([IO.Path]::GetTempPath())
foreach ($guard in @(@{ p = $installRoot; n = 'InstallRoot' }, @{ p = $stateRoot; n = 'StateRoot' })) {
    if ($guard.p -eq [IO.Path]::GetPathRoot($guard.p)) {
        throw "$($guard.n) may not be a filesystem root: $($guard.p)"
    }
    if (-not (Test-CanonicalContained -Root $tempRoot -Candidate $guard.p)) {
        throw ("$($guard.n) must live under the system temp directory after canonical " +
               "resolution so this harness cannot back up, restore over, upgrade or purge " +
               "anything the operator relies on. Given: $($guard.p); temp: $tempRoot")
    }
    if (Test-Path -LiteralPath $guard.p) {
        if (Test-TreeContainsReparsePoint $guard.p) {
            throw "$($guard.n) contains a reparse point; refusing recursive delete/move/ACL: $($guard.p)"
        }
    }
}
$defaultState = Get-CanonicalPath (Join-Path $env:LOCALAPPDATA 'SovereignWorkspace')
if ($stateRoot.Equals($defaultState, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to run acceptance against the operator's real state root: $stateRoot"
}

New-Item -ItemType Directory -Path $evidenceDir -Force | Out-Null
$recordPath = Join-Path $evidenceDir 'acceptance-record.jsonl'
$logDir = Join-Path $evidenceDir 'logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$runId = [Guid]::NewGuid().ToString('N').Substring(0, 12)
$checkoutSha = (& git -C $repoRoot rev-parse HEAD).Trim()
$candidate = $checkoutSha
$artifactHash = if (Test-Path -LiteralPath $artifactPath) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $artifactPath).Hash.ToLowerInvariant()
} else { $null }
# Checkout SHA is NOT proof the zip was built from that SHA.
$artifactBuiltFromSha = $null
$buildManifestPath = Join-Path (Split-Path -Parent $artifactPath) 'release-build-manifest.json'
if (Test-Path -LiteralPath $buildManifestPath -PathType Leaf) {
    $buildManifest = Get-Content -Raw -LiteralPath $buildManifestPath | ConvertFrom-Json
    $named = @($buildManifest.artifacts | Where-Object { $_.name -eq [IO.Path]::GetFileName($artifactPath) })
    if ($named.Count -eq 1 -and $named[0].sha256 -eq $artifactHash) {
        $artifactBuiltFromSha = [string]$named[0].cut_from
        if (-not $artifactBuiltFromSha) { $artifactBuiltFromSha = [string]$buildManifest.source_commit }
    }
}

function Write-Record {
    param([string]$Step, [string]$Name, [string]$Verdict, [string]$Reason,
          $ExitCode, [string]$Command, [string]$Evidence, [datetime]$Started)
    $record = [ordered]@{
        workflow      = 'SWS-ACCEPT-01'
        run_id        = $runId
        environment   = $Environment
        step          = $Step
        name          = $Name
        checkout_sha  = $checkoutSha
        candidate_sha = $candidate
        artifact      = [IO.Path]::GetFileName($artifactPath)
        artifact_sha256 = $artifactHash
        artifact_built_from_sha = $artifactBuiltFromSha
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
        # F-080. Always install shortcuts into a FIXTURE directory, never the operator's real
        # Desktop/Start Menu. The harness claims it "refuses to touch the operator's real
        # installation or state"; a bare install used to overwrite the real launcher shortcut, and
        # step 8's uninstall then deleted it. A fixture -TargetDir keeps the whole shortcut
        # lifecycle inside the acceptance sandbox.
        $shortcutFixture = Join-Path (Split-Path -Parent $installRoot) 'acceptance-shortcuts'
        $r = Invoke-Child (Join-Path $release 'install.ps1') `
            @('-Dest', $installRoot, '-Artifact', $artifactPath, '-TargetDir', $shortcutFixture) 'step1-install'
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

# --- step 3: frozen HTTP workflow --------------------------------------------------------------
if ($Steps -contains '3') {
    $started = Get-Date
    $launcher = Join-Path $installRoot 'Start-Shell.ps1'
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        Write-Record '3' 'frozen useful workflow through the assembled UI' 'BLOCKED' `
            'no installation to launch' $null '' '' $started
    }
    else {
        $wf = Join-Path $PSScriptRoot 'exercise_live.ps1'
        $r = Invoke-Child $wf @(
            '-InstallRoot', $installRoot,
            '-StateRoot', $stateRoot,
            '-Mode', 'workflow',
            '-EvidenceLog', (Join-Path $logDir 'step3-workflow.log')
        ) 'step3-workflow'
        $verdict = if ($r.ExitCode -eq 0) { 'PASS' } elseif ($r.ExitCode -eq 2) { 'BLOCKED' } else { 'FAIL' }
        $reason = ''
        if ($verdict -ne 'PASS') {
            $reason = "exercise_live.ps1 -Mode workflow exited $($r.ExitCode)"
        }
        Write-Record '3' 'HTTP integration of frozen workflow (not assembled UI)' $verdict $reason `
            $r.ExitCode 'exercise_live.ps1 -Mode workflow' $r.Log $started
    }
}

# --- step 4/5: cancellation and crash recovery -------------------------------------------------
foreach ($pending in @(
    @{ n = '4'; t = 'cancel real in-progress work, then restart and complete another task'; mode = 'cancel' },
    @{ n = '5'; t = 'crash an owned instance at a checkpoint and recover'; mode = 'crash' })) {
    if ($Steps -contains $pending.n) {
        $started = Get-Date
        if (-not (Test-Path -LiteralPath (Join-Path $installRoot 'Start-Shell.ps1'))) {
            Write-Record $pending.n $pending.t 'BLOCKED' 'no installation to exercise' $null '' '' $started
        }
        else {
            $r = Invoke-Child (Join-Path $PSScriptRoot 'exercise_live.ps1') @(
                '-InstallRoot', $installRoot, '-StateRoot', $stateRoot, '-Mode', $pending.mode,
                '-EvidenceLog', (Join-Path $logDir ("step$($pending.n)-$($pending.mode).log"))
            ) ("step$($pending.n)-$($pending.mode)")
            $verdict = if ($r.ExitCode -eq 0) { 'PASS' } elseif ($r.ExitCode -eq 2) { 'BLOCKED' } else { 'FAIL' }
            Write-Record $pending.n $pending.t $verdict `
                $(if ($verdict -ne 'PASS') { "exercise_live.ps1 -Mode $($pending.mode) exited $($r.ExitCode)" } else { '' }) `
                $r.ExitCode "exercise_live.ps1 -Mode $($pending.mode)" $r.Log $started
        }
    }
}

# --- step 6: back up, verify, restore into a SEPARATE state location ---------------------------
if ($Steps -contains '6') {
    $started = Get-Date
    $dbLive = Join-Path $stateRoot 'sovereign\runtime\sovereign.db'
    $pyLive = Join-Path $installRoot 'modules\sovereign\.venv\Scripts\python.exe'
    $ok = $false
    $reason = ''
    $code = $null
    $restoreRoot = $null
    if (-not (Test-Path -LiteralPath $dbLive -PathType Leaf)) {
        $reason = 'no sovereign.db from a completed workflow; a marker file is not sufficient'
    }
    elseif (-not (Test-Path -LiteralPath $pyLive -PathType Leaf)) {
        $reason = "missing $pyLive"
    }
    else {
        $capturePy = Join-Path $env:TEMP ('sws-accept-cap-' + [Guid]::NewGuid().ToString('N') + '.py')
        [IO.File]::WriteAllText($capturePy, @'
import hashlib, sqlite3, sys
c = sqlite3.connect(sys.argv[1])
chk = c.execute("PRAGMA integrity_check").fetchone()[0]
if chk != "ok":
    raise SystemExit("integrity_check=" + chk)
row = c.execute(
    "select job_id, content from messages where role='sovereign' and status='accepted' "
    "and content like '%qwen2.5:3b-instruct%' and content like '%SovereignWorkspace%' "
    "order by created_at desc"
).fetchone()
if not row:
    raise SystemExit("no accepted useful-workflow answer in live state")
print(row[0])
print(hashlib.sha256(row[1].encode("utf-8")).hexdigest())
'@, $utf8NoBom)
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $cap = & $pyLive $capturePy $dbLive 2>&1 | Out-String
        $capCode = if ($null -eq $LASTEXITCODE) { 1 } else { [int]$LASTEXITCODE }
        $ErrorActionPreference = $prevEap
        Remove-Item -LiteralPath $capturePy -Force -ErrorAction SilentlyContinue
        if ($capCode -ne 0) {
            $reason = "live database probe failed: $cap"
        }
        else {
            $capLines = @($cap.Trim().Split("`n") | ForEach-Object { $_.Trim() } | Where-Object { $_ })
            $liveJob = $capLines[0]
            $liveHash = $capLines[1]
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
            $code = $r.ExitCode
            $restoredDb = Join-Path $restoreRoot 'sovereign\runtime\sovereign.db'
            if ($b.ExitCode -ne 0) { $reason = "backup exited $($b.ExitCode)" }
            elseif ($r.ExitCode -ne 0) { $reason = "restore exited $($r.ExitCode)" }
            elseif (-not (Test-Path -LiteralPath $restoredDb -PathType Leaf)) {
                $reason = 'restored state has no sovereign.db'
            }
            else {
                $checkPy = Join-Path $env:TEMP ('sws-accept-rst-' + [Guid]::NewGuid().ToString('N') + '.py')
                [IO.File]::WriteAllText($checkPy, @'
import hashlib, sqlite3, sys
c = sqlite3.connect(sys.argv[1])
chk = c.execute("PRAGMA integrity_check").fetchone()[0]
if chk != "ok":
    raise SystemExit("integrity_check=" + chk)
job_id, expect = sys.argv[2], sys.argv[3]
row = c.execute(
    "select content, status from messages where role='sovereign' and job_id=?",
    (job_id,),
).fetchone()
if not row:
    raise SystemExit("restored job missing")
if row[1] != "accepted":
    raise SystemExit("restored message status " + row[1])
got = hashlib.sha256(row[0].encode("utf-8")).hexdigest()
if got != expect:
    raise SystemExit("restored answer hash %s != %s" % (got, expect))
if "qwen2.5:3b-instruct" not in row[0] or "SovereignWorkspace" not in row[0]:
    raise SystemExit("restored answer missing required facts")
print("ok")
'@, $utf8NoBom)
                $prevEap2 = $ErrorActionPreference
                $ErrorActionPreference = 'Continue'
                $chkOut = & $pyLive $checkPy $restoredDb $liveJob $liveHash 2>&1 | Out-String
                $chkCode = if ($null -eq $LASTEXITCODE) { 1 } else { [int]$LASTEXITCODE }
                $ErrorActionPreference = $prevEap2
                Remove-Item -LiteralPath $checkPy -Force -ErrorAction SilentlyContinue
                if ($chkCode -ne 0) {
                    $reason = "restored database check failed: $chkOut"
                }
                else { $ok = $true }
            }
        }
    }
    Write-Record '6' 'back up, verify, restore meaningful application state' `
        $(if ($ok) { 'PASS' } else { 'FAIL' }) $reason $code `
        'backup_state.ps1 + restore_state.ps1 + sqlite reopen' $evidenceDir $started
    if ($restoreRoot -and (Test-Path -LiteralPath $restoreRoot)) {
        Remove-Item -LiteralPath $restoreRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
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
        if ($verdict -eq 'PASS') {
            $startedUp = Get-Date
            $u = Invoke-Child (Join-Path $release 'upgrade.ps1') `
                @('-Dest', $installRoot, '-Artifact', $artifactPath) 'step7-upgrade'
            $still = Test-Path -LiteralPath (Join-Path $installRoot 'install-manifest.json')
            $upOk = ($u.ExitCode -eq 0 -and $still)
            $upReason = if (-not $still) { 'successful upgrade removed the installation' }
                        elseif ($u.ExitCode -ne 0) { "upgrade.ps1 exited $($u.ExitCode)" }
                        else { '' }
            Write-Record '7' 'successful upgrade after rollback recovery' `
                $(if ($upOk) { 'PASS' } else { 'FAIL' }) $upReason `
                $u.ExitCode 'upgrade.ps1' $u.Log $startedUp
            if ($upOk) {
                $startedWf = Get-Date
                $wf = Invoke-Child (Join-Path $PSScriptRoot 'exercise_live.ps1') @(
                    '-InstallRoot', $installRoot, '-StateRoot', $stateRoot,
                    '-Mode', 'workflow', '-ShellPort', '15182',
                    '-EvidenceLog', (Join-Path $logDir 'step7-upgrade-workflow.log')
                ) 'step7-upgrade-workflow'
                $wfOk = ($wf.ExitCode -eq 0)
                Write-Record '7' 'useful workflow after successful upgrade' `
                    $(if ($wfOk) { 'PASS' } else { 'FAIL' }) `
                    $(if ($wfOk) { '' } else { "post-upgrade workflow exited $($wf.ExitCode)" }) `
                    $wf.ExitCode 'exercise_live.ps1 after upgrade' $wf.Log $startedWf
            }
        }
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
        $originalSddl = (Get-Acl -LiteralPath $installRoot).GetSecurityDescriptorSddlForm('All')
        $me = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $deny = New-Object Security.AccessControl.FileSystemAccessRule(
            $me, 'Write', 'ContainerInherit,ObjectInherit', 'None', 'Deny')
        $ok = $false; $reason = ''; $code = $null
        try {
            $acl = Get-Acl -LiteralPath $installRoot
            $acl.AddAccessRule($deny)
            Set-Acl -LiteralPath $installRoot -AclObject $acl
            $probe = Join-Path $installRoot ('.accept-write-probe-' + [Guid]::NewGuid().ToString('N'))
            $writeDenied = $false
            try {
                [IO.File]::WriteAllText($probe, 'should-fail')
            }
            catch { $writeDenied = $true }
            if (Test-Path -LiteralPath $probe) {
                Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
            }
            if (-not $writeDenied) {
                $reason = 'negative control failed: write succeeded under the deny-Write ACL'
            }
            else {
                $r = Invoke-Child (Join-Path $PSScriptRoot 'exercise_live.ps1') @(
                    '-InstallRoot', $installRoot, '-StateRoot', $stateRoot,
                    '-Mode', 'workflow', '-ShellPort', '15181',
                    '-EvidenceLog', (Join-Path $logDir 'step9-readonly.log')
                ) 'step9-readonly'
                $code = $r.ExitCode
                $ok = ($r.ExitCode -eq 0)
                if (-not $ok) { $reason = "live launch under deny-Write failed (exit $($r.ExitCode))" }
            }
        }
        catch { $reason = $_.Exception.Message }
        finally {
            try {
                $restore = Get-Acl -LiteralPath $installRoot
                $restore.SetSecurityDescriptorSddlForm($originalSddl)
                Set-Acl -LiteralPath $installRoot -AclObject $restore
            }
            catch {
                Write-Host "WARNING: failed to restore original ACL on $installRoot : $($_.Exception.Message)" -ForegroundColor Red
            }
        }
        Write-Record '9' 'launch with a non-writable installation directory' `
            $(if ($ok) { 'PASS' } else { 'FAIL' }) $reason $code 'exercise_live.ps1 under deny-Write' $logDir $started
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
        $hashBefore = @{}
        Get-ChildItem -LiteralPath $stateRoot -Force -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
            $rel = $_.FullName.Substring($stateRoot.Length).TrimStart('\')
            $hashBefore[$rel] = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash
        }
        $r = Invoke-Child (Join-Path $release 'uninstall.ps1') @('-Dest', $installRoot) 'step8-uninstall'
        $hashAfter = @{}
        Get-ChildItem -LiteralPath $stateRoot -Force -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
            $rel = $_.FullName.Substring($stateRoot.Length).TrimStart('\')
            $hashAfter[$rel] = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash
        }
        $missing = @($hashBefore.Keys | Where-Object { -not $hashAfter.ContainsKey($_) })
        $changed = @($hashBefore.Keys | Where-Object { $hashAfter.ContainsKey($_) -and $hashAfter[$_] -ne $hashBefore[$_] })
        $verdict = if ($r.ExitCode -eq 0 -and $missing.Count -eq 0 -and $changed.Count -eq 0) { 'PASS' } else { 'FAIL' }
        $reason = if ($r.ExitCode -ne 0) { "uninstall exited $($r.ExitCode)" }
                  elseif ($missing.Count -gt 0 -or $changed.Count -gt 0) {
                      "uninstall changed state hashes: missing=$($missing.Count) changed=$($changed.Count)"
                  } else { '' }
        Write-Record '8' 'uninstall, preserving state by default' $verdict $reason `
            $r.ExitCode 'uninstall.ps1' $r.Log $started
    }
}

# --- summary --------------------------------------------------------------------------------------
Write-Host ""
Write-Host "  record: $recordPath" -ForegroundColor Cyan
$records = @(Get-Content -LiteralPath $recordPath | ForEach-Object { $_ | ConvertFrom-Json } |
    Where-Object { $_.run_id -eq $runId })
$counts = $records | Group-Object verdict | ForEach-Object { "$($_.Name)=$($_.Count)" }
Write-Host ("  {0}" -f ($counts -join '  '))
Write-Host ""
if ($Environment -ne 'CLEAN') {
    Write-Host "  ACCEPTANCE GATE D: NOT SATISFIED - this was a $Environment run." -ForegroundColor Yellow
    Write-Host "  Gate D requires a fresh Windows VM or clean host." -ForegroundColor Yellow
    Write-Host ""
}
$fails = @($records | Where-Object { $_.verdict -eq 'FAIL' })
$blocked = @($records | Where-Object { $_.verdict -eq 'BLOCKED' })
if ($fails.Count -gt 0) { exit 1 }
if ($blocked.Count -gt 0) {
    Write-Host "  RUN INCOMPLETE: $($blocked.Count) required step(s) BLOCKED. Exit 0 is not completion." -ForegroundColor Yellow
    exit 2
}
exit 0
