# Start-OpenCode-CP-MERGE-01.ps1 - operator tooling only. Not part of the shell; not a module launch.
# Launches OX ALPHA (OpenCode) at the Production Workspace root for the merged CP-01 + CP-02 loop.
#
# The merge is safe because there is exactly ONE writer. This launcher's job is to prove that:
# it refuses to start if the superseded CP-01 session still has a live writer, and it verifies
# that the Band 0 evidence the merged run ADOPTS is actually present before handing over.

$ErrorActionPreference = 'Stop'
$Workspace = "D:\Product Software\Production Workspace"
if (-not (Test-Path -LiteralPath $Workspace)) { throw "Workspace not found: $Workspace" }

# ---- 1. Envelope + goal-definition files must exist -------------------------------
$required = @(
    'AGENTS.md','CLAUDE.md','opencode.json','BUILD-DIRECTIVE-SWS-UI-001.md',
    'docs\SWS-UI-001-v1.2-ADDENDUM-01.md',
    'docs\SWS-UI-001-v1.2-ADDENDUM-02.md',
    'docs\SWS-UI-001-v1.2-ADDENDUM-03.md',
    'docs\OX-ALPHA-DIRECTIVE-CP-01.md',
    'docs\OX-ALPHA-DIRECTIVE-CP-02.md',
    'docs\OX-ALPHA-DIRECTIVE-CP-MERGE-01.md',
    'docs\OX-ALPHA-CP-MERGE-01-PASTE.md',
    'docs\CP-02-MODERNIZATION-ASSESSMENT.md',
    'docs\CP-02-REVIEW-01.md','docs\CP-02-CONFLICT-AUDIT.md','docs\CP-01-WATCH-01.md',
    'docs\THEME-BASELINE-v3.md',
    'evidence\GATE-LEDGER.json','evidence\OPERATOR-INSTRUCTIONS.log'
)
foreach ($f in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $Workspace $f))) { throw "Missing: $f" }
}
$a = (Get-FileHash (Join-Path $Workspace 'AGENTS.md') -Algorithm SHA256).Hash
$c = (Get-FileHash (Join-Path $Workspace 'CLAUDE.md') -Algorithm SHA256).Hash
if ($a -ne $c) { throw "AGENTS.md and CLAUDE.md differ - envelope copies out of sync" }
Write-Host "Envelope sha256: $($a.ToLower())"
foreach ($f in @('docs\SWS-UI-001-v1.2-ADDENDUM-03.md','docs\OX-ALPHA-DIRECTIVE-CP-MERGE-01.md')) {
    Write-Host ("{0}  {1}" -f (Get-FileHash (Join-Path $Workspace $f) -Algorithm SHA256).Hash.ToLower(), $f)
}

# ---- 2. Adopted Band 0 evidence must be present ------------------------------------
Write-Host ""
Write-Host "-- adopted CP-01 Band 0 evidence (ADD-03 section 2) --"
$adopted = @(
    'evidence\cp01\session-start.txt',
    'evidence\cp01\tools\goalcheck.py',
    'evidence\cp01\before\HASHES.txt',
    'evidence\cp01\test-run-before.txt',
    'evidence\cp01\sow-git-inspect-1.txt',
    'evidence\cp01\sow-git-inspect-2.txt',
    'evidence\cp01\manifests\manifest-cp01-before-product-software.txt',
    'evidence\cp01\manifests\manifest-cp01-before-multi-model-terminal-app.txt',
    'evidence\cp01\manifests\manifest-cp01-before-sovereign-distillery.txt',
    'evidence\cp01\manifests\manifest-cp01-before-sov-1.txt',
    'evidence\cp01\manifests\manifest-cp01-before-token-piggy-bank.txt'
)
$missing = @()
foreach ($f in $adopted) {
    $p = Join-Path $Workspace $f
    if (Test-Path -LiteralPath $p) { Write-Host ("  ok    {0}" -f $f) }
    else { $missing += $f; Write-Warning ("  MISS  {0}" -f $f) }
}
if ($missing) { throw "ADOPTED_EVIDENCE_MISSING: the merged run expects CP-01 Band 0 on disk. Missing $($missing.Count) artifact(s)." }

$ss = (Get-FileHash (Join-Path $Workspace 'evidence\cp01\session-start.txt') -Algorithm SHA256).Hash.ToLower()
$expect = '7eef5d0aded54e0fd80552a05c069854c3877a458283b00143febe0be29e0d78'
if ($ss -ne $expect) { Write-Warning "session-start.txt hash $ss differs from the ADD-03 record $expect - the builder re-verifies at M0.2 and will report it." }
else { Write-Host "  session-start.txt matches the ADD-03 record." }

