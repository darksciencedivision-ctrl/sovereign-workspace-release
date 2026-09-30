"""The llama.cpp client's streaming error paths (overnight review: none was exercised).

What a job sees when the model server misbehaves mid-answer decides whether the run fails with a
clear message, keeps the partial text, or hangs: a non-SSE line, invalid JSON, an error event, a
stream that ends without a done event, read/connection timeouts, an HTTP error, a cancel, and
malformed chunks. Each must raise the documented error and carry ``partial_response``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import requests

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product.llama_cpp_client import LlamaCppClient  # noqa: E402
from sovereign_product.model_client import (  # noqa: E402
    GenerationCancelled, GenerationTimeout, ModelClientError)
from sovereign_product.runtime_contracts import InferenceProtocolError  # noqa: E402


def _event(**delta):
    return "data: " + json.dumps({"model": "qwen3-14b", "choices": [{"delta": delta}]})


DONE = "data: [DONE]"


class _Stream:
    def __init__(self, items, status=200):
        self.items, self.status_code = list(items), status
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_lines(self, decode_unicode=False):
        for item in self.items:
            if isinstance(item, BaseException):
                raise item
            yield item

    def json(self):
        return {"data": [{"id": "qwen3-14b", "aliases": ["qwen3:14b"],
                          "meta": {"n_ctx_train": 8192}}], "prompt": "p", "tokens": [1]}

    def close(self):
        self.closed = True


class _Session:
    def __init__(self, stream):
        self.stream = stream

    def request(self, method, url, json=None, **kwargs):
        if url.endswith("/v1/chat/completions"):
            return self.stream
        return _Stream([])  # models / apply-template / tokenize


def _chat(items, *, status=200, cancel=None):
    stream = _Stream(items, status)
    client = LlamaCppClient("http://127.0.0.1:18080", api_key="k", session=_Session(stream))
    kwargs = {} if cancel is None else {"cancel_requested": cancel}
    return client.chat(model="qwen3:14b", messages=[{"role": "user", "content": "hi"}],
                       options={"num_ctx": 4096, "num_predict": 64}, **kwargs)


def _fails(items, error, **kwargs):
    with pytest.raises(error) as caught:
        _chat(items, **kwargs)
    assert isinstance(caught.value.partial_response, dict)
    return caught.value


def test_a_line_that_is_not_server_sent_events_is_a_protocol_error():
    error = _fails([_event(content="par"), "hello"], InferenceProtocolError)
    assert "non-SSE" in str(error) and error.partial_response["text"] == "par"


def test_invalid_json_and_a_non_object_event_are_protocol_errors():
    assert "invalid streaming JSON" in str(_fails(["data: {oops"], InferenceProtocolError))
    assert "must be a JSON object" in str(_fails(["data: [1, 2]"], InferenceProtocolError))


def test_an_error_event_from_the_server_fails_the_call_with_its_message():
    error = _fails([_event(content="a"), "data: " + json.dumps({"error": "out of memory"})],
                   ModelClientError)
    assert "out of memory" in str(error) and error.partial_response["text"] == "a"


def test_a_stream_that_ends_without_a_done_event_keeps_the_partial_text():
    error = _fails([_event(content="par"), _event(content="tial")], InferenceProtocolError)
    assert "without a done event" in str(error) and error.partial_response["text"] == "partial"


def test_an_http_error_status_is_a_model_client_error():
    assert "HTTP error" in str(_fails([], ModelClientError, status=500))


def test_a_read_timeout_and_a_connection_timeout_are_generation_timeouts():
    error = _fails([_event(content="x"), requests.ReadTimeout("slow")], GenerationTimeout)
    assert error.timeout_kind == "read"
    error = _fails([requests.ConnectionError("Read timed out")], GenerationTimeout)
    assert error.timeout_kind == "read"


def test_a_dropped_connection_is_a_model_client_error_not_a_timeout():
    error = _fails([_event(content="x"), requests.ConnectionError("reset by peer")],
                   ModelClientError)
    assert not isinstance(error, GenerationTimeout) and "stream failed" in str(error)


def test_a_cancel_during_the_stream_raises_generation_cancelled():
    state = {"calls": 0}

    def cancel():
        state["calls"] += 1
        return state["calls"] > 3

    _fails([_event(content="a"), _event(content="b"), _event(content="c"), _event(content="d"),
            DONE], GenerationCancelled, cancel=cancel)


def test_malformed_chunks_are_protocol_errors():
    assert "must be text" in str(_fails([_event(content=5)], InferenceProtocolError))
    assert "reasoning chunk must be text" in str(
        _fails([_event(content="", reasoning_content=[1])], InferenceProtocolError))
    bad = "data: " + json.dumps({"choices": ["not an object"]})
    assert "choice must be an object" in str(_fails([bad], InferenceProtocolError))


def test_reasoning_text_and_split_tool_calls_are_assembled():
    call1 = {"index": 0, "id": "c1", "type": "function", "function": {"name": "f", "arguments": "{\"a\""}}
    call2 = {"index": 0, "function": {"arguments": ": 1}"}}
    response = _chat([_event(reasoning_content="think "), _event(content="ok"),
                      _event(tool_calls=[call1]), _event(tool_calls=[call2]), DONE])
    assert response.text == "ok" and response.reasoning == "think "
    (call,) = response.tool_calls
    assert call["id"] == "c1" and call["function"] == {"name": "f", "arguments": "{\"a\": 1}"}
