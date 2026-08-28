from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def debate_app():
    temp_dir = Path(tempfile.mkdtemp(prefix=".v1-unit-", dir=ROOT / "tests"))
    config_path = temp_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "ollama_url": "http://127.0.0.1:9",
                "port": 18777,
                "seats": [
                    {
                        "name": "Neo",
                        "model": "mock-alpha:latest",
                        "color": "#4fd1ff",
                        "persona": "Builder",
                    },
                    {
                        "name": "Clue",
                        "model": "mock-beta:latest",
                        "color": "#7dffa0",
                        "persona": "Challenger",
                    },
                ],
                "insight_panel": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    old_config = os.environ.get("CONFIG_PATH")
    old_ollama = os.environ.get("OLLAMA_URL")
    os.environ["CONFIG_PATH"] = str(config_path)
    os.environ["OLLAMA_URL"] = "http://127.0.0.1:9"
    module_name = "debate_table_v1_unit"
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "app.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop(module_name, None)
        if old_config is None:
            os.environ.pop("CONFIG_PATH", None)
        else:
            os.environ["CONFIG_PATH"] = old_config
        if old_ollama is None:
            os.environ.pop("OLLAMA_URL", None)
        else:
            os.environ["OLLAMA_URL"] = old_ollama
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def reset_state(debate_app):
    debate_app.state.reset_debate_state()
    debate_app.state.topic = "Test topic"
    debate_app.state.topic_epoch = 1
    debate_app.state.transcript = []
    debate_app.state.turn = 0
    debate_app.state.speaker_idx = 0
    debate_app.state.generation_active = False
    debate_app.state.paused = False
    debate_app.state.shutting_down = False
    yield


def test_directed_question_detected_and_name_only_is_not(debate_app):
    assert debate_app.detect_directed_questions(
        "Clue, what evidence would change your view?", "Neo", ["Neo", "Clue"]
    ) == {"Clue"}
    assert debate_app.detect_directed_questions(
        "Clue made the strongest claim.", "Neo", ["Neo", "Clue"]
    ) == set()


def test_directed_question_precedence_and_consumption(debate_app):
    debate_app.state.pending_questions["Clue"].append("Neo")
    debate_app.state.repetition_pending = {"Clue": 0.91}
    for index in range(4):
        debate_app.state.recent_turns.append({"name": "Neo", "text": f"agreement {index}"})
    key, _text, reason = debate_app.pick_move(debate_app.SEATS[1], 5)
    assert key == "answer-then-advance"
    assert reason == "directed_question_from:Neo"
    assert not debate_app.state.pending_questions["Clue"]


def unique_words(prefix: str, count: int) -> str:
    return " ".join(f"{prefix}{index}" for index in range(count))


def test_repetition_above_and_below_threshold(debate_app):
    first = unique_words("word", 25)
    repeated = first + " additional"
    unrelated = unique_words("different", 25)
    assert debate_app.repetition_overlap(first, repeated, 20) >= 0.60
    assert debate_app.repetition_overlap(first, unrelated, 20) == 0


def test_repetition_short_turn_exemption(debate_app):
    text = unique_words("tiny", 8)
    assert debate_app.repetition_overlap(text, text, 20) == 0


def test_repetition_forces_deterministic_alternation(debate_app):
    # G-09: remediation is per-seat; alternation/consumption preserved for
    # the seat that caused it (cross-seat inheritance is separately proven
    # forbidden in the v1.2.1 turn-accounting suite).
    debate_app.state.repetition_pending = {"Neo": 0.75}
    first = debate_app.pick_move(debate_app.SEATS[0], 2)
    debate_app.state.repetition_pending["Neo"] = 0.82
    second = debate_app.pick_move(debate_app.SEATS[0], 3)
    assert (first[0], second[0]) == ("reframe", "challenge")
    assert first[2] == "self_repetition_overlap:0.75"
    assert second[2] == "self_repetition_overlap:0.82"
    assert debate_app.state.repetition_pending == {}


