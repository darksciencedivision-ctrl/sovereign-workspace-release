# SOVEREIGN Phase 18.3 - Broker Memory Context Validation
# Generated UTC at runtime.
# Simulates packet generation from approved retrieval sources only.

param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string[]]$Topics = @(),
    [string]$OutDir = "",
    [string]$Stamp = "",
    [switch]$WriteInbox
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $OutDir = Join-Path $Root "praxis_validation\results"
}

function Get-UtcNow {
    return ([DateTime]::UtcNow).ToString("yyyy-MM-ddTHH:mm:ssZ")
}

function Get-StampNow {
    return ([DateTime]::UtcNow).ToString("yyyyMMddTHHmmssZ")
}

function Read-JsonSafe {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    try {
        return (Get-Content $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Read-JsonlSafe {
    param([string]$Path)
    $records = @()
    if (-not (Test-Path $Path)) { return $records }
    Get-Content $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line) {
            try {
                $records += ($line | ConvertFrom-Json)
            } catch {
            }
        }
    }
    return $records
}

function Read-TextSafe {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return "" }
    try {
        return (Get-Content $Path -Raw -Encoding UTF8)
    } catch {
        return ""
    }
}

function Get-Tokens {
    param([string]$Text)
    $matches = [regex]::Matches(($Text | ForEach-Object { "$_".ToLowerInvariant() }), "[a-z0-9]+")
    $stop = @(
        "a","an","and","are","as","at","be","by","can","did","do","does","for","from","how","in","is","it","of",
        "on","or","that","the","this","to","was","what","when","where","which","who","why","with"
    )
    $tokens = @()
    foreach ($match in $matches) {
        $token = $match.Value.Trim()
        if ($token.Length -ge 2 -and -not ($stop -contains $token)) {
            $tokens += $token
        }
    }
    return $tokens
}

function Get-MatchedTerms {
    param(
        [string[]]$QueryTokens,
        [string]$Haystack
    )
    $lower = "$Haystack".ToLowerInvariant()
    $hits = @()
    foreach ($token in ($QueryTokens | Select-Object -Unique)) {
        if ($lower.Contains($token)) {
            $hits += $token
        }
    }
    return ($hits | Select-Object -Unique)
}

function Make-Snippet {
    param(
        [string]$Text,
        [string[]]$MatchedTerms
    )
    if (-not $Text) { return "" }
    $clean = $Text -replace "\r\n", "`n" -replace "\r", "`n"
    if (-not $MatchedTerms -or $MatchedTerms.Count -eq 0) {
        return $clean.Substring(0, [Math]::Min(240, $clean.Length))
    }
    $lower = $clean.ToLowerInvariant()
    $first = -1
    foreach ($term in $MatchedTerms) {
        $index = $lower.IndexOf($term)
        if ($index -ge 0 -and ($first -lt 0 -or $index -lt $first)) {
            $first = $index
        }
    }
    if ($first -lt 0) {
        return $clean.Substring(0, [Math]::Min(240, $clean.Length))
    }
    $start = [Math]::Max(0, $first - 80)
    $length = [Math]::Min(260, $clean.Length - $start)
    return $clean.Substring($start, $length)
}

if (-not $Stamp) {
    $Stamp = Get-StampNow
}

$safeSources = @(
    (Join-Path $Root "library\config\runtime_mode.json"),
    (Join-Path $Root "library\config\clu_runtime_policy.json"),
    (Join-Path $Root "library\index\runtime_contract.json"),
    (Join-Path $Root "library\index\ontology_graph.json"),
    (Join-Path $Root "library\memory\operator_decisions\compression_batch_001_approval_20260514T003317Z.json"),
    (Join-Path $Root "library\memory\operator_decisions\semantic_drift_operator_confirmation_20260514T003317Z.json"),
    (Join-Path $Root "library\memory\operator_decisions\semantic_drift_operator_decisions_20260513T234318Z.jsonl"),
    (Join-Path $Root "library\reports\PHASE18_2_COMPLETION_FOR_18_3_REVIEW_20260514T004916Z.md"),
    (Join-Path $Root "library\reports\compression\compression_quality_report_batch_001_20260514T004209Z.md"),
    (Join-Path $Root "library\reports\praxis_embedding_health\praxis_side_by_side_comparison_20260514T004334Z.md"),
    (Join-Path $Root "library\reports\archive_bloat\deletion_safety_audit_20260514T004450Z.md"),
    (Join-Path $Root "library\reports\semantic_governance\replay_dependency_audit_20260514T004450Z.md"),
    (Join-Path $Root "library\reports\semantic_governance\semantic_drift_confirmation_20260514T003317Z.md")
)
$safeSources += @(Get-ChildItem -Path (Join-Path $Root "library\memory\compressed\batch_001") -File -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })

$indexedSources = @()
foreach ($path in $safeSources) {
    if (-not (Test-Path $path)) { continue }
    $text = Read-TextSafe -Path $path
    $indexedSources += [pscustomobject]@{
        path = $path
        text = $text
        tokens = @(Get-Tokens -Text ($path + " " + $text))
    }
}

$contract = Read-JsonSafe -Path (Join-Path $Root "library\index\runtime_contract.json")
$ontology = Read-JsonSafe -Path (Join-Path $Root "library\index\ontology_graph.json")
$contradictions = Read-JsonlSafe -Path (Join-Path $Root "library\index\contradiction_registry.jsonl")
$decisionLog = Read-JsonlSafe -Path (Join-Path $Root "library\memory\operator_decisions\semantic_drift_operator_decisions_20260513T234318Z.jsonl")
$compressionApproval = Read-JsonSafe -Path (Join-Path $Root "library\memory\operator_decisions\compression_batch_001_approval_20260514T003317Z.json")
$semanticConfirmation = Read-JsonSafe -Path (Join-Path $Root "library\memory\operator_decisions\semantic_drift_operator_confirmation_20260514T003317Z.json")

