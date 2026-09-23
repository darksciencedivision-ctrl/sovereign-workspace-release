"""
SWS Probes — readiness, identity, pre-flight.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import urllib.request
import urllib.error

try:
    from modules.sow.adapters.cmd_shim import assert_cmd_shim_argv_safe
except ImportError:  # direct execution: repository root not on sys.path
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location(
        "cmd_shim", Path(__file__).resolve().parents[2] / "modules/sow/adapters/cmd_shim.py")
    _mod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mod)
    assert_cmd_shim_argv_safe = _mod.assert_cmd_shim_argv_safe


# N-27. How long ONE readiness request may wait for an answer. This is not the poll interval and
# must never be derived from it: `poll_ms` says how often to ask, this says how long an answer may
# take. A health endpoint that reports on downstream services legitimately takes seconds -
# SOVEREIGN's /v1/health answers 200 in ~1.25 s because it reports on the local model service - and
# a probe that hangs up before the answer arrives can never succeed no matter how large timeout_s
# is. Capped so a hung socket cannot consume the whole readiness budget in one attempt.
HTTP_REQUEST_TIMEOUT_CAP_S = 10.0
HTTP_REQUEST_TIMEOUT_FLOOR_S = 0.5


def _request_timeout(deadline: float) -> float:
    """Per-request socket timeout: the remaining readiness budget, capped."""
    remaining = deadline - time.time()
    return max(HTTP_REQUEST_TIMEOUT_FLOOR_S, min(HTTP_REQUEST_TIMEOUT_CAP_S, remaining))


# R23/F-016/F-109. Every probe here targets a loopback service (127.0.0.1 - readiness endpoints,
# the local Ollama). urllib's default opener consults the environment's / Windows registry proxy
# settings, and a configured proxy does NOT auto-bypass dotted loopback like 127.0.0.1 - so a
# probe could be routed through a third-party proxy, leaking identities and health payloads off the
# machine. Build a dedicated opener with an EMPTY ProxyHandler so these requests always go direct.
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _open_direct(req, timeout):
    """urlopen for a loopback probe, guaranteed to bypass any configured proxy (R23/F-016)."""
    return _NO_PROXY_OPENER.open(req, timeout=timeout)


def http_probe(url: str, expect_status: int, timeout_s: int, poll_ms: int) -> tuple[bool, float, str]:
    """Poll an HTTP endpoint until it returns expect_status or timeout."""
    deadline = time.time() + timeout_s
    start = time.time()
    last_error = ""
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, method="GET")
            # CR-013: close the response deterministically so repeated dashboard probes do not
            # retain sockets/handles (http_json_identity already did this; the others did not).
            with _open_direct(req, timeout=_request_timeout(deadline)) as resp:
                status = resp.status
            if status == expect_status:
                return True, time.time() - start, ""
            last_error = f"HTTP {status}"
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}"
        except Exception as e:
            last_error = str(e)
        time.sleep(poll_ms / 1000)
    return False, time.time() - start, last_error


def http_functional_probe(url: str, expect_status: int, require_json: dict,
                           timeout_s: int, poll_ms: int) -> tuple[bool, bool, float, str]:
    """Poll an HTTP JSON health endpoint, separating LIVENESS from functional READINESS.

    SW-13: an endpoint that answers `expect_status` but reports itself not ready - e.g.
    SOVEREIGN's /v1/health returns HTTP 200 with `{"ok": false, "status": "degraded",
    "configured_models_ready": false}` when no model is available - is LIVE but not
    functionally READY. `http_probe` cannot see that difference (it only matches the status
    code), so the shell reached READY for a product that could serve nothing. `require_json`
    maps health-payload keys to the values a functionally-ready product must emit
    (e.g. {"ok": true}); a live answer that fails any pair is degraded, not ready.

    Returns (live, ready, latency, detail):
      - live   : the endpoint answered `expect_status` at least once during the window
      - ready  : a live answer satisfied every require_json pair
      - detail : the payload's own `detail`/reason from the last live-but-degraded answer,
                 else the last transport error - so the tile can say WHY it is degraded.
    Returns as soon as a ready answer is seen; otherwise polls until timeout so a product
    still loading its model has the whole readiness budget to come up.
    """
    deadline = time.time() + timeout_s
    start = time.time()
    live = False
    detail = ""
    last_error = ""
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, method="GET")
            with _open_direct(req, timeout=_request_timeout(deadline)) as resp:
                status = resp.status
                body = resp.read()
            if status == expect_status:
                live = True
                try:
                    data = json.loads(body.decode("utf-8", errors="replace"))
                except ValueError:
                    data = None
                if isinstance(data, dict):
                    unmet = [k for k, v in require_json.items() if data.get(k) != v]
                    if not unmet:
                        return True, True, time.time() - start, ""
                    detail = str(data.get("detail") or "").strip() or (
                        "health requirement not met: " + ", ".join(sorted(unmet)))
                else:
                    detail = "health response is not a JSON object"
            else:
                last_error = f"HTTP {status}"
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}"
        except Exception as e:
            last_error = str(e)
        time.sleep(poll_ms / 1000)
    return live, False, time.time() - start, (detail or last_error)


def http_json_identity(url: str, required_keys: list[str],
                       require: dict | None = None) -> tuple[bool, str]:
    """GET url and verify JSON response has required_keys and optional require values.

    F-034: key presence alone accepts any service that happens to share those keys.
    `require` pins values already emitted by the real product (not a self-named
    service label). Malformed / non-object bodies fail closed.
    """
    try:
        req = urllib.request.Request(url, method="GET")
        resp = _open_direct(req, timeout=5)
        try:
            data = json.loads(resp.read().decode())
        finally:
            try:
                resp.close()
            except Exception:
                pass
        if not isinstance(data, dict):
            return False, "identity response is not a JSON object"
        for key in required_keys:
            if key not in data:
                return False, f"Missing key: {key}"
        if require:
            for key, expected in require.items():
                if data.get(key) != expected:
                    return False, f"identity key {key} mismatch"
        return True, ""
    except Exception as e:
        return False, str(e)


def http_html_identity(url: str, marker: str) -> tuple[bool, str]:
    """GET url and verify response body contains marker string."""
    try:
        req = urllib.request.Request(url, method="GET")
        with _open_direct(req, timeout=5) as resp:  # CR-013: always close the response
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
        with _open_direct(req, timeout=5) as resp:  # CR-013: always close the response
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
            if name == "npm":
                resolved = shutil.which("npm")
                if not resolved:
                    raise FileNotFoundError("npm not found on PATH")
                args = [resolved, "--version"]
                if resolved.lower().endswith((".cmd", ".bat")):
                    assert_cmd_shim_argv_safe(args)
                    args = ["cmd.exe", "/d", "/c", *args]
            r = subprocess.run(args, capture_output=True, text=True, timeout=10)
            # R17/F-019. "The process ran" is not "the tool is present". `py -3.12 --version` on a
            # host without 3.12 exits non-zero with empty stdout; marking that present:True rendered
            # the panel "Python 3.12 available" when it was not. Require a clean exit AND a usable
            # version string, and keep the exit code / stderr in the failure detail.
            version = (r.stdout or "").strip()
            if r.returncode == 0 and version:
                results[name] = {"present": True, "version": version}
            else:
                detail = (r.stderr or "").strip() or version or "no version output"
                results[name] = {
                    "present": False,
                    "error": f"exit {r.returncode}: {detail}",
                }
        except Exception as e:
            results[name] = {"present": False, "error": str(e)}
    return results


def _shell_port() -> int:
    """F-032: the shell's actual listen port, so the port check is not hard-wired to 5180.

    Derived from SWS_SHELL_ORIGIN (set by main() to http://127.0.0.1:<port>), default 5180.
    """
    origin = os.environ.get("SWS_SHELL_ORIGIN", "")
    try:
        return int(origin.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return 5180


def preflight_ports(shell_port: int = None) -> dict:
    """Check whether the module ports and the shell's own port are free."""
    if shell_port is None:
        shell_port = _shell_port()
    results = {}
    for port in [5175, 8700, shell_port]:
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


def resolve_preflight_checks(ollama: dict, toolchain: dict, ports: dict,
                             shell_port: int = None) -> list:
    """Resolve raw probe output into panel-ready checks (THEME-01 D4).

    Semantics are pinned by directive section 4.1: each id gets a definite
    ok|bad status plus a non-empty detail; the shell-port check inverts deliberately
    (occupied means the shell you are talking to - REVIEW-BUILD-06 section 3,
    correction 1). Absent tooling stays a truthful bad with its reason. CR-012: the
    shell port is derived from configuration, not hard-wired.
    """
    if shell_port is None:
        shell_port = _shell_port()
    checks = []
    if ollama.get("reachable"):
        checks.append({"id": "ollama", "status": "ok",
                       "detail": "{} models".format(ollama.get("model_count", 0))})
    else:
        checks.append({"id": "ollama", "status": "bad",
                       "detail": str(ollama.get("error") or "unreachable")})
    for key, cid in (("py-3.12", "py312"), ("node", "node"), ("npm", "npm")):
        entry = toolchain.get(key) or {}
        if entry.get("present"):
            version = str(entry.get("version") or "").strip() or "present"
            checks.append({"id": cid, "status": "ok", "detail": version})
        else:
            reason = str(entry.get("error") or "not found")
            checks.append({"id": cid, "status": "bad", "detail": reason})
    for port in (5175, 8700):
        free = bool((ports.get(str(port)) or {}).get("free"))
        checks.append({"id": "port_{}".format(port),
                       "status": "ok" if free else "bad",
                       "detail": "free" if free else "in use"})
    # CR-012: the shell-port check is derived from the CONFIGURED port, not hard-wired to 5180.
    # The old code looked up ports[str(5180)] and emitted id "port_5180" regardless of the real
    # port, so a custom deployment on 5181 reported "port_5180 ok shell" — approving the wrong
    # endpoint. The id is now the stable, port-agnostic "port_shell" and the configured port is
    # carried in `port` and the detail. Occupied still means "the shell you are talking to" (the
    # inverted status is deliberate — REVIEW-BUILD-06 section 3, correction 1).
    shell_free = bool((ports.get(str(shell_port)) or {}).get("free"))
    checks.append({"id": "port_shell", "port": shell_port,
                   "status": "bad" if shell_free else "ok",
                   "detail": ("free ({})" if shell_free else "shell ({})").format(shell_port)})
    return checks


def run_preflight() -> dict:
    """Run all pre-flight probes and return panel-ready results (THEME-01 D4).

    Statuses are resolved server-side so every PREFLIGHT_ITEMS id resolves to a
    definite status; the frontend consumes the already-supported payload.checks
    array instead of guessing at nested boolean key names.
    """
    # CR-012: resolve the port ONCE and pass it to both the port probe and the check resolver, so
    # the probed target and the reported check are the same configured endpoint.
    shell_port = _shell_port()
    return {
        "checks": resolve_preflight_checks(preflight_ollama(), preflight_toolchain(),
                                           preflight_ports(shell_port), shell_port=shell_port),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
