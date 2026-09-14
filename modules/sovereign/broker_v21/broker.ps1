# broker.ps1 - SOVEREIGN Broker (controlled upgrade)
# Preserves the canonical entry point while delegating synthesis to the strict live orchestrator.

param(
    [string]$Root = "",
    [string]$ManifestPath = "",
    [string]$InboxPath = "",
    [string]$LogsPath = "",
    [string]$PraxisLogsPath = "",
    [string]$TopicFilePath = "",
    [string]$DialogLogPath = "",
    [string]$SystemLogPath = "",
    [string]$SynthesisFilePath = "",
    [string]$LiveOrchestratorPath = "",
    [string]$OllamaBaseUrl = "",
    [string]$ModelA = "",
    [string]$ModelB = "",
    [string]$ModelC = "",
    [string]$ModelSynth = "",
    [int]$DebateRounds = 2,
    [int]$MaxTokensPerTurn = 768,
    [int]$MaxTokensSynth = 1024,
    [double]$DebateTemp = 0.7,
    [double]$SynthTemp = 0.3,
    [int]$Seed = 0,
    [int]$TurnTimeoutSec = 225,
    [int]$SynthTimeoutSec = 300,
    [string]$SystemPromptFile = "",
    [string]$PythonExe = "python",
    [string]$SafeTheoremManifestPath = "",
    [switch]$SafeTheoremMode,
    [switch]$Once
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-FullPath {
    param([string]$PathValue)
    $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PathValue)
}

# The Python launcher owns root discovery.  The broker accepts only that
# explicitly supplied root and validates the same authoritative marker.
$RootMarkerName = ".sovereign-root"
$RootMarkerContent = "SOVEREIGN_ROOT_MARKER=1"

function Normalize-PathText {
    param([string]$PathValue)
    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return ""
    }
    $trimmed = $PathValue.Trim().Replace('/', '\').TrimEnd('\')
    if ($trimmed.Length -eq 2 -and $trimmed[1] -eq ':') {
        return $trimmed + '\'
    }
    return $trimmed
}

function Normalize-RootPath {
    param([string]$PathValue)
    $resolved = (Resolve-Path -LiteralPath $PathValue -ErrorAction Stop).Path
    return Normalize-PathText $resolved
}

function Assert-ValidRuntimeRoot {
    param(
        [string]$CandidateRoot,
        [string]$Source
    )
    if ([string]::IsNullOrWhiteSpace($CandidateRoot)) {
        throw "Runtime root validation failed ($Source): no candidate root was provided."
    }
    $resolvedRoot = Normalize-RootPath $CandidateRoot
    $markerPath = Join-Path $resolvedRoot $RootMarkerName
    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        throw "Runtime root validation failed ($Source): missing $RootMarkerName under $resolvedRoot"
    }
    $markerText = (Get-Content -Raw -LiteralPath $markerPath).Trim()
    if ($markerText -ne $RootMarkerContent) {
        throw "Runtime root validation failed ($Source): invalid $RootMarkerName contents under $resolvedRoot"
    }
    foreach ($requiredPath in @("cycle_runner_v3.py", "SYSTEM_MANIFEST.json", "synthesis\live_orchestrator.py")) {
        if (-not (Test-Path -LiteralPath (Join-Path $resolvedRoot $requiredPath))) {
            throw "Runtime root validation failed ($Source): missing required path $requiredPath under $resolvedRoot"
        }
    }
    return @{
        Root = $resolvedRoot
        MarkerHits = @($RootMarkerName)
    }
}

function Find-CanonicalRuntimeRoot {
    param([string]$StartPath)
    $resolvedStart = Normalize-RootPath $StartPath
    $item = Get-Item -LiteralPath $resolvedStart -ErrorAction Stop
    if (-not $item.PSIsContainer) {
        $item = $item.Directory
    }
    $lastError = ""
    $current = $item
    while ($null -ne $current) {
        try {
            return Assert-ValidRuntimeRoot -CandidateRoot $current.FullName -Source "discovered from broker.ps1 location"
        }
        catch {
            $lastError = $_.Exception.Message
            $current = $current.Parent
        }
    }
    throw "Canonical runtime root discovery failed from $resolvedStart. $lastError"
}

