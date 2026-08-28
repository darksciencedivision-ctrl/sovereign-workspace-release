"""Artificially-autostarting shell fixture for test_cold_start_starts_nothing.

Boots the REAL ShellAPIHandler with ONE runnable adapter (an ephemeral fixture_http child),
but - unlike the product - starts the runner immediately at boot, the way an autostarting
shell would. A cold-start assertion run against this fixture must FAIL; against the product
it must PASS.

Usage: py -3.12 fixtures/fixture_autostart_server.py --port P
Prints "FIXTURE READY" once serving.
"""
import argparse
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, WS)

from http.server import ThreadingHTTPServer

from shell.src import server as srv
from shell.src.logring import LogRing
from shell.src.states import ModuleRunner
from shell.src.supervisor import JobSupervisor


def free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    args = ap.parse_args()

    fx_port = free_port()
    fx = subprocess.Popen(
        [sys.executable, "-B", os.path.join(HERE, "fixture_http.py"),
         "--port", str(fx_port), "--identity", "ok"],
        cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    adapter = {
        "id": "fx",
        "display_name": "Autostart Fixture",
        "description": "artificially autostarted module",
        "state_class": "runnable",
        "root": HERE,
        "runtime_writes": [],
        "launch": {
            "cwd": HERE,
            "argv": [sys.executable, "-B", os.path.join(HERE, "fixture_http.py"),
                     "--port", str(fx_port), "--identity", "ok"],
            "env_allowlist": ["SYSTEMROOT", "PATH", "TEMP", "TMP"],
            "env_set": {"PYTHONDONTWRITEBYTECODE": "1"},
        },
        "readiness": {"kind": "http", "url": "http://127.0.0.1:%d/" % fx_port,
                      "expect_status": 200, "timeout_s": 10, "poll_ms": 250},
        "identity": {"kind": "http_html_marker",
                     "url": "http://127.0.0.1:%d/" % fx_port,
                     "html_marker": "Debate Table"},
        "open": {"kind": "browser", "url": "http://127.0.0.1:%d/" % fx_port},
        "stop": {"kind": "job_object", "grace_s": 3},
    }

    supervisor = JobSupervisor()
    ring = LogRing()
    states = {"fx": ModuleRunner("fx", adapter, supervisor, ring)}
    srv.ShellAPIHandler.supervisor = supervisor
    srv.ShellAPIHandler.adapters = {"fx": adapter}
    srv.ShellAPIHandler.states = states
    srv.ShellAPIHandler.log_rings = {"fx": ring}
    srv.ShellAPIHandler.server_start = time.time()

    # THE DEFECT THIS FIXTURE EMBODIES: start modules at boot.
    threading.Thread(target=states["fx"].start, daemon=True).start()

    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), srv.ShellAPIHandler)
    print("FIXTURE READY")
    sys.stdout.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            supervisor.close()
        except Exception:
            pass
        fx.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())