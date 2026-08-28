$ErrorActionPreference = 'Stop'
$listeners = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
foreach ($listener in $listeners) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    if ($process -and $process.Name -match '^python' -and $process.CommandLine -match 'piggybank\.py') {
        Stop-Process -Id $listener.OwningProcess
    }
}
