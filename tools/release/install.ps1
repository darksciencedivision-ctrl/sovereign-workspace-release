[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Dest,
    [string] $TargetDir,
    [string] $Artifact
)

$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
$workspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$destRoot = [IO.Path]::GetFullPath($Dest).TrimEnd('\')
$destPrefix = $destRoot + '\'
if ($destRoot -eq [IO.Path]::GetPathRoot($destRoot)) {
    throw "Refusing filesystem-root destination: $destRoot"
}
if (-not $Artifact) {
    $version = (Get-Content -Raw -LiteralPath (Join-Path $workspaceRoot 'VERSION.json') | ConvertFrom-Json).version
    $Artifact = Join-Path $workspaceRoot "release-artifacts\sovereign-workspace-$version-install.zip"
}
$artifactPath = [IO.Path]::GetFullPath($Artifact)
if (-not (Test-Path -LiteralPath $artifactPath -PathType Leaf)) {
    throw "Install artifact not found: $artifactPath"
}
$sidecarPath = $artifactPath + '.sha256'
if (-not (Test-Path -LiteralPath $sidecarPath -PathType Leaf)) {
    throw "Install artifact sidecar not found: $sidecarPath"
}
$sidecarLine = (Get-Content -Raw -LiteralPath $sidecarPath).Trim()
$expectedHash = ($sidecarLine -split '\s+')[0].ToLowerInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $artifactPath).Hash.ToLowerInvariant()
if ($expectedHash -ne $actualHash) { throw 'Install artifact SHA-256 mismatch' }

$destExisted = Test-Path -LiteralPath $destRoot
if ($destExisted) {
    if (-not (Test-Path -LiteralPath $destRoot -PathType Container)) {
        throw "Destination is not a directory: $destRoot"
    }
    if (Get-ChildItem -LiteralPath $destRoot -Force | Select-Object -First 1) {
        throw "Destination must be empty: $destRoot"
    }
}
else {
    New-Item -ItemType Directory -Path $destRoot | Out-Null
}

