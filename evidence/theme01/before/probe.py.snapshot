"""
SWS Probes — readiness, identity, pre-flight.
"""
import json
import os
import socket
import subprocess
import time
import urllib.request
import urllib.error


def http_probe(url: str, expect_status: int, timeout_s: int, poll_ms: int) -> tuple[bool, float, str]:
    """Poll an HTTP endpoint until it returns expect_status or timeout."""
    deadline = time.time() + timeout_s
    start = time.time()
    last_error = ""
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, method="GET")
            resp = urllib.request.urlopen(req, timeout=min(5, poll_ms / 1000))
            if resp.status == expect_status:
                return True, time.time() - start, ""
            last_error = f"HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}"
        except Exception as e:
            last_error = str(e)
        time.sleep(poll_ms / 1000)
    return False, time.time() - start, last_error


def http_json_identity(url: str, required_keys: list[str]) -> tuple[bool, str]:
    """GET url and verify JSON response has required_keys."""
    try:
        req = urllib.request.Request(url, method="GET")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        for key in required_keys:
            if key not in data:
                return False, f"Missing key: {key}"
        return True, ""
    except Exception as e:
        return False, str(e)


def http_html_identity(url: str, marker: str) -> tuple[bool, str]:
    """GET url and verify response body contains marker string."""
    try:
        req = urllib.request.Request(url, method="GET")
        resp = urllib.request.urlopen(req, timeout=5)
        body = resp.read().decode("utf-8", errors="replace")
        if marker in body:
            return True, ""
        return False, f"HTML marker '{marker}' not found"
    except Exception as e:
        return False, str(e)


def process_alive(pid: int) -> bool:
    """Check if a process with given PID is alive."""
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        kernel32.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    except Exception:
        return False


def receipt_file_probe(path: str, timeout_s: int, poll_ms: int,
                       require: dict | None = None,
                       newer_than: float | None = None) -> tuple[bool, float, str]:
    """Poll for a receipt file whose JSON satisfies every key/value in `require`.

    `newer_than` is a wall-clock epoch: a receipt whose mtime predates it is treated as stale
    and ignored. Without this, a receipt left behind by an earlier run satisfies the probe
    instantly and readiness becomes meaningless — the SOW receipt in particular is a committed
    gate artifact that is already on disk before the run starts.
    """
    require = require if require is not None else {"ok": True}
    deadline = time.time() + timeout_s
    start = time.time()
    last = "Timeout waiting for receipt"
    while time.time() < deadline:
        if os.path.isfile(path):
            try:
                if newer_than is not None and os.path.getmtime(path) < newer_than:
                    last = "Receipt is stale (predates launch)"
                else:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    bad = [k for k, v in require.items() if data.get(k) != v]
                    if not bad:
                        return True, time.time() - start, ""
                    last = "Receipt does not satisfy: " + ", ".join(bad)
            except (OSError, ValueError) as e:
                last = str(e)
        time.sleep(poll_ms / 1000)
    return False, time.time() - start, last


def preflight_ollama() -> dict:
    """Probe Ollama at 127.0.0.1:11434."""
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        models = [m.get("name", m.get("model", "")) for m in data.get("models", [])]
        return {"reachable": True, "model_count": len(models), "models": models}
    except Exception as e:
        return {"reachable": False, "error": str(e)}


def preflight_toolchain() -> dict:
    """Check py -3.12, node, npm availability."""
    results = {}
    for name, args in [("py-3.12", ["py", "-3.12", "--version"]),
                        ("node", ["node", "--version"]),
                        ("npm", ["npm", "--version"])]:
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=10)
            results[name] = {"present": True, "version": r.stdout.strip()}
        except Exception as e:
            results[name] = {"present": False, "error": str(e)}
    return results


def preflight_ports() -> dict:
    """Check if ports 5175, 8700, 5180 are free."""
    results = {}
    for port in [5175, 8700, 5180]:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        try:
            s.connect(("127.0.0.1", port))
            results[str(port)] = {"free": False, "occupied": True}
        except (socket.timeout, ConnectionRefusedError, OSError):
            results[str(port)] = {"free": True, "occupied": False}
        finally:
            s.close()
    return results


def run_preflight() -> dict:
    """Run all pre-flight probes and return results."""
    return {
        "ollama": preflight_ollama(),
        "toolchain": preflight_toolchain(),
        "ports": preflight_ports(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }