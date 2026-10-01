"""DEEP rejects a llama.cpp reply that was cut off at the token limit.

The truncation check read only Ollama's ``done_reason``; llama.cpp reports ``finish_reason`` in its
telemetry, so a member answer cut off mid-sentence (finish_reason "length") was accepted as
complete. Both transports now feed the same check.
"""
from __future__ import annotations

import sys
from pathlib import Path

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product.semantic_deep import _done_reason  # noqa: E402

TRUNCATED = {"length", "max_tokens", "max_token"}


def test_llama_cpp_finish_reason_is_read_as_the_reason_the_model_stopped():
    assert str(_done_reason({"finish_reason": "length"}, {})).lower() in TRUNCATED
    assert str(_done_reason({"finish_reason": "stop"}, {})).lower() not in TRUNCATED


def test_ollama_done_reason_still_wins_and_the_terminal_event_is_the_last_resort():
    assert _done_reason({"done_reason": "length", "finish_reason": "stop"}, {}) == "length"
    assert _done_reason({}, {"done_reason": "length"}) == "length"
    assert _done_reason({}, {}) is None
