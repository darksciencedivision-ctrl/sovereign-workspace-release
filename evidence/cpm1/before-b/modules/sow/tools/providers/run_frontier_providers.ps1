<#
.SYNOPSIS
    Grok Build / Gemini-Antigravity provider bootstrap and diagnostic runner (Phase 18A, OP-12).

.DESCRIPTION
    The operator's one command surface for the two frontier providers authorized by register
    OP-12: status, install, login, probe, launch.

    This is a BOOTSTRAP AND DIAGNOSTIC SURFACE ONLY (operator directive section 1). It is not a
    second orchestration system: it owns no pane and publishes no artifact.

    -Action probe MAKES ONE LIVE, BILLABLE CALL. As of 18C it is no longer a bare child: the Python
    engine admits it through the live-operation switch AND a governed session
    (node_runtime/supervisor/provider_probe_session.py) that mints a node identity, holds ONE I-X3
    lease on that provider's own subscription for exactly the child's lifetime, runs it inside the
    repository's job-object boundary with a credential-scrubbed environment, and releases the lease
    on every exit path - U234, discharged. The probe output PRINTS that governed record (subscription,
    lease, supervised execution, and the measured teardown incl. the lease returning to zero), so
    this description is something the operator can check rather than take on trust - operator
    directive section 17. What is still NOT claimed: no Sovereign node RECORD exists for either
    provider. Until 2026-08-01 that was because the canonical vocabulary refused the ids; the
    operator ruled U227 that day (OP-12.1) and node@1.1 admits both, so the remaining - narrower -
    reason is simply that nothing in this path is wired to create a record.

    -Action login remains the one action that starts the vendor's own sign-in flow, which for
    Antigravity is a full vendor TUI (U241) - invariant-2 tension, and it may not become the pattern
    for anything: panes and workers go through the existing supervised ConPTY + launch-ticket path
    (operator directive section 9). Everywhere else the existing Sovereign node runtime remains
    responsible for process supervision, ConPTY sessions, node identity, dispatch, workspace
    binding, leases, artifacts, tool authority, cleanup and recovery.

    All classification logic lives in tools/providers/frontier_provider_recon.py, which is covered
    by the deterministic suite (tests/unit/test_frontier_provider_recon.py). This script is the
    thin, testable shell around it, so status semantics cannot drift between the two. The
    decisions that are genuinely this script's own - i.e. not read off an engine state - are:
    which AVAILABLE providers a launch carries a command hint for (carriage, not classification);
    how an unverifiable install is reported (exit 7 below); that a FAILED install is reported as
    exit 5; the per-provider login argv (duplicated from the engine's descriptor - U232); and the
    sequential warning on -Action login -Provider all (warned, never blocked - I-30). This
    enumeration is checkable, and round-4 spec-audit finding 14 is why it is now longer than it
    was: a closed list in a header is a claim like any other.

    What this script will NEVER do (operator directive section 3):
      - edit application source, create commits, or touch git state;
      - read, print, copy or store an authentication token, credential file or cookie;
      - install anything without an explicit -InstallMissing;
      - launch an interactive authentication flow during -Action status;
      - modify docs/loop/LOOP_STATE.json or start the autonomous build loop.

    Repeat-safe: every action is idempotent. Running -Action install twice installs nothing the
    second time; -Action status never mutates anything at all.

.PARAMETER Provider
    all | grok | gemini   (default: all)

.PARAMETER Action
    status | install | login | probe | launch   (default: status)

.PARAMETER RepoRoot
    Repository root. Defaults to the repository this script lives in.

.PARAMETER Model
    Optional model slug for -Action probe. Must be a slug the provider's own `models` command
    listed; nothing here invents one.

.PARAMETER Prompt
    Optional probe prompt override. The provider must still return the exact acceptance token.

.PARAMETER InstallMissing
    Required before -Action install will install anything.

.PARAMETER NoLaunch
    With -Action launch: run every status check and print the capability table, then stop without
    starting the desktop shell.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools/providers/run_frontier_providers.ps1 -Action status

.NOTES
    Exit codes:
      0 success
      2 install requested without -InstallMissing (nothing was installed)
      3 probe refused or not accepted (including a fail-closed live-authorization denial)
      4 install completed but PATH still lacks the command - a NEW terminal session is required
      5 the requested action needs a provider that is not available; ALSO: an install command
        itself failed or threw (the install did not happen - round-4 gate-validator finding 3)
      6 environment problem (repository root, Python interpreter, or the engine itself)
      7 install unverifiable - the vendor's PowerShell installer set no exit code and the command
        is still unresolvable, so a PATH refresh and a silent failure cannot be told apart here
      * -Action launch passes the desktop shell's own exit code straight through

    Every action reports through the script-scoped $script:ActionExit rather than a function
    return value: in PowerShell a native command's stdout joins the caller's output stream, so
    `exit (Invoke-Something)` would receive an array instead of the code on exactly the paths
    where a command actually ran (spec-audit F-6b). Environment failures likewise use
    Write-Failure + exit rather than Write-Error, whose terminating behaviour under
    $ErrorActionPreference='Stop' made the documented code unreachable (F-6a).

    Because the exit code no longer travels through the pipeline, native commands are invoked
    WITHOUT `| Out-Host`: their output reaches the console directly, which the interactive
    sign-in flows need (piping a full-screen TUI's stdout typically breaks its rendering -
    spec-audit N-14).
#>
[CmdletBinding()]
param(
    [ValidateSet('all', 'grok', 'gemini')]
    [string]$Provider = 'all',

    [ValidateSet('status', 'install', 'login', 'probe', 'launch')]
    [string]$Action = 'status',

    [string]$RepoRoot,

    [string]$Model,

    [string]$Prompt,

    [switch]$InstallMissing,

    [switch]$NoLaunch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# The Gemini display name carries a non-ASCII separator (operator directive section 14 fixes the
# label exactly). Windows PowerShell's default console encoding would render it as '?', so the
# console is switched to UTF-8 for this process only - no global setting is changed.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$EXIT_OK = 0
$EXIT_INSTALL_NOT_AUTHORIZED = 2
$EXIT_PROBE_REFUSED = 3
$EXIT_PATH_REFRESH_REQUIRED = 4
$EXIT_PROVIDER_UNAVAILABLE = 5
$EXIT_ENVIRONMENT = 6
# An install whose success nothing could verify (a PowerShell installer sets no exit code) and
# whose command is still unresolvable. Deliberately NOT code 4: 4 asserts the install happened.
$EXIT_INSTALL_UNVERIFIED = 7

# Every action writes its result here; main exits with it. See .NOTES for why a return value
# cannot carry it.
$script:ActionExit = $EXIT_OK

function Write-Failure {
    # Write-Error is a TERMINATING error under $ErrorActionPreference='Stop', so a following
    # `exit <code>` never runs and the caller sees exit 1 instead of the documented code. This
    # writes the same text to stderr without terminating, leaving the exit code to the caller.
    param([Parameter(Mandatory)] [string]$Message)
    [Console]::Error.WriteLine($Message)
}

function Test-HasProperty {
    # Under Set-StrictMode -Version Latest, reading a property an object does not have is a
    # TERMINATING error - so `$null -ne $obj.maybe` cannot be used to ask whether it is there.
    # The engine's probe document is deliberately shaped by outcome (a refusal carries no
    # `governed` key), so the runner must ask about presence, not value.
    param($InputObject, [Parameter(Mandatory)] [string]$Name)
    if ($null -eq $InputObject) { return $false }
    return [bool]($InputObject.PSObject.Properties.Match($Name).Count)
}

# ---------------------------------------------------------------------------------------------
# Environment resolution
# ---------------------------------------------------------------------------------------------
function Resolve-RepoRoot {
    param([string]$Candidate)
    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        $Candidate = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
    }
    if (-not (Test-Path $Candidate)) {
        Write-Failure "RepoRoot does not exist: $Candidate"
        exit $EXIT_ENVIRONMENT
    }
    $root = (Resolve-Path $Candidate).Path
    # Refuse to operate against a directory that is not this repository: the engine reads the
    # frozen schemas and the live-authorization module from here, and a wrong root would produce
    # a confident but meaningless report.
    if (-not (Test-Path (Join-Path $root 'AUTONOMOUS_BUILD_DIRECTIVE.md'))) {
        Write-Failure "Not a Sovereign Orchestration Workspace root (no AUTONOMOUS_BUILD_DIRECTIVE.md): $root"
        exit $EXIT_ENVIRONMENT
    }
    return $root
}

function Resolve-PythonCommand {
    # The repository targets Python 3.12 (D-LANG-01). Prefer the launcher's 3.12, then any
    # launcher, then python on PATH; report honestly if none can run.
    $candidates = @(
        @{ File = 'py';     Args = @('-3.12') },
        @{ File = 'py';     Args = @() },
        @{ File = 'python'; Args = @() }
    )
    foreach ($c in $candidates) {
        $cmd = Get-Command $c.File -ErrorAction SilentlyContinue
        if ($null -eq $cmd) { continue }
        try {
            $probeArgs = @($c.Args + @('-c', 'import sys; print(sys.version_info[0])'))
            $out = & $cmd.Source @probeArgs 2>$null
            if ($LASTEXITCODE -eq 0 -and "$out".Trim() -eq '3') {
                return @{ File = $cmd.Source; Args = $c.Args }
            }
        } catch {
            continue
        }
    }
    return $null
}

function Invoke-ReconEngine {
    <#
      Runs the Python status/recon/probe engine and returns its parsed report plus exit code.
      The report travels through a temp FILE rather than the pipe: the engine emits UTF-8 and
      Windows PowerShell's console pipe would mangle the display name otherwise.
    #>
    param(
        [Parameter(Mandatory)] [string]$RepoRootPath,
        [Parameter(Mandatory)] [hashtable]$Python,
        [Parameter(Mandatory)] [string]$EngineAction,
        [string]$ProviderSelector = 'all',
        [string[]]$Extra = @()
    )
    $script = Join-Path $RepoRootPath 'tools\providers\frontier_provider_recon.py'
    if (-not (Test-Path $script)) {
        Write-Failure "Recon engine missing: $script"
        exit $EXIT_ENVIRONMENT
    }
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("sow_provider_{0}.json" -f ([guid]::NewGuid().ToString('N')))
    $argList = @($Python.Args + @($script, '--provider', $ProviderSelector, '--action', $EngineAction, '--emit', $tmp) + $Extra)
    $prevPythonPath = $env:PYTHONPATH
    $prevIoEncoding = $env:PYTHONIOENCODING
    try {
        $env:PYTHONPATH = $RepoRootPath
        $env:PYTHONIOENCODING = 'utf-8'
        Push-Location $RepoRootPath
        try {
            & $Python.File @argList | Out-Null
            $code = $LASTEXITCODE
        } finally {
            Pop-Location
        }
        if (-not (Test-Path $tmp)) {
            Write-Failure "Recon engine produced no report (exit $code)."
            exit $EXIT_ENVIRONMENT
        }
        $json = Get-Content -Path $tmp -Raw -Encoding UTF8
        return @{ Report = ($json | ConvertFrom-Json); ExitCode = $code }
    } finally {
        $env:PYTHONPATH = $prevPythonPath
        $env:PYTHONIOENCODING = $prevIoEncoding
        if (Test-Path $tmp) { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
    }
}

# ---------------------------------------------------------------------------------------------
# Rendering (operator directive section 6 - independent per provider, distinct states)
# ---------------------------------------------------------------------------------------------
function Write-ProviderStatus {
    param([Parameter(Mandatory)] $Entry)
    Write-Host ''
    Write-Host ("=== {0}  [{1}]" -f $Entry.display, $Entry.provider)
    Write-Host ("  command            : {0}" -f $Entry.command)
    Write-Host ("  command found      : {0}" -f $Entry.command_found)
    Write-Host ("  executable         : {0}" -f $(if ($Entry.executable) { $Entry.executable } else { '(none)' }))
    Write-Host ("  version            : {0}" -f $(if ($Entry.version) { $Entry.version } else { '(unknown)' }))
    Write-Host ("  state              : {0}" -f $Entry.state)
    # A state that reads wider than it is must never be printed alone (spec-audit F-2).
    if ($Entry.state_caveat) { Write-Host ("    ^ caveat          : {0}" -f $Entry.state_caveat) }
    # The gloss must follow the VALUE. Printed unconditionally it told the operator, on the same
    # line as `False`, that the CLI HAD reported a signed-in session - on exactly the provider
    # (Antigravity, U228) whose auth is unverifiable offline, which is the case the field was
    # renamed for in the first place (round-3 spec-audit MAJOR-1 / gate-validator A-1).
    $authGloss = if ($Entry.auth_confirmed) {
        'the CLI itself reported a signed-in session - NOT launch readiness'
    } else {
        'NOTHING reported a signed-in session here - which is not a claim that the operator is signed out'
    }
    Write-Host ("  auth confirmed     : {0}  ({1})" -f $Entry.auth_confirmed, $authGloss)
    Write-Host ("  authentication     : {0}  {1}" -f $Entry.auth_state, $Entry.auth_detail)
    $models = @($Entry.models)
    Write-Host ("  models             : ({0}) {1}" -f $models.Count, $(if ($models.Count) { ($models -join ', ') } else { '(none reported - fails the picker closed)' }))
    if ($Entry.default_model) { Write-Host ("  default model      : {0}" -f $Entry.default_model) }
    Write-Host ("  headless / interactive / structured : {0} / {1} / {2}" -f `
        $Entry.headless_supported, $Entry.interactive_supported, $Entry.structured_output_supported)
    Write-Host ("  subscription       : {0} (allowance {1}); lease {2}" -f `
        $Entry.subscription_resource, $Entry.terminal_allowance, $Entry.lease_state)
    Write-Host ("  app registration   : {0} - {1}" -f $Entry.registration_state, $Entry.registration_detail)
    if ($Entry.state -eq 'NOT_INSTALLED') {
        Write-Host ("  install with       : {0}   (this runner: -Action install -InstallMissing)" -f $Entry.install_command)
    }
}

function Write-CapabilityTable {
    param([Parameter(Mandatory)] $Report)
    Write-Host ''
    Write-Host 'Provider capability table'
    Write-Host '-------------------------'
    $rows = foreach ($p in $Report.providers) {
        [pscustomobject]@{
            Provider     = $p.provider
            Display      = $p.display
            State        = $p.state
            Auth         = $p.auth_state
            AuthConfirmed  = $p.auth_confirmed
            Models       = @($p.models).Count
            Registered   = $p.registration_state
        }
    }
    $rows | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
}

# ---------------------------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------------------------
function Invoke-StatusAction {
    param($RepoRootPath, $Python, $Selector)
    $result = Invoke-ReconEngine -RepoRootPath $RepoRootPath -Python $Python -EngineAction 'status' -ProviderSelector $Selector
    foreach ($entry in $result.Report.providers) { Write-ProviderStatus -Entry $entry }
    Write-CapabilityTable -Report $result.Report
    Write-Host ''
    # Round-4 spec-audit finding 9: this line used to read 'No credential was read, printed, or
    # stored by this run' - phrased as an observation about the run, produced by nothing in the
    # run, and unable to go false. It is a STRUCTURAL claim, so it now says so and names what
    # enforces it.
    Write-Host 'Credential isolation is structural, not observed: no code path in this script or'
    Write-Host 'its engine opens a credential store (operator directive section 13). Enforced by'
    Write-Host 'tests/unit/test_run_frontier_providers_ps1.py::TestRunnerProhibitions.'
}

function Invoke-InstallAction {
    param($RepoRootPath, $Python, $Selector, [bool]$Authorized)
    $report = Invoke-ReconEngine -RepoRootPath $RepoRootPath -Python $Python -EngineAction 'status' -ProviderSelector $Selector
    foreach ($entry in $report.Report.providers) {
        if ($entry.command_found) {
            Write-Host ("{0}: already installed at {1} - nothing to do (repeat-safe)." -f $entry.display, $entry.executable)
            continue
        }
        if (-not $Authorized) {
            Write-Host ("{0}: NOT installed. Nothing was installed: -InstallMissing was not supplied." -f $entry.display)
            Write-Host ("  the operator's own install command is: {0}" -f $entry.install_command)
            $script:ActionExit = $EXIT_INSTALL_NOT_AUTHORIZED
            continue
        }
        Write-Host ("{0}: installing with the provider's official command: {1}" -f $entry.display, $entry.install_command)
        $installExit = 0
        # Whether the install's SUCCESS is machine-verifiable at all. A native command's exit code
        # is evidence; a PowerShell installer's silence is not. Carried separately so the
        # post-condition below can say which of the two it is looking at.
        $installVerifiable = $true
        switch ($entry.provider) {
            'grok_build' {
                & npm install -g '@xai-official/grok'
                $installExit = $LASTEXITCODE
            }
            'google_antigravity' {
                # The vendor's documented installer, quoted from operator directive 4.2. Executed
                # ONLY under an explicit -InstallMissing, and never during status. It is remote
                # code with no published checksum to pin - an unverified-integrity step the
                # operator authorized by name, recorded as such rather than dressed up as safe.
                Write-Host '  NOTE: this executes the vendor installer fetched over the network.'
                Write-Host '  Antigravity publishes no checksum for it, so its integrity is unverified.'
                # Invoke-Expression of a POWERSHELL installer does not set $LASTEXITCODE unless a
                # NATIVE command inside it fails, so reading it here returned a STALE 0 - the one
                # the Python engine left moments earlier - and a silently failed install fell
                # straight through to the PATH-refresh branch, reporting an install that never
                # happened with exit 4. That is the N-7b defect surviving on the ONE path that runs
                # unverified remote code (round-3 gate-validator M-1 / spec-audit MEDIUM-5).
                $global:LASTEXITCODE = 0
                $installVerifiable = $false
                try {
                    Invoke-Expression (Invoke-RestMethod 'https://antigravity.google/cli/install.ps1')
                    $installExit = if ($LASTEXITCODE) { $LASTEXITCODE } else { 0 }
                } catch {
                    # A fetch or installer failure is an install failure, not a PATH problem.
                    # Untrapped it was a terminating error under -Stop and exited 1, a code the
                    # documented table does not carry (gate-validator A-9).
                    Write-Failure ("  the vendor installer failed: {0}" -f $_.Exception.Message)
                    $installExit = 1
                }
            }
            default {
                Write-Failure ("unknown provider id {0}" -f $entry.provider)
                $script:ActionExit = $EXIT_ENVIRONMENT
                return
            }
        }
        # A FAILED install must not be reported as a successful one needing a new terminal. Without
        # this check the next branch says "installed, but not on PATH in THIS session" and exits 4
        # - a false claim with the wrong machine-readable code (spec-audit N-7b).
        if ($installExit -ne 0) {
            Write-Failure ("{0}: install command FAILED (exit {1}) - nothing was installed." -f $entry.display, $installExit)
            $script:ActionExit = $EXIT_PROVIDER_UNAVAILABLE
            continue
        }
        # Resolve the ACTUAL executable through normal discovery - never a hardcoded npm roaming
        # path (operator directive section 4.1).
        $found = Get-Command $entry.command -ErrorAction SilentlyContinue
        if ($null -eq $found) {
            if ($installVerifiable) {
                Write-Host ("{0}: installed, but '{1}' is still not on PATH in THIS session." -f $entry.display, $entry.command)
                Write-Host '  Open a NEW terminal and re-run -Action status. (PATH changes do not reach a running session.)'
                $script:ActionExit = $EXIT_PATH_REFRESH_REQUIRED
            } else {
                # No exit code proved this install happened, and the command is not resolvable. It
                # is EITHER a PATH refresh OR a silent failure and this runner cannot tell which -
                # so it says exactly that, under its own code, instead of asserting an install.
                Write-Host ("{0}: the vendor installer returned no failure, but '{1}' is not resolvable in this session." -f $entry.display, $entry.command)
                Write-Host '  This runner CANNOT distinguish a PATH refresh from a silent install failure here:'
                Write-Host '  the installer reports nothing machine-readable. Open a NEW terminal and re-run -Action'
                Write-Host '  status - if it still reports NOT_INSTALLED, the install did not happen.'
                $script:ActionExit = $EXIT_INSTALL_UNVERIFIED
            }
        } else {
            Write-Host ("{0}: resolved to {1}" -f $entry.display, $found.Source)
        }
    }
}

function Invoke-LoginAction {
    param($RepoRootPath, $Python, $Selector)
    $report = Invoke-ReconEngine -RepoRootPath $RepoRootPath -Python $Python -EngineAction 'status' -ProviderSelector $Selector
    $entries = @($report.Report.providers)
    if ($entries.Count -gt 1) {
        # -Provider all would open BOTH vendors' interactive sign-ins back to back. Say so before
        # the first browser window appears, so the operator can narrow with -Provider.
        Write-Host ''
        Write-Host ("NOTE: -Provider all will start {0} interactive sign-in flows in sequence." -f $entries.Count)
        Write-Host '      Use -Provider grok or -Provider gemini to sign in to one at a time.'
    }
    foreach ($entry in $entries) {
        if (-not $entry.command_found) {
            Write-Host ("{0}: cannot sign in - the CLI is not installed. Install it first." -f $entry.display)
            $script:ActionExit = $EXIT_PROVIDER_UNAVAILABLE
            continue
        }
        Write-Host ''
        Write-Host ("{0}: starting the provider's OWN authentication flow. This runner never reads," -f $entry.display)
        Write-Host '  copies, or stores the resulting credential - it stays in the provider CLI''s own store.'
        switch ($entry.provider) {
            'grok_build' {
                # `grok login` opens Grok's own browser flow (--oauth / --device-auth available).
                & $entry.executable login
                if ($LASTEXITCODE -ne 0) { $script:ActionExit = $EXIT_PROVIDER_UNAVAILABLE }
            }
            'google_antigravity' {
                # This CLI has no login subcommand: starting the TUI triggers Antigravity's own
                # Google browser sign-in (operator directive 5.2, quoted). Note honestly what that
                # means: for the duration of onboarding this is the full Antigravity agent, not a
                # supervised Sovereign node. It runs in the caller's working directory, so sign in
                # from outside a workspace you would not hand an agent.
                Write-Host '  Antigravity has no login subcommand: its TUI is starting. Complete the Google'
                Write-Host '  sign-in in the browser it opens, then exit the TUI to return here.'
                Write-Host '  This onboarding session is the vendor TUI itself - not a supervised node.'
                & $entry.executable
                if ($LASTEXITCODE -ne 0) { $script:ActionExit = $EXIT_PROVIDER_UNAVAILABLE }
            }
        }
    }
}

function Invoke-ProbeAction {
    param($RepoRootPath, $Python, $Selector, $ModelSlug, $PromptText)
    $extra = @()
    if (-not [string]::IsNullOrWhiteSpace($ModelSlug)) { $extra += @('--model', $ModelSlug) }
    if (-not [string]::IsNullOrWhiteSpace($PromptText)) { $extra += @('--prompt', $PromptText) }
    $result = Invoke-ReconEngine -RepoRootPath $RepoRootPath -Python $Python -EngineAction 'probe' `
        -ProviderSelector $Selector -Extra $extra
    foreach ($p in $result.Report.probes) {
        Write-Host ''
        Write-Host ("=== probe: {0}" -f $p.display)
        Write-Host ("  live gate  : {0} - {1}" -f $p.gate.allowed, $p.gate.reason)
        Write-Host ("  executed   : {0}" -f $p.executed)
        Write-Host ("  accepted   : {0}" -f $p.accepted)
        Write-Host ("  reason     : {0}" -f $p.reason)
        # The GOVERNED half. Operator directive section 17 requires the live receipt to confirm the
        # lease returned to zero; through 18C's first cut the engine measured all of this and the
        # runner printed none of it, so the header's "holds ONE I-X3 lease ... releases on every
        # exit path" was a promise the operator's own surface could not check (invariant 27).
        # Printed for every probe, including a refused one, where the absence of a lease IS the
        # fact worth seeing.
        # Property PRESENCE, not $null: this runs under Set-StrictMode -Version Latest, where
        # reading a property an object does not have is a terminating error. A refused probe
        # carries no `governed` key at all - which is precisely the shape this branch exists for,
        # so testing it with `$null -ne $p.governed` would throw on the only input that reaches it.
        if (Test-HasProperty $p 'governed') {
            $g = $p.governed
            $t = if (Test-HasProperty $g 'teardown') { $g.teardown } else { $null }
            $supervisedExec = if (Test-HasProperty $p 'supervised_execution') { $p.supervised_execution } else { 'unknown' }
            Write-Host ("  subscript. : {0} (allowance {1}, in use {2})" -f $g.subscription_ref, $g.allowance, $g.in_use)
            Write-Host ("  lease      : {0} [{1}]" -f $g.lease_id, $g.lease_key)
            Write-Host ("  supervised : execution={0} node_registered={1} pids={2}" -f `
                $supervisedExec, $g.node_registered, (($g.spawned_pids -join ',')))
            if ($null -ne $t) {
                Write-Host ("  teardown   : lease_released={0} governor_released={1} in_use_after={2} process_tree_clean={3} measured={4}" -f `
                    $t.lease_released, $t.governor_released, $t.in_use_after, $t.process_tree_clean, $t.measured)
            } else {
                Write-Host '  teardown   : (none recorded)'
            }
        } else {
            Write-Host '  governed   : no session was opened (refused before any lease was taken)'
        }
    }
    # Distinguish a governed refusal from a broken tool: the engine returns 3 for "refused or not
    # accepted" and anything else nonzero means the engine itself failed. Collapsing them would
    # let a crash read as a fail-closed denial (spec-audit F-16).
    if ($result.ExitCode -eq 3) {
        $script:ActionExit = $EXIT_PROBE_REFUSED
    } elseif ($result.ExitCode -ne 0) {
        Write-Failure ("provider engine failed with exit {0} (this is a tool failure, not a governed refusal)" -f $result.ExitCode)
        $script:ActionExit = $EXIT_ENVIRONMENT
    }
}

function Invoke-LaunchAction {
    param($RepoRootPath, $Python, $Selector, [bool]$SkipLaunch)
    $report = (Invoke-ReconEngine -RepoRootPath $RepoRootPath -Python $Python -EngineAction 'status' -ProviderSelector $Selector).Report
    foreach ($entry in $report.providers) { Write-ProviderStatus -Entry $entry }
    Write-CapabilityTable -Report $report

    # Report which providers this launch will not carry a hint for; an unavailable provider never
    # blocks the shell or the other provider (operator directive section 15). "Report", not
    # "refuse": the desktop shell runs its own gates and this runner has no authority over them
    # (spec-audit F-21 - a diagnostic must not claim an authority it does not hold).
    $available = @($report.providers | Where-Object { $_.state -eq 'AVAILABLE' })
    foreach ($entry in $report.providers) {
        if ($entry.state -ne 'AVAILABLE') {
            Write-Host ("NOT CARRIED into this launch: {0} is {1} ({2})" -f $entry.display, $entry.state, $entry.auth_detail)
        } elseif ($entry.state_caveat) {
            Write-Host ("CAVEAT: {0} - {1}" -f $entry.display, $entry.state_caveat)
        }
    }

    # Non-secret command-location hints only. These are PATHS, never credentials. The application's
    # own discovery remains authoritative - these merely mirror what this run resolved.
    foreach ($entry in $available) {
        switch ($entry.provider) {
            'grok_build'         { $env:SOVEREIGN_GROK_COMMAND = $entry.executable }
            'google_antigravity' { $env:SOVEREIGN_ANTIGRAVITY_COMMAND = $entry.executable }
        }
    }

    if ($SkipLaunch) {
        Write-Host ''
        Write-Host '-NoLaunch: status complete, desktop shell not started.'
        return
    }

    # The repository's EXISTING canonical desktop launcher (apps/desktop/RUN_ON_WINDOWS.md):
    # `npm start` in apps/desktop. No new launch command is invented here.
    $desktop = Join-Path $RepoRootPath 'apps\desktop'
    if (-not (Test-Path (Join-Path $desktop 'package.json'))) {
        Write-Failure "Canonical desktop launcher not found at $desktop"
        $script:ActionExit = $EXIT_ENVIRONMENT
        return
    }
    Write-Host ''
    Write-Host ("Starting the existing Sovereign desktop shell: npm start (in {0})" -f $desktop)
    Push-Location $desktop
    try {
        & npm start
        # section 15: pass the application's own exit code through, unaltered.
        $script:ActionExit = $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------------
$root = Resolve-RepoRoot -Candidate $RepoRoot
$python = Resolve-PythonCommand
if ($null -eq $python) {
    Write-Failure 'No usable Python 3 interpreter found (tried: py -3.12, py, python).'
    exit $EXIT_ENVIRONMENT
}

Write-Host ("Sovereign frontier provider runner - provider={0} action={1}" -f $Provider, $Action)
Write-Host ("repo root: {0}" -f $root)

switch ($Action) {
    'status' {
        Invoke-StatusAction -RepoRootPath $root -Python $python -Selector $Provider
    }
    'install' {
        Invoke-InstallAction -RepoRootPath $root -Python $python -Selector $Provider -Authorized ([bool]$InstallMissing)
    }
    'login' {
        Invoke-LoginAction -RepoRootPath $root -Python $python -Selector $Provider
    }
    'probe' {
        Invoke-ProbeAction -RepoRootPath $root -Python $python -Selector $Provider -ModelSlug $Model -PromptText $Prompt
    }
    'launch' {
        Invoke-LaunchAction -RepoRootPath $root -Python $python -Selector $Provider -SkipLaunch ([bool]$NoLaunch)
    }
}

exit $script:ActionExit
