#!/usr/bin/env python3
"""Content digest of a release archive, ignoring its provenance stamp.

EPC-01 P2-7. Punch List V7 recorded the six per-module archives as "byte-identical in content
across two seals but carrying different sha256", and called them not reproducible. Measured
precisely, that framing was half right and the diagnosis was wrong.

`git archive` stamps every archive with the commit it was cut from — a pax global header
`comment=<sha>` in tar, the archive comment in zip. The difference between two archives of
IDENTICAL content cut at different commits is exactly that stamp and nothing else: for a tar,
every byte after the first 1024 matches; for a zip, every entry name and every entry body
matches. `--mtime` does not help, because time was never the variable.

That stamp is not a defect. It is provenance, and a release archive that could not say which
commit produced it would be worse. What was missing is a way to ask the other question —
"is this the same CONTENT as that?" — so a consumer diffing hashes between releases saw all
eight artifacts change when only two had actually changed.

This tool answers that question. The digest covers every entry name and every entry body, in
sorted order, and nothing else: no timestamps, no compression metadata, no commit stamp. Two
archives of the same files produce the same digest whatever commit cut them.

    py -3.12 tools/release/archive_content_hash.py <archive> [<archive> ...]
    py -3.12 tools/release/archive_content_hash.py --compare a.zip b.zip

Exit codes: 0 ok (and for --compare, contents match), 1 contents differ, 2 usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import sys
import tarfile
import zipfile
from pathlib import Path


def _digest_zip(path: Path) -> str:
    h = hashlib.sha256()
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            h.update(name.encode("utf-8"))
            h.update(b"\0")
            info = archive.getinfo(name)
            if info.is_dir():
                h.update(b"<dir>")
            else:
                h.update(archive.read(name))
            h.update(b"\0")
    return h.hexdigest()


def _digest_tar(path: Path) -> str:
    h = hashlib.sha256()
    with tarfile.open(path) as archive:
        members = sorted(archive.getmembers(), key=lambda m: m.name)
        for member in members:
            # The pax global header IS the provenance stamp. Skip it by type, not by name.
            if member.type == tarfile.XGLTYPE:
                continue
            h.update(member.name.encode("utf-8"))
            h.update(b"\0")
            if member.isfile():
                stream = archive.extractfile(member)
                if stream is not None:
                    for chunk in iter(lambda: stream.read(65536), b""):
                        h.update(chunk)
            else:
                h.update(b"<nonfile>")
            h.update(b"\0")
    return h.hexdigest()


def content_digest(path: Path) -> str:
    """SHA-256 over entry names and bodies only. Provenance and timestamps excluded."""
    if zipfile.is_zipfile(path):
        return _digest_zip(path)
    if tarfile.is_tarfile(path):
        return _digest_tar(path)
    raise ValueError(f"not a zip or tar archive: {path}")


def provenance(path: Path) -> str | None:
    """The commit `git archive` stamped into the archive, if it carries one."""
    try:
        if zipfile.is_zipfile(path):
            comment = zipfile.ZipFile(path).comment
            return comment.decode("utf-8", "replace") or None
        if tarfile.is_tarfile(path):
            with tarfile.open(path) as archive:
                return archive.pax_headers.get("comment")
    except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError):
        return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--compare", action="store_true",
                        help="compare exactly two archives by content and report whether the "
                             "difference is only the provenance stamp")
    args = parser.parse_args()

    for path in args.archives:
        if not path.is_file():
            print(f"archive_content_hash: no such file: {path}", file=sys.stderr)
            return 2

    if args.compare:
        if len(args.archives) != 2:
            print("archive_content_hash: --compare takes exactly two archives", file=sys.stderr)
            return 2
        left, right = args.archives
        left_digest, right_digest = content_digest(left), content_digest(right)
        left_whole = hashlib.sha256(left.read_bytes()).hexdigest()
        right_whole = hashlib.sha256(right.read_bytes()).hexdigest()
        print(f"  {left.name}")
        print(f"    whole-file {left_whole}")
        print(f"    content    {left_digest}")
        print(f"    cut from   {provenance(left) or '(no stamp)'}")
        print(f"  {right.name}")
        print(f"    whole-file {right_whole}")
        print(f"    content    {right_digest}")
        print(f"    cut from   {provenance(right) or '(no stamp)'}")
        print()
        if left_digest == right_digest:
            if left_whole == right_whole:
                print("IDENTICAL: same content, same bytes")
            else:
                print("SAME CONTENT: the archives differ only in the commit they were cut from")
            return 0
        print("DIFFERENT CONTENT: these archives do not hold the same files")
        return 1

    for path in args.archives:
        print(f"{content_digest(path)}  {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
