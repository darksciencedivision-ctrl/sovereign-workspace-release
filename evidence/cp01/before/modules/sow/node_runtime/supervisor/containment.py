"""Process-tree containment scaffold: Windows Job Objects (Plan section 7-P3, invariant 29).

What this ENFORCES today (no admin rights needed): every process assigned to the job —
including grandchildren it spawns — is killed when the job handle closes
(JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE). A node cannot leave surviving process trees.

What this does NOT enforce (recorded, U10 / Phase 10): filesystem or network denial at
the OS layer. Until P10 hardening, fs containment is the WorkspaceBinding API layer and
network policy is the (future) broker; a raw-syscall bypass is out of this phase's scope.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

_KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True) if hasattr(ctypes, "windll") else None

JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", wt.LARGE_INTEGER),
        ("PerJobUserTimeLimit", wt.LARGE_INTEGER),
        ("LimitFlags", wt.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wt.DWORD),
        ("Affinity", ctypes.POINTER(wt.ULONG)),
        ("PriorityClass", wt.DWORD),
        ("SchedulingClass", wt.DWORD),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class ContainmentError(Exception):
    pass


class JobObjectContainment:
    """One job per node. Explicit close() — or supervisor-process death — kills the tree
    (KILL_ON_JOB_CLOSE fires when the last handle closes). NOTE: the handle is a raw int
    with no finalizer, so merely dropping this object does NOT close the job; callers must
    use `with` or call close() (spec-audit MINOR: earlier docstring overclaimed GC-kills)."""

    def __init__(self, name: str | None = None) -> None:
        if _KERNEL32 is None:
            raise ContainmentError("Job Objects are Windows-only")
        self._handle = _KERNEL32.CreateJobObjectW(None, name)
        if not self._handle:
            raise ContainmentError(f"CreateJobObject failed (err={ctypes.get_last_error()})")
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = _KERNEL32.SetInformationJobObject(
            self._handle, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info))
        if not ok:
            _KERNEL32.CloseHandle(self._handle)
            raise ContainmentError("SetInformationJobObject(KILL_ON_JOB_CLOSE) failed")
        self._closed = False

    def assign(self, pid: int) -> None:
        """Fail closed: a node process that cannot be assigned must not keep running."""
        if self._closed:
            raise ContainmentError("job already closed")
        process = _KERNEL32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
        if not process:
            raise ContainmentError(f"OpenProcess({pid}) failed — cannot contain, refuse to run")
        try:
            if not _KERNEL32.AssignProcessToJobObject(self._handle, process):
                raise ContainmentError(f"AssignProcessToJobObject({pid}) failed — refuse to run uncontained")
        finally:
            _KERNEL32.CloseHandle(process)

    def close(self) -> None:
        """Kill the entire contained tree (KILL_ON_JOB_CLOSE) and release the job."""
        if not self._closed:
            self._closed = True
            _KERNEL32.CloseHandle(self._handle)

    def __enter__(self) -> "JobObjectContainment":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