$targetRoot = $null
$targetBefore = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
if ($TargetDir) {
    $targetRoot = [IO.Path]::GetFullPath($TargetDir).TrimEnd('\')
    if ($targetRoot -eq [IO.Path]::GetPathRoot($targetRoot)) {
        throw "Refusing filesystem-root shortcut target: $targetRoot"
    }
    if (Test-Path -LiteralPath $targetRoot) {
        [void]$targetBefore.Add($targetRoot)
        Get-ChildItem -LiteralPath $targetRoot -Force -Recurse | ForEach-Object {
            [void]$targetBefore.Add([IO.Path]::GetFullPath($_.FullName))
        }
    }
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($artifactPath)
try {
    foreach ($entry in $archive.Entries) {
        $name = $entry.FullName.Replace('\', '/')
        if (-not $name.StartsWith('sovereign-workspace/', [StringComparison]::Ordinal)) {
            throw "Unexpected archive entry outside install prefix: $name"
        }
        $relative = $name.Substring('sovereign-workspace/'.Length).TrimEnd('/')
        if (-not $relative) { continue }
        $destination = [IO.Path]::GetFullPath((Join-Path $destRoot $relative))
        if (-not $destination.StartsWith($destPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Archive path escapes destination: $name"
        }
        if (-not $entry.Name) {
            New-Item -ItemType Directory -Path $destination -Force | Out-Null
            continue
        }
        $parent = Split-Path -Parent $destination
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $destination, $false)
    }
}
finally {
    $archive.Dispose()
}

$pyLauncher = (Get-Command py -ErrorAction Stop).Source
$npm = (Get-Command npm.cmd -ErrorAction Stop).Source
$configPath = Join-Path $destRoot 'shell\config\install.json'
$sourceConfig = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$sourceModulesRoot = [string]$sourceConfig.modules_root
$python312 = (& $pyLauncher -3.12 -c 'import sys;print(sys.executable)').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is unavailable' }
$installConfig = [ordered]@{
    modules_root = $destRoot
    source_modules_root = $sourceModulesRoot
    python_312 = $python312
    optional_adapters = @('llamacpp')
}
$utf8NoBom = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText($configPath, (($installConfig | ConvertTo-Json -Compress) + "`n"), $utf8NoBom)

Write-Output 'install: provisioning SOVEREIGN Python from exact retained lock'
& $pyLauncher -3.12 -m venv (Join-Path $destRoot 'modules\sovereign\.venv')
if ($LASTEXITCODE -ne 0) { throw 'SOVEREIGN venv creation failed' }
$sovereignPython = Join-Path $destRoot 'modules\sovereign\.venv\Scripts\python.exe'
& $sovereignPython -m pip install --disable-pip-version-check --index-url https://pypi.org/simple --only-binary=:all: --no-deps -r (Join-Path $destRoot 'modules\sovereign\WORKSPACE-RESOLVED-LOCK.txt')
if ($LASTEXITCODE -ne 0) { throw 'SOVEREIGN lock install failed' }

Write-Output 'install: provisioning Debate Python from exact retained lock'
& $pyLauncher -3.14 -m venv (Join-Path $destRoot 'modules\debate\.venv')
if ($LASTEXITCODE -ne 0) { throw 'Debate venv creation failed' }
$debatePython = Join-Path $destRoot 'modules\debate\.venv\Scripts\python.exe'
& $debatePython -m pip install --disable-pip-version-check --index-url https://pypi.org/simple --only-binary=:all: --no-deps -r (Join-Path $destRoot 'modules\debate\requirements.lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Debate lock install failed' }

Write-Output 'install: provisioning SOW Python from exact pinned runtime closure'
# EPC-01 P0-2. This block did not exist. SOVEREIGN and Debate were provisioned; SOW was
# not — while apps/desktop spawned `py -3.12` (the SYSTEM interpreter) for seventeen
# entry points, twelve of whose modules import jsonschema. On a clean machine with
# Python 3.12 and no jsonschema, the IPC gateway died on import at first launch.
# apps/desktop/python-runtime.js resolves this venv when it exists and falls back to the
# py launcher when it does not, so a development tree without one behaves as before.
& $pyLauncher -3.12 -m venv (Join-Path $destRoot 'modules\sow\.venv')
if ($LASTEXITCODE -ne 0) { throw 'SOW venv creation failed' }
$sowPython = Join-Path $destRoot 'modules\sow\.venv\Scripts\python.exe'
& $sowPython -m pip install --disable-pip-version-check --index-url https://pypi.org/simple --only-binary=:all: --no-deps -r (Join-Path $destRoot 'modules\sow\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'SOW runtime lock install failed' }
# Prove the gateway imports in the environment we just built, before declaring install
# success. A provisioning step that is not verified is a provisioning step that silently
# regresses. This is the exact failure P0-2 records, asserted at install time. The check
# runs FROM the module root because that is where the app spawns it from and where
# sys.path resolves control_plane.
Push-Location (Join-Path $destRoot 'modules\sow')
try {
    & $sowPython -c "import importlib; importlib.import_module('control_plane.ipc.run_gateway')"
    if ($LASTEXITCODE -ne 0) { throw 'SOW gateway import check failed in the provisioned environment' }
}
finally { Pop-Location }

foreach ($nodeRoot in @(
    (Join-Path $destRoot 'modules\sovereign\ui\ui_shell')
)) {
    Write-Output "install: npm ci $nodeRoot"
    Push-Location $nodeRoot
    try {
        & $npm ci --registry=https://registry.npmjs.org
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed: $nodeRoot" }
    }
    finally { Pop-Location }
}

Write-Output 'install: provisioning SOW via install_sow.py (ADR-005 hash-verified Electron)'
# EPC-01 P1-9. This installer previously ran a plain `npm ci` for modules\sow\apps\desktop and
# never invoked install_sow.py at all — so Electron's postinstall ran and downloaded a ~100 MB
# binary from GitHub with NO hash verification.
#
# That contradicts the workspace's own architecture decision. ADR-005 records that this
# workspace CHOOSES `--ignore-scripts` and that Electron is "provisioned by an explicit,
# logged, hash-verified step — which is the whole point of this ADR", checking the zip's
# SHA-256 against the checksums.json shipped inside the npm package the lockfile pins. The
# authoritative install path was quietly bypassing the one supply-chain control the project
# wrote an ADR to establish.
#
# install_sow.py performs `npm ci --ignore-scripts` itself as its step 3, so this REPLACES the
# npm ci above for that root rather than adding to it. It resolves its own paths from
# __file__, logs every step, and exits non-zero on any mismatch.
& $sovereignPython -B (Join-Path $destRoot 'shell\tools\install_sow.py')
if ($LASTEXITCODE -ne 0) { throw 'SOW provisioning failed (install_sow.py)' }

& $sovereignPython -B (Join-Path $destRoot 'tools\release\rebase_adapters.py') --root $destRoot
if ($LASTEXITCODE -ne 0) { throw 'Installed adapter rebase failed' }

$expectedLinks = @()
if ($targetRoot) {
    $expectedLinks = @(
        (Join-Path $targetRoot 'Desktop\Sovereign Workspace.lnk'),
        (Join-Path $targetRoot 'Start Menu\Programs\Sovereign Workspace.lnk')
    )
    foreach ($link in $expectedLinks) {
        if (Test-Path -LiteralPath $link) { throw "Refusing to overwrite existing shortcut: $link" }
    }
    & (Join-Path $destRoot 'tools\release\install_shortcut.ps1') -TargetDir $targetRoot | Out-Null
}
else {
    & (Join-Path $destRoot 'tools\release\install_shortcut.ps1') | ForEach-Object { $expectedLinks += [string]$_ }
}

$paths = @()
Get-ChildItem -LiteralPath $destRoot -Force -Recurse | Sort-Object FullName | ForEach-Object {
    $relative = $_.FullName.Substring($destPrefix.Length).Replace('\', '/')
    if ($relative -eq 'install-manifest.json') { return }
    if ($_.PSIsContainer) {
        $paths += [ordered]@{ scope = 'install'; kind = 'directory'; path = $relative }
    }
    else {
        $paths += [ordered]@{
            scope = 'install'; kind = 'file'; path = $relative
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
        }
    }
}
$paths += [ordered]@{ scope = 'install'; kind = 'manifest'; path = 'install-manifest.json'; sha256 = $null }

if ($targetRoot) {
    if (Test-Path -LiteralPath $targetRoot) {
        $targetAfter = @($targetRoot) + @(Get-ChildItem -LiteralPath $targetRoot -Force -Recurse | ForEach-Object { $_.FullName })
        foreach ($path in $targetAfter) {
            $full = [IO.Path]::GetFullPath($path)
            if ($targetBefore.Contains($full)) { continue }
            $item = Get-Item -LiteralPath $full
            if ($item.PSIsContainer) {
                $paths += [ordered]@{ scope = 'shortcut'; kind = 'directory'; path = $full }
            }
            else {
                $paths += [ordered]@{
                    scope = 'shortcut'; kind = 'file'; path = $full
                    sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $full).Hash.ToLowerInvariant()
                }
            }
        }
    }
}
else {
    foreach ($link in $expectedLinks) {
        $full = [IO.Path]::GetFullPath($link)
        $paths += [ordered]@{
            scope = 'shortcut'; kind = 'file'; path = $full
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $full).Hash.ToLowerInvariant()
        }
    }
}

$manifest = [ordered]@{
    schema = 'sovereign.install-manifest.v1'
    version = (Get-Content -Raw -LiteralPath (Join-Path $destRoot 'VERSION.json') | ConvertFrom-Json).version
    source_archive = [IO.Path]::GetFileName($artifactPath)
    source_archive_sha256 = $actualHash
    install_root = $destRoot
    install_root_created = -not $destExisted
    shortcut_target_root = $targetRoot
    claim = 'uninstall removes exactly the paths recorded by this manifest after exact-set verification'
    paths = @($paths | Sort-Object scope, path)
}
$manifestPath = Join-Path $destRoot 'install-manifest.json'
[IO.File]::WriteAllText($manifestPath, (($manifest | ConvertTo-Json -Depth 8) + "`n"), $utf8NoBom)
Write-Output "install: recorded $($paths.Count) created paths in $manifestPath"
