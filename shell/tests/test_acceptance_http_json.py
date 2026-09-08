"""GET must never send a body. The [string]$Body + $null binding is the timeout cause."""
from __future__ import annotations

import json
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "tools" / "acceptance" / "http_json.ps1"


class _Handler(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *_args) -> None:
        return

    def _record(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.seen.append({
            "method": self.command,
            "path": self.path,
            "length": length,
            "body": body.decode("utf-8", "replace"),
        })

    def do_GET(self) -> None:
        self._record()
        if self.path == "/err":
            payload = b'{"ok":false}'
            self.send_response(500)
        else:
            payload = b'{"ok":true,"path":"%s"}' % self.path.encode("ascii")
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        self._record()
        payload = b'{"ok":true,"echo":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _ps(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-Command", script],
        capture_output=True, text=True, timeout=30)


class HttpJsonHelper(unittest.TestCase):
    def setUp(self) -> None:
        _Handler.seen = []
        self.httpd = HTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def _invoke(self, snippet: str) -> dict:
        script = (
            f". '{HELPER}'\n"
            f"$base = 'http://127.0.0.1:{self.port}'\n"
            + snippet + "\n"
            "$r | ConvertTo-Json -Compress\n"
        )
        proc = _ps(script)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_get_with_null_body_does_not_send_a_content_body(self) -> None:
        r = self._invoke("$r = Invoke-Json -Method GET -Url \"$base/ok\" -Body $null")
        self.assertEqual(r["Code"], 200)
        self.assertEqual(_Handler.seen[-1]["method"], "GET")
        self.assertEqual(_Handler.seen[-1]["length"], 0)

    def test_get_omitting_body_does_not_send_a_content_body(self) -> None:
        r = self._invoke("$r = Invoke-Json -Method GET -Url \"$base/ok\"")
        self.assertEqual(r["Code"], 200)
        self.assertEqual(_Handler.seen[-1]["length"], 0)

    def test_post_json_body_is_delivered(self) -> None:
        r = self._invoke("$r = Invoke-Json -Method POST -Url \"$base/p\" -Body '{\"id\":\"sovereign\"}'")
        self.assertEqual(r["Code"], 200)
        self.assertEqual(_Handler.seen[-1]["method"], "POST")
        self.assertIn("sovereign", _Handler.seen[-1]["body"])

    def test_http_error_is_returned_not_hidden(self) -> None:
        r = self._invoke("$r = Invoke-Json -Method GET -Url \"$base/err\"")
        self.assertEqual(r["Code"], 500)
        self.assertIn("ok", r["Text"])

    def test_wait_url_reports_the_last_error_not_a_bare_timeout(self) -> None:
        script = (
            f". '{HELPER}'\n"
            "try { Wait-Url -Url 'http://127.0.0.1:1/nope' -Seconds 1 } catch { "
            "Write-Output $_.Exception.Message; exit 7 }\n"
        )
        proc = _ps(script)
        self.assertEqual(proc.returncode, 7)
        self.assertIn("last error", proc.stdout.lower())
        self.assertNotEqual(proc.stdout.strip(), "timed out waiting for http://127.0.0.1:1/nope")


if __name__ == "__main__":
    unittest.main()
