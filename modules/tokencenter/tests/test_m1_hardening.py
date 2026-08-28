"""M-1 full hardening tests — Token Center (SWS-REM-DIR-20260828 R2 B2-3).

Extends the B1-2 CSRF contract with the full M-1 hardening surface:

* EXACT-origin parse: the startswith('http://127.0.0.1') prefix flaw is gone —
  confusable origins (127.0.0.1.evil.example, wrong port, https) are refused
  even with a valid token;
* mutation guard: the refresh endpoint accepts NO body — Content-Length > 0,
  chunked Transfer-Encoding, and form-family Content-Types are refused;
* standard security headers on ALL responses (JSON, static, token endpoint,
  200 and 403 alike): Content-Security-Policy (strict 'self'), nosniff,
  X-Frame-Options DENY, Referrer-Policy no-referrer;
* lifecycle: the token is stable within one process and differs across
  independently constructed handler servers.

Fail-before (against the B1-2 state): exact-origin, body-guard, and header
tests fail. Pass-after: all green, and the B1-2 contract suite stays green.
"""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import piggybank


class _Server:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        state = piggybank.State(Path(self.tmp.name), 7)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0),
                                          piggybank.make_handler(state))
        self.port = self.server.server_address[1]
        self.base = "http://127.0.0.1:%d" % self.port
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def token(self):
        with urllib.request.urlopen(self.base + "/api/csrf-token",
                                    timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))["token"]

    def post_refresh(self, origin, token, body=None, content_type=None,
                     content_length=None):
        headers = {"Origin": origin,
                   "Host": "127.0.0.1:%d" % self.port}
        if token is not None:
            headers["X-CSRF-Nonce"] = token
        if content_type is not None:
            headers["Content-Type"] = content_type
        if content_length is not None:
            headers["Content-Length"] = str(content_length)
        # The real UI does fetch(..., {method:'POST'}) with NO body and NO
        # Content-Type. data=None reproduces that exactly; data=b"" would make
        # urllib invent application/x-www-form-urlencoded, which the guard
        # must (and does) refuse.
        req = urllib.request.Request(self.base + "/api/refresh", data=body,
                                     method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def get(self, path):
        req = urllib.request.Request(self.base + path)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()


class ExactOriginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = _Server()
        cls.tok = cls.fx.token()

    @classmethod
    def tearDownClass(cls):
        cls.fx.stop()

    def _expect_403(self, origin):
        status, _, _ = self.fx.post_refresh(origin, self.tok)
        self.assertEqual(status, 403, "origin %r must be refused" % origin)

    def test_exact_same_origin_passes(self):
        status, _, body = self.fx.post_refresh(self.fx.base, self.tok)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body.decode("utf-8"))["ok"])

    def test_prefix_confusion_refused(self):
        self._expect_403("http://127.0.0.1.evil.example")

    def test_foreign_origin_refused(self):
        self._expect_403("http://evil.example")

    def test_wrong_port_refused(self):
        other = self.fx.port + 1 if self.fx.port < 65535 else self.fx.port - 1
        self._expect_403("http://127.0.0.1:%d" % other)

    def test_https_variant_refused(self):
        self._expect_403("https://127.0.0.1:%d" % self.fx.port)

    def test_origin_with_trailing_garbage_refused(self):
        self._expect_403(self.fx.base + "@evil.example")


class MutationGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = _Server()
        cls.tok = cls.fx.token()

    @classmethod
    def tearDownClass(cls):
        cls.fx.stop()

    def test_zero_body_passes(self):
        status, _, _ = self.fx.post_refresh(self.fx.base, self.tok)
        self.assertEqual(status, 200)

    def test_nonzero_body_refused(self):
        status, _, _ = self.fx.post_refresh(self.fx.base, self.tok,
                                            body=b"payload",
                                            content_length=7)
        self.assertEqual(status, 403)

    def test_form_content_type_refused_even_empty(self):
        status, _, _ = self.fx.post_refresh(
            self.fx.base, self.tok,
            content_type="application/x-www-form-urlencoded")
        self.assertEqual(status, 403)

    def test_multipart_content_type_refused(self):
        status, _, _ = self.fx.post_refresh(
            self.fx.base, self.tok,
            content_type="multipart/form-data; boundary=x")
        self.assertEqual(status, 403)

    def test_chunked_encoding_refused(self):
        # Raw socket: urllib would normalize the body headers away, and the
        # guard must see exactly what a hand-built attacker request sends.
        import socket
        raw = (
            "POST /api/refresh HTTP/1.1\r\n"
            "Host: 127.0.0.1:%d\r\n"
            "Origin: %s\r\n"
            "X-CSRF-Nonce: %s\r\n"
            "Transfer-Encoding: chunked\r\n"
            "\r\n" % (self.fx.port, self.fx.base, self.tok)
        ).encode("ascii")
        with socket.create_connection(("127.0.0.1", self.fx.port),
                                      timeout=10) as sock:
            sock.sendall(raw)
            sock.settimeout(10)
            response = sock.recv(4096).decode("latin-1", errors="replace")
        self.assertIn("403", response.split("\r\n", 1)[0], response[:200])


class SecurityHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = _Server()
        cls.tok = cls.fx.token()

    @classmethod
    def tearDownClass(cls):
        cls.fx.stop()

    def _assert_headers(self, headers, context):
        csp = headers.get("Content-Security-Policy", "")
        self.assertIn("default-src 'self'", csp, context)
        self.assertIn("frame-ancestors 'none'", csp, context)
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff",
                         context)
        self.assertEqual(headers.get("X-Frame-Options"), "DENY", context)
        self.assertEqual(headers.get("Referrer-Policy"), "no-referrer",
                         context)

    def test_headers_on_index(self):
        status, headers, _ = self.fx.get("/")
        self.assertEqual(status, 200)
        self._assert_headers(headers, "GET /")

    def test_headers_on_app_js(self):
        status, headers, _ = self.fx.get("/app.js")
        self.assertEqual(status, 200)
        self._assert_headers(headers, "GET /app.js")

    def test_headers_on_summary_api(self):
        status, headers, _ = self.fx.get("/api/summary")
        self.assertEqual(status, 200)
        self._assert_headers(headers, "GET /api/summary")

    def test_headers_on_token_endpoint(self):
        status, headers, _ = self.fx.get("/api/csrf-token")
        self.assertEqual(status, 200)
        self._assert_headers(headers, "GET /api/csrf-token")

    def test_headers_on_successful_refresh(self):
        status, headers, _ = self.fx.post_refresh(self.fx.base, self.tok)
        self.assertEqual(status, 200)
        self._assert_headers(headers, "POST 200")

    def test_headers_on_403_error(self):
        status, headers, _ = self.fx.post_refresh("http://evil.example",
                                                  self.tok)
        self.assertEqual(status, 403)
        self._assert_headers(headers, "POST 403")

    def test_headers_on_404_error(self):
        status, headers, _ = self.fx.get("/no-such-route")
        self.assertEqual(status, 404)
        self._assert_headers(headers, "GET 404")


class TokenLifecycleTests(unittest.TestCase):
    def test_token_stable_within_process(self):
        fx = _Server()
        try:
            self.assertEqual(fx.token(), fx.token())
        finally:
            fx.stop()

    def test_token_differs_across_processes(self):
        fx1, fx2 = _Server(), _Server()
        try:
            self.assertNotEqual(fx1.token(), fx2.token())
        finally:
            fx1.stop()
            fx2.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
