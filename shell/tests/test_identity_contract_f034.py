"""F-034 — identity rejects unrelated responders, stale keys, and malformed bodies."""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if WS not in sys.path:
    sys.path.insert(0, WS)

from shell.src import probe  # noqa: E402


class _IdentityHandler(BaseHTTPRequestHandler):
    payload = b"{}"
    content_type = "application/json"

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", self.content_type)
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *a):
        pass


def _serve(payload: bytes, content_type: str = "application/json"):
    class H(_IdentityHandler):
        pass
    H.payload = payload
    H.content_type = content_type
    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class IdentityContract(unittest.TestCase):
    def tearDown(self):
        if getattr(self, "server", None):
            self.server.shutdown()
            self.server.server_close()

    def _url(self, payload, content_type="application/json"):
        self.server = _serve(payload, content_type)
        return f"http://127.0.0.1:{self.server.server_port}/"

    def test_malformed_non_object_json_fails(self):
        url = self._url(b'"status ok"')
        ok, err = probe.http_json_identity(url, ["status"])
        self.assertFalse(ok)
        self.assertIn("not a JSON object", err)

    def test_array_body_fails(self):
        url = self._url(b"[1]")
        ok, err = probe.http_json_identity(url, ["status"])
        self.assertFalse(ok)

    def test_missing_key_fails(self):
        url = self._url(b'{"status":"ok"}')
        ok, err = probe.http_json_identity(url, ["status", "product_version"])
        self.assertFalse(ok)
        self.assertIn("Missing key", err)

    def test_wrong_instance_same_generic_keys_fails_distillery_shape(self):
        sovereign_shaped = json.dumps({
            "ok": True, "status": "ready", "product_version": "3.1.2",
        }).encode()
        url = self._url(sovereign_shaped)
        ok, err = probe.http_json_identity(url, ["ok", "status", "compute"])
        self.assertFalse(ok, err)

    def test_require_value_mismatch_fails(self):
        url = self._url(b'{"status":"ok","product_version":"x","loopback_only":false}')
        ok, err = probe.http_json_identity(
            url, ["status", "product_version", "loopback_only"],
            require={"loopback_only": True})
        self.assertFalse(ok)
        self.assertIn("mismatch", err)

    def test_intended_sovereign_shape_passes(self):
        url = self._url(b'{"status":"ok","product_version":"3.1.2","loopback_only":true}')
        ok, err = probe.http_json_identity(
            url, ["status", "product_version", "loopback_only"],
            require={"loopback_only": True})
        self.assertTrue(ok, err)

    def test_html_marker_absent_fails(self):
        url = self._url(b"<html><title>Other</title></html>", "text/html")
        ok, err = probe.http_html_identity(url, "Debate Table")
        self.assertFalse(ok)

    def test_html_marker_present_passes(self):
        url = self._url(b"<html><title>Debate Table</title></html>", "text/html")
        ok, err = probe.http_html_identity(url, "Debate Table")
        self.assertTrue(ok, err)


if __name__ == "__main__":
    unittest.main()
