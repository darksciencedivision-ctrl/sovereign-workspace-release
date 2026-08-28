"""v1.2.1 hardening regression tests: control-heuristic corrections (Phase 7)."""

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
PORT = 19022

_SEATS = [
    {"name": "Neo", "model": "m", "color": "#4fd1ff", "persona": "B", "thesis": "T"},
    {"name": "Clue", "model": "m", "color": "#7dffa0", "persona": "C", "thesis": "T"},
]


@pytest.fixture(scope="module")
def heur_app():
    temp_dir = Path(tempfile.mkdtemp(prefix=".r10-", dir=ROOT / "tests"))
    cfg = temp_dir / "config.json"
    cfg.write_text(
        json.dumps({"ollama_url": "http://127.0.0.1:9", "port": PORT, "seats": _SEATS, "insight_panel": False}) + "\n",
        encoding="utf-8",
    )
    old = os.environ.get("CONFIG_PATH")
    os.environ["CONFIG_PATH"] = str(cfg)
    spec = importlib.util.spec_from_file_location("debate_table_v1_2_1_heur", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["debate_table_v1_2_1_heur"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    if old is None:
        os.environ.pop("CONFIG_PATH", None)
    else:
        os.environ["CONFIG_PATH"] = old
    return module


def test_directed_question_vocative_form_detected(heur_app):
    assert heur_app.detect_directed_questions(
        "Clue, why does your mechanism survive that failure?",
        "Neo",
        ["Neo", "Clue"],
    ) == {"Clue"}


def test_narrative_why_is_not_directed_question(heur_app):
    assert heur_app.detect_directed_questions(
        "Clue explained why the mechanism fails.", "Neo", ["Neo", "Clue"]
    ) == set()


def test_named_question_without_second_person_or_vocative_not_directed(heur_app):
    assert heur_app.detect_directed_questions(
        "Did Neo challenge Clue about evidence?", "Neo", ["Neo", "Clue"]
    ) == set()


def test_disagreement_boundaries_respect_tokens(heur_app):
    def window(text):
        return [{"name": "Neo", "text": text}]

    assert heur_app.disagreement_present(window("Butter improves texture.")) is False
    assert (
        heur_app.disagreement_present(window("Distributed systems attribute blame."))
        is False
    )
    assert heur_app.disagreement_present(window("Contributed but attributed.")) is False
    # Standalone register-noise singletons are deliberately NOT markers
    # (snapshot D1: they saturated every window and kept the breaker inert).
    assert heur_app.disagreement_present(window("However, this fails.")) is False
    assert heur_app.disagreement_present(window("I disagree entirely.")) is True
    assert (
        heur_app.disagreement_present(window("On the contrary, that collapses."))
        is True
    )


def test_consensus_breaker_fires_only_without_explicit_disagreement(
    heur_app, monkeypatch
):
    captured = []

    def choose(weights):
        captured.append(dict(weights))
        return "challenge"

    monkeypatch.setattr(heur_app, "_weighted_choice", choose)
    state = heur_app.state

    for index in range(4):
        state.recent_turns.append(
            {"name": "Neo", "text": f"I agree and extend point {index}."}
        )
    _k, _t, reason = heur_app.pick_move(heur_app.SEATS[0], 5)
    assert reason == "consensus_breaker:no_disagreement_in_4_turns"
    assert captured[-1]["challenge"] == 9.0  # 3.0 x consensus multiplier

    state.last_move = None
    state.recent_turns.clear()
    for index in range(4):
        state.recent_turns.append(
            {"name": "Clue", "text": f"I disagree with that framing {index}."}
        )
    _k2, _t2, reason2 = heur_app.pick_move(heur_app.SEATS[0], 6)
    assert reason2 != "consensus_breaker:no_disagreement_in_4_turns"


def test_min_turn_chars_knob_retired(heur_app):
    # S17.4 option 2: the inert knob is removed, not silently half-wired.
    assert "min_turn_chars" not in heur_app.DEFAULTS
    production = json.loads(
        (ROOT / "config.json").read_text(encoding="utf-8-sig")
    )
    assert "min_turn_chars" not in production
    # Loader tolerates its presence as an unknown key (operator leftovers).
    doc = {
        "ollama_url": "http://127.0.0.1:9",
        "min_turn_chars": 55,
        "seats": _SEATS,
        "insight_panel": False,
    }
    cfg = ROOT / "tests" / ".r10-legacy-key.json"
    cfg.write_text(json.dumps(doc) + "\n", encoding="utf-8")
    try:
        loaded = heur_app.load_config(cfg)
        assert loaded["min_turn_chars"] == 55  # passed through untouched
    finally:
        cfg.unlink(missing_ok=True)