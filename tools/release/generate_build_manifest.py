#!/usr/bin/env python
"""Generate and verify shell/BUILD-MANIFEST.txt - the per-file hash census of shell/.

SWS-CORRECTIVE-01 workstream 2 (R2). Three separate defects met in this file:

1.  The manifest was produced by a TEST. `shell/tests/test_zz_evidence.py` rewrote it on
    every suite run, so routine verification mutated a tracked release input. Measured this
    run: `pytest shell/tests tools/release` left `shell/BUILD-MANIFEST.txt` modified in the
    working tree, with a fresh `# utc:` stamp and a different entry count.

2.  It enumerated the WORKING TREE, so anything sitting under `shell/` at generation time was
    baked into a tracked release input. The committed manifest carried five
    `shell/modules/*.json.pre-rebase` files - untracked build residue from
    `rebase_adapters.py`, `export-ignore`d by `.gitattributes` and shipped in nothing. The
    manifest described a developer's working directory rather than the candidate.

3.  Nothing regenerated the pin. `RELEASE-MANIFEST.json` records the manifest's content hash,
    and that pin was last written at `27bfc848`, when the manifest had 99 entries. Two later
    `chore(evidence)` commits committed the test's regenerated 102-entry output without
    re-running any release-identity step, and the gate has failed on committed bytes ever
    since.

The enumeration is now GIT-TRACKED FILES under `shell/`, which is the definitive answer to
"which files are the product": untracked residue cannot enter it, and a file that ships is by
definition tracked. `--check` is the gate; `--write` is the deliberate regeneration step;
`--out` writes a run-stamped copy somewhere untracked without touching the release input.

Run `--write` after any change under `shell/`, then re-pin with
`tools/release/sync_release_manifest.py --write`, and commit the two together.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HEADER_VERSION = "# SWS-BUILD-MANIFEST v1"
PRODUCER = "# producer: claude-code REM-01"
ROOT_LINE = "# root: shell/"
EXCLUDED_LINE = "# excluded: __pycache__/**, BUILD-MANIFEST.txt (self), untracked files"
SELF = "BUILD-MANIFEST.txt"

#: The `# utc:` line records WHEN, not WHAT. Every comparison drops it, exactly as
#: release_manifest_check.py does for the same file.
_STAMP = re.compile(r"^#\s*utc:\s*\S+\s*$", re.IGNORECASE)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tracked_shell_files(root: Path) -> list[str]:
    """Relative posix paths of the git-tracked files under shell/, excluding the manifest."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--", "shell/"],
        capture_output=True, text=True, check=True)
    out = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        rel = line[len("shell/"):]
        if rel == SELF:
            continue
        if "__pycache__/" in rel:
            continue
        out.append(rel)
    return sorted(out)


def render(root: Path, when: str) -> str:
    shell = root / "shell"
    entries = []
    missing = []
    for rel in tracked_shell_files(root):
        full = shell / rel
        if not full.is_file():
            # A tracked path that is not on disk is a broken checkout, not something to
            # quietly skip: the manifest would then describe a tree nobody has.
            missing.append(rel)
            continue
        entries.append((rel, sha256_file(full)))
    if missing:
        raise SystemExit(
            "generate_build_manifest: {} tracked file(s) under shell/ are missing from the "
            "working tree, the first being {}. Refusing to describe an incomplete tree."
            .format(len(missing), missing[0]))

    lines = [
        HEADER_VERSION,
        "# utc: {}".format(when),
        PRODUCER,
        ROOT_LINE,
        EXCLUDED_LINE,
        "# entries: {}".format(len(entries)),
    ]
    lines.extend("{}  {}".format(digest, rel) for rel, digest in entries)
    return "\n".join(lines) + "\n"


def content_only(text: str) -> str:
    return "".join(
        line + "\n" for line in text.splitlines() if not _STAMP.match(line))


def content_hash(text: str) -> str:
    return hashlib.sha256(content_only(text).encode("utf-8")).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true",
                       help="fail if the tracked manifest does not describe this tree")
    group.add_argument("--write", action="store_true",
                       help="regenerate the tracked manifest")
    parser.add_argument("--out", metavar="PATH",
                        help="write a run-stamped copy here instead of the tracked manifest")
    args = parser.parse_args(argv)

    root = repo_root()
    when = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    target = root / "shell" / SELF
    generated = render(root, when)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(generated, encoding="utf-8", newline="\n")
        print("generate_build_manifest: run record written to {}".format(out))
        if not args.check:
            return 0

    if args.write:
        target.write_text(generated, encoding="utf-8", newline="\n")
        print("generate_build_manifest: wrote {} ({} entries, content hash {})".format(
            target.relative_to(root).as_posix(),
            generated.count("\n") - 6, content_hash(generated)))
        print("  Now re-pin it: py -3.12 tools/release/sync_release_manifest.py --write")
        return 0

    # --check
    if not target.is_file():
        print("generate_build_manifest: FAIL - {} does not exist".format(target))
        return 1
    current = target.read_text(encoding="utf-8")
    if content_only(current) == content_only(generated):
        print("generate_build_manifest: PASS - {} describes {} tracked file(s) under shell/"
              .format(SELF, generated.count("\n") - 6))
        return 0

    have = {}
    for line in current.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        have[rel] = digest
    want = {}
    for line in generated.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        want[rel] = digest

    print("generate_build_manifest: FAIL - {} does not describe this tree".format(SELF))
    for rel in sorted(set(have) - set(want)):
        print("  ENUMERATED BUT NOT A TRACKED PRODUCT FILE: {}".format(rel))
    for rel in sorted(set(want) - set(have)):
        print("  TRACKED BUT NOT ENUMERATED: {}".format(rel))
    for rel in sorted(set(want) & set(have)):
        if have[rel] != want[rel]:
            print("  HASH CHANGED: {} ({} -> {})".format(rel, have[rel], want[rel]))
    print("  Regenerate with: py -3.12 tools/release/generate_build_manifest.py --write")
    print("  then re-pin with: py -3.12 tools/release/sync_release_manifest.py --write")
    return 1


if __name__ == "__main__":
    sys.exit(main())
