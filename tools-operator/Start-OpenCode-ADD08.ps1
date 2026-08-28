# Start-OpenCode-ADD08.ps1 - operator tooling only. Not part of the shell; not a module launch.
# Resumes the CP-M1 zero-stop loop under ADDENDUM-08 (C-8(c) launch mechanism).
#
# Four consecutive sessions froze on Start-Process with redirected handles. This launcher does the
# two service relaunches ITSELF, using the C-8(c) mechanism, so the builder starts with both up and
# never has to touch a long-lived process. It also verifies the state the paste tells the builder to
# adopt, so a stale entry-state line can never send it off re-deriving.

$ErrorActionPreference = 'Stop'
$WS = "D:\Product Software\Production Workspace"
if (-not (Test-Path -LiteralPath $WS)) { throw "Workspace not found: $WS" }
Set-Location -LiteralPath $WS

Write-Host "=== CP-M1 / ADDENDUM-08 resume ===" -ForegroundColor Cyan

# ---- 1. Required files -------------------------------------------------------------
$required = @(
    'AGENTS.md','opencode.json','BUILD-DIRECTIVE-SWS-UI-001.md',
    'docs\SWS-UI-001-v1.2-ADDENDUM-05.md','docs\SWS-UI-001-v1.2-ADDENDUM-06.md',
    'docs\SWS-UI-001-v1.2-ADDENDUM-07.md','docs\SWS-UI-001-v1.2-ADDENDUM-08.md',
    'docs\OX-ALPHA-DIRECTIVE-CP-M1.md','docs\OX-ALPHA-CP-M1-ADD08-PASTE.md',
    'evidence\GATE-LEDGER.json','evidence\cpm1\RUN-LOG.md','evidence\cpm1\reachability-sweep.md'
)
$missing = $required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $WS $_)) }
if ($missing) { throw "MISSING: $($missing -join ', ')" }
Write-Host "  all required files present" -ForegroundColor Green

# ---- 2. Permissions ----------------------------------------------------------------
$cfg = Get-Content -LiteralPath (Join-Path $WS 'opencode.json') -Raw | ConvertFrom-Json
if ($cfg.permission -eq 'allow') {
    Write-Host "  opencode.json permission = allow (no prompts)" -ForegroundColor Green
} else {
    Write-Warning "opencode.json permission is '$($cfg.permission)' - the session may PAUSE on a tool prompt."
    Write-Warning "  Set it to `"permission`": `"allow`" or the loop will look frozen while it waits on you."
}

# ---- 3. Entry state the paste asserts ----------------------------------------------
Write-Host ""
Write-Host "-- entry state --"
$ledger = (Get-FileHash (Join-Path $WS 'evidence\GATE-LEDGER.json') -Algorithm SHA256).Hash.ToLower()
$expect = '7e0a55b9d67b54ee76e9f539126842ef8bb9e9bfcf82817a270064c6f9b2e2e4'
if ($ledger -eq $expect) { Write-Host "  ledger sha256 matches ADD-08" -ForegroundColor Green }
else { Write-Warning "  ledger sha256 is $ledger, ADD-08 records $expect - the builder re-verifies and will report it." }
$resolved = (Select-String -LiteralPath (Join-Path $WS 'evidence\cpm1\RUN-LOG.md') -Pattern '^G\d+ \|').Count
Write-Host "  RUN-LOG resolved lines: $resolved"
Select-String -LiteralPath (Join-Path $WS 'evidence\cpm1\reachability-sweep.md') -Pattern '^(TRUE|NOT_RUN|REACHABLE|PENDING_DEP):' |
    ForEach-Object { Write-Host "  $($_.Line)" }

# ---- 4. Relaunch the two services under C-8(c) -------------------------------------
# cmd /c start "" /B returns immediately and leaves this shell NO child handle.
Write-Host ""
Write-Host "-- services (C-8(c) launch) --"
$py   = "C:\Users\Sslaw\AppData\Local\Programs\Python\Python312\python.exe"
$logs = Join-Path $env:TEMP 'cpm1-procs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $WS 'modules\distillery\logs') | Out-Null

function Start-Detached([string]$Name, [string]$Script, [string]$ExtraArgs, [int]$Port) {
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        Write-Host "  $Name already listening on $Port" -ForegroundColor Green
        return
    }
    $out = Join-Path $logs "$Name.out"
    $err = Join-Path $logs "$Name.err"
    $cmd = 'start "" /B "{0}" "{1}" {2} > "{3}" 2> "{4}"' -f $py, $Script, $ExtraArgs, $out, $err
    cmd /c $cmd
    Start-Sleep -Seconds 4
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        Write-Host "  $Name UP on $Port" -ForegroundColor Green
    } else {
        Write-Warning "  $Name did NOT come up on $Port - stderr tail:"
        Get-Content -LiteralPath $err -Tail 5 -ErrorAction SilentlyContinue | ForEach-Object { Write-Warning "    $_" }
        Write-Warning "  Not fatal. The builder records it and continues (ADD-07: no halt condition)."
    }
}
Start-Detached 'distillery'  (Join-Path $WS 'modules\distillery\serve.py')     ''             5184
Start-Detached 'tokencenter' (Join-Path $WS 'modules\tokencenter\piggybank.py') '--port 8765' 8765
Write-Host "  service logs: $logs"

# ---- 5. Host observations (never fatal) --------------------------------------------
Write-Host ""
Write-Host "-- host --"
foreach ($p in 5175,5180,5183,5184,8700,8765) {
    $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { Write-Host ("  {0} held by pid {1}" -f $p, $c.OwningProcess) } else { Write-Host "  $p free" }
}

# ---- 6. Kickoff to clipboard -------------------------------------------------------
Set-Clipboard -Value (Get-Content -LiteralPath (Join-Path $WS 'docs\OX-ALPHA-CP-M1-ADD08-PASTE.md') -Raw)
Write-Host ""
Write-Host "ADD-08 kickoff copied to clipboard. Paste with Ctrl+V as the FIRST message." -ForegroundColor Cyan
Write-Host "C-8(c): the builder must NEVER use Start-Process with redirected handles. Four sessions died on it."
Write-Host "If the session goes quiet for 30+ minutes with reachable work left, it FROZE - paste the resume line."
Write-Host ""

# ---- 7. Launch ---------------------------------------------------------------------
if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) { throw "opencode not on PATH" }
& opencode
