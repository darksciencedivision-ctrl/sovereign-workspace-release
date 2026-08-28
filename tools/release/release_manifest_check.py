#!/usr/bin/env python
"""Release-manifest validator — SWS-REM-DIR-20260828 R2, B2-2 (C-3 closure).

Reads RELEASE-MANIFEST.json and mechanically verifies, per enumerated module:

* the current provenance record exists at the exact enumerated path and its
  bytes hash to the enumerated ``provenance_record_sha256``;
* every superseded provenance path exists (legacy files preserved untouched);
* every enumerated lock / module-manifest / artifact path exists and its
  SHA-256 equals the enumerated hash;
* every explicitly enumerated batch-touched file exists and its SHA-256 equals
  the freshly measured hash (the manifest excludes itself by construction);
* the current record's own ``source_sha256`` equals the manifest's
  ``source_identity.content_digest_sha256`` or ``source_identity.source_sha256``
  when both are enumerated (consistency, not trust).

The validator NEVER infers paths by glob: the manifest is the enumeration
authority (R2 §4 Batch 2, C-3 design). Exit codes: 0 pass, 1 failures,
2 configuration error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check(root: str, manifest: dict) -> list:
    problems = []
    modules = manifest.get("modules", {})
    if not modules:
        problems.append("manifest enumerates no modules")
        return problems

    for name, entry in modules.items():
        cur = entry.get("current_provenance_path")
        if not cur:
            problems.append(f"{name}: no current_provenance_path enumerated")
            continue
        cur_full = os.path.join(root, cur.replace("/", os.sep))
        if not os.path.isfile(cur_full):
            problems.append(f"{name}: current record missing at {cur}")
            record = None
        else:
            expected_rec = entry.get("provenance_record_sha256")
            if expected_rec:
                actual = sha256_file(cur_full)
                if actual != expected_rec:
                    problems.append(
                        f"{name}: provenance record hash mismatch at {cur} "
                        f"(enumerated {expected_rec}, measured {actual})")
            try:
                with open(cur_full, "r", encoding="utf-8-sig") as f:
                    record = json.load(f)
            except (OSError, ValueError) as exc:
                problems.append(f"{name}: current record unreadable: {exc}")
                record = None

        for sup in entry.get("superseded_provenance_paths", []):
            if not os.path.isfile(os.path.join(root, sup.replace("/", os.sep))):
                problems.append(f"{name}: superseded record missing at {sup}")

        for group in ("locks", "module_manifests", "artifacts"):
            for item in entry.get(group, []):
                p = item.get("path")
                want = item.get("sha256")
                full = os.path.join(root, p.replace("/", os.sep))
                if not os.path.isfile(full):
                    problems.append(f"{name}: {group} file missing at {p}")
                    continue
                got = sha256_file(full)
                if got != want:
                    problems.append(
                        f"{name}: {group} hash mismatch at {p} "
                        f"(enumerated {want}, measured {got})")

        ident = entry.get("source_identity", {})
        expected_src = (ident.get("content_digest_sha256")
                        or ident.get("source_sha256"))
        if record is not None and expected_src:
            actual_src = record.get("source_sha256")
            if actual_src and actual_src != expected_src:
                problems.append(
                    f"{name}: record source_sha256 {actual_src} != manifest "
                    f"source identity {expected_src}")

    for item in manifest.get("batch_files", []):
        path = item.get("path")
        expected = item.get("sha256")
        if not path or not expected:
            problems.append("batch_files: every item must enumerate path and sha256")
            continue
        full = os.path.join(root, path.replace("/", os.sep))
        if not os.path.isfile(full):
            problems.append(f"batch_files: file missing at {path}")
            continue
        actual = sha256_file(full)
        if actual != expected:
            problems.append(
                f"batch_files: hash mismatch at {path} "
                f"(enumerated {expected}, measured {actual})")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate RELEASE-MANIFEST.json bytes.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--manifest", default="RELEASE-MANIFEST.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    manifest_path = os.path.join(args.root, args.manifest.replace("/", os.sep)) \
        if not os.path.isabs(args.manifest) else args.manifest
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"release_manifest_check: CONFIG ERROR: cannot read manifest: {exc}",
              file=sys.stderr)
        return 2
    if not os.path.isdir(args.root):
        print(f"release_manifest_check: no such directory: {args.root}",
              file=sys.stderr)
        return 2

    problems = check(os.path.abspath(args.root), manifest)
    report = {
        "gate": "release_manifest_check",
        "directive": "SWS-REM-DIR-20260828 R2 / B2-2 (C-3 closure)",
        "manifest": manifest_path,
        "root": os.path.abspath(args.root),
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verdict": "FAIL" if problems else "PASS",
        "problem_count": len(problems),
        "problems": problems,
    }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"release_manifest_check: {report['verdict']} "
              f"({report['problem_count']} problems)")
        for p in problems:
            print(f"  PROBLEM {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
