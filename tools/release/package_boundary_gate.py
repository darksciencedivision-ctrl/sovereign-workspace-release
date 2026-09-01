#!/usr/bin/env python
"""Package boundary gate — SWS-REM-DIR-20260828 R2, item B1-1 (C-1 closure).

Allow-list-oriented packaging scan. FAILS (exit 1) when user/runtime state,
databases, env files, logs, caches, or credential patterns are present in the
scanned tree outside quarantined-historical lanes.

Design rules (per Punch List v2.1 C-1 and directive R2 §4 Batch 1):

* Rejected classes: ``*.db``/``*.sqlite*`` databases, ``.env*`` env files,
  key material extensions, ``*.log`` logs, runtime/session-state directories
  (node_modules, venvs, __pycache__, .approvals, .recovery, the sovereign
  ``runtime`` lane), cache/junk files, and high-confidence credential
  content patterns.
* The ``evidence/`` lane and the ``dev/`` staging lane are treated as
  QUARANTINED-HISTORICAL: their contents are counted and listed but never
  fail the scan. Both are ``export-ignore``d, so NO quarantine lane covers a
  byte that ships - see ``NoLaneCoversShippedBytes`` in the tests, which
  holds that property rather than leaving it to be re-derived.

  The Distillery ``modules/distillery/runs/`` lane was removed with the
  ``runs`` component rule that created the need for it (SYSTEM-REVIEW
  2026-08-31, F-2).
* Declared-fixture allow-list is VALUE-BASED: an entry matches only on an
  exact relative path AND exact SHA-256 of the file content. Glob/wildcard
  characters in allow-list paths are rejected with a configuration error.
  Nothing is allow-listed by pattern.

Exit codes: 0 = pass, 1 = violations found, 2 = configuration/usage error.

This gate is CANDIDATE release tooling authored under directive
SWS-REM-DIR-20260828 R2; it asserts no gate PASS by itself.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Rejection rules
# ---------------------------------------------------------------------------

# File-name suffix rules (case-insensitive).
SUFFIX_RULES = [
    ("database", (".db", ".db-shm", ".db-wal", ".sqlite", ".sqlite3",
                  ".sqlite-wal", ".sqlite-shm")),
    ("env-file", (".pem", ".key", ".p12", ".pfx", ".keystore")),
    ("log", (".log",)),
    ("cache-junk", (".cache", ".tmp", ".bak")),
]

# Exact base-name rules (case-insensitive).
BASENAME_RULES = [
    ("env-file", {".env"}),
    ("cache-junk", {"thumbs.db", "desktop.ini", ".ds_store"}),
    ("local-settings", {"settings.local.json"}),
    ("runtime-operation-state", {"live_operation.json"}),
]

# Path-component (directory-name) rules: any file whose relative path
# contains one of these components is rejected.
COMPONENT_RULES = {
    "runtime-session-state": {
        "node_modules", ".venv", "venv", "env", ".eggs",
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        ".cache", ".approvals", ".recovery", ".runtime",
        # `runs` was here and is deliberately gone (SYSTEM-REVIEW 2026-08-31, F-2).
        #
        # Every other member of this set is a directory a TOOL creates and nobody
        # curates - a virtualenv, a package cache, a bytecode cache. `runs` is not:
        # it is a name a project may choose for material it maintains on purpose.
        #
        # Measured on this tree: `modules/distillery/runs/` was the ONLY tracked
        # path with a `runs` component, all 80 files of it, and it is the
        # Distillery's curated release-gate evidence - cited by four shipped tests
        # (test_cold_restore_record, test_gate_status_chain, test_live_g0) and by
        # the shipped tools/build_completion_manifest.py. The module already
        # separates its volatile run output at the right layer: its own .gitignore
        # excludes runs/G0-live/*.jsonl and runs/G0-live/private/.
        #
        # So this entry matched 79 shipped files, every one of them a false
        # positive, and a quarantine lane existed solely to suppress them - which
        # made the gate print `violations: 0` while 79 shipped files had matched a
        # violation rule. The lane went with the rule: a name-based rule that
        # needs a standing exemption to be usable is the wrong rule, and removing
        # the exemption without removing the rule would have turned the lane red
        # over no defect.
    },
}

# The sovereign runtime lane is runtime state by definition: ANY file below
# modules/sovereign/runtime/ is rejected (the frozen ZIP preserves history).
RUNTIME_LANES = [
    ("runtime-session-state", "modules/sovereign/runtime"),
]

# Env-file family: basename == '.env' or starts with '.env.'
def _is_env_name(name: str) -> bool:
    low = name.lower()
    return low == ".env" or low.startswith(".env.")


# High-confidence credential content patterns (value-based detection).
CREDENTIAL_PATTERNS = [
    ("aws-access-key-id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("openai-style-key", re.compile(r"\bsk-[A-Za-z0-9]{24,}\b")),
]

CONTENT_SCAN_MAX_BYTES = 1_000_000  # only content-scan files up to 1 MB

TEXT_SCAN_SUFFIXES = {
    ".txt", ".md", ".json", ".jsonl", ".py", ".js", ".ts", ".jsx", ".tsx",
    ".toml", ".cfg", ".ini", ".yaml", ".yml", ".xml", ".html", ".css",
    ".sh", ".ps1", ".bat", ".cmd", ".env",
}

# Directories never scanned at all.
SKIP_DIRS = {".git"}

# Default quarantined-historical lanes (relative POSIX prefixes).
# evidence/  — frozen historical evidence captures (cp01, cpm1, gate4b, ...)
# dev/       — director-accepted v1.2.1-hardening release staging history
#
# BOTH are `export-ignore`d in .gitattributes (X-4, OD-35), so neither ships. That
# is the property worth keeping: a quarantine lane may cover bytes a recipient
# never receives, and may not cover bytes that ship. A lane over shipped bytes
# turns "violations: 0" into a statement about the lane rather than about the
# distribution. `modules/distillery/runs/` was such a lane and was removed with
# the `runs` component rule above (SYSTEM-REVIEW 2026-08-31, F-2).
DEFAULT_QUARANTINE_LANES = ("evidence/", "dev/")


def _posix(rel: str) -> str:
    return rel.replace(os.sep, "/")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_allowlist(path: str | None) -> dict:
    """Load and validate the declared-fixture allow-list.

    Value-based contract: every entry must carry an exact relative ``path``
    (no glob characters) and an exact content ``sha256``. Anything else is a
    configuration error (exit 2), never a silent pass.
    """
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as exc:
        raise AllowlistError(f"cannot read allow-list {path}: {exc}") from exc
    entries = doc.get("entries", [])
    if not isinstance(entries, list):
        raise AllowlistError("allow-list 'entries' must be a list")
    table: dict[str, dict] = {}
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise AllowlistError(f"entry #{i} is not an object")
        rel = entry.get("path")
        digest = entry.get("sha256")
        if not isinstance(rel, str) or not rel:
            raise AllowlistError(f"entry #{i} missing exact 'path'")
        if any(ch in rel for ch in ("*", "?", "[")):
            raise AllowlistError(
                f"entry #{i} path {rel!r} contains glob/wildcard characters; "
                "the allow-list is value-based (exact path + sha256), never pattern-based")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise AllowlistError(
                f"entry #{i} must carry an exact 64-hex lowercase sha256")
        rel = _posix(rel)
        table[rel] = {"sha256": digest, "reason": entry.get("reason", "")}
    return table


class AllowlistError(Exception):
    pass


def classify(rel_posix: str, basename: str, components: set) -> tuple | None:
    """Return (class, rule) when the path violates the boundary, else None."""
    low = basename.lower()

    for lane_class, lane_prefix in RUNTIME_LANES:
        if rel_posix == lane_prefix or rel_posix.startswith(lane_prefix + "/"):
            return (lane_class, f"runtime lane {lane_prefix}/")

    for comp_class, names in COMPONENT_RULES.items():
        hit = components & names
        if hit:
            return (comp_class, f"path component {sorted(hit)[0]}/")

    # Exact base names take precedence over suffixes (Thumbs.db is
    # cache-junk, not a database).
    for cls, names in BASENAME_RULES:
        if low in names:
            return (cls, f"basename {basename}")

    for cls, suffixes in SUFFIX_RULES:
        if low.endswith(suffixes):
            return (cls, "suffix " + [s for s in suffixes if low.endswith(s)][0])

    if _is_env_name(basename):
        return ("env-file", ".env* family")

    return None


def scan_content(path: str, basename: str) -> list:
    """Content-scan small text files for high-confidence credential values."""
    suffix = os.path.splitext(basename)[1].lower()
    is_env = _is_env_name(basename)
    if not is_env and suffix not in TEXT_SCAN_SUFFIXES:
        return []
    try:
        if os.path.getsize(path) > CONTENT_SCAN_MAX_BYTES:
            return []
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return []
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        return []
    hits = []
    for name, rx in CREDENTIAL_PATTERNS:
        m = rx.search(text)
        if m:
            hits.append((name, f"pattern {name}"))
    return hits


def scan_tree(root: str, quarantine_lanes: tuple, allowlist: dict,
              allowlist_source_path: str | None = None) -> dict:
    violations = []
    quarantined = []
    allowlisted = []
    content_hits = []
    files_scanned = 0

    root_abs = os.path.abspath(root)
    allowlist_abs = (os.path.abspath(allowlist_source_path)
                     if allowlist_source_path else None)
    for dirpath, dirnames, filenames in os.walk(root_abs):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = _posix(os.path.relpath(full, root_abs))
            files_scanned += 1

            # Quarantined-historical lanes: recorded, never failed.
            if any(rel == lane.rstrip("/") or rel.startswith(lane)
                   for lane in quarantine_lanes):
                cls = classify(rel, fn, set(rel.split("/")[:-1]))
                quarantined.append({"path": rel,
                                    "class": cls[0] if cls else "in-lane"})
                continue

            cls = classify(rel, fn, set(rel.split("/")[:-1]))

            # Value-based allow-list: exact path AND exact content hash.
            if rel in allowlist:
                expected = allowlist[rel]
                actual = sha256_file(full)
                if actual == expected["sha256"]:
                    allowlisted.append({
                        "path": rel,
                        "class": cls[0] if cls else "declared-fixture",
                        "reason": expected["reason"],
                    })
                    continue
                violations.append({
                    "path": rel,
                    "class": cls[0] if cls else "declared-fixture",
                    "rule": ("allow-list sha256 mismatch: declared "
                             f"{expected['sha256']}, measured {actual}"),
                })
                continue

            if cls:
                violations.append({"path": rel, "class": cls[0], "rule": cls[1]})
                continue

            # The gate's own allow-list configuration is hash-governed
            # version-controlled input; its declared reason strings may quote
            # synthetic fixture values by design. Never content-scan it.
            #
            # EPC-01 P2-9: the absolute-path comparison alone was not enough. When the gate
            # scans an EXPORTED archive (--from-commit) the file sits at
            # <tempdir>/tools/release/fixture_allowlist.json while allowlist_abs still points
            # into the repository, so the two never matched and the gate reported its OWN
            # allow-list as a credential hit. Matching the trailing relative path as well
            # makes the exclusion hold wherever the scanned tree happens to live.
            if allowlist_abs is not None and (
                full == allowlist_abs
                or _posix(rel).endswith("/" + os.path.basename(allowlist_abs))
                or _posix(rel) == os.path.basename(allowlist_abs)
            ):
                continue

            hits = scan_content(full, fn)
            for name, rule in hits:
                content_hits.append({"path": rel, "class": "credential-pattern",
                                     "rule": rule})

    return {
        "violations": violations,
        "quarantined": quarantined,
        "allowlisted": allowlisted,
        "credential_hits": content_hits,
        "files_scanned": files_scanned,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Allow-list-oriented package boundary gate (C-1 closure).")
    ap.add_argument("--root", default=".",
                    help="tree root to scan (default: current directory)")
    ap.add_argument("--from-commit", default=None, metavar="REV",
                    help="EPC-01 P2-9: export `git archive REV` to a temporary directory and "
                         "scan THAT instead of --root. This is what the gate should almost "
                         "always do: the boundary being policed is the DISTRIBUTION's, and a "
                         "working tree additionally holds .venv, node_modules, .pytest_cache "
                         "and build output no recipient ever sees. Scanning the tree reported "
                         "20,093 violations where the archive has none.")
    ap.add_argument("--allowlist", default=None,
                    help="declared-fixture allow-list JSON (value-based). Defaults to "
                         "tools/release/fixture_allowlist.json beside this script when it "
                         "exists — it shipped as the answer to the declared-fixture problem "
                         "and was then never passed, so the gate reported its own fixtures "
                         "as credential hits.")
    ap.add_argument("--quarantine-lane", action="append", default=None,
                    help="quarantined-historical lane prefix (repeatable); "
                         "default: evidence/ and dev/")
    ap.add_argument("--json", action="store_true", help="emit JSON report")
    args = ap.parse_args(argv)

    lanes = tuple(args.quarantine_lane) if args.quarantine_lane \
        else DEFAULT_QUARANTINE_LANES
    lanes = tuple(l if l.endswith("/") else l + "/" for l in lanes)

    allowlist_path = args.allowlist
    if allowlist_path is None:
        beside = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "fixture_allowlist.json")
        if os.path.isfile(beside):
            allowlist_path = beside

    try:
        allowlist = load_allowlist(allowlist_path)
    except AllowlistError as exc:
        print(f"package_boundary_gate: CONFIG ERROR: {exc}", file=sys.stderr)
        return 2

    scan_root, exported = args.root, None
    if args.from_commit:
        exported = tempfile.mkdtemp(prefix="pbg-archive-")
        proc = subprocess.run(
            ["git", "-C", os.path.abspath(args.root), "archive", "--format=tar",
             args.from_commit],
            capture_output=True, check=False)
        if proc.returncode != 0:
            shutil.rmtree(exported, ignore_errors=True)
            print(f"package_boundary_gate: git archive {args.from_commit} failed: "
                  f"{proc.stderr.decode('utf-8', 'replace')[:200]}", file=sys.stderr)
            return 2
        with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
            tar.extractall(exported)
        scan_root = exported

    if not os.path.isdir(scan_root):
        print(f"package_boundary_gate: no such directory: {scan_root}",
              file=sys.stderr)
        return 2

    try:
        result = scan_tree(scan_root, lanes, allowlist,
                           allowlist_source_path=allowlist_path)
    finally:
        if exported:
            shutil.rmtree(exported, ignore_errors=True)
    failed = bool(result["violations"]) or bool(result["credential_hits"])
    report = {
        "gate": "package_boundary_gate",
        "directive": "SWS-REM-DIR-20260828 R2 / B1-1 (C-1 closure)",
        "root": os.path.abspath(args.root),
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verdict": "FAIL" if failed else "PASS",
        "quarantine_lanes": list(lanes),
        "files_scanned": result["files_scanned"],
        "violation_count": len(result["violations"]),
        "credential_hit_count": len(result["credential_hits"]),
        "quarantined_count": len(result["quarantined"]),
        "allowlisted_count": len(result["allowlisted"]),
        "violations": result["violations"],
        "credential_hits": result["credential_hits"],
        "quarantined_sample": result["quarantined"][:25],
        "allowlisted": result["allowlisted"],
    }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"package_boundary_gate: {report['verdict']} "
              f"(files scanned: {report['files_scanned']}, "
              f"violations: {report['violation_count']}, "
              f"credential hits: {report['credential_hit_count']}, "
              f"quarantined-historical: {report['quarantined_count']}, "
              f"allowlisted: {report['allowlisted_count']})")
        for v in result["violations"]:
            print(f"  VIOLATION [{v['class']}] {v['path']}  ({v['rule']})")
        for v in result["credential_hits"]:
            print(f"  VIOLATION [credential-pattern] {v['path']}  ({v['rule']})")
        if result["quarantined"] and not args.json:
            print(f"  (quarantined-historical items listed in JSON mode; "
                  f"{report['quarantined_count']} total)")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
