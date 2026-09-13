[CmdletBinding()]
param(
    [string]$Root = $PSScriptRoot,
    [ValidateRange(1, 65535)]
    [int]$Port = 5175,
    [ValidateRange(1, 8)]
    [int]$Workers = 1,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$rootPath = [System.IO.Path]::GetFullPath($Root)
$markerPath = Join-Path $rootPath ".sovereign-root"
$manifestPath = Join-Path $rootPath "SYSTEM_MANIFEST.json"
$uiIndexPath = Join-Path $rootPath "ui\ui_shell\dist\index.html"
$pythonPath = Join-Path $rootPath ".venv\Scripts\python.exe"
# F-120. State lives in the shell's per-user state root, NEVER the install tree. Writing under
# <install>\modules\sovereign\runtime put sovereign.db, evidence, logs and service_state.json
# outside the backup scope, made them an "extra" path uninstall refuses over, and failed on a
# read-only per-machine install. Match the shell's layout and EXPORT the same env the shell sets,
# so a standalone launch and a shell launch share one state root and the product writes there too.
$stateRoot = $env:SOVEREIGN_WORKSPACE_STATE
if ([string]::IsNullOrWhiteSpace($stateRoot)) {
    $localAppData = $env:LOCALAPPDATA
    if ([string]::IsNullOrWhiteSpace($localAppData)) {
        $localAppData = Join-Path $env:USERPROFILE "AppData\Local"
    }
    $stateRoot = Join-Path $localAppData "SovereignWorkspace\sovereign"
}
$stateDirectory = Join-Path $stateRoot "runtime"
$env:SOVEREIGN_WORKSPACE_STATE = $stateRoot
$env:SOVEREIGN_STATE_DIR = $stateDirectory
$env:SOVEREIGN_EVIDENCE_DIR = (Join-Path $stateDirectory "evidence")
$statePath = Join-Path $stateDirectory "service_state.json"
$logDirectory = Join-Path $stateDirectory "logs"
$stdoutPath = Join-Path $logDirectory "product.stdout.log"
$stderrPath = Join-Path $logDirectory "product.stderr.log"
$healthUrl = "http://127.0.0.1:$Port/v1/health"

function Test-ProcessDescendsFrom {
    param(
        [int]$ChildProcessId,
        [int]$AncestorProcessId
    )
    if ($ChildProcessId -eq $AncestorProcessId) {
        return $true
    }
    $visited = [System.Collections.Generic.HashSet[int]]::new()
    $currentProcessId = $ChildProcessId
    for ($depth = 0; $depth -lt 32; $depth++) {
        if (-not $visited.Add($currentProcessId)) {
            return $false
        }
        $record = Get-CimInstance `
            Win32_Process `
            -Filter "ProcessId = $currentProcessId" `
            -ErrorAction SilentlyContinue
        if ($null -eq $record) {
            return $false
        }
        $parentProcessId = [int]$record.ParentProcessId
        if ($parentProcessId -eq $AncestorProcessId) {
            return $true
        }
        if ($parentProcessId -le 0) {
            return $false
        }
        $currentProcessId = $parentProcessId
    }
    return $false
}

function Stop-LaunchedProcessTree {
    param(
        [int]$LauncherProcessId,
        [int]$ListenerPort,
        [string]$ExpectedRoot
    )
    $taskkill = Join-Path $env:SystemRoot "System32\taskkill.exe"
    $launcher = Get-Process `
        -Id $LauncherProcessId `
        -ErrorAction SilentlyContinue
    if ($null -ne $launcher) {
        & $taskkill /PID ([string]$LauncherProcessId) /T /F | Out-Null
    }
    $possibleChildren = @(
        Get-NetTCPConnection `
            -State Listen `
            -LocalPort $ListenerPort `
            -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    )
    foreach ($candidateProcessId in $possibleChildren) {
        $candidateRecord = Get-CimInstance `
            Win32_Process `
            -Filter "ProcessId = $candidateProcessId" `
            -ErrorAction SilentlyContinue
        $candidateCommand = [string]$candidateRecord.CommandLine
        $ownedCandidate = (
            $null -ne $candidateRecord -and
            $candidateCommand -match "sovereign_product\.server" -and
            $candidateCommand.IndexOf(
                $ExpectedRoot,
                [System.StringComparison]::OrdinalIgnoreCase
            ) -ge 0 -and
            (Test-ProcessDescendsFrom `
                -ChildProcessId ([int]$candidateProcessId) `
                -AncestorProcessId $LauncherProcessId)
        )
        if ($ownedCandidate) {
            & $taskkill /PID ([string]$candidateProcessId) /T /F | Out-Null
        }
    }
}

if (
    -not (Test-Path -LiteralPath $markerPath -PathType Leaf) -or
    (Get-Content -LiteralPath $markerPath -Raw).Trim() -ne "SOVEREIGN_ROOT_MARKER=1"
) {
    throw "The selected directory is not a marker-validated SOVEREIGN root: $rootPath"
}
foreach ($requiredPath in @($manifestPath, $uiIndexPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required product file is missing: $requiredPath"
    }
}
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "The local environment is missing: $pythonPath"
}

& $pythonPath -c "import flask, requests, sovereign_product, sovereign_product.server"
if ($LASTEXITCODE -ne 0) {
    throw "The SOVEREIGN environment is incomplete. Run: & `"$pythonPath`" -m pip install -e `"$rootPath`""
}

$manifestJson = & $pythonPath -c (
    "import json,sys; " +
    "from system_manifest import load_system_manifest; " +
    "print(json.dumps(load_system_manifest(manifest_path=sys.argv[1])))"
) $manifestPath
if ($LASTEXITCODE -ne 0) {
    throw "SYSTEM_MANIFEST validation failed."
}
$manifest = $manifestJson | ConvertFrom-Json
$ollamaBaseUrl = [string]$manifest.RUNTIME.OLLAMA_BASE_URL
$ollamaTagsUrl = $ollamaBaseUrl.TrimEnd("/") + "/api/tags"

New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

if (Test-Path -LiteralPath $statePath -PathType Leaf) {
    try {
        $existing = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        $existingPid = [int]$existing.pid
        $existingProcess = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        $existingLauncherProcess = $null
        if ($existing.launcher_pid) {
            $existingLauncherProcess = Get-Process `
                -Id ([int]$existing.launcher_pid) `
                -ErrorAction SilentlyContinue
        }
    } catch {
        throw "The service process record is unreadable. Run .\Diagnose-Sovereign.ps1 before changing it."
    }
    if ($null -ne $existingProcess) {
        $existingRecord = Get-CimInstance Win32_Process -Filter "ProcessId = $existingPid"
        $existingCommand = [string]$existingRecord.CommandLine
        $sameService = (
            $existingCommand -match "sovereign_product\.server" -and
            $existingCommand.IndexOf(
                $rootPath,
                [System.StringComparison]::OrdinalIgnoreCase
            ) -ge 0
        )
        $sameIdentity = $false
        if (
            [int]$existing.schema_version -eq 3 -and
            $existing.process_started_at
        ) {
            $recordedExistingStart = [DateTimeOffset]::Parse(
                [string]$existing.process_started_at
            )
            $actualExistingStart = (
                [DateTimeOffset]$existingProcess.StartTime.ToUniversalTime()
            )
            $sameIdentity = (
                [Math]::Abs(
                    ($actualExistingStart - $recordedExistingStart).TotalMilliseconds
                ) -le 100
            )
        }
        if ($sameService -and $sameIdentity) {
            throw "SOVEREIGN is already running as PID $existingPid at $($existing.url)."
        }
        if ($sameService) {
            throw (
                "A SOVEREIGN-like process uses recorded PID $existingPid, but its " +
                "schema/start identity does not match; refusing to overwrite possible reused-PID state."
            )
        }
        throw "The service record refers to unrelated live PID $existingPid; refusing to overwrite it."
    }
    if ($null -ne $existingLauncherProcess) {
        throw (
            "The recorded listener PID $existingPid is gone, but launcher PID " +
            "$($existing.launcher_pid) is still live; refusing to discard state or risk an orphan."
        )
    }
    Remove-Item -LiteralPath $statePath -Force
}

$listeners = @(
    Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
)
if ($listeners.Count -gt 0) {
    $owners = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    throw "Port $Port is already in use by PID(s): $($owners -join ', ')."
}

try {
    $tags = Invoke-RestMethod `
        -Uri $ollamaTagsUrl `
        -Method Get `
        -TimeoutSec 5
} catch {
    throw "Local Ollama is not reachable on the manifest endpoint $ollamaBaseUrl."
}

$installed = @(
    $tags.models | ForEach-Object {
        if ($_.name) { [string]$_.name }
        elseif ($_.model) { [string]$_.model }
    }
)
$requiredModels = @(
    $manifest.MODELS.PRIMARY_REASONER,
    $manifest.MODELS.ADVERSARIAL_CHALLENGER,
    $manifest.MODELS.CRITIC,
    $manifest.MODELS.SYNTHESIZER,
    $manifest.MODELS.EMBEDDING_MODEL
) | Where-Object { $_ } | Sort-Object -Unique
$missingModels = @(
    $requiredModels | Where-Object { $_ -notin $installed }
)
if ($missingModels.Count -gt 0) {
    throw "Required local Ollama model(s) are missing: $($missingModels -join ', ')"
}

$quotedRoot = '"' + $rootPath.Replace('"', '\"') + '"'
$process = Start-Process `
    -FilePath $pythonPath `
    -ArgumentList @(
        "-m", "sovereign_product.server",
        "--root", $quotedRoot,
        "--host", "127.0.0.1",
        "--port", [string]$Port,
        "--workers", [string]$Workers
    ) `
    -WorkingDirectory $rootPath `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -PassThru

$ready = $false
$health = $null
for ($attempt = 0; $attempt -lt 120; $attempt++) {
    if ($process.HasExited) {
        break
    }
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 2
        if ($health.status -eq "ok") {
            $ready = $true
            break
        }
    } catch {
        # Startup commonly refuses the connection until Flask begins listening.
    }
    Start-Sleep -Milliseconds 500
}

if (-not $ready) {
    Stop-LaunchedProcessTree `
        -LauncherProcessId $process.Id `
        -ListenerPort $Port `
        -ExpectedRoot $rootPath
    if (-not $process.HasExited) {
        $process.WaitForExit(5000) | Out-Null
    }
    $stderrTail = if (Test-Path -LiteralPath $stderrPath) {
        (Get-Content -LiteralPath $stderrPath -Tail 30) -join [Environment]::NewLine
    } else {
        "No server error log was written."
    }
    $healthDetail = if ($null -ne $health) {
        $health | ConvertTo-Json -Compress -Depth 5
    } else {
        "No health response was received."
    }
    throw "SOVEREIGN did not become ready. Health: $healthDetail`nServer log:`n$stderrTail"
}

$readyListeners = @(
    Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop
)
$nonLoopbackListeners = @(
    $readyListeners | Where-Object {
        $_.LocalAddress -notin @("127.0.0.1", "::1")
    }
)
$listenerOwners = @(
    $readyListeners | Select-Object -ExpandProperty OwningProcess -Unique
)
if ($nonLoopbackListeners.Count -gt 0 -or $listenerOwners.Count -ne 1) {
    Stop-LaunchedProcessTree `
        -LauncherProcessId $process.Id `
        -ListenerPort $Port `
        -ExpectedRoot $rootPath
    throw "The product listener is not a single loopback-owned process; startup was terminated."
}
$servicePid = [int]$listenerOwners[0]
$serviceProcess = Get-Process -Id $servicePid -ErrorAction Stop
$serviceRecord = Get-CimInstance Win32_Process -Filter "ProcessId = $servicePid"
$serviceCommand = [string]$serviceRecord.CommandLine
if (
    -not (Test-ProcessDescendsFrom `
        -ChildProcessId $servicePid `
        -AncestorProcessId $process.Id) -or
    $serviceCommand -notmatch "sovereign_product\.server" -or
    $serviceCommand.IndexOf(
        $rootPath,
        [System.StringComparison]::OrdinalIgnoreCase
    ) -lt 0
) {
    Stop-LaunchedProcessTree `
        -LauncherProcessId $process.Id `
        -ListenerPort $Port `
        -ExpectedRoot $rootPath
    throw "The loopback listener is not the launched SOVEREIGN process tree for this root; startup was terminated."
}

$process.Refresh()
$serviceState = [ordered]@{
    schema_version = 3
    pid = $servicePid
    process_started_at = $serviceProcess.StartTime.ToUniversalTime().ToString("o")
    launcher_pid = $process.Id
    launcher_started_at = $process.StartTime.ToUniversalTime().ToString("o")
    executable = $pythonPath
    root = $rootPath
    host = "127.0.0.1"
    port = $Port
    url = "http://127.0.0.1:$Port/"
    health_url = $healthUrl
    started_at = [DateTimeOffset]::UtcNow.ToString("o")
    version = $health.product_version
}
$temporaryState = "$statePath.tmp"
try {
    $serviceState |
        ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath $temporaryState -Encoding UTF8
    Move-Item -LiteralPath $temporaryState -Destination $statePath -Force
} catch {
    Stop-LaunchedProcessTree `
        -LauncherProcessId $process.Id `
        -ListenerPort $Port `
        -ExpectedRoot $rootPath
    if (-not $process.HasExited) {
        $process.WaitForExit(5000) | Out-Null
    }
    if (Test-Path -LiteralPath $temporaryState -PathType Leaf) {
        Remove-Item -LiteralPath $temporaryState -Force
    }
    throw "SOVEREIGN became ready but its process record could not be committed: $($_.Exception.Message)"
}

Write-Host (
    "SOVEREIGN is ready at {0} (PID {1}, version {2})." -f
    $serviceState.url,
    $servicePid,
    $health.product_version
)
if (-not $NoBrowser) {
    Start-Process $serviceState.url
}
