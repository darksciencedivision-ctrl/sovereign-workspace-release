"""Run the committed Phase 19 Python suite contract with its wall-clock ceiling.

This wrapper intentionally uses only the standard library. pytest-timeout is not a repository
dependency and Phase 19 may not install it without a separate operator ruling.
"""
from __future__ import annotations

import argparse
import configparser
import os
from pathlib import Path
import signal
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "pytest.ini"


def _contract() -> tuple[float, list[str]]:
    parser = configparser.ConfigParser()
    if not parser.read(CONFIG, encoding="utf-8") or "pytest" not in parser:
        raise SystemExit(f"Phase 19 pytest contract is unreadable: {CONFIG}")
    section = parser["pytest"]
    ceiling = float(section["phase19_suite_timeout_seconds"])
    paths = [line.strip() for line in section["phase19_focused_paths"].splitlines()
             if line.strip()]
    if ceiling <= 0 or not paths:
        raise SystemExit("Phase 19 pytest contract has an invalid ceiling or empty focused subset")
    return ceiling, paths


#: The two bounds beneath the ceiling. A ceiling is only a ceiling if every wait under it is
#: finite: the wrapper used to send SIGTERM and then call `process.wait()` with NO timeout, so a
#: child that ignored the signal hung here forever and the committed ceiling never fired (6.12).
TERMINATE_GRACE_SECONDS = 10.0
HARD_KILL_GRACE_SECONDS = 10.0


def _terminate_tree(process: subprocess.Popen[bytes], *, hard: bool = False) -> None:
    """Signal the tree. `hard` selects the un-ignorable step.

    On Windows there is no softer tree-wide option in the standard library: `taskkill /T /F` is
    already the hard kill, so both steps take it and the escalation is a no-op on the second call.
    On POSIX the soft step is SIGTERM — which a child may ignore, which is the whole defect — and
    the hard step is SIGKILL, which it may not.
    """
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        os.killpg(process.pid, signal.SIGKILL if hard else signal.SIGTERM)


def _reap(process: subprocess.Popen[bytes]) -> bool:
    """Bounded escalation: terminate → bounded wait → kill → bounded wait. Returns True when the
    tree is STILL unreaped afterwards, so the caller reports that rather than waiting on it."""
    _terminate_tree(process)
    try:
        process.wait(timeout=TERMINATE_GRACE_SECONDS)
        return False
    except subprocess.TimeoutExpired:
        pass
    _terminate_tree(process, hard=True)
    try:
        process.wait(timeout=HARD_KILL_GRACE_SECONDS)
        return False
    except subprocess.TimeoutExpired:
        return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("focused", "full"))
    ap.add_argument("pytest_args", nargs=argparse.REMAINDER)
    ns = ap.parse_args(argv)
    ceiling, focused = _contract()
    targets = focused if ns.mode == "focused" else ["tests/"]
    extra = ns.pytest_args[1:] if ns.pytest_args[:1] == ["--"] else ns.pytest_args
    command = [sys.executable, "-m", "pytest", *targets, "-q", *extra]
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(command, cwd=ROOT, creationflags=creationflags,
                               start_new_session=os.name != "nt")
    try:
        return process.wait(timeout=ceiling)
    except subprocess.TimeoutExpired:
        unreaped = _reap(process)
        print(f"Phase 19 {ns.mode} suite exceeded the committed {ceiling:g}s ceiling",
              file=sys.stderr)
        if unreaped:
            # Reported, never waited on: an unreaped tree is a different outcome from a suite that
            # merely ran long, and the operator has to be able to tell them apart.
            print(f"…and the process tree was still unreaped after "
                  f"{TERMINATE_GRACE_SECONDS:g}s + {HARD_KILL_GRACE_SECONDS:g}s",
                  file=sys.stderr)
            return 125
        return 124


if __name__ == "__main__":
    raise SystemExit(main())
