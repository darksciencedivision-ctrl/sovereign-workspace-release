"""P2 SOW ingress: F-016 (loopback no-proxy) and R06 (replay retention).

F-016: SOW loopback HTTP clients issued requests through urllib's default opener, which honours a
       configured environment/registry proxy that does NOT auto-exclude dotted loopback -- so an
       Ollama/app-control call (and, for sovereign_tools, its bearer token) could be routed through
       the proxy. Each client now uses an empty-ProxyHandler opener.
R06: the replay cache expired a record one freshness window after first receipt, but a future-
     skewed envelope stays fresh until ts + window (up to TWO windows after first seen), so the
     identical signed envelope was accepted again once its record expired. Retention is now two
     windows.
"""
from __future__ import annotations

import threading
import unittest
import urllib.request
from unittest import mock

from control_plane.ipc import gateway
from control_plane.ipc import envelope as env
import adapters.detect as detect
import adapters.base.backend as backend
import adapters.local.llamacpp as llamacpp
import adapters.local.conductor_tools as conductor_tools
from mcp_server import sovereign_tools
import tools.live.enumerate_pane_picker as enumerate_pane_picker


class F016_LoopbackNoProxy(unittest.TestCase):
    MODULES = [detect, backend, llamacpp, conductor_tools, sovereign_tools, enumerate_pane_picker]

    def test_every_loopback_client_has_a_proxy_free_opener(self) -> None:
        for module in self.MODULES:
            opener = getattr(module, "_NO_PROXY_OPENER", None)
            self.assertIsNotNone(opener, f"{module.__name__} has no _NO_PROXY_OPENER")
            active = [h for h in opener.handlers
                      if isinstance(h, urllib.request.ProxyHandler) and h.proxies]
            self.assertEqual(active, [], f"{module.__name__} opener carries an active proxy")


class R06_ReplayRetention(unittest.TestCase):
    def _fresh_gateway_replay(self):
        fake = type("F", (), {})()
        fake._replay_seen = {}
        fake._replay_lock = threading.Lock()
        fake._remember_or_reject = gateway.IpcGateway._remember_or_reject.__get__(fake, type(fake))
        return fake

    def test_a_future_skewed_replay_is_refused_past_one_window(self) -> None:
        g = self._fresh_gateway_replay()
        w = env.FRESHNESS_WINDOW_S
        with mock.patch.object(gateway.time, "monotonic") as clock:
            clock.return_value = 0.0
            self.assertTrue(g._remember_or_reject("nodeA", "msg1"))   # first receipt
            # One window later, the record must STILL be present (a future-skewed message can stay
            # fresh until ts + window = up to two windows after first receipt).
            clock.return_value = w + 1
            self.assertFalse(g._remember_or_reject("nodeA", "msg1"),
                             "replay accepted after one window while still within freshness (R06)")

    def test_the_record_is_released_after_two_windows(self) -> None:
        g = self._fresh_gateway_replay()
        w = env.FRESHNESS_WINDOW_S
        with mock.patch.object(gateway.time, "monotonic") as clock:
            clock.return_value = 0.0
            self.assertTrue(g._remember_or_reject("nodeA", "msg1"))
            # Past two windows the message can no longer be fresh, so the record is reclaimed.
            clock.return_value = 2 * w + 1
            self.assertTrue(g._remember_or_reject("nodeA", "msg1"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
