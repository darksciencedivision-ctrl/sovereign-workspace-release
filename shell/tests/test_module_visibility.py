"""
FIXUP-01 F-2 / S-17 — every module the shell loads is a module the operator can see.

N-22: `shell/static/app.js` carried a hardcoded five-entry MODULES array while
`load_all_adapters()` loaded six adapters. The sixth (llamacpp) was served in `/api/state`,
printed in the shell's own startup line, and rendered nowhere. Nothing failed, because every
existing proof compares configuration against configuration: the adapter is valid, the schema
admits it, the loader loads it. No test ever asked whether it reaches the screen.

That is the assertion this file makes, against the rendered DOM:

  test_every_loaded_module_has_a_card
      The set of module ids in /api/state equals the set of data-module cards in the rendered
      page. A backend module with no card fails here, whichever module it is.

  test_absent_optional_runtime_is_present_and_unavailable
      llamacpp's runtime ships in no release archive (R2 §3), so the binary is legitimately
      missing. The card must still exist, must NAME the missing path, and must not offer Start.
      "Present and unavailable, never absent" is the requirement; this pins all three halves.
      This is also where OBS-2 becomes visible to a human: the optional-adapter skip is now a
      readable line on a card instead of a silent gap.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import urllib.request
from html.parser import HTMLParser

from shell.tests._harness import start_shell, stop_shell

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _edge_path():
    for p in EDGE_CANDIDATES:
        if os.path.isfile(p):
            return p
    raise unittest.SkipTest("Microsoft Edge not present on this host")


class _Cards(HTMLParser):
    """Card ids, their visible text, and their action-button states."""

    def __init__(self):
        super().__init__()
        self.order = []
        self.text = {}
        self.buttons = {}
        self._cur = None
        self._depth = 0
        self._btn = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "article" and "module-card" in a.get("class", ""):
            self._cur = a.get("data-module")
            self.order.append(self._cur)
            self.text[self._cur] = []
            self.buttons[self._cur] = {}
            self._depth = 1
            return
        if self._cur is None:
            return
        self._depth += 1
        if tag == "button" and a.get("data-action"):
            self._btn = a
        if tag == "button" and a.get("data-action"):
            self.buttons[self._cur][a["data-action"]] = "disabled" in a

    def handle_endtag(self, tag):
        if self._cur is None:
            return
        if tag == "button":
            self._btn = None
        self._depth -= 1
        if self._depth <= 0:
            self._cur = None

    def handle_data(self, data):
        if self._cur is not None:
            self.text[self._cur].append(data)

    def visible(self, mid):
        return " ".join("".join(self.text.get(mid, [])).split())


def _render_cards(port):
    edge = _edge_path()
    prof = tempfile.mkdtemp(prefix="sws-fixup01-vis-")
    try:
        cp = subprocess.run(
            [edge, "--headless=new", "--disable-gpu", "--no-first-run",
             "--user-data-dir=" + prof, "--virtual-time-budget=8000",
             "--dump-dom", "http://127.0.0.1:{}/".format(port)],
            capture_output=True, timeout=120)
        dom = cp.stdout.decode("utf-8", "replace")
        i = dom.find("<!doctype")
        if i < 0:
            i = dom.find("<html")
        if i < 0:
            raise AssertionError("dump-dom produced no HTML document")
        parsed = _Cards()
        parsed.feed(dom[i:])
        return parsed
    finally:
        shutil.rmtree(prof, ignore_errors=True)


def _api_state(port):
    with urllib.request.urlopen(
            "http://127.0.0.1:{}/api/state".format(port), timeout=10) as r:
        payload = json.loads(r.read().decode("utf-8"))
    return payload.get("modules", payload)


class TestEveryLoadedModuleIsVisible(unittest.TestCase):

    def test_every_loaded_module_has_a_card(self):
        proc, port, _nonce = start_shell()
        try:
            served = set(_api_state(port).keys())
            cards = _render_cards(port)
        finally:
            stop_shell(proc)

        rendered = set(cards.order)
        self.assertEqual(
            served, rendered,
            "modules the shell loaded but never rendered: {}\n"
            "cards rendered for modules the shell does not serve: {}".format(
                sorted(served - rendered), sorted(rendered - served)))

    def test_absent_optional_runtime_is_present_and_unavailable(self):
        proc, port, _nonce = start_shell()
        try:
            state = _api_state(port)
            cards = _render_cards(port)
        finally:
            stop_shell(proc)

        self.assertIn("llamacpp", state, "the optional llamacpp adapter is no longer loaded")
        record = state["llamacpp"]
        self.assertFalse(
            record["runtime_present"],
            "this host now HAS a llama.cpp runtime, so the absent-runtime path is untested here")
        missing = record["runtime_path"]
        self.assertTrue(missing, "the adapter declares no runtime path to report")

        # Present.
        self.assertIn("llamacpp", cards.order,
                      "llamacpp is loaded by the shell but renders no card (N-22)")
        # ...and honestly unavailable, naming the path.
        shown = cards.visible("llamacpp")
        self.assertIn("Runtime not installed", shown,
                      "the card does not say the runtime is missing; got: {!r}".format(shown))
        self.assertIn(missing, shown,
                      "the card does not name the missing runtime path the operator must supply")
        # ...and it does not offer an action it cannot perform.
        self.assertTrue(cards.buttons["llamacpp"].get("start"),
                        "Start is enabled for a module whose binary does not exist")
        self.assertFalse(cards.buttons["llamacpp"].get("logs", True),
                         "Logs must stay reachable so the operator can inspect the module")


if __name__ == "__main__":
    unittest.main()
