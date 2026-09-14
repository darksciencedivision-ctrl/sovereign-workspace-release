[CmdletBinding()]
param(
    [string] $OutputDir,
    [string] $Commit = 'HEAD'
)

# Release artifact producer - SWS-REM-DIR-20260828 R2.
#
# LOCAL-01 F-7 (OD-33). This script used to `git archive` the TWO composite archives and then
# enumerate `Get-ChildItem *.zip` from the output directory, recording whatever it found as
# authoritative. The six per-module archives were never cut by it. At the FIXUP-01 seal all six on
# disk were stale leftovers from the PARENT commit, and without a manual re-cut they would have
# shipped pre-fix bytes under correct-looking, internally consistent hashes - a worse failure than
# the one X-1 fixed, because every number would have agreed with every other number and been wrong.
#
# The validator recorded this as its own defect: X-1 step 2 said "extend the producer so it
# ENUMERATES every release artifact", and *enumerate* was the wrong verb. The producer must CUT all
# eight from the named commit, and then record what it cut.
#
# So: the artifact list is now the CUT LIST, not a directory listing, and a `.zip` in the output
# directory that this run did not cut is a hard error rather than a silent authority. Both halves
# matter - cutting everything closes the stale-bytes hole, and refusing strangers closes the hole
# where something else's output inherits this manifest's authority.

$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
$workspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if (-not $OutputDir) {
    $OutputDir = Join-Path $workspaceRoot 'release-artifacts'
}
$outputRoot = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

$trackedStatus = & git -C $workspaceRoot status --porcelain=v1 --untracked-files=no
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect git status' }
if ($trackedStatus) { throw 'Refusing release build with tracked modifications' }
$resolvedCommit = (& git -C $workspaceRoot rev-parse $Commit).Trim()
if ($LASTEXITCODE -ne 0 -or $resolvedCommit -notmatch '^[0-9a-f]{40}$') {
    throw "Unable to resolve release commit: $Commit"
}
$headCommit = (& git -C $workspaceRoot rev-parse HEAD).Trim()

# F-062. The bytes come from `git archive $resolvedCommit`, but the IDENTITY inputs - the version,
# the per-module versions (INSTALL-PROVENANCE.json), and the SBOM/NOTICE --check - used to be read
# from the WORKING TREE. With -Commit != HEAD the artifact was named and manifested with HEAD's
# identity while containing another commit's files. The identity must originate from the SAME
# candidate as the packaged bytes (directive 2.5). When the requested commit is HEAD, the working
# tree is that commit (tracked modifications were just refused), so it is used directly; otherwise
# a detached worktree is checked out at $resolvedCommit and EVERY identity input is read from it.
$identityRoot = $workspaceRoot
$identityWorktree = $null
if ($resolvedCommit -ne $headCommit) {
    $identityWorktree = Join-Path ([IO.Path]::GetTempPath()) ("sws-build-identity-" + [Guid]::NewGuid().ToString('N').Substring(0, 12))
    & git -C $workspaceRoot worktree add --detach $identityWorktree $resolvedCommit | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Unable to check out identity worktree at $resolvedCommit" }
    $identityRoot = [IO.Path]::GetFullPath($identityWorktree)
    Write-Output "identity read from clean worktree at $resolvedCommit ($identityRoot)"
}

try {

$versionDoc = Get-Content -Raw -LiteralPath (Join-Path $identityRoot 'VERSION.json') | ConvertFrom-Json
$version = [string]$versionDoc.version
if (-not $version) { throw 'VERSION.json does not contain a version' }

# --- the attribution files must describe THIS tree before anything is cut ----------------------
# EPC-01 P2-1/P2-2/P2-3. SBOM.json is generated from the six lock files and NOTICE from the SBOM.
# Both ship. If a lock has moved since either was generated, the release would carry an
# attribution set describing a different dependency tree than the one inside the archives -- and
# the numbers would all agree with each other while being wrong, which is the failure mode this
# whole script exists to prevent. Checked here, before the first archive is cut, so the build
# fails without leaving half a release behind.
foreach ($generator in @('generate_sbom.py', 'generate_notice.py')) {
    # F-062: run the COMMIT's copy of the tool from the identity root, so --check describes the
    # commit's tracked inputs (the bytes being packaged), not the working tree's.
    $tool = Join-Path $identityRoot (Join-Path 'tools\release' $generator)
    Push-Location $identityRoot
    try { & py -3.12 $tool --check } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) {
        throw ("$generator --check failed: the shipped attribution files are out of date with " +
               "their sources. Re-run tools/release/generate_sbom.py then generate_notice.py, " +
               "re-sync RELEASE-MANIFEST.json, and commit before building a release.")
    }
}

