"""SW-20 / SW-21 / SW-22 — bounded resource use and CAS repair (system-review 2026-09-22).

  SW-20 git output is drained into a bounded tail, not buffered whole,
  SW-21 a runaway/oversized inference stream is refused with a distinct over-limit outcome, and the
        retained raw lines/events are a bounded diagnostic tail,
  SW-22 re-publishing over a CORRUPT blob repairs it instead of reporting false success, and the
        per-ref publication-lock table stays bounded.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SOW_ROOT = Path(__file__).resolve().parents[2]
if str(SOW_ROOT) not in sys.path:
    sys.path.insert(0, str(SOW_ROOT))
SOV = Path(__file__).resolve().parents[4] / "modules" / "sovereign" / "sovereign_product"
if str(SOV) not in sys.path:
    sys.path.insert(0, str(SOV))

import node_runtime.workspace.git_runner as gr  # noqa: E402
from persistence.cas import ContentAddressedStore  # noqa: E402
import model_client as mc  # noqa: E402


# -- SW-20 -----------------------------------------------------------------
class _ChunkStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)
    def read(self, n=-1):
        return self._chunks.pop(0) if self._chunks else b""
    def close(self):
        pass


def test_sw20_drain_retains_only_a_bounded_tail(monkeypatch):
    monkeypatch.setattr(gr, "_MAX_GIT_OUTPUT_BYTES", 1000)
    chunks = [bytes([65 + (i % 26)]) * 1000 for i in range(100)]  # 100_000 bytes >> ceiling
    sink: dict = {}
    gr._drain(_ChunkStream(chunks), sink)
    assert len(sink["buf"]) == 1000, "drain retained more than the ceiling (buffered whole)"
    assert sink["truncated"] is True
    assert sink["buf"] == chunks[-1], "the retained bytes are not the newest tail"


# -- SW-21 -----------------------------------------------------------------
class _StreamResp:
    status_code = 200
    def __init__(self, lines):
        self._lines = lines
    def iter_lines(self, decode_unicode=False):
        for ln in self._lines:
            yield ln
    def raise_for_status(self):
        return None
    def close(self):
        pass


class _StreamSession:
    def __init__(self, lines):
        self._lines = lines
        self.posts = 0
    def post(self, url, *a, **k):
        self.posts += 1
        return _StreamResp(self._lines)
    def get(self, *a, **k):
        raise AssertionError("unexpected GET")


def _event(text, done=False):
    import json
    ev = {"response": text, "model": "m"}
    if done:
        ev["done"] = True
        ev["done_reason"] = "stop"
    return json.dumps(ev)


def test_sw21_runaway_event_count_is_refused(monkeypatch):
    monkeypatch.setattr(mc, "_MAX_STREAM_EVENTS", 5)
    lines = [_event("x") for _ in range(20)]  # 20 events, never 'done'
    client = mc.OllamaClient(session=_StreamSession(lines))
    with pytest.raises(mc.GenerationOverLimit):
        client.generate(model="m", prompt="hi", options={})


def test_sw21_runaway_byte_size_is_refused(monkeypatch):
    monkeypatch.setattr(mc, "_MAX_RESPONSE_TEXT_BYTES", 100)
    lines = [_event("A" * 50) for _ in range(10)]  # 500 bytes of text >> 100
    client = mc.OllamaClient(session=_StreamSession(lines))
    with pytest.raises(mc.GenerationOverLimit):
        client.generate(model="m", prompt="hi", options={})


def test_sw21_diagnostic_tail_is_bounded_but_text_is_complete(monkeypatch):
    monkeypatch.setattr(mc, "_STREAM_DIAGNOSTIC_TAIL", 3)
    lines = [_event(str(i)) for i in range(9)] + [_event("!", done=True)]  # 10 events, done last
    client = mc.OllamaClient(session=_StreamSession(lines))
    resp = client.generate(model="m", prompt="hi", options={})
    assert resp.text == "012345678!"                      # full output preserved
    assert len(resp.raw_events) <= 3, "raw_events tail is not bounded"
    assert resp.telemetry["event_count"] == 10, "true event_count lost to the bounded tail"


# -- SW-22 -----------------------------------------------------------------
def test_sw22_republish_over_corrupt_blob_repairs_it(tmp_path):
    store = ContentAddressedStore(tmp_path)
    content = b"the canonical bytes"
    ref = store.put(content)
    assert store.classify(ref) == "ok"

    # Corrupt the stored blob in place.
    blob = store._path_for(ref)
    blob.write_bytes(b"tampered - wrong bytes")
    assert store.classify(ref) == "corrupt"

    # Re-publishing the correct content must REPAIR, not report false success.
    ref2 = store.put(content)
    assert ref2 == ref
    assert store.classify(ref) == "ok", "put() reported success but left the blob corrupt"
    assert store.get(ref) == content


def test_sw22_publish_lock_table_is_bounded(tmp_path):
    store = ContentAddressedStore(tmp_path)
    for i in range(50):
        store.put(f"content-{i}".encode())
    # Every blob now exists, so its per-ref lock is no longer needed and must have been dropped.
    assert len(store._publish_locks) == 0, "per-ref publication locks accumulate without bound"
