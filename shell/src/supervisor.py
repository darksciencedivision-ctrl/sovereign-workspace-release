"""
SWS Windows Job Object supervisor — process lifecycle management (HC-11, H-6).

Design notes that matter for H-6:

* Two nested Job Objects. A per-shell job carries JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, so if the
  shell process dies for any reason — including os._exit — every managed process dies with it.
  A per-module job nested inside it allows Stop to terminate exactly one module's whole process
  tree with TerminateJobObject, without touching the others. Nested jobs require Windows 8+.
* JOB_OBJECT_LIMIT_BREAKAWAY_OK and JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK are never set, so a
  child that passes CREATE_BREAKAWAY_FROM_JOB fails to escape.
* Every process is created suspended, assigned to both jobs, then resumed. If assignment fails
  the process is terminated before it ever runs a user instruction, and the caller sees
  JOB_ASSIGN.
* stdout and stderr are captured through an anonymous pipe and pushed into a LogRing, so H-8
  redaction happens before the bytes reach any buffer, response, or file.
* All ctypes entry points declare argtypes/restypes. Without them a HANDLE round-trips through
  a C int and is truncated on 64-bit, which fails silently.
"""
import ctypes
import threading
import time
import uuid
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

# --- constants -------------------------------------------------------------
CREATE_SUSPENDED = 0x00000004
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_UNICODE_ENVIRONMENT = 0x00000400
CREATE_NO_WINDOW = 0x08000000
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x00001000
JobObjectExtendedLimitInformation = 9

CTRL_BREAK_EVENT = 1

STARTF_USESTDHANDLES = 0x00000100
HANDLE_FLAG_INHERIT = 0x00000001
STILL_ACTIVE = 259
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

GENERIC_WRITE = 0x40000000
GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3


# --- structures ------------------------------------------------------------
class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_ulonglong),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", wintypes.LPVOID),
        ("bInheritHandle", wintypes.BOOL),
    ]


