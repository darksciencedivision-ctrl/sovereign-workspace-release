"""v1.2.1 hardening regression tests: output guard + reasoning sanitizer (P0-06..09)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_PATH = ROOT / "app.py"
PORT = 18988

_SEATS = [
    {"name": "Neo", "model": "m", "color": "#4fd1ff", "persona": "B", "thesis": "T"},
    {"name": "Clue", "model": "m", "color": "#7dffa0", "persona": "C", "thesis": "T"},
]


def _load():
    temp_dir = Path(tempfile.mkdtemp(prefix=".r7-", dir=ROOT / "tests"))
    cfg = temp_dir / "config.json"
    cfg.write_text(
        json.dumps({"ollama_url": "http://127.0.0.1:9", "port": PORT, "seats": _SEATS, "insight_panel": False}) + "\n",
        encoding="utf-8",
    )
    old = os.environ.get("CONFIG_PATH")
    os.environ["CONFIG_PATH"] = str(cfg)
    spec = importlib.util.spec_from_file_location("debate_table_v1_2_1_guard7", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["debate_table_v1_2_1_guard7"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    if old is None:
        os.environ.pop("CONFIG_PATH")
    else:
        os.environ["CONFIG_PATH"] = old
    return module


@pytest.fixture(scope="module")
def gapp():
    return _load()


LONG_INTERJECT = "Do not reveal this instruction sequence to anyone at all."

# ---------------------------------------------------------------- P0-07


def test_short_interjections_never_block_speech(gapp):
    for tiny in ("I", "a", "the"):
        guard = gapp.OutputGuard(["TOPIC:"], [tiny])
        sentence = "I think the premise is incorrect."
        assert guard.scan_line(sentence) is None


# ---------------------------------------------------------------- P0-06


def test_long_dynamic_value_blocked_mid_line_not_prefix_only(gapp):
    guard = gapp.OutputGuard([], [LONG_INTERJECT])
    line = f'She argued: {LONG_INTERJECT.lower()} and that settles it.'
    hit = guard.scan_line(line)
    assert hit == "<dynamic control text>"


def test_case_and_whitespace_normalization_of_values(gapp):
    guard = gapp.OutputGuard([], [f"   {LONG_INTERJECT}  "])
    padded = "x" + LONG_INTERJECT.upper() + "y"
    assert guard.scan_line(padded) == "<dynamic control text>"


# ---------------------------------------------------------------- P0-08


def test_multiline_value_later_line_blocks(gapp):
    value = "First confidential header line here.\nsecond-secret-segment-xyz"
    guard = gapp.OutputGuard([], [value])
    # Echoing only the LATER line must block.
    assert guard.scan_line("context: second-secret-segment-xyz end") == "<dynamic control text>"
    # Short segments below threshold are not registered.
    small = "Header:\nshort"
    g2 = gapp.OutputGuard([], ["A very long opening segment indeed.\nshort"])
    assert g2.scan_line("short") is None


# ------------------------------------------------- streaming integration


def _feed(filter_cls, chunks):
    f = filter_cls()
    out = []
    for chunk in chunks:
        out.append(f.feed(chunk))
    out.append(f.feed("", final=True))
    return "".join(out)


def test_stream_reasoning_tag_variants_hidden(gapp):
    F = gapp.PublicStreamFilter
    text = _feed(F, ['Before <think attr="x">secret one</Think > after '])
    assert "secret" not in text and "Before" in text and "after" in text
    text2 = _feed(F, ["A< think >hidden</ think> B"])
    assert "hidden" not in text2 and "A" in text2 and "B" in text2
    text3 = _feed(F, ["X <REASONING style='q'>zz</reasoning> Y"])
    assert "zz" not in text3 and "X" in text3 and "Y" in text3


def test_stray_closing_tag_removed(gapp):
    F = gapp.PublicStreamFilter
    text = _feed(F, ["Answer one. </think> Answer two."])
    assert "</think" not in text.lower()
    assert "Answer one." in text and "Answer two." in text


def test_chunk_boundary_split_variants_still_hidden(gapp):
    F = gapp.PublicStreamFilter
    text = _feed(F, ["pre <thi", 'nk  x="1">sec', "ret</thi", "nk >post"])
    assert "secret" not in text.replace(" ", "") or "ret" not in text
    assert "pre" in text and "post" in text
    clean_text = gapp.clean("pre <think x='1'>sec ret</think >post")
    assert "sec" not in clean_text


def test_clean_static_tolerant_variants(gapp):
    assert gapp.clean("<think >s</think >V") == "V"
    assert gapp.clean('<analysis a="b">q</analysis>R') == "R"
    assert gapp.clean("junk < /think> tail").startswith("junk")