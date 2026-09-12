"""R22 — one absolute deadline bounds a generation, and blocked I/O is interrupted at it.

generate() used to check its overall timeout only BETWEEN streamed lines, with each socket read
allowed the full generation budget (a day, by default). A slow set of response headers, a partial
line that never completed, or a stalled metadata probe therefore blocked far past the intended
deadline -- the timeout fired "after an unfinished line", not at the deadline.

Now a single absolute deadline is fixed before the metadata lookup and covers the /api/show probe,
the connect, the headers and every streamed line: each socket op is capped by the time remaining,
and a watcher thread closes the active response the moment the deadline passes, interrupting a
blocked read. These tests drive each stall with a fake session and assert termination near the
deadline, not near the (much longer) simulated stall.
"""
from __future__ import annotations

import json
import sys
import threading
import time
import unittest
from pathlib import Path

import requests

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.model_client import (  # noqa: E402
    GenerationTimeout,
    OllamaClient,
)

OVERALL = 0.4          # the deadline under test
LONG_STALL = 8.0       # far longer than the deadline; must never be waited out


class _DoneStream:
    status_code = 200

    def raise_for_status(self) -> None:
        pass

    def iter_lines(self, decode_unicode: bool = False):
        yield json.dumps({"response": "hello", "done": True, "model": "m:1"})

    def close(self) -> None:
        pass


class _BlockedStream:
    """A response whose read blocks until the client closes it (as a stalled socket would)."""

    status_code = 200

    def __init__(self) -> None:
        self._closed = threading.Event()

    def raise_for_status(self) -> None:
        pass

    def iter_lines(self, decode_unicode: bool = False):
        # Block as a socket read would; when the watcher closes us, surface a closed-stream error.
        if self._closed.wait(LONG_STALL):
            raise requests.ConnectionError("stream closed by client")
        yield "unreachable"

    def close(self) -> None:
        self._closed.set()


class _Session:
    def __init__(self, *, generate=None, show_behaviour=None) -> None:
        self.trust_env = False
        self._generate = generate
        self._show_behaviour = show_behaviour
        self.calls: list[dict] = []

    def post(self, url, json=None, stream=False, timeout=None, allow_redirects=True):
        self.calls.append({"url": url, "timeout": timeout})
        if url.endswith("/api/show"):
            if self._show_behaviour is not None:
                return self._show_behaviour(timeout)
            raise AssertionError("unexpected /api/show call")
        if callable(self._generate):
            return self._generate(timeout)
        return self._generate


def _client(session: _Session) -> OllamaClient:
    return OllamaClient(
        "http://127.0.0.1:11434",
        connect_timeout=OVERALL,
        read_timeout=LONG_STALL,       # deliberately huge; the deadline must override it
        overall_timeout=LONG_STALL,
        session=session,
    )


class DeadlineBoundsStreaming(unittest.TestCase):
    def test_a_partial_line_that_never_completes_terminates_at_the_deadline(self) -> None:
        blocked = _BlockedStream()
        session = _Session(generate=lambda timeout: blocked)
        client = _client(session)
        start = time.monotonic()
        with self.assertRaises(GenerationTimeout) as ctx:
            client.generate(model="m:1", prompt="hi", overall_timeout=OVERALL)
        elapsed = time.monotonic() - start
        self.assertEqual(ctx.exception.timeout_kind, "overall")
        self.assertLess(elapsed, LONG_STALL / 2,
                        f"blocked read was not interrupted at the deadline (took {elapsed:.2f}s)")
        self.assertTrue(blocked._closed.is_set(), "the response was not closed to interrupt I/O")

    def test_the_stream_read_timeout_is_capped_by_the_remaining_budget(self) -> None:
        done = _DoneStream()
        session = _Session(generate=lambda timeout: done)
        client = _client(session)
        client.generate(model="m:1", prompt="hi", overall_timeout=OVERALL)
        gen_call = [c for c in session.calls if c["url"].endswith("/api/generate")][0]
        _connect_to, read_to = gen_call["timeout"]
        self.assertLessEqual(read_to, OVERALL + 1e-6,
                             "the streaming read timeout must not exceed the overall deadline")

    def test_a_normal_stream_still_succeeds(self) -> None:
        done = _DoneStream()
        session = _Session(generate=lambda timeout: done)
        client = _client(session)
        result = client.generate(model="m:1", prompt="hi", overall_timeout=OVERALL)
        self.assertEqual(result.text, "hello")


class DeadlineBoundsHeaders(unittest.TestCase):
    def test_slow_headers_terminate_at_the_deadline(self) -> None:
        def slow_post(timeout):
            time.sleep(OVERALL + 0.15)          # headers never arrive within budget
            raise requests.ReadTimeout("headers timed out")

        session = _Session(generate=slow_post)
        client = _client(session)
        start = time.monotonic()
        with self.assertRaises(GenerationTimeout) as ctx:
            client.generate(model="m:1", prompt="hi", overall_timeout=OVERALL)
        elapsed = time.monotonic() - start
        self.assertEqual(ctx.exception.timeout_kind, "overall")
        self.assertLess(elapsed, LONG_STALL / 2, f"took {elapsed:.2f}s")


class DeadlineBoundsMetadata(unittest.TestCase):
    def test_a_metadata_stall_is_bounded_by_the_deadline(self) -> None:
        seen: dict = {}

        def show(timeout):
            seen["timeout"] = timeout
            raise requests.ReadTimeout("model-info stalled")

        session = _Session(
            generate=lambda timeout: _DoneStream(),
            show_behaviour=show,
        )
        client = _client(session)
        # Passing num_ctx/num_predict forces the native-context (/api/show) lookup.
        with self.assertRaises(GenerationTimeout):
            client.generate(
                model="m:1", prompt="hi", overall_timeout=OVERALL,
                options={"num_ctx": 4096, "num_predict": 256},
            )
        _connect_to, read_to = seen["timeout"]
        self.assertLessEqual(read_to, OVERALL + 1e-6,
                             "the metadata read timeout must be capped by the deadline")


if __name__ == "__main__":
    unittest.main(verbosity=2)
