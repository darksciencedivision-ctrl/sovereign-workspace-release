# SOVEREIGN Phase 18.1 — Broker Library Retrieval
# Generated UTC: 2026-05-13T22:39:40Z
# Read-only hook. Does NOT modify broker.ps1.
# Reads library indexes and writes memory context packet to broker inbox.

param(
    [string]$Topic = "",
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [int]$MaxArtifacts = 20,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$LibraryRoot = Join-Path $Root "library"
$InboxPath = Join-Path $Root "broker_v21\inbox\memory_context_packet.json"
$ReportDir = Join-Path $LibraryRoot "reports\semantic_governance"

function Get-UtcNow {
    return ([System.DateTime]::UtcNow).ToString("yyyy-MM-ddTHH:mm:ssZ")
}

function Read-JsonlSafe {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return @() }
    $records = @()
    Get-Content $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -ne "") {
            try { $records += ($line | ConvertFrom-Json) }
            catch { }
        }
    }
    return $records
}

function Read-JsonSafe {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    try { return (Get-Content $Path -Raw -Encoding UTF8 | ConvertFrom-Json) }
    catch { return $null }
}

Write-Host "=== Broker Library Retrieval === DryRun=$DryRun Topic='$Topic'"

# Load registry
$RegistryPath = Join-Path $LibraryRoot "index\artifact_registry.jsonl"
$artifacts = Read-JsonlSafe -Path $RegistryPath

# Filter by topic if provided
$retrieved = @()
if ($Topic -ne "" -and $artifacts.Count -gt 0) {
    $retrieved = $artifacts | Where-Object {
        $_.path -like "*$Topic*" -or $_.subsystem -like "*$Topic*" -or $_.artifact_type -like "*$Topic*"
    } | Select-Object -First $MaxArtifacts
} else {
    $retrieved = $artifacts | Where-Object {
        $_.canonical_status -in @("canonical", "research_evidence")
    } | Select-Object -First $MaxArtifacts
}

# Load canonical constraints from runtime contract
$ContractPath = Join-Path $LibraryRoot "index\runtime_contract.json"
$contract = Read-JsonSafe -Path $ContractPath
$canonicalConstraints = @()
if ($contract) {
    $canonicalConstraints = @(
        "fail_closed=$($contract.fail_closed)",
        "deletion_enabled=$($contract.deletion_enabled)",
        "no_uri_authority_expansion=$($contract.no_uri_authority_expansion)"
    )
}

# Load contradictions
$ContradictionsPath = Join-Path $LibraryRoot "index\contradiction_registry.jsonl"
$contradictions = Read-JsonlSafe -Path $ContradictionsPath | Select-Object -First 10

# Load operator decisions
$DecisionsPath = Join-Path $LibraryRoot "memory\operator_decisions\operator_decisions.jsonl"
$decisions = Read-JsonlSafe -Path $DecisionsPath | Select-Object -Last 10

# Load ontology terms
$OntologyPath = Join-Path $LibraryRoot "index\ontology_graph.json"
$ontology = Read-JsonSafe -Path $OntologyPath
$ontologyTerms = @()
if ($ontology -and $ontology.concepts) {
    $ontologyTerms = $ontology.concepts | Select-Object -First 10 | ForEach-Object {
        "$($_.canonical_name) ($($_.concept_id))"
    }
}

$packet = @{
    topic = $Topic
    retrieved_artifacts = @($retrieved)
    canonical_constraints = $canonicalConstraints
    known_contradictions = @($contradictions)
    relevant_prior_decisions = @($decisions)
    ontology_terms = $ontologyTerms
    created_utc = Get-UtcNow
}

$packetJson = $packet | ConvertTo-Json -Depth 10

Write-Host "  Retrieved artifacts: $($retrieved.Count)"
Write-Host "  Canonical constraints: $($canonicalConstraints.Count)"
Write-Host "  Contradictions: $($contradictions.Count)"
Write-Host "  Operator decisions: $($decisions.Count)"
Write-Host "  Ontology terms: $($ontologyTerms.Count)"

if (-not $DryRun) {
    $InboxDir = Split-Path $InboxPath -Parent
    if (-not (Test-Path $InboxDir)) { New-Item -ItemType Directory -Path $InboxDir -Force | Out-Null }
    $packetJson | Out-File -FilePath $InboxPath -Encoding UTF8 -Force
    Write-Host "  Written: $InboxPath"
} else {
    Write-Host "  [DRY RUN] Would write: $InboxPath"
}

# Write report
$ts = Get-UtcNow
$tsFile = $ts -replace "[:\-]", ""
$reportPath = Join-Path $ReportDir "broker_retrieval_$tsFile.md"
if (-not (Test-Path $ReportDir)) { New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null }

@"
# Broker Library Retrieval Report
**Generated UTC:** $ts
**Dry-run:** $DryRun
**Topic:** $Topic

## Summary

- Artifacts retrieved: $($retrieved.Count)
- Canonical constraints: $($canonicalConstraints.Count)
- Contradictions: $($contradictions.Count)
- Operator decisions: $($decisions.Count)
- Ontology terms: $($ontologyTerms.Count)
- Output: ``$InboxPath``
"@ | Out-File -FilePath $reportPath -Encoding UTF8
Write-Host "  Report: $reportPath"
