# Shared canonical-path helpers for release/acceptance scripts.
# Resolve through reparse points via GetFinalPathNameByHandleW so a junction under
# temp cannot smuggle a path to operator data.

if (-not ('SovereignNativePath' -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

public static class SovereignNativePath {
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern SafeFileHandle CreateFileW(
        string lpFileName, uint dwDesiredAccess, uint dwShareMode,
        IntPtr lpSecurityAttributes, uint dwCreationDisposition,
        uint dwFlagsAndAttributes, IntPtr hTemplateFile);

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern uint GetFinalPathNameByHandleW(
        SafeFileHandle hFile, StringBuilder lpszFilePath, uint cchFilePath, uint dwFlags);

    public const uint GENERIC_READ = 0x80000000;
    public const uint FILE_SHARE_ALL = 0x00000007;
    public const uint OPEN_EXISTING = 3;
    public const uint FILE_FLAG_BACKUP_SEMANTICS = 0x02000000;
    public const uint VOLUME_NAME_DOS = 0;

    public static string GetFinalPath(string path) {
        if (string.IsNullOrEmpty(path)) {
            throw new ArgumentException("path is empty");
        }
        var handle = CreateFileW(
            path, GENERIC_READ, FILE_SHARE_ALL, IntPtr.Zero,
            OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, IntPtr.Zero);
        if (handle == null || handle.IsInvalid) {
            return Path.GetFullPath(path).TrimEnd('\\');
        }
        try {
            var sb = new StringBuilder(1024);
            uint n = GetFinalPathNameByHandleW(handle, sb, (uint)sb.Capacity, VOLUME_NAME_DOS);
            if (n == 0) {
                return Path.GetFullPath(path).TrimEnd('\\');
            }
            if (n > sb.Capacity) {
                sb.EnsureCapacity((int)n + 1);
                n = GetFinalPathNameByHandleW(handle, sb, (uint)sb.Capacity, VOLUME_NAME_DOS);
                if (n == 0) {
                    return Path.GetFullPath(path).TrimEnd('\\');
                }
            }
            string p = sb.ToString();
            if (p.StartsWith(@"\\?\UNC\", StringComparison.Ordinal)) {
                p = @"\\" + p.Substring(8);
            } else if (p.StartsWith(@"\\?\", StringComparison.Ordinal)) {
                p = p.Substring(4);
            }
            return Path.GetFullPath(p).TrimEnd('\\');
        } finally {
            handle.Dispose();
        }
    }
}
"@
}

function Test-UncOrDevicePath {
    param([string] $Path)
    if (-not $Path) { return $true }
    foreach ($pref in @('\\?\', '//?/', '\\.\', '//./')) {
        if ($Path.StartsWith($pref, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    $norm = $Path.Replace('/', '\')
    return $norm.StartsWith('\\', [StringComparison]::Ordinal)
}

function Get-CanonicalPath {
    param([string] $Path)
    if (Test-UncOrDevicePath $Path) {
        throw "UNC, device, or extended-length path is not allowed: $Path"
    }
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    if (Test-Path -LiteralPath $full) {
        return [SovereignNativePath]::GetFinalPath($full)
    }
    # R04: the target does not exist yet, so returning the LEXICAL full path would let a junction in
    # the existing prefix smuggle a not-yet-created child past containment (e.g. allowed\link\new,
    # where `link` is a junction into an outside tree, resolves lexically under `allowed`). Instead
    # canonicalize the NEAREST EXISTING ANCESTOR through GetFinalPath (which follows reparse points)
    # and re-append only the missing tail, so the child resolves under the junction's REAL target and
    # containment is decided honestly. Fail closed when no existing ancestor can be found.
    $tail = @()
    $probe = $full
    while ($true) {
        $parent = [IO.Path]::GetDirectoryName($probe)
        if ([string]::IsNullOrEmpty($parent) -or $parent -eq $probe) {
            throw "cannot canonicalize a path with no existing ancestor: $Path"
        }
        $tail = , ([IO.Path]::GetFileName($probe)) + $tail
        if (Test-Path -LiteralPath $parent) {
            $resolved = [SovereignNativePath]::GetFinalPath($parent)
            foreach ($seg in $tail) { $resolved = [IO.Path]::Combine($resolved, $seg) }
            return $resolved.TrimEnd('\')
        }
        $probe = $parent
    }
}

function Test-CanonicalContained {
    param([string] $Root, [string] $Candidate)
    $r = (Get-CanonicalPath $Root).TrimEnd('\')
    $c = (Get-CanonicalPath $Candidate).TrimEnd('\')
    if ($c.Equals($r, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    return $c.StartsWith($r + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Test-TreeContainsReparsePoint {
    param([string] $Root)
    if (-not (Test-Path -LiteralPath $Root)) { return $false }
    $item = Get-Item -LiteralPath $Root -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return $true }
    $found = @(Get-ChildItem -LiteralPath $Root -Force -Recurse -ErrorAction SilentlyContinue |
        Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 })
    return ($found.Count -gt 0)
}

function Test-SensitiveSystemPath {
    # True when $Candidate equals a well-known system/user location, or CONTAINS one (is an ancestor
    # of it) — the shapes that must never be recursively deleted. Being CONTAINED BY one (e.g. the
    # state root under %LOCALAPPDATA%) is normal and is NOT flagged. Canonical, junction-resolved.
    param([string] $Candidate)
    $canon = Get-CanonicalPath $Candidate
    if ($canon -eq [IO.Path]::GetPathRoot($canon)) { return $true }
    foreach ($name in @('USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'ProgramData', 'ProgramFiles',
            'ProgramW6432', 'SystemRoot', 'windir', 'PUBLIC')) {
        $val = [Environment]::GetEnvironmentVariable($name)
        if (-not $val) { continue }
        try { $sens = Get-CanonicalPath $val } catch { continue }
        if ($canon.Equals($sens, [StringComparison]::OrdinalIgnoreCase)) { return $true }
        # $canon is an ancestor of a sensitive dir ⇒ deleting it would take that dir with it.
        if (Test-CanonicalContained -Root $canon -Candidate $sens) { return $true }
    }
    return $false
}

function Assert-PurgeableStateRoot {
    # Fail-closed gate before any recursive delete of the operator's state root (F-040). The state
    # root arrives from the environment, so it is validated canonically here: never a filesystem
    # root, never a sensitive system/user location or an ancestor of one, never overlapping the
    # install, never a tree containing a reparse point, and it must be the product's own
    # 'SovereignWorkspace' directory. A custom-named location is refused rather than deleted; the
    # caller names it so the operator can remove it by hand. Returns the canonical path to delete.
    param([Parameter(Mandatory = $true)][string] $StateRoot, [string] $InstallRoot)
    $canon = Get-CanonicalPath $StateRoot   # throws on UNC/device/extended-length
    if ($canon -eq [IO.Path]::GetPathRoot($canon)) {
        throw "refusing to purge a filesystem root: $canon"
    }
    if ((Split-Path -Leaf $canon) -ne 'SovereignWorkspace') {
        throw ("refusing to purge $canon - it is not the product's own state directory " +
            "(expected a 'SovereignWorkspace' folder). Remove a custom state location by hand.")
    }
    if (Test-SensitiveSystemPath $canon) {
        throw "refusing to purge a sensitive system or user location: $canon"
    }
    if ($InstallRoot) {
        $install = Get-CanonicalPath $InstallRoot
        if ((Test-CanonicalContained -Root $canon -Candidate $install) -or
            (Test-CanonicalContained -Root $install -Candidate $canon)) {
            throw "refusing to purge a state root that overlaps the install root: $canon"
        }
    }
    if (Test-TreeContainsReparsePoint $canon) {
        throw "refusing to purge a state tree that contains a reparse point: $canon"
    }
    return $canon
}
