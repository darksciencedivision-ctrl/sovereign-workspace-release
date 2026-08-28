"""Run the committed Phase 19 Python suite contract with its wall-clock ceiling.

This wrapper intentionally uses only the standard library. pytest-timeout is not a repository
dependency and Phase 19 may not install it without a separate operator ruling.

EXIT VOCABULARY (U480): a ceiling breach and a suite failure are DIFFERENT outcomes.
The child's own exit code is returned unchanged when it finishes. On a breach:
124  the ceiling fired with NO test failure observed - host load, NOT a product verdict;
123  the ceiling fired with at least one test failure/error OBSERVED - a product verdict;
125  the process tree could not be reaped at all.
The gate runner maps these onto NOT_VERIFIED_ON_THIS_HOST / FAIL respectively.
"""
from __future__ import annotations

import argparse
import configparser
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading


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

#: Exit code for a breach where at least one test failure/error was OBSERVED before the
#: kill. A breach carrying real failures stays a product verdict downstream (U480).
CEILING_FAILURE_OBSERVED_EXIT = 123

_COLLECTED_RE = re.compile(rb"^collected \d+ items?", re.MULTILINE)


def _drain(pipe, sink: bytearray) -> None:
    """Read the child's merged output until EOF.

    Runs on a daemon thread so the pipe can never fill and stall the suite beneath a
    wall-clock ceiling; draining is load-bearing for the breach classification, because a
    stalled child stops streaming progress and late failures would go unobserved.
    """
    while True:
        chunk = pipe.read(65536)
        if not chunk:
            return
        sink.extend(chunk)


def _failures_observed(stream: bytes | None) -> bool:
    """Did any test failure/error surface in the captured stream BEFORE the kill?

    With ``-q`` the only LIVE evidence pytest streams is one progress character per
    finished test (``.``/``F``/``E``/``s``/``x``/``X``); failure tracebacks and summaries
    are buffered to the END of the run, which a breached run never reaches. Scanning
    starts AFTER the last ``collected N items`` header so header words cannot masquerade
    as progress characters. If collection had not completed when the ceiling fired, no
    failure COULD have been observed yet and the answer is honestly False.
    """
    if not stream:
        return False
    matches = list(_COLLECTED_RE.finditer(stream))
    region = stream[matches[-1].end():] if matches else stream
    return b"F" in region or b"E" in region


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
    # Merged into one pipe and drained CONTINUOUSLY on a daemon thread: an unread pipe
    # fills, the child stalls, and late failures would vanish from the classification.
    process = subprocess.Popen(command, cwd=ROOT, creationflags=creationflags,
                               start_new_session=os.name != "nt",
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    captured = bytearray()
    drainer = None
    child_out = getattr(process, "stdout", None)
    if child_out is not None:
        drainer = threading.Thread(target=_drain, args=(child_out, captured), daemon=True)
        drainer.start()
    try:
        rc = process.wait(timeout=ceiling)
    except subprocess.TimeoutExpired:
        unreaped = _reap(process)
        if drainer is not None:
            drainer.join(TERMINATE_GRACE_SECONDS + HARD_KILL_GRACE_SECONDS)
        print(f"Phase 19 {ns.mode} suite exceeded the committed {ceiling:g}s ceiling",
              file=sys.stderr)
        if unreaped:
            # Reported, never waited on: an unreaped tree is a different outcome from a suite that
            # merely ran long, and the operator has to be able to tell them apart.
            print(f"…and the process tree was still unreaped after "
                  f"{TERMINATE_GRACE_SECONDS:g}s + {HARD_KILL_GRACE_SECONDS:g}s",
                  file=sys.stderr)
            return 125
        if _failures_observed(bytes(captured)):
            print(
                "At least one test failure/error was OBSERVED before the ceiling fired; "
                f"reporting exit {CEILING_FAILURE_OBSERVED_EXIT} so a loaded host cannot "
                "excuse real failures.",
                file=sys.stderr)
            return CEILING_FAILURE_OBSERVED_EXIT
        print(
            "NO test failure was observed before the ceiling fired: this is host load, "
            "not a product verdict.",
            file=sys.stderr)
        return 124
    if drainer is not None:
        drainer.join(30.0)
    sys.stdout.buffer.write(bytes(captured))
    sys.stdout.buffer.flush()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
