"""
H-12 filesystem watch (R3-9).

Watches the three protected roots with ReadDirectoryChangesW via ctypes for the whole test run.
Any event is a test failure and is listed in evidence/hardening/fs-watch.txt. An empty file with
only the header means no write was observed.

The watcher is deliberately read-only with respect to the watched trees: it opens each root with
FILE_LIST_DIRECTORY and never writes into it.
"""
import ctypes
import os
import threading
import time
from ctypes import wintypes

PROTECTED_ROOTS = [
    r"D:\Product Software",
    r"D:\multi model terminal app",
    r"D:\Sovereign Distillery",
]

# D:\Product Software contains the workspace itself; writes under Production Workspace\ are ours
# and expected. Everything else under that root is protected.
IGNORE_PREFIXES = [
    os.path.normcase(r"Production Workspace"),
]

FILE_LIST_DIRECTORY = 0x0001
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

FILE_NOTIFY_CHANGE_FILE_NAME = 0x00000001
FILE_NOTIFY_CHANGE_DIR_NAME = 0x00000002
FILE_NOTIFY_CHANGE_ATTRIBUTES = 0x00000004
FILE_NOTIFY_CHANGE_SIZE = 0x00000008
FILE_NOTIFY_CHANGE_LAST_WRITE = 0x00000010
FILE_NOTIFY_CHANGE_CREATION = 0x00000040

WATCH_MASK = (FILE_NOTIFY_CHANGE_FILE_NAME | FILE_NOTIFY_CHANGE_DIR_NAME
              | FILE_NOTIFY_CHANGE_ATTRIBUTES | FILE_NOTIFY_CHANGE_SIZE
              | FILE_NOTIFY_CHANGE_LAST_WRITE | FILE_NOTIFY_CHANGE_CREATION)

ACTIONS = {1: "ADDED", 2: "REMOVED", 3: "MODIFIED", 4: "RENAMED_OLD", 5: "RENAMED_NEW"}

# G4-1: a replacement report whose window is under this fraction of the recorded one is refused.
# A single test module observes seconds; the suite observes about a minute.
SHRINK_THRESHOLD = 0.5

INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
k32.CreateFileW.restype = wintypes.HANDLE
k32.ReadDirectoryChangesW.argtypes = [
    wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID, wintypes.LPVOID]
k32.ReadDirectoryChangesW.restype = wintypes.BOOL
k32.CancelIoEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
k32.CancelIoEx.restype = wintypes.BOOL
k32.CloseHandle.argtypes = [wintypes.HANDLE]
k32.CloseHandle.restype = wintypes.BOOL


