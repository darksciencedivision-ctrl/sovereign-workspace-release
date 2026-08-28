# Autonomous build loop runner v2 - Sovereign Orchestration Workspace
# Usage:  powershell -ExecutionPolicy Bypass -File tools\loop\run_loop.ps1
# Drives Claude Code through AUTONOMOUS_BUILD_DIRECTIVE.md until COMPLETE or BLOCKED.
param(
  [int]$MaxIterations = 300,
  [int]$StallLimit = 5,
  [ValidateSet("claude")]
  [string]$Builder = "claude",
  [string]$Model = ""   # optional --model slug for the builder CLI (e.g. claude-opus-4-5); default = CLI default
)
$ErrorActionPreference = "Stop"
$modelArgs = @()
if ($Model) {
  $modelArgs = @("--model", $Model)
  Write-Host "[loop] builder model override: $Model (pre-flight will verify the CLI accepts it)"
}
$repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $repo
$stateFile  = Join-Path $repo "docs\loop\LOOP_STATE.json"
$logDir     = Join-Path $repo "docs\loop\logs"
$promptFile = Join-Path $repo "tools\loop\driver_prompt.txt"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claudeCmd) {
  Write-Host "BLOCKED: Claude Code CLI ('claude') not found on PATH. Install it, then re-run." -ForegroundColor Red
  exit 2
}
Write-Host "[loop] claude resolves to: $($claudeCmd.Source)"
$claudeVer = (& claude --version 2>&1 | Out-String).Trim()
Write-Host "[loop] claude version: $claudeVer"

@"
You are the autonomous builder for this repository. Read AUTONOMOUS_BUILD_DIRECTIVE.md
(all sections, including s9 Phase 14 and s10 operator authorization OP-4/OP-5) and
docs/loop/LOOP_STATE.json now, then execute the Loop Protocol (directive section 3)
for EXACTLY ONE work unit. Reconcile state to git tags first if they disagree. Implement
test-first, self-check every exit criterion with real command output, run the
gate-validator subagent for confirmation (mandatory for high-stakes gates incl. 14A),
write the evidence report, follow the two-commit convention, tag passed gates, update
docs/loop/LOOP_STATE.json (increment iteration; set consecutive_failures correctly;
set status COMPLETE or BLOCKED only per directive section 8), commit the state change,
and exit. Do not ask the operator anything. Do not exceed one work unit.

PRINT-MODE FACT (D-LOOP-2, binding): you are running under 'claude -p'. Your process
ENDS when your turn ends. Background tasks (subagent reviews, test suites, waiters,
heartbeats) DO NOT survive your turn, and NO completion notification will EVER re-invoke
you - 'waiting for notifications' is waiting for something that cannot happen and trips
the stall guard. Therefore: run the gate-validator, spec-auditor, and any test suite IN
THE FOREGROUND and wait for them synchronously INSIDE this turn. Never end a turn
'waiting' or 'standing by'. If LOOP_STATE or an evidence draft claims reviews/suites are
'in flight' from a prior iteration, they are DEAD - re-run them fresh, foreground. If a
unit cannot fit its reviews in one turn, split it: commit an explicit work-in-progress
checkpoint (so the stall guard sees progress) with LOOP_STATE recording exactly what
remains, then complete reviews+finalization as the next unit's first act. If you spawn
ANY child process, watcher, or monitor this turn, poll it to completion (or kill it,
D-LOOP-1) BEFORE the turn ends - in-turn polling is the ONLY mechanism that exists;
'waiting for the monitor notification rather than polling' is choosing a channel that
does not exist and has already killed one iteration (16d.recovery, 2026-07-24).
"@ | Set-Content $promptFile -Encoding UTF8

# ---- runner-level BLOCKED auto-reset (stall guard / login) ----
$state = Get-Content $stateFile -Raw | ConvertFrom-Json
if ($state.status -eq "BLOCKED" -and $state.blocked_reason -match "stall guard|Not logged in|session limit") {
  Write-Host "[loop] clearing runner-level BLOCKED state ($($state.blocked_reason))"
  $state.status = "RUNNING"; $state.blocked_reason = $null; $state.smallest_unblocking_action = $null
  $state | ConvertTo-Json -Depth 10 | Set-Content $stateFile -Encoding UTF8
  git add docs/loop/LOOP_STATE.json | Out-Null
  git commit -q -m "chore(loop): reset runner-level BLOCKED (auth/stall), resume" | Out-Null
}

