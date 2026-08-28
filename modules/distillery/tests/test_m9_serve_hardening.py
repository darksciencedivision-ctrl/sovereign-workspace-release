"""M-9 hardening tests — Distillery serve.py (SWS-REM-DIR-20260828 R2 B2-8).

Health/console server hardening: Host validation (loopback exact), strict CSP
(no inline style — the console stylesheet ships as /console.css), nosniff,
X-Frame-Options DENY, Referrer-Policy no-referrer — on every response,
404 included. Stdlib-only, offline.

Fail-before (against the shipped serve.py): host checks, headers, and the
external-CSS tests fail. Pass-after: all green.
"""

import json
import os
import socket
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
import serve  # noqa: E402


class _Server:
    def __init__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), serve.H)
        self.port = self.server.server_address[1]
        self.base = "http://127.0.0.1:%d" % self.port
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def get(self, path, host=None):
        headers = {"Host": host} if host else {}
        req = urllib.request.Request(self.base + path, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def raw(self, request_line_and_headers):
        with socket.create_connection(("127.0.0.1", self.port),
                                      timeout=10) as sock:
            sock.sendall(request_line_and_headers)
            sock.settimeout(10)
            return sock.recv(4096).decode("latin-1", errors="replace")


class HostValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = _Server()

    @classmethod
    def tearDownClass(cls):
        cls.fx.stop()

    def _expect_refused(self, host):
        status, _, _ = self.fx.get("/health", host=host)
        self.assertEqual(status, 403, "Host %r must be refused" % host)

    def test_bound_loopback_host_passes(self):
        status, _, body = self.fx.get(
            "/health", host="127.0.0.1:%d" % self.fx.port)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body.decode("utf-8"))["ok"])

    def test_default_port_host_refused_on_other_port(self):
        self._expect_refused("127.0.0.1:5184")

    def test_prefix_confusion_refused(self):
        self._expect_refused("127.0.0.1.evil.example")

    def test_foreign_host_refused(self):
        self._expect_refused("evil.example")

    def test_localhost_name_refused(self):
        # DNS names are rebinding vectors; only the literal loopback IP passes.
        self._expect_refused("localhost:%d" % self.fx.port)

    def test_missing_host_refused(self):
        raw = ("GET /health HTTP/1.1\r\n\r\n").encode("ascii")
        response = self.fx.raw(raw)
        self.assertIn("403", response.split("\r\n", 1)[0], response[:200])


class SecurityHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = _Server()

    @classmethod
    def tearDownClass(cls):
        cls.fx.stop()

    def _assert_headers(self, headers, context):
        csp = headers.get("Content-Security-Policy", "")
        self.assertIn("default-src 'self'", csp, context)
        self.assertIn("frame-ancestors 'none'", csp, context)
        self.assertNotIn("unsafe-inline", csp, context)
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff",
                         context)
        self.assertEqual(headers.get("X-Frame-Options"), "DENY", context)
        self.assertEqual(headers.get("Referrer-Policy"), "no-referrer",
                         context)

    def test_headers_on_health(self):
        status, headers, _ = self.fx.get("/health")
        self.assertEqual(status, 200)
        self._assert_headers(headers, "GET /health")

    def test_headers_on_console(self):
        status, headers, body = self.fx.get("/console")
        self.assertEqual(status, 200)
        self._assert_headers(headers, "GET /console")
        self.assertNotIn(b"<style", body,
                         "console must carry no inline style (strict CSP)")
        self.assertIn(b"/console.css", body)

    def test_headers_on_console_css(self):
        status, headers, body = self.fx.get("/console.css")
        self.assertEqual(status, 200)
        self.assertTrue(headers.get("Content-Type", "").startswith("text/css"))
        self._assert_headers(headers, "GET /console.css")
        self.assertIn(b"font-family", body)

    def test_headers_on_404(self):
        status, headers, _ = self.fx.get("/no-such-route")
        self.assertEqual(status, 404)
        self._assert_headers(headers, "GET 404")


class ConsoleContractTests(unittest.TestCase):
    """The console stays a health-only surface (module docstring contract)."""

    @classmethod
    def setUpClass(cls):
        cls.fx = _Server()

    @classmethod
    def tearDownClass(cls):
        cls.fx.stop()

    def test_health_reports_no_compute(self):
        _, _, body = self.fx.get("/health")
        doc = json.loads(body.decode("utf-8"))
        self.assertIs(doc["compute"], False)
        self.assertEqual(doc["status"], "idle")

    def test_console_states_runtime_only(self):
        _, _, body = self.fx.get("/console")
        self.assertIn(b"runtime only; pipeline not invoked", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
