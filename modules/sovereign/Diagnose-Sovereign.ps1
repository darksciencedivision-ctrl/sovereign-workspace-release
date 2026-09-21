[CmdletBinding()]
param(
    [string]$Root = $PSScriptRoot,
    [ValidateRange(1, 65535)]
    [int]$Port = 5175
)

$ErrorActionPreference = "Continue"
$rootPath = [System.IO.Path]::GetFullPath($Root)
$consumerEnvPath = Join-Path $rootPath "runtime\llamacpp_supervisor\consumer.env"
if (Test-Path -LiteralPath $consumerEnvPath -PathType Leaf) {
    Get-Content -LiteralPath $consumerEnvPath | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            Set-Item -Path ("Env:" + $Matches[1]) -Value $Matches[2]
        }
    }
}
if ([string]::IsNullOrWhiteSpace([string]$env:SOVEREIGN_INFERENCE_BACKEND)) {
    $env:SOVEREIGN_INFERENCE_BACKEND = "llama.cpp"
}
if (
    [string]$env:SOVEREIGN_INFERENCE_BACKEND -eq "llama.cpp" -and
    [string]::IsNullOrWhiteSpace([string]$env:SOVEREIGN_LLAMA_CPP_BASE_URL)
) {
    $env:SOVEREIGN_LLAMA_CPP_BASE_URL = "http://127.0.0.1:18080"
}
if (
    [string]$env:SOVEREIGN_INFERENCE_BACKEND -eq "llama.cpp" -and
    [string]::IsNullOrWhiteSpace([string]$env:SOVEREIGN_LLAMA_CPP_API_KEY)
) {
    $keyPath = Join-Path $rootPath "runtime\llamacpp_supervisor\api_key"
    if (Test-Path -LiteralPath $keyPath -PathType Leaf) {
        $env:SOVEREIGN_LLAMA_CPP_API_KEY = (Get-Content -LiteralPath $keyPath -Raw).Trim()
    }
}
$checks = [System.Collections.Generic.List[object]]::new()

function Add-Check {
    param([string]$Name, [bool]$Passed, [string]$Detail)
    $checks.Add([pscustomobject]@{
        Check = $Name
        Result = if ($Passed) { "PASS" } else { "FAIL" }
        Detail = $Detail
    })
}

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

$markerPath = Join-Path $rootPath ".sovereign-root"
$markerValid = $false
if (Test-Path -LiteralPath $markerPath -PathType Leaf) {
    try {
        $markerValid = (
            (Get-Content -LiteralPath $markerPath -Raw).Trim() -eq
            "SOVEREIGN_ROOT_MARKER=1"
        )
    } catch {
        $markerValid = $false
    }
}
Add-Check "Root marker" $markerValid $markerPath

$requiredFiles = [ordered]@{
    "System manifest" = "SYSTEM_MANIFEST.json"
    "Unified service" = "sovereign_product\server.py"
    "Built UI" = "ui\ui_shell\dist\index.html"
    "Legacy handoff" = "ui\adapter_service\adapter.py"
}
foreach ($entry in $requiredFiles.GetEnumerator()) {
    $path = Join-Path $rootPath $entry.Value
    Add-Check $entry.Key (Test-Path -LiteralPath $path -PathType Leaf) $path
}

$pythonPath = Join-Path $rootPath ".venv\Scripts\python.exe"
$pythonValid = Test-Path -LiteralPath $pythonPath -PathType Leaf
Add-Check "Python environment" $pythonValid $pythonPath

if ($pythonValid) {
    $pythonVersion = & $pythonPath --version 2>&1
    Add-Check "Python version" ($LASTEXITCODE -eq 0) ([string]$pythonVersion)
    & $pythonPath -c "import flask, requests, sovereign_product, sovereign_product.server, sqlite3"
    Add-Check (
        "Python dependencies"
    ) ($LASTEXITCODE -eq 0) "flask, requests, unified service, sqlite3"

    $legacyPath = Join-Path $rootPath "ui\adapter_service\adapter.py"
    & $pythonPath $legacyPath --help *> $null
    Add-Check (
        "Legacy adapter handoff"
    ) ($LASTEXITCODE -eq 0) "Forwards to sovereign_product.server"
}

