# SW-25: where SOVEREIGN's mutable state lives, for PowerShell callers.
#
# Dot-source this file. It mirrors sovereign_product/paths.py (resolve_state_home /
# resolve_runtime_dir) so launchers that run BEFORE the venv exists (Start-Shell.ps1 -CheckOnly,
# the clean-room gate) agree with the product about where state is. A parity test
# (test_sw25b_state_layout.py) runs both resolvers against the same inputs; change them together.
#
# Precedence:
#   state home  : SOVEREIGN_STATE_HOME -> STATE_LAYOUT.json "external" -> the install root
#   runtime dir : SOVEREIGN_STATE_DIR  -> <state home>\runtime
# The external default is <SOVEREIGN_WORKSPACE_STATE or %LOCALAPPDATA%\SovereignWorkspace>\sovereign.
# Trust checks (containment, UNC/device refusal) are enforced by the Python resolver, which every
# process that WRITES state goes through; this helper only locates.

function Get-SovereignStateLayout {
    param([Parameter(Mandatory = $true)][string]$Root)
    $layoutPath = Join-Path $Root 'STATE_LAYOUT.json'
    if (-not (Test-Path -LiteralPath $layoutPath -PathType Leaf)) { return 'install' }
    $doc = Get-Content -LiteralPath $layoutPath -Raw | ConvertFrom-Json
    $state = [string]$doc.state
    if ($state -ne 'external' -and $state -ne 'install') {
        throw "STATE_LAYOUT.json must declare state 'external' or 'install', got '$state'"
    }
    return $state
}

function Get-SovereignWorkspaceStateBase {
    $local = [string]$env:LOCALAPPDATA
    if (-not $local) { $local = Join-Path $HOME 'AppData\Local' }
    $configured = [string]$env:SOVEREIGN_WORKSPACE_STATE
    if ($configured.Trim()) {
        $configured = $configured.Trim()
        if ([IO.Path]::IsPathRooted($configured)) { return [IO.Path]::GetFullPath($configured) }
        return [IO.Path]::GetFullPath((Join-Path $local $configured))
    }
    return [IO.Path]::GetFullPath((Join-Path $local 'SovereignWorkspace'))
}

function Get-SovereignStateHome {
    param([Parameter(Mandatory = $true)][string]$Root)
    $rootPath = [IO.Path]::GetFullPath($Root)
    $configured = [string]$env:SOVEREIGN_STATE_HOME
    if ($configured.Trim()) {
        $configured = $configured.Trim()
        if ([IO.Path]::IsPathRooted($configured)) { return [IO.Path]::GetFullPath($configured) }
        return [IO.Path]::GetFullPath((Join-Path $rootPath $configured))
    }
    if ((Get-SovereignStateLayout -Root $rootPath) -eq 'external') {
        return (Join-Path (Get-SovereignWorkspaceStateBase) 'sovereign')
    }
    return $rootPath
}

function Get-SovereignRuntimeDir {
    param([Parameter(Mandatory = $true)][string]$Root)
    $rootPath = [IO.Path]::GetFullPath($Root)
    $configured = [string]$env:SOVEREIGN_STATE_DIR
    if ($configured.Trim()) {
        $configured = $configured.Trim()
        if ([IO.Path]::IsPathRooted($configured)) { return [IO.Path]::GetFullPath($configured) }
        return [IO.Path]::GetFullPath((Join-Path $rootPath $configured))
    }
    return (Join-Path (Get-SovereignStateHome -Root $rootPath) 'runtime')
}

function Resolve-SovereignRuntimeFile {
    # A runtime file to READ: the state-dir copy, or - before the first migration has run - the
    # legacy install-tree copy. Returns the preferred (state-dir) path when neither exists.
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$RelativePath
    )
    $preferred = Join-Path (Get-SovereignRuntimeDir -Root $Root) $RelativePath
    if (Test-Path -LiteralPath $preferred) { return $preferred }
    $legacy = Join-Path (Join-Path ([IO.Path]::GetFullPath($Root)) 'runtime') $RelativePath
    if (Test-Path -LiteralPath $legacy) { return $legacy }
    return $preferred
}
