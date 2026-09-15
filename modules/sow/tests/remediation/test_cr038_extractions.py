"""CR-038 — behavior-preserving extraction of a pure phase from a large orchestration function,
pinned by a characterization test. Here: _normalize_response_format, extracted verbatim from
OllamaClient.generate (which dropped from 124 to 110 branch points)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SOV = Path(__file__).resolve().parents[4] / "modules" / "sovereign" / "sovereign_product"
if str(SOV) not in sys.path:
    sys.path.insert(0, str(SOV))

import model_client as mc  # noqa: E402


def test_cr038_none_and_json_string():
    assert mc._normalize_response_format(None) is None
    assert mc._normalize_response_format("json") == "json"


def test_cr038_invalid_string_rejected():
    with pytest.raises(ValueError):
        mc._normalize_response_format("xml")


def test_cr038_mapping_is_copied_and_validated():
    src = {"type": "object", "properties": {"a": {"type": "string"}}, "nums": [1, 2.5, True, None]}
    out = mc._normalize_response_format(src)
    assert out == src and out is not src  # a copy, not the caller's object


def test_cr038_non_string_key_rejected():
    with pytest.raises(ValueError):
        mc._normalize_response_format({1: "x"})


def test_cr038_non_finite_float_rejected():
    with pytest.raises(ValueError):
        mc._normalize_response_format({"v": float("inf")})


def test_cr038_non_json_value_rejected():
    with pytest.raises(ValueError):
        mc._normalize_response_format({"v": object()})


def test_cr038_non_mapping_type_rejected():
    with pytest.raises(TypeError):
        mc._normalize_response_format(12345)


def test_cr038_generate_still_uses_the_extraction(tmp_path):
    # end-to-end: a bad response_format is rejected by generate() via the extracted helper,
    # identical to before the extraction.
    client = mc.OllamaClient(session=object())
    with pytest.raises(ValueError):
        client.generate(model="m", prompt="hi", options={}, response_format="xml")
