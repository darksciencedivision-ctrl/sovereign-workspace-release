"""Distillery runtime console - health only. Starts no training, distillation, or merge.

SW-24: the console now states its capability status honestly - what is unavailable (real
training, promotion) and why - and marks preview evidence as synthetic fixture kept separate
from measured/qualified runs, instead of showing a bare "idle" page that implied a finished,
idle-but-ready product. The status is derived from the real gates (see capability.py).
"""
from __future__ import annotations
import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import capability
from shutdown_watcher import install_shutdown_watcher

HOST = "127.0.0.1"
# The shell adapter does not pass DISTILLERY_PORT (not in its env_allowlist), so a shell launch is
# always 5184; the override exists so the SW-18 graceful-shutdown test can run the real entry point
# without colliding with a running console.
PORT = int(os.environ.get("DISTILLERY_PORT", "5184"))

# M-9 (B2-8): hardening for the health/console surface.
# - Host header must exactly match the bound loopback origin (DNS names and
#   prefix-confusion hosts are refused; there is no legitimate remote client).
# - Strict Content-Security-Policy on every response: the console stylesheet
#   ships as /console.css, so no inline style or script is needed anywhere. The
#   capability status is therefore rendered SERVER-SIDE into the HTML text below.
# - nosniff, frame DENY, and no-referrer on every response, errors included.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; "
       "connect-src 'self'; img-src 'self'; "
       "frame-ancestors 'none'; object-src 'none'; base-uri 'none'")

CONSOLE_CSS = """body{font-family:ui-monospace,monospace;background:#0b0e14;color:#c7d1de;margin:16px}
h1{font-size:16px}h2{font-size:13px}section{border:1px solid #232b3a;padding:8px;margin:8px 0}
.maturity{display:inline-block;border:1px solid #7a5c00;background:#2a2000;color:#e8c76b;padding:1px 6px;border-radius:3px;font-size:11px}
.unavailable{color:#e88;font-weight:bold}
.reason{color:#8fa3bf;font-size:12px}
.evidence{border-color:#5c3a00;background:#160f04}
.cap{margin:6px 0}"""


def health_payload() -> dict:
    """The shell probes /health and requires keys ok/status/compute (see distillery.json)."""
    report = capability.capability_report()
    return {
        "ok": True,
        "status": "idle",
        "compute": report["compute"],
        # Additive: surface maturity + a functional-capability summary without changing the
        # required keys the shell identity check depends on.
        "maturity": report["maturity"],
        "capabilities_available": [c["id"] for c in report["capabilities"] if c.get("available")],
    }


def capability_payload() -> dict:
    return capability.capability_report()


def build_console_html(report: dict) -> str:
    """Render the capability report to console HTML (server-side; no inline script/style)."""
    def esc(value) -> str:
        return html.escape(str(value))

    cap_rows = []
    for cap in report.get("capabilities", []):
        state = "AVAILABLE" if cap.get("available") else "UNAVAILABLE"
        cls = "" if cap.get("available") else ' class="unavailable"'
        cap_rows.append(
            f'<div class="cap"><span{cls}>{esc(cap.get("label"))}: {state}</span>'
            f'<br><span class="reason">{esc(cap.get("reason"))} - {esc(cap.get("detail"))}</span></div>'
        )
    caps_html = "".join(cap_rows) or "<p>no capabilities reported</p>"
    ev = report.get("evidence", {})
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>Distillery Console</title>'
        '<link rel="stylesheet" href="/console.css"></head>'
        "<body>"
        '<h1>Distillery Console <span class="maturity">maturity: '
        f'{esc(report.get("maturity", "unspecified"))}</span></h1>'
        '<section><h2>Runtime Status</h2><p>idle - console/health only; this process starts no '
        "training, distillation, or merge compute.</p></section>"
        f'<section><h2>Capability Status</h2>{caps_html}</section>'
        f'<section class="evidence"><h2>Evidence</h2><p>{esc(ev.get("note", ""))}</p>'
        f'<p class="reason">shown class: {esc(ev.get("class_shown", "unknown"))} | '
        f'gate-qualifying class: {esc(ev.get("measured_class", "unknown"))}</p></section>'
        "<section><h2>Pipeline State</h2><p>idle - no compute</p></section>"
        "<section><h2>Queue</h2><p>empty</p></section>"
        "<section><h2>Artifacts/Outputs</h2><p>none this session (fixture evidence, if any, is "
        "not a measured artifact)</p></section>"
        "</body></html>"
    )


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
        route = self.path.split("?", 1)[0]
        if route in ("/health", "/healthz"):
            self._send(200, json.dumps(health_payload()))
            return
        if route == "/capability":
            self._send(200, json.dumps(capability_payload()))
            return
        if route == "/console.css":
            self._send(200, CONSOLE_CSS, "text/css; charset=utf-8")
            return
        if route in ("/", "/console"):
            self._send(200, build_console_html(capability_payload()), "text/html; charset=utf-8")
            return
        self._send(404, json.dumps({"ok": False}))

def main():
    httpd = ThreadingHTTPServer((HOST, PORT), H)
    # SW-18: stop serving when the shell signals graceful shutdown (before its terminate fallback).
    install_shutdown_watcher(httpd.shutdown)
    print(f"distillery-console http://{HOST}:{PORT}", flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        print("distillery-console stopped (graceful)", flush=True)

if __name__ == "__main__":
    main()