# --- the eight artifacts, enumerated EXPLICITLY -------------------------------------------------
# Never by glob. `module_source_registry.json`'s own policy states the rule for this program:
# "Enumeration is explicit ... consumers must never infer paths by glob." Each per-module archive
# takes its version from a NAMED file and field, so the name this script produces is derivable from
# the commit rather than remembered from the last build. The version SOURCES differ per module
# because the modules genuinely differ - that is recorded here rather than smoothed over.

function Get-JsonField {
    param([string] $RelativePath, [string] $Field)
    # F-062: identity is read from the identity root (the commit's worktree when != HEAD).
    $path = Join-Path $identityRoot $RelativePath
    if (-not (Test-Path -LiteralPath $path)) { throw "Version source missing: $RelativePath" }
    $doc = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
    $value = [string]$doc.$Field
    if (-not $value) { throw "Version source $RelativePath has no '$Field'" }
    return $value
}

$sovereignRevision = Get-JsonField 'modules/sovereign/INSTALL-PROVENANCE.json' 'source_revision'
# tokencenter carries no version of its own; its archive is identified by the DATE of the
# provenance record that admitted it, which is what the sealed name has always encoded.
$tokencenterUtc = Get-JsonField 'modules/tokencenter/INSTALL-PROVENANCE.json' 'utc'
$tokencenterStamp = 'record-dated-' + $tokencenterUtc.Substring(0, 10)

$plan = @(
    [ordered]@{ name = "sovereign-workspace-$version-source.zip";  pathspec = $null; prefix = $null },
    [ordered]@{ name = "sovereign-workspace-$version-install.zip"; pathspec = $null; prefix = 'sovereign-workspace/' },
    [ordered]@{ name = ("debate-{0}-src.zip"     -f (Get-JsonField 'modules/debate/INSTALL-PROVENANCE.json' 'version'));     pathspec = 'modules/debate';     prefix = $null },
    [ordered]@{ name = ("distillery-{0}-src.zip" -f (Get-JsonField 'modules/distillery/INSTALL-PROVENANCE.json' 'version')); pathspec = 'modules/distillery'; prefix = $null },
    [ordered]@{ name = ("shell-{0}-src.zip"      -f $version);                                                              pathspec = 'shell';             prefix = $null },
    [ordered]@{ name = ("sovereign-{0}-src.zip"  -f $sovereignRevision);                                                    pathspec = 'modules/sovereign'; prefix = $null },
    [ordered]@{ name = ("sow-{0}-src.zip"        -f (Get-JsonField 'modules/sow/INSTALL-PROVENANCE.json' 'version'));        pathspec = 'modules/sow';       prefix = $null },
    [ordered]@{ name = ("tokencenter-{0}-src.zip" -f $tokencenterStamp);                                                    pathspec = 'modules/tokencenter'; prefix = $null }
)

# --- cut every one of them FROM THE NAMED COMMIT ------------------------------------------------
$utf8NoBom = [Text.UTF8Encoding]::new($false)
$cutNames = New-Object 'System.Collections.Generic.HashSet[string]'
foreach ($item in $plan) {
    $target = Join-Path $outputRoot $item.name
    # Remove any predecessor first: `git archive` would happily write beside a stale file, and the
    # whole defect being closed here is a stale file surviving a build.
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force }

    $gitArgs = @('-C', $workspaceRoot, 'archive', '--format=zip', "--output=$target")
    if ($item.prefix) { $gitArgs += "--prefix=$($item.prefix)" }
    $gitArgs += $resolvedCommit
    if ($item.pathspec) { $gitArgs += @('--', $item.pathspec) }

    & git @gitArgs
    if ($LASTEXITCODE -ne 0) { throw "git archive failed for $($item.name)" }
    if (-not (Test-Path -LiteralPath $target)) { throw "git archive produced nothing for $($item.name)" }
    [void]$cutNames.Add($item.name)

    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLowerInvariant()
    $sidecar = $target + '.sha256'
    [IO.File]::WriteAllText($sidecar, "$hash  $($item.name)`n", $utf8NoBom)
}

