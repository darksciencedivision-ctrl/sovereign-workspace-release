[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Dest,

    [string] $Artifact,

    # Where the outgoing installation is moved to rather than deleted. Defaults to a sibling
    # of $Dest stamped with the version being replaced. An upgrade that destroys the only copy
    # of the previous install has no rollback, so this is not optional behaviour.
    [string] $BackupTo,

    # Where the transaction stages its controller, its artifact copy and its journal. Defaults
    # to a sibling of $Dest. Must overlap neither $Dest nor $BackupTo.
    [string] $TransactionRoot,

    # Skip the pre-upgrade state backup. Off by default and deliberately awkward to reach.
    [switch] $NoStateBackup,

    # Proceed even though the incoming build declares a different state schema than the
    # outgoing one. Rolling the binaries back does NOT undo a migration, so this is explicit.
    [switch] $AcceptStateSchemaChange,

    # Set by the staged re-invocation. Never pass this by hand.
    [string] $ResumeTransaction,

    # Test hook. Fails the named phase deliberately so the recovery path can be exercised.
    # Accepted values: prepare, cutover, postcheck, rollback.
    [string] $InjectFailureAt
)

# SWS-CORRECTIVE-01 workstream 1.1 - the upgrade is a transaction, and its controller
# outlives the installation it replaces.
#
# THE DEFECT THIS REPLACES (L1). The previous controller bound `$here = $PSScriptRoot`,
# moved the installation containing `$here` aside, and then invoked `install.ps1` through
# that former path. Upgrading the installed copy - the only copy an operator has - left no
# installation at all:
#
#     upgrade: moving the outgoing installation to ...\Sovereign Workspace.previous-1.0.0-...
#     upgrade: installing the new version
#     The term '...\Sovereign Workspace\tools\release\install.ps1' is not recognized ...
#     install dir exists: False
#
# It also read `$LASTEXITCODE` after `&`-ing a `.ps1`, which never sets it, so both of its
# failure guards were inert, and it discovered nothing about dependencies, disk space,
# permissions or quiescence until after the move.
#
# THE MODEL NOW. Six durable phases, journalled, with the controller staged outside both the
# outgoing and the incoming installation:
#
#   resolve   validate every path before any mutation; reject overlap, roots, bad filesystems
#   verify    hash the artifact against its sidecar and validate its structure; copy it to the
#             transaction root if it lives under $Dest, so displacing $Dest cannot lose it
#   preflight interpreters, disk space, write permission, quiescence, rollback feasibility,
#             state-schema compatibility - everything that could fail AFTER the move, checked
#             BEFORE it
#   snapshot  capture the operator state through backup_state.ps1, outside $Dest and $BackupTo
#   cutover   move outgoing -> $BackupTo, then install the incoming version at $Dest
#   postcheck verify_install.ps1 against the new installation
#
# A failure at cutover or postcheck rolls back automatically: the partial incoming tree is
# preserved as evidence, and the outgoing installation is moved back to $Dest. If the rollback
# itself fails, the script reports the exact surviving locations and exits non-zero. No success
# line is printed before postcheck passes.
#
# WHY PROVISIONING HAPPENS AT THE FINAL PATH. Requirement 4 asks that the incoming install be
# prepared in isolation and warns that a working staging install is not proof that its relocated
# form works. That warning is decisive here rather than advisory: this product provisions three
# `.venv` trees, and a CPython venv records its absolute path in `pyvenv.cfg` and inside every
# `Scripts\*.exe` shim, so a venv built at a staging path and then moved is broken. The
# resolution is therefore NOT to relocate a prepared install: the transaction validates the
# archive's structure and every dependency in isolation, and performs the path-bound
# provisioning once, at the final path, with a tested rollback behind it.

$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop

$utf8NoBom = [Text.UTF8Encoding]::new($false)
$script:Journal = $null
$script:TxRoot = $null

