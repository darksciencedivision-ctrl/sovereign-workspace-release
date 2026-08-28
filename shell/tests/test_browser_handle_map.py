"""G18 browser-lifecycle proof (CP-M1 Band 2).

The shell opens module UIs with window.open(rec._url, "_blank", "noopener"). Historically the
returned handle was discarded, so orphan tabs accumulated. R-01/G18 require:
  (1) the per-module handle is RETAINED in a map,
  (2) a second Open REUSES the live handle instead of spawning another tab,
  (3) when the module leaves READY/EXTERNAL the handle is CLOSED via the map,
  (4) nothing ever kills a browser process the shell did not open.

This test pins those behaviours structurally in shell/static/app.js (the renderer has no
test harness of its own; H-4/H-13 precedent is source-level assertion). Fails-before was
captured before the handle-map landed.
"""
import os
import re
import unittest

APP_JS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "shell", "static", "app.js")

import os


class TestBrowserHandleMap(unittest.TestCase):
    def setUp(self):
        with open(APP_JS, "r", encoding="utf-8-sig", errors="replace") as f:
            self.src = f.read()

    def test_handle_map_retained(self):
        self.assertRegex(self.src, r"browserHandles\s*=\s*new Map\(\)")
        self.assertRegex(self.src, r"browserHandles\.set\(")

    def test_second_open_reuses_live_handle(self):
        m = re.search(r"let h = browserHandles\.get\((\w+)\);", self.src)
        self.assertIsNotNone(m, "Open must reuse the mapped handle")
        self.assertRegex(self.src, r"h && !h\.closed \? h :")

    def test_handle_closed_when_module_leaves_ready_external(self):
        self.assertRegex(self.src, r"function closeBrowserHandle\(")
        # close-on-transition must be invoked inside applyModuleState BEFORE the
        # state map is overwritten with the new state.
        apply_block = re.search(r"function applyModuleState\(.*?\n  \}", self.src, re.S)
        self.assertIsNotNone(apply_block)
        block = apply_block.group(0)
        self.assertIn("closeBrowserHandle(id);", block)
        self.assertLess(block.index("closeBrowserHandle(id);"),
                        block.index("moduleState.set(id,"))
        block = re.search(r"function closeBrowserHandle\(.*?\n\}", self.src, re.S)
        self.assertIsNotNone(block)
        body = block.group(0)
        self.assertIn(".closed", body)
        self.assertIn(".close()", body)

    def test_no_process_kills_against_browsers(self):
        for bad in ("taskkill", "process.kill", "Stop-Process"):
            self.assertNotIn(bad, self.src)


if __name__ == "__main__":
    unittest.main()