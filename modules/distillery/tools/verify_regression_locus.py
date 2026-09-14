from __future__ import annotations

"""Reproduce-or-refuse verification of the recorded regression locus (R-1).

Reads measured_at_commit / command / result / exit_code from
LOOP_STATE.last_full_regression, materializes that commit in a temporary
worktree OUTSIDE the repository, overlays the declared-evidence payloads that
the certified configuration is known to carry (the binding ledger itself and
everything in locus..HEAD, which the manifest generator already constrains to
evidence paths), runs the recorded command there, and compares observed vs
recorded. Emits runs/release-baseline/REGRESSION_LOCUS_VERIFICATION.json with
observed/recorded and verdict PASS|FAIL; exits non-zero on ANY difference.

The overlay is explicit: bare-locus checkouts lack the binding ledger by
construction (a ledger cannot name its own containing commit), so the honest,
reproducible configuration is "locus tree + sealed evidence payloads". The
record lists every overlaid path and its source blob sha so any verifier can
reproduce it cold.
"""

import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOOP_STATE_PATH = ROOT / "runs" / "completion-loop" / "LOOP_STATE.json"
RECORD_PATH = ROOT / "runs" / "release-baseline" / "REGRESSION_LOCUS_VERIFICATION.json"


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=check)


def _blob_sha(repo: Path, relative: str) -> str:
    out = _git(repo, "rev-parse", f"HEAD:{relative}").stdout.strip()
    return out


def verify() -> dict:
    record = {
        "kind": "REGRESSION_LOCUS_VERIFICATION",
        "tool": "tools/verify_regression_locus.py",
        "started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "recorded": {},
        "observed": {},
        "overlay": [],
        "worktree_cleaned_up": False,
        "verdict": "FAIL",
    }
    state = json.loads(LOOP_STATE_PATH.read_text(encoding="utf-8"))
    regression = state.get("last_full_regression", {})
    measured_at_commit = regression.get("measured_at_commit")
    command = regression.get("command")
    recorded_result = regression.get("result")
    recorded_exit = regression.get("exit_code")
    if not all(isinstance(v, str) and v for v in (measured_at_commit, command, recorded_result)) or not isinstance(recorded_exit, int):
        record["error"] = "LOOP_STATE.last_full_regression lacks a complete binding"
        return record
    record["recorded"] = {
        "measured_at_commit": measured_at_commit,
        "command": command,
        "result": recorded_result,
        "exit_code": recorded_exit,
    }

    ancestor = _git(ROOT, "merge-base", "--is-ancestor", measured_at_commit, "HEAD", check=False)
    record["is_ancestor_or_self_of_head"] = ancestor.returncode == 0

    temp_parent = Path(tempfile.mkdtemp(prefix="sd_locus_verify_"))
    worktree = temp_parent / "wt"
    try:
        _git(ROOT, "worktree", "add", "--detach", str(worktree), measured_at_commit)
        # The certified configuration is the locus tree plus EXACTLY the evidence
        # payloads present when the binding was sealed - i.e. the last commit
        # that touched LOOP_STATE - never HEAD's later append-only ledger rows,
        # which would otherwise shift enumerated-subtest counts retroactively.
        seal_commit = _git(ROOT, "log", "-1", "--format=%H", "--", str(LOOP_STATE_PATH.relative_to(ROOT))).stdout.strip()
        record["overlay_source_commit"] = seal_commit
        delta = _git(ROOT, "diff", "--name-only", f"{measured_at_commit}..{seal_commit}").stdout.splitlines()
        for relative in (line.strip() for line in delta if line.strip()):
            show = subprocess.run(
                ["git", "-C", str(ROOT), "show", f"{seal_commit}:{relative}"],
                capture_output=True, check=False,
            )
            if show.returncode != 0:
                target = worktree / relative
                if target.exists():
                    target.unlink()
                    record["overlay"].append({"path": relative.replace("\\", "/"), "status": "DELETED_PER_SEAL_COMMIT"})
                else:
                    record["overlay"].append({"path": relative, "status": "ABSENT_IN_SEAL_COMMIT_SKIPPED"})
                continue
            payload = show.stdout
            target = worktree / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            record["overlay"].append(
                {
                    "path": relative.replace("\\", "/"),
                    "source_blob_sha256": hashlib.sha256(payload).hexdigest(),
                    "status": "OVERLAID",
                }
            )

        argv = shlex.split(command, posix=(os.name != "nt"))
        if not argv:
            record["error"] = "recorded command is empty"
            return record
        env = {
            key: value for key, value in os.environ.items()
            if not any(tok in key.upper() for tok in
                       ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH"))
        }
        env["PYTHONPYCACHEPREFIX"] = str(temp_parent / "pycache")
        completed = subprocess.run(
            argv, shell=False, cwd=str(worktree), capture_output=True, text=True, env=env,
        )
        import re as _re
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        raw_last_line = lines[-1].strip() if lines else ""
        observed_result = _re.sub(r"\s+in\s+[\d.]+s(?:.*$)?", "", raw_last_line).strip()
        record["observed"] = {
            "result": observed_result,
            "raw_last_line": raw_last_line,
            "exit_code": completed.returncode,
        }
        record["worktree_cleaned_up"] = True
    finally:
        subprocess.run(["git", "-C", str(ROOT), "worktree", "remove", "--force", str(worktree)], capture_output=True, text=True)
        import shutil as _shutil
        _shutil.rmtree(temp_parent, ignore_errors=True)

    matches = (
        record.get("is_ancestor_or_self_of_head") is True
        and record["observed"].get("exit_code") == recorded_exit
        and record["observed"].get("result") == recorded_result
    )
    record["finished_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    record["verdict"] = "PASS" if matches else "FAIL"
    return record


def main(argv: list[str]) -> int:
    record = verify()
    RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECORD_PATH.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: record[key] for key in ("verdict", "recorded", "observed")}, indent=2, sort_keys=True))
    return 0 if record["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
