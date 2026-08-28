# Start-Loop-Resume.ps1 - operator tooling only. Not part of the shell; not a module launch.
# Fresh OpenCode session for resuming LOOP-01 with a MINIMAL first prompt.
# The heavy artifacts (goalcheck oracle, helper drivers) already exist, so this run
# reads almost nothing up front - keeping every request small.

$Workspace = "D:\Product Software\Production Workspace"

# 1. Required files.
foreach ($f in @(
    "AGENTS.md",
    "opencode.json",
    "docs\OX-ALPHA-DIRECTIVE-LOOP-01.md",
    "evidence\loop5\tools\goalcheck.py",
    "evidence\GATE-LEDGER.json"
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $Workspace $f))) { throw "Missing: $f" }
}
Write-Host "Workspace files present."

# 2. Helper liveness - report, do not kill. The loop verifies these itself.
$pidFiles = @{
    "watcher" = "evidence\loop5\tools\fswatch-driver.pid"
    "poller"  = "evidence\loop5\tools\poller.pid"
    "shell"   = "evidence\loop5\shell.pid"
}
$alive = @{}
foreach ($k in $pidFiles.Keys) {
    $pf = Join-Path $Workspace $pidFiles[$k]
    if (Test-Path -LiteralPath $pf) {
        $procId = (Get-Content -LiteralPath $pf -Raw).Trim()
        $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
        $alive[$k] = [bool]$p
        Write-Host ("helper {0,-8} pid {1,-7} alive={2}" -f $k, $procId, [bool]$p)
    } else {
        $alive[$k] = $false
        Write-Host ("helper {0,-8} pid-file absent" -f $k)
    }
}
$listen = Get-NetTCPConnection -State Listen -LocalPort 5180 -ErrorAction SilentlyContinue
if ($listen) { Write-Host "shell listening: $($listen.LocalAddress):$($listen.LocalPort)" }
else { Write-Warning "nothing listening on 5180 - the loop will need to restart the shell helper" }

# 3. SOW tree spot check - warn only.
$SowTree = "D:\multi model terminal app\sovereign-orchestration-workspace"
if (Test-Path -LiteralPath $SowTree) {
    $env:GIT_OPTIONAL_LOCKS = '0'
    $h1 = (& git -C $SowTree rev-parse HEAD) 2>$null
    Start-Sleep -Seconds 5
    $h2 = (& git -C $SowTree rev-parse HEAD) 2>$null
    Remove-Item Env:\GIT_OPTIONAL_LOCKS -ErrorAction SilentlyContinue
    if ($h1 -ne $h2) { Write-Warning "SOW tree HEAD moved in 5s ($h1 -> $h2). Stop the SOW loop or LOOP-01 will stop at G1." }
    else { Write-Host "SOW tree HEAD stable over 5s: $h1" }
}

# 4. Lean resume prompt to clipboard - deliberately small; no bulk document reads.
$kickoff = @"
Run this first, before reading anything:

  py -3.12 evidence\loop5\tools\goalcheck.py resume1

Then read ONLY docs/OX-ALPHA-DIRECTIVE-LOOP-01.md and continue that loop from the first failing goal, without pausing, until every goal is TRUE or a STOP condition fires.

Context you do not need to rediscover: the goalcheck oracle and the helper drivers already exist under evidence/loop5/tools/, and the watcher, shell and poller were started detached at 2026-08-24T07:24Z. Verify them; do not restart a helper that is alive. G0 is already TRUE on disk.

Keep every turn small: read a document only when the goal you are working on requires it, never re-read one you have already read, and never echo a large file back into the transcript. Prefer many small tool calls over one large one.

Operator authorizations stand as logged at 2026-08-24T06:42:39Z: REM-03 option 2 fresh baselines, stage pauses waived, every long-running helper detached, STOP and name the files if the protected tree moves. End your final message with the section 7 claim line.
"@
Set-Clipboard -Value $kickoff
Write-Host "Lean resume prompt copied to clipboard."

# 5. Launch OpenCode from the workspace root.
if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) { throw "opencode not on PATH" }
Set-Location -LiteralPath $Workspace
Write-Host "Launching OpenCode in $(Get-Location). Paste (Ctrl+V) as the first message."
& opencode