# ---- 3. The superseded CP-01 session must have no live writer ----------------------
Write-Host ""
Write-Host "-- single-writer check: sampling evidence\cp01 for 45s --"
function Get-TreeStamp($p) {
    (Get-ChildItem -LiteralPath $p -Recurse -File -ErrorAction SilentlyContinue |
     Sort-Object FullName | ForEach-Object { "$($_.FullName)|$($_.Length)|$($_.LastWriteTimeUtc.Ticks)" }) -join "`n"
}
$s1 = Get-TreeStamp (Join-Path $Workspace 'evidence\cp01')
Start-Sleep -Seconds 45
$s2 = Get-TreeStamp (Join-Path $Workspace 'evidence\cp01')
if ($s1 -ne $s2) { throw "CONCURRENT_WRITER: evidence\cp01 changed during the sample. Close the superseded CP-01 OpenCode session before starting the merged run." }
Write-Host "  quiescent - no live CP-01 writer."

# ---- 4. Host quiescence (blocking) - 5183 included for the CP-02 bands -------------
$ports = 5175, 8700, 8765, 5180, 5183
$listening = Get-NetTCPConnection -State Listen -LocalPort $ports -ErrorAction SilentlyContinue
if ($listening) {
    $listening | ForEach-Object {
        $owner = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        Write-Warning ("port {0} held by pid {1} {2}" -f $_.LocalPort, $_.OwningProcess, $owner.Path)
    }
    $only8765 = @($listening | Where-Object { $_.LocalPort -ne 8765 }).Count -eq 0
    if ($only8765) {
        Write-Warning "Only 8765 is held - that is the operator's Token Center. ADD-03 A-3 authorizes the builder to stop it by pid immediately before Gate 8i. Proceeding."
    } else {
        throw "HOST_NOT_QUIESCENT: a module/shell/llama.cpp port is listening. Stop it, or record it as EXTERNAL evidence first."
    }
}
$procs = Get-Process python, electron, node -ErrorAction SilentlyContinue |
         Where-Object { $_.Path -like "$Workspace\modules\*" -or $_.Path -like "$Workspace\runtime\*" }
if ($procs) {
    $procs | ForEach-Object { Write-Warning ("process {0} {1}" -f $_.Id, $_.Path) }
    throw "HOST_NOT_QUIESCENT: a module or runtime process is still running"
}

# ---- 5. Provider-spend contradiction (the builder STOPs on it at M0.5) -------------
$liveOp = Join-Path $Workspace 'modules\sow\config\live_operation.json'
if (Test-Path -LiteralPath $liveOp) {
    $lo = Get-Content -LiteralPath $liveOp -Raw | ConvertFrom-Json
    if ($lo.live_operation_authorized -eq $true) {
        Write-Warning "live_operation_authorized = true while this package authorizes no provider spend."
        Write-Warning "  providers: $($lo.scope.providers -join ', ')"
        Write-Warning "  The run will STOP at M0.5 with PROVIDER_SPEND_CONTRADICTION until you reconcile this."
        Write-Warning "  Resolve it now - narrow the config, or widen the authorization - or expect an immediate stop report."
    }
}

# ---- 6. Protected-tree spot check (warn-only) --------------------------------------
$env:GIT_OPTIONAL_LOCKS = '0'
foreach ($t in @('D:\multi model terminal app\sovereign-orchestration-workspace','D:\Sovereign Distillery','D:\Sov 1','D:\Token Piggy Bank')) {
    if (-not (Test-Path -LiteralPath $t)) { Write-Warning "protected tree absent: $t"; continue }
    if (Test-Path -LiteralPath (Join-Path $t '.git')) {
        $h1 = git -C $t rev-parse HEAD 2>$null; Start-Sleep -Seconds 3; $h2 = git -C $t rev-parse HEAD 2>$null
        if ($h1 -ne $h2) { Write-Warning "$t HEAD moved - the run will stop at M0.2" } else { Write-Host ("quiescent: {0}  {1}" -f $t, $h1) }
    } else { Write-Host "present (no git): $t" }
}
Remove-Item Env:\GIT_OPTIONAL_LOCKS -ErrorAction SilentlyContinue
Write-Host "note: D:\Token Piggy Bank\data\** is excluded from the baseline by ADD-03 A-1 - its sqlite drifts while the app runs."

# ---- 7. Kickoff to clipboard -------------------------------------------------------
Set-Clipboard -Value (Get-Content -LiteralPath (Join-Path $Workspace 'docs\OX-ALPHA-CP-MERGE-01-PASTE.md') -Raw)
Write-Host ""
Write-Host "CP-MERGE-01 kickoff copied to clipboard. Paste with Ctrl+V as the FIRST message of the session."
Write-Host "20 gates: 8a-8j then 9a-9j. Order is the safety argument - CP-01 completes before CP-02 begins."
Write-Host "This package promotes nothing. Ollama stays the production default."
Write-Host ""

# ---- 8. Launch ---------------------------------------------------------------------
if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) { throw "opencode not on PATH" }
Set-Location -LiteralPath $Workspace
& opencode