function Write-Phase {
    param([string] $Phase, [string] $Status, [hashtable] $Detail)
    $record = [ordered]@{
        utc    = (Get-Date).ToUniversalTime().ToString('o')
        phase  = $Phase
        status = $Status
    }
    if ($Detail) { foreach ($k in $Detail.Keys) { $record[$k] = $Detail[$k] } }
    $line = ($record | ConvertTo-Json -Compress -Depth 6)
    if ($script:Journal) {
        [IO.File]::AppendAllText($script:Journal, $line + "`n", $utf8NoBom)
    }
    Write-Verbose $line
}

function Fail {
    param([string] $Phase, [string] $Message)
    Write-Phase $Phase 'FAILED' @{ message = $Message }
    throw $Message
}

function Get-CanonicalPath {
    param([string] $Path)
    # Resolve through the filesystem where possible so a junction, a substituted drive or a
    # sibling-prefix confusion cannot make two different paths look unrelated.
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    if (Test-Path -LiteralPath $full) {
        try {
            $item = Get-Item -LiteralPath $full -Force
            if ($item.PSObject.Properties.Name -contains 'Target' -and $item.Target) {
                $full = [IO.Path]::GetFullPath([string]@($item.Target)[0]).TrimEnd('\')
            }
        }
        catch { }
    }
    return $full
}

function Test-PathOverlap {
    param([string] $A, [string] $B)
    if (-not $A -or -not $B) { return $false }
    $a = $A.TrimEnd('\'); $b = $B.TrimEnd('\')
    if ($a.Equals($b, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($b.StartsWith($a + '\', [StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($a.StartsWith($b + '\', [StringComparison]::OrdinalIgnoreCase)) { return $true }
    return $false
}

function Assert-SafeRoot {
    param([string] $Path, [string] $Label)
    if (-not $Path) { Fail 'resolve' "$Label was not resolved" }
    if ($Path -match '^\\\\\?\\' -or $Path -match '^\\\\\.\\') {
        Fail 'resolve' "$Label uses an unsupported device path: $Path"
    }
    if ($Path -eq [IO.Path]::GetPathRoot($Path)) {
        Fail 'resolve' "Refusing filesystem-root $($Label.ToLower()): $Path"
    }
    if ([IO.Path]::GetDirectoryName($Path) -eq $null) {
        Fail 'resolve' "$Label has no parent directory: $Path"
    }
}

function Invoke-Child {
    <#
      Run a PowerShell script as a CHILD PROCESS. The exit code lands in
      $script:LastChildExit; nothing is returned down the pipeline.

      `& script.ps1` does not set $LASTEXITCODE, which is why the previous controller's two
      failure guards never fired. A child powershell.exe does set it, so the status recorded
      here belongs to the script that ran rather than to whatever ran before it.

      The status is passed by variable rather than by return value on purpose: a PowerShell
      function returns everything it emits, so `$code = Invoke-Child ...` would bind an array
      of the child's output with the exit code on the end, and every comparison against it
      would be meaningless.
    #>
    param([string] $Script, [string[]] $ScriptArgs, [string] $LogPath, [switch] $Quiet)
    $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if (-not (Test-Path -LiteralPath $psExe -PathType Leaf)) { $psExe = 'powershell.exe' }
    # -ArgumentList joins with spaces and quotes nothing, so an install path containing a
    # space arrives as two positional arguments. Every argument is quoted here explicitly.
    $quoted = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $Script + '"'))
    foreach ($a in $ScriptArgs) {
        if ($a -match '[\s"]') { $quoted += '"' + ($a -replace '"', '\"') + '"' }
        else { $quoted += $a }
    }
    $all = $quoted
    if (-not $LogPath) {
        $LogPath = Join-Path $script:TxRoot ('child-' + [Guid]::NewGuid().ToString('N').Substring(0, 8) + '.log')
    }
    $errPath = $LogPath + '.err'
    $p = Start-Process -FilePath $psExe -ArgumentList $all -NoNewWindow -Wait -PassThru `
                       -RedirectStandardOutput $LogPath -RedirectStandardError $errPath
    if (-not $Quiet) {
        foreach ($f in @($LogPath, $errPath)) {
            if ((Test-Path -LiteralPath $f) -and (Get-Item -LiteralPath $f).Length -gt 0) {
                foreach ($l in (Get-Content -LiteralPath $f)) { Write-Output "    $l" }
            }
        }
    }
    $script:LastChildExit = [int]$p.ExitCode
}

function Get-FreeBytes {
    param([string] $Path)
    try {
        $qualifier = (Split-Path -Qualifier ([IO.Path]::GetFullPath($Path)))
        $drive = Get-PSDrive -Name $qualifier.TrimEnd(':') -ErrorAction Stop
        return [int64]$drive.Free
    }
    catch { return $null }
}

function Test-Writable {
    param([string] $Path)
    $probe = Join-Path $Path (".sovereign-upgrade-probe-" + [Guid]::NewGuid().ToString('N').Substring(0, 8))
    try {
        [IO.File]::WriteAllText($probe, 'probe', $utf8NoBom)
        Remove-Item -LiteralPath $probe -Force
        return $true
    }
    catch { return $false }
}

# ================================================================= phase: resolve
$destRoot = Get-CanonicalPath $Dest
Assert-SafeRoot $destRoot 'Destination'
if (-not (Test-Path -LiteralPath $destRoot -PathType Container)) {
    throw "Nothing to upgrade: $destRoot does not exist. Use install.ps1 for a first install."
}
$manifestPath = Join-Path $destRoot 'install-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Not an installation produced by install.ps1: $manifestPath is missing"
}

$outgoingVersion = 'unknown'
$outgoingSchema = 'unknown'
$versionPath = Join-Path $destRoot 'VERSION.json'
if (Test-Path -LiteralPath $versionPath -PathType Leaf) {
    $outgoingDoc = Get-Content -Raw -LiteralPath $versionPath | ConvertFrom-Json
    $outgoingVersion = [string]$outgoingDoc.version
    if ($outgoingDoc.PSObject.Properties.Name -contains 'state_schema') {
        $outgoingSchema = [string]$outgoingDoc.state_schema
    }
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$destParent = Split-Path -Parent $destRoot
$destLeaf = Split-Path -Leaf $destRoot

if (-not $BackupTo) { $BackupTo = Join-Path $destParent ("$destLeaf.previous-$outgoingVersion-$stamp") }
$backupRoot = [IO.Path]::GetFullPath($BackupTo).TrimEnd('\')
Assert-SafeRoot $backupRoot 'Rollback location'

if (-not $TransactionRoot) { $TransactionRoot = Join-Path $destParent ".sovereign-upgrade-$stamp" }
$txRoot = [IO.Path]::GetFullPath($TransactionRoot).TrimEnd('\')
Assert-SafeRoot $txRoot 'Transaction root'
$script:TxRoot = $txRoot

foreach ($pair in @(
        @{ a = $destRoot;   an = 'destination';      b = $backupRoot; bn = 'rollback location' },
        @{ a = $destRoot;   an = 'destination';      b = $txRoot;     bn = 'transaction root' },
        @{ a = $backupRoot; an = 'rollback location'; b = $txRoot;    bn = 'transaction root' })) {
    if (Test-PathOverlap $pair.a $pair.b) {
        throw ("Refusing overlapping paths: the {0} ({1}) and the {2} ({3}) contain one another." `
               -f $pair.an, $pair.a, $pair.bn, $pair.b)
    }
}
if (Test-Path -LiteralPath $backupRoot) {
    throw "Refusing to overwrite an existing rollback location: $backupRoot"
}
if ((Test-Path -LiteralPath $txRoot) -and -not $ResumeTransaction) {
    throw "Refusing to reuse an existing transaction root: $txRoot"
}

New-Item -ItemType Directory -Path $txRoot -Force | Out-Null
$script:Journal = Join-Path $txRoot 'upgrade-journal.jsonl'
$logDir = Join-Path $txRoot 'logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

Write-Phase 'resolve' 'BEGIN' @{
    dest = $destRoot; rollback = $backupRoot; transaction = $txRoot
    outgoing_version = $outgoingVersion; outgoing_state_schema = $outgoingSchema
}

# The controller must survive the destination being displaced. Stage it - and everything it
# invokes - into the transaction root, then hand off. `$PSScriptRoot` in the staged copy points
# at the staged copy, so nothing this script runs afterwards resolves through $destRoot.
$here = $PSScriptRoot
$stagedController = Join-Path $txRoot 'controller'
$selfIsStaged = $here.TrimEnd('\').Equals($stagedController, [StringComparison]::OrdinalIgnoreCase)

Write-Output "upgrade: outgoing installation is version $outgoingVersion at $destRoot"
Write-Output "upgrade: transaction root $txRoot"

# ================================================================= phase: verify
Write-Phase 'verify' 'BEGIN' @{}
if (-not $Artifact) {
    $controllerWorkspace = [IO.Path]::GetFullPath((Join-Path $here '..\..'))
    $incomingVersionFile = Join-Path $controllerWorkspace 'VERSION.json'
    if (-not (Test-Path -LiteralPath $incomingVersionFile -PathType Leaf)) {
        Fail 'verify' ("No -Artifact was given and no VERSION.json sits beside this controller " +
                       "at $controllerWorkspace. Pass -Artifact explicitly.")
    }
    $incoming = (Get-Content -Raw -LiteralPath $incomingVersionFile | ConvertFrom-Json).version
    $Artifact = Join-Path $controllerWorkspace "release-artifacts\sovereign-workspace-$incoming-install.zip"
}
$artifactPath = [IO.Path]::GetFullPath($Artifact)
if (-not (Test-Path -LiteralPath $artifactPath -PathType Leaf)) {
    Fail 'verify' "Install artifact not found: $artifactPath"
}
$sidecarPath = $artifactPath + '.sha256'
if (-not (Test-Path -LiteralPath $sidecarPath -PathType Leaf)) {
    Fail 'verify' "Install artifact sidecar not found: $sidecarPath"
}
$expectedHash = ((Get-Content -Raw -LiteralPath $sidecarPath).Trim() -split '\s+')[0].ToLowerInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $artifactPath).Hash.ToLowerInvariant()
if ($expectedHash -ne $actualHash) {
    Fail 'verify' "Install artifact SHA-256 mismatch - refusing to upgrade (sidecar $expectedHash, measured $actualHash)"
}

# An artifact stored under the outgoing installation would be carried away by the cutover move.
# Copy it to the transaction root and use the stable copy from here on.
if (Test-PathOverlap $destRoot $artifactPath) {
    $stableArtifact = Join-Path $txRoot ([IO.Path]::GetFileName($artifactPath))
    Copy-Item -LiteralPath $artifactPath -Destination $stableArtifact -Force
    Copy-Item -LiteralPath $sidecarPath -Destination ($stableArtifact + '.sha256') -Force
    $recheck = (Get-FileHash -Algorithm SHA256 -LiteralPath $stableArtifact).Hash.ToLowerInvariant()
    if ($recheck -ne $expectedHash) { Fail 'verify' 'Artifact copy did not reproduce its hash' }
    Write-Output "upgrade: artifact lived under the destination; using the stable copy at $stableArtifact"
    $artifactPath = $stableArtifact
    $sidecarPath = $stableArtifact + '.sha256'
}

# Structure. An archive that verifies its bytes can still be the wrong archive.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$incomingVersion = 'unknown'
$incomingSchema = 'unknown'
$zip = [IO.Compression.ZipFile]::OpenRead($artifactPath)
try {
    $names = @($zip.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
    $outside = @($names | Where-Object { -not $_.StartsWith('sovereign-workspace/', [StringComparison]::Ordinal) })
    if ($outside.Count -gt 0) {
        Fail 'verify' ("Artifact holds {0} entr(y/ies) outside the install prefix, the first being '{1}'" `
                       -f $outside.Count, $outside[0])
    }
    foreach ($required in @('sovereign-workspace/VERSION.json',
                            'sovereign-workspace/shell/src/__main__.py',
                            'sovereign-workspace/tools/release/install.ps1',
                            'sovereign-workspace/tools/release/verify_install.ps1')) {
        if ($names -notcontains $required) {
            Fail 'verify' "Artifact is missing a required entry: $required"
        }
    }
    $entry = $zip.GetEntry('sovereign-workspace/VERSION.json')
    $reader = New-Object IO.StreamReader($entry.Open())
    try { $incomingDoc = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
    $incomingVersion = [string]$incomingDoc.version
    if ($incomingDoc.PSObject.Properties.Name -contains 'state_schema') {
        $incomingSchema = [string]$incomingDoc.state_schema
    }
}
finally { $zip.Dispose() }
Write-Phase 'verify' 'OK' @{
    artifact = $artifactPath; sha256 = $actualHash
    incoming_version = $incomingVersion; incoming_state_schema = $incomingSchema
}
Write-Output "upgrade: incoming artifact verified - version $incomingVersion, sha256 $actualHash"

# ================================================================= phase: preflight
Write-Phase 'preflight' 'BEGIN' @{}
$problems = @()

# Interpreters and tools the installer needs. Discovering a missing 3.14 AFTER the move is
# exactly the failure requirement 3 names.
foreach ($spec in @(
        @{ exe = 'py'; probe = @('-3.12', '--version'); label = 'Python 3.12 (py -3.12)' },
        @{ exe = 'py'; probe = @('-3.14', '--version'); label = 'Python 3.14 (py -3.14)' })) {
    $cmd = Get-Command $spec.exe -ErrorAction SilentlyContinue
    if (-not $cmd) { $problems += "$($spec.label): the '$($spec.exe)' launcher is not on PATH"; continue }
    & $cmd.Source @($spec.probe) > $null 2>&1
    if ($LASTEXITCODE -ne 0) { $problems += "$($spec.label) is not available" }
}
foreach ($tool in @('npm.cmd', 'node.exe', 'git.exe')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        $problems += "$tool is not on PATH"
    }
}

# Disk space: the incoming install, the retained outgoing copy and the state snapshot all have
# to fit. The expanded install is several times the archive; 6x is the measured order and is
# deliberately generous rather than exact.
$artifactBytes = (Get-Item -LiteralPath $artifactPath).Length
$outgoingBytes = 0
try {
    $outgoingBytes = [int64](Get-ChildItem -LiteralPath $destRoot -Force -Recurse -File -ErrorAction SilentlyContinue |
                             Measure-Object -Property Length -Sum).Sum
}
catch { }
$needed = ($artifactBytes * 6) + $outgoingBytes
$free = Get-FreeBytes $destParent
if ($free -ne $null -and $free -lt $needed) {
    $problems += ("Insufficient free space on the destination volume: need about {0:N0} bytes, {1:N0} free" -f $needed, $free)
}

# Permissions on every directory this transaction writes to.
foreach ($writable in @(@{ p = $destParent; n = 'the destination parent' },
                        @{ p = $txRoot;     n = 'the transaction root' })) {
    if (-not (Test-Writable $writable.p)) {
        $problems += "No write permission on $($writable.n): $($writable.p)"
    }
}

# Quiescence. Only processes running FROM the outgoing installation are the transaction's
# business; nothing else on the host is touched or reported as a conflict.
$destPrefix = $destRoot + '\'
$occupants = @()
try {
    $occupants = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $p = $null
        try { $p = $_.Path } catch { $p = $null }
        $p -and $p.StartsWith($destPrefix, [StringComparison]::OrdinalIgnoreCase)
    })
}
catch { }
if ($occupants.Count -gt 0) {
    $listed = ($occupants | ForEach-Object { "$($_.ProcessName) (pid $($_.Id))" }) -join ', '
    $problems += ("The outgoing installation is not quiescent: $listed. " +
                  "Stop them and re-run; this transaction never terminates a process it did not start.")
}

# Rollback feasibility: the outgoing installation has to be movable to the rollback location on
# the same volume, or the cutover has no cheap undo.
if ((Split-Path -Qualifier $destRoot) -ne (Split-Path -Qualifier $backupRoot)) {
    $problems += ("Rollback would cross volumes: $destRoot and $backupRoot are on different " +
                  "drives, so the cutover could not be undone by a move.")
}

# State-schema compatibility. Moving old binaries back does NOT undo a state migration, so a
# schema change is surfaced here and requires an explicit acknowledgement.
if ($incomingSchema -ne $outgoingSchema -and
    $outgoingSchema -ne 'unknown' -and $incomingSchema -ne 'unknown') {
    if (-not $AcceptStateSchemaChange) {
        $problems += ("State schema changes from '$outgoingSchema' to '$incomingSchema'. " +
                      "Rolling the installation back does NOT reverse a state migration; the " +
                      "pre-upgrade state snapshot is the only route back. Re-run with " +
                      "-AcceptStateSchemaChange once you have read docs/OPERATIONS.md.")
    }
}

if ($problems.Count -gt 0) {
    Write-Output ''
    Write-Output "upgrade: REFUSED before any change was made. $($problems.Count) blocking problem(s):"
    $problems | ForEach-Object { Write-Output "  - $_" }
    Write-Phase 'preflight' 'FAILED' @{ problems = $problems }
    Write-Output ''
    Write-Output "  Nothing was moved. The installation at $destRoot is untouched."
    exit 2
}
Write-Phase 'preflight' 'OK' @{ artifact_bytes = $artifactBytes; outgoing_bytes = $outgoingBytes }
Write-Output 'upgrade: preflight clear - dependencies, space, permissions, quiescence, rollback route'

# Stage the controller now that preflight has passed, and hand off to the staged copy so the
# rest of the transaction cannot be executing out of the directory it is about to move.
if (-not $selfIsStaged) {
    New-Item -ItemType Directory -Path $stagedController -Force | Out-Null
    Copy-Item -Path (Join-Path $here '*') -Destination $stagedController -Recurse -Force
    Write-Phase 'stage' 'OK' @{ controller = $stagedController }
    Write-Output "upgrade: controller staged at $stagedController"

    $handoff = @('-Dest', $destRoot, '-Artifact', $artifactPath, '-BackupTo', $backupRoot,
                 '-TransactionRoot', $txRoot, '-ResumeTransaction', $txRoot)
    if ($NoStateBackup) { $handoff += '-NoStateBackup' }
    if ($AcceptStateSchemaChange) { $handoff += '-AcceptStateSchemaChange' }
    if ($InjectFailureAt) { $handoff += @('-InjectFailureAt', $InjectFailureAt) }
    Invoke-Child (Join-Path $stagedController 'upgrade.ps1') $handoff `
                 (Join-Path $logDir 'staged-controller.log')
    exit $script:LastChildExit
}

# ================================================================= phase: snapshot
$stateRoot = $env:SOVEREIGN_WORKSPACE_STATE
if (-not $stateRoot) {
    $localAppData = $env:LOCALAPPDATA
    if (-not $localAppData) { $localAppData = Join-Path $env:USERPROFILE 'AppData\Local' }
    $stateRoot = Join-Path $localAppData 'SovereignWorkspace'
}
$stateSnapshot = $null
Write-Phase 'snapshot' 'BEGIN' @{ state_root = $stateRoot }
if ($NoStateBackup) {
    Write-Output 'upgrade: state snapshot SKIPPED at explicit operator request'
    Write-Phase 'snapshot' 'SKIPPED' @{ reason = 'operator passed -NoStateBackup' }
}
elseif (Test-Path -LiteralPath $stateRoot -PathType Container) {
    $stateSnapshot = Join-Path $txRoot "state-pre-upgrade-$stamp.zip"
    Write-Output "upgrade: capturing operator state to $stateSnapshot"
    Invoke-Child (Join-Path $here 'backup_state.ps1') `
                 @('-StateRoot', $stateRoot, '-Out', $stateSnapshot) `
                 (Join-Path $logDir 'snapshot.log')
    $code = $script:LastChildExit
    if ($code -ne 0) {
        Fail 'snapshot' ("State snapshot failed with exit $code. Nothing has been moved; the " +
                         "installation at $destRoot is untouched. See $logDir\snapshot.log.")
    }
    Write-Phase 'snapshot' 'OK' @{ archive = $stateSnapshot }
}
else {
    Write-Output "upgrade: no operator state at $stateRoot - nothing to snapshot"
    Write-Phase 'snapshot' 'EMPTY' @{}
}

if ($InjectFailureAt -eq 'prepare') {
    Write-Phase 'prepare' 'FAILED' @{ message = 'injected failure' }
    Write-Output 'upgrade: FAILED during preparation (injected). Nothing was moved.'
    Write-Output "  installation still at $destRoot"
    exit 3
}

# ================================================================= phase: cutover
Write-Phase 'cutover' 'BEGIN' @{ from = $destRoot; to = $backupRoot }
Write-Output "upgrade: moving the outgoing installation to $backupRoot"
Move-Item -LiteralPath $destRoot -Destination $backupRoot
if (Test-Path -LiteralPath $destRoot) {
    Fail 'cutover' "Destination is still present after the move: $destRoot"
}
Write-Phase 'cutover' 'MOVED' @{}

$rollbackNeeded = $false
$failureReason = $null
$installLog = Join-Path $logDir 'install.log'

if ($InjectFailureAt -eq 'cutover') {
    $rollbackNeeded = $true
    $failureReason = 'Installation of the incoming version failed (injected failure at cutover).'
    Write-Phase 'cutover' 'FAILED' @{ message = $failureReason }
}
else {
    Write-Output 'upgrade: installing the incoming version'
    Invoke-Child (Join-Path $here 'install.ps1') `
                 @('-Dest', $destRoot, '-Artifact', $artifactPath) $installLog
    $code = $script:LastChildExit
    if ($code -ne 0) {
        $rollbackNeeded = $true
        $failureReason = "Installation of the incoming version failed with exit $code. See $installLog."
        Write-Phase 'cutover' 'FAILED' @{ exit_code = $code; log = $installLog }
    }
    else {
        Write-Phase 'cutover' 'OK' @{ log = $installLog }
    }
}

# ================================================================= phase: postcheck
if (-not $rollbackNeeded) {
    Write-Phase 'postcheck' 'BEGIN' @{}
    if ($InjectFailureAt -eq 'postcheck') {
        $rollbackNeeded = $true
        $failureReason = 'Post-cutover verification failed (injected failure at postcheck).'
        Write-Phase 'postcheck' 'FAILED' @{ message = $failureReason }
    }
    else {
        Write-Output 'upgrade: verifying the new installation'
        $verifyLog = Join-Path $logDir 'verify.log'
        Invoke-Child (Join-Path $here 'verify_install.ps1') @('-Dest', $destRoot) $verifyLog
        $code = $script:LastChildExit
        if ($code -ne 0) {
            $rollbackNeeded = $true
            $failureReason = "Post-cutover verification failed with exit $code. See $verifyLog."
            Write-Phase 'postcheck' 'FAILED' @{ exit_code = $code; log = $verifyLog }
        }
        else {
            Write-Phase 'postcheck' 'OK' @{}
        }
    }
}

# ================================================================= phase: rollback
if ($rollbackNeeded) {
    Write-Output ''
    Write-Output "upgrade: FAILED - $failureReason"
    Write-Phase 'rollback' 'BEGIN' @{ reason = $failureReason }

    $preserved = $null
    $rollbackErrors = @()
    try {
        if ($InjectFailureAt -eq 'rollback') { throw 'injected rollback failure' }
        if (Test-Path -LiteralPath $destRoot) {
            # Keep the failed incoming tree as evidence rather than deleting it.
            $preserved = Join-Path $txRoot "failed-incoming-$stamp"
            Move-Item -LiteralPath $destRoot -Destination $preserved
            Write-Output "upgrade: failed incoming installation preserved at $preserved"
        }
        Move-Item -LiteralPath $backupRoot -Destination $destRoot
        Write-Output "upgrade: rolled back - the previous installation is at $destRoot again"
        Write-Phase 'rollback' 'OK' @{ preserved_incoming = $preserved }
    }
    catch {
        $rollbackErrors += $_.Exception.Message
        Write-Phase 'rollback' 'FAILED' @{ errors = $rollbackErrors }
    }

    Write-Output ''
    if ($rollbackErrors.Count -gt 0) {
        Write-Output '  ROLLBACK DID NOT COMPLETE. Recover by hand from these exact locations:'
        Write-Output "    previous installation   $backupRoot"
        if ($preserved) { Write-Output "    failed incoming tree    $preserved" }
        if ($stateSnapshot) { Write-Output "    state snapshot          $stateSnapshot" }
        Write-Output "    transaction journal     $script:Journal"
        Write-Output ''
        Write-Output '  To recover: move the previous installation back to'
        Write-Output "    $destRoot"
        Write-Output '  then re-run tools\release\verify_install.ps1 -Dest <that path>.'
        $rollbackErrors | ForEach-Object { Write-Output "    rollback error: $_" }
        exit 5
    }

    Write-Output '  The previous installation is running again. Nothing was deleted.'
    Write-Output "    installation            $destRoot"
    if ($preserved) { Write-Output "    failed incoming tree    $preserved" }
    if ($stateSnapshot) { Write-Output "    state snapshot          $stateSnapshot" }
    Write-Output "    transaction journal     $script:Journal"
    exit 4
}

# ================================================================= success
$newVersion = 'unknown'
if (Test-Path -LiteralPath (Join-Path $destRoot 'VERSION.json') -PathType Leaf) {
    $newVersion = [string](Get-Content -Raw -LiteralPath (Join-Path $destRoot 'VERSION.json') | ConvertFrom-Json).version
}
Write-Phase 'complete' 'OK' @{ from = $outgoingVersion; to = $newVersion }

Write-Output ''
Write-Output "upgrade: COMPLETE  $outgoingVersion -> $newVersion"
Write-Output "  installed at        $destRoot"
Write-Output "  previous version at $backupRoot   (nothing was deleted; move it back to roll back)"
if ($stateSnapshot) { Write-Output "  state snapshot at   $stateSnapshot" }
Write-Output "  operator state at   $stateRoot   (carried forward, not copied into the install)"
Write-Output "  transaction journal $script:Journal"
Write-Output ''
Write-Output '  Nothing was removed by this upgrade. Delete the previous installation, the state'
Write-Output '  snapshot and the transaction root yourself once the new version has proved itself.'
if ($incomingSchema -ne $outgoingSchema -and $outgoingSchema -ne 'unknown' -and $incomingSchema -ne 'unknown') {
    Write-Output ''
    Write-Output "  STATE SCHEMA CHANGED: $outgoingSchema -> $incomingSchema. Moving the previous"
    Write-Output '  installation back does NOT reverse that. To return to the previous version you'
    Write-Output '  must also restore the state snapshot named above.'
}
exit 0