def test_consensus_breaker_on_and_off(debate_app, monkeypatch):
    captured = []

    def choose(weights):
        captured.append(weights)
        return "challenge"

    monkeypatch.setattr(debate_app, "_weighted_choice", choose)
    for index in range(4):
        debate_app.state.recent_turns.append(
            {"name": "Neo", "text": f"I agree and extend point {index}."}
        )
    _key, _text, reason = debate_app.pick_move(debate_app.SEATS[0], 5)
    assert reason == "consensus_breaker:no_disagreement_in_4_turns"
    assert captured[-1]["challenge"] == 9.0

    debate_app.state.last_move = None
    debate_app.state.recent_turns.clear()
    # Adapted (v1.2.1 Phase 7): bare "however" is register-noise, not a
    # disagreement marker; explicit phrase preserves the OFF-path regression.
    for text in ("I agree.", "I disagree with that step.", "Continue.", "Extend."):
        debate_app.state.recent_turns.append({"name": "Neo", "text": text})
    _key, _text, reason = debate_app.pick_move(debate_app.SEATS[0], 6)
    assert reason == "weighted_fallback"
    assert captured[-1]["challenge"] == 3.0


def test_fallback_before_full_consensus_window(debate_app, monkeypatch):
    monkeypatch.setattr(debate_app, "_weighted_choice", lambda _weights: "analyze")
    debate_app.state.recent_turns.append({"name": "Neo", "text": "Agreed."})
    key, _text, reason = debate_app.pick_move(debate_app.SEATS[0], 1)
    assert key == "analyze"
    assert reason == "weighted_fallback"


def test_turn_start_event_has_move_reason(debate_app, monkeypatch):
    events = []

    async def send(event):
        events.append(event)

    async def chat(_model, _messages, on_public=None, **_kwargs):
        if on_public:
            await on_public("Public response with enough substance.")
        return "Public response with enough substance."

    monkeypatch.setattr(debate_app.hub, "send", send)
    monkeypatch.setattr(debate_app, "ollama_chat", chat)
    asyncio.run(debate_app.run_turn(debate_app.SEATS[0], 1))
    start = next(event for event in events if event["type"] == "turn_start")
    assert start["move_reason"] == "weighted_fallback"


def test_generation_failure_skips_and_ends_turn(debate_app, monkeypatch):
    events = []

    async def send(event):
        events.append(event)

    async def fail(*_args, **_kwargs):
        raise OSError("simulated local endpoint failure")

    monkeypatch.setattr(debate_app.hub, "send", send)
    monkeypatch.setattr(debate_app, "ollama_chat", fail)
    asyncio.run(debate_app.run_turn(debate_app.SEATS[0], 1))
    assert [event["type"] for event in events if event["type"] in {"turn_skipped", "turn_end"}] == [
        "turn_skipped",
        "turn_end",
    ]
    assert next(event for event in events if event["type"] == "turn_skipped")["reason"] == "generation_error"
    assert debate_app.state.generation_active is False


def test_pause_arriving_during_topic_generation_blocks_next_turn(debate_app, monkeypatch):
    turns = []

    async def generate(_seed):
        debate_app.state.paused = True
        return "Generated while pause arrived?"

    async def run_turn(*_args):
        turns.append(True)

    async def send(_event):
        return None

    monkeypatch.setattr(debate_app, "generate_topic", generate)
    monkeypatch.setattr(debate_app, "run_turn", run_turn)
    monkeypatch.setattr(debate_app.hub, "send", send)

    async def exercise():
        task = asyncio.create_task(debate_app.orchestrator())
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())
    assert turns == []


def test_state_resets_on_topic_and_survives_model_swap(debate_app, monkeypatch):
    async def send(_event):
        return None

    monkeypatch.setattr(debate_app.hub, "send", send)
    debate_app.state.pending_questions["Clue"].append("Neo")
    debate_app.state.previous_public["Neo"] = "prior"
    asyncio.run(debate_app.set_topic("Replacement topic"))
    assert not debate_app.state.pending_questions["Clue"]
    assert debate_app.state.previous_public == {}

    debate_app.state.pending_questions["Clue"].append("Neo")
    old_model = debate_app.SEATS[0]["model"]
    debate_app.SEATS[0]["model"] = "replacement:model"
    try:
        assert list(debate_app.state.pending_questions["Clue"]) == ["Neo"]
    finally:
        debate_app.SEATS[0]["model"] = old_model


