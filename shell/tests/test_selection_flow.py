"""G21 proof (CP-M1 Band 3): execution-type selection while EMPTY.

Pins structurally in modules/sow/apps/desktop/main.js:
  (1) the four-value execution-type vocabulary,
  (2) selection is refused from any state other than EMPTY,
  (3) a model reference is required exactly for local_model/api_model,
  (4) selection mutates only metadata (state -> CONFIGURING); it spawns nothing.
Fails-before was captured before this handler existed.
"""
import os
import re
import unittest

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAIN = os.path.join(WS, "modules", "sow", "apps", "desktop", "main.js")


def read(p):
    with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


class TestSelectionFlow(unittest.TestCase):
    def setUp(self):
        self.src = read(MAIN)
        i = self.src.index('pane:select-execution')
        b = self.src.index('const EXECUTION_TYPES')
        endm = re.search(r'\n  \}\);', self.src[b:])
        assert endm
        self.block = self.src[b: b + endm.start() + len('\n  });')]

    def test_vocabulary_is_the_four_execution_types(self):
        self.assertIn('["local_model", "api_model", "opencode", "powershell"]', self.block)

    def test_selection_refused_from_non_empty_states(self):
        self.assertIn('meta.state !== "EMPTY"', self.block)

    def test_model_required_only_for_model_backends(self):
        self.assertIn('MODEL_BACKENDS.includes(type) && !p.modelRef', self.block)

    def test_selection_spawns_nothing(self):
        for bad in ("pty.spawn", "ptyFactory(", "manager.spawn", "createPaneWithSession"):
            self.assertNotIn(bad, self.block)


if __name__ == "__main__":
    unittest.main()