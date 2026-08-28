# Start-OpenCode-FullAccess.ps1 - operator tooling only. Not part of the shell; not a module launch.
# Launches OpenCode with the Production Workspace as project root (AGENTS.md + opencode.json
# full-access config auto-loaded), after verifying the envelope files, the LOOP-01 directive,
# and host quiescence. Copies the LOOP-01 kickoff to the clipboard.

$Workspace = "D:\Product Software\Production Workspace"

# 1. Required files - fail fast.
foreach ($f in @(
    "AGENTS.md",
    "CLAUDE.md",
    "opencode.json",
    "BUILD-DIRECTIVE-SWS-UI-001.md",
    "docs\OX-ALPHA-DIRECTIVE-LOOP-01.md",
    "docs\OX-ALPHA-DIRECTIVE-GATE5.md",
    "docs\REMEDIATION-03.md",
    "docs\THEME-BASELINE-v2.md",
    "evidence\GATE-LEDGER.json",
    "evidence\OPERATOR-INSTRUCTIONS.log"
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $Workspace $f))) { throw "Missing: $f" }
}
$a = (Get-FileHash (Join-Path $Workspace "AGENTS.md") -Algorithm SHA256).Hash
$c = (Get-FileHash (Join-Path $Workspace "CLAUDE.md") -Algorithm SHA256).Hash
if ($a -ne $c) { throw "AGENTS.md and CLAUDE.md differ - envelope copies out of sync" }
Write-Host "Envelope sha256: $($a.ToLower())"

# 2. Host quiescence - shell/module ports free, no module processes.
$busy = Get-NetTCPConnection -State Listen -LocalPort 5175,8700,5180 -ErrorAction SilentlyContinue
if ($busy) { $busy | Format-Table LocalAddress,LocalPort,OwningProcess; throw "HOST_NOT_QUIESCENT: a module/shell port is already listening" }
$procs = Get-Process python,electron,node -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Workspace\modules\*" }
if ($procs) { $procs | Format-Table Id,ProcessName,Path; throw "HOST_NOT_QUIESCENT: module process still running" }

# 3. SOW tree spot check - warn (do not block) if the protected tree looks active.
$SowTree = "D:\multi model terminal app\sovereign-orchestration-workspace"
if (Test-Path -LiteralPath $SowTree) {
    $env:GIT_OPTIONAL_LOCKS = '0'
    $h1 = (& git -C $SowTree rev-parse HEAD) 2>$null
    Start-Sleep -Seconds 5
    $h2 = (& git -C $SowTree rev-parse HEAD) 2>$null
    Remove-Item Env:\GIT_OPTIONAL_LOCKS -ErrorAction SilentlyContinue
    if ($h1 -ne $h2) { Write-Warning "SOW tree HEAD moved during a 5s window ($h1 -> $h2). Stop the SOW loop before pasting the kickoff, or LOOP-01 will stop at G1." }
    else { Write-Host "SOW tree HEAD stable over 5s: $h1 (LOOP-01 still proves 60s quiescence itself)" }
}

# 4. LOOP-01 kickoff to clipboard.
$kickoff = @"
Before anything, report which shell your bash tool runs; if not PowerShell, run cmdlets via powershell.exe -NoProfile -Command. Confirm AGENTS.md from this project root is loaded; if not, say so and stop.

Read from disk, in order: BUILD-DIRECTIVE-SWS-UI-001.md, docs/OX-ALPHA-DIRECTIVE-LOOP-01.md, docs/OX-ALPHA-DIRECTIVE-GATE5.md, docs/REMEDIATION-03.md, docs/STOP-REPORT-SOW-TREE-ACTIVITY.md, docs/THEME-BASELINE-v2.md, docs/REVIEW-BUILD-05.md, evidence/GATE-LEDGER.json, evidence/OPERATOR-INSTRUCTIONS.log, evidence/rem03/sow-git-external-change.txt. Then execute docs/OX-ALPHA-DIRECTIVE-LOOP-01.md in full.

OPERATOR INSTRUCTION: All modules are at production baseline and none are being worked on; the SOW loop writer is stopped. STOP-REPORT-SOW-TREE-ACTIVITY option 2 is selected - capture fresh REM-03 baselines after proving the tree quiescent, preserving the originals. LOOP-01 is authorized: run the goal-state loop to completion without pausing, all stage pauses waived, every long-running helper started detached. If the protected tree moves again, STOP and name the files. Log this instruction verbatim with UTC in evidence/OPERATOR-INSTRUCTIONS.log before any other mutation, and end your final message with the section 14 claim line LOOP-01 section 7 specifies.
"@
Set-Clipboard -Value $kickoff
Write-Host "LOOP-01 kickoff copied to clipboard."

# 5. Launch OpenCode with the workspace as project root.
if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) { throw "opencode not on PATH" }
Set-Location -LiteralPath $Workspace
Write-Host "Launching OpenCode in $(Get-Location). Paste (Ctrl+V) the kickoff as the first message."
& opencode