$manifest = $null
if ($markerValid -and $pythonValid) {
    try {
        $manifestPath = Join-Path $rootPath "SYSTEM_MANIFEST.json"
        $manifestJson = & $pythonPath -c (
            "import json,sys; " +
            "from system_manifest import load_system_manifest; " +
            "print(json.dumps(load_system_manifest(manifest_path=sys.argv[1])))"
        ) $manifestPath
        if ($LASTEXITCODE -ne 0) {
            throw "canonical manifest validation failed"
        }
        $manifest = $manifestJson | ConvertFrom-Json
        Add-Check "Manifest validation" $true "Canonical loader accepted the manifest"
    } catch {
        Add-Check "Manifest validation" $false $_.Exception.Message
    }
}

try {
    if ($null -eq $manifest) {
        throw "A validated manifest is unavailable"
    }
    $ollamaBaseUrl = [string]$manifest.RUNTIME.OLLAMA_BASE_URL
    $ollamaTagsUrl = $ollamaBaseUrl.TrimEnd("/") + "/api/tags"
    $tags = Invoke-RestMethod `
        -Uri $ollamaTagsUrl `
        -Method Get `
        -TimeoutSec 5
    Add-Check "Ollama" $true "$ollamaBaseUrl reachable; $(@($tags.models).Count) installed tag(s)"
    if ($null -ne $manifest) {
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
        $requireOllamaModels = [string]$env:SOVEREIGN_INFERENCE_BACKEND -eq "ollama"
        foreach ($model in $requiredModels) {
            $present = $model -in $installed
            $modelDetail = "missing"
            if ($present) {
                $modelDetail = "installed"
            }
            if ($requireOllamaModels) {
                Add-Check "Model $model" $present $modelDetail
            } else {
                Add-Check "Ollama residual $model" $present $modelDetail
            }
        }
    }
} catch {
    if ([string]$env:SOVEREIGN_INFERENCE_BACKEND -eq "ollama") {
        Add-Check "Ollama" $false $_.Exception.Message
    } else {
        Add-Check "Ollama residual" $false $_.Exception.Message
    }
}

if ([string]$env:SOVEREIGN_INFERENCE_BACKEND -ne "ollama") {
    try {
        $llamaBaseUrl = [string]$env:SOVEREIGN_LLAMA_CPP_BASE_URL
        if ([string]::IsNullOrWhiteSpace($llamaBaseUrl)) {
            $llamaBaseUrl = "http://127.0.0.1:18080"
        }
        $llamaHeaders = @{}
        if (-not [string]::IsNullOrWhiteSpace($env:SOVEREIGN_LLAMA_CPP_API_KEY)) {
            $llamaHeaders["Authorization"] = "Bearer $($env:SOVEREIGN_LLAMA_CPP_API_KEY)"
        }
        $llamaModels = Invoke-RestMethod `
            -Uri ($llamaBaseUrl.TrimEnd("/") + "/models") `
            -Method Get `
            -Headers $llamaHeaders `
            -TimeoutSec 5
        $llamaCount = 0
        if ($llamaModels.data) {
            $llamaCount = @($llamaModels.data).Count
        }
        Add-Check "llama.cpp supervisor" $true "$llamaBaseUrl reachable; $llamaCount registered profile(s)"
    } catch {
        Add-Check "llama.cpp supervisor" $false $_.Exception.Message
    }
    try {
        $persistJson = & $pythonPath -m sovereign_product.supervisor_service --root $rootPath persistence-status
        $persist = $persistJson | ConvertFrom-Json
        $persistOk = [bool]$persist.persistent -and [bool]$persist.autostart
        $persistDetail = (
            "logon=$($persist.logon_launcher_present); " +
            "failure=$($persist.failure_launcher_present); " +
            "autostart=$($persist.autostart); " +
            "watch_alive=$($persist.watch_alive)"
        )
        Add-Check "llama.cpp persistence" $persistOk $persistDetail
    } catch {
        Add-Check "llama.cpp persistence" $false $_.Exception.Message
    }
}

$statePath = Join-Path $rootPath "runtime\service_state.json"
$state = $null
$recordedProcess = $null
$stateValid = $false
if (Test-Path -LiteralPath $statePath -PathType Leaf) {
    try {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        $schemaValid = [int]$state.schema_version -eq 3
        $recordedRoot = [System.IO.Path]::GetFullPath([string]$state.root)
        $rootMatches = [System.StringComparer]::OrdinalIgnoreCase.Equals(
            $recordedRoot,
            $rootPath
        )
        $servicePid = [int]$state.pid
        $recordedProcess = Get-Process `
            -Id $servicePid `
            -ErrorAction SilentlyContinue
        $commandMatches = $false
        $startMatches = $false
        if ($null -ne $recordedProcess) {
            $processRecord = Get-CimInstance `
                Win32_Process `
                -Filter "ProcessId = $servicePid" `
                -ErrorAction SilentlyContinue
            $commandLine = [string]$processRecord.CommandLine
            $commandMatches = (
                $commandLine -match "sovereign_product\.server" -and
                $commandLine.IndexOf(
                    $rootPath,
                    [System.StringComparison]::OrdinalIgnoreCase
                ) -ge 0
            )
            if ($state.process_started_at) {
                $recordedStart = [DateTimeOffset]$state.process_started_at
                $actualStart = [DateTimeOffset]$recordedProcess.StartTime.ToUniversalTime()
                $startMatches = (
                    [Math]::Abs(
                        ($actualStart - $recordedStart).TotalMilliseconds
                    ) -le 100
                )
            }
        }

        $stateUri = [Uri]([string]$state.url)
        $healthUri = [Uri]([string]$state.health_url)
        $recordedPort = [int]$state.port
        $urlSafe = (
            $stateUri.Scheme -eq "http" -and
            $stateUri.Host -in @("127.0.0.1", "::1", "localhost") -and
            $stateUri.Port -eq $recordedPort -and
            $stateUri.AbsolutePath -eq "/" -and
            -not $stateUri.Query -and
            -not $stateUri.Fragment -and
            -not $stateUri.UserInfo -and
            $healthUri.Scheme -eq "http" -and
            $healthUri.Host -in @("127.0.0.1", "::1", "localhost") -and
            $healthUri.Port -eq $recordedPort -and
            $healthUri.AbsolutePath -eq "/v1/health" -and
            -not $healthUri.Query -and
            -not $healthUri.Fragment -and
            -not $healthUri.UserInfo
        )

        $launcherValid = $true
        if ($state.launcher_pid -and [int]$state.launcher_pid -ne $servicePid) {
            $launcherPid = [int]$state.launcher_pid
            $launcher = Get-Process `
                -Id $launcherPid `
                -ErrorAction SilentlyContinue
            if ($null -ne $launcher) {
                $launcherStartMatches = $false
                if ($state.launcher_started_at) {
                    $recordedLauncherStart = [DateTimeOffset]$state.launcher_started_at
                    $actualLauncherStart = (
                        [DateTimeOffset]$launcher.StartTime.ToUniversalTime()
                    )
                    $launcherStartMatches = (
                        [Math]::Abs(
                            (
                                $actualLauncherStart -
                                $recordedLauncherStart
                            ).TotalMilliseconds
                        ) -le 100
                    )
                }
                $launcherValid = (
                    $launcherStartMatches -and
                    (Test-ProcessDescendsFrom `
                        -ChildProcessId $servicePid `
                        -AncestorProcessId $launcherPid)
                )
            }
        }
        $stateValid = (
            $schemaValid -and
            $rootMatches -and
            $null -ne $recordedProcess -and
            $commandMatches -and
            $startMatches -and
            $urlSafe -and
            $launcherValid
        )
        Add-Check (
            "Service process record"
        ) $stateValid (
            "PID $servicePid; schema=$schemaValid; root=$rootMatches; " +
            "command=$commandMatches; start=$startMatches; url=$urlSafe; " +
            "launcher=$launcherValid"
        )
    } catch {
        Add-Check "Service process record" $false $_.Exception.Message
    }
} else {
    Add-Check "Service process record" $true "Not running"
}