# --- prototypes (mandatory: HANDLE is 64-bit) --------------------------------
kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
kernel32.CreateJobObjectW.restype = wintypes.HANDLE
kernel32.SetInformationJobObject.argtypes = [
    wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
kernel32.SetInformationJobObject.restype = wintypes.BOOL
kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
kernel32.IsProcessInJob.argtypes = [
    wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
kernel32.IsProcessInJob.restype = wintypes.BOOL
kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
kernel32.TerminateJobObject.restype = wintypes.BOOL
kernel32.CreateProcessW.argtypes = [
    wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.LPVOID, wintypes.LPVOID,
    wintypes.BOOL, wintypes.DWORD, wintypes.LPVOID, wintypes.LPCWSTR,
    ctypes.POINTER(STARTUPINFOW), ctypes.POINTER(PROCESS_INFORMATION)]
kernel32.CreateProcessW.restype = wintypes.BOOL
kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
kernel32.ResumeThread.restype = wintypes.DWORD
kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
kernel32.TerminateProcess.restype = wintypes.BOOL
kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel32.GetExitCodeProcess.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CreatePipe.argtypes = [
    ctypes.POINTER(wintypes.HANDLE), ctypes.POINTER(wintypes.HANDLE),
    ctypes.POINTER(SECURITY_ATTRIBUTES), wintypes.DWORD]
kernel32.CreatePipe.restype = wintypes.BOOL
kernel32.SetHandleInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
kernel32.SetHandleInformation.restype = wintypes.BOOL
kernel32.ReadFile.argtypes = [
    wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
kernel32.ReadFile.restype = wintypes.BOOL
kernel32.GenerateConsoleCtrlEvent.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.GenerateConsoleCtrlEvent.restype = wintypes.BOOL
# F-011: a per-module named Event is the graceful-shutdown channel. CREATE_NO_WINDOW gives each
# child its own console, so CTRL_BREAK never reaches it; the module instead waits on this event
# (shell/src/graceful.py) and shuts itself down cleanly when the supervisor signals it.
kernel32.CreateEventW.argtypes = [
    wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.SetEvent.argtypes = [wintypes.HANDLE]
kernel32.SetEvent.restype = wintypes.BOOL
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(SECURITY_ATTRIBUTES),
    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class SupervisorError(Exception):
    pass


def query_process_image(pid: int) -> str | None:
    """Full image path of a live process, or None. Used by identity.kind == process_image."""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return None
    finally:
        kernel32.CloseHandle(h)


SW_RESTORE = 9
SW_SHOW = 5

_ENUM_WINDOWS_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _top_level_windows_for(pids: set) -> list:
    """Visible, titled, top-level windows owned by any pid in `pids`, outermost first.

    Electron splits a running app across a main process and several children, and the window
    does not reliably belong to the pid the shell spawned. Matching a SET of pids - in practice
    every pid in the module's Job Object - is what makes this work for a real desktop app.
    """
    found = []

    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindow(hwnd, 4) != 0:  # GW_OWNER: skip owned tool/dialog windows
            return True
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        owner = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value in pids:
            found.append(hwnd)
        return True

    user32.EnumWindows(_ENUM_WINDOWS_PROC(_cb), 0)
    return found


JobObjectBasicProcessIdList = 3


class JOBOBJECT_BASIC_PROCESS_ID_LIST(ctypes.Structure):
    _fields_ = [
        ("NumberOfAssignedProcesses", wintypes.DWORD),
        ("NumberOfProcessIdsInList", wintypes.DWORD),
        ("ProcessIdList", ctypes.c_size_t * 512),
    ]


def job_pids(job_handle) -> set:
    """Every pid currently assigned to `job_handle`.

    A module is a process TREE - Electron alone is a main process plus renderer, GPU and utility
    children - and the window belongs to whichever of them created it. The Job Object already
    defines the tree the shell owns (H-9), so it is also the correct answer to "which processes
    may I raise a window for": nothing outside the job is ever touched.
    """
    if not job_handle:
        return set()
    info = JOBOBJECT_BASIC_PROCESS_ID_LIST()
    size = ctypes.sizeof(info)
    ok = kernel32.QueryInformationJobObject(
        job_handle, JobObjectBasicProcessIdList, ctypes.byref(info), size, None)
    if not ok:
        return set()
    count = min(info.NumberOfProcessIdsInList, 512)
    return {int(info.ProcessIdList[i]) for i in range(count)}


def focus_window_for_pids(pids: set) -> tuple:
    """Raise and focus a top-level window owned by one of `pids`.

    Returns (ok, detail). The detail is reported to the operator verbatim, so a failure says what
    actually happened rather than leaving a control that silently does nothing (S-17).
    """
    if not pids:
        return False, "module is not running"
    windows = _top_level_windows_for(pids)
    if not windows:
        return False, "the module is running but owns no visible top-level window yet"
    hwnd = windows[0]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    else:
        user32.ShowWindow(hwnd, SW_SHOW)
    user32.BringWindowToTop(hwnd)
    raised = bool(user32.SetForegroundWindow(hwnd))
    if raised:
        return True, "window raised"
    # Windows refuses SetForegroundWindow to a process that does not own the foreground window.
    # The window HAS been restored and brought to the top of the Z-order, which is the visible
    # part; say so plainly instead of claiming a focus that did not happen.
    return True, "window restored and brought to front (foreground focus refused by Windows)"


def _quote(arg: str) -> str:
    """Windows command-line quoting (subprocess.list2cmdline, inlined to keep imports minimal)."""
    if arg and not any(c in arg for c in ' \t\n\v"'):
        return arg
    out = ['"']
    backslashes = 0
    for c in arg:
        if c == "\\":
            backslashes += 1
            continue
        if c == '"':
            out.append("\\" * (backslashes * 2 + 1))
            out.append('"')
        else:
            out.append("\\" * backslashes)
            out.append(c)
        backslashes = 0
    out.append("\\" * backslashes * 2)
    out.append('"')
    return "".join(out)


def build_cmdline(argv: list) -> str:
    return " ".join(_quote(str(a)) for a in argv)


class ProcessHandle:
    """Wraps a Windows process handle, its PID, and its per-module Job."""

    def __init__(self, h_process, h_thread, pid: int, job_handle, module_id: str,
                 shutdown_event=None, shutdown_event_name: str | None = None):
        self.h_process = h_process
        self.h_thread = h_thread
        self.pid = pid
        self.job_handle = job_handle
        self.module_id = module_id
        # F-011: the module's graceful-shutdown Event (parent handle) and its name, or None.
        self.shutdown_event = shutdown_event
        self.shutdown_event_name = shutdown_event_name
        self._exit_code = None
        self.started = time.time()

    def is_alive(self) -> bool:
        if self._exit_code is not None:
            return False
        code = wintypes.DWORD()
        if kernel32.GetExitCodeProcess(self.h_process, ctypes.byref(code)):
            if code.value == STILL_ACTIVE:
                return True
            self._exit_code = code.value
            return False
        return False

    @property
    def exit_code(self):
        if self._exit_code is not None:
            return self._exit_code
        code = wintypes.DWORD()
        if kernel32.GetExitCodeProcess(self.h_process, ctypes.byref(code)):
            if code.value != STILL_ACTIVE:
                self._exit_code = code.value
                return self._exit_code
        return None

    def in_job(self, job_handle=None) -> bool:
        """IsProcessInJob against this process's own job (H-6 breakaway assertion)."""
        result = wintypes.BOOL()
        job = job_handle if job_handle is not None else self.job_handle
        if not kernel32.IsProcessInJob(self.h_process, job, ctypes.byref(result)):
            return False
        return bool(result.value)


def pid_in_job(pid: int, job_handle) -> bool:
    """IsProcessInJob for an arbitrary PID — used to assert a grandchild failed to break away."""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    try:
        result = wintypes.BOOL()
        if not kernel32.IsProcessInJob(h, job_handle, ctypes.byref(result)):
            return False
        return bool(result.value)
    finally:
        kernel32.CloseHandle(h)


def _make_job(kill_on_close: bool):
    h = kernel32.CreateJobObjectW(None, None)
    if not h:
        raise SupervisorError(f"CreateJobObject failed: {ctypes.get_last_error()}")
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    # BREAKAWAY_OK and SILENT_BREAKAWAY_OK are deliberately left clear (H-6).
    info.BasicLimitInformation.LimitFlags = (
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE if kill_on_close else 0)
    ok = kernel32.SetInformationJobObject(
        h, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info))
    if not ok:
        err = ctypes.get_last_error()
        kernel32.CloseHandle(h)
        raise SupervisorError(f"SetInformationJobObject failed: {err}")
    return h


class JobSupervisor:
    """Manages processes under nested Windows Job Objects."""

    def __init__(self, max_processes: int = 4):
        self._shell_job = _make_job(kill_on_close=True)
        self._processes: dict = {}
        self._readers: dict = {}
        self._lock = threading.RLock()
        self._max_processes = max_processes
        self._closed = False

    # -- properties ---------------------------------------------------------
    @property
    def shell_job(self):
        return self._shell_job

    @property
    def process_count(self) -> int:
        with self._lock:
            return len(self._processes)

    def get_process(self, module_id: str):
        return self._processes.get(module_id)

    def get_pids(self) -> dict:
        return {k: v.pid for k, v in self._processes.items()}

    # -- spawn --------------------------------------------------------------
    def spawn(self, module_id: str, argv: list, cwd: str, env: dict, log_ring=None):
        """Create suspended, assign to both jobs, resume. Raises SupervisorError on failure."""
        with self._lock:
            # F-014. Refuse to spawn over a module that already has a LIVE managed process.
            # `self._processes[module_id] = ph` used to silently replace an existing handle, so the
            # previous process (and its job handle) became unreachable by stop()/Open -- it kept
            # running untracked, still holding the module's port, until shell exit. This is
            # reachable via a poll/Start race (F-013) or a start whose readiness failed after spawn;
            # a live entry now blocks the second spawn instead of orphaning the first.
            existing = self._processes.get(module_id)
            if existing is not None and existing.is_alive():
                raise SupervisorError(
                    f"module {module_id!r} already has a live managed process "
                    f"(pid {existing.pid}); stop it before spawning again")
            if len(self._processes) >= self._max_processes:
                raise SupervisorError(
                    f"Max {self._max_processes} managed processes reached (H-7)")

            module_job = _make_job(kill_on_close=True)
            sa = SECURITY_ATTRIBUTES()
            sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
            sa.lpSecurityDescriptor = None
            sa.bInheritHandle = True

            read_h = wintypes.HANDLE()
            write_h = wintypes.HANDLE()
            if log_ring is not None:
                if not kernel32.CreatePipe(ctypes.byref(read_h), ctypes.byref(write_h),
                                           ctypes.byref(sa), 0):
                    kernel32.CloseHandle(module_job)
                    raise SupervisorError(f"CreatePipe failed: {ctypes.get_last_error()}")
                # The parent's read end must not be inherited by the child.
                kernel32.SetHandleInformation(read_h, HANDLE_FLAG_INHERIT, 0)
            else:
                # No consumer for the output. Give the child NUL rather than a pipe whose read
                # end we immediately close: that would break the child's first write, killing a
                # process the caller expects to be running.
                write_h = wintypes.HANDLE(kernel32.CreateFileW(
                    "NUL", GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                    ctypes.byref(sa), OPEN_EXISTING, 0, None))
                if not write_h or write_h.value == INVALID_HANDLE_VALUE:
                    kernel32.CloseHandle(module_job)
                    raise SupervisorError(
                        f"CreateFileW(NUL) failed: {ctypes.get_last_error()}")

            # Give the child NUL for stdin rather than the shell's own stdin.
            nul = kernel32.CreateFileW("NUL", GENERIC_READ,
                                       FILE_SHARE_READ | FILE_SHARE_WRITE,
                                       ctypes.byref(sa), OPEN_EXISTING, 0, None)

            si = STARTUPINFOW()
            si.cb = ctypes.sizeof(STARTUPINFOW)
            si.dwFlags = STARTF_USESTDHANDLES
            si.hStdInput = nul if nul != INVALID_HANDLE_VALUE else None
            si.hStdOutput = write_h
            si.hStdError = write_h

            pi = PROCESS_INFORMATION()
            cmdline = ctypes.create_unicode_buffer(build_cmdline(argv))

            # CREATE_UNICODE_ENVIRONMENT is required because the block below is UTF-16.
            # CREATE_NEW_PROCESS_GROUP makes GenerateConsoleCtrlEvent addressable.
            flags = (CREATE_SUSPENDED | CREATE_NEW_PROCESS_GROUP
                     | CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW)

            # F-011: create the per-module graceful-shutdown Event (manual-reset, unsignalled) and
            # pass its name to the child in SWS_SHUTDOWN_EVENT. A module that installs the watcher
            # (shell/src/graceful.py) shuts itself down cleanly when Stop signals this, before the
            # CTRL_BREAK -> TerminateJobObject fallback. Adding the variable is harmless for a module
            # that does not adopt the watcher. `Local\` scopes the name to this logon session, which
            # the child (same user, same session) can open by name.
            safe_id = "".join(c for c in str(module_id) if c.isalnum() or c in "._-") or "module"
            evt_name = f"Local\\SWS_SHUTDOWN_{safe_id}_{uuid.uuid4().hex}"
            h_event = kernel32.CreateEventW(None, True, False, evt_name)
            child_env = dict(env)
            if h_event:
                child_env["SWS_SHUTDOWN_EVENT"] = evt_name
            else:
                evt_name = None

            block = "".join(f"{k}={v}\0" for k, v in child_env.items()) + "\0"
            env_buf = ctypes.create_unicode_buffer(block)

            ok = kernel32.CreateProcessW(
                None, cmdline, None, None, True, flags,
                ctypes.byref(env_buf), cwd, ctypes.byref(si), ctypes.byref(pi))

            kernel32.CloseHandle(write_h)
            if nul and nul != INVALID_HANDLE_VALUE:
                kernel32.CloseHandle(nul)

            if not ok:
                err = ctypes.get_last_error()
                if log_ring is not None:
                    kernel32.CloseHandle(read_h)
                kernel32.CloseHandle(module_job)
                if h_event:
                    kernel32.CloseHandle(h_event)
                raise SupervisorError(f"CreateProcess failed: {err}")

            # Assignment ORDER is load-bearing. Each assignment nests the new job INSIDE the
            # process's current job, so the outermost job must be assigned first. Assigning the
            # per-module job first would make the shared shell job a child of module job #1, and
            # the second module's spawn would then fail with ERROR_ACCESS_DENIED because a job
            # cannot have two parents. Shell job first, module job second: one shell job with
            # many sibling module jobs nested inside it.
            if not kernel32.AssignProcessToJobObject(self._shell_job, pi.hProcess):
                err = ctypes.get_last_error()
                kernel32.TerminateProcess(pi.hProcess, 1)
                kernel32.CloseHandle(pi.hProcess)
                kernel32.CloseHandle(pi.hThread)
                if log_ring is not None:
                    kernel32.CloseHandle(read_h)
                kernel32.CloseHandle(module_job)
                if h_event:
                    kernel32.CloseHandle(h_event)
                raise SupervisorError(f"AssignProcessToJobObject (shell) failed: {err} (JOB_ASSIGN)")
            if not kernel32.AssignProcessToJobObject(module_job, pi.hProcess):
                err = ctypes.get_last_error()
                kernel32.TerminateProcess(pi.hProcess, 1)
                kernel32.CloseHandle(pi.hProcess)
                kernel32.CloseHandle(pi.hThread)
                if log_ring is not None:
                    kernel32.CloseHandle(read_h)
                kernel32.CloseHandle(module_job)
                if h_event:
                    kernel32.CloseHandle(h_event)
                raise SupervisorError(f"AssignProcessToJobObject failed: {err} (JOB_ASSIGN)")

            kernel32.ResumeThread(pi.hThread)

            ph = ProcessHandle(pi.hProcess, pi.hThread, pi.dwProcessId, module_job, module_id,
                               shutdown_event=(h_event or None), shutdown_event_name=evt_name)
            self._processes[module_id] = ph

            if log_ring is not None:
                t = threading.Thread(target=self._pump, args=(read_h, log_ring), daemon=True)
                self._readers[module_id] = (t, read_h)
                t.start()
            return ph

    @staticmethod
    def _pump(read_h, log_ring):
        """Drain the child's pipe into the LogRing. Redaction happens inside LogRing.write."""
        buf = ctypes.create_string_buffer(8192)
        n = wintypes.DWORD()
        try:
            while True:
                if not kernel32.ReadFile(read_h, buf, 8192, ctypes.byref(n), None):
                    break
                if n.value == 0:
                    break
                try:
                    log_ring.write(buf.raw[:n.value])
                except Exception:
                    break
        finally:
            # R14: the stream ended; emit any partial final line held in the carry (redacted),
            # so a last line without a trailing newline is neither dropped nor left un-redacted.
            try:
                log_ring.flush()
            except Exception:
                pass
            kernel32.CloseHandle(read_h)

    # -- stop ---------------------------------------------------------------
    def stop(self, module_id: str, grace_s: int = 10):
        """Graceful shutdown signal, then grace_s, then TerminateJobObject on the module's own job.

        F-011: the graceful nudge is now TWO signals, because a CREATE_NO_WINDOW child never
        receives CTRL_BREAK (its console is not the shell's). First SetEvent on the module's
        shutdown Event, which a module that installed the watcher (shell/src/graceful.py) uses to
        close cleanly — flushing its database before exit; CTRL_BREAK is kept as a harmless second
        nudge for any console child. Only if the process is still alive after grace_s does
        TerminateJobObject fire (it, not TerminateProcess, is what kills grandchildren — H-6).

        Returns an observable record so a caller can see whether the module exited on its own
        (`graceful`) or had to be force-terminated (`forced`), and how long it waited — the "grace
        expired is an observable event" half of the fix. Existing callers ignore the return.
        """
        started = time.time()
        with self._lock:
            ph = self._processes.get(module_id)
            if not ph:
                return {"module_id": module_id, "found": False, "graceful": False,
                        "forced": False, "waited_ms": 0, "exit_code": None}
            if not ph.is_alive():
                record = {"module_id": module_id, "found": True, "graceful": True,
                          "forced": False, "waited_ms": 0, "exit_code": ph.exit_code}
                self._cleanup(module_id, ph)
                return record
            if ph.shutdown_event:
                kernel32.SetEvent(ph.shutdown_event)
            kernel32.GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, ph.pid)

        deadline = time.time() + max(0, grace_s)
        graceful = False
        while time.time() < deadline:
            if not ph.is_alive():
                graceful = True
                break
            time.sleep(0.05)

        forced = False
        with self._lock:
            if not graceful:
                # Grace expired: the module did not stop itself. Force the whole tree down.
                kernel32.TerminateJobObject(ph.job_handle, 1)
                forced = True
                deadline = time.time() + 2
                while time.time() < deadline and ph.is_alive():
                    time.sleep(0.02)
            exit_code = ph.exit_code
            reader = self._readers.get(module_id)
            self._cleanup(module_id, ph)

        # Drain the pipe before returning. Once every writer handle is closed the pump sees EOF
        # and exits; joining here means a caller that reads the LogRing immediately after stop()
        # sees the child's final output rather than a truncated tail.
        if reader is not None:
            reader[0].join(timeout=5)

        return {"module_id": module_id, "found": True, "graceful": graceful, "forced": forced,
                "waited_ms": int((time.time() - started) * 1000), "exit_code": exit_code}

    def stop_all(self):
        with self._lock:
            for module_id, ph in list(self._processes.items()):
                kernel32.TerminateJobObject(ph.job_handle, 1)
                self._cleanup(module_id, ph)
            self._processes.clear()

    def _cleanup(self, module_id: str, ph):
        for h in (ph.h_process, ph.h_thread, ph.job_handle, ph.shutdown_event):
            if not h:
                continue
            try:
                kernel32.CloseHandle(h)
            except Exception:
                pass
        self._processes.pop(module_id, None)
        self._readers.pop(module_id, None)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.stop_all()
        try:
            kernel32.CloseHandle(self._shell_job)
        except Exception:
            pass
