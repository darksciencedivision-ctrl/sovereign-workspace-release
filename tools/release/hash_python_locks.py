#!/usr/bin/env python
"""F-071: pin the BYTES of every Python lock, not only the names and versions.

`==` pins guarantee a distribution NAME and VERSION. They do not guarantee bytes: a wheel newly
uploaded for an existing version (a better platform tag), or a mirror/proxy substitution, is
accepted silently. `pip install --require-hashes` refuses any file whose sha256 is not pinned in
the lock, and `tools/release/install.ps1` refuses a lock that carries no hashes at all. This tool
is how the hashes get into the locks, and how CI proves they are still there.

  --write          For every `name==version` pin, read the file list PyPI publishes for exactly
                   that release and record the sha256 of each wheel installable on the supported
                   platform (Windows x64: `win_amd64` or `any`). The installer passes
                   `--only-binary=:all:`, so an sdist is never a candidate and is not pinned.
                   Versions are never changed. Refuses a pin with no wheel the lock's target
                   interpreter can install, because the installer would refuse it too.
  --check          Offline and a pure function of tracked bytes. Every requirement is an exact
                   `==` pin carrying at least one well-formed sha256; no duplicates; the only
                   option allowed is `-r` naming another lock this tool also checks; the file is
                   in the canonical form --write produces.
  --verify-index   Online. Recompute the hash sets from PyPI and require equality.

Stdlib-only. Locks are enumerated explicitly below, never by glob.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_JSON = "https://pypi.org/pypi/{name}/{version}/json"
SUPPORTED_PLATFORMS = frozenset({"win_amd64", "any"})

#: (lock, the interpreter install.ps1 / the CI lane installs it into).
LOCKS: tuple[tuple[str, tuple[int, int]], ...] = (
    ("modules/sovereign/WORKSPACE-RESOLVED-LOCK.txt", (3, 12)),
    ("modules/debate/requirements.lock.txt", (3, 14)),
    ("modules/sow/requirements.txt", (3, 12)),
    ("modules/sow/requirements-dev.txt", (3, 12)),
)

_REQ = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9.+!_-]+)$")
_HASH = re.compile(r"^--hash=sha256:([0-9a-f]{64})$")
_INCLUDE = re.compile(r"^-r\s+(\S+)$")


@dataclass
class Requirement:
    name: str
    version: str
    hashes: list[str] = field(default_factory=list)


@dataclass
class Lock:
    # Each entry is a Requirement, or a str holding a verbatim comment / blank / -r line.
    entries: list = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def requirements(self) -> list[Requirement]:
        return [e for e in self.entries if isinstance(e, Requirement)]

    @property
    def includes(self) -> list[str]:
        out = []
        for e in self.entries:
            if isinstance(e, str):
                m = _INCLUDE.match(e.strip())
                if m:
                    out.append(m.group(1))
        return out


def canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def parse(text: str) -> Lock:
    lock = Lock()
    pending: list[str] = []
    physical = text.splitlines()
    for number, raw in enumerate(physical, start=1):
        line = raw.rstrip()
        stripped = line.strip()
        if not pending and (not stripped or stripped.startswith("#")):
            lock.entries.append(stripped if not stripped else line)
            continue
        if stripped.endswith("\\"):
            pending.append(stripped[:-1].strip())
            if number != len(physical):
                continue
        else:
            pending.append(stripped)
        logical = " ".join(p for p in pending if p)
        pending = []
        if logical.startswith("-"):
            if not _INCLUDE.match(logical):
                lock.problems.append(
                    f"line {number}: option {logical!r} is not allowed; the only option a hashed "
                    "lock may carry is '-r <another checked lock>'")
            lock.entries.append(logical)
            continue
        tokens = logical.split()
        match = _REQ.match(tokens[0])
        if not match:
            lock.problems.append(f"line {number}: not an exact name==version pin: {tokens[0]!r}")
            continue
        req = Requirement(match.group(1), match.group(2))
        for token in tokens[1:]:
            hashed = _HASH.match(token)
            if not hashed:
                lock.problems.append(
                    f"line {number}: {req.name}: malformed or unsupported token {token!r} "
                    "(expected --hash=sha256:<64 lowercase hex>)")
                continue
            req.hashes.append(hashed.group(1))
        lock.entries.append(req)
    return lock


def render(lock: Lock) -> str:
    lines: list[str] = []
    for entry in lock.entries:
        if isinstance(entry, str):
            lines.append(entry)
            continue
        head = f"{entry.name}=={entry.version}"
        hashes = sorted(set(entry.hashes))
        if not hashes:
            lines.append(head)
            continue
        lines.append(head + " \\")
        for index, digest in enumerate(hashes):
            tail = " \\" if index < len(hashes) - 1 else ""
            lines.append(f"    --hash=sha256:{digest}{tail}")
    return "\n".join(lines) + "\n"


def wheel_tags(filename: str):
    if not filename.endswith(".whl"):
        return None
    parts = filename[:-4].split("-")
    if len(parts) not in (5, 6):
        return None
    py, abi, plat = parts[-3], parts[-2], parts[-1]
    return set(py.split(".")), set(abi.split(".")), set(plat.split("."))


def on_supported_platform(filename: str) -> bool:
    tags = wheel_tags(filename)
    return bool(tags and tags[2] & SUPPORTED_PLATFORMS)


def installable_by(filename: str, target: tuple[int, int]) -> bool:
    """A conservative subset of pip's tag rules for CPython X.Y on Windows x64."""
    tags = wheel_tags(filename)
    if not tags or not tags[2] & SUPPORTED_PLATFORMS:
        return False
    py, abi, _ = tags
    major, minor = target
    cp = f"cp{major}{minor}"
    if "none" in abi and py & {f"py{major}", f"py{major}{minor}", cp}:
        return True
    if cp in abi and cp in py:
        return True
    if "abi3" in abi:
        for tag in py:
            m = re.fullmatch(rf"cp{major}(\d+)", tag)
            if m and int(m.group(1)) <= minor:
                return True
    return False


