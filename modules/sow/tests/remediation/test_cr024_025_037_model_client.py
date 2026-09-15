"""CR-024 (expired deadline restores full transport timeout), CR-025 (cancellation does not
cover model metadata lookup), CR-037 (one requests.Session shared by multiple workers)."""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

SOV = Path(__file__).resolve().parents[4] / "modules" / "sovereign" / "sovereign_product"
if str(SOV) not in sys.path:
    sys.path.insert(0, str(SOV))

import model_client as mc  # noqa: E402


# -- CR-024 ----------------------------------------------------------------
class _NoPostSession:
    def post(self, *a, **k):  # must never be reached when the budget is already zero
        raise AssertionError("POST started with a nonpositive deadline budget")

    def get(self, *a, **k):
        raise AssertionError("unexpected GET")


class _ExpiringClock:
    """First reading is the request start; every later reading is far past the deadline."""
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return 0.0 if self.calls == 1 else 1e9


def test_cr024_expired_deadline_never_starts_post_with_full_timeout():
    client = mc.OllamaClient(session=_NoPostSession(), monotonic=_ExpiringClock())
    with pytest.raises(mc.GenerationTimeout):
        # options without num_ctx/num_predict => metadata lookup is skipped, so control reaches the
        # pre-POST budget check directly. The clock has advanced past the deadline, so the remaining
        # budget is nonpositive and the request must be abandoned, never sent with a restored
        # transport timeout.
        client.generate(model="m", prompt="hi", options={}, overall_timeout=1.0)


# -- CR-025 ----------------------------------------------------------------
class _StallingResponse:
    def __init__(self):
        self.status_code = 200
        self._closed = threading.Event()

    def raise_for_status(self):
        return None

    def json(self):
        # block as a stalled /api/show body read would, until the watcher closes us
        self._closed.wait(timeout=5.0)
        raise mc.requests.ConnectionError("response closed by watcher")

    def close(self):
        self._closed.set()


class _MetadataStallSession:
    def __init__(self):
        self.show_calls = 0
        self.generate_calls = 0

    def post(self, url, *a, **k):
        if "/api/show" in url:
            self.show_calls += 1
            return _StallingResponse()
        self.generate_calls += 1
        raise AssertionError("generation POST must not run after cancel during metadata")

    def get(self, *a, **k):
        raise AssertionError("unexpected GET")


class _CancelAfterFirst:
    """False on the pre-request check, True during metadata (so we exercise the metadata path)."""
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.calls > 1


def test_cr025_cancel_during_metadata_exits_promptly():
    session = _MetadataStallSession()
    client = mc.OllamaClient(session=session, overall_timeout=60.0)
    start = time.monotonic()
    with pytest.raises(mc.GenerationCancelled):
        client.generate(
            model="m", prompt="hi",
            options={"num_ctx": 4096, "num_predict": 128},  # triggers /api/show metadata lookup
            cancel_requested=_CancelAfterFirst(),
        )
    elapsed = time.monotonic() - start
    # The watcher polls every 50 ms; cancellation must be observed during the stalled metadata
    # read, far below the 5 s stall and the 60 s overall timeout.
    assert elapsed < 2.0, f"cancel during metadata took {elapsed:.2f}s"
    assert session.show_calls == 1 and session.generate_calls == 0


# -- CR-037 ----------------------------------------------------------------
def test_cr037_default_session_is_per_thread():
    client = mc.OllamaClient()
    held: dict[int, object] = {}

    def grab(i):
        held[i] = client._session  # hold the object so its id cannot be reused by GC

    threads = [threading.Thread(target=grab, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    sessions = list(held.values())
    assert len({id(s) for s in sessions}) == 4, "workers shared one Session"
    assert all(getattr(s, "trust_env", True) is False for s in sessions)


def test_cr037_explicit_session_is_shared_as_given():
    sentinel = object.__new__(mc.requests.Session)
    client = mc.OllamaClient(session=sentinel)
    assert client._session is sentinel  # injected transport honored as-is
