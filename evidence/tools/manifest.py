"""
SWS-MANIFEST v1 — Manifest generator for protected-source integrity verification.

Usage: py -3.12 manifest.py <root> <output_file> [--exclude GLOB [--exclude GLOB ...]]

Generates a UTF-8 LF manifest of all files under <root> with SHA-256, size,
mtime in UTC nanoseconds, and relative path (forward slashes, NFC-normalized).
The generator's own SHA-256 is recorded in the manifest header.
"""
import sys
import os
import hashlib
import time
from pathlib import Path
from fnmatch import fnmatch
import unicodedata

MANIFEST_VERSION = "SWS-MANIFEST v1"


def sha256_file(path: str) -> str:
    """Return lowercase hex SHA-256 of file contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_self() -> str:
    """Return SHA-256 of this script file."""
    return sha256_file(__file__)


def mtime_utc_ns(path: str) -> int:
    """Return mtime as UTC nanoseconds since epoch."""
    stat = os.stat(path)
    return int(stat.st_mtime * 1_000_000_000)


def normalize_path(rel: str) -> str:
    """Normalize relative path: forward slashes, NFC."""
    rel = rel.replace("\\", "/")
    return unicodedata.normalize("NFC", rel)


def should_exclude(rel_path: str, patterns: list[str]) -> bool:
    """Check if rel_path matches any exclusion glob."""
    # Normalize for matching
    np = normalize_path(rel_path)
    parts = np.split("/")
    for pattern in patterns:
        # fnmatch against full path and each component
        if fnmatch(np, pattern):
            return True
        for part in parts:
            if fnmatch(part, pattern):
                return True
    return False


def generate_manifest(root: str, output_path: str, exclude_patterns: list[str]):
    """Walk root and write manifest to output_path."""
    root_path = Path(root).resolve()
    entries = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirpath_p = Path(dirpath)
        for fname in filenames:
            full = dirpath_p / fname
            try:
                rel = str(full.relative_to(root_path))
            except ValueError:
                continue
            if should_exclude(rel, exclude_patterns):
                continue
            try:
                file_hash = sha256_file(str(full))
                size = full.stat().st_size
                mtime = mtime_utc_ns(str(full))
            except (OSError, PermissionError) as e:
                print(f"WARNING: skipping {full}: {e}", file=sys.stderr)
                continue
            entries.append((normalize_path(rel), file_hash, size, mtime))

    # Sort lexicographically by normalized relative path
    entries.sort(key=lambda e: e[0])

    self_hash = sha256_self()

    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# {MANIFEST_VERSION}\n")
        f.write(f"# tool-sha256: {self_hash}\n")
        f.write(f"# root: {root_path.as_posix()}\n")
        if exclude_patterns:
            f.write(f"# excluded: {', '.join(exclude_patterns)}\n")
        else:
            f.write(f"# excluded: (none)\n")
        f.write(f"# entries: {len(entries)}\n")
        for rel, file_hash, size, mtime in entries:
            f.write(f"{file_hash}\t{size}\t{mtime}\t{rel}\n")

    print(f"Manifest written: {output_path}")
    print(f"  Entries: {len(entries)}")
    print(f"  Tool SHA-256: {self_hash}")


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <root> <output_file> [--exclude GLOB ...]")
        sys.exit(1)

    root = sys.argv[1]
    output_path = sys.argv[2]
    exclude_patterns = []
    i = 3
    while i < len(sys.argv):
        if sys.argv[i] == "--exclude" and i + 1 < len(sys.argv):
            exclude_patterns.append(sys.argv[i + 1])
            i += 2
        else:
            i += 1

    if not os.path.isdir(root):
        print(f"ERROR: root is not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    generate_manifest(root, output_path, exclude_patterns)


if __name__ == "__main__":
    main()