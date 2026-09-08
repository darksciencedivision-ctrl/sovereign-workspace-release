# Fixture process identity for acceptance. Parse --root; do not substring-match paths.

if (-not ('SovereignCommandLine' -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class SovereignCommandLine {
    [DllImport("shell32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern IntPtr CommandLineToArgvW(string lpCmdLine, out int pNumArgs);

    [DllImport("kernel32.dll")]
    private static extern IntPtr LocalFree(IntPtr hMem);

    public static string[] Split(string commandLine) {
        if (string.IsNullOrEmpty(commandLine)) {
            return new string[0];
        }
        int count;
        IntPtr ptr = CommandLineToArgvW(commandLine, out count);
        if (ptr == IntPtr.Zero) {
            throw new InvalidOperationException("CommandLineToArgvW failed");
        }
        try {
            string[] args = new string[count];
            for (int i = 0; i < count; i++) {
                IntPtr argPtr = Marshal.ReadIntPtr(ptr, i * IntPtr.Size);
                args[i] = Marshal.PtrToStringUni(argPtr) ?? "";
            }
            return args;
        }
        finally {
            LocalFree(ptr);
        }
    }
}
"@
}

function Convert-OwnershipPath {
    param([string] $Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $null }
    $p = $Path.Trim().Trim('"').Trim("'")
    $p = $p.Replace('/', '\')
    if ($p.StartsWith('\\?\UNC\', [StringComparison]::OrdinalIgnoreCase)) {
        $p = '\' + $p.Substring(7)
    } elseif ($p.StartsWith('\\?\', [StringComparison]::OrdinalIgnoreCase)) {
        $p = $p.Substring(4)
    }
    try {
        $p = [IO.Path]::GetFullPath($p)
    } catch {
        return $null
    }
    return $p.TrimEnd('\')
}

function Test-SameOwnershipPath {
    param([string] $Left, [string] $Right)
    $a = Convert-OwnershipPath $Left
    $b = Convert-OwnershipPath $Right
    if (-not $a -or -not $b) { return $false }
    return $a.Equals($b, [StringComparison]::OrdinalIgnoreCase)
}

function Get-ExpectedSovereignRoot {
    param([string] $InstallRoot)
    $install = Convert-OwnershipPath $InstallRoot
    if (-not $install) { return $null }
    return Convert-OwnershipPath (Join-Path $install 'modules\sovereign')
}

function Get-CommandLineNamedArgument {
    param(
        [string] $CommandLine,
        [Parameter(Mandatory = $true)][string] $Name
    )
    if ([string]::IsNullOrWhiteSpace($CommandLine)) { return $null }
    $flag = '--' + $Name.Trim().TrimStart('-')
    try {
        $argv = [SovereignCommandLine]::Split($CommandLine)
    } catch {
        return $null
    }
    $prefix = $flag + '='
    for ($i = 0; $i -lt $argv.Length; $i++) {
        $a = [string]$argv[$i]
        if ($a.Equals($flag, [StringComparison]::OrdinalIgnoreCase)) {
            if (($i + 1) -lt $argv.Length) { return [string]$argv[$i + 1] }
            return $null
        }
        if ($a.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -and
            $a.Length -gt $prefix.Length) {
            return $a.Substring($prefix.Length)
        }
    }
    return $null
}

function Test-CommandLineOwnsExpectedRoot {
    param([string] $CommandLine, [string] $ExpectedRoot)
    $parsed = Get-CommandLineNamedArgument -CommandLine $CommandLine -Name 'root'
    if (-not $parsed) { return $false }
    return Test-SameOwnershipPath $parsed $ExpectedRoot
}

function Test-ProcessDescendsFrom {
    param(
        [int] $ChildProcessId,
        [int] $AncestorProcessId
    )
    if ($ChildProcessId -le 0 -or $AncestorProcessId -le 0) { return $false }
    if ($ChildProcessId -eq $AncestorProcessId) { return $true }
    $visited = [System.Collections.Generic.HashSet[int]]::new()
    $current = $ChildProcessId
    for ($depth = 0; $depth -lt 32; $depth++) {
        if (-not $visited.Add($current)) { return $false }
        $record = Get-CimInstance Win32_Process -Filter "ProcessId=$current" -ErrorAction SilentlyContinue
        if ($null -eq $record) { return $false }
        $parent = [int]$record.ParentProcessId
        if ($parent -eq $AncestorProcessId) { return $true }
        if ($parent -le 0) { return $false }
        $current = $parent
    }
    return $false
}

function Get-ProcessRootEvidence {
    param(
        [int] $ProcessId,
        [int] $MaxDepth = 16
    )
    $visited = [System.Collections.Generic.HashSet[int]]::new()
    $current = $ProcessId
    for ($depth = 0; $depth -lt $MaxDepth; $depth++) {
        if ($current -le 0) { break }
        if (-not $visited.Add($current)) { break }
        $record = Get-CimInstance Win32_Process -Filter "ProcessId=$current" -ErrorAction SilentlyContinue
        if ($null -eq $record) { break }
        $parsed = Get-CommandLineNamedArgument -CommandLine ([string]$record.CommandLine) -Name 'root'
        if ($parsed) {
            return [pscustomobject]@{
                Pid         = $current
                Root        = $parsed
                CommandLine = [string]$record.CommandLine
                Executable  = [string]$record.ExecutablePath
                Self        = ($current -eq $ProcessId)
            }
        }
        $current = [int]$record.ParentProcessId
    }
    return $null
}

function New-OwnershipDiagnostic {
    param(
        [bool] $Owned,
        [string] $Reason,
        [int] $ProcessId,
        [string] $ExpectedRoot,
        [string] $ParsedRoot,
        [bool] $Descendant,
        [string] $CommandLine
    )
    $canon = if ($ParsedRoot) { Convert-OwnershipPath $ParsedRoot } else { '' }
    $lines = @(
        $(if ($Owned) { 'sovereign listener is the fixture install' } else { 'sovereign listener is not the fixture install' }),
        "  pid: $ProcessId",
        "  expected_root: $ExpectedRoot",
        "  parsed_root: $ParsedRoot",
        "  canonical_parsed_root: $canon",
        "  descendant_of_launcher: $Descendant",
        "  reason: $Reason"
    )
    if ($CommandLine) { $lines += "  command_line: $CommandLine" }
    return [pscustomobject]@{
        Owned       = $Owned
        Reason      = $Reason
        Pid         = $ProcessId
        ExpectedRoot = $ExpectedRoot
        ParsedRoot  = $ParsedRoot
        CanonicalRoot = $canon
        DescendantOfLauncher = $Descendant
        CommandLine = $CommandLine
        Diagnostic  = ($lines -join [Environment]::NewLine)
    }
}

function Resolve-FixtureListenerOwnership {
    param(
        [Parameter(Mandatory = $true)][int] $ListenerPid,
        [Parameter(Mandatory = $true)][string] $ExpectedRoot,
        [int] $LauncherPid,
        $LauncherCreated
    )
    $expected = Convert-OwnershipPath $ExpectedRoot
    $record = Get-CimInstance Win32_Process -Filter "ProcessId=$ListenerPid" -ErrorAction SilentlyContinue
    if ($null -eq $record) {
        return New-OwnershipDiagnostic -Owned $false -Reason 'missing-process' -ProcessId $ListenerPid `
            -ExpectedRoot $expected -ParsedRoot '' -Descendant $false -CommandLine ''
    }
    $cmd = [string]$record.CommandLine
    if ([string]::IsNullOrWhiteSpace($cmd)) {
        return New-OwnershipDiagnostic -Owned $false -Reason 'empty-command-line' -ProcessId $ListenerPid `
            -ExpectedRoot $expected -ParsedRoot '' -Descendant $false -CommandLine $cmd
    }
    $descendant = $false
    if ($LauncherPid -gt 0) {
        $descendant = Test-ProcessDescendsFrom -ChildProcessId $ListenerPid -AncestorProcessId $LauncherPid
        if ($descendant -and $LauncherCreated) {
            $childCreated = $record.CreationDate
            if ($childCreated -and ($childCreated -lt $LauncherCreated)) {
                $descendant = $false
            }
        }
    }
    $evidence = Get-ProcessRootEvidence -ProcessId $ListenerPid
    $parsed = if ($evidence) { [string]$evidence.Root } else { '' }
    if (-not $parsed) {
        return New-OwnershipDiagnostic -Owned $false -Reason 'missing-root-argument' -ProcessId $ListenerPid `
            -ExpectedRoot $expected -ParsedRoot '' -Descendant $descendant -CommandLine $cmd
    }
    if (-not (Test-SameOwnershipPath $parsed $expected)) {
        return New-OwnershipDiagnostic -Owned $false -Reason 'root-mismatch' -ProcessId $ListenerPid `
            -ExpectedRoot $expected -ParsedRoot $parsed -Descendant $descendant -CommandLine $cmd
    }
    $exe = [string]$record.ExecutablePath
    $exeUnder = $false
    if ($exe) {
        $exeCanon = Convert-OwnershipPath $exe
        $expPrefix = $expected + '\'
        $exeUnder = (Test-SameOwnershipPath $exeCanon $expected) -or
            ($exeCanon -and $exeCanon.StartsWith($expPrefix, [StringComparison]::OrdinalIgnoreCase))
    }
    if ($LauncherPid -gt 0) {
        if (-not $descendant) {
            return New-OwnershipDiagnostic -Owned $false -Reason 'not-descendant-of-launcher' -ProcessId $ListenerPid `
                -ExpectedRoot $expected -ParsedRoot $parsed -Descendant $false -CommandLine $cmd
        }
    } else {
        if (-not $evidence.Self -and -not $exeUnder) {
            return New-OwnershipDiagnostic -Owned $false -Reason 'root-only-on-unrelated-ancestor' -ProcessId $ListenerPid `
                -ExpectedRoot $expected -ParsedRoot $parsed -Descendant $false -CommandLine $cmd
        }
    }
    $reason = if ($evidence.Self) { 'root-and-ancestry' } else { 'ancestor-root-venv-descendant' }
    return New-OwnershipDiagnostic -Owned $true -Reason $reason -ProcessId $ListenerPid `
        -ExpectedRoot $expected -ParsedRoot $parsed -Descendant $descendant -CommandLine $cmd
}

function New-OwnedProcessTracker {
    return New-Object System.Collections.Generic.List[object]
}

function Add-OwnedProcessInstance {
    param(
        $Tracker,
        [int] $ProcessId
    )
    if ($null -eq $Tracker -or $ProcessId -le 0) { return }
    $record = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $record) { return }
    foreach ($existing in $Tracker) {
        if ([int]$existing.Pid -eq $ProcessId -and $existing.Created -eq $record.CreationDate) {
            return
        }
    }
    $Tracker.Add([pscustomobject]@{
        Pid     = [int]$record.ProcessId
        Created = $record.CreationDate
        Name    = [string]$record.Name
    })
}

function Test-SameProcessInstance {
    param(
        [int] $ProcessId,
        $Created
    )
    if ($ProcessId -le 0) { return $false }
    $live = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $live) { return $false }
    if ($null -eq $Created) { return $true }
    return ($live.CreationDate -eq $Created)
}

function Get-DescendantProcessRecords {
    param([int[]] $RootPids)
    $seen = [System.Collections.Generic.HashSet[int]]::new()
    $queue = [System.Collections.Generic.Queue[int]]::new()
    $out = New-Object System.Collections.Generic.List[object]
    foreach ($root in @($RootPids)) {
        if ($root -gt 0) { $queue.Enqueue([int]$root) }
    }
    while ($queue.Count -gt 0) {
        $id = $queue.Dequeue()
        if (-not $seen.Add($id)) { continue }
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
        if ($null -ne $proc) { $out.Add($proc) }
        $kids = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$id" -ErrorAction SilentlyContinue)
        foreach ($kid in $kids) {
            if ($null -ne $kid) { $queue.Enqueue([int]$kid.ProcessId) }
        }
    }
    return $out
}

function Stop-OwnedProcessTree {
    param(
        $Tracker,
        [int] $LauncherPid,
        $LauncherCreated
    )
    $ErrorActionPreference = 'Continue'
    $roots = New-Object System.Collections.Generic.List[int]
    if ($LauncherPid -gt 0) { $roots.Add($LauncherPid) }
    if ($Tracker) {
        foreach ($item in $Tracker) {
            $ownedId = [int]$item.Pid
            if ($ownedId -gt 0) { $roots.Add($ownedId) }
        }
    }
    $created = @{}
    if ($LauncherPid -gt 0 -and $LauncherCreated) {
        $created[$LauncherPid] = $LauncherCreated
    }
    if ($Tracker) {
        foreach ($item in $Tracker) {
            $created[[int]$item.Pid] = $item.Created
        }
    }
    $records = @(Get-DescendantProcessRecords -RootPids $roots.ToArray())
    foreach ($rec in $records) {
        $created[[int]$rec.ProcessId] = $rec.CreationDate
    }

    $taskkill = Join-Path $env:SystemRoot 'System32\taskkill.exe'
    if ($LauncherPid -gt 0 -and (Test-SameProcessInstance -ProcessId $LauncherPid -Created $LauncherCreated)) {
        & $taskkill /PID ([string]$LauncherPid) /T /F 2>$null | Out-Null
    }

    foreach ($ownedId in @($created.Keys)) {
        if (Test-SameProcessInstance -ProcessId ([int]$ownedId) -Created $created[$ownedId]) {
            try { Stop-Process -Id ([int]$ownedId) -Force -ErrorAction SilentlyContinue } catch { }
        }
    }

    Start-Sleep -Milliseconds 200
    $remain = @(Get-DescendantProcessRecords -RootPids $roots.ToArray())
    foreach ($rec in $remain) {
        $ownedId = [int]$rec.ProcessId
        $expect = $created[$ownedId]
        if ($null -eq $expect -or $rec.CreationDate -eq $expect) {
            try { Stop-Process -Id $ownedId -Force -ErrorAction SilentlyContinue } catch { }
        }
    }
}
