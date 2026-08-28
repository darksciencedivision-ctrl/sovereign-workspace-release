<#
.SYNOPSIS
    Prepare a restored Debate Table checkout for first run. Windows / PowerShell.

.DESCRIPTION
    Checks the Python version, creates a virtual environment, installs from
    requirements.lock.txt, then CHECKS that Ollama responds and that every model
    named in config.json is present.

    This script never installs, removes or replaces a model, and never edits
    config.json. Missing models are reported with the exact `ollama pull` command
    to run; you run it yourself.

    Every failure prints a message naming the missing prerequisite. No stack traces.

.PARAMETER SkipOllama
    Skip the Ollama and model checks. The app cannot hold a debate without Ollama,
    but the environment will be installed and the test suite will run.

.EXAMPLE
    .\scripts\bootstrap.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipOllama
)

$ErrorActionPreference = 'Stop'

$MinPython = [Version]'3.10'
$VerifiedPython = '3.14.6'

$Root = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $Root '.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$Lockfile = Join-Path $Root 'requirements.lock.txt'
$ConfigPath = Join-Path $Root 'config.json'

$script:Failed = $false
$script:Warned = $false

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "    OK    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    WARN  $msg" -ForegroundColor Yellow; $script:Warned = $true }
function Write-Fail($msg) { Write-Host "    FAIL  $msg" -ForegroundColor Red; $script:Failed = $true }

Write-Host "Debate Table -- bootstrap" -ForegroundColor White
Write-Host "Project root: $Root"

# --- 1. Python -------------------------------------------------------------
Write-Step "Checking Python"

$pythonExe = $null
foreach ($candidate in @('python', 'python3', 'py')) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) { $pythonExe = $cmd.Source; break }
}
if (-not $pythonExe) {
    Write-Fail "Python was not found on PATH. Install Python $VerifiedPython (or $MinPython+) from https://www.python.org/downloads/ and make sure 'Add python.exe to PATH' is ticked."
    exit 1
}

try {
    $versionString = (& $pythonExe -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>&1 | Out-String).Trim()
    $version = [Version]$versionString
} catch {
    Write-Fail "Found '$pythonExe' but could not determine its version. Is it a working Python interpreter?"
    exit 1
}

if ($version -lt $MinPython) {
    Write-Fail "Python $versionString found at $pythonExe, but this project needs $MinPython or newer. Install a newer Python and re-run."
    exit 1
}
Write-Ok "Python $versionString at $pythonExe"
if ($versionString -ne $VerifiedPython) {
    Write-Warn "This baseline was validated only on Python $VerifiedPython. $versionString satisfies the declared minimum but is untested here."
}

# --- 2. Lockfile -----------------------------------------------------------
Write-Step "Checking lockfile"
if (-not (Test-Path $Lockfile)) {
    Write-Fail "requirements.lock.txt not found at $Lockfile. The restore is incomplete -- re-extract the snapshot."
    exit 1
}
Write-Ok "requirements.lock.txt present"

# --- 3. Virtual environment ------------------------------------------------
Write-Step "Creating virtual environment"
if (Test-Path $VenvPython) {
    Write-Ok ".venv already exists, reusing it"
} else {
    & $pythonExe -m venv $VenvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) {
        Write-Fail "Could not create a virtual environment at $VenvDir. On some systems the 'venv' module is a separate package."
        exit 1
    }
    Write-Ok "Created $VenvDir"
}

# --- 4. Dependencies -------------------------------------------------------
Write-Step "Installing pinned dependencies"
& $VenvPython -m pip install --quiet --disable-pip-version-check -r $Lockfile
if ($LASTEXITCODE -ne 0) {
    Write-Fail "pip could not install from requirements.lock.txt. If you are offline, this step needs network access to PyPI."
    exit 1
}
Write-Ok "Installed all pins from requirements.lock.txt"

Write-Step "Installing pytest (development-only self-check tool)"
& $VenvPython -m pip install --quiet --disable-pip-version-check pytest
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Could not install pytest. The app will still run; you just cannot run the self-check suite."
} else {
    Write-Ok "pytest installed (deliberately not a runtime dependency -- see README)"
}

