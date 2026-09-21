[CmdletBinding()]
param(
    [string]$Root = $PSScriptRoot,
    [ValidateRange(1, 300)]
    [int]$CancelWaitSeconds = 30
)

$ErrorActionPreference = "Stop"
$rootPath = [System.IO.Path]::GetFullPath($Root)
$markerPath = Join-Path $rootPath ".sovereign-root"
$statePath = Join-Path $rootPath "runtime\service_state.json"

if (
    -not (Test-Path -LiteralPath $markerPath -PathType Leaf) -or
    (Get-Content -LiteralPath $markerPath -Raw).Trim() -ne "SOVEREIGN_ROOT_MARKER=1"
) {
    throw "The selected directory is not a marker-validated SOVEREIGN root: $rootPath"
}
if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    Write-Host "SOVEREIGN is not recorded as running."
    return
}

try {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    if ([int]$state.schema_version -ne 3) {
        throw "schema_version 3 is required for destructive process control"
    }
    if (-not $state.process_started_at) {
        throw "process_started_at is required for PID-reuse protection"
    }
    $servicePid = [int]$state.pid
    $recordedRoot = [System.IO.Path]::GetFullPath([string]$state.root)
} catch {
    throw "The SOVEREIGN service process record is unreadable or unsafe: $($_.Exception.Message). It was retained."
}
if (
    -not [System.StringComparer]::OrdinalIgnoreCase.Equals(
        $recordedRoot,
        $rootPath
    )
) {
    throw "The service process record belongs to a different product root; refusing to stop it."
}

