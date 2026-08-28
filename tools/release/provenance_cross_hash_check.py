#!/usr/bin/env python
"""Provenance cross-module-hash check — SWS-REM-DIR-20260828 R2, B2-1 (C-2).

Mechanically rejects INSTALL-PROVENANCE records whose ``source_sha256`` is the
registered source hash of a DIFFERENT module (the C-2 defect class: sovereign
carrying the Distillery digest), and records whose hash matches no registered
identity at all.

Enumeration is EXPLICIT: the registry names each module and the exact relative
path of its current provenance record. No filename globs are used anywhere —
the manifest/registry is the authority (R2 §4 Batch 2, C-3 design).

Verdicts per module:
  OK        record present; hash equals the module's own registered hash
  CROSS     record present; hash equals ANOTHER module's registered hash -> FAIL
  UNKNOWN   record present; hash matches no registered identity -> FAIL
  MISSING   registered module has no current record at the named path -> FAIL
            (before B2-2 generates debate/sow/distillery records, the registry
            marks those modules 'pending' and they report PENDING instead)
  PENDING   registry entry carries no source_sha256 yet (not a failure)

Exit codes: 0 = no failures, 1 = at least one CROSS/UNKNOWN/MISSING,
2 = configuration/usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone


def load_registry(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as exc:
        raise RegistryError(f"cannot read registry {path}: {exc}") from exc
    modules = doc.get("modules")
    if not isinstance(modules, dict) or not modules:
        raise RegistryError("registry must contain a non-empty 'modules' map")
    for name, entry in modules.items():
        if not isinstance(entry, dict) or "provenance_path" not in entry:
            raise RegistryError(f"module {name!r} must name an exact provenance_path")
        p = entry["provenance_path"]
        if any(ch in p for ch in ("*", "?", "[")):
            raise RegistryError(
                f"module {name!r} provenance_path {p!r} contains glob characters; "
                "enumeration must be explicit")
    return modules


class RegistryError(Exception):
    pass


def check(root: str, modules: dict) -> dict:
    # hash -> owning module(s), for cross-module detection.
    # Ownership covers the registered source hash AND any historical hashes
    # a module is known to own (e.g. distillery owns 620e8459…, the digest
    # found mis-attributed inside sovereign's defective record).
    hash_owners: dict[str, list] = {}
    for name, entry in modules.items():
        owned = [entry.get("source_sha256")]
        owned.extend(entry.get("historical_source_hashes", []) or [])
        for h in owned:
            if h:
                hash_owners.setdefault(h, []).append(name)

    results = {}
    for name, entry in modules.items():
        rel = entry["provenance_path"]
        registered = entry.get("source_sha256")
        full = os.path.join(root, rel.replace("/", os.sep))

        if not os.path.isfile(full):
            if entry.get("status") == "pending" or not registered:
                results[name] = {"verdict": "PENDING",
                                 "detail": "no current record; registry entry pending (B2-2)"}
            else:
                results[name] = {"verdict": "MISSING",
                                 "detail": f"registered module lacks {rel}"}
            continue

        try:
            with open(full, "r", encoding="utf-8-sig") as f:
                record = json.load(f)
        except (OSError, ValueError) as exc:
            results[name] = {"verdict": "UNKNOWN",
                             "detail": f"record unreadable: {exc}"}
            continue

        actual = record.get("source_sha256")
        results[name] = {"record_path": rel, "record_source_sha256": actual}

        if actual == registered and registered:
            results[name]["verdict"] = "OK"
            results[name]["detail"] = "hash equals the module's own registered source hash"
        elif actual in hash_owners and all(owner != name for owner in hash_owners[actual]):
            results[name]["verdict"] = "CROSS"
            results[name]["detail"] = (
                "source_sha256 belongs to module(s): "
                + ", ".join(sorted(hash_owners[actual])))
        elif registered and actual != registered:
            results[name]["verdict"] = "UNKNOWN"
            results[name]["detail"] = (
                f"hash matches no registered identity (expected {registered})")
        elif not registered:
            results[name]["verdict"] = "PENDING"
            results[name]["detail"] = "registry entry carries no source_sha256 yet"
        else:
            results[name]["verdict"] = "OK"
            results[name]["detail"] = "hash equals the module's own registered source hash"
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Reject cross-module source hashes in INSTALL-PROVENANCE records.")
    ap.add_argument("--root", default=".", help="worktree root")
    ap.add_argument("--registry", required=True, help="module source registry JSON")
    ap.add_argument("--json", action="store_true", help="emit JSON report")
    args = ap.parse_args(argv)

    try:
        modules = load_registry(args.registry)
    except RegistryError as exc:
        print(f"provenance_cross_hash_check: CONFIG ERROR: {exc}", file=sys.stderr)
        return 2
    if not os.path.isdir(args.root):
        print(f"provenance_cross_hash_check: no such directory: {args.root}",
              file=sys.stderr)
        return 2

    results = check(args.root, modules)
    failures = {name: r for name, r in results.items()
                if r["verdict"] in ("CROSS", "UNKNOWN", "MISSING")}
    report = {
        "gate": "provenance_cross_hash_check",
        "directive": "SWS-REM-DIR-20260828 R2 / B2-1 (C-2 closure)",
        "root": os.path.abspath(args.root),
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verdict": "FAIL" if failures else "PASS",
        "results": results,
    }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"provenance_cross_hash_check: {report['verdict']}")
        for name in sorted(results):
            r = results[name]
            print(f"  {name:<12} {r['verdict']:<8} {r.get('detail', '')}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
