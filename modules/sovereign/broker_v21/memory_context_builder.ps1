# SOVEREIGN Phase 18.1 — Broker Memory Context Builder
# Generated UTC: 2026-05-13T22:39:40Z
# Read-only. Builds a memory context packet from library indexes.
# Writes packet to broker_v21/inbox/memory_context_packet.json.
# Does NOT modify broker.ps1.

param(
    [string]$Topic = "",
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [int]$MaxArtifacts = 30,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$LibraryRoot = Join-Path $Root "library"
$PacketPath = Join-Path $Root "broker_v21\inbox\memory_context_packet.json"
$ReportDir = Join-Path $LibraryRoot "reports\semantic_governance"

function Get-UtcNow {
    ([System.DateTime]::UtcNow).ToString("yyyy-MM-ddTHH:mm:ssZ")
}

function Read-JsonSafe([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    try { Get-Content $Path -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $null }
}

function Read-JsonlSafe([string]$Path) {
    $out = @()
    if (-not (Test-Path $Path)) { return $out }
    Get-Content $Path -Encoding UTF8 | ForEach-Object {
        $l = $_.Trim()
        if ($l) { try { $out += ($l | ConvertFrom-Json) } catch {} }
    }
    $out
}

function Get-PythonExe([string]$ResolvedRoot) {
    $venvPython = Join-Path $ResolvedRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) { return $venvPython }
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) { return $pythonCmd.Source }
    throw "Python runtime not found for ecological memory prioritizer."
}

Write-Host "=== Memory Context Builder === Topic='$Topic' DryRun=$DryRun"

$pythonExe = Get-PythonExe -ResolvedRoot $Root
$prioritizerPath = Join-Path $Root "broker_v21\memory_prioritizer.py"
if (-not (Test-Path $prioritizerPath)) {
    throw "Missing memory prioritizer: $prioritizerPath"
}

$invokeArgs = @(
    $prioritizerPath,
    "--topic", $Topic,
    "--root", $Root,
    "--max-items", "$MaxArtifacts",
    "--out", $PacketPath
)
if ($DryRun) {
    $invokeArgs += "--dry-run"
}

& $pythonExe @invokeArgs
if ($LASTEXITCODE -ne 0) {
    throw "memory_prioritizer.py exited with code $LASTEXITCODE"
}

$inspectionPath = $PacketPath
if ($DryRun -or -not (Test-Path $inspectionPath)) {
    $inspectionPath = Join-Path $Root "ecology\memory_packets\latest_memory_packet.json"
}

$packet = Read-JsonSafe $inspectionPath
if (-not $packet) {
    throw "Ecological memory packet was not produced: $inspectionPath"
}

$selected = @($packet.selected_items)
$suppressed = @($packet.suppressed_results)
$constraints = @($packet.canonical_constraints)
$ontTerms = @($packet.ontology_terms)
$explanations = @($packet.ranking_explanations)

Write-Host "  Packet: $($selected.Count) selected | $($suppressed.Count) suppressed | $($ontTerms.Count) ontology terms"
if (-not $DryRun) {
    Write-Host "  Written: $PacketPath"
} else {
    Write-Host "  [DRY RUN] Broker inbox write skipped; ecological packet inspected at: $inspectionPath"
}

# Report
$ts = Get-UtcNow
$tsFile = $ts -replace "[:\-]",""
$rpt = Join-Path $ReportDir "broker_read_hooks_$tsFile.md"
if (-not (Test-Path $ReportDir)) { New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null }
@"
# Broker Read Hooks Report
**Generated UTC:** $ts
**Dry-run:** $DryRun

## Memory Context Packet Schema

| Field | Description |
|-------|-------------|
| topic | Query topic |
| retrieved_artifacts / selected_items | Explainable, semantically ranked memory items |
| canonical_constraints | Runtime contract constraints |
| known_contradictions / contradictions | Surfaced contradiction traces |
| relevant_prior_decisions | Operator decisions and confirmations |
| ontology_terms | Ontology-aligned concepts used in ranking |
| truth_weights | Truth-weight signals linked to retrieval |
| ranking_explanations | Inspectable reasons for ranking decisions |
| suppressed_results | Inspectable reasons for suppression |
| attention_budget | Budget allocation and constraint state |
| created_utc | Packet creation timestamp |

## Output Path

``$PacketPath``

## Ecological Retrieval Summary

- Selected items: $($selected.Count)
- Suppressed items: $($suppressed.Count)
- Canonical constraints: $($constraints.Count)
- Ontology terms: $($ontTerms.Count)
- Ranking explanations: $($explanations.Count)
- Explainability report: $($packet.explainability_report_path)
- Arbitration report: $($packet.arbitration.report_path)

## Safety

- broker.ps1 NOT modified
- Retrieval is read-only and fail-closed
- No URI shell execution added
- No file deletion or movement
- Contradictions are surfaced, not silently suppressed
- Raw archive retrieval remains blocked
"@ | Out-File -FilePath $rpt -Encoding UTF8
Write-Host "  Report: $rpt"
