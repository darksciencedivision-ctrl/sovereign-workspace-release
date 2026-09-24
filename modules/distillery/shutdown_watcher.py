"""SW-18: graceful shutdown on the shell's SWS_SHUTDOWN_EVENT for the Distillery console.

The workspace shell launches serve.py inside a Windows Job Object with CREATE_NO_WINDOW, so a
CTRL_BREAK never reaches it. At Stop the shell first signals a per-module named Event (name passed in
SWS_SHUTDOWN_EVENT) and only force-terminates the job after the grace period. Watching that Event
lets the console stop serving on its own terms. Stdlib only, like serve.py. Mirrors the canonical
shell/src/graceful.py contract (a module cannot import the shell package); the retained suite drives
the real serve.py under the real Job supervisor (tests/remediation/test_sw18b_graceful_owned.py).
"""
from __future__ import annotations

import os
import sys
import threading
from typing import Callable

#: The environment variable the shell supervisor sets to this module's shutdown-event name.
SHUTDOWN_EVENT_ENV = "SWS_SHUTDOWN_EVENT"


def install_shutdown_watcher(on_shutdown: Callable[[], None], *,
                             env: dict | None = None) -> threading.Thread | None:
    """Call ``on_shutdown`` once when the shell signals this module's graceful-shutdown Event.

    Returns the daemon watcher thread, or None when there is nothing to watch (not Windows, or not
    launched by the shell). ``on_shutdown`` runs on the watcher thread and must be safe to call
    from it; if it raises or hangs, the shell's TerminateJobObject fallback still applies after the
    grace period, so adopting the watcher can only improve shutdown, never wedge it.
    """
    if sys.platform != "win32":
        return None
    name = ((env if env is not None else os.environ).get(SHUTDOWN_EVENT_ENV) or "").strip()
    if not name:
        return None

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenEventW.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    synchronize = 0x00100000
    infinite = 0xFFFFFFFF
    wait_object_0 = 0

    handle = kernel32.OpenEventW(synchronize, False, name)
    if not handle:
        return None

    def _wait() -> None:
        try:
            if kernel32.WaitForSingleObject(handle, infinite) == wait_object_0:
                try:
                    on_shutdown()
                except Exception:
                    pass  # the shell's terminate fallback remains the backstop
        finally:
            kernel32.CloseHandle(handle)

    thread = threading.Thread(target=_wait, name="sws-shutdown-watcher", daemon=True)
    thread.start()
    return thread
