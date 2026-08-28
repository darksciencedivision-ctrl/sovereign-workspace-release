"""CSRF refresh-contract tests — H-3 closure, M-1 Option A (SWS-REM-DIR-20260828 R2 B1-2).

Contract under test (decision-block M-1 Option A — a REAL compared token):

* the server generates one CSRF token per process at start;
* the same-origin UI can fetch it (GET /api/csrf-token, loopback Host only);
* POST /api/refresh succeeds (200) only with Origin + the exact process token;
* bare POSTs, absent tokens, wrong tokens, and cross-origin POSTs get 403.

Fail-before (pre-fix) expectations: the UI-pattern test fails (endpoint absent)
and the wrong-token test fails (nonce was only non-emptiness-checked). Pass-after:
all green. Stdlib-only (unittest + http.server + urllib), offline, no fixtures.
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


class ServerFixture:
    """One live Token Center server on an ephemeral loopback port."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        home = Path(self.tmp.name)
        state = piggybank.State(home, 7)
        # make_handler(state) generates the per-process token internally
        # (post-fix); main() passes its own generated token the same way.
        handler_class = piggybank.make_handler(state)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
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

    # --- request helpers -------------------------------------------------

    def post_refresh(self, headers=None):
        req = urllib.request.Request(self.base + "/api/refresh", data=b"",
                                     method="POST", headers=headers or {})
        return self._run(req)

    def get_csrf_token(self):
        req = urllib.request.Request(self.base + "/api/csrf-token",
                                     method="GET")
        return self._run(req)

    @staticmethod
    def _run(req):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def origin_headers(self, extra=None):
        headers = {
            "Origin": self.base,
            "Host": "127.0.0.1:%d" % self.port,
            "Content-Length": "0",
        }
        if extra:
            headers.update(extra)
        return headers


class RefreshContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = ServerFixture()

    @classmethod
    def tearDownClass(cls):
        cls.fx.stop()

    def test_bare_post_rejected(self):
        """The pre-fix UI pattern (bare POST, no headers) must be 403."""
        status, _ = self.fx.post_refresh()
        self.assertEqual(status, 403)

    def test_ui_refresh_pattern_succeeds(self):
        """UI fetches the process token same-origin, sends it, gets 200."""
        status, body = self.fx.get_csrf_token()
        self.assertEqual(status, 200, "GET /api/csrf-token must exist")
        token = json.loads(body.decode("utf-8"))["token"]
        self.assertIsInstance(token, str)
        self.assertGreaterEqual(len(token), 32, "token must carry real entropy")
        status, body = self.fx.post_refresh(
            self.fx.origin_headers({"X-CSRF-Nonce": token}))
        self.assertEqual(status, 200, "UI pattern with exact token must pass")
        payload = json.loads(body.decode("utf-8"))
        self.assertTrue(payload["ok"])

    def test_wrong_token_rejected(self):
        """A present-but-wrong nonce must be 403 (real comparison, not
        non-emptiness)."""
        status, _ = self.fx.post_refresh(
            self.fx.origin_headers({"X-CSRF-Nonce": "definitely-not-the-token"}))
        self.assertEqual(status, 403)

    def test_absent_token_rejected(self):
        status, _ = self.fx.post_refresh(self.fx.origin_headers())
        self.assertEqual(status, 403)

    def test_cross_origin_rejected_even_with_valid_token(self):
        status, body = self.fx.get_csrf_token()
        if status == 200:
            token = json.loads(body.decode("utf-8"))["token"]
        else:
            token = "placeholder"
        headers = {
            "Origin": "http://example.com",
            "Host": "127.0.0.1:%d" % self.fx.port,
            "X-CSRF-Nonce": token,
            "Content-Length": "0",
        }
        status, _ = self.fx.post_refresh(headers)
        self.assertEqual(status, 403)

    def test_token_endpoint_rejects_foreign_host(self):
        """The token endpoint is loopback-Host-only."""
        req = urllib.request.Request(self.fx.base + "/api/csrf-token",
                                     headers={"Host": "public.example.com"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
