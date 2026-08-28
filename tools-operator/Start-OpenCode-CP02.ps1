# Start-OpenCode-CP02.ps1 - operator tooling only. Not part of the shell; not a module launch.
# Launches OX ALPHA (OpenCode) at the Production Workspace root for the CP-02 local-inference loop.
#
# This launcher REFUSES TO START while CP-01 is still live. That is deliberate: CP-01 and CP-02
# overlap on modules/sow/adapters, modules/sow/control_plane, shell/**, and GATE-LEDGER.json.
# Every overlap is safe sequentially and corrupting concurrently. See docs/CP-02-CONFLICT-AUDIT.md.

$ErrorActionPreference = 'Stop'
$Workspace = "D:\Product Software\Production Workspace"

if (-not (Test-Path -LiteralPath $Workspace)) { throw "Workspace not found: $Workspace" }

# ---- 1. Envelope files must exist -------------------------------------------------
$required = @(
    'AGENTS.md',
    'CLAUDE.md',
    'opencode.json',
    'BUILD-DIRECTIVE-SWS-UI-001.md',
    'docs\SWS-UI-001-v1.2-ADDENDUM-02.md',
    'docs\OX-ALPHA-DIRECTIVE-CP-02.md',
    'docs\OX-ALPHA-CP-02-PASTE.md',
    'docs\CP-02-REVIEW-01.md',
    'docs\CP-02-CONFLICT-AUDIT.md',
    'docs\CP-02-MODERNIZATION-ASSESSMENT.md',
    'docs\THEME-BASELINE-v3.md',
    'evidence\GATE-LEDGER.json',
    'evidence\OPERATOR-INSTRUCTIONS.log'
)
foreach ($f in $required) {
    $p = Join-Path $Workspace $f
    if (-not (Test-Path -LiteralPath $p)) { throw "Missing: $f" }
}

$a = (Get-FileHash (Join-Path $Workspace 'AGENTS.md') -Algorithm SHA256).Hash
$c = (Get-FileHash (Join-Path $Workspace 'CLAUDE.md') -Algorithm SHA256).Hash
if ($a -ne $c) { throw "AGENTS.md and CLAUDE.md differ - envelope copies out of sync" }
Write-Host "Envelope sha256: $($a.ToLower())"

foreach ($f in @('docs\SWS-UI-001-v1.2-ADDENDUM-02.md','docs\OX-ALPHA-DIRECTIVE-CP-02.md')) {
    $h = (Get-FileHash (Join-Path $Workspace $f) -Algorithm SHA256).Hash.ToLower()
    Write-Host ("{0}  {1}" -f $h, $f)
}

# ---- 2. CP-01 MUST HAVE EXITED (blocking) -----------------------------------------
Write-Host ""
Write-Host "-- CP-01 exit check (G0.0 precondition) --"

$cp01Report = Join-Path $Workspace 'docs\CP-01-REPORT.md'
$cp01Stop   = Join-Path $Workspace 'docs\STOP-REPORT-CP-01.md'
$hasReport  = Test-Path -LiteralPath $cp01Report
$hasStop    = Test-Path -LiteralPath $cp01Stop

if (-not ($hasReport -or $hasStop)) {
    throw "CP01_STILL_LIVE: neither docs\CP-01-REPORT.md nor docs\STOP-REPORT-CP-01.md exists. CP-01 has not exited. Do not start CP-02."
}
Write-Host ("CP-01 exit artifact: {0}" -f $(if ($hasReport) { 'CP-01-REPORT.md' } else { 'STOP-REPORT-CP-01.md' }))

# Gate keys and reviewer verdict
$ledger = Get-Content -LiteralPath (Join-Path $Workspace 'evidence\GATE-LEDGER.json') -Raw | ConvertFrom-Json
$eightKeys = $ledger.gates.PSObject.Properties.Name | Where-Object { $_ -like '8*' }
if ($hasReport -and -not $eightKeys) {
    throw "CP01_STILL_LIVE: CP-01-REPORT.md exists but no 8* gate keys are in the ledger."
}
foreach ($k in $eightKeys) {
    $g = $ledger.gates.$k
    Write-Host ("  gate {0}: {1} (evaluated_by: {2})" -f $k, $g.status, $(if ($g.evaluated_by) { $g.evaluated_by } else { 'null' }))
    if ($g.status -eq 'CANDIDATE' -and -not $g.evaluated_by) {
        Write-Warning "gate $k is CANDIDATE with no reviewer verdict"
    }
}
$verdicts = Get-ChildItem -LiteralPath (Join-Path $Workspace 'docs') -Filter 'REVIEW-BUILD-*.md' |
            Sort-Object Name | Select-Object -Last 1
Write-Host ("  newest reviewer verdict: {0}" -f $verdicts.Name)
Write-Host "  NOTE: the builder re-verifies G0.0 from disk. This check is advisory triage, not the gate."

