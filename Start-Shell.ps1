<#
.SYNOPSIS
    Starts the Sovereign Workspace Shell (SWS-UI-001) and opens it in the browser.

.DESCRIPTION
    Runs the shell in the foreground on 127.0.0.1. Ctrl+C stops it, and because the
    shell holds its modules in a Windows Job Object, anything it launched stops too.

    Checks before starting:
      - py 3.12 is present (the build is pinned to it; bare python here is 3.14)
      - the working directory really is the workspace root
      - the port is free
      - Windows is in dark mode, because the shell follows the OS and the light
        variant is a different surface level

.PARAMETER Port
    Port to bind. Default 5180.

.PARAMETER NoBrowser
    Start the shell but do not open a browser window.

.EXAMPLE
    .\Start-Shell.ps1

.EXAMPLE
    .\Start-Shell.ps1 -Port 5181 -NoBrowser
#>
[CmdletBinding()]
param(
    [int] $Port = 5180,
    [switch] $NoBrowser
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host ""
Write-Host "  Sovereign Workspace Shell" -ForegroundColor Cyan
Write-Host "  $root"
Write-Host ""

# --- the workspace root, not some other folder -----------------------------
if (-not (Test-Path (Join-Path $root "shell\src\__main__.py"))) {
    Write-Host "  shell\src\__main__.py not found." -ForegroundColor Red
    Write-Host "  Put this script in the folder that CONTAINS shell\, and run it from there."
    exit 1
}

# --- python 3.12, resolved to an absolute path -----------------------------
$pyCmd = Get-Command py -ErrorAction SilentlyContinue
if ($null -eq $pyCmd) {
    Write-Host "  The 'py' launcher is not on PATH. Install Python 3.12." -ForegroundColor Red
    exit 1
}
$py = $pyCmd.Source
$ver = & $py -3.12 --version 2>$null
if (-not $?) {
    Write-Host "  py -3.12 is not available. This build is pinned to Python 3.12." -ForegroundColor Red
    Write-Host "  Bare 'python' on this host is a different version and is not supported."
    exit 1
}
Write-Host "  python   $ver"

# --- port ------------------------------------------------------------------
$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($null -ne $busy) {
    Write-Host "  Port $Port is already in use (pid $($busy[0].OwningProcess))." -ForegroundColor Red
    Write-Host "  Either stop that process, or start on another port:"
    Write-Host "      .\Start-Shell.ps1 -Port 5181"
    exit 1
}
Write-Host "  port     $Port free"

# --- theme -----------------------------------------------------------------
# The shell follows prefers-color-scheme. In light mode you get the light
# variant, which is a legitimate theme but not the dark identity.
$themeKey = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"
$appsLight = $null
if (Test-Path $themeKey) {
    $appsLight = (Get-ItemProperty -Path $themeKey -ErrorAction SilentlyContinue).AppsUseLightTheme
}
if ($appsLight -eq 1) {
    Write-Host ""
    Write-Host "  Windows is set to LIGHT mode." -ForegroundColor Yellow
    Write-Host "  The shell follows your OS, so you will get the light variant, not the"
    Write-Host "  dark ice-blue identity. To switch:"
    Write-Host ""
    Write-Host "      Settings > Personalization > Colors > Choose your mode > Dark"
    Write-Host ""
    Write-Host "  Or set it for apps only, then refresh the page:"
    Write-Host "      Set-ItemProperty '$themeKey' AppsUseLightTheme 0"
    Write-Host ""
}
else {
    Write-Host "  theme    dark"
}

# --- run -------------------------------------------------------------------
$url = "http://127.0.0.1:$Port"
$env:PYTHONDONTWRITEBYTECODE = '1'
Write-Host ""
Write-Host "  Starting. Ctrl+C to stop." -ForegroundColor Cyan
Write-Host ""

$proc = Start-Process -FilePath $py `
                      -ArgumentList @('-3.12', '-B', '-m', 'shell.src', '--port', "$Port") `
                      -WorkingDirectory $root -NoNewWindow -PassThru

try {
    # wait for the port to come up before pointing a browser at it
    $listening = $false
    for ($i = 0; $i -lt 40; $i++) {
        if ($proc.HasExited) { break }
        $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($null -ne $c) { $listening = $true; break }
        Start-Sleep -Milliseconds 250
    }

    if ($proc.HasExited) {
        Write-Host "  The shell exited during startup (code $($proc.ExitCode))." -ForegroundColor Red
        exit $proc.ExitCode
    }

    if ($listening) {
        Write-Host "  Listening on $url" -ForegroundColor Green
        if (-not $NoBrowser) { Start-Process $url }
    }
    else {
        Write-Host "  Port $Port did not come up within 10s. Leaving the process running." -ForegroundColor Yellow
        Write-Host "  Check the output above for the reason."
    }

    Wait-Process -Id $proc.Id
}
finally {
    if (-not $proc.HasExited) {
        Write-Host ""
        Write-Host "  Stopping the shell..." -ForegroundColor Cyan
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        $proc.WaitForExit(5000) | Out-Null
    }
    Write-Host "  Stopped." -ForegroundColor Cyan
    Write-Host ""
}
