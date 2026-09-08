[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InstallRoot,
    [Parameter(Mandatory = $true)][string] $StateRoot,
    [ValidateSet('workflow', 'cancel', 'crash')]
    [string] $Mode = 'workflow',
    [int] $ShellPort = 15180,
    [int] $SovereignPort = 15175,
    [string] $EvidenceLog
)

$ErrorActionPreference = 'Stop'
$utf8NoBom = [Text.UTF8Encoding]::new($false)
$installRoot = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
$stateRoot = [IO.Path]::GetFullPath($StateRoot).TrimEnd('\')
$env:SOVEREIGN_WORKSPACE_STATE = $stateRoot
$env:PYTHONPATH = ''
$query = 'Using only the supplied project evidence, state which model is configured as the primary reasoner and where runtime state is kept. Cite each fact.'

function Invoke-Json {
    param([string]$Method, [string]$Url, [string]$Body, [hashtable]$Headers)
    $req = [Net.HttpWebRequest]::Create($Url)
    $req.Method = $Method
    $req.Timeout = 30000
    $req.Host = ([Uri]$Url).Authority
    if ($Headers) { foreach ($k in $Headers.Keys) { $req.Headers[$k] = $Headers[$k] } }
    if ($null -ne $Body) {
        $bytes = $utf8NoBom.GetBytes($Body)
        $req.ContentType = 'application/json'
        $req.ContentLength = $bytes.Length
        $s = $req.GetRequestStream()
        try { $s.Write($bytes, 0, $bytes.Length) } finally { $s.Dispose() }
    }
    try {
        $resp = $req.GetResponse()
    }
    catch [Net.WebException] {
        $resp = $_.Exception.Response
        if (-not $resp) { throw }
    }
    $code = [int]$resp.StatusCode
    $reader = New-Object IO.StreamReader($resp.GetResponseStream())
    try { $text = $reader.ReadToEnd() } finally { $reader.Dispose(); $resp.Dispose() }
    return @{ Code = $code; Text = $text; Json = $(try { $text | ConvertFrom-Json } catch { $null }) }
}

function Wait-Url {
    param([string]$Url, [int]$Seconds = 60)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-Json 'GET' $Url $null $null
            if ($r.Code -ge 200 -and $r.Code -lt 300) { return $r }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    throw "timed out waiting for $Url"
}

function Get-Listener {
    param([int]$Port)
    return Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

$launcher = Join-Path $installRoot 'Start-Shell.ps1'
if (-not (Test-Path -LiteralPath $launcher)) { Write-Output 'no launcher'; exit 2 }

foreach ($port in @($ShellPort, 5175, $SovereignPort)) {
    $listener = Get-Listener $port
    if ($listener) {
        Write-Output "port $port already in use (PID $($listener.OwningProcess)); refusing to attach to a non-fixture instance"
        exit 2
    }
}

$psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$proc = $null
try {
    $proc = Start-Process -FilePath $psExe -WorkingDirectory $installRoot -PassThru -WindowStyle Hidden `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $launcher,
                        '-Port', "$ShellPort", '-NoBrowser')
    $info = Wait-Url "http://127.0.0.1:$ShellPort/api/shell-info" 90
    if (-not ($info.Json.version -like 'SWS-UI-001*')) {
        Write-Output "unexpected shell-info: $($info.Text)"
        exit 1
    }
    $html = Invoke-Json 'GET' "http://127.0.0.1:$ShellPort/" $null $null
    $nonce = $null
    if ($html.Text -match 'csrf-nonce" content="([^"]+)"') { $nonce = $Matches[1] }
    $origin = "http://127.0.0.1:$ShellPort"
    $csrf = @{ 'Origin' = $origin; 'X-CSRF-Nonce' = $nonce }
    $start = Invoke-Json 'POST' "$origin/api/start" '{"id":"sovereign"}' $csrf
    if ($start.Code -ne 200) { Write-Output "start sovereign failed $($start.Code) $($start.Text)"; exit 1 }
    $deadline = (Get-Date).AddSeconds(90)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        $st = Invoke-Json 'GET' "$origin/api/state" $null $null
        if ($st.Json.modules.sovereign.state -eq 'READY') { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { Write-Output 'sovereign never reached READY'; exit 2 }

    $sov = [string]$st.Json.modules.sovereign.url
    if (-not $sov) { $sov = "http://127.0.0.1:5175/" }
    $sov = $sov.TrimEnd('/')
    $sovUri = [Uri]$sov
    $sovOwner = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f ((Get-Listener $sovUri.Port).OwningProcess)) -ErrorAction SilentlyContinue
    if (-not $sovOwner -or -not $sovOwner.CommandLine -or
        -not $sovOwner.CommandLine.ToLower().Contains($installRoot.ToLower())) {
        Write-Output "sovereign listener is not the fixture install at $installRoot"
        exit 2
    }
    Wait-Url "$sov/v1/health" 45 | Out-Null

    if ($Mode -eq 'workflow') {
        $sess = Invoke-Json 'POST' "$sov/v1/sessions" '{}' $null
        $sid = $sess.Json.session.session_id
        $body = @{ session_id = $sid; input = $query; route_override = 'QUICK' } | ConvertTo-Json -Compress
        $msg = Invoke-Json 'POST' "$sov/v1/message" $body $null
        if ($msg.Code -ne 202 -and $msg.Code -ne 200) {
            Write-Output "message submit failed $($msg.Code) $($msg.Text)"
            exit 1
        }
        $jobId = $msg.Json.job_id
        if (-not $jobId) { $jobId = $msg.Json.job.job_id }
        $jobDeadline = (Get-Date).AddSeconds(180)
        $job = $null
        while ((Get-Date) -lt $jobDeadline) {
            $job = Invoke-Json 'GET' "$sov/v1/jobs/$jobId" $null $null
            $status = [string]$job.Json.status
            if ($status -in @('completed', 'rejected', 'failed', 'cancelled', 'interrupted')) { break }
            Start-Sleep -Seconds 1
        }
        $db = Join-Path $stateRoot 'sovereign\runtime\sovereign.db'
        if (-not (Test-Path -LiteralPath $db)) {
            Write-Output "sovereign.db missing at $db"
            exit 1
        }
        $py = Join-Path $installRoot 'modules\sovereign\.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $py)) { $py = 'py' }
        $check = @"
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
print(c.execute('PRAGMA integrity_check').fetchone()[0])
rows = c.execute("select content, status from messages where role='sovereign'").fetchall()
print('rows', len(rows))
if rows:
    print(rows[0][1])
"@
        $tmpPy = Join-Path $env:TEMP ('sws-accept-db-' + [Guid]::NewGuid().ToString('N') + '.py')
        [IO.File]::WriteAllText($tmpPy, $check, $utf8NoBom)
        $dbOut = & $py $tmpPy $db
        Remove-Item -LiteralPath $tmpPy -Force -ErrorAction SilentlyContinue
        if ($dbOut -notmatch '^ok') { Write-Output "integrity_check failed: $dbOut"; exit 1 }
        Write-Output "workflow job=$jobId db=$dbOut"
        exit 0
    }

    if ($Mode -eq 'cancel') {
        $sess = Invoke-Json 'POST' "$sov/v1/sessions" '{}' $null
        $sid = $sess.Json.session.session_id
        $body = @{ session_id = $sid; input = $query; route_override = 'DEEP' } | ConvertTo-Json -Compress
        $msg = Invoke-Json 'POST' "$sov/v1/message" $body $null
        $jobId = $msg.Json.job_id
        if (-not $jobId) { $jobId = $msg.Json.job.job_id }
        Start-Sleep -Seconds 2
        $can = Invoke-Json 'POST' "$sov/v1/jobs/$jobId/cancel" '{}' $null
        $deadline = (Get-Date).AddSeconds(60)
        $status = ''
        while ((Get-Date) -lt $deadline) {
            $job = Invoke-Json 'GET' "$sov/v1/jobs/$jobId" $null $null
            $status = [string]$job.Json.status
            if ($status -in @('cancelled', 'interrupted', 'failed', 'completed', 'rejected')) { break }
            Start-Sleep -Milliseconds 500
        }
        if ($status -ne 'cancelled') {
            Write-Output "cancel did not reach cancelled (status=$status)"
            exit 1
        }
        Write-Output "cancelled $jobId"
        exit 0
    }

    if ($Mode -eq 'crash') {
        $owning = Get-CimInstance Win32_Process | Where-Object {
            $_.CommandLine -and $_.CommandLine -match 'sovereign_product\.server' -and
            $_.CommandLine.ToLower().Contains($installRoot.ToLower())
        } | Select-Object -First 1
        if (-not $owning) { Write-Output 'no owned sovereign server process'; exit 2 }
        $pidToKill = [int]$owning.ProcessId
        Stop-Process -Id $pidToKill -Force
        Start-Sleep -Seconds 2
        $start = Invoke-Json 'POST' "$origin/api/start" '{"id":"sovereign"}' $csrf
        $deadline = (Get-Date).AddSeconds(90)
        $db = Join-Path $stateRoot 'sovereign\runtime\sovereign.db'
        $py = Join-Path $installRoot 'modules\sovereign\.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $py)) { $py = 'py' }
        $check = @"
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
print(c.execute('PRAGMA integrity_check').fetchone()[0])
stuck = c.execute("select count(*) from jobs where status='running'").fetchone()[0]
print('stuck', stuck)
"@
        $tmpPy = Join-Path $env:TEMP ('sws-accept-crash-' + [Guid]::NewGuid().ToString('N') + '.py')
        [IO.File]::WriteAllText($tmpPy, $check, $utf8NoBom)
        if (Test-Path -LiteralPath $db) {
            $dbOut = & $py $tmpPy $db
            Remove-Item -LiteralPath $tmpPy -Force -ErrorAction SilentlyContinue
            if ($dbOut -notmatch '^ok') { Write-Output "integrity after crash failed: $dbOut"; exit 1 }
            if ($dbOut -match 'stuck ([1-9])') { Write-Output "running jobs remain after crash: $dbOut"; exit 1 }
        }
        Write-Output "crash-recover pid=$pidToKill"
        exit 0
    }
}
catch {
    Write-Output $_.Exception.Message
    exit 1
}
finally {
    if ($proc -and -not $proc.HasExited) {
        try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch { }
    }
    Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -match "Port $ShellPort" -or
            ($_.CommandLine -match 'sovereign_product\.server' -and
             $_.CommandLine.ToLower().Contains($installRoot.ToLower()))
        )
    } | ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch { }
    }
}