$ScriptDir = Split-Path -Parent $PSCommandPath
if ([string]::IsNullOrWhiteSpace($Root)) {
    throw "The canonical launcher must supply -Root; broker-side root discovery is disabled."
}
$RootValidation = Assert-ValidRuntimeRoot -CandidateRoot $Root -Source "explicit -Root parameter"
$RootResolved = [string]$RootValidation.Root
$RootMarkerHits = @($RootValidation.MarkerHits)
Write-Host "BROKER_ROOT=$RootResolved"
$EffectiveManifestPath = if ([string]::IsNullOrWhiteSpace($ManifestPath)) { Join-Path $RootResolved "SYSTEM_MANIFEST.json" } else { (Resolve-Path $ManifestPath).Path }
function Assert-PathInsideRuntimeRoot {
    param(
        [string]$Label,
        [string]$CandidatePath
    )
    $resolvedCandidate = Resolve-FullPath $CandidatePath
    if (-not $resolvedCandidate.StartsWith($RootResolved, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label must stay inside safe runtime root. candidate=$resolvedCandidate runtime_root=$RootResolved"
    }
}

function ConvertTo-HashtableRecursive {
    param([object]$InputObject)
    if ($null -eq $InputObject) { return $null }
    if ($InputObject -is [System.Collections.IDictionary]) {
        $table = @{}
        foreach ($key in $InputObject.Keys) {
            $table[$key] = ConvertTo-HashtableRecursive $InputObject[$key]
        }
        return $table
    }
    if (($InputObject -is [string]) -or ($InputObject -is [ValueType])) {
        return $InputObject
    }
    if (($InputObject -is [System.Collections.IEnumerable]) -and -not ($InputObject -is [string])) {
        $items = @()
        foreach ($item in $InputObject) {
            $items += ,(ConvertTo-HashtableRecursive $item)
        }
        return $items
    }
    $properties = @($InputObject.PSObject.Properties)
    if ($properties.Count -gt 0) {
        $table = @{}
        foreach ($property in $properties) {
            $table[$property.Name] = ConvertTo-HashtableRecursive $property.Value
        }
        return $table
    }
    return $InputObject
}
if (-not (Test-Path $EffectiveManifestPath)) {
    throw "SYSTEM_MANIFEST.json missing: $EffectiveManifestPath"
}
try {
    $ManifestObject = Get-Content $EffectiveManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
    $Manifest = ConvertTo-HashtableRecursive $ManifestObject
}
catch {
    throw "SYSTEM_MANIFEST.json malformed or unreadable: $EffectiveManifestPath | $($_.Exception.Message)"
}
foreach ($section in @("MODELS", "RUNTIME", "THRESHOLDS")) {
    if (-not $Manifest.ContainsKey($section)) {
        throw "SYSTEM_MANIFEST.json missing required section '$section'"
    }
}
function Get-ManifestString {
    param([hashtable]$Section, [string]$Key, [string]$Label)
    $value = [string]$Section[$Key]
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "SYSTEM_MANIFEST.json missing required value $Label.$Key"
    }
    return $value.Trim()
}
$Models = [hashtable]$Manifest["MODELS"]
$Runtime = [hashtable]$Manifest["RUNTIME"]
$OllamaBaseUrl = if ([string]::IsNullOrWhiteSpace($OllamaBaseUrl)) { Get-ManifestString -Section $Runtime -Key "OLLAMA_BASE_URL" -Label "RUNTIME" } else { $OllamaBaseUrl }
$ModelA = if ([string]::IsNullOrWhiteSpace($ModelA)) { Get-ManifestString -Section $Models -Key "PRIMARY_REASONER" -Label "MODELS" } else { $ModelA }
$ModelB = if ([string]::IsNullOrWhiteSpace($ModelB)) { Get-ManifestString -Section $Models -Key "ADVERSARIAL_CHALLENGER" -Label "MODELS" } else { $ModelB }
$ModelC = if ([string]::IsNullOrWhiteSpace($ModelC)) { Get-ManifestString -Section $Models -Key "CRITIC" -Label "MODELS" } else { $ModelC }
$ModelSynth = if ([string]::IsNullOrWhiteSpace($ModelSynth)) { Get-ManifestString -Section $Models -Key "SYNTHESIZER" -Label "MODELS" } else { $ModelSynth }
$InboxDir = if ([string]::IsNullOrWhiteSpace($InboxPath)) { Join-Path $RootResolved "broker_v21\inbox" } else { Resolve-FullPath $InboxPath }
$LogsDir = if ([string]::IsNullOrWhiteSpace($LogsPath)) { Join-Path $RootResolved "logs" } else { Resolve-FullPath $LogsPath }
$PraxisLogsDir = if ([string]::IsNullOrWhiteSpace($PraxisLogsPath)) { Join-Path $RootResolved "praxis\logs" } else { Resolve-FullPath $PraxisLogsPath }
$StopFile = Join-Path $RootResolved "STOP"
$StopPraxis = Join-Path $RootResolved "praxis\STOP"
$TopicFile = if ([string]::IsNullOrWhiteSpace($TopicFilePath)) { Join-Path $InboxDir "topic.txt" } else { Resolve-FullPath $TopicFilePath }
$DialogLog = if ([string]::IsNullOrWhiteSpace($DialogLogPath)) { Join-Path $LogsDir "dialog.txt" } else { Resolve-FullPath $DialogLogPath }
$SystemLog = if ([string]::IsNullOrWhiteSpace($SystemLogPath)) { Join-Path $LogsDir "system.txt" } else { Resolve-FullPath $SystemLogPath }
$SynthesisFile = if ([string]::IsNullOrWhiteSpace($SynthesisFilePath)) { Join-Path $PraxisLogsDir "synthesis.txt" } else { Resolve-FullPath $SynthesisFilePath }
$LiveOrchestrator = if ([string]::IsNullOrWhiteSpace($LiveOrchestratorPath)) { Join-Path $RootResolved "synthesis\live_orchestrator.py" } else { Resolve-FullPath $LiveOrchestratorPath }

