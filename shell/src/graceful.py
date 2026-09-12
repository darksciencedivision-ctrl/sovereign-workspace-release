"""Cross-process graceful-shutdown channel (F-011).

The supervisor spawns modules with CREATE_NO_WINDOW, so each child has its own hidden console and a
CTRL_BREAK from the shell reaches nothing — Stop therefore waited out the grace period and then
hard-killed the process tree with TerminateJobObject, which risks a torn write for the SQLite/WAL
writers (SOVEREIGN, Token Center) and Electron's recovery files.

This is the module side of the fix. The supervisor creates a per-module named Windows Event, passes
its name to the child in ``SWS_SHUTDOWN_EVENT``, and signals it at Stop BEFORE the CTRL_BREAK ->
TerminateJobObject fallback. A module calls :func:`install_shutdown_watcher` once at startup with a
callback that performs a clean shutdown (stop the HTTP server, flush and close the database); the
watcher fires that callback when the event is signalled, so the module exits on its own terms within
the grace window. If it does not, the supervisor's terminate fallback still fires — so adopting the
watcher can only improve shutdown, never wedge it.

POSIX has no named-event channel here and no CREATE_NO_WINDOW problem; the helper is a no-op there.
"""
from __future__ import annotations

import os
import sys
import threading
from typing import Callable

#: The environment variable the supervisor sets to the module's shutdown-event name.
SHUTDOWN_EVENT_ENV = "SWS_SHUTDOWN_EVENT"


def shutdown_event_name(env: dict | None = None) -> str | None:
    """The shutdown-event name the supervisor passed, or None when not launched by it."""
    name = (env if env is not None else os.environ).get(SHUTDOWN_EVENT_ENV, "")
    name = name.strip()
    return name or None


def install_shutdown_watcher(on_shutdown: Callable[[], None], *, event_name: str | None = None,
                             env: dict | None = None) -> threading.Thread | None:
    """Watch the supervisor's shutdown event and call ``on_shutdown`` once when it is signalled.

    Returns the daemon watcher thread, or None when there is nothing to watch (POSIX, or a process
    the supervisor did not launch with a shutdown event). ``on_shutdown`` runs on the watcher thread,
    so it must be safe to call from a thread other than the main one and should be idempotent — the
    supervisor may also CTRL_BREAK and, past the grace window, terminate.
    """
    if sys.platform != "win32":
        return None
    name = event_name or shutdown_event_name(env)
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

    SYNCHRONIZE = 0x00100000
    INFINITE = 0xFFFFFFFF
    WAIT_OBJECT_0 = 0

    handle = kernel32.OpenEventW(SYNCHRONIZE, False, name)
    if not handle:
        return None

    def _wait() -> None:
        try:
            if kernel32.WaitForSingleObject(handle, INFINITE) == WAIT_OBJECT_0:
                try:
                    on_shutdown()
                except Exception:
                    # A shutdown callback that raises must not crash the watcher thread; the
                    # supervisor's terminate fallback remains the backstop.
                    pass
        finally:
            kernel32.CloseHandle(handle)

    thread = threading.Thread(target=_wait, name="sws-shutdown-watcher", daemon=True)
    thread.start()
    return thread
