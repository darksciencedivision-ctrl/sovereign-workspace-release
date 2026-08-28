"""
Fixture HTTP service for state-machine tests (R3-2).

    fixture_http.py --port P --identity {ok|wrong} [--exit-after S] [--unready]
                    [--degrade-flag PATH]

Serves exactly two paths:
  /        HTML. With --identity ok it contains the marker "Debate Table"; with wrong it does not.
  /health  JSON. With --identity ok: {"status":"ok","product_version":"fixture"}.
           With wrong: {"status":"ok"} — present but missing the identifying key.
           With --unready, or while --degrade-flag names an existing file: HTTP 503.

--exit-after S makes the process exit(0) S seconds after start, for the FAILED(EXIT) transition.
"""
import argparse
import json
import os
import sys
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ARGS = None

HTML_OK = "<!doctype html><title>Debate Table</title><h1>Debate Table</h1>"
HTML_WRONG = "<!doctype html><title>Something Else</title><h1>Not the marker</h1>"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, status, body: bytes, ctype: str):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _degraded(self) -> bool:
        if ARGS.unready:
            return True
        if ARGS.degrade_flag and os.path.exists(ARGS.degrade_flag):
            return True
        return False

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            if self._degraded():
                self._send(503, b'{"status":"unready"}', "application/json")
                return
            payload = {"status": "ok"}
            if ARGS.identity == "ok":
                payload["product_version"] = "fixture"
            self._send(200, json.dumps(payload).encode(), "application/json")
        elif path == "/":
            html = HTML_OK if ARGS.identity == "ok" else HTML_WRONG
            self._send(200, html.encode(), "text/html; charset=utf-8")
        else:
            self._send(404, b"{}", "application/json")


def main():
    global ARGS
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--identity", choices=["ok", "wrong"], default="ok")
    p.add_argument("--exit-after", type=float, default=0.0)
    p.add_argument("--unready", action="store_true")
    p.add_argument("--degrade-flag", default="")
    ARGS = p.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", ARGS.port), Handler)
    print("fixture_http listening on {}".format(ARGS.port), flush=True)

    if ARGS.exit_after > 0:
        def bail():
            time.sleep(ARGS.exit_after)
            os._exit(0)
        threading.Thread(target=bail, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