# Quiescence of the CP-01 evidence tree - two reads, 60s apart
$cp01Dir = Join-Path $Workspace 'evidence\cp01'
if (Test-Path -LiteralPath $cp01Dir) {
    function Get-TreeStamp($p) {
        (Get-ChildItem -LiteralPath $p -Recurse -File -ErrorAction SilentlyContinue |
         Sort-Object FullName | ForEach-Object { "$($_.FullName)|$($_.Length)|$($_.LastWriteTimeUtc.Ticks)" }) -join "`n"
    }
    Write-Host "  sampling evidence\cp01 for 60s to confirm no active writer..."
    $s1 = Get-TreeStamp $cp01Dir
    Start-Sleep -Seconds 60
    $s2 = Get-TreeStamp $cp01Dir
    if ($s1 -ne $s2) { throw "CP01_STILL_LIVE: evidence\cp01 changed during the 60s sample. A CP-01 writer is active." }
    Write-Host "  evidence\cp01 quiescent."
}

# ---- 3. Host quiescence (blocking) - 5183 joins the set ---------------------------
$ports = 5175, 8700, 8765, 5180, 5183
$listening = Get-NetTCPConnection -State Listen -LocalPort $ports -ErrorAction SilentlyContinue
if ($listening) {
    $listening | ForEach-Object {
        $owner = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        Write-Warning ("port {0} held by pid {1} {2}" -f $_.LocalPort, $_.OwningProcess, $owner.Path)
    }
    throw "HOST_NOT_QUIESCENT: a module/shell/token-center/llama.cpp port is already listening. Stop it, or record it as EXTERNAL evidence first."
}

$modProcs = Get-Process python, electron, node -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -like "$Workspace\modules\*" -or $_.Path -like "$Workspace\runtime\*" }
if ($modProcs) {
    $modProcs | ForEach-Object { Write-Warning ("process {0} {1}" -f $_.Id, $_.Path) }
    throw "HOST_NOT_QUIESCENT: a module or runtime process is still running"
}

# ---- 4. Provider-spend contradiction (advisory - the builder STOPs on it at G0.2) --
$liveOp = Join-Path $Workspace 'modules\sow\config\live_operation.json'
if (Test-Path -LiteralPath $liveOp) {
    $lo = Get-Content -LiteralPath $liveOp -Raw | ConvertFrom-Json
    if ($lo.live_operation_authorized -eq $true) {
        Write-Warning "live_operation_authorized = true while CP-02 authorizes no provider spend."
        Write-Warning "  providers: $($lo.scope.providers -join ', ')"
        Write-Warning "  CP-02 will STOP at G0.2 with PROVIDER_SPEND_CONTRADICTION until you reconcile this."
        Write-Warning "  Resolve it now (narrow the config, or widen the authorization) or expect an immediate stop report."
    }
}

# ---- 5. Protected-tree spot check (warn-only; G0.3 does this properly) -------------
$protected = @(
    'D:\multi model terminal app\sovereign-orchestration-workspace',
    'D:\Sovereign Distillery',
    'D:\Sov 1',
    'D:\Token Piggy Bank'
)
$env:GIT_OPTIONAL_LOCKS = '0'
foreach ($t in $protected) {
    if (-not (Test-Path -LiteralPath $t)) { Write-Warning "protected tree absent: $t"; continue }
    if (Test-Path -LiteralPath (Join-Path $t '.git')) {
        $h1 = git -C $t rev-parse HEAD 2>$null
        Start-Sleep -Seconds 3
        $h2 = git -C $t rev-parse HEAD 2>$null
        if ($h1 -ne $h2) { Write-Warning "$t HEAD moved during spot check - CP-02 will stop at G0.3" }
        else { Write-Host ("quiescent: {0}  {1}" -f $t, $h1) }
    } else {
        Write-Host "present (no git): $t"
    }
}
Remove-Item Env:\GIT_OPTIONAL_LOCKS -ErrorAction SilentlyContinue

# ---- 6. Kickoff to clipboard -------------------------------------------------------
$paste = Get-Content -LiteralPath (Join-Path $Workspace 'docs\OX-ALPHA-CP-02-PASTE.md') -Raw
Set-Clipboard -Value $paste
Write-Host ""
Write-Host "CP-02 kickoff copied to clipboard. Paste with Ctrl+V as the FIRST message of the session."
Write-Host "It carries the ADDENDUM-02 section 9 authorization sentence - the builder logs it verbatim before any mutation."
Write-Host "Reminder: CP-02 promotes nothing. Ollama stays the production default; llama.cpp exits as a candidate."
Write-Host ""

# ---- 7. Launch ---------------------------------------------------------------------
if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) { throw "opencode not on PATH" }
Set-Location -LiteralPath $Workspace
& opencode
