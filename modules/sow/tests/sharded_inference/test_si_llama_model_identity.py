"""The llama.cpp client reports the model the product asked for, as Ollama does.

Live (2026-09-28, isolated stack, llama.cpp backend): every DEEP run failed at once with
"member_1 requested model 'qwen3:14b' but transport reported 'qwen3-14b'". The router answers
with its engine id (the registry's name for the served model), and DEEP's identity check compares
the reply's model with the product's model name. When the server reports exactly the engine id
the client sent, the response now names the product's model; any other reported model is still
passed through, so a wrong model is still caught.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product.llama_cpp_client import LlamaCppClient  # noqa: E402


class _Response:
    def __init__(self, status=200, payload=None, lines=()):
        self.status_code, self._payload, self._lines = status, payload, list(lines)

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None

    def iter_lines(self, decode_unicode=False):
        yield from self._lines

    def close(self):
        pass


class _Router:
    """A llama.cpp router that serves ``engine`` and names ``reported`` in its stream."""

    def __init__(self, engine, reported):
        self.engine, self.reported = engine, reported

    def request(self, method, url, json=None, **kwargs):
        if method == "GET":
            return _Response(payload={"data": [{"id": self.engine, "meta": {"n_ctx_train": 8192}}]})
        if url.endswith("/apply-template"):
            return _Response(payload={"prompt": "hi"})
        if url.endswith("/tokenize"):
            return _Response(payload={"tokens": [1, 2, 3]})
        event = {"model": self.reported,
                 "choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]}
        return _Response(lines=["data: " + _dumps(event), "data: [DONE]"])


def _dumps(value):
    return json.dumps(value)


def _chat(engine, reported):
    registry = SimpleNamespace(engine_id=lambda model: engine)
    client = LlamaCppClient("http://127.0.0.1:18080", api_key="k", registry=registry,
                            session=_Router(engine, reported))
    return client.chat(model="qwen3:14b", messages=[{"role": "user", "content": "hi"}],
                       options={"num_ctx": 4096, "num_predict": 64})


def test_the_served_engine_id_is_reported_as_the_requested_model():
    response = _chat("qwen3-14b", "qwen3-14b")
    assert response.model == "qwen3:14b"
    assert response.telemetry["reported_model"] == "qwen3-14b"  # the raw fact is kept


def test_a_different_served_model_is_still_reported_as_it_is():
    response = _chat("qwen3-14b", "qwen3-8b")
    assert response.model == "qwen3-8b"