class FsWatch:
    """Watches the protected roots. Collected events are failures."""

    def __init__(self, roots=None):
        self.roots = roots if roots is not None else PROTECTED_ROOTS
        self.events = []
        self.errors = []
        self._handles = []
        self._threads = []
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.started_utc = None
        self.stopped_utc = None

    def _ignored(self, root: str, rel: str) -> bool:
        if os.path.normcase(root) != os.path.normcase(r"D:\Product Software"):
            return False
        nrel = os.path.normcase(rel)
        return any(nrel == p or nrel.startswith(p + os.sep) for p in IGNORE_PREFIXES)

    def _watch(self, root: str, handle):
        buf = ctypes.create_string_buffer(64 * 1024)
        returned = wintypes.DWORD()
        while not self._stop.is_set():
            ok = k32.ReadDirectoryChangesW(
                handle, buf, ctypes.sizeof(buf), True, WATCH_MASK,
                ctypes.byref(returned), None, None)
            if not ok:
                # CancelIoEx during stop() lands here; that is not an error.
                if not self._stop.is_set():
                    with self._lock:
                        self.errors.append(
                            "{}: ReadDirectoryChangesW failed, err={}".format(
                                root, ctypes.get_last_error()))
                return
            if returned.value == 0:
                continue
            offset = 0
            raw = buf.raw
            while True:
                next_off = int.from_bytes(raw[offset:offset + 4], "little")
                action = int.from_bytes(raw[offset + 4:offset + 8], "little")
                name_len = int.from_bytes(raw[offset + 8:offset + 12], "little")
                name = raw[offset + 12:offset + 12 + name_len].decode("utf-16-le", "replace")
                if not self._ignored(root, name):
                    with self._lock:
                        self.events.append({
                            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "root": root,
                            "action": ACTIONS.get(action, str(action)),
                            "path": name,
                        })
                if next_off == 0:
                    break
                offset += next_off

    def start(self):
        self.started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        for root in self.roots:
            if not os.path.isdir(root):
                with self._lock:
                    self.errors.append("{}: not a directory, not watched".format(root))
                continue
            h = k32.CreateFileW(
                root, FILE_LIST_DIRECTORY,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, None,
                OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, None)
            if not h or h == INVALID_HANDLE_VALUE:
                with self._lock:
                    self.errors.append("{}: CreateFileW failed, err={}".format(
                        root, ctypes.get_last_error()))
                continue
            self._handles.append(h)
            t = threading.Thread(target=self._watch, args=(root, h), daemon=True)
            t.start()
            self._threads.append(t)
        return self

    def stop(self):
        self._stop.set()
        for h in self._handles:
            try:
                k32.CancelIoEx(h, None)
            except Exception:
                pass
        for t in self._threads:
            t.join(timeout=3)
        for h in self._handles:
            try:
                k32.CloseHandle(h)
            except Exception:
                pass
        self._handles = []
        self._threads = []
        self.stopped_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return self.events

    def duration_s(self) -> float:
        """Length of the observed window in seconds, 0 if it never started/stopped."""
        if not (self.started_utc and self.stopped_utc):
            return 0.0
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        try:
            a = time.mktime(time.strptime(self.started_utc, fmt))
            b = time.mktime(time.strptime(self.stopped_utc, fmt))
        except ValueError:
            return 0.0
        return max(0.0, b - a)

    @staticmethod
    def existing_window_s(path: str) -> float:
        """Window length recorded in an existing report, or -1 if there is none to read."""
        if not os.path.isfile(path):
            return -1.0
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.startswith("#"):
                        break
                    if line.startswith("# window:"):
                        raw = line.split(":", 1)[1].strip()
                        start, _, end = raw.partition(" .. ")
                        a = time.mktime(time.strptime(start.strip(), fmt))
                        b = time.mktime(time.strptime(end.strip(), fmt))
                        return max(0.0, b - a)
        except (OSError, ValueError):
            return -1.0
        return -1.0

    def write_report(self, path: str):
        """Write the H-12 artifact, refusing to shrink an existing window (G4-1).

        A single-test run observes a window of seconds; the suite observes a window of a minute.
        Letting the short run overwrite the long one silently destroys the proof — which is
        exactly what happened between the R3 suite run and a later standalone run of this
        module. Returns ("written", reason) or ("refused", reason).
        """
        os.makedirs(os.path.dirname(path), exist_ok=True)
        mine = self.duration_s()
        theirs = self.existing_window_s(path)
        # The threshold discriminates "somebody ran one test module" (a few seconds) from
        # "somebody ran the suite" (about a minute). A normal re-run that happens to be a little
        # faster than the recorded one must still be able to replace it, or the artifact freezes
        # at whichever run was longest and stops describing the current tree.
        if theirs > 0 and mine < theirs * SHRINK_THRESHOLD:
            return ("refused",
                    "existing report covers {:.0f}s, this run covers {:.0f}s (< {:.0%} of it); "
                    "refusing to shrink the window".format(theirs, mine, SHRINK_THRESHOLD))
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("# utc: {}\n".format(self.stopped_utc or self.started_utc))
            f.write("# producer: claude-code REM-01\n")
            f.write("# proof: H-12 - no runtime writes outside Production Workspace\\\n")
            f.write("# watcher: ReadDirectoryChangesW via ctypes, recursive, on each root\n")
            f.write("# window: {} .. {}\n".format(self.started_utc, self.stopped_utc))
            for root in self.roots:
                f.write("# root: {}\n".format(root))
            f.write("# ignored under D:\\Product Software: Production Workspace\\ "
                    "(this workspace's own writes)\n")
            f.write("# events: {}\n".format(len(self.events)))
            if self.errors:
                f.write("# watcher-errors: {}\n".format(len(self.errors)))
                for e in self.errors:
                    f.write("# watcher-error: {}\n".format(e))
            f.write("# window-seconds: {:.0f}\n".format(mine))
            for ev in self.events:
                f.write("{}\t{}\t{}\t{}\n".format(
                    ev["utc"], ev["root"], ev["action"], ev["path"]))
        return ("written", "window {:.0f}s".format(mine))
