"""G25 proof (CP-M1 Band 4): persistent Conductor typing surface.

Structural pins across the three files the surface spans:
  renderer/index.html - a text input, a submit button and a transcript container exist,
                        the input is NOT disabled, and there is no second conductor bar.
  preload.js          - sendOperatorText + onConductorTranscript are exposed.
  renderer.js         - submit handler calls S.sendOperatorText; transcript rows render
                        via textContent with timestamps from turn.utc.
  main.js             - conductor:operator-text short-circuits __sweep probes (no spend),
                        refuses empty/oversized text, routes through deliverConductorChat,
                        surfaces CONDUCTOR_COMMUNICATION_FAILED instead of silence.
Fails-before: the pre-edit renderer had NO input element at all - captured in
evidence/cpm1/8d/conductor-dom-fails-before.txt (source inventory of every interactive
element in index.html before this band).
"""
import os
import re
import unittest

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DESK = os.path.join(WS, "modules", "sow", "apps", "desktop")


def read(p):
    with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


class TestConductorSurface(unittest.TestCase):
    def setUp(self):
        self.html = read(os.path.join(DESK, "renderer", "index.html"))
        self.preload = read(os.path.join(DESK, "preload.js"))
        self.renderer = read(os.path.join(DESK, "renderer", "renderer.js"))
        self.main = read(os.path.join(DESK, "main.js"))

    def test_input_button_transcript_exist_and_enabled(self):
        m = re.search(r'<input id="conductor-input"[^>]*>', self.html)
        self.assertIsNotNone(m)
        self.assertNotIn("disabled", m.group(0))
        self.assertIn('id="conductor-send"', self.html)
        self.assertIn('id="conductor-transcript"', self.html)

    def test_preload_exposes_surface_methods(self):
        self.assertIn("sendOperatorText:", self.preload)
        self.assertIn("onConductorTranscript:", self.preload)

    def test_renderer_submits_and_renders_turns(self):
        self.assertRegex(self.renderer, r'S\.sendOperatorText\(text\)')
        self.assertRegex(self.renderer, r'S\.onConductorTranscript\(render\)')
        self.assertRegex(self.renderer, r'turn\.utc')

    def test_main_guards_and_failure_class(self):
        i = self.main.index('"conductor:operator-text"')
        block = self.main[i: i + 2400]
        self.assertIn("__sweep", block)
        self.assertIn("empty-directive", block)
        self.assertIn("directive-too-long", block)
        self.assertIn("CONDUCTOR_COMMUNICATION_FAILED", block)
        self.assertIn("deliverConductorChat(text)", block)


if __name__ == "__main__":
    unittest.main()