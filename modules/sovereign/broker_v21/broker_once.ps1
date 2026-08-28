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

Remove-Item -Force $StopFile -ErrorAction SilentlyContinue

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = Get-PowerShellExe
$psi.Arguments = "-ExecutionPolicy Bypass -File `"$BrokerPath`" -Root `"$Root`""
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi
[void]$proc.Start()

$Topic | Out-File -Encoding utf8 -FilePath $TopicFile -Force

$deadline = (Get-Date).AddSeconds($TimeoutSec)
$sawSynth = $false

while ((Get-Date) -lt $deadline) {
    if (Test-Path $SynthFile) {
        $len = (Get-Item $SynthFile).Length
        if ($len -gt 0) {
            $sawSynth = $true
            break
        }
    }
    Start-Sleep -Milliseconds $PollMs
}

New-Item -ItemType File -Force -Path $StopFile | Out-Null
Start-Sleep -Milliseconds 600
if (-not $proc.HasExited) {
    try { $proc.Kill() } catch {}
}

if (-not $sawSynth) {
    throw "broker_once timeout: synthesis not written to $SynthFile within $TimeoutSec sec"
}

Write-Host ("OK: synthesis written: " + $SynthFile)
