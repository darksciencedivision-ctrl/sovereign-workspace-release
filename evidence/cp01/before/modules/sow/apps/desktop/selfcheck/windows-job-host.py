"""Pre-spawn Windows Job Object host for packaged Electron self-checks.

The host process owns the Job Object but is not a member. It launches a gated member
process, assigns that member before releasing it to spawn Electron, and waits until the
job has no members. This closes the inventory race where an Electron bootstrap could
spawn and reparent a child before a polling launcher first observed it.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from adapters.frontier.process_tree import WindowsJob


TIMEOUT_EXIT = 124
HOST_ERROR_EXIT = 125


def _member(command: list[str]) -> int:
    if sys.stdin.readline().strip() != "GO":
        print("[windows-job-host] member was not admitted", file=sys.stderr)
        return HOST_ERROR_EXIT
    try:
        return subprocess.Popen(command).wait()
    except OSError as error:
        print(f"[windows-job-host] member launch failed: {error}", file=sys.stderr)
        return HOST_ERROR_EXIT


def _host(command: list[str], timeout_ms: int) -> int:
    if os.name != "nt":
        return subprocess.Popen(command).wait()

    job = WindowsJob()
    member: subprocess.Popen[str] | None = None
    try:
        member_cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--member",
            "--",
            *command,
        ]
        member = subprocess.Popen(member_cmd, stdin=subprocess.PIPE, text=True)
        job.assign(member)
        assert member.stdin is not None
        member.stdin.write("GO\n")
        member.stdin.close()

        deadline = time.monotonic() + max(0.001, timeout_ms / 1000)
        member_code: int | None = None
        while time.monotonic() < deadline:
            if member_code is None:
                member_code = member.poll()
            if not job.pids():
                if member_code is None:
                    member_code = member.wait(timeout=1)
                return int(member_code)
            time.sleep(0.05)

        remaining = job.terminate_and_wait(15.0)
        if remaining:
            print(
                f"[windows-job-host] timeout cleanup left job pids {sorted(remaining)}",
                file=sys.stderr,
            )
            return HOST_ERROR_EXIT
        if member.poll() is None:
            member.wait(timeout=5)
        print(
            f"[windows-job-host] hard timeout after {timeout_ms}ms; job reaped",
            file=sys.stderr,
        )
        return TIMEOUT_EXIT
    except BaseException as error:
        try:
            remaining = job.terminate_and_wait(15.0)
        except BaseException as cleanup_error:
            print(
                f"[windows-job-host] setup failed: {error}; cleanup failed: {cleanup_error}",
                file=sys.stderr,
            )
            return HOST_ERROR_EXIT
        print(
            f"[windows-job-host] setup failed: {error}; remaining={sorted(remaining)}",
            file=sys.stderr,
        )
        return HOST_ERROR_EXIT
    finally:
        job.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-ms", type=int, default=150_000)
    parser.add_argument("--member", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a command is required after --")
    return _member(command) if args.member else _host(command, args.timeout_ms)


if __name__ == "__main__":
    raise SystemExit(main())