if ($SafeTheoremMode) {
    if ([string]::IsNullOrWhiteSpace($SafeTheoremManifestPath)) {
        throw "Safe theorem mode requires -SafeTheoremManifestPath"
    }
    $ResolvedSafeTheoremManifestPath = Resolve-FullPath $SafeTheoremManifestPath
    if (-not (Test-Path $ResolvedSafeTheoremManifestPath)) {
        throw "Safe theorem manifest missing: $ResolvedSafeTheoremManifestPath"
    }
    foreach ($item in @(
        @{ Label = "InboxPath"; Path = $InboxDir },
        @{ Label = "LogsPath"; Path = $LogsDir },
        @{ Label = "PraxisLogsPath"; Path = $PraxisLogsDir },
        @{ Label = "TopicFilePath"; Path = $TopicFile },
        @{ Label = "DialogLogPath"; Path = $DialogLog },
        @{ Label = "SystemLogPath"; Path = $SystemLog },
        @{ Label = "SynthesisFilePath"; Path = $SynthesisFile }
    )) {
        Assert-PathInsideRuntimeRoot -Label $item.Label -CandidatePath $item.Path
    }
}

foreach ($dir in @($InboxDir, $LogsDir, $PraxisLogsDir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
foreach ($file in @($DialogLog, $SystemLog)) {
    if (-not (Test-Path $file)) {
        New-Item -ItemType File -Force -Path $file | Out-Null
    }
}

function Get-UtcStamp {
    (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss")
}

function Log-System {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-UtcStamp), $Message
    Add-Content -Path $SystemLog -Value $line -Encoding UTF8
    Write-Host $line
}

function Log-Dialog {
    param([string]$Message)
    Add-Content -Path $DialogLog -Value $Message -Encoding UTF8
}

function Test-StopRequested {
    return (Test-Path $StopFile) -or (Test-Path $StopPraxis)
}

function Get-RawTopicPayload {
    if (-not (Test-Path $TopicFile)) {
        throw "Topic file not found: $TopicFile"
    }
    Get-Content $TopicFile -Raw -Encoding UTF8
}

function Get-SessionIdFromText {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $null }
    $m = [regex]::Match($Text, '\[TOPIC\s+session_id=([^\]\s]+)\]', 'IgnoreCase')
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    $m = [regex]::Match($Text, '\[SYNTH\s+session_id=([^\]\s]+)\]', 'IgnoreCase')
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    return $null
}

function Get-CleanTopic {
    param([string]$RawText)
    $text = $RawText -replace '\r\n', "`n"
    $text = $text -replace '(?is)\[TOPIC[^\]]*\]', ''
    $text = $text -replace '(?is)\[/TOPIC\]', ''
    $text.Trim()
}

function New-SessionId {
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $short = [guid]::NewGuid().ToString("N").Substring(0, 8)
    "{0}_{1}" -f $stamp, $short
}

function Invoke-SynthKing {
    param(
        [string]$Topic,
        [string]$SessionId
    )

    if (-not (Test-Path $LiveOrchestrator)) {
        throw "Missing live_orchestrator.py: $LiveOrchestrator"
    }

    $argList = @(
        $LiveOrchestrator,
        "--root", $RootResolved,
        "--topic", $Topic,
        "--session-id", $SessionId,
        "--ollama-base-url", $OllamaBaseUrl,
        "--model-a", $ModelA,
        "--model-b", $ModelB,
        "--model-c", $ModelC,
        "--model-synth", $ModelSynth,
        "--debate-rounds", [string]$DebateRounds,
        "--max-tokens-turn", [string]$MaxTokensPerTurn,
        "--max-tokens-synth", [string]$MaxTokensSynth,
        "--debate-temp", [string]$DebateTemp,
        "--synth-temp", [string]$SynthTemp,
        "--seed", [string]$Seed,
        "--turn-timeout-sec", [string]$TurnTimeoutSec,
        "--synth-timeout-sec", [string]$SynthTimeoutSec
    )

    $effectiveSystemPromptFile = $SystemPromptFile
    if ([string]::IsNullOrWhiteSpace($effectiveSystemPromptFile) -and -not [string]::IsNullOrWhiteSpace($env:SOVEREIGN_SYSTEM_PROMPT_FILE)) {
        $effectiveSystemPromptFile = $env:SOVEREIGN_SYSTEM_PROMPT_FILE
    }
    if (-not [string]::IsNullOrWhiteSpace($effectiveSystemPromptFile)) {
        $argList += @("--system-prompt-file", $effectiveSystemPromptFile)
    }

    Log-System "Delegating controlled debate to live_orchestrator.py"
    $previousBrokerOnly = $env:SOVEREIGN_BROKER_ONLY
    $previousBrokerScript = $env:SOVEREIGN_BROKER_SCRIPT
    $previousBrokerSessionId = $env:SOVEREIGN_BROKER_SESSION_ID
    $previousBrokerRoot = $env:SOVEREIGN_BROKER_ROOT
    $previousSafeTheoremMode = $env:SOVEREIGN_SAFE_THEOREM_MODE
    $previousSafeTheoremManifest = $env:SOVEREIGN_SAFE_THEOREM_MANIFEST
    try {
        $env:SOVEREIGN_BROKER_ONLY = "1"
        $env:SOVEREIGN_BROKER_SCRIPT = $PSCommandPath
        $env:SOVEREIGN_BROKER_SESSION_ID = $SessionId
        $env:SOVEREIGN_BROKER_ROOT = $RootResolved
        if ($SafeTheoremMode) {
            $env:SOVEREIGN_SAFE_THEOREM_MODE = "1"
            $env:SOVEREIGN_SAFE_THEOREM_MANIFEST = $ResolvedSafeTheoremManifestPath
        }
        # F-125(k): under Windows PowerShell 5.1 with EAP=Stop, the first stderr line from the
        # orchestrator (a warning, a logged exception, its own error JSON) became a terminating
        # NativeCommandError, so the broker died with exit 1 and the real exit code and output were
        # lost. Run the native call under Continue and keep stderr as plain text.
        $previousEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $output = @(& $PythonExe @argList 2>&1 | ForEach-Object { "$_" })
            $exitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousEap
        }
    }
    finally {
        $env:SOVEREIGN_BROKER_ONLY = $previousBrokerOnly
        $env:SOVEREIGN_BROKER_SCRIPT = $previousBrokerScript
        $env:SOVEREIGN_BROKER_SESSION_ID = $previousBrokerSessionId
        if ($null -eq $previousBrokerRoot) {
            Remove-Item Env:SOVEREIGN_BROKER_ROOT -ErrorAction SilentlyContinue
        } else {
            $env:SOVEREIGN_BROKER_ROOT = $previousBrokerRoot
        }
        if ($SafeTheoremMode) {
            if ($null -eq $previousSafeTheoremMode) {
                Remove-Item Env:SOVEREIGN_SAFE_THEOREM_MODE -ErrorAction SilentlyContinue
            } else {
                $env:SOVEREIGN_SAFE_THEOREM_MODE = $previousSafeTheoremMode
            }
            if ($null -eq $previousSafeTheoremManifest) {
                Remove-Item Env:SOVEREIGN_SAFE_THEOREM_MANIFEST -ErrorAction SilentlyContinue
            } else {
                $env:SOVEREIGN_SAFE_THEOREM_MANIFEST = $previousSafeTheoremManifest
            }
        }
    }
    if ($output) {
        foreach ($line in $output) {
            Log-System "[synth_king] $line"
        }
    }
    if ($exitCode -ne 0) {
        throw "live_orchestrator.py failed with exit code $exitCode"
    }
}

