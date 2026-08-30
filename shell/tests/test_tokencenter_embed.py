"""
FIXUP-01 F-1 / S-17 — the Token Center panel is never a blank rectangle.

OP-4 named one forbidden end state: a silent empty frame with no fallback and no error. Every
existing proof of the embed asserts *configuration* (the CSP header pair, the `src` string, the
presence of an `<iframe>` tag) and none of them asserts that the operator is shown something. This
file asserts the rendered DOM instead, through the same headless-Edge harness test_render.py uses
for H-17.

Covered here:

  test_stopped_module_renders_a_status_and_a_start_control
      With Token Center NOT running, the panel must show a visible fallback carrying a status line
      and an enabled Start control, and the frame must be hidden and carry no `src`. This is the
      state an operator meets on a cold shell, and it is the state OP-4 forbids being blank.

  test_sandbox_is_the_recorded_combination_and_the_frame_is_cross_origin
      N-21b. `allow-scripts allow-same-origin` is kept deliberately (see the rationale block at the
      construction site in app.js). The reason it is safe here is that the framed document is a
      DIFFERENT ORIGIN from the shell, so `allow-same-origin` hands the frame its own origin rather
      than the shell's and the "can escape its sandboxing" warning is unreachable. That property is
      what this test pins: if anyone ever moves Token Center onto the shell's own origin, the
      rationale stops holding and this fails.

Phase D established that the frame DOES commit and paint when Token Center is running (see
bundles/FIXUP01/D/DIAGNOSIS.md, D-1), so the running case is proven live rather than here: driving
a module start from inside a unit test would make the suite depend on Token Center's own runtime.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from html.parser import HTMLParser

from shell.tests._harness import WORKSPACE, start_shell, stop_shell

STATIC = os.path.join(WORKSPACE, "shell", "static")
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _edge_path():
    for p in EDGE_CANDIDATES:
        if os.path.isfile(p):
            return p
    raise unittest.SkipTest("Microsoft Edge not present on this host")


class _EmbedDOM(HTMLParser):
    """Pulls the embed region out of the rendered document."""

    def __init__(self):
        super().__init__()
        self.frame = None            # attrs of iframe.tokencenter-frame
        self.fallback = None         # attrs of div.tokencenter-fallback
        self._in_fallback = 0
        self.fallback_text = []
        self.fallback_buttons = []   # (text, disabled) for buttons inside the fallback
        self._btn = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if tag == "iframe" and "tokencenter-frame" in cls:
            self.frame = a
        if tag == "div" and "tokencenter-fallback" in cls:
            self.fallback = a
            self._in_fallback = 1
            return
        if self._in_fallback:
            self._in_fallback += 1
            if tag == "button":
                self._btn = [a, ""]

    def handle_endtag(self, tag):
        if self._in_fallback:
            if tag == "button" and self._btn is not None:
                self.fallback_buttons.append(
                    (self._btn[1].strip(), "disabled" in self._btn[0]))
                self._btn = None
            self._in_fallback -= 1

    def handle_data(self, data):
        if self._in_fallback:
            if self._btn is not None:
                self._btn[1] += data
            else:
                self.fallback_text.append(data)


def _render(url):
    edge = _edge_path()
    prof = tempfile.mkdtemp(prefix="sws-fixup01-embed-")
    try:
        cp = subprocess.run(
            [edge, "--headless=new", "--disable-gpu", "--no-first-run",
             "--user-data-dir=" + prof, "--virtual-time-budget=8000", "--dump-dom", url],
            capture_output=True, timeout=120)
        dom = cp.stdout.decode("utf-8", "replace")
        i = dom.find("<!doctype")
        if i < 0:
            i = dom.find("<html")
        if i < 0:
            raise AssertionError("dump-dom produced no HTML document")
        parsed = _EmbedDOM()
        parsed.feed(dom[i:])
        return parsed
    finally:
        shutil.rmtree(prof, ignore_errors=True)


class TestTokenCenterEmbedRendersSomething(unittest.TestCase):
    """The panel always shows either a committed frame or an explicit fallback — never nothing."""

    def test_stopped_module_renders_a_status_and_a_start_control(self):
        proc, port, _nonce = start_shell()
        try:
            dom = _render("http://127.0.0.1:{}/".format(port))
        finally:
            stop_shell(proc)

        self.assertIsNotNone(dom.frame, "the Token Center iframe was not rendered at all")
        self.assertIsNotNone(dom.fallback, "no fallback region was rendered")

        # The frame is hidden and inert while the module is down: no src means no failed
        # navigation is left on screen.
        self.assertIn("hidden", dom.frame,
                      "frame is visible while Token Center is not running")
        self.assertIsNone(dom.frame.get("src"),
                          "a stopped module must not leave a src on the frame")

        # ...and because it is hidden, something else must be visible in its place.
        self.assertNotIn("hidden", dom.fallback,
                         "OP-4 forbidden state: frame hidden AND fallback hidden — a blank panel")

        status = " ".join("".join(dom.fallback_text).split())
        self.assertRegex(status, r"Token Center is \w+",
                         "fallback carries no status line naming the module state")

        labels = [t for t, _d in dom.fallback_buttons]
        self.assertIn("Start Token Center", labels,
                      "fallback offers no Start control; got {!r}".format(labels))
        enabled = [t for t, disabled in dom.fallback_buttons if not disabled]
        self.assertIn("Start Token Center", enabled,
                      "the Start control is rendered disabled on a stopped module, so the panel "
                      "offers the operator no action at all")

    def test_sandbox_is_the_recorded_combination_and_the_frame_is_cross_origin(self):
        proc, port, _nonce = start_shell()
        try:
            dom = _render("http://127.0.0.1:{}/".format(port))
        finally:
            stop_shell(proc)

        self.assertIsNotNone(dom.frame)
        self.assertEqual(dom.frame.get("sandbox"), "allow-scripts allow-same-origin",
                         "N-21b: the sandbox combination changed without updating the recorded "
                         "rationale in app.js")

        with open(os.path.join(STATIC, "app.js"), "r", encoding="utf-8") as f:
            js = f.read()
        m = re.search(r'TOKEN_CENTER_URL\s*=\s*"http://127\.0\.0\.1:(\d+)/"', js)
        self.assertIsNotNone(m, "TOKEN_CENTER_URL is no longer a literal loopback origin")
        self.assertNotEqual(
            m.group(1), str(port),
            "Token Center now shares the shell's origin. `allow-same-origin` would then hand the "
            "frame the SHELL's origin, the frame could delete its own sandbox attribute, and the "
            "rationale recorded in app.js for keeping both tokens no longer holds.")


if __name__ == "__main__":
    unittest.main()
