"""Distillery runtime console — health only. Starts no training, distillation, or merge."""
from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = 5184

# M-9 (B2-8): hardening for the health/console surface.
# - Host header must exactly match the bound loopback origin (DNS names and
#   prefix-confusion hosts are refused; there is no legitimate remote client).
# - Strict Content-Security-Policy on every response: the console stylesheet
#   ships as /console.css, so no inline style or script is needed anywhere.
# - nosniff, frame DENY, and no-referrer on every response, errors included.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; "
       "connect-src 'self'; img-src 'self'; "
       "frame-ancestors 'none'; object-src 'none'; base-uri 'none'")

CONSOLE_CSS = """body{font-family:ui-monospace,monospace;background:#0b0e14;color:#c7d1de;margin:16px}
h1{font-size:16px}section{border:1px solid #232b3a;padding:8px;margin:8px 0}"""

CONSOLE = """<!doctype html><html><head><meta charset="utf-8"><title>Distillery Console</title>
<link rel="stylesheet" href="/console.css"></head>
<body>
<h1>Distillery Console</h1>
<section><h2>Runtime Status</h2><p>idle</p></section>
<section><h2>Student Model</h2><p>none selected</p></section>
<section><h2>Teacher/Source Models</h2><p>none</p></section>
<section><h2>Pipeline State</h2><p>idle — no compute</p></section>
<section><h2>Current Stage</h2><p>none</p></section>
<section><h2>Queue</h2><p>empty</p></section>
<section><h2>Hardware/Compute Status</h2><p>no training process</p></section>
<section><h2>Start/Pause/Stop</h2><p>runtime only; pipeline not invoked</p></section>
<section><h2>Logs/Evidence</h2><p>see evidence/cpm1/8h</p></section>
<section><h2>Artifacts/Outputs</h2><p>none this session</p></section>
</body></html>"""

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        return
    def send_response(self, code, message=None):
        super().send_response(code, message)
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
    def _loopback_host(self):
        return self.headers.get("Host") == "127.0.0.1:%d" % (
            self.server.server_address[1],)
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        if not self._loopback_host():
            self.send_error(403, "Host not loopback")
            return
        if self.path.split("?",1)[0] in ("/health", "/healthz"):
            self._send(200, json.dumps({"ok": True, "status": "idle", "compute": False}))
            return
        if self.path.split("?",1)[0] == "/console.css":
            self._send(200, CONSOLE_CSS, "text/css; charset=utf-8")
            return
        if self.path.split("?",1)[0] in ("/", "/console"):
            self._send(200, CONSOLE, "text/html; charset=utf-8")
            return
        self._send(404, json.dumps({"ok": False}))

def main():
    httpd = ThreadingHTTPServer((HOST, PORT), H)
    print(f"distillery-console http://{HOST}:{PORT}", flush=True)
    httpd.serve_forever()

if __name__ == "__main__":
    main()