Log-System "SOVEREIGN Broker started"
Log-System "BROKER_ROOT=$RootResolved"
Log-System "Root markers: $($RootMarkerHits -join ', ')"
Log-System "Models: A=$ModelA B=$ModelB C=$ModelC Synth=$ModelSynth"
Log-System "Manifest: $EffectiveManifestPath"
Log-System "Config: Rounds=$DebateRounds MaxTokens/Turn=$MaxTokensPerTurn DebateTemp=$DebateTemp SynthTemp=$SynthTemp Seed=$Seed TurnTimeout=${TurnTimeoutSec}s SynthTimeout=${SynthTimeoutSec}s"
Log-System "Paths: TopicFile=$TopicFile SynthesisFile=$SynthesisFile"
if ($SafeTheoremMode) {
    Log-System "Safe theorem mode active. Manifest=$ResolvedSafeTheoremManifestPath"
}

Write-Host ""
Write-Host "=== SOVEREIGN BROKER ==="
Write-Host "Root         : $RootResolved"
Write-Host "Topic file   : $TopicFile"
Write-Host "Synthesis out: $SynthesisFile"
Write-Host "STOP file    : $StopFile"
Write-Host ""

if (Test-StopRequested) {
    Log-System "STOP file present at startup. Exiting."
    exit 0
}

