from __future__ import annotations

import platform
import sys
from pathlib import Path

from distillery.common import ContractError, utc_now, write_new_json


STATUSES = {"PASS", "PASS_WITH_LIMITATIONS", "FAIL", "BLOCKED", "QUARANTINED"}


def create_attempt(run_root: str | Path, run_id: str, phase: str, attempt: int, result: dict) -> Path:
    if attempt < 1 or attempt > 3:
        raise ContractError("attempt must respect retry ceiling 1..3")
    if result.get("status") not in STATUSES:
        raise ContractError("invalid attempt status")
    attempt_dir = Path(run_root) / run_id / f"attempt-{attempt:03d}"
    document = {
        "run_id": run_id, "phase": phase, "attempt": attempt, "git_head_before": "", "git_head_after": "",
        "inputs": [], "outputs": [], "measured": {}, "derived": {}, "limitations": [], "failures": [],
        "resume_pointer": "", "evidence_paths": [], **result,
    }
    write_new_json(attempt_dir / "result.json", document)
    write_new_json(attempt_dir / "environment.json", {"recorded_at": utc_now(), "python": sys.version, "platform": platform.platform()})
    return attempt_dir
