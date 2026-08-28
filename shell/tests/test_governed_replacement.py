"""G22 proof (CP-M1 Band 3): governed replacement of a live session.

Pins structurally in picker/worker-spawn.js (+ main.js wiring):
  (1) the blanket refusal string is gone from every product path,
  (2) an unconfirmed replacement is refused with its own class
      ("replacement-requires-confirmation") naming selection.replaceConfirmed,
  (3) a CONFIRMED replacement calls the injected endLiveSession teardown and waits
      for the record to release before re-launching,
  (4) main.js wires endLiveSession to manager.kill - the same primitive pane:close uses.
Fails-before was captured while the old blanket refusal existed.
"""
import os
import re
import unittest

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPAWN = os.path.join(WS, "modules", "sow", "apps", "desktop", "picker", "worker-spawn.js")
MAIN = os.path.join(WS, "modules", "sow", "apps", "desktop", "main.js")


def read(p):
    with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


class TestGovernedReplacement(unittest.TestCase):
    def setUp(self):
        self.src = read(SPAWN)
        self.main = read(MAIN)

    def test_blanket_refusal_gone(self):
        self.assertNotIn("close it before launching another model into it", self.src)

    def test_unconfirmed_click_is_soft_refused_with_class(self):
        self.assertIn("replacement-requires-confirmation", self.src)
        m = re.search(r"if \(selection\.replaceConfirmed !== true\) \{", self.src)
        self.assertIsNotNone(m)

    def test_confirmed_replacement_uses_injected_teardown_then_waits(self):
        i = self.src.index("replaceConfirmed !== true")
        block = self.src[i: i + 1200]
        self.assertIn("endLiveSession(pid);", block)
        self.assertRegex(block, r"hasLiveSession\(pid\)")
        self.assertRegex(block, r"did not release within")

    def test_main_wires_endlivesession_to_manager_kill(self):
        self.assertRegex(
            self.main,
            r"endLiveSession:\s*\(paneId\)\s*=>\s*\{\s*if \(manager\) manager\.kill\(paneId\);")


if __name__ == "__main__":
    unittest.main()