$process = Get-Process -Id $servicePid -ErrorAction SilentlyContinue
if ($null -eq $process) {
    if ($state.launcher_pid -and [int]$state.launcher_pid -ne $servicePid) {
        $staleLauncherPid = [int]$state.launcher_pid
        $staleLauncher = Get-Process `
            -Id $staleLauncherPid `
            -ErrorAction SilentlyContinue
        if ($null -ne $staleLauncher) {
            $staleLauncherMatches = $false
            if ($state.launcher_started_at) {
                $recordedLauncherStart = [DateTimeOffset]$state.launcher_started_at
                $actualLauncherStart = (
                    [DateTimeOffset]$staleLauncher.StartTime.ToUniversalTime()
                )
                $staleLauncherMatches = (
                    [Math]::Abs(
                        ($actualLauncherStart - $recordedLauncherStart).TotalMilliseconds
                    ) -le 100
                )
            }
            $staleLauncherRecord = Get-CimInstance `
                Win32_Process `
                -Filter "ProcessId = $staleLauncherPid" `
                -ErrorAction SilentlyContinue
            $staleLauncherCommand = [string]$staleLauncherRecord.CommandLine
            $staleLauncherMatches = (
                $staleLauncherMatches -and
                $staleLauncherCommand -match "sovereign_product\.server" -and
                $staleLauncherCommand.IndexOf(
                    $rootPath,
                    [System.StringComparison]::OrdinalIgnoreCase
                ) -ge 0
            )
            if (-not $staleLauncherMatches) {
                throw (
                    "The listener PID is gone but its recorded launcher PID is live " +
                    "and does not match the v3 identity; state was retained."
                )
            }
            $taskkill = Join-Path $env:SystemRoot "System32\taskkill.exe"
            & $taskkill /PID ([string]$staleLauncherPid) /T /F | Out-Null
            $staleLauncher.WaitForExit(5000) | Out-Null
            if (-not $staleLauncher.HasExited) {
                throw "The recorded launcher did not stop; state was retained."
            }
        }
    }
    Remove-Item -LiteralPath $statePath -Force
    Write-Host "Removed a stale SOVEREIGN process record; PID $servicePid was not running."
    return
}

try {
    $baseUri = [Uri]([string]$state.url)
    $recordedPort = [int]$state.port
    $safeHost = $baseUri.Host -in @("127.0.0.1", "::1", "localhost")
    if (
        $baseUri.Scheme -ne "http" -or
        -not $safeHost -or
        $baseUri.Port -ne $recordedPort -or
        $baseUri.AbsolutePath -ne "/" -or
        $baseUri.Query -or
        $baseUri.Fragment -or
        $baseUri.UserInfo
    ) {
        throw "recorded URL must be loopback HTTP on the recorded port"
    }
} catch {
    throw "The service process record contains an unsafe URL; refusing network access or process control."
}

$processRecord = Get-CimInstance Win32_Process -Filter "ProcessId = $servicePid"
$commandLine = [string]$processRecord.CommandLine
$commandMatches = (
    $commandLine -match "sovereign_product\.server" -and
    $commandLine.IndexOf(
        $rootPath,
        [System.StringComparison]::OrdinalIgnoreCase
    ) -ge 0
)
if (-not $commandMatches) {
    throw "PID $servicePid is not the recorded SOVEREIGN service for this root; refusing to stop it."
}
$recordedStart = [DateTimeOffset]$state.process_started_at
$actualStart = [DateTimeOffset]$process.StartTime.ToUniversalTime()
if ([Math]::Abs(($actualStart - $recordedStart).TotalMilliseconds) -gt 100) {
    throw "PID $servicePid start time does not match the process record; refusing to stop a reused PID."
}

$listeners = @(
    Get-NetTCPConnection `
        -State Listen `
        -LocalPort $recordedPort `
        -ErrorAction SilentlyContinue
)
$foreignListeners = @(
    $listeners | Where-Object {
        $_.OwningProcess -ne $servicePid -or
        $_.LocalAddress -notin @("127.0.0.1", "::1")
    }
)
if ($foreignListeners.Count -gt 0) {
    throw "The recorded port has a foreign or non-loopback listener; refusing scoped shutdown."
}

# Ask every durable active job to cancel before terminating the service. This
# gives DEEP execution a chance to terminate only the process tree it owns.
$baseUrl = $baseUri.AbsoluteUri.TrimEnd("/")
try {
    $active = Invoke-RestMethod `
        -Uri "$baseUrl/v1/jobs?status=queued,running" `
        -Method Get `
        -TimeoutSec 5
    foreach ($job in @($active.jobs)) {
        Invoke-RestMethod `
            -Uri "$baseUrl/v1/jobs/$($job.job_id)/cancel" `
            -Method Post `
            -ContentType "application/json" `
            -Body "{}" `
            -TimeoutSec 5 | Out-Null
    }

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($CancelWaitSeconds)
    do {
        $remaining = Invoke-RestMethod `
            -Uri "$baseUrl/v1/jobs?status=queued,running" `
            -Method Get `
            -TimeoutSec 5
        if (@($remaining.jobs).Count -eq 0) {
            break
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTimeOffset]::UtcNow -lt $deadline)

    if (@($remaining.jobs).Count -gt 0) {
        Write-Warning (
            "{0} active job(s) did not reach a terminal state before shutdown." -f
            @($remaining.jobs).Count
        )
    }
} catch {
    Write-Warning "The service did not accept the pre-stop cancellation sweep: $($_.Exception.Message)"
}

$taskkill = Join-Path $env:SystemRoot "System32\taskkill.exe"
& $taskkill /PID ([string]$servicePid) /T /F | Out-Null
$process.WaitForExit(10000) | Out-Null
if (-not $process.HasExited) {
    throw "SOVEREIGN PID $servicePid did not stop. The process record was retained."
}

# A virtual-environment launcher may be distinct from the listener process.
# Remove it only when both its PID and recorded start time still identify the
# exact process created by Start-Sovereign; otherwise never act on a reused PID.
if ($state.launcher_pid -and [int]$state.launcher_pid -ne $servicePid) {
    $launcherPid = [int]$state.launcher_pid
    $launcher = Get-Process -Id $launcherPid -ErrorAction SilentlyContinue
    if ($null -ne $launcher) {
        $launcherIdentityMatches = $false
        if ($state.launcher_started_at) {
            $recordedLauncherStart = [DateTimeOffset]$state.launcher_started_at
            $actualLauncherStart = [DateTimeOffset]$launcher.StartTime.ToUniversalTime()
            $launcherIdentityMatches = (
                [Math]::Abs(
                    ($actualLauncherStart - $recordedLauncherStart).TotalMilliseconds
                ) -le 100
            )
        }
        $launcherRecord = Get-CimInstance `
            Win32_Process `
            -Filter "ProcessId = $launcherPid" `
            -ErrorAction SilentlyContinue
        $launcherCommand = [string]$launcherRecord.CommandLine
        $launcherIdentityMatches = (
            $launcherIdentityMatches -and
            $launcherCommand -match "sovereign_product\.server" -and
            $launcherCommand.IndexOf(
                $rootPath,
                [System.StringComparison]::OrdinalIgnoreCase
            ) -ge 0
        )
        if ($launcherIdentityMatches) {
            & $taskkill /PID ([string]$launcherPid) /T /F | Out-Null
            $launcher.WaitForExit(5000) | Out-Null
        } else {
            Write-Warning (
                "Launcher PID $launcherPid is live but no longer matches its recorded " +
                "start time; it was not touched."
            )
        }
    }
}

Remove-Item -LiteralPath $statePath -Force
Write-Host (
    "SOVEREIGN stopped. Durable sessions, checkpoints, and evidence were retained."
)
