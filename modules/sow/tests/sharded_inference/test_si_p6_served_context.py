"""Sharded inference P6 fix: the client sizes work by the router's SERVED context.

Live failure: a LONG job on the real supervisor died with "native context capability is missing for
model 'qwen3.8:27b'". The llama.cpp router lists an UNLOADED preset model with only its launch args
(`status.args`: `--ctx-size 131072 ... --parallel 1`) - no `meta.n_ctx_train` - and the client read
only n_ctx_train, which is anyway the training context, not the served one. The served per-slot
context (`--ctx-size` / `--parallel`) is the limit a request must fit; the model metadata remains
the answer when no launch args are listed (single-model server).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product.llama_cpp_client import LlamaCppClient  # noqa: E402
from sovereign_product.model_client import ModelCapabilityError  # noqa: E402


class _Response:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload

    def close(self):
        pass


class _Session:
    def __init__(self, payload):
        self.payload = payload

    def request(self, method, url, **kwargs):
        assert url.endswith("/v1/models")
        return _Response(200, self.payload)


def _client(rows):
    return LlamaCppClient("http://127.0.0.1:18080", api_key="k", session=_Session({"data": rows}))


def _router_row(ctx="131072", parallel="1", *, loaded_meta=None):
    """The shape b11160's router returns for a preset model (captured live, trimmed)."""
    row = {
        "id": "qwen3_8-27b-hybrid-128k", "aliases": ["qwen3.8:27b"], "object": "model",
        "source": "preset",
        "status": {"value": "unloaded" if loaded_meta is None else "loaded",
                   "args": ["llama-server.exe", "--host", "127.0.0.1", "--port", "0",
                            "--alias", "qwen3_8-27b-hybrid-128k", "--ctx-size", ctx,
                            "--cache-type-k", "q8_0", "--n-gpu-layers", "13",
                            "--parallel", parallel]},
    }
    if loaded_meta is not None:
        row["meta"] = loaded_meta
    return row


def test_si_p6_unloaded_router_model_reports_its_served_context():
    assert _client([_router_row()]).native_context_length("qwen3.8:27b") == 131072


def test_si_p6_served_context_is_per_slot():
    assert _client([_router_row("65536", "4")]).native_context_length("qwen3.8:27b") == 16384


def test_si_p6_served_context_beats_the_training_context_once_loaded():
    row = _router_row("131072", loaded_meta={"n_ctx_train": 262144})
    assert _client([row]).native_context_length("qwen3.8:27b") == 131072


def test_si_p6_metadata_still_answers_without_launch_args():
    row = {"id": "m", "meta": {"n_ctx_train": 40960}}
    assert _client([row]).native_context_length("m") == 40960


@pytest.mark.parametrize("args", [
    ["--ctx-size", "0"],            # "from the model": not a served number
    ["--ctx-size", "lots"],
    ["--n-gpu-layers", "13"],       # no ctx at all
])
def test_si_p6_no_usable_context_is_still_refused(args):
    row = {"id": "m", "status": {"value": "unloaded", "args": args}}
    with pytest.raises(ModelCapabilityError, match="missing"):
        _client([row]).native_context_length("m")
