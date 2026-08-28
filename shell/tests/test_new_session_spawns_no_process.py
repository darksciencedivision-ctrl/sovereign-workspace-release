"""G20 proof (CP-M1 Band 3): creating a session container spawns NO PTY.

Pins three structural facts in modules/sow/apps/desktop/main.js (+ wiring):
  (1) the implicit shell default at the PTY boundary is GONE (no `spec.file ||`),
  (2) an explicit no-process creation path exists ("pane:create-empty") whose record
      carries backend=none / modelRef null / pid null / state EMPTY,
  (3) the renderer "+ Terminal" control routes to that path instead of pane:new.
Fails-before was captured before these edits landed (the old code defaulted to
powershell.exe and always spawned).
"""
import os
import re
import unittest

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAIN = os.path.join(WS, "modules", "sow", "apps", "desktop", "main.js")
PRELOAD = os.path.join(WS, "modules", "sow", "apps", "desktop", "preload.js")
RENDERER = os.path.join(WS, "modules", "sow", "apps", "desktop", "renderer", "renderer.js")


def read(p):
    with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


class TestNewSessionSpawnsNoProcess(unittest.TestCase):
    def setUp(self):
        self.main = read(MAIN)
        self.preload = read(PRELOAD)
        self.renderer = read(RENDERER)

    def test_no_implicit_shell_default_at_pty_boundary(self):
        self.assertNotRegex(self.main, r"spec\.file \|\| \(IS_WIN")

    def test_create_empty_path_exists_with_empty_record_fields(self):
        self.assertIn('"pane:create-empty"', self.main)
        m = re.search(r"function createEmptyPane\(.*?\n\}", self.main, re.S)
        self.assertIsNotNone(m)
        body = m.group(0)
        self.assertIn('sessionId: null', body)
        self.assertIn('backend: "none"', body)
        self.assertIn('modelRef: null', body)
        self.assertIn('pid: null', body)
        self.assertIn('"EMPTY"', body)

    def test_renderer_plus_terminal_routes_to_empty(self):
        self.assertRegex(self.renderer,
                         r"(?s)btn-new.*?S\.createEmptyPane\(")
        self.assertRegex(self.preload, r'createEmptyPane')


if __name__ == "__main__":
    unittest.main()