# Binding D-LOOP-2 path: one foreground `claude -p` process per work unit.
Write-Host "[loop] pre-flight: probing 'claude -p' (may take ~30s)..."
$probeOut = ""
try { $probeOut = (& claude -p "Reply with exactly: OK" @modelArgs 2>&1 | Out-String) } catch { $probeOut = "$_" }
$probeCode = $LASTEXITCODE
if ($null -eq $probeCode) { $probeCode = 0 }
if ($probeCode -ne 0 -or $probeOut -match "Not logged in|Please run /login|Invalid API key") {
  Write-Host ""
  Write-Host "PRE-FLIGHT FAILED (exit=$probeCode). Claude's actual output:" -ForegroundColor Red
  ($probeOut -split "`r?`n" | Select-Object -First 8) | ForEach-Object { Write-Host "  | $_" -ForegroundColor Gray }
  exit 2
}
Write-Host "[loop] pre-flight OK ($claudeVer)"

$lastHead = ""
$stall = 0
for ($i = 1; $i -le $MaxIterations; $i++) {
  $state = Get-Content $stateFile -Raw | ConvertFrom-Json
  if ($state.status -eq "COMPLETE" -or $state.status -eq "BLOCKED") { break }

  $head = (git rev-parse HEAD).Trim()
  if ($head -eq $lastHead) { $stall++ } else { $stall = 0; $lastHead = $head }
  if ($stall -ge $StallLimit) {
    $state.status = "BLOCKED"
    $state.blocked_reason = "No new commit in $StallLimit consecutive iterations (stall guard)."
    $state.smallest_unblocking_action = "Read the newest file in docs/loop/logs and send it to the build session."
    $state | ConvertTo-Json -Depth 10 | Set-Content $stateFile -Encoding UTF8
    git add docs/loop/LOOP_STATE.json | Out-Null
    git commit -q -m "chore(loop): stall guard tripped" | Out-Null
    break
  }

  $log = Join-Path $logDir ("iter_{0:d3}_{1}.log" -f $i, (Get-Date -Format "yyyyMMdd_HHmmss"))
  Write-Host ("[loop] iteration {0}  step={1}" -f $i, $state.next_step)
  # A native command (claude.exe) writing to stderr must NOT terminate the loop
  # (runner v5, defect D-LOOP-1: a 'Background tasks still running' stderr write with
  # ErrorActionPreference=Stop crashed the script out to the prompt mid-Phase-15D).
  # Cap the print-mode background wait so a lingering live node doesn't burn 10 min.
  $env:CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS = "120000"
  $prevEAP = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & claude -p (Get-Content $promptFile -Raw) --permission-mode acceptEdits @modelArgs 2>&1 | Out-File -FilePath $log -Encoding utf8
    $code = $LASTEXITCODE
  } catch {
    "RUNNER-CAUGHT: $_" | Out-File -FilePath $log -Append -Encoding utf8
    $code = 1
  }
  $ErrorActionPreference = $prevEAP
  if ($null -eq $code) { $code = 0 }
  $tailLines = @(Get-Content $log -Tail 2)
  Write-Host ("[loop]   exit={0}  {1}" -f $code, ($tailLines -join " / "))
  $logText = Get-Content $log -Raw
  if ($logText -match "Not logged in") {
    Write-Host "BLOCKED: Claude Code session expired mid-run. Type claude, then /login, then re-run." -ForegroundColor Red
    exit 2
  }
  $usageLimited = $logText -match "hit your \w+ limit|usage limit"
  if ($usageLimited) {
    $stall = 0  # a usage limit is not a stall; do not trip the guard
    Write-Host "[loop] usage limit reached - waiting 15 minutes, then retrying automatically (Ctrl+C to stop; re-running later resumes from the same step)" -ForegroundColor Yellow
    Start-Sleep -Seconds 900
    continue
  }
  if ($logText -match "Background tasks still running") {
    Write-Host "[loop]   note: iteration left background tasks; the work unit must tear down every spawned process before exit (D-LOOP-1)." -ForegroundColor Yellow
  }
  Start-Sleep -Seconds 2
}

$state = Get-Content $stateFile -Raw | ConvertFrom-Json
switch ($state.status) {
  "COMPLETE" {
    Write-Host ""
    Write-Host "==============================================" -ForegroundColor Green
    Write-Host " BUILD COMPLETE - read FINAL_LIVE_REPORT.md (latest addendum at end) " -ForegroundColor Green
    Write-Host "==============================================" -ForegroundColor Green
    exit 0
  }
  "BLOCKED" {
    Write-Host ""
    Write-Host "BUILD BLOCKED: $($state.blocked_reason)" -ForegroundColor Red
    Write-Host "Smallest unblocking action: $($state.smallest_unblocking_action)" -ForegroundColor Yellow
    exit 2
  }
  default {
    Write-Host "Loop ended at MaxIterations=$MaxIterations (status=$($state.status)). Re-run to continue." -ForegroundColor Yellow
    exit 1
  }
}