# --- 5. Ollama and models --------------------------------------------------
if ($SkipOllama) {
    Write-Step "Skipping Ollama checks (-SkipOllama)"
    Write-Warn "Ollama not checked. The app starts, but no seat can speak without it."
} else {
    Write-Step "Checking Ollama and the models config.json asks for"

    if (-not (Test-Path $ConfigPath)) {
        Write-Fail "config.json not found at $ConfigPath. The restore is incomplete."
        exit 1
    }

    # P0-04/P0-05: resolve configuration through the canonical policy module.
    $effRaw = & $VenvPython (Join-Path $PSScriptRoot 'effective_config.py') $ConfigPath
    $effCode = $LASTEXITCODE
    if ($effCode -eq 5) {
        $why = (($effRaw | Where-Object { $_ -like 'BADCONFIG|*' }) -split '\|')[1]
        Write-Fail "config.json could not be read as JSON: $why"
        Write-Fail "Restore it from the release archive; do not let tools regenerate it."
        exit 1
    }
    if ($effCode -ne 0) {
        Write-Fail "The effective-config check did not run. Verify the virtual environment exists."
        exit 1
    }
    $eff = ($effRaw | Select-Object -First 1) | ConvertFrom-Json
    if ($eff.endpoint_class -eq 'remote') {
        Write-Warn "remote Ollama endpoint enabled by operator opt-in ($($eff.ollama_url)); traffic leaves this host"
        Write-Warn "the local-first privacy statement does not apply to this configuration"
    }

    # Ask Python to do the work: it is already installed, has httpx, and parses
    # JSON without PowerShell-version differences.
    $checkScript = Join-Path $PSScriptRoot '_check_models.py'
    $inline = @'
import json, sys, pathlib
try:
    import httpx
except ImportError:
    print("NOHTTPX"); sys.exit(3)
# URL arrives pre-resolved and policy-checked from effective_config.py.
cfg = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
url = sys.argv[2].rstrip("/")
wanted = []
for seat in cfg.get("seats", []):
    if seat.get("model"):
        wanted.append((seat["model"], "seat " + str(seat.get("name", "?"))))
if cfg.get("insight_panel") and cfg.get("extractor_model"):
    wanted.append((cfg["extractor_model"], "extractor_model"))
try:
    tags = httpx.get(url + "/api/tags", timeout=10).json()
except Exception as exc:
    print("NOOLLAMA|" + url + "|" + type(exc).__name__); sys.exit(4)
installed = {m["name"] for m in tags.get("models", [])}
print("URL|" + url)
for name, why in wanted:
    print(("HAVE|" if name in installed else "MISS|") + name + "|" + why)
if not cfg.get("insight_panel") and cfg.get("extractor_model"):
    print("NOTE|extractor_model '" + str(cfg["extractor_model"]) +
          "' is NOT required: insight_panel is false")
'@
    Set-Content -Path $checkScript -Value $inline -Encoding utf8
    try {
        # 2>&1 would wrap native stderr in ErrorRecords on PS 5.1; keep them apart.
        $lines = & $VenvPython $checkScript $ConfigPath $eff.ollama_url
        $code = $LASTEXITCODE
    } finally {
        Remove-Item $checkScript -ErrorAction SilentlyContinue
    }

    $tagged = @($lines | Where-Object { "$_" -match '^(URL|HAVE|MISS|NOTE|NOOLLAMA|NOHTTPX|BADCONFIG)\|' })

    if ($code -eq 3) {
        Write-Fail "httpx is missing from the virtual environment; the dependency install did not complete. Delete .venv and re-run this script."
    } elseif ($code -eq 4) {
        $u = (($tagged | Where-Object { $_ -like 'NOOLLAMA|*' }) -split '\|')[1]
        Write-Fail "Ollama did not respond at $u. Start it with 'ollama serve', or install it from https://ollama.com/download."
    } elseif ($code -eq 5) {
        $why = (($tagged | Where-Object { $_ -like 'BADCONFIG|*' }) -split '\|')[1]
        Write-Fail "config.json could not be read as JSON: $why"
        Write-Host "          Check it is valid JSON and saved as UTF-8." -ForegroundColor Yellow
    } elseif ($tagged.Count -eq 0) {
        # Never surface a raw traceback: name the prerequisite and move on.
        Write-Fail "The model check did not complete (exit $code). Verify Ollama is running and config.json is valid, then re-run."
    } else {
        foreach ($line in $tagged) {
            $p = "$line" -split '\|'
            switch ($p[0]) {
                'URL'  { Write-Ok "Ollama responded at $($p[1])" }
                'HAVE' { Write-Ok "model present: $($p[1])  ($($p[2]))" }
                'MISS' {
                    Write-Fail "model MISSING: $($p[1])  ($($p[2]))"
                    Write-Host "          run yourself:  ollama pull $($p[1])" -ForegroundColor Yellow
                }
                'NOTE' { Write-Host "    NOTE  $($p[1])" -ForegroundColor DarkGray }
            }
        }
    }
}

# --- 6. Result -------------------------------------------------------------
Write-Host ""
if ($script:Failed) {
    Write-Host "BOOTSTRAP INCOMPLETE -- resolve the FAIL lines above, then re-run." -ForegroundColor Red
    exit 1
}

Write-Host "BOOTSTRAP OK" -ForegroundColor Green
if ($script:Warned) {
    Write-Host "(with warnings above)" -ForegroundColor Yellow
}
$port = 8700
try {
    $port = (Get-Content $ConfigPath -Raw | ConvertFrom-Json).port
} catch { }
Write-Host @"

Next steps:

  run the self-check suite
      .venv\Scripts\python.exe -m pytest tests -q -W error

  start the app
      .venv\Scripts\python.exe app.py

  then open  http://127.0.0.1:$port
  stop it with Ctrl+C
"@
exit 0
