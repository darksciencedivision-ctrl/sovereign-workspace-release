"""Focused regressions for the six v1.1 punch-list defects (see
DIRECTIVE-V1.1-CLAUDE-CODE.md §9). All existing v1 tests in
test_v1_logic.py and test_smoke.py must also keep passing unchanged.
"""

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

sys.path.insert(0, str(ROOT))
from debate import argument_memory, prompt_contract  # noqa: E402
from debate import turn_completion as tc  # noqa: E402
from debate.output_guard import OutputGuard  # noqa: E402
from debate.sentence_buffer import SentenceBuffer  # noqa: E402

LABELS = (
    "TOPIC:",
    "CONTINUITY ANCHOR:",
    "RECENT TABLE TRANSCRIPT:",
    "OPERATOR NOTE:",
    "YOUR MOVE:",
    "YOUR RECENT ARGUMENTS:",
)


@pytest.fixture(scope="module")
def debate_app():
    temp_dir = Path(tempfile.mkdtemp(prefix=".v1-1-unit-", dir=ROOT / "tests"))
    config_path = temp_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "ollama_url": "http://127.0.0.1:9",
                "port": 18778,
                "seats": [
                    {
                        "name": "Neo",
                        "model": "mock-alpha:latest",
                        "color": "#4fd1ff",
                        "persona": "Builder",
                        "thesis": "Systems beat individual cleverness.",
                    },
                    {
                        "name": "Clue",
                        "model": "mock-beta:latest",
                        "color": "#7dffa0",
                        "persona": "Challenger",
                        "thesis": "Every claim owes a mechanism.",
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
    module_name = "debate_table_v1_1_unit"
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
    debate_app.state.public_title = "Test topic"
    debate_app.state.topic_epoch = 1
    debate_app.state.transcript = []
    debate_app.state.turn = 0
    debate_app.state.speaker_idx = 0
    debate_app.state.generation_active = False
    debate_app.state.paused = False
    debate_app.state.shutting_down = False
    debate_app.argument_memory_tracker.reset()
    yield


# ---------------------------------------------------------------------------
# Output integrity (§4, §9 "Output integrity")
# ---------------------------------------------------------------------------


def test_required_regression_leak_removed_speech_preserved():
    """The exact regression specified in directive §4.3."""
    guard = OutputGuard(LABELS, dynamic_values=["challenge Neo's last claim."])
    buffer = SentenceBuffer(guard)
    raw = (
        "Your move: challenge Neo's last claim.\n"
        "Neo's argument fails because the proposed mechanism does not "
        "establish causality."
    )
    emitted = []
    e, _b = buffer.feed(raw)
    emitted.extend(e)
    fe, tail, _fb = buffer.finish()
    emitted.extend(fe)
    assert emitted == [
        "Neo's argument fails because the proposed mechanism does not "
        "establish causality."
    ]
    assert tail == ""


def test_label_split_across_two_fragments_cannot_bypass_guard():
    guard = OutputGuard(LABELS)
    buffer = SentenceBuffer(guard)
    out = []
    for fragment in ["Your mo", "ve: challenge this.\n", "Real speech follows."]:
        e, _b = buffer.feed(fragment)
        out.extend(e)
    fe, tail, _fb = buffer.finish()
    out.extend(fe)
    full = "".join(out) + tail
    assert "Real speech follows." in full
    assert "your mo" not in full.lower()


def test_your_move_phrase_inside_ordinary_speech_survives():
    guard = OutputGuard(LABELS)
    buffer = SentenceBuffer(guard)
    e, _b = buffer.feed("In my view, your move here was clever.\n")
    fe, tail, _fb = buffer.finish()
    full = "".join(e + fe) + tail
    assert "your move" in full.lower()


def test_guard_blocks_dynamic_move_text_echo_without_label():
    guard = OutputGuard(LABELS, dynamic_values=["Test the strongest prior claim."])
    buffer = SentenceBuffer(guard)
    e, blocked = buffer.feed("Test the strongest prior claim.\nReal content here.\n")
    fe, tail, fb = buffer.finish()
    blocked += fb
    full = "".join(e + fe) + tail
    assert "Real content here." in full
    assert "strongest prior claim" not in full
    assert blocked


def test_diagnostics_never_leak_onto_token_events(debate_app, monkeypatch):
    """Assertions read `token` events, not `turn_end` (§4.1 trap #4)."""
    events = []

    async def send(event):
        events.append(event)

    async def chat(_model, messages, on_public=None, **_kwargs):
        if on_public is None:
            return "done."
        await on_public("Your move: challenge Neo's last claim.\n")
        await on_public("A legitimate rebuttal follows here without any leak.")
        return "unused"

    monkeypatch.setattr(debate_app.hub, "send", send)
    monkeypatch.setattr(debate_app, "ollama_chat", chat)
    asyncio.run(debate_app.run_turn(debate_app.SEATS[0], 1))

    token_events = [event for event in events if event["type"] == "token"]
    diagnostic_events = [event for event in events if event["type"] == "diagnostic"]
    turn_end = next(event for event in events if event["type"] == "turn_end")

    assert diagnostic_events
    assert diagnostic_events[0]["kind"] == "CONTROL_TEXT_LEAK_BLOCKED"
    for event in token_events:
        assert "your move" not in event["text"].lower()
        assert "challenge neo" not in event["text"].lower()
    assert "your move" not in turn_end["text"].lower()


def test_narrowed_clean_preserves_in_short_and_fact(debate_app):
    assert debate_app.clean("In short: this is the point.") == "In short: this is the point."
    assert debate_app.clean("Fact: water boils at 100C.") == "Fact: water boils at 100C."


def test_narrowed_clean_still_strips_known_labels_and_seat_names(debate_app):
    assert debate_app.clean("TOPIC: something") == "something"
    assert debate_app.clean("Neo: hello there") == "hello there"
    assert debate_app.clean("<think>secret</think>Visible") == "Visible"


# ---------------------------------------------------------------------------
# Sentence buffering (§4.5, §9 "Sentence buffering")
# ---------------------------------------------------------------------------


def test_sentence_buffer_emits_complete_sentences_with_correct_spacing():
    guard = OutputGuard(LABELS)
    buffer = SentenceBuffer(guard)
    out = []
    for fragment in [
        "First sentence here. Second sen",
        "tence follows. Third one too.",
    ]:
        e, _b = buffer.feed(fragment)
        out.extend(e)
    fe, tail, _fb = buffer.finish()
    out.extend(fe)
    assert len(out) == 3
    assert "".join(out) + tail == (
        "First sentence here. Second sentence follows. Third one too."
    )


def test_sentence_buffer_retains_partial_until_terminator():
    guard = OutputGuard(LABELS)
    buffer = SentenceBuffer(guard)
    e, _b = buffer.feed("Neo, I think the mechanism you propose")
    assert e == []
    e2, _b2 = buffer.feed(" doesn't hold.")
    assert e2 == ["Neo, I think the mechanism you propose doesn't hold."]


def test_sentence_buffer_final_flush_returns_unterminated_tail():
    guard = OutputGuard(LABELS)
    buffer = SentenceBuffer(guard)
    buffer.feed("This sentence never ends with punctuation")
    emitted, tail, _blocked = buffer.finish()
    assert emitted == []
    assert tail.strip() == "This sentence never ends with punctuation"


def test_speaking_signal_fires_before_first_token(debate_app, monkeypatch):
    events = []

    async def send(event):
        events.append(event)

    async def chat(_model, _messages, on_public=None, **_kwargs):
        if on_public is None:
            return "done."
        await on_public("Public speech with enough words to count as a turn.")
        return "unused"

    monkeypatch.setattr(debate_app.hub, "send", send)
    monkeypatch.setattr(debate_app, "ollama_chat", chat)
    asyncio.run(debate_app.run_turn(debate_app.SEATS[0], 1))

    types_in_order = [event["type"] for event in events]
    assert "speaking" in types_in_order
    assert types_in_order.index("speaking") < types_in_order.index("token")


# ---------------------------------------------------------------------------
# Completion / truncation repair (§5, §9 "Completion")
# ---------------------------------------------------------------------------


def test_classify_turn_complete():
    state, signals, confident = tc.classify(
        text="A complete thought.", budget_exhausted=False, hidden_reasoning_present=False
    )
    assert state == tc.TURN_COMPLETE
    assert signals == []
    assert confident


def test_classify_turn_truncated_by_budget():
    state, signals, confident = tc.classify(
        text="This sentence just stops and", budget_exhausted=True, hidden_reasoning_present=False
    )
    assert state == tc.TURN_TRUNCATED_BY_BUDGET
    assert "done_reason:length" in signals
    assert confident


def test_classify_turn_interrupted():
    state, signals, confident = tc.classify(
        text="anything", budget_exhausted=False, hidden_reasoning_present=False, interrupted=True
    )
    assert state == tc.TURN_INTERRUPTED
    assert confident


def test_classify_turn_empty_after_reasoning():
    state, signals, confident = tc.classify(
        text="", budget_exhausted=False, hidden_reasoning_present=True
    )
    assert state == tc.TURN_EMPTY_AFTER_REASONING
    assert confident


def test_classify_turn_failed():
    state, signals, confident = tc.classify(
        text="", budget_exhausted=False, hidden_reasoning_present=False
    )
    assert state == tc.TURN_FAILED
    assert confident


def test_bound_continuation_hard_trims_to_35_words():
    long_text = " ".join(f"word{i}" for i in range(60))
    bounded = tc.bound_continuation(long_text)
    assert len(bounded.split()) == 35


def test_continuation_applied_exactly_once_no_double_emission(debate_app, monkeypatch):
    events = []
    chat_calls = []

    async def send(event):
        events.append(event)

    async def chat(_model, messages, on_public=None, metrics=None, **_kwargs):
        chat_calls.append(on_public is None)
        if on_public is None:
            # continuation call: non-streaming
            return "and this finishes the thought."
        if metrics is not None:
            metrics.update(
                {
                    "first_raw_seconds": 0.01,
                    "first_public_seconds": 0.01,
                    "duration_seconds": 0.05,
                    "hidden_reasoning_present": False,
                    "budget_exhausted": True,
                }
            )
        await on_public("Neo's framework depends on a mechanism that cuts off mid")
        return "unused"

    monkeypatch.setattr(debate_app.hub, "send", send)
    monkeypatch.setattr(debate_app, "ollama_chat", chat)
    asyncio.run(debate_app.run_turn(debate_app.SEATS[0], 1))

    continuation_calls = sum(1 for was_continuation in chat_calls if was_continuation)
    assert continuation_calls == 1

    token_events = [event["type"] == "token" for event in events]
    token_texts = [event["text"] for event in events if event["type"] == "token"]
    assert any("and this finishes the thought." in text for text in token_texts)
    # The unfinished tail must never appear on its own as a separate token
    # before the merged/completed version (no double emission).
    assert "cuts off mid" not in "".join(
        t for t in token_texts if "and this finishes the thought." not in t
    )
    turn_metrics = next(event for event in events if event["type"] == "turn_metrics")
    assert turn_metrics["attempts"][0]["completion_state"] == tc.TURN_TRUNCATED_BY_BUDGET
    assert turn_metrics["attempts"][0]["continuation_applied"] is True


# ---------------------------------------------------------------------------
# Argument memory (§8.1, §9 "Argument memory")
# ---------------------------------------------------------------------------


def test_argument_memory_duplicate_detected():
    memory = argument_memory.ArgumentMemory(["Neo", "Clue"])
    first = (
        "Structural resilience matters more than any single clever insight "
        "when systems face unexpected stress."
    )
    repeat = (
        "As I said, structural resilience matters more than any single "
        "clever insight in the long run."
    )
    assert memory.check_and_record("Neo", first) is None
    matched = memory.check_and_record("Neo", repeat)
    assert matched is not None


def test_argument_memory_unrelated_not_flagged():
    memory = argument_memory.ArgumentMemory(["Neo", "Clue"])
    first = "Structural resilience matters more than any single clever insight."
    unrelated = "Consider instead how price signals coordinate distributed knowledge."
    memory.check_and_record("Neo", first)
    assert memory.check_and_record("Neo", unrelated) is None


def test_argument_memory_depth_bounded():
    memory = argument_memory.ArgumentMemory(["Neo"], depth=5)
    for index in range(10):
        memory.check_and_record("Neo", f"Unique argument number {index} about topic {index}.")
    assert len(memory.recent("Neo")) == 5


def test_argument_memory_per_seat_isolation():
    memory = argument_memory.ArgumentMemory(["Neo", "Clue"])
    text = "Structural resilience matters more than any single clever insight."
    memory.check_and_record("Neo", text)
    # Clue saying something similar must not be flagged against Neo's memory.
    assert memory.check_and_record("Clue", text) is None


def test_pick_move_forces_reframe_on_pending_reframe(debate_app):
    debate_app.state.pending_reframe["Neo"] = "structural resilience clever insight"
    key, _text, reason = debate_app.pick_move(debate_app.SEATS[0], 3)
    assert key == "reframe"
    assert reason == "repeated_argument:structural resilience clever insight"
    assert "Neo" not in debate_app.state.pending_reframe


# ---------------------------------------------------------------------------
# Thesis (§7, §9 "Thesis")
# ---------------------------------------------------------------------------


def test_ordinary_turn_preserves_thesis(debate_app):
    prompt_before = debate_app.system_prompt(debate_app.SEATS[0])
    assert debate_app.SEATS[0]["thesis"] in prompt_before
    # An ordinary move (e.g. concur-extend) does not alter the seat's thesis.
    prompt_after = debate_app.system_prompt(debate_app.SEATS[0])
    assert prompt_after == prompt_before


def test_thesis_revision_emits_position_revision_event(debate_app, monkeypatch):
    events = []

    async def send(event):
        events.append(event)

    monkeypatch.setattr(debate_app.hub, "send", send)
    original = debate_app.SEATS[0]["thesis"]
    body = debate_app.SeatThesisIn(
        seat="Neo", thesis="A revised position.", reason="operator_test"
    )
    response = asyncio.run(debate_app.api_seat_thesis(body))
    assert response.status_code == 200
    assert debate_app.SEATS[0]["thesis"] == "A revised position."
    persisted = json.loads(debate_app.CONFIG_PATH.read_text(encoding="utf-8"))
    assert persisted["seats"][0]["thesis"] == "A revised position."
    revision_events = [event for event in events if event["type"] == "position_revision"]
    assert revision_events
    assert revision_events[0]["previous_thesis"] == original
    assert revision_events[0]["revised_thesis"] == "A revised position."
    debate_app.SEATS[0]["thesis"] = original
    debate_app.persist_seat_thesis("Neo", original)


# ---------------------------------------------------------------------------
# Config / API (§6, §9 "Config/API")
# ---------------------------------------------------------------------------


def test_topic_endpoint_rejects_over_limit_title(debate_app):
    too_long = "x" * (debate_app.PUBLIC_TITLE_MAX_CHARS + 1)
    debate_app.state.pending_topic = None
    response = asyncio.run(debate_app.api_topic(debate_app.TextIn(text=too_long)))
    assert response.status_code == 400
    assert "error" in json.loads(response.body)
    assert debate_app.state.pending_topic is None


def test_brief_endpoint_rejects_over_limit_brief(debate_app):
    debate_app.state.pending_topic = None
    body = debate_app.BriefIn(
        public_title="A short title",
        debate_brief="x" * (debate_app.DEBATE_BRIEF_MAX_CHARS + 1),
    )
    response = asyncio.run(debate_app.api_brief(body))
    assert response.status_code == 400
    assert "error" in json.loads(response.body)
    assert debate_app.state.pending_topic is None


def test_brief_endpoint_accepts_valid_values_never_truncates(debate_app):
    title = "A properly sized title"
    brief = "A properly sized debate brief with real context. " * 5
    body = debate_app.BriefIn(public_title=title, debate_brief=brief)
    response = asyncio.run(debate_app.api_brief(body))
    assert response.status_code == 200
    assert debate_app.state.pending_topic == {
        "public_title": title.strip(),
        "debate_brief": brief.strip(),
    }
    debate_app.state.pending_topic = None


def test_no_test_touches_production_config():
    production = ROOT / "config.json"
    before = production.read_bytes()
    assert before == production.read_bytes()


# ---------------------------------------------------------------------------
# UI hardening (§11)
# ---------------------------------------------------------------------------


def test_public_stage_markup_has_no_move_key_text():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert 'class="move"' not in html
    assert "seat.move.textContent" not in html
    move_diagnostic_index = html.index('id="move-diagnostic"')
    drawer_index = html.index('id="drawer"')
    assert drawer_index < move_diagnostic_index
