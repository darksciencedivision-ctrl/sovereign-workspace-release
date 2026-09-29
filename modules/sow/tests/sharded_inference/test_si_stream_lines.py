"""Streamed model output containing U+2028, U+2029 or U+0085 no longer breaks the stream.

Live (2026-09-28, isolated stack, llama.cpp backend): a RESEARCH run failed after 1,642 s with
"llama.cpp emitted invalid streaming JSON". ``requests``' ``iter_lines(decode_unicode=True)``
splits decoded text with ``str.splitlines()``, which also breaks at U+2028, U+2029 and U+0085;
JSON leaves those characters unescaped, so one such character in the model's output cut an event
line in two. Both clients now split the raw bytes on newlines only (Ollama had the same reader).
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import requests

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import model_client as MC  # noqa: E402
from sovereign_product.llama_cpp_client import LlamaCppClient  # noqa: E402

TRICKY = "one two three\u0085four é 中"  # line separators + multi-byte text


def _response(body: bytes, status: int = 200) -> requests.Response:
    response = requests.models.Response()
    response.status_code = status
    response.raw = io.BytesIO(body)
    response.encoding = "utf-8"
    return response


def test_stream_lines_split_on_newlines_only_and_keep_bytes_whole():
    body = ("data: " + json.dumps({"t": TRICKY}, ensure_ascii=False) + "\r\n\r\ndata: [DONE]\n")
    lines = list(MC.stream_lines(_response(body.encode("utf-8"))))
    assert [line.decode("utf-8") for line in lines] == [
        "data: " + json.dumps({"t": TRICKY}, ensure_ascii=False), "", "data: [DONE]"]


def test_stream_lines_still_accept_a_transport_without_raw_chunks():
    fake = SimpleNamespace(iter_lines=lambda decode_unicode=False: iter(["a", "b"]))
    assert list(MC.stream_lines(fake)) == ["a", "b"]


class _LlamaSession:
    def request(self, method, url, json=None, **kwargs):
        if method == "GET":
            return _response(b'{"data": [{"id": "m", "meta": {"n_ctx_train": 8192}}]}')
        if url.endswith("/apply-template"):
            return _response(b'{"prompt": "hi"}')
        if url.endswith("/tokenize"):
            return _response(b'{"tokens": [1, 2, 3]}')
        event = {"model": "m", "choices": [{"delta": {"content": TRICKY},
                                            "finish_reason": "stop"}]}
        body = "data: " + _dumps(event) + "\n\ndata: [DONE]\n\n"
        return _response(body.encode("utf-8"))


def _dumps(value):
    return json.dumps(value, ensure_ascii=False)


def test_llama_cpp_output_with_line_separators_streams_intact():
    client = LlamaCppClient("http://127.0.0.1:18080", api_key="k", session=_LlamaSession())
    response = client.chat(model="m", messages=[{"role": "user", "content": "hi"}],
                           options={"num_ctx": 4096, "num_predict": 64})
    assert response.text == TRICKY


class _OllamaSession:
    def post(self, url, *args, **kwargs):
        events = [{"model": "m", "response": TRICKY},
                  {"model": "m", "response": "", "done": True, "done_reason": "stop"}]
        return _response(("\n".join(_dumps(e) for e in events) + "\n").encode("utf-8"))

    def get(self, *args, **kwargs):
        raise AssertionError("unexpected GET")


def test_ollama_output_with_line_separators_streams_intact():
    client = MC.OllamaClient(session=_OllamaSession())
    response = client.generate(model="m", prompt="hi", options={})
    assert response.text == TRICKY
