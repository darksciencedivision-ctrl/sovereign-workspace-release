"""
FIXUP-01 F-6 — the regression guard for the whole defect class.

Three defects reached the operator's screen through fully green suites: the Token Center panel
(N-21), llamacpp vanishing from the UI (N-22), and an Open button enabled only on the one module
that could not open anything (N-23). Every gate passed, because every gate compares configuration
with configuration — the adapter is valid, the schema admits it, the header is correct, the loader
loads it. Not one of them asked whether the running product does the thing.

The shape they share is precise: **the rendered page is never compared with what the shell says
about itself.** So that is what this file compares, generically, over the real DOM of the real
page served by the real shell. It names no module and hardcodes no card list; it derives
everything from `/api/state`, so it catches the next instance rather than the last three.

  test_rendered_cards_match_the_shells_own_module_list          (the N-22 class)
  test_no_enabled_control_exceeds_the_modules_declared_capability (the N-23 class)
  test_the_embed_region_always_shows_the_frame_or_the_fallback  (the N-21 class)

The per-defect proofs live beside their fixes — test_module_visibility.py, test_open_capability.py
and test_tokencenter_embed.py. This file is the invariant they are instances of, and it is the
item the directive says must not be treated as optional.
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

# States in which the shell will accept each action, per SWS-UI-001 v1.2 §7.3(2). The rendered
# page must not offer an action outside these, and must not offer one the module cannot perform.
STARTABLE = {"NOT_STARTED", "STOPPED", "FAILED", "CONFIG_ERROR"}
STOPPABLE = {"READY", "STARTING", "DEGRADED"}
RESTARTABLE = {"READY", "STARTING", "DEGRADED", "FAILED", "CONFIG_ERROR"}


def _edge_path():
    for p in EDGE_CANDIDATES:
        if os.path.isfile(p):
            return p
    raise unittest.SkipTest("Microsoft Edge not present on this host")


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cards = []                 # module ids, in render order
        self.buttons = {}               # id -> {action: enabled}
        self.frame = None               # iframe.tokencenter-frame attrs
        self.fallback = None            # div.tokencenter-fallback attrs
        self.fallback_buttons = []      # (label, enabled)
        self._cur = None
        self._depth = 0
        self._in_fallback = 0
        self._btn = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if tag == "article" and "module-card" in cls:
            self._cur = a.get("data-module")
            self.cards.append(self._cur)
            self.buttons[self._cur] = {}
            self._depth = 1
            return
        if tag == "iframe" and "tokencenter-frame" in cls:
            self.frame = a
        if tag == "div" and "tokencenter-fallback" in cls:
            self.fallback = a
            self._in_fallback = 1
        elif self._in_fallback:
            self._in_fallback += 1
        if self._cur is not None:
            self._depth += 1
            if tag == "button" and a.get("data-action"):
                self.buttons[self._cur][a["data-action"]] = "disabled" not in a
        if self._in_fallback and tag == "button":
            self._btn = [a, ""]

    def handle_endtag(self, tag):
        if self._in_fallback:
            if tag == "button" and self._btn is not None:
                self.fallback_buttons.append((self._btn[1].strip(), "disabled" not in self._btn[0]))
                self._btn = None
            self._in_fallback -= 1
        if self._cur is not None:
            self._depth -= 1
            if self._depth <= 0:
                self._cur = None

    def handle_data(self, data):
        if self._btn is not None:
            self._btn[1] += data


def _load_page(port):
    edge = _edge_path()
    prof = tempfile.mkdtemp(prefix="sws-fixup01-contract-")
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
        page = _Page()
        page.feed(dom[i:])
        return page
    finally:
        shutil.rmtree(prof, ignore_errors=True)


class RenderedControlContract(unittest.TestCase):
    """One shell, one render, three invariants."""

    @classmethod
    def setUpClass(cls):
        cls.proc, cls.port, _nonce = start_shell()
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:{}/api/state".format(cls.port), timeout=10) as r:
                payload = json.loads(r.read().decode("utf-8"))
            cls.state = payload.get("modules", payload)
            cls.page = _load_page(cls.port)
        except BaseException:
            stop_shell(cls.proc)
            raise

    @classmethod
    def tearDownClass(cls):
        stop_shell(cls.proc)

    # ---- the N-22 class -------------------------------------------------
    def test_rendered_cards_match_the_shells_own_module_list(self):
        served = set(self.state)
        rendered = set(self.page.cards)
        self.assertEqual(
            served, rendered,
            "the page and the shell disagree about which modules exist.\n"
            "  loaded but never rendered: {}\n"
            "  rendered but not loaded  : {}\n"
            "A module the operator cannot see is a module they cannot act on (N-22)."
            .format(sorted(served - rendered), sorted(rendered - served)))

    # ---- the N-23 class -------------------------------------------------
    def test_no_enabled_control_exceeds_the_modules_declared_capability(self):
        """Every enabled button must be an action the shell would actually accept.

        This is the generic form of N-23: `sow.json` declared `open.kind: none`, the page
        enabled Open anyway because it derived enablement from state alone, and clicking it did
        nothing. The rule below is checked for every module and every action, so it fails for
        whichever control drifts next.
        """
        problems = []
        for mid, record in self.state.items():
            buttons = self.page.buttons.get(mid, {})
            state = record.get("state", "")
            runtime = record.get("runtime_present", True)

            def enabled(action):
                return buttons.get(action) is True

            # Open: the shell publishes the authoritative answer; the page must not disagree.
            if enabled("open") != bool(record.get("can_open")):
                problems.append(
                    "{}: Open rendered {} but the shell reports can_open={} "
                    "(open.kind={!r}, state={})".format(
                        mid, "ENABLED" if enabled("open") else "disabled",
                        record.get("can_open"), record.get("open_kind"), state))

            # Nothing may be launched without the binary the adapter names.
            if not runtime:
                for action in ("start", "restart", "test"):
                    if enabled(action):
                        problems.append(
                            "{}: {} is enabled although the declared runtime does not exist "
                            "({})".format(mid, action, record.get("runtime_path")))

            # Lifecycle actions must respect the state machine.
            if enabled("start") and state not in STARTABLE:
                problems.append("{}: Start enabled in state {}".format(mid, state))
            if enabled("stop") and state not in STOPPABLE:
                problems.append("{}: Stop enabled in state {}".format(mid, state))
            if enabled("restart") and state not in RESTARTABLE:
                problems.append("{}: Restart enabled in state {}".format(mid, state))
            if enabled("test") and state not in STARTABLE:
                problems.append("{}: Run Startup Test enabled in state {}".format(mid, state))

        self.assertEqual(problems, [],
                         "controls offered that the shell cannot perform:\n  - "
                         + "\n  - ".join(problems))

    def test_no_shipped_module_can_ever_report_an_openable_dead_control(self):
        """The state-independent half of the N-23 guard, and the reason it exists.

        The DOM check above compares the page against `can_open` for the states that happen to
        exist while the test runs - which, on a cold shell, is STOPPED for everything. N-23 only
        appears in READY. A guard that can only see the current render would have passed while
        the defect sat one state transition away; this run exists because exactly that kind of
        green test let five defects through.

        So this sweeps every SHIPPED adapter across the whole state vocabulary and asserts the
        invariant directly: a module may report `can_open` only if it declares an open action
        the shell can actually perform. No module is started to do it.
        """
        from shell.src.adapter import load_all_adapters
        from shell.src.states import (
            CONFIG_ERROR, DEGRADED, EXTERNAL, FAILED, NOT_STARTED, READY, STARTING, STOPPED,
            ModuleRunner)

        every_state = [NOT_STARTED, STOPPED, STARTING, READY, DEGRADED, FAILED, EXTERNAL,
                       CONFIG_ERROR]
        problems = []
        adapters = load_all_adapters()
        self.assertTrue(adapters, "no adapters loaded, so this guard proved nothing")

        for mid, adapter in adapters.items():
            if "error" in adapter:
                continue
            runner = ModuleRunner(mid, adapter, supervisor=None)
            block = adapter.get("open") or {}
            kind = block.get("kind")
            performable = kind == "focus_window" or (kind == "browser" and block.get("url"))
            for state in every_state:
                runner.state = state
                if runner.can_open() and not performable:
                    problems.append(
                        "{}: reports can_open in state {} but declares open.kind={!r} url={!r} - "
                        "that is an enabled control wired to nothing".format(
                            mid, state, kind, block.get("url")))

        self.assertEqual(problems, [],
                         "modules that would offer a dead Open control:\n  - "
                         + "\n  - ".join(problems))

    # ---- the N-21 class -------------------------------------------------
    def test_the_embed_region_always_shows_the_frame_or_the_fallback(self):
        """OP-4 named one forbidden end state: a blank rectangle. Exactly one of the two halves
        of the embed is visible at all times, and whichever it is carries real content."""
        self.assertIsNotNone(self.frame_or_fail(), "no Token Center iframe was rendered")
        self.assertIsNotNone(self.page.fallback, "no Token Center fallback region was rendered")

        frame_hidden = "hidden" in self.page.frame
        fallback_hidden = "hidden" in self.page.fallback

        self.assertFalse(
            frame_hidden and fallback_hidden,
            "OP-4 forbidden state: the frame is hidden AND the fallback is hidden, so the panel "
            "is a blank rectangle with no status and no control")
        self.assertFalse(
            (not frame_hidden) and (not fallback_hidden),
            "both halves of the embed are visible at once; the panel is showing the module and "
            "an error about the module simultaneously")

        if frame_hidden:
            # The fallback is carrying the panel: it must offer an action, not just prose.
            enabled = [label for label, on in self.page.fallback_buttons if on]
            self.assertTrue(
                enabled,
                "the fallback is the only visible half and offers no enabled control; the "
                "operator is shown a dead panel")
        else:
            # The frame is carrying the panel: it must be pointed somewhere.
            self.assertTrue(
                self.page.frame.get("src"),
                "the frame is visible with no src, which renders as a blank rectangle")

    def frame_or_fail(self):
        return self.page.frame


if __name__ == "__main__":
    unittest.main()
