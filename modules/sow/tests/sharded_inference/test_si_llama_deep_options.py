"""DEEP's per-stage option resolution works on the llama.cpp client (overnight P1 finding).

Live (2026-09-29, isolated stack, llama.cpp): DEEP ran three members and was then REJECTED at the
critique stage: "critique conservative input bound (10935) plus output budget (16383) exceeds
num_ctx 16384; input must be compacted". The DEEP executor asks its client for
``resolve_generation_options`` before every stage, which clips ``num_predict`` to what physically
fits behind the prompt. The Ollama client had it; ``LlamaCppClient`` did not, so ``num_predict``
stayed at the whole window (16383) and DEEP's own conservative check rejected every stage whose
prompt was more than a few bytes on the 16k-context critic model.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product.llama_cpp_client import LlamaCppClient  # noqa: E402
from sovereign_product.model_client import (  # noqa: E402
    CONTEXT_TEMPLATE_MARGIN_TOKENS,
    ModelCapabilityError,
)


class _Response:
    def __init__(self, payload):
        self.status_code, self._payload = 200, payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass

    def close(self):
        pass


class _Router:
    """A router whose single model is served at a per-slot context of ``ctx``."""

    def __init__(self, ctx):
        self.ctx = ctx

    def request(self, method, url, json=None, **kwargs):
        return _Response({"data": [{"id": "qwen3-8b", "aliases": ["qwen3:8b"],
                                    "meta": {"n_ctx_train": self.ctx}}]})


def _client(ctx=16384):
    return LlamaCppClient("http://127.0.0.1:18080", api_key="k", session=_Router(ctx))


def test_the_client_offers_the_option_resolver_deep_asks_for():
    assert callable(getattr(_client(), "resolve_generation_options", None))


def test_num_predict_is_clipped_to_what_fits_behind_the_prompt():
    prompt = "x" * 10_000
    options = {"num_ctx": 16384, "num_predict": 16383}
    resolved = _client().resolve_generation_options(
        model="qwen3:8b", prompt=prompt, options=options, system="s")
    room = 16384 - len(prompt) - len("s") - CONTEXT_TEMPLATE_MARGIN_TOKENS
    assert resolved["num_predict"] == room
    assert resolved["num_ctx"] == 16384
    # DEEP's own gate (its bound plus the output budget must fit) now passes.
    bound = len(prompt) + len("s") + CONTEXT_TEMPLATE_MARGIN_TOKENS
    assert bound + resolved["num_predict"] <= resolved["num_ctx"]
    assert options["num_predict"] == 16383  # the caller's mapping is not modified


def test_a_prompt_that_leaves_no_room_is_refused_not_truncated():
    with pytest.raises(ModelCapabilityError):
        _client().resolve_generation_options(
            model="qwen3:8b", prompt="x" * 16_384,
            options={"num_ctx": 16384, "num_predict": 100})


def test_a_request_above_the_served_context_is_refused():
    with pytest.raises(ModelCapabilityError):
        _client().resolve_generation_options(
            model="qwen3:8b", prompt="hi", options={"num_ctx": 40960, "num_predict": 100})