if (-not (Test-Path $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}

$topicList = @($Topics | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
if ($topicList.Count -eq 1 -and $topicList[0].Contains("|")) {
    $topicList = @($topicList[0].Split("|") | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}
if ($topicList.Count -eq 0) {
    $topicList = @(
        "Phase 18.2 completion status",
        "deletion policy",
        "CLU disabled status",
        "semantic drift decisions",
        "compression batch 001"
    )
}

$packets = @()
foreach ($topic in $topicList) {
    $queryTokens = @(Get-Tokens -Text $topic)
    $hits = @()
    foreach ($source in $indexedSources) {
        $matched = @(Get-MatchedTerms -QueryTokens $queryTokens -Haystack ($source.path + " " + $source.text))
        if ($matched.Count -eq 0) { continue }
        $score = [Math]::Round(($matched.Count / [Math]::Max(1, ($queryTokens | Select-Object -Unique).Count)) + 0.1, 4)
        $hits += [pscustomobject]@{
            path = $source.path
            score = $score
            matched_terms = $matched
            snippet = Make-Snippet -Text $source.text -MatchedTerms $matched
        }
    }
    $topHits = @($hits | Sort-Object @{Expression = "score"; Descending = $true}, @{Expression = "path"; Descending = $false} | Select-Object -First 8)
    $ontologyTerms = @()
    if ($ontology -and $ontology.concepts) {
        foreach ($concept in $ontology.concepts) {
            $conceptText = "$($concept.canonical_name) $($concept.definition) $($concept.aliases -join ' ')"
            $matchedConceptTerms = @(Get-MatchedTerms -QueryTokens $queryTokens -Haystack $conceptText)
            if ($matchedConceptTerms.Count -gt 0) {
                $ontologyTerms += [pscustomobject]@{
                    concept_id = $concept.concept_id
                    canonical_name = $concept.canonical_name
                    matched_terms = $matchedConceptTerms
                }
            }
        }
        if ($ontologyTerms.Count -eq 0) {
            $ontologyTerms = @($ontology.concepts | Select-Object -First 5 | ForEach-Object {
                [pscustomobject]@{
                    concept_id = $_.concept_id
                    canonical_name = $_.canonical_name
                    matched_terms = @()
                }
            })
        }
    }

    $relevantDecisions = @()
    if ($compressionApproval) {
        $relevantDecisions += [pscustomobject]@{
            source = "compression_batch_001_approval"
            decision = $compressionApproval.approval_status
            notes = $compressionApproval.notes
        }
    }
    if ($semanticConfirmation) {
        $relevantDecisions += [pscustomobject]@{
            source = "semantic_drift_operator_confirmation"
            decision = $semanticConfirmation.decision
            notes = $semanticConfirmation.notes
        }
    }
    foreach ($record in ($decisionLog | Select-Object -First 5)) {
        $relevantDecisions += [pscustomobject]@{
            source = "semantic_drift_operator_decisions"
            decision = $record.decision
            notes = $record.reason
        }
    }

    $packet = [ordered]@{
        topic = $topic
        created_utc = Get-UtcNow
        simulated = $true
        retrieved_artifacts = $topHits
        canonical_constraints = @(
            "fail_closed=$($contract.fail_closed)",
            "deletion_enabled=$($contract.deletion_enabled)",
            "DELETE_DISABLED=$($contract.DELETE_DISABLED)",
            "no_direct_sandbox_writes=$($contract.no_direct_sandbox_writes)",
            "no_raw_archive_runtime_retrieval=$($contract.no_raw_archive_runtime_retrieval)"
        )
        known_contradictions = @($contradictions | Select-Object -First 5)
        relevant_prior_decisions = $relevantDecisions
        ontology_terms = $ontologyTerms
        safety = [ordered]@{
            raw_archive_traversal = $false
            mutation_performed = $false
            write_inbox = [bool]$WriteInbox
        }
    }

    $packetPath = Join-Path $OutDir ("broker_memory_context_packet_" + ($topic -replace "[^A-Za-z0-9]+", "_").Trim("_").ToLowerInvariant() + "_" + $Stamp + ".json")
    $packet | ConvertTo-Json -Depth 20 | Set-Content -Path $packetPath -Encoding UTF8
    $packets += [pscustomobject]@{
        topic = $topic
        packet_path = $packetPath
        artifact_count = $topHits.Count
        ontology_term_count = $ontologyTerms.Count
        contradiction_count = (@($contradictions | Select-Object -First 5)).Count
        operator_decision_count = $relevantDecisions.Count
    }

    if ($WriteInbox) {
        $inboxPath = Join-Path $Root "broker_v21\inbox\memory_context_packet.json"
        $inboxDir = Split-Path $inboxPath -Parent
        if (-not (Test-Path $inboxDir)) {
            New-Item -ItemType Directory -Path $inboxDir -Force | Out-Null
        }
        $packet | ConvertTo-Json -Depth 20 | Set-Content -Path $inboxPath -Encoding UTF8
    }
}

$summary = [ordered]@{
    generated_utc = Get-UtcNow
    stamp = $Stamp
    simulated = (-not $WriteInbox)
    out_dir = $OutDir
    packet_count = $packets.Count
    packets = $packets
    safety = [ordered]@{
        raw_archive_traversal = $false
        mutation_performed = $false
        write_inbox = [bool]$WriteInbox
    }
}

$summaryPath = Join-Path $OutDir ("broker_memory_context_summary_" + $Stamp + ".json")
$summary | ConvertTo-Json -Depth 20 | Set-Content -Path $summaryPath -Encoding UTF8
Write-Host $summaryPath
