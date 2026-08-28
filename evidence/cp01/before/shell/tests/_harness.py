"""
Shared test harness (R3-1).

start_shell() picks a free loopback port, launches `py -3.12 -m shell.src --port <p>` as a
subprocess, polls until the API answers, and returns (proc, port, csrf_nonce). No test may assume
port 5180.
"""
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

# The shell is polled on /api/shell-info. REM-01 R3-1 names "/api/shell", which does not exist in
# this build; adding it would be a new endpoint and is forbidden by directive section 0.1(7).
READY_PATH = "/api/shell-info"


def free_port() -> int:
    """Ask the OS for an unused loopback port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def python_exe() -> str:
    """Absolute path to the running interpreter — used as fixture argv[0]."""
    return os.path.realpath(sys.executable)


def _child_env() -> dict:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def start_shell(timeout_s: float = 10.0):
    """Launch a shell instance on an ephemeral port. Returns (proc, port, csrf_nonce)."""
    port = free_port()
    proc = subprocess.Popen(
        [python_exe(), "-B", "-m", "shell.src", "--port", str(port)],
        cwd=WORKSPACE, env=_child_env(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    base = "http://127.0.0.1:{}".format(port)
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read() if proc.stdout else ""
            raise RuntimeError(
                "shell exited during startup with code {}:\n{}".format(proc.returncode, out))
        try:
            with urllib.request.urlopen(base + READY_PATH, timeout=1) as resp:
                if resp.status == 200:
                    break
        except (urllib.error.URLError, OSError) as e:
            last = e
        time.sleep(0.1)
    else:
        stop_shell(proc)
        raise RuntimeError("shell did not become ready within {}s: {}".format(timeout_s, last))

    nonce = ""
    try:
        with urllib.request.urlopen(base + "/", timeout=5) as resp:
            html = resp.read().decode("utf-8", "replace")
        m = re.search(r'<meta name="csrf-nonce" content="([^"]+)"', html)
        if m:
            nonce = m.group(1)
    except (urllib.error.URLError, OSError):
        pass
    return proc, port, nonce


def stop_shell(proc, timeout_s: float = 10.0):
    """Terminate the shell subprocess, wait for it, and close its pipes.

    Closing the pipes matters for evidence, not just tidiness: an unclosed stream emits a
    ResourceWarning at interpreter shutdown, which lands AFTER unittest's trailing "OK" and
    would leave evidence/test-run.txt not ending in OK (R3-12).
    """
    if proc is None:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=timeout_s)
    finally:
        for stream in (proc.stdout, proc.stderr, proc.stdin):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass


def request(port: int, path: str, method: str = "GET", body=None, nonce: str = "",
            headers: dict | None = None, timeout: float = 10.0):
    """Issue a request to the shell. Returns (status, headers, text). Never raises on 4xx/5xx."""
    import json as _json
    base = "http://127.0.0.1:{}".format(port)
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = _json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
        hdrs.setdefault("Origin", "http://127.0.0.1:{}".format(port))
        if nonce:
            hdrs.setdefault("X-CSRF-Nonce", nonce)
    req = urllib.request.Request(base + path, data=data, method=method)
    for k, v in hdrs.items():
        if v is not None:
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")


def fixture(name: str) -> str:
    return os.path.join(FIXTURES, name)


def wait_until(pred, timeout_s: float, step_s: float = 0.1) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(step_s)
    return pred()


def pid_alive(pid: int) -> bool:
    """True while the PID names a live process."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k32.GetExitCodeProcess.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = wintypes.DWORD()
        if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
            return False
        return code.value == 259  # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)
