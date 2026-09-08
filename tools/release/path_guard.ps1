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
    return $full
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
