"""Managed subprocess trees for live CLI adapters."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any


_JOB_MEMBER_FLAG = "--sovereign-job-member"


class ProcessTreeCleanupError(RuntimeError):
    """A managed live subprocess left descendants after bounded teardown."""


@dataclass(frozen=True)
class ManagedCompletedProcess:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str
    spawned_pids: tuple[int, ...]


class WindowsJob:
    """Small Windows Job Object wrapper with kill-on-close descendant ownership."""
    _KILL_ON_JOB_CLOSE = 0x00002000
    _EXTENDED_LIMIT_INFO = 9
    _BASIC_PID_LIST = 3
    _WAIT_OBJECT_0 = 0
    _ERROR_MORE_DATA = 234

    class _BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class _ExtendedLimit(ctypes.Structure):
        pass

    _ExtendedLimit._fields_ = [
        ("BasicLimitInformation", _BasicLimit),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]

    def __init__(self) -> None:
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        self._kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
        self._kernel32.SetInformationJobObject.argtypes = (
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32)
        self._kernel32.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        self._kernel32.QueryInformationJobObject.argtypes = (
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p)
        self._kernel32.TerminateJobObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        self._kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        self._kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)

        self.handle = self._kernel32.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = self._ExtendedLimit()
        info.BasicLimitInformation.LimitFlags = self._KILL_ON_JOB_CLOSE
        if not self._kernel32.SetInformationJobObject(
                self.handle, self._EXTENDED_LIMIT_INFO, ctypes.byref(info), ctypes.sizeof(info)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, proc: subprocess.Popen[str]) -> None:
        if not self._kernel32.AssignProcessToJobObject(
                self.handle, ctypes.c_void_p(int(proc._handle))):  # type: ignore[attr-defined]
            raise ctypes.WinError(ctypes.get_last_error())

    def pids(self) -> tuple[int, ...]:
        capacity = 16
        while True:
            class _PidList(ctypes.Structure):
                _fields_ = [
                    ("NumberOfAssignedProcesses", ctypes.c_uint32),
                    ("NumberOfProcessIdsInList", ctypes.c_uint32),
                    ("ProcessIdList", ctypes.c_size_t * capacity),
                ]

            info = _PidList()
            ok = self._kernel32.QueryInformationJobObject(
                self.handle, self._BASIC_PID_LIST, ctypes.byref(info), ctypes.sizeof(info), None)
            if ok:
                return tuple(int(info.ProcessIdList[i])
                             for i in range(int(info.NumberOfProcessIdsInList)))
            error = ctypes.get_last_error()
            if error != self._ERROR_MORE_DATA:
                raise ctypes.WinError(error)
            capacity = max(capacity * 2, int(info.NumberOfAssignedProcesses) + 8)

    def terminate_and_wait(self, timeout_s: float) -> tuple[int, ...]:
        if self.pids() and not self._kernel32.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())
        # M-4: a Job Object handle is signaled only on an end-of-job TIME LIMIT, never on
        # member exit — WaitForSingleObject here always ran to the full ceiling even when the
        # job was already empty (a measured ~15 s tax on EVERY managed run; independent review
        # F-3 / INDEPENDENT_REVIEW_WINDOWS_HOST_20260816.md). Poll the pid list instead: the
        # wait ends as soon as the last member is gone, still bounded by timeout_s.
        deadline = time.monotonic() + max(0.001, timeout_s)
        while True:
            remaining = self.pids()
            if not remaining:
                return ()
            if time.monotonic() >= deadline:
                return remaining
            time.sleep(0.05)

    def close(self) -> None:
        if self.handle:
            self._kernel32.CloseHandle(self.handle)
            self.handle = None


def _job_member_main(command: list[str]) -> int:
    """Wait for host admission, then spawn the target as an already-assigned job member."""
    # The Windows text-mode pipe translates the host's "GO\n" to CRLF. Read only
    # those four bytes from the raw descriptor so no payload is prefetched.
    gate = b""
    while len(gate) < 4:
        chunk = os.read(sys.stdin.fileno(), 4 - len(gate))
        if not chunk:
            break
        gate += chunk
    if gate != b"GO\r\n":
        print("managed process member was not admitted", file=sys.stderr)
        return 125
    if not command:
        print("managed process member has no target command", file=sys.stderr)
        return 125
    try:
        return subprocess.Popen(
            command,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
            text=True,
        ).wait()
    except OSError as error:
        print(f"managed process target launch failed: {error}", file=sys.stderr)
        return 125


def _run_windows(
    cmd: list[str], *, timeout: float, env: dict[str, str], stdin: Any,
    input_text: str | None = None, cwd: str | None = None,
) -> ManagedCompletedProcess:
    job = WindowsJob()
    proc: subprocess.Popen[str] | None = None
    tracked: set[int] = set()
    stdout = ""
    stderr = ""
    timed_out: subprocess.TimeoutExpired | None = None
    cleanup_error: BaseException | None = None
    assigned = False
    tracking_stop = threading.Event()
    tracking_error: list[BaseException] = []
    tracking_thread: threading.Thread | None = None
    try:
        # The member blocks on GO, so it cannot spawn/reparent the real target before
        # AssignProcessToJobObject succeeds. This is the pre-first-inventory boundary U158 requires.
        member_cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            _JOB_MEMBER_FLAG,
            "--",
            *cmd,
        ]
        proc = subprocess.Popen(
            member_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            # W-03/A-2: pin the codec. `text=True` ALONE resolves to the host ANSI codepage
            # (cp1252 here), where an undefined byte kills subprocess's reader THREAD -- and
            # subprocess swallows that exception, so the call returns exit 0 with the whole
            # transcript gone. `errors="replace"` is right for a TRANSPORT that reports the
            # text onward; the MCP stdio path deliberately uses `strict` instead, because there
            # the bytes become persisted content with hashes computed over them (W-04).
            encoding="utf-8", errors="replace",
            env=env,
            stdin=subprocess.PIPE,
            # The member inherits this and the real target inherits it from the member, so a
            # workspace binding survives the extra hop the job boundary requires.
            cwd=cwd,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        tracked.add(proc.pid)
        job.assign(proc)
        assigned = True

        def track_job_pids() -> None:
            while not tracking_stop.wait(0.05):
                try:
                    tracked.update(job.pids())
                except BaseException as error:
                    tracking_error.append(error)
                    return

        tracking_thread = threading.Thread(
            target=track_job_pids, name="live-cli-job-pid-tracker", daemon=True)
        tracking_thread.start()
        try:
            stdout, stderr = proc.communicate(
                input="GO\n" + (input_text or ""), timeout=timeout)
        except subprocess.TimeoutExpired as error:
            timed_out = error
    finally:
        try:
            if assigned:
                tracked.update(job.pids())
                remaining = job.terminate_and_wait(15.0)
                tracked.update(remaining)
                tracking_stop.set()
                if tracking_thread is not None:
                    tracking_thread.join(timeout=2.0)
                if tracking_error:
                    raise tracking_error[0]
                if remaining:
                    cleanup_error = ProcessTreeCleanupError(
                        f"managed workspace process descendants remain after shutdown: {sorted(remaining)}")
            elif proc is not None and proc.poll() is None:
                # Assignment can fail when a host applies an incompatible outer job. The call fails,
                # but its just-spawned tree must still be reaped before that error is surfaced.
                subprocess.run(
                    ["taskkill.exe", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True, text=True, check=False, timeout=15.0)
        except BaseException as error:
            cleanup_error = error
        finally:
            tracking_stop.set()
            if tracking_thread is not None:
                tracking_thread.join(timeout=2.0)
            job.close()
        if proc is not None:
            try:
                tail_out, tail_err = proc.communicate(timeout=5.0)
                stdout = stdout or tail_out or ""
                stderr = stderr or tail_err or ""
            except (subprocess.TimeoutExpired, ValueError):
                pass

    if cleanup_error is not None:
        raise ProcessTreeCleanupError(str(cleanup_error)) from cleanup_error
    if timed_out is not None:
        raise subprocess.TimeoutExpired(cmd, timeout, output=stdout, stderr=stderr)
    assert proc is not None
    return ManagedCompletedProcess(
        args=cmd, returncode=proc.returncode, stdout=stdout or "", stderr=stderr or "",
        spawned_pids=tuple(sorted(tracked)),
    )


def _run_posix(
    cmd: list[str], *, timeout: float, env: dict[str, str], stdin: Any,
    input_text: str | None = None, cwd: str | None = None,
) -> ManagedCompletedProcess:
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        # W-03/A-2: pin the codec. `text=True` ALONE resolves to the host ANSI codepage
        # (cp1252 here), where an undefined byte kills subprocess's reader THREAD -- and
        # subprocess swallows that exception, so the call returns exit 0 with the whole
        # transcript gone. `errors="replace"` is right for a TRANSPORT that reports the
        # text onward; the MCP stdio path deliberately uses `strict` instead, because there
        # the bytes become persisted content with hashes computed over them (W-04).
        encoding="utf-8", errors="replace",
        env=env,
        stdin=subprocess.PIPE if input_text is not None else stdin,
        cwd=cwd,
        start_new_session=True,
    )
    stdout = ""
    stderr = ""
    timed_out: subprocess.TimeoutExpired | None = None
    try:
        try:
            stdout, stderr = proc.communicate(input=input_text, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            timed_out = error
    finally:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                os.killpg(proc.pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            tail_out, tail_err = proc.communicate(timeout=5.0)
            stdout = stdout or tail_out or ""
            stderr = stderr or tail_err or ""
        except subprocess.TimeoutExpired as error:
            raise ProcessTreeCleanupError(
                f"managed workspace process descendants remain after shutdown: pgid {proc.pid}") from error

    if timed_out is not None:
        raise subprocess.TimeoutExpired(cmd, timeout, output=stdout, stderr=stderr)
    return ManagedCompletedProcess(
        args=cmd, returncode=proc.returncode, stdout=stdout or "", stderr=stderr or "",
        spawned_pids=(proc.pid,),
    )


def run_managed_process(
    cmd: list[str], *, timeout: float, env: dict[str, str], stdin: Any,
    input_text: str | None = None, cwd: str | None = None,
) -> ManagedCompletedProcess:
    """Run one live CLI call in a descendant-killing boundary and await cleanup.

    `cwd` is the child's working directory, `None` meaning "inherit" — which is what every caller
    before Phase 18B passed implicitly, so their behaviour is unchanged. It exists for a CLI whose
    workspace binding IS its working directory because it has no `--cwd`-equivalent flag (`agy`):
    without it the choice would have been between the job-object boundary and workspace
    containment, and giving up either would be a real loss."""
    if os.name == "nt":
        return _run_windows(
            cmd, timeout=timeout, env=env, stdin=stdin, input_text=input_text, cwd=cwd)
    return _run_posix(
        cmd, timeout=timeout, env=env, stdin=stdin, input_text=input_text, cwd=cwd)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == _JOB_MEMBER_FLAG:
        target = args[1:]
        if target and target[0] == "--":
            target = target[1:]
        raise SystemExit(_job_member_main(target))
    raise SystemExit("process_tree.py is a library; only the managed job-member mode is executable")
