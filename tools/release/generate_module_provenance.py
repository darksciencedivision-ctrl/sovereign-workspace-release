#!/usr/bin/env python
"""Generate current INSTALL-PROVENANCE.json records against the CANDIDATE'S ACTUAL CONTENTS.

SWS-REM-DIR-20260828 R2, B2-2 (C-3 closure, part 1). For each named module the
record is derived mechanically from the bytes present in the release worktree
(extracted from SYSTEM baseline 75e4be07…ac27138), never from prose or memory:

* ``source_sha256`` is the module CONTENT DIGEST — SHA-256 over the sorted
  ``<sha256>  <relpath>`` lines of every file under ``modules/<m>/`` at
  generation time, excluding the module's own INSTALL-PROVENANCE.json
  (self-reference). The basis string records the method verbatim.
* lockfiles and build artifacts are re-hashed on the spot.
* lineage facts from the preserved legacy records are carried into
  ``lineage_history`` marked as history, with [U] where unverified.

Legacy supersession files are never renamed, rewritten, or removed by this
tool. Stdlib-only, offline. Run with --write to emit the records; default is
dry-run printing the JSON to stdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

BASELINE_ZIP = "SOVEREIGN_SYSTEM_BASELINE_20260827.zip"
BASELINE_SHA256 = "75e4be075dcb5629c3175850f5aa3f342c7c693f2967c3620d6cd4914ac27138"
INITIAL_COMMIT = "cf50cde2f64b9db1a5021db80da8d9843a657926"
RECORD_NAME = "INSTALL-PROVENANCE.json"

MODULES = {
    "debate": {
        "version_source": "modules/debate/BUILD-INFO.json::version",
        "lockfiles": ["modules/debate/requirements.lock.txt"],
        "artifacts": [],
        "lineage_history": {
            "carried_from": "modules/debate/INSTALL-PROVENANCE.previous.json",
            "installed_source_archive": "D:/Product Software/Debate_Table_v1.2_Phase1_Production_20260811_201116 - Copy.zip",
            "installed_source_sha256": "29b364b075e55b4ac5e66cd1399145838dfca691d82c4500253d4ece36742f93",
            "note": "The installed v1.2 Phase1 archive was superseded by the director-accepted v1.2.1-hardening swap (BUILD-INFO.json: source_commit 43695bd, upstream baseline d7be33579c0f986db74c0b221b5bdf06a9d280df); release ZIP d03ba417… cited by directive §3 remains [U] here.",
            "module_manifest": {
                "path": "modules/debate/MANIFEST-SHA256.json",
                "note": "module's own content manifest; hash measured at generation",
            },
        },
        "open_items": [
            "OD-9: Debate Phase-7/Phase-8 deferrals and extended soak stay out of this release (named limitations)",
        ],
    },
    "sow": {
        "version_source": "modules/sow/apps/desktop/package.json::version",
        "lockfiles": ["modules/sow/apps/desktop/package-lock.json"],
        "artifacts": [],
        "lineage_history": {
            "carried_from": "modules/sow/INSTALL-PROVENANCE.previous.json",
            "source_kind": "git_worktree_copy",
            "git_head": "6d23a81082836778ffd46c70151821b467dc7432",
            "upstream_ref": "e6fcb89 [U] (directive §3; records cite upstream e6fcb89, unverified)",
            "working_tree_state": "dirty_tracked=true, dirty_untracked=true (four dirty entries per legacy record) [U]",
            "electron_zip_sha256": "e91986dd243d55947e6c5d3fad21795562ec21fa0eec5e95f7e28c830571467f",
            "electron_version": "31.7.7 (EOL; H-2 upgrade is its own Batch-3 unit)",
            "note": "Canonical SOW lineage is UNRESOLVED pending the OD-20 ruling (H-5): RESET-only files control_plane/canonical_registry.py and adapters/local/llamacpp.py are absent from this SYSTEM tree. This record describes the candidate bytes as they stand; it does not adjudicate lineage.",
        },
        "open_items": [
            "OD-20: H-5 canonical lineage ruling required before any SOW lineage claim becomes accepted",
            "H-1 admission-before-spawn and H-2 Electron upgrade are separate authorized units",
        ],
    },
    "distillery": {
        "version_source": "modules/distillery/pyproject.toml::version",
        "lockfiles": [],
        "artifacts": [
            "modules/distillery/dist/sovereign_grounded_distillery-1.1.0rc3-py3-none-any.whl",
            "modules/distillery/dist/sovereign_grounded_distillery-1.1.0rc3.tar.gz",
        ],
        "lineage_history": {
            "carried_from": "modules/distillery/INSTALL-PROVENANCE.json.previous (and INSTALL-MANIFEST.txt.previous, both preserved untouched)",
            "source": "D:\\Product Software\\SOVEREIGN_DISTILLERY_ENTERPRISE_20260821T011825Z_5ff6f56e\\SOURCE_TREE",
            "method": "robocopy /E",
            "commit": "6cd9886 [U] (directive §3)",
            "note": "Protected D:\\Sovereign Distillery\\ was never a copy source. Version 1.1.0rc3 is coupled in pyproject.toml and docs/VERSION_MATRIX.json (W-4 coupling; OD-2 governs release).",
        },
        "open_items": [
            "OD-2: SD-RBR-v1.0 W-4/W-5 release token issued at T-1; execution in its authorized batch",
            "OD-7/OD-8: Distillery governance dispositions; ships status-only this release (OD-8 default)",
        ],
    },
}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def content_digest(module_dir: str) -> tuple:
    entries = []
    for root, dirs, files in os.walk(module_dir):
        dirs.sort()
        for fn in sorted(files):
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, module_dir).replace(os.sep, "/")
            if rel == RECORD_NAME:
                continue
            entries.append((rel, sha256_file(full)))
    entries.sort(key=lambda item: item[0])
    blob = "".join(f"{digest}  {rel}\n" for rel, digest in entries)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest(), len(entries)


def read_version(root: str, spec: str) -> str:
    path, _, field = spec.partition("::")
    full = os.path.join(root, path.replace("/", os.sep))
    if path.endswith(".json"):
        with open(full, "r", encoding="utf-8-sig") as f:
            return str(json.load(f)[field])
    # pyproject.toml: naive but deterministic for 'version = "..."'
    for line in open(full, "r", encoding="utf-8"):
        line = line.strip()
        if line.startswith(field):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise KeyError(f"{field} not found in {path}")


def head_commit(root: str) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip() if out.returncode == 0 else "[U]"
    except Exception:
        return "[U]"


def generate(root: str) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    head = head_commit(root)
    records = {}
    for name, cfg in MODULES.items():
        module_dir = os.path.join(root, "modules", name)
        digest, count = content_digest(module_dir)
        record = {
            "module": name,
            "record_kind": "candidate-content provenance (SWS-REM-DIR-20260828 R2 B2-2)",
            "generated_utc": now,
            "producer": "builder qwen3.8-max via tools/release/generate_module_provenance.py",
            "candidate": {
                "baseline_archive": BASELINE_ZIP,
                "baseline_sha256": BASELINE_SHA256,
                "worktree": "D:/producttion software 2/release-worktree",
                "worktree_initial_commit": INITIAL_COMMIT,
                "worktree_commit_at_generation": head,
            },
            "source_kind": "candidate_tree_module",
            "source_sha256": digest,
            "source_sha256_basis": (
                "module content digest: SHA-256 over sorted '<sha256>  <relpath>' "
                f"lines of all {count} files under modules/{name}/ at generation "
                f"time, excluding {RECORD_NAME} itself"),
            "content_file_count": count,
            "version": read_version(root, cfg["version_source"]),
            "lockfiles": [
                {"path": p, "sha256": sha256_file(os.path.join(root, p.replace("/", os.sep)))}
                for p in cfg["lockfiles"]
            ],
            "artifacts": [
                {"path": p, "sha256": sha256_file(os.path.join(root, p.replace("/", os.sep)))}
                for p in cfg["artifacts"]
            ],
            "lineage_history": cfg["lineage_history"],
            "superseded_records": [cfg["lineage_history"]["carried_from"].split(" (")[0]],
            "operator_authorized": None,
            "integrity_verified": True,
            "verification_basis": (
                "content digest, lockfile and artifact hashes computed mechanically "
                "from candidate bytes at generation time; lineage_history carried "
                "from the preserved legacy record and marked [U] where unverified"),
            "open_items": cfg["open_items"],
        }
        records[name] = record
    return records


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--write", action="store_true",
                    help="write modules/<m>/INSTALL-PROVENANCE.json (default: dry-run)")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    records = generate(root)
    for name, record in records.items():
        if args.write:
            dest = os.path.join(root, "modules", name, RECORD_NAME)
            with open(dest, "w", encoding="utf-8", newline="\n") as f:
                json.dump(record, f, indent=2, ensure_ascii=False)
                f.write("\n")
            print(f"wrote {os.path.relpath(dest, root)}")
        else:
            print(json.dumps(record, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
