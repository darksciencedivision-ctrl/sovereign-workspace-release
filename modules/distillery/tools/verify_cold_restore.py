from __future__ import annotations

"""Machine-checked cold restoration of the exported git bundle (SD-RBR-v1.0 W-3).

Replaces the prose-only "cold restore executed against regenerated bundle"
evidence with a deterministic, re-runnable check:

  1. clone the exported git bundle into a fresh temporary directory outside the repository
  2. verify the restored HEAD equals the declared source commit
  3. compare GIT BLOB HASHES for every tracked file, source vs restored
     (never raw worktree bytes: core.autocrlf transforms them on this host)
  4. run the full test suite inside the restored tree
  5. emit runs/export/COLD_RESTORE_RECORD.json with a machine verdict
  6. clean up the temporary clone

Exit code is 0 iff the verdict is PASS.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD_PATH = ROOT / "runs" / "export" / "COLD_RESTORE_RECORD.json"


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=check)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ls_tree_blobs(repo: Path, revision: str = "HEAD") -> dict[str, str]:
    output = _git(repo, "ls-tree", "-r", revision).stdout
    blobs: dict[str, str] = {}
    for line in output.splitlines():
        meta, path = line.split("\t", 1)
        _mode, kind, sha = meta.split()
        if kind == "blob":
            blobs[path] = sha
    return blobs


def _run_suite(restored: Path, cache_prefix: str) -> tuple[int, str]:
    env = dict(os.environ)
    env["PYTHONPYCACHEPREFIX"] = str(Path(tempfile.gettempdir()) / cache_prefix)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=str(restored), capture_output=True, text=True, env=env,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    summary = lines[-1].strip() if lines else ""
    return completed.returncode, summary


def verify(bundle_path: Path, source_commit: str | None = None) -> dict:
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    source_commit = source_commit or _git(ROOT, "rev-parse", "HEAD").stdout.strip()
    record: dict = {
        "kind": "COLD_RESTORE_RECORD",
        "tool": "tools/verify_cold_restore.py",
        "started_at_utc": started_at,
        "bundle_path": str(bundle_path),
        "bundle_sha256": _sha256_file(bundle_path),
        "source_commit": source_commit,
        "restored_head": None,
        "files_compared": 0,
        "mismatches": [],
        "suite": {"command": f"{sys.executable} -m pytest -q -p no:cacheprovider", "result": None, "exit_code": None},
        "temp_clone_cleaned_up": False,
        "verdict": "FAIL",
    }
    temp_parent = Path(tempfile.mkdtemp(prefix="sd_cold_restore_"))
    restored = temp_parent / "restored"
    try:
        _git(temp_parent.parent, "clone", str(bundle_path), str(restored))
        record["restored_head"] = _git(restored, "rev-parse", "HEAD").stdout.strip()
        head_matches = record["restored_head"] == source_commit
        if not head_matches:
            record["mismatches"].append(
                f"restored HEAD {record['restored_head']} != declared source commit {source_commit}"
            )

        source_blobs = _ls_tree_blobs(ROOT, source_commit)
        restored_blobs = _ls_tree_blobs(restored)
        for path in sorted(set(source_blobs) | set(restored_blobs)):
            if path not in restored_blobs:
                record["mismatches"].append(f"missing in restored tree: {path}")
            elif path not in source_blobs:
                record["mismatches"].append(f"unexpected in restored tree: {path}")
            elif source_blobs[path] != restored_blobs[path]:
                record["mismatches"].append(
                    f"blob hash mismatch: {path}: {source_blobs[path]} != {restored_blobs[path]}"
                )
        record["files_compared"] = len(source_blobs)

        suite_exit, suite_summary = _run_suite(restored, "sd_cold_restore_pycache")
        record["suite"]["exit_code"] = suite_exit
        record["suite"]["result"] = suite_summary

        record["temp_clone_cleaned_up"] = True
    finally:
        shutil.rmtree(temp_parent, ignore_errors=True)

    passed = (
        head_matches
        and not record["mismatches"]
        and record["suite"]["exit_code"] == 0
        and record["files_compared"] > 0
    )
    record["finished_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    record["verdict"] = "PASS" if passed else "FAIL"
    return record


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Machine-checked cold restore verification of the exported git bundle.")
    parser.add_argument("--bundle", required=True, type=Path, help="path to the exported git bundle")
    parser.add_argument("--source-commit", default=None, help="declared source commit (defaults to current HEAD)")
    parser.add_argument(
        "--record-output",
        type=Path,
        default=None,
        help="record destination (default: runs/export/COLD_RESTORE_RECORD.json; the verified fa89a2b9 record must not be overwritten)",
    )
    args = parser.parse_args(argv)
    if not args.bundle.is_file():
        print(f"FAIL: bundle not found: {args.bundle}")
        return 2
    record_path = args.record_output or RECORD_PATH
    record = verify(args.bundle.resolve(), args.source_commit)
    record["record_path"] = str(record_path)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: record[key] for key in ("verdict", "restored_head", "files_compared", "bundle_sha256")}, indent=2))
    return 0 if record["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