$effectivePort = $Port
if ($null -ne $state -and $state.port) {
    try {
        $candidatePort = [int]$state.port
        if ($candidatePort -ge 1 -and $candidatePort -le 65535) {
            $effectivePort = $candidatePort
        }
    } catch {
        # Keep the explicit diagnostic port when the state value is corrupt.
    }
}
$listeners = @(
    Get-NetTCPConnection `
        -State Listen `
        -LocalPort $effectivePort `
        -ErrorAction SilentlyContinue
)
if ($stateValid) {
    $unexpected = @(
        $listeners | Where-Object {
            $_.OwningProcess -ne [int]$state.pid -or
            $_.LocalAddress -notin @("127.0.0.1", "::1")
        }
    )
    $portValid = $listeners.Count -gt 0 -and $unexpected.Count -eq 0
    $listenerDetail = "Listener is missing, non-loopback, or owned by another PID"
    if ($portValid) {
        $listenerDetail = "Port $effectivePort belongs only to recorded loopback PID $($state.pid)"
    }
    Add-Check "Product listener containment" $portValid $listenerDetail
} else {
    $portDetail = "Port $effectivePort is occupied without a valid SOVEREIGN process record"
    if ($listeners.Count -eq 0) {
        $portDetail = "Port $effectivePort is free"
    }
    Add-Check "Product port" ($listeners.Count -eq 0) $portDetail
}

if ($stateValid) {
    try {
        $health = Invoke-RestMethod `
            -Uri $state.health_url `
            -Method Get `
            -TimeoutSec 4
        Add-Check (
            "Service health"
        ) ($health.status -eq "ok") (
            $health | ConvertTo-Json -Compress -Depth 6
        )
    } catch {
        Add-Check "Service health" $false $_.Exception.Message
    }

    try {
        Invoke-WebRequest `
            -Uri $state.health_url `
            -Headers @{ Host = "attacker.invalid" } `
            -UseBasicParsing `
            -TimeoutSec 4 |
            Out-Null
        Add-Check "Host-header containment" $false "Untrusted Host was accepted"
    } catch {
        $statusCode = [int]$_.Exception.Response.StatusCode
        Add-Check (
            "Host-header containment"
        ) ($statusCode -eq 403) "Untrusted Host returned HTTP $statusCode"
    }
}

$dbPath = Join-Path $rootPath "runtime\sovereign.db"
if ($pythonValid -and (Test-Path -LiteralPath $dbPath -PathType Leaf)) {
    $dbCheck = @'
import sys
from sovereign_product.store import SovereignStore
store = SovereignStore(sys.argv[1])
print(store.status_summary())
print(store.verify_event_chain())
'@
    & $pythonPath -c $dbCheck $dbPath
    Add-Check (
        "Durable store"
    ) ($LASTEXITCODE -eq 0) "SQLite quick-check and event-chain verification"
} else {
    Add-Check "Durable store" $true "Not initialized yet"
}

$checks | Format-Table -AutoSize -Wrap
if (@($checks | Where-Object { $_.Result -eq "FAIL" }).Count -gt 0) {
    exit 1
}
exit 0