try {
    $rawTopicPayload = Get-RawTopicPayload
    $sessionId = $env:SOVEREIGN_SESSION_ID
    if ([string]::IsNullOrWhiteSpace($sessionId)) {
        $sessionId = Get-SessionIdFromText -Text $rawTopicPayload
    }
    if ([string]::IsNullOrWhiteSpace($sessionId)) {
        $sessionId = New-SessionId
        Log-System "No session_id found in env or topic payload. Generated session_id=$sessionId"
    } else {
        Log-System "Using session_id=$sessionId"
    }

    $topic = Get-CleanTopic -RawText $rawTopicPayload
    if ([string]::IsNullOrWhiteSpace($topic)) {
        throw "Topic text is empty after parsing."
    }

    Log-Dialog ""
    Log-Dialog "============================================================"
    Log-Dialog "[CONTROLLED SESSION] session_id=$sessionId TOPIC: $topic"
    Log-Dialog "============================================================"
    Log-Dialog ""

    Invoke-SynthKing -Topic $topic -SessionId $sessionId

    if (-not (Test-Path $SynthesisFile)) {
        throw "Canonical synthesis was not written to $SynthesisFile"
    }
    $synthText = Get-Content $SynthesisFile -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($synthText)) {
        throw "Canonical synthesis is empty at $SynthesisFile"
    }

    Log-System "Synthesis written: $SynthesisFile"
    Log-System "Controlled session completed. session_id=$sessionId"
    exit 0
}
catch {
    Log-System "Controlled session aborted. ERROR: $($_.Exception.Message)"
    exit 1
}
