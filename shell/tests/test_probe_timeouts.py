"""
FIXUP-01 F-4 / N-27 — a readiness probe must outlive the endpoint's own response time.

`http_probe` gave each request a socket timeout of `min(5, poll_ms / 1000)`. The poll interval
and the per-request timeout are unrelated quantities: one says how often to ask, the other how
long an answer may take. Conflating them meant `sovereign.json`'s `poll_ms: 500` gave
`/v1/health` — which answers HTTP 200 in about 1.25 s, because it reports on the local model
service — a 0.5 s budget. Every one of the ~90 attempts inside the 45 s window timed out at
~0.53 s and the module reported HEALTH_CHECK_FAILED with the endpoint healthy the whole time.

The important property is that this was unfixable by configuration: no value of `timeout_s`
helps, because the failure is per-request, not cumulative. Raising the module's timeout to make
a red probe green would have been the S-12 error the directive forbids, and it would not have
worked anyway. test_raising_the_overall_timeout_does_not_rescue_a_short_request_timeout pins
that, so nobody "fixes" a future instance of this by adding seconds to an adapter.
"""
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from shell.src import probe as probe_mod
from shell.tests._harness import free_port

# Comfortably longer than the 0.5 s the old code allowed, comfortably shorter than the new cap.
RESPONSE_DELAY_S = 1.25


def _slow_handler(delay):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(delay)
            body = b'{"status": "degraded", "product_version": "3.1.2"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_a):
            pass
    return Handler


class SlowEndpoint:
    """A loopback endpoint that answers 200, but not instantly — like SOVEREIGN's /v1/health."""

    def __init__(self, delay=RESPONSE_DELAY_S):
        self.port = free_port()
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), _slow_handler(delay))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self):
        return "http://127.0.0.1:{}/v1/health".format(self.port)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class TestReadinessProbeToleratesASlowHealthyEndpoint(unittest.TestCase):

    def setUp(self):
        self.endpoint = SlowEndpoint()
        self.addCleanup(self.endpoint.close)

    def test_endpoint_slower_than_the_poll_interval_still_reaches_ready(self):
        """SOVEREIGN's exact shape: poll_ms 500 against a ~1.25 s endpoint."""
        ok, elapsed, err = probe_mod.http_probe(
            self.endpoint.url, expect_status=200, timeout_s=15, poll_ms=500)
        self.assertTrue(
            ok,
            "readiness failed against an endpoint that answers 200 in ~{:.2f}s; last error "
            "{!r}. The per-request timeout is being derived from poll_ms again (N-27)."
            .format(RESPONSE_DELAY_S, err))
        self.assertEqual(err, "")
        self.assertLess(elapsed, 15, "probe returned success only after the whole budget")

    def test_raising_the_overall_timeout_does_not_rescue_a_short_request_timeout(self):
        """The non-fix the directive forbids, demonstrated as a non-fix (S-12).

        With the defect present, every request dies at the socket timeout, so a longer
        `timeout_s` only buys more identical failures. This test asserts the probe succeeds
        QUICKLY — roughly one response time — which a short per-request timeout cannot do at
        any `timeout_s`.
        """
        started = time.time()
        ok, _elapsed, err = probe_mod.http_probe(
            self.endpoint.url, expect_status=200, timeout_s=120, poll_ms=500)
        took = time.time() - started
        self.assertTrue(ok, "probe still fails with a 120 s budget; last error {!r}".format(err))
        self.assertLess(
            took, 10,
            "the probe took {:.1f}s to accept a {:.2f}s endpoint: it is succeeding by accident "
            "rather than by waiting for the answer".format(took, RESPONSE_DELAY_S))

    def test_a_refused_port_still_fails_fast_and_reports_why(self):
        """The longer request timeout must not slow down honest failure: a closed port is
        refused by the OS immediately, it does not wait for the cap."""
        dead = "http://127.0.0.1:{}/v1/health".format(free_port())
        started = time.time()
        ok, _elapsed, err = probe_mod.http_probe(
            dead, expect_status=200, timeout_s=3, poll_ms=500)
        took = time.time() - started
        self.assertFalse(ok, "probe reported ready against a port nothing is listening on")
        self.assertTrue(err, "a failed probe must carry the reason it failed")
        self.assertLess(took, 10, "a refused connection should not consume the request cap")

    def test_request_timeout_is_bounded_by_the_remaining_budget(self):
        """One attempt can never wait past the deadline the adapter declared."""
        deadline = time.time() + 2.0
        self.assertLessEqual(probe_mod._request_timeout(deadline), 2.0 + 1e-6)
        far = time.time() + 10_000
        self.assertEqual(probe_mod._request_timeout(far), probe_mod.HTTP_REQUEST_TIMEOUT_CAP_S)
        past = time.time() - 5
        self.assertEqual(probe_mod._request_timeout(past), probe_mod.HTTP_REQUEST_TIMEOUT_FLOOR_S)


if __name__ == "__main__":
    unittest.main()
