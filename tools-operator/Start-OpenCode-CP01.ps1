# Start-OpenCode-CP01.ps1 - operator tooling only. Not part of the shell; not a module launch.
# Launches OX ALPHA (OpenCode) at the Production Workspace root for the CP-01 control-plane loop,
# after verifying the authority envelope and host quiescence. Same family as
# Start-OpenCode-FullAccess.ps1 / tools-operator\Start-OpenCode-Gate5.ps1.

$ErrorActionPreference = 'Stop'
$Workspace = "D:\Product Software\Production Workspace"

if (-not (Test-Path -LiteralPath $Workspace)) { throw "Workspace not found: $Workspace" }

# ---- 1. Envelope files must exist -------------------------------------------------
$required = @(
    'AGENTS.md',
    'CLAUDE.md',
    'opencode.json',
    'BUILD-DIRECTIVE-SWS-UI-001.md',
    'docs\SWS-UI-001-v1.2-ADDENDUM-01.md',
    'docs\OX-ALPHA-DIRECTIVE-CP-01.md',
    'docs\OX-ALPHA-CP-01-PASTE.md',
    'docs\THEME-BASELINE-v3.md',
    'evidence\GATE-LEDGER.json',
    'evidence\OPERATOR-INSTRUCTIONS.log'
)
foreach ($f in $required) {
    $p = Join-Path $Workspace $f
    if (-not (Test-Path -LiteralPath $p)) { throw "Missing: $f" }
}

$a = (Get-FileHash (Join-Path $Workspace 'AGENTS.md')  -Algorithm SHA256).Hash
$c = (Get-FileHash (Join-Path $Workspace 'CLAUDE.md')  -Algorithm SHA256).Hash
if ($a -ne $c) { throw "AGENTS.md and CLAUDE.md differ - envelope copies out of sync" }
Write-Host "Envelope sha256: $($a.ToLower())"

foreach ($f in @('docs\SWS-UI-001-v1.2-ADDENDUM-01.md','docs\OX-ALPHA-DIRECTIVE-CP-01.md')) {
    $h = (Get-FileHash (Join-Path $Workspace $f) -Algorithm SHA256).Hash.ToLower()
    Write-Host ("{0}  {1}" -f $h, $f)
}

# ---- 2. Host quiescence (blocking) ------------------------------------------------
# 8765 is the Sovereign Token Center. It joins 5175/8700/5180 for this loop.
$ports = 5175, 8700, 8765, 5180
$listening = Get-NetTCPConnection -State Listen -LocalPort $ports -ErrorAction SilentlyContinue
if ($listening) {
    $listening | ForEach-Object {
        $owner = (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue)
        Write-Warning ("port {0} held by pid {1} {2}" -f $_.LocalPort, $_.OwningProcess, $owner.Path)
    }
    throw "HOST_NOT_QUIESCENT: a module/shell/token-center port is already listening. Stop it, or record it as EXTERNAL evidence first."
}

$modProcs = Get-Process python, electron, node -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -like "$Workspace\modules\*" }
if ($modProcs) {
    $modProcs | ForEach-Object { Write-Warning ("module process {0} {1}" -f $_.Id, $_.Path) }
    throw "HOST_NOT_QUIESCENT: module process still running"
}

# ---- 3. Protected-tree spot check (warn-only; G0.1 does this properly) ------------
$protected = @(
    'D:\multi model terminal app\sovereign-orchestration-workspace',
    'D:\Sovereign Distillery',
    'D:\Sov 1',
    'D:\Token Piggy Bank'
)
$env:GIT_OPTIONAL_LOCKS = '0'
foreach ($t in $protected) {
    if (-not (Test-Path -LiteralPath $t)) { Write-Warning "protected tree absent: $t"; continue }
    if (Test-Path -LiteralPath (Join-Path $t '.git')) {
        $h1 = git -C $t rev-parse HEAD 2>$null
        Start-Sleep -Seconds 3
        $h2 = git -C $t rev-parse HEAD 2>$null
        if ($h1 -ne $h2) { Write-Warning "$t HEAD moved during spot check - CP-01 will stop at G0.1" }
        else { Write-Host ("quiescent: {0}  {1}" -f $t, $h1) }
    } else {
        Write-Host "present (no git): $t"
    }
}
Remove-Item Env:\GIT_OPTIONAL_LOCKS -ErrorAction SilentlyContinue

# ---- 4. Kickoff to clipboard -------------------------------------------------------
$paste = Get-Content -LiteralPath (Join-Path $Workspace 'docs\OX-ALPHA-CP-01-PASTE.md') -Raw
Set-Clipboard -Value $paste
Write-Host ""
Write-Host "CP-01 kickoff copied to clipboard. Paste with Ctrl+V as the FIRST message of the session."
Write-Host "It carries the ADDENDUM-01 section 9 authorization sentence - the builder logs it verbatim before any mutation."
Write-Host ""

# ---- 5. Launch ---------------------------------------------------------------------
if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) { throw "opencode not on PATH" }
Set-Location -LiteralPath $Workspace
& opencode
