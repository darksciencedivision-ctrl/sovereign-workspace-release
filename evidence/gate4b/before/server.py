"""
SWS Shell Server — main entry point (SWS-UI-001 v1.2).

    py -3.12 -m shell.src [--port 5180] [--selftest]

--selftest is a proof hook for H-11, not a feature: it serves exactly one request to /, asserts
that no loaded module came from site-packages, prints the result and exits. It adds no HTTP
endpoint.
"""
import argparse
import json
import os
import sys
import time
import threading
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

from shell.src.adapter import load_all_adapters
from shell.src.supervisor import JobSupervisor
from shell.src.logring import LogRing
from shell.src.csrf import get_csrf
from shell.src.probe import run_preflight
from shell.src.distillery import get_distillery_status
from shell.src.startup_test import run_startup_test
from shell.src.states import ModuleRunner, EXTERNAL, READY, DEGRADED, STARTING

MAX_BODY = 16384
START_RATE_LIMIT_S = 2.0  # H-7: one Start per module per 2 s

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; "
       "connect-src 'self'; img-src 'self' data:; "
       "frame-ancestors 'none'; object-src 'none'; base-uri 'none'")


class ShellAPIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the SWS shell."""

    supervisor: JobSupervisor = None
    adapters: dict = {}
    states: dict = {}
    log_rings: dict = {}
    csrf = get_csrf()
    server_start = time.time()
    lock = threading.RLock()
    selftest = False
    selftest_served = threading.Event()

    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # Suppress default logging

    # -- response helpers ---------------------------------------------------
    def _common_headers(self):
        # H-3. No Access-Control-* header is emitted anywhere: the shell is same-origin only.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._common_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message: str, status: int = 400):
        self._send_json({"error": message}, status)

    # -- H-2 ----------------------------------------------------------------
    def _expected_origin(self):
        port = self.server.server_port
        return f"127.0.0.1:{port}", f"http://127.0.0.1:{port}"

    def _validate_state_changing_request(self):
        """H-2. Returns None when valid, else (status, message). Runs BEFORE the body is read.

        Host and Origin must both be PRESENT and EXACTLY equal to the shell origin. localhost is
        not accepted as an alternate spelling; a missing header is a rejection, not a pass.
        """
        host_expected, origin_expected = self._expected_origin()

        host = self.headers.get("Host")
        if host is None:
            return 403, "Host header required"
        if host != host_expected:
            return 403, "Host does not match shell origin"

        origin = self.headers.get("Origin")
        if origin is None:
            return 403, "Origin header required"
        if origin != origin_expected:
            return 403, "Origin does not match shell origin"

        ctype = self.headers.get("Content-Type")
        if ctype != "application/json":
            return 400, "Content-Type must be application/json"

        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            return 400, "Content-Length required"
        try:
            length = int(raw_len)
        except ValueError:
            return 400, "Content-Length must be an integer"
        if length < 0:
            return 400, "Content-Length must be non-negative"
        if length > MAX_BODY:
            return 400, f"Content-Length exceeds {MAX_BODY}"

        if not self.csrf.validate(self.headers.get("X-CSRF-Nonce", "")):
            return 403, "Invalid CSRF nonce"
        return None

    def _read_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    # -- verbs --------------------------------------------------------------
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._serve_index()
            if self.selftest:
                self.selftest_served.set()
        elif path.startswith("/static/"):
            self._serve_static(path)
        elif path == "/api/state":
            self._handle_get_state()
        elif path == "/api/preflight":
            self._send_json(run_preflight())
        elif path == "/api/distillery":
            self._send_json(get_distillery_status())
        elif path == "/api/shell-info":
            self._handle_get_shell_info()
        elif path.startswith("/api/logs/"):
            self._handle_get_logs(path.split("/api/logs/", 1)[1])
        else:
            self._send_error("Not found", 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        bad = self._validate_state_changing_request()
        if bad:
            status, message = bad
            self._send_error(message, status)
            return

        body = self._read_body()
        if body is None or not isinstance(body, dict):
            self._send_error("Invalid request body", 400)
            return

        if path == "/api/start":
            self._handle_start(body)
        elif path == "/api/stop":
            self._handle_stop(body)
        elif path == "/api/restart":
            self._handle_restart(body)
        elif path == "/api/startup-test":
            self._handle_startup_test(body)
        else:
            self._send_error("Not found", 404)

    def do_PUT(self):
        self._reject_non_get()

    def do_DELETE(self):
        self._reject_non_get()

    def do_PATCH(self):
        self._reject_non_get()

    def do_OPTIONS(self):
        # No CORS preflight is supported; the shell is same-origin only (H-2, N-4).
        self._reject_non_get()

    def _reject_non_get(self):
        bad = self._validate_state_changing_request()
        if bad:
            status, message = bad
            self._send_error(message, status)
            return
        self._send_error("Method not allowed", 405)

    # -- GET handlers -------------------------------------------------------
    def _serve_index(self):
        index_path = os.path.join(os.path.dirname(__file__), "..", "static", "index.html")
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                html = f.read()
            body = html.replace("NONCE_PLACEHOLDER", self.csrf.nonce).encode("utf-8")
        except OSError:
            self._send_error("Index not found", 500)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._common_headers()
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path: str):
        safe = path.replace("\\", "/").lstrip("/")
        if ".." in safe:
            self._send_error("Forbidden", 403)
            return
        file_path = os.path.join(os.path.dirname(__file__), "..", safe)
        if not os.path.isfile(file_path):
            self._send_error("Not found", 404)
            return
        try:
            with open(file_path, "rb") as f:
                content = f.read()
        except OSError:
            self._send_error("Not found", 404)
            return
        ctype = ("text/css" if path.endswith(".css")
                 else "application/javascript" if path.endswith(".js")
                 else "image/svg+xml" if path.endswith(".svg")
                 else "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self._common_headers()
        self.end_headers()
        self.wfile.write(content)

    def _handle_get_state(self):
        with self.lock:
            states = {mid: r.to_dict() for mid, r in self.states.items()}
        self._send_json({"modules": states})

    def _handle_get_shell_info(self):
        self._send_json({
            "version": "SWS-UI-001 v1.2",
            "build_id": "2026-08-21",
            "host": os.environ.get("COMPUTERNAME", "unknown"),
            "clock": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "uptime_s": int(time.time() - self.server_start),
        })

    def _handle_get_logs(self, module_id: str):
        ring = self.log_rings.get(module_id)
        self._send_json({"logs": ring.read() if ring else "", "module_id": module_id})

    # -- POST handlers ------------------------------------------------------
    def _runner(self, body):
        module_id = body.get("id", "")
        if not module_id or module_id not in self.states:
            return None, None
        return module_id, self.states[module_id]

    def _handle_start(self, body: dict):
        module_id, runner = self._runner(body)
        if runner is None:
            self._send_error("Unknown module", 400)
            return

        # H-7 is checked BEFORE the state check. A second Start gesture inside the window is
        # rate-limited as such; reporting "cannot start from state STARTING" instead would hide
        # the rate limit behind a race with the first Start's own transition.
        with self.lock:
            elapsed = time.time() - runner.last_start
            if elapsed < START_RATE_LIMIT_S:
                self._send_error(
                    f"Rate limited: {START_RATE_LIMIT_S - elapsed:.1f}s remaining", 429)
                return

        allowed, status, message = runner.can_start()
        if not allowed:
            self._send_error(message, status)
            return

        with self.lock:
            runner.last_start = time.time()

        threading.Thread(target=self._start_worker, args=(runner,), daemon=True).start()
        self._send_json({"status": "accepted", "id": module_id})

    @staticmethod
    def _start_worker(runner):
        try:
            runner.start()
        except Exception as e:  # noqa: BLE001 - a runner failure must not kill the thread quietly
            runner._set("FAILED", f"SPAWN: {e}")

    def _handle_stop(self, body: dict):
        module_id, runner = self._runner(body)
        if runner is None:
            self._send_error("Unknown module", 400)
            return
        if runner.state == STARTING:
            runner.cancel()
        else:
            runner.stop()
        self._send_json({"status": "stopped", "id": module_id, "state": runner.display})

    def _handle_restart(self, body: dict):
        module_id, runner = self._runner(body)
        if runner is None:
            self._send_error("Unknown module", 400)
            return
        if runner.state in (READY, STARTING, DEGRADED):
            runner.stop()
        runner.last_start = 0.0  # a restart is one operator gesture, not two Starts
        self._handle_start(body)

    def _handle_startup_test(self, body: dict):
        module_id, runner = self._runner(body)
        if runner is None:
            self._send_error("Unknown module", 400)
            return
        adapter = runner.adapter
        if adapter.get("state_class") == "not_started":
            self._send_error("Startup test not applicable for this module", 400)
            return
        if "error" in adapter:
            self._send_error(f"Adapter error: {adapter['reason']}", 400)
            return

        if runner.state in (READY, STARTING, DEGRADED):
            runner.stop()

        ring = self.log_rings.get(module_id)
        if ring is None:
            ring = LogRing()
            self.log_rings[module_id] = ring
        ring.clear()

        result = run_startup_test(module_id, adapter, self.supervisor, ring,
                                  bool(body.get("keep", False)), runner=runner)
        self._send_json(result)


def _poll_loop(interval: float = 5.0):
    """READY/DEGRADED every 5 s, everything else every 30 s (§7.7 idle-CPU budget)."""
    tick = 0
    while True:
        time.sleep(interval)
        tick += 1
        with ShellAPIHandler.lock:
            runners = list(ShellAPIHandler.states.values())
        for runner in runners:
            if runner.state in (READY, DEGRADED):
                pass
            elif tick % 6 != 0:
                continue
            try:
                runner.poll()
            except Exception:
                pass


def _run_selftest(port: int) -> int:
    """H-11 proof hook. Serve exactly one request to /, check sys.modules, exit."""
    adapters = load_all_adapters()
    ShellAPIHandler.supervisor = JobSupervisor()
    ShellAPIHandler.adapters = adapters
    ShellAPIHandler.states = {
        mid: ModuleRunner(mid, a, ShellAPIHandler.supervisor) for mid, a in adapters.items()}
    ShellAPIHandler.log_rings = {}
    ShellAPIHandler.selftest = True
    ShellAPIHandler.selftest_served.clear()

    server = ThreadingHTTPServer(("127.0.0.1", port), ShellAPIHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"SELFTEST: listening on http://127.0.0.1:{server.server_port}")

    import urllib.request
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/", timeout=10) as resp:
            served_status = resp.status
            served_bytes = len(resp.read())
    except Exception as e:
        print(f"SELFTEST: FAIL - request to / raised {type(e).__name__}: {e}")
        return 1

    print(f"SELFTEST: GET / -> {served_status}, {served_bytes} bytes")
    if served_status != 200:
        print("SELFTEST: FAIL - / did not return 200")
        return 1

    offenders = []
    checked = 0
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None)
        if not f:
            continue
        checked += 1
        if "site-packages" in f.replace("\\", "/").lower():
            offenders.append(f"{name} -> {f}")

    print(f"SELFTEST: sys.modules with a __file__ checked: {checked}")
    print(f"SELFTEST: modules originating in site-packages: {len(offenders)}")
    for o in offenders:
        print(f"SELFTEST:   OFFENDER {o}")
    if offenders:
        print("SELFTEST: FAIL - third-party runtime dependency loaded")
        return 1

    print("SELFTEST: PASS - served one request, zero site-packages modules")
    ShellAPIHandler.supervisor.close()
    server.shutdown()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sovereign Workspace Shell")
    parser.add_argument("--port", type=int, default=5180, help="Listen port (default: 5180)")
    parser.add_argument("--selftest", action="store_true",
                        help="H-11 proof hook: serve one request to / and exit")
    args = parser.parse_args(argv)

    if args.selftest:
        return _run_selftest(args.port)

    adapters = load_all_adapters()
    supervisor = JobSupervisor()
    log_rings = {}
    states = {}
    for mid, adapter in adapters.items():
        ring = LogRing() if adapter.get("state_class") == "runnable" else None
        if ring is not None:
            log_rings[mid] = ring
        states[mid] = ModuleRunner(mid, adapter, supervisor, ring)

    ShellAPIHandler.supervisor = supervisor
    ShellAPIHandler.adapters = adapters
    ShellAPIHandler.states = states
    ShellAPIHandler.log_rings = log_rings
    ShellAPIHandler.server_start = time.time()

    threading.Thread(target=_poll_loop, daemon=True).start()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), ShellAPIHandler)
    print(f"SWS Shell listening on http://127.0.0.1:{server.server_port}")
    print(f"Modules loaded: {list(states.keys())}")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # H-9: only Job-owned processes are stopped. EXTERNAL instances are never touched.
        supervisor.close()
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