def test_incremental_public_filter_never_emits_reasoning(debate_app):
    filter_ = debate_app.PublicStreamFilter()
    fragments = [
        "<thi",
        "nk>private chain",
        "</th",
        "ink>Public ",
        "answer.",
    ]
    emitted = "".join(filter_.feed(fragment) for fragment in fragments)
    emitted += filter_.feed("", final=True)
    assert emitted == "Public answer."
    assert "private" not in emitted
    assert "<think>" not in emitted


def test_separate_thinking_field_has_no_public_path(debate_app):
    assert debate_app.clean("<think>secret</think>Visible") == "Visible"
    assert debate_app.clean("<analysis>secret</analysis>Visible") == "Visible"


def test_insight_disabled_has_no_worker_or_requests(debate_app):
    assert debate_app.CONFIG["insight_panel"] is False
    assert debate_app.insight_manager is None


def test_insight_queue_bound_drop_oldest_and_empty_no_call(debate_app):
    manager = debate_app.InsightManager(2, 1, "extractor")
    manager.enqueue({"text": "", "turn": 0})
    assert manager.queue.empty()
    for turn in (1, 2, 3):
        manager.enqueue({"text": f"public {turn}", "turn": turn})
    queued = [manager.queue.get_nowait(), manager.queue.get_nowait()]
    assert [item["turn"] for item in queued] == [2, 3]


def test_insight_timeout_isolated_and_failure_event_safe(debate_app, monkeypatch):
    events = []

    async def models():
        return ["extractor"]

    async def slow_chat(*_args, **_kwargs):
        await asyncio.sleep(0.1)
        return "{}"

    async def send(event):
        events.append(event)

    monkeypatch.setattr(debate_app, "installed_models", models)
    monkeypatch.setattr(debate_app, "ollama_chat", slow_chat)
    monkeypatch.setattr(debate_app.hub, "send", send)
    manager = debate_app.InsightManager(2, 0.01, "extractor")
    asyncio.run(
        manager._extract(
            {"text": "public only", "seat": "Neo", "turn": 1, "topic_epoch": 1}
        )
    )
    assert events[-1]["type"] == "insight"
    assert events[-1]["status"] == "unavailable"
    assert events[-1]["stance"] == "—"


def test_insight_prompt_contains_only_supplied_public_text(debate_app, monkeypatch):
    prompts = []
    events = []

    async def models():
        return ["extractor"]

    async def chat(_model, messages, **_kwargs):
        prompts.append(messages[0]["content"])
        return '{"stance":"mixed","addressed_seat":"Clue","claims":["A"],"question":""}'

    async def send(event):
        events.append(event)

    monkeypatch.setattr(debate_app, "installed_models", models)
    monkeypatch.setattr(debate_app, "ollama_chat", chat)
    monkeypatch.setattr(debate_app.hub, "send", send)
    manager = debate_app.InsightManager(2, 1, "extractor")
    asyncio.run(
        manager._extract(
            {"text": "Only public prose.", "seat": "Neo", "turn": 2, "topic_epoch": 1}
        )
    )
    assert "Only public prose." in prompts[0]
    assert "<think>" not in prompts[0]
    assert events[-1]["heuristic"] is True
    assert events[-1]["status"] == "complete"


def test_insight_preemption_cancels_active_work(debate_app):
    async def exercise():
        manager = debate_app.InsightManager(2, 1, "extractor")
        manager.active_task = asyncio.create_task(asyncio.sleep(10))
        await manager.preempt()
        assert manager.active_task is None

    asyncio.run(exercise())


def test_insight_reset_drops_stale_jobs(debate_app, monkeypatch):
    events = []

    async def send(event):
        events.append(event)

    monkeypatch.setattr(debate_app.hub, "send", send)
    manager = debate_app.InsightManager(2, 1, "extractor")
    manager.enqueue({"text": "old", "turn": 1})
    asyncio.run(manager.reset())
    assert manager.queue.empty()
    assert events[-1]["type"] == "insight_reset"
