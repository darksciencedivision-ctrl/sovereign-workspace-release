# Start-OpenCode-Gate5.ps1 - operator tooling only. Not part of the shell; not a module launch.
# Opens OpenCode with the Production Workspace as its project root so AGENTS.md is auto-loaded,
# after verifying the envelope files and directive are present and the host is quiescent.

$Workspace = "D:\Product Software\Production Workspace"

# 1. Preconditions the builder will check anyway - fail fast here instead.
foreach ($f in @("AGENTS.md", "BUILD-DIRECTIVE-SWS-UI-001.md", "docs\OX-ALPHA-DIRECTIVE-GATE5.md", "evidence\GATE-LEDGER.json")) {
    if (-not (Test-Path -LiteralPath (Join-Path $Workspace $f))) { throw "Missing: $f" }
}
$a = (Get-FileHash (Join-Path $Workspace "AGENTS.md") -Algorithm SHA256).Hash
$c = (Get-FileHash (Join-Path $Workspace "CLAUDE.md") -Algorithm SHA256).Hash
if ($a -ne $c) { throw "AGENTS.md and CLAUDE.md differ - envelope copies out of sync" }
Write-Host "Envelope sha256: $($a.ToLower())"

$busy = Get-NetTCPConnection -State Listen -LocalPort 5175,8700,5180 -ErrorAction SilentlyContinue
if ($busy) { $busy | Format-Table LocalAddress,LocalPort,OwningProcess; throw "HOST_NOT_QUIESCENT: a module/shell port is already listening" }
$procs = Get-Process python,electron,node -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Workspace\modules\*" }
if ($procs) { $procs | Format-Table Id,ProcessName,Path; throw "HOST_NOT_QUIESCENT: module process still running" }

# 2. Kickoff text to the clipboard so it can be pasted as the first message.
$kickoff = @"
Before step 1, report which shell your bash tool runs (PowerShell, Git Bash, WSL, cmd). If it is not PowerShell, run every PowerShell cmdlet in the directive via powershell.exe -NoProfile -Command "<cmdlet>" - builder tooling, not a module launch. Record the shell name in evidence/gate5/session-start.txt.

Confirm AGENTS.md from this project root is loaded in your context before any tool call; if it is not, say so and stop.

Then execute docs/OX-ALPHA-DIRECTIVE-GATE5.md in full, reading it from disk. Do not pause at stage boundaries; the operator has waived stage pauses for this session, as that directive's section 1 records. Everything else in the directive and in AGENTS.md binds exactly as written.
"@
Set-Clipboard -Value $kickoff
Write-Host "Kickoff message copied to clipboard."

# 3. Launch OpenCode with the workspace as cwd (project root = AGENTS.md location).
if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) { throw "opencode not on PATH" }
Set-Location -LiteralPath $Workspace
Write-Host "Launching OpenCode in $(Get-Location). Paste (Ctrl+V) the kickoff as the first message."
& opencode
