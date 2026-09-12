"""R23/F-016/F-109 — loopback probes and the Ollama client must never route through a configured
proxy.

A proxy set in the environment (HTTP_PROXY/HTTPS_PROXY) or the Windows registry does NOT
auto-exclude dotted loopback addresses like 127.0.0.1. urllib's default opener and a default
`requests.Session` both honour such a proxy, so without an explicit bypass a readiness/identity
probe - or a prompt to the local model - could be tunnelled through a third party.

These tests set a proxy pointing at a dead port and prove the request still reaches a real local
server (had it honoured the proxy, it would have failed connecting to the dead proxy).
"""
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if WS not in sys.path:
    sys.path.insert(0, WS)

from shell.src import probe  # noqa: E402

# A proxy that would fail every request if it were ever consulted (nothing listens here).
_DEAD_PROXY = "http://127.0.0.1:9"
_PROXY_ENV = {
    "HTTP_PROXY": _DEAD_PROXY, "HTTPS_PROXY": _DEAD_PROXY,
    "http_proxy": _DEAD_PROXY, "https_proxy": _DEAD_PROXY,
    "ALL_PROXY": _DEAD_PROXY, "all_proxy": _DEAD_PROXY,
    "NO_PROXY": "", "no_proxy": "",
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"service": "test", "ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class TestLoopbackProbeBypassesProxy(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_port
        self.url = f"http://127.0.0.1:{self.port}/"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_http_json_identity_reaches_loopback_with_proxy_set(self):
        with mock.patch.dict(os.environ, _PROXY_ENV, clear=False):
            ok, err = probe.http_json_identity(self.url, ["service", "ok"])
        self.assertTrue(ok, f"loopback probe was blocked (routed through the dead proxy?): {err}")

    def test_http_probe_reaches_loopback_with_proxy_set(self):
        with mock.patch.dict(os.environ, _PROXY_ENV, clear=False):
            ok, _elapsed, err = probe.http_probe(self.url, 200, timeout_s=5, poll_ms=100)
        self.assertTrue(ok, f"loopback readiness probe was blocked by a proxy: {err}")

    def test_http_html_identity_reaches_loopback_with_proxy_set(self):
        with mock.patch.dict(os.environ, _PROXY_ENV, clear=False):
            ok, err = probe.http_html_identity(self.url, "service")
        self.assertTrue(ok, f"loopback html probe was blocked by a proxy: {err}")

    def test_opener_carries_no_active_proxy(self):
        # Structural pin. build_opener only appends a ProxyHandler that actually defines proxy
        # methods, so a ProxyHandler({}) is (correctly) omitted entirely - the opener therefore has
        # NO proxy handler and connects direct. If a future edit reintroduced a real proxy, a
        # ProxyHandler with a non-empty `proxies` map would appear here; assert none does.
        import urllib.request
        active = [h for h in probe._NO_PROXY_OPENER.handlers
                  if isinstance(h, urllib.request.ProxyHandler) and h.proxies]
        self.assertEqual(active, [], f"opener must not carry any active proxy: {active}")


class TestOllamaClientDisablesEnvProxy(unittest.TestCase):
    """The loopback Ollama client owns its session and must opt out of environment proxies."""

    def test_self_created_session_does_not_trust_env(self):
        sys.path.insert(0, os.path.join(WS, "modules", "sovereign"))
        try:
            from sovereign_product.model_client import OllamaClient
        except Exception as exc:  # pragma: no cover - import env issue, not the property under test
            self.skipTest(f"model_client not importable in this environment: {exc}")
        client = OllamaClient(base_url="http://127.0.0.1:11434")
        self.assertFalse(client._session.trust_env,
                         "a loopback client's own session must not honour environment proxies")

    def test_injected_session_is_left_untouched(self):
        sys.path.insert(0, os.path.join(WS, "modules", "sovereign"))
        try:
            import requests
            from sovereign_product.model_client import OllamaClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"model_client not importable in this environment: {exc}")
        injected = requests.Session()
        injected.trust_env = True
        client = OllamaClient(base_url="http://127.0.0.1:11434", session=injected)
        self.assertIs(client._session, injected, "an injected session must be used as-is")
        self.assertTrue(client._session.trust_env, "the caller's session config must be respected")


if __name__ == "__main__":
    unittest.main(verbosity=2)
