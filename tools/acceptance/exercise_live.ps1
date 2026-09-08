[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InstallRoot,
    [Parameter(Mandatory = $true)][string] $StateRoot,
    [ValidateSet('workflow', 'cancel', 'crash')]
    [string] $Mode = 'workflow',
    [int] $ShellPort = 15180,
    [string] $EvidenceLog
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'http_json.ps1')
$utf8NoBom = [Text.UTF8Encoding]::new($false)
$installRoot = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
$stateRoot = [IO.Path]::GetFullPath($StateRoot).TrimEnd('\')
$env:SOVEREIGN_WORKSPACE_STATE = $stateRoot
$env:PYTHONPATH = ''
$query = 'Using only the supplied project evidence, state which model is configured as the primary reasoner and where runtime state is kept. Cite each fact.'
$ownedPids = New-Object System.Collections.Generic.List[int]

function Get-Listener {
    param([int]$Port)
    return Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Invoke-Db {
    param([string]$Py, [string]$Code, [string[]]$PyArgs)
    $tmpPy = Join-Path $env:TEMP ('sws-accept-db-' + [Guid]::NewGuid().ToString('N') + '.py')
    [IO.File]::WriteAllText($tmpPy, $Code, $utf8NoBom)
    $out = & $Py $tmpPy @PyArgs 2>&1 | Out-String
    $code = $LASTEXITCODE
    Remove-Item -LiteralPath $tmpPy -Force -ErrorAction SilentlyContinue
    if ($code -ne 0) { throw "database probe exited $code : $out" }
    return $out
}

function Wait-Job {
    param([string]$Base, [string]$JobId, [int]$Seconds, [string[]]$Terminal)
    $deadline = [datetime]::UtcNow.AddSeconds($Seconds)
    $job = $null
    while ([datetime]::UtcNow -lt $deadline) {
        $job = Invoke-Json -Method GET -Url "$Base/v1/jobs/$JobId"
        $status = [string]$job.Json.status
        if ($Terminal -contains $status) { return $job }
        Start-Sleep -Milliseconds 500
    }
    throw "job $JobId still $([string]$job.Json.status) after ${Seconds}s"
}

$launcher = Join-Path $installRoot 'Start-Shell.ps1'
if (-not (Test-Path -LiteralPath $launcher)) { Write-Output 'no launcher'; exit 2 }
if (-not (Test-Path -LiteralPath (Join-Path $installRoot 'install-manifest.json'))) {
    Write-Output "not an installed artifact: $installRoot"
    exit 2
}

foreach ($port in @($ShellPort, 5175)) {
    $listener = Get-Listener $port
    if ($listener) {
        Write-Output "port $port already in use (PID $($listener.OwningProcess)); refusing to attach to a non-fixture instance"
        exit 2
    }
}

$psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$logDir = if ($EvidenceLog) { Split-Path -Parent $EvidenceLog } else {
    Join-Path $env:TEMP ('sws-live-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
}
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stdoutLog = Join-Path $logDir "shell-$Mode.out.log"
$stderrLog = Join-Path $logDir "shell-$Mode.err.log"
$proc = $null
try {
    $proc = Start-Process -FilePath $psExe -WorkingDirectory $installRoot -PassThru -NoNewWindow `
        -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $launcher,
                        '-Port', "$ShellPort", '-NoBrowser')
    $ownedPids.Add([int]$proc.Id)
    $info = Wait-Url -Url "http://127.0.0.1:$ShellPort/api/shell-info" -Seconds 90 -Child $proc
    if (-not ($info.Json.version -like 'SWS-UI-001*')) {
        Write-Output "unexpected shell-info: $($info.Text)"
        exit 1
    }
    $html = Invoke-Json -Method GET -Url "http://127.0.0.1:$ShellPort/"
    $nonce = $null
    if ($html.Text -match 'csrf-nonce" content="([^"]+)"') { $nonce = $Matches[1] }
    $origin = "http://127.0.0.1:$ShellPort"
    $csrf = @{ 'Origin' = $origin; 'X-CSRF-Nonce' = $nonce }
    $start = Invoke-Json -Method POST -Url "$origin/api/start" -Body '{"id":"sovereign"}' -Headers $csrf
    if ($start.Code -ne 200) { Write-Output "start sovereign failed $($start.Code) $($start.Text)"; exit 1 }
    $readyDeadline = [datetime]::UtcNow.AddSeconds(90)
    $ready = $false
    $st = $null
    while ([datetime]::UtcNow -lt $readyDeadline) {
        if ($proc.HasExited) { throw "shell exited $($proc.ExitCode) before READY" }
        $st = Invoke-Json -Method GET -Url "$origin/api/state"
        if ($st.Json.modules.sovereign.state -eq 'READY') { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { Write-Output 'sovereign never reached READY'; exit 2 }

    $sov = [string]$st.Json.modules.sovereign.url
    if (-not $sov) { $sov = "http://127.0.0.1:5175/" }
    $sov = $sov.TrimEnd('/')
    $sovUri = [Uri]$sov
    $listen = Get-Listener $sovUri.Port
    if (-not $listen) { Write-Output "no listener on $($sovUri.Port)"; exit 2 }
    $sovOwner = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $listen.OwningProcess)
    if (-not $sovOwner -or -not $sovOwner.CommandLine -or
        -not $sovOwner.CommandLine.ToLower().Contains($installRoot.ToLower())) {
        Write-Output "sovereign listener is not the fixture install at $installRoot"
        exit 2
    }
    $ownedPids.Add([int]$sovOwner.ProcessId)
    Wait-Url -Url "$sov/v1/health" -Seconds 45 | Out-Null
    $py = Join-Path $installRoot 'modules\sovereign\.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $py)) { Write-Output "missing $py"; exit 2 }
    $db = Join-Path $stateRoot 'sovereign\runtime\sovereign.db'

    if ($Mode -eq 'workflow') {
        $sess = Invoke-Json -Method POST -Url "$sov/v1/sessions" -Body '{}'
        $sid = $sess.Json.session.session_id
        if (-not $sid) { Write-Output "no session_id: $($sess.Text)"; exit 1 }
        $body = @{ session_id = $sid; input = $query; route_override = 'QUICK' } | ConvertTo-Json -Compress
        $msg = Invoke-Json -Method POST -Url "$sov/v1/message" -Body $body
        if ($msg.Code -ne 202 -and $msg.Code -ne 200) {
            Write-Output "message submit failed $($msg.Code) $($msg.Text)"
            exit 1
        }
        $jobId = $msg.Json.job_id
        if (-not $jobId) { $jobId = $msg.Json.job.job_id }
        $job = Wait-Job -Base $sov -JobId $jobId -Seconds 180 -Terminal @('completed','rejected','failed','cancelled','interrupted')
        if ([string]$job.Json.status -ne 'completed') {
            Write-Output "workflow job $jobId ended $($job.Json.status) : $($job.Text)"
            exit 1
        }
        $answer = [string]$job.Json.message.content
        if (-not $answer) { Write-Output "completed job $jobId has no message.content"; exit 1 }
        if ($answer -notmatch 'qwen2\.5:3b-instruct') { Write-Output "answer missing primary reasoner: $answer"; exit 1 }
        if ($answer -notmatch 'SovereignWorkspace') { Write-Output "answer missing state location: $answer"; exit 1 }
        if ($answer -notmatch '\[source:[^\]]+\]') { Write-Output "answer missing citations: $answer"; exit 1 }
        if (-not (Test-Path -LiteralPath $db)) { Write-Output "sovereign.db missing at $db"; exit 1 }
        $probe = @"
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
chk = c.execute('PRAGMA integrity_check').fetchone()[0]
if chk != 'ok':
    raise SystemExit('integrity_check=' + chk)
job_id = sys.argv[2]
row = c.execute('select content, status from messages where role=? and job_id=?',
                ('sovereign', job_id)).fetchone()
if not row:
    raise SystemExit('no persisted sovereign message for ' + job_id)
if row[1] != 'accepted':
    raise SystemExit('message status ' + row[1])
if 'qwen2.5:3b-instruct' not in row[0] or 'SovereignWorkspace' not in row[0]:
    raise SystemExit('persisted answer missing required facts')
print('ok')
print('persisted', job_id)
"@
        $dbOut = Invoke-Db $py $probe @($db, $jobId)
        Write-Output "workflow job=$jobId db=$dbOut"
        exit 0
    }

    if ($Mode -eq 'cancel') {
        $sess = Invoke-Json -Method POST -Url "$sov/v1/sessions" -Body '{}'
        $sid = $sess.Json.session.session_id
        $body = @{ session_id = $sid; input = $query; route_override = 'DEEP' } | ConvertTo-Json -Compress
        $msg = Invoke-Json -Method POST -Url "$sov/v1/message" -Body $body
        $jobId = $msg.Json.job_id
        if (-not $jobId) { $jobId = $msg.Json.job.job_id }
        $seenActive = $false
        $activeDeadline = [datetime]::UtcNow.AddSeconds(30)
        while ([datetime]::UtcNow -lt $activeDeadline) {
            $job = Invoke-Json -Method GET -Url "$sov/v1/jobs/$jobId"
            $stj = [string]$job.Json.status
            if ($stj -in @('queued', 'running')) { $seenActive = $true; break }
            if ($stj -in @('completed', 'rejected', 'failed', 'cancelled', 'interrupted')) { break }
            Start-Sleep -Milliseconds 200
        }
        if (-not $seenActive) {
            Write-Output "cancel had no in-progress job (status=$stj)"
            exit 1
        }
        $can = Invoke-Json -Method POST -Url "$sov/v1/jobs/$jobId/cancel" -Body '{}'
        $done = Wait-Job -Base $sov -JobId $jobId -Seconds 60 -Terminal @('cancelled','interrupted','failed','completed','rejected')
        if ([string]$done.Json.status -ne 'cancelled') {
            Write-Output "cancel did not reach cancelled (status=$($done.Json.status))"
            exit 1
        }
        $sess2 = Invoke-Json -Method POST -Url "$sov/v1/sessions" -Body '{}'
        $sid2 = $sess2.Json.session.session_id
        $body2 = @{ session_id = $sid2; input = $query; route_override = 'QUICK' } | ConvertTo-Json -Compress
        $msg2 = Invoke-Json -Method POST -Url "$sov/v1/message" -Body $body2
        $job2 = $msg2.Json.job_id
        if (-not $job2) { $job2 = $msg2.Json.job.job_id }
        $after = Wait-Job -Base $sov -JobId $job2 -Seconds 180 -Terminal @('completed','rejected','failed','cancelled','interrupted')
        if ([string]$after.Json.status -ne 'completed') {
            Write-Output "work after cancel failed: $($after.Json.status)"
            exit 1
        }
        Write-Output "cancelled $jobId then completed $job2"
        exit 0
    }

    if ($Mode -eq 'crash') {
        $sess = Invoke-Json -Method POST -Url "$sov/v1/sessions" -Body '{}'
        $sid = $sess.Json.session.session_id
        $body = @{ session_id = $sid; input = $query; route_override = 'QUICK' } | ConvertTo-Json -Compress
        $msg = Invoke-Json -Method POST -Url "$sov/v1/message" -Body $body
        $jobId = $msg.Json.job_id
        if (-not $jobId) { $jobId = $msg.Json.job.job_id }
        $checkpoint = Wait-Job -Base $sov -JobId $jobId -Seconds 180 -Terminal @('completed','rejected','failed','cancelled','interrupted')
        if ([string]$checkpoint.Json.status -ne 'completed') {
            Write-Output "checkpoint job did not complete: $($checkpoint.Json.status)"
            exit 1
        }
        if (-not (Test-Path -LiteralPath $db)) { Write-Output "no db at checkpoint"; exit 1 }
        $pidToKill = [int]$sovOwner.ProcessId
        Stop-Process -Id $pidToKill -Force
        $ownedPids.Remove($pidToKill) | Out-Null
        Start-Sleep -Seconds 2
        $start2 = Invoke-Json -Method POST -Url "$origin/api/start" -Body '{"id":"sovereign"}' -Headers $csrf
        if ($start2.Code -ne 200) { Write-Output "restart failed $($start2.Code) $($start2.Text)"; exit 1 }
        $up = $false
        $upDeadline = [datetime]::UtcNow.AddSeconds(90)
        while ([datetime]::UtcNow -lt $upDeadline) {
            $st2 = Invoke-Json -Method GET -Url "$origin/api/state"
            if ($st2.Json.modules.sovereign.state -eq 'READY') { $up = $true; break }
            Start-Sleep -Seconds 1
        }
        if (-not $up) { Write-Output 'sovereign did not return to READY after crash'; exit 1 }
        $listen2 = Get-Listener $sovUri.Port
        if ($listen2) { $ownedPids.Add([int]$listen2.OwningProcess) }
        $probe = @"
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
chk = c.execute('PRAGMA integrity_check').fetchone()[0]
if chk != 'ok':
    raise SystemExit('integrity_check=' + chk)
job_id = sys.argv[2]
row = c.execute('select status from messages where role=? and job_id=?',
                ('sovereign', job_id)).fetchone()
if not row:
    raise SystemExit('checkpoint message missing')
stuck = c.execute("select count(*) from jobs where status='running'").fetchone()[0]
if stuck:
    raise SystemExit('stuck running jobs=' + str(stuck))
print('ok')
print('checkpoint', job_id, row[0])
"@
        $dbOut = Invoke-Db $py $probe @($db, $jobId)
        Write-Output "crash-recover pid=$pidToKill db=$dbOut"
        exit 0
    }
}
catch {
    Write-Output $_.Exception.Message
    if (Test-Path -LiteralPath $stdoutLog) {
        Write-Output '--- shell stdout ---'
        Get-Content -LiteralPath $stdoutLog -Tail 40
    }
    if (Test-Path -LiteralPath $stderrLog) {
        Write-Output '--- shell stderr ---'
        Get-Content -LiteralPath $stderrLog -Tail 40
    }
    exit 1
}
finally {
    foreach ($id in @($ownedPids)) {
        try { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue } catch { }
    }
}
