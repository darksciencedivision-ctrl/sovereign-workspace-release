"""Sharded inference P1: exact prompt-token counting on the llama.cpp path.

The first SW-27 qualification found the usable prompt capped at ~8k tokens with a 40960-token window:
capacity was checked with a conservative one-token-per-UTF-8-byte bound (~4x a real tokenizer).
Shards must be sized from real token counts, so on llama.cpp the client now renders the conversation
through the model's own chat template (`/apply-template`) and counts it with the model's own
tokenizer (`/tokenize`). Failure injection: either endpoint failing, returning junk, or tools being
attached (the template endpoint cannot see tool schemas) - each falls back to the conservative bound,
never to an optimistic guess.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product.llama_cpp_client import LlamaCppClient  # noqa: E402
from sovereign_product.model_client import ModelCapabilityError  # noqa: E402

TEMPLATED = "<|im_start|>user\nhello<|im_end|>\n<|im_start|>assistant\n"


class _Response:
    def __init__(self, status: int, payload):
        self.status_code = status
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def close(self):
        pass


class _Session:
    """Routes by path; records every request body."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.trust_env = False

    def request(self, method, url, json=None, **kwargs):
        path = url.split("127.0.0.1:18080", 1)[1]
        self.calls.append((method, path, json))
        route = self.routes.get(path)
        if route is None:
            return _Response(404, {"error": "no route"})
        return route(json) if callable(route) else route


def _client(routes):
    session = _Session(routes)
    return LlamaCppClient("http://127.0.0.1:18080", api_key="k", session=session), session


def _models(ctx=40960):
    return _Response(200, {"data": [{"id": "qwen3:14b", "meta": {"n_ctx_train": ctx},
                                     "status": {"args": ["--ctx-size", str(ctx)]}}]})


def test_si_p1_counts_the_templated_prompt_with_the_models_tokenizer():
    client, session = _client({
        "/apply-template": _Response(200, {"prompt": TEMPLATED}),
        "/tokenize": _Response(200, {"tokens": list(range(9))}),
    })
    count = client.count_prompt_tokens("qwen3:14b", [{"role": "user", "content": "hello"}],
                                       think=False)
    assert count == 9
    (_, p1, body1), (_, p2, body2) = session.calls
    assert p1 == "/apply-template" and body1["model"] == "qwen3:14b"
    assert body1["chat_template_kwargs"] == {"enable_thinking": False}
    assert p2 == "/tokenize" and body2 == {"model": "qwen3:14b", "content": TEMPLATED,
                                           "add_special": True}


@pytest.mark.parametrize("routes", [
    {"/apply-template": _Response(500, {"error": "boom"})},
    {"/apply-template": _Response(200, {"prompt": TEMPLATED}),
     "/tokenize": _Response(400, {"error": "model name is missing"})},
    {"/apply-template": _Response(200, {"nope": 1})},
    {"/apply-template": _Response(200, {"prompt": TEMPLATED}),
     "/tokenize": _Response(200, ValueError("not json"))},
    {"/apply-template": _Response(200, {"prompt": TEMPLATED}),
     "/tokenize": _Response(200, {"tokens": "many"})},
])
def test_si_p1_any_counting_failure_returns_none_not_a_guess(routes):
    client, _ = _client(routes)
    assert client.count_prompt_tokens("qwen3:14b", [{"role": "user", "content": "x"}]) is None


def test_si_p1_exact_count_replaces_the_byte_bound_in_the_capacity_check():
    client, _ = _client({"/v1/models": _models(40960)})
    prompt = "x" * 60_000  # 60000 bytes: the byte bound alone would refuse this outright
    with pytest.raises(ModelCapabilityError, match="input bound \\(60000\\)"):
        client._resolve_generation_capacity(model="qwen3:14b", prompt=prompt,
                                            options={"num_ctx": 40960, "num_predict": 4096},
                                            system=None, response_format=None)
    resolved, capacity = client._resolve_generation_capacity(
        model="qwen3:14b", prompt=prompt, options={"num_ctx": 40960, "num_predict": 4096},
        system=None, response_format=None, exact_input_tokens=15_000)
    assert capacity["input_count"] == "exact" and capacity["input_bound"] == 15_000
    assert resolved["num_predict"] == 4096


def test_si_p1_exact_count_still_refuses_a_prompt_that_truly_does_not_fit():
    client, _ = _client({"/v1/models": _models(40960)})
    with pytest.raises(ModelCapabilityError, match="leaves no generation capacity"):
        client._resolve_generation_capacity(
            model="qwen3:14b", prompt="x", options={"num_ctx": 40960, "num_predict": 4096},
            system=None, response_format=None, exact_input_tokens=40_500)


class _Stop(Exception):
    pass


def _capture_capacity(client, monkeypatch):
    seen = {}

    def fake_resolve(**kwargs):
        seen.update(kwargs)
        raise _Stop()

    monkeypatch.setattr(client, "_resolve_generation_capacity", fake_resolve)
    return seen


def test_si_p1_chat_uses_the_exact_count(monkeypatch):
    client, _ = _client({})
    monkeypatch.setattr(client, "count_prompt_tokens", lambda model, messages, think=None: 1234)
    seen = _capture_capacity(client, monkeypatch)
    with pytest.raises(_Stop):
        client.chat(model="qwen3:14b", messages=[{"role": "user", "content": "hi"}],
                    options={"num_ctx": 8192, "num_predict": 512})
    assert seen["exact_input_tokens"] == 1234


def test_si_p1_tools_keep_the_conservative_bound(monkeypatch):
    client, _ = _client({})
    called = []
    monkeypatch.setattr(client, "count_prompt_tokens",
                        lambda *a, **k: called.append(1) or 1234)
    seen = _capture_capacity(client, monkeypatch)
    with pytest.raises(_Stop):
        client.chat(model="qwen3:14b", messages=[{"role": "user", "content": "hi"}],
                    options={"num_ctx": 8192, "num_predict": 512},
                    tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}])
    assert seen["exact_input_tokens"] is None and called == []


def test_si_p1_no_context_budget_means_no_counting_call(monkeypatch):
    client, _ = _client({})
    called = []
    monkeypatch.setattr(client, "count_prompt_tokens", lambda *a, **k: called.append(1) or 1)
    seen = _capture_capacity(client, monkeypatch)
    with pytest.raises(_Stop):
        client.chat(model="qwen3:14b", messages=[{"role": "user", "content": "hi"}])
    assert called == [] and seen["exact_input_tokens"] is None


def test_si_p1_tokenize_paths_are_allowed_and_ollama_paths_still_refused():
    client, _ = _client({"/tokenize": _Response(200, {"tokens": []})})
    client._request("POST", "/tokenize", json_body={"model": "m", "content": ""})
    from sovereign_product.model_client import ModelClientError
    with pytest.raises(ModelClientError, match="refuses native Ollama path"):
        client._request("POST", "/api/generate", json_body={})