# --- a stranger in the output directory is an ERROR ---------------------------------------------
# The old code would have adopted it and published its hash as authoritative. That is exactly how
# six stale archives came to be recorded as this release's bytes.
$strangers = @()
foreach ($zip in (Get-ChildItem -LiteralPath $outputRoot -Filter '*.zip' -File)) {
    if (-not $cutNames.Contains($zip.Name)) { $strangers += $zip.Name }
}
if ($strangers.Count -gt 0) {
    throw ("Output directory holds .zip file(s) this build did not cut: {0}. They would otherwise " -f ($strangers -join ', ')) +
          'be recorded as authoritative release bytes (OD-33). Remove them or add them to the cut plan.'
}

# CLOSEOUT-01 X-1 (A-1 / OD-24): this manifest is the SOLE authority for release-artifact
# hashes. It now enumerates the CUT LIST -- every artifact this run produced from the named
# commit -- rather than whatever happened to be on disk. Each sidecar is hashed in its own
# right, and each sidecar's recorded hash is cross-checked against its artifact.
# This file cannot enumerate itself: writing its own hash into it would change that hash.
$artifacts = @()
foreach ($item in $plan) {
    $path = Join-Path $outputRoot $item.name
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    $sidecarPath = $path + '.sha256'
    if (-not (Test-Path -LiteralPath $sidecarPath)) {
        throw "Release artifact has no .sha256 sidecar: $($item.name)"
    }
    $sidecarText = Get-Content -Raw -LiteralPath $sidecarPath
    $recorded = ($sidecarText -split '\s+')[0].ToLowerInvariant()
    if ($recorded -ne $hash) {
        throw "Sidecar disagrees with artifact for $($item.name): sidecar $recorded, measured $hash"
    }
    $artifacts += [ordered]@{
        name = $item.name
        bytes = (Get-Item -LiteralPath $path).Length
        sha256 = $hash
        sidecar = [IO.Path]::GetFileName($sidecarPath)
        sidecar_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $sidecarPath).Hash.ToLowerInvariant()
        cut_from = $resolvedCommit
        pathspec = $item.pathspec
    }
}

if ($artifacts.Count -ne $plan.Count) { throw 'Release build did not record every artifact it cut' }
if ($artifacts.Count -lt 2) { throw 'Release build produced fewer than the two composite archives' }

$manifest = [ordered]@{
    schema = 'release_build_manifest@1.0'
    version = $version
    source_commit = $resolvedCommit
    archive_basis = 'git archive of the named source commit; ignored host state excluded'
    hash_authority_note = 'Sole authority for release-artifact and sidecar hashes. RELEASE-MANIFEST.json is tracked, therefore archived, therefore cannot carry these hashes (CLOSEOUT-01 A-1). This file is untracked and excludes itself by construction.'
    artifact_count = $artifacts.Count
    artifacts = $artifacts
}
$manifestPath = Join-Path $outputRoot 'release-build-manifest.json'
[IO.File]::WriteAllText($manifestPath, (($manifest | ConvertTo-Json -Depth 6) + "`n"), $utf8NoBom)

Write-Output "commit $resolvedCommit"
Write-Output "artifacts $($artifacts.Count)"
foreach ($artifact in $artifacts) {
    Write-Output ("{0} {1} {2}" -f $artifact.sha256, $artifact.bytes, $artifact.name)
}

}
finally {
    # F-062: remove the identity worktree (only created when building a non-HEAD commit).
    if ($identityWorktree) {
        & git -C $workspaceRoot worktree remove --force $identityWorktree | Out-Null
        if (Test-Path -LiteralPath $identityWorktree) {
            Remove-Item -LiteralPath $identityWorktree -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
