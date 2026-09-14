$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptPath = Join-Path $root 'piggybank.py'
$dashboardUrl = 'http://127.0.0.1:8765/'

# F-133(c): the shell sets TOKENCENTER_DATA_DIR from the module state root, but this standalone
# launcher did not, so piggybank.py fell back to APP_ROOT/data and wrote piggybank.sqlite INTO the
# install tree (the P4-4 install-tree-mutation defect). Point it at the per-user state root so the
# standalone path stores data exactly where the shell path does. Start-Process inherits this env.
if (-not $env:TOKENCENTER_DATA_DIR) {
    $stateRoot = $env:SOVEREIGN_WORKSPACE_STATE
    if (-not $stateRoot) {
        $localAppData = $env:LOCALAPPDATA
        if (-not $localAppData) { $localAppData = Join-Path $env:USERPROFILE 'AppData\Local' }
        $stateRoot = Join-Path $localAppData 'SovereignWorkspace'
    }
    $env:TOKENCENTER_DATA_DIR = Join-Path $stateRoot 'tokencenter'
}
if (-not (Test-Path -LiteralPath $env:TOKENCENTER_DATA_DIR)) {
    New-Item -ItemType Directory -Path $env:TOKENCENTER_DATA_DIR -Force | Out-Null
}

$listener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1

if ($listener) {
    $listenerProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    if (-not $listenerProcess -or $listenerProcess.Name -notmatch '^python' -or $listenerProcess.CommandLine -notmatch 'piggybank\.py') {
        throw "Port 8765 is already being used by another program."
    }
} else {
    $pythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($pythonLauncher) {
        $pythonPath = (& $pythonLauncher.Source -3.12 -c 'import sys; print(sys.executable)').Trim()
        if ($LASTEXITCODE -ne 0 -or -not $pythonPath) {
            throw "Python 3.12 could not be located."
        }
    } else {
        $pythonPath = (Get-Command python.exe -ErrorAction Stop).Source
    }

    $argumentLine = '"{0}" --host 127.0.0.1 --port 8765' -f $scriptPath
    $serverProcess = Start-Process -FilePath $pythonPath -ArgumentList $argumentLine -WorkingDirectory $root -WindowStyle Hidden -PassThru
    $ready = $false

    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($serverProcess.HasExited) {
            throw "Sovereign Token Center stopped during startup."
        }
        try {
            $health = Invoke-RestMethod -Uri ($dashboardUrl + 'healthz') -TimeoutSec 2
            if ($health.ok) {
                $ready = $true
                break
            }
        } catch {
            # The first ledger scan may take several seconds.
        }
    }

    if (-not $ready) {
        Stop-Process -Id $serverProcess.Id -ErrorAction SilentlyContinue
        throw "Sovereign Token Center did not become ready within 30 seconds."
    }
}

Write-Host "Sovereign Token Center is ready at $dashboardUrl" -ForegroundColor Green
Start-Process $dashboardUrl