def fetch_release_files(name: str, version: str) -> list[dict]:
    url = INDEX_JSON.format(name=name, version=version)
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https host
        document = json.loads(response.read().decode("utf-8"))
    return list(document.get("urls") or [])


def index_hashes(req: Requirement, target: tuple[int, int],
                 fetch: Callable[[str, str], list[dict]]) -> tuple[list[str], list[str]]:
    """(sorted sha256 set for supported-platform wheels, problems)."""
    try:
        files = fetch(req.name, req.version)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return [], [f"{req.name}=={req.version}: index lookup failed: {exc}"]
    wheels = [f for f in files
              if f.get("packagetype") == "bdist_wheel" and on_supported_platform(f.get("filename", ""))]
    problems = []
    if not any(installable_by(f["filename"], target) for f in wheels):
        problems.append(
            f"{req.name}=={req.version}: PyPI publishes no wheel installable by CPython "
            f"{target[0]}.{target[1]} on win_amd64; install.ps1 passes --only-binary=:all: and "
            "would refuse it")
    digests = sorted({str(f.get("digests", {}).get("sha256", "")).lower() for f in wheels})
    digests = [d for d in digests if re.fullmatch(r"[0-9a-f]{64}", d)]
    if wheels and len(digests) != len({f["filename"] for f in wheels}):
        problems.append(f"{req.name}=={req.version}: a wheel on the index carries no sha256 digest")
    return digests, problems


def check_lock(root: Path, rel: str, checked: set[str]) -> list[str]:
    path = root / rel
    if not path.is_file():
        return [f"{rel}: missing"]
    text = read_text(path)
    lock = parse(text)
    problems = [f"{rel}: {p}" for p in lock.problems]
    if not lock.requirements and not lock.includes:
        problems.append(f"{rel}: declares nothing")
    seen: dict[str, str] = {}
    for req in lock.requirements:
        key = canonical_name(req.name)
        if key in seen:
            problems.append(f"{rel}: duplicate pin for {key} ({seen[key]} and {req.version})")
        seen[key] = req.version
        if not req.hashes:
            problems.append(f"{rel}: {req.name}=={req.version} carries no --hash (F-071)")
    for include in lock.includes:
        target = (path.parent / include).resolve()
        try:
            include_rel = target.relative_to(root.resolve()).as_posix()
        except ValueError:
            include_rel = str(target)
        if include_rel not in checked:
            problems.append(f"{rel}: -r {include} names a file this gate does not check")
    if path.read_bytes() != render(lock).encode("utf-8"):
        problems.append(f"{rel}: not in canonical hashed form (UTF-8, LF, sorted hashes); "
                        "run hash_python_locks.py --write")
    return problems


def write_lock(root: Path, rel: str, target: tuple[int, int],
               fetch: Callable[[str, str], list[dict]]) -> list[str]:
    path = root / rel
    lock = parse(read_text(path))
    problems = [f"{rel}: {p}" for p in lock.problems]
    if problems:
        return problems
    for req in lock.requirements:
        digests, found = index_hashes(req, target, fetch)
        problems.extend(f"{rel}: {p}" for p in found)
        if digests:
            req.hashes = digests
    if problems:
        return problems
    rendered = render(lock).encode("utf-8")
    if path.read_bytes() != rendered:
        path.write_bytes(rendered)
        print(f"hash_python_locks: wrote {rel} ({len(lock.requirements)} pins)")
    else:
        print(f"hash_python_locks: {rel} unchanged ({len(lock.requirements)} pins)")
    return []


def verify_lock(root: Path, rel: str, target: tuple[int, int],
                fetch: Callable[[str, str], list[dict]]) -> list[str]:
    lock = parse(read_text(root / rel))
    problems = []
    for req in lock.requirements:
        digests, found = index_hashes(req, target, fetch)
        problems.extend(f"{rel}: {p}" for p in found)
        if digests and sorted(set(req.hashes)) != digests:
            problems.append(f"{rel}: {req.name}=={req.version} pinned hashes differ from the index")
    return problems


def main(argv=None, fetch: Callable[[str, str], list[dict]] = fetch_release_files) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--verify-index", action="store_true")
    parser.add_argument("--root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    root = Path(args.root)
    checked = {rel for rel, _ in LOCKS}
    problems: list[str] = []
    for rel, target in LOCKS:
        if args.write:
            problems.extend(write_lock(root, rel, target, fetch))
        elif args.verify_index:
            problems.extend(verify_lock(root, rel, target, fetch))
        else:
            problems.extend(check_lock(root, rel, checked))
    if problems:
        print("hash_python_locks: FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    verb = "written" if args.write else "match the index" if args.verify_index else "hashed and canonical"
    print(f"hash_python_locks: PASS - {len(LOCKS)} lock(s) {verb}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
