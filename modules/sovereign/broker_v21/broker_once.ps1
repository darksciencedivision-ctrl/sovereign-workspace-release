# broker_once.ps1 - SOVEREIGN helper
# Runs one broker session and exits after canonical synthesis is written.

param(
    [Parameter(Mandatory = $true)][string]$BrokerPath,
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$Topic,
    [int]$TimeoutSec = 240,
    [int]$PollMs = 250
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-PowerShellExe {
    # Discovery order matches the cycle runner: pwsh -> powershell -> powershell.exe.
    foreach ($name in @('pwsh', 'powershell', 'powershell.exe')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    throw "No PowerShell executable found (tried pwsh, powershell, powershell.exe)."
}

$Inbox = Join-Path $Root "broker_v21\inbox"
$Logs = Join-Path $Root "logs"
$TopicFile = Join-Path $Inbox "topic.txt"
$StopFile = Join-Path $Root "STOP"
$SynthFile = Join-Path $Root "praxis\logs\synthesis.txt"

foreach ($path in @($Inbox, $Logs, (Split-Path -Parent $SynthFile))) {
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Force -Path $path | Out-Null
    }
}

# F-125(l). A STOP file is the operator's emergency stop and the cycle runner's --fail-closed latch.
# This helper used to delete it unconditionally before starting, overriding both. It refuses instead.
if (Test-Path -LiteralPath $StopFile) {
    throw "broker_once refused: STOP file present at $StopFile (operator stop or fail-closed latch). Remove it deliberately to continue."
}

# F-125(l). Any non-empty synthesis.txt used to satisfy the wait, so a PREVIOUS run's synthesis
# ended it immediately and "OK" was printed for work that never happened. Move it aside so only
# output written by this run can end the wait.
if (Test-Path -LiteralPath $SynthFile) {
    Move-Item -LiteralPath $SynthFile -Destination ($SynthFile + ".prev") -Force
}

# F-125(l). The topic is written BEFORE the broker starts. It used to be written after, so the broker
# could pick up the previous topic.
$Topic | Out-File -Encoding utf8 -FilePath $TopicFile -Force

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = Get-PowerShellExe
$psi.Arguments = "-ExecutionPolicy Bypass -File `"$BrokerPath`" -Root `"$Root`""
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi
[void]$proc.Start()

$deadline = (Get-Date).AddSeconds($TimeoutSec)
$sawSynth = $false

while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $SynthFile) {
        $len = (Get-Item -LiteralPath $SynthFile).Length
        if ($len -gt 0) {
            $sawSynth = $true
            break
        }
    }
    Start-Sleep -Milliseconds $PollMs
}

# The broker loop exits on STOP. This run creates that STOP for ITS broker only and removes it once
# the broker has gone: the helper used to leave it behind, which turned every later cycle into an
# abort (F-125(l)/(c)).
New-Item -ItemType File -Force -Path $StopFile | Out-Null
try {
    if (-not $proc.WaitForExit(5000)) {
        # Kill the broker's whole tree - its Python orchestrator would otherwise keep running and
        # keep writing the shared IPC files (the same defect F-125(d) records for the runner).
        & taskkill.exe /PID $proc.Id /T /F 2>&1 | Out-Null
        [void]$proc.WaitForExit(5000)
    }
}
finally {
    Remove-Item -LiteralPath $StopFile -Force -ErrorAction SilentlyContinue
}

if (-not $sawSynth) {
    throw "broker_once timeout: synthesis not written to $SynthFile within $TimeoutSec sec"
}

Write-Host ("OK: synthesis written: " + $SynthFile)
