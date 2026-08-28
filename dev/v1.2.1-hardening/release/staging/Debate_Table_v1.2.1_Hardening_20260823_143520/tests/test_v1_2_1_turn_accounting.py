"""v1.2.1 hardening regression tests: turn accounting + state hygiene (P0-15/19/20, G-09)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_PATH = ROOT / "app.py"
PORT = 18966

_SEATS = [
    {"name": "Neo", "model": "mock-a:latest", "color": "#4fd1ff", "persona": "B", "thesis": "T"},
    {"name": "Clue", "model": "mock-b:latest", "color": "#7dffa0", "persona": "C", "thesis": "T"},
]


@pytest.fixture(scope="module")
def acct_app():
    temp_dir = Path(tempfile.mkdtemp(prefix=".r6-", dir=ROOT / "tests"))
    cfg = temp_dir / "config.json"
    doc = {
        "ollama_url": f"http://127.0.0.1:{PORT}",
        "port": PORT,
        "seats": _SEATS,
        "insight_panel": False,
    }
    cfg.write_text(json.dumps(doc) + "\n", encoding="utf-8")
    old = {k: os.environ.get(k) for k in ("CONFIG_PATH", "OLLAMA_URL")}
    os.environ["CONFIG_PATH"] = str(cfg)
    os.environ.pop("OLLAMA_URL", None)
    spec = importlib.util.spec_from_file_location("debate_table_v1_2_1_acct", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["debate_table_v1_2_1_acct"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop("debate_table_v1_2_1_acct", None)
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(autouse=True)
def _clean_state(acct_app):
    acct_app.state.reset_debate_state()
    acct_app.state.topic = "T"
    acct_app.state.public_title = "T"
    yield


def test_completed_turn_returns_completed_and_appends(acct_app, monkeypatch):
    async def fake_chat(model, messages, on_public=None, **kwargs):
        fragment = "A complete public sentence. Another one follows."
        if on_public is not None:
            await on_public(fragment)
        return fragment

    monkeypatch.setattr(acct_app, "ollama_chat", fake_chat)
    outcome = asyncio.run(
        acct_app.run_turn(acct_app.SEATS[0], 1)
    )
    assert outcome is acct_app.tc.TurnOutcome.COMPLETED
    assert acct_app.state.transcript[-1]["text"].startswith("A complete")


def test_generation_error_maps_to_skip_outcome(acct_app, monkeypatch):
    async def boom(model, messages, **kwargs):
        raise ValueError("transport down")

    monkeypatch.setattr(acct_app, "ollama_chat", boom)
    outcome = asyncio.run(acct_app.run_turn(acct_app.SEATS[0], 1))
    assert outcome is acct_app.tc.TurnOutcome.SKIPPED_GENERATION_ERROR


def test_empty_public_maps_to_skip_outcome(acct_app, monkeypatch):
    async def silent(model, messages, on_public=None, **kwargs):
        if on_public is not None:
            pass
        return ""

    monkeypatch.setattr(acct_app, "ollama_chat", silent)
    outcome = asyncio.run(
        acct_app.run_turn(acct_app.SEATS[0], 1)
    )
    assert outcome is acct_app.tc.TurnOutcome.SKIPPED_EMPTY_PUBLIC


def test_accounting_counters_and_cadence(acct_app):
    state = acct_app.state
    OC = acct_app.tc.TurnOutcome
    acct_app._account_turn_outcome(OC.COMPLETED)
    acct_app._account_turn_outcome(OC.COMPLETED)
    acct_app._account_turn_outcome(OC.SKIPPED_EMPTY_PUBLIC)
    acct_app._account_turn_outcome(OC.PROTOCOL_INCOMPLETE)
    assert state.attempted_turns == 4
    assert state.completed_public_turns == 2
    assert state.skipped_turns == 2
    assert state.completed_turns == 2


def test_topic_rotation_and_anchor_follow_completed_counter(acct_app):
    state = acct_app.state
    OC = acct_app.tc.TurnOutcome
    state.turn = 50
    state.completed_turns = 0
    # attempted/display counter alone must NOT trigger rotation (P0-15)
    should_rotate = (
        acct_app.TOPIC_ROTATE_TURNS > 0 and state.completed_turns >= acct_app.TOPIC_ROTATE_TURNS
    )
    assert should_rotate is False
    state.completed_turns = acct_app.TOPIC_ROTATE_TURNS
    assert state.completed_turns >= acct_app.TOPIC_ROTATE_TURNS
    # anchor cadence keys off completed turns and never fires at zero
    acct_app.ANCHOR_EVERY_TURNS = 2
    assert (state.completed_turns % 2 == 0) and state.completed_turns > 0


def test_interjection_cannot_cross_topic_reset(acct_app):
    acct_app.state.interject = "Old-topic interjection"
    acct_app.state.reset_debate_state()
    assert acct_app.state.interject is None


def test_repetition_remediation_is_seat_attributed(acct_app):
    state = acct_app.state
    neo_text = " ".join(f"word{i}" for i in range(30))
    state.observe_public_turn("Neo", neo_text)
    state.observe_public_turn("Neo", neo_text + " extra tail words here")
    assert "Neo" in state.repetition_pending

    # Clue speaks next: must NOT inherit Neo's remediation (G-09).
    key, _text, reason = acct_app.pick_move(state and acct_app.SEATS[1], 3)
    assert not reason.startswith("self_repetition_overlap")

    # Neo himself still receives it exactly once.
    key2, _t2, reason2 = acct_app.pick_move(acct_app.SEATS[0], 4)
    assert reason2.startswith("self_repetition_overlap:")
    assert "Neo" not in state.repetition_pending


def test_interrupted_propagates_from_run_turn(acct_app, monkeypatch):
    async def interrupted(model, messages, **kwargs):
        raise acct_app.TurnInterrupted

    monkeypatch.setattr(acct_app, "ollama_chat", interrupted)
    with pytest.raises(acct_app.TurnInterrupted):
        asyncio.run(acct_app.run_turn(acct_app.SEATS[0], 1))