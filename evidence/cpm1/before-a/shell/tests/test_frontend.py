"""
H-4 — no dangerous DOM sinks; logs rendered as text (REVIEW-BUILD-02 G4-3).

Two proofs:
  1. Static: no `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `eval(`, `new Function` or
     `document.write` anywhere in shell/static/*.js, and no inline script or event-handler
     attribute in index.html.
  2. Round trip: a log line containing `<script>` is pushed through the real API and comes back
     inside a JSON string, served as application/json with nosniff — never as HTML.
"""
import json
import os
import re
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from shell.src.logring import LogRing
from shell.src.server import ShellAPIHandler
from shell.tests._harness import WORKSPACE, free_port

STATIC = os.path.join(WORKSPACE, "shell", "static")

# H-4 forbids these as sinks for dynamic data.
FORBIDDEN = [
    ("innerHTML", re.compile(r"\binnerHTML\b")),
    ("outerHTML", re.compile(r"\bouterHTML\b")),
    ("insertAdjacentHTML", re.compile(r"\binsertAdjacentHTML\b")),
    ("eval(", re.compile(r"\beval\s*\(")),
    ("new Function", re.compile(r"\bnew\s+Function\b")),
    ("document.write", re.compile(r"\bdocument\s*\.\s*write\b")),
]

# Empty by design. Any entry here is a documented exception and must carry a reason; the test
# prints the allowlist into the artifact so a reviewer sees whether it grew.
ALLOWLIST = {}

PAYLOAD = '<script>alert("xss")</script> & <img src=x onerror=alert(1)> </script>'


class TestFrontendStatic(unittest.TestCase):
    """H-4 part 1: static scan of the shipped frontend."""

    def _js_files(self):
        return [os.path.join(STATIC, n) for n in sorted(os.listdir(STATIC))
                if n.endswith(".js")]

    def test_no_dangerous_dom_sinks(self):
        self.assertTrue(self._js_files(), "no JS files found to scan; test would be vacuous")
        hits = []
        for path in self._js_files():
            rel = os.path.relpath(path, WORKSPACE).replace("\\", "/")
            with open(path, "r", encoding="utf-8") as f:
                for lineno, line in enumerate(f, 1):
                    for name, pattern in FORBIDDEN:
                        if pattern.search(line):
                            key = "{}:{}:{}".format(rel, lineno, name)
                            if key in ALLOWLIST:
                                continue
                            hits.append("{}  {}".format(key, line.strip()[:120]))
        self.assertEqual(hits, [], "H-4 violated, forbidden DOM sink(s):\n" + "\n".join(hits))

    def test_no_inline_script_or_handlers(self):
        """CSP is script-src 'self'; inline script or an on* attribute would break it."""
        path = os.path.join(STATIC, "index.html")
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        inline = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html, re.IGNORECASE)
        self.assertEqual(inline, [], "inline <script> block in index.html: {}".format(inline))
        handlers = re.findall(r"\son[a-z]+\s*=", html, re.IGNORECASE)
        self.assertEqual(handlers, [],
                         "inline event handler attribute in index.html: {}".format(handlers))
        styles = re.findall(r"<style[^>]*>", html, re.IGNORECASE)
        self.assertEqual(styles, [], "inline <style> block in index.html: {}".format(styles))

    def test_dynamic_text_uses_textcontent(self):
        """§7.3 item 4: log and status text is set as text nodes, not parsed as markup."""
        joined = ""
        for path in self._js_files():
            with open(path, "r", encoding="utf-8") as f:
                joined += f.read()
        self.assertIn("textContent", joined,
                      "no textContent assignment found; how is dynamic text rendered?")


class TestFrontendLogRoundTrip(unittest.TestCase):
    """H-4 part 2: a <script> log line survives the API as JSON string data, not markup."""

    @classmethod
    def setUpClass(cls):
        cls.ring = LogRing()
        ShellAPIHandler.supervisor = None
        ShellAPIHandler.adapters = {}
        ShellAPIHandler.states = {}
        ShellAPIHandler.log_rings = {"frontend": cls.ring}
        ShellAPIHandler.selftest = False
        cls.server = ThreadingHTTPServer(("127.0.0.1", free_port()), ShellAPIHandler)
        cls.port = cls.server.server_port
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_script_tag_returned_as_json_string(self):
        self.ring.clear()
        self.ring.write((PAYLOAD + "\n").encode("utf-8"))

        url = "http://127.0.0.1:{}/api/logs/frontend".format(self.port)
        with urllib.request.urlopen(url, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            headers = dict(resp.headers)

        # Served as data, not as a document: a browser cannot be talked into parsing this as
        # HTML, which is what makes the payload inert regardless of its content.
        self.assertEqual(headers.get("Content-Type"), "application/json")
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("frame-ancestors 'none'", headers.get("Content-Security-Policy", ""))

        # The body is well-formed JSON and the payload is inside a string value, not loose in
        # the document. json.loads would raise if the response had been assembled by string
        # concatenation without escaping.
        parsed = json.loads(raw)
        self.assertEqual(parsed["module_id"], "frontend")
        self.assertIn(PAYLOAD, parsed["logs"],
                      "the log line did not round-trip intact")

        # The quotes inside the payload are escaped in the wire format; that is the property
        # that keeps the JSON parseable.
        self.assertIn('alert(\\"xss\\")', raw,
                      "embedded double quotes were not JSON-escaped on the wire")
        self.assertNotIn('"logs": "<script>alert("', raw)

    def test_payload_is_not_altered_by_redaction(self):
        """Control: the round trip proves escaping, not accidental removal of the payload."""
        self.ring.clear()
        self.ring.write((PAYLOAD + "\n").encode("utf-8"))
        self.assertIn(PAYLOAD, self.ring.read())


if __name__ == "__main__":
    unittest.main()
