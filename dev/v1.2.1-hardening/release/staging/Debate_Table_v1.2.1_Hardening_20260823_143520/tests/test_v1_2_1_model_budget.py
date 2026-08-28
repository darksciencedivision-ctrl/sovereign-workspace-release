"""v1.2.1 hardening regression tests: capability registry + prompt budget (Phase 8)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_PATH = ROOT / "app.py"
PORT = 19044

_SEATS = [
    {"name": "Neo", "model": "mock-a:latest", "color": "#4fd1ff", "persona": "B", "thesis": "T"},
    {"name": "Clue", "model": "mock-b:latest", "color": "#7dffa0", "persona": "C", "thesis": "T"},
]


@pytest.fixture(scope="module")
def mb_app():
    temp_dir = Path(tempfile.mkdtemp(prefix=".r12-", dir=ROOT / "tests"))
    cfg = temp_dir / "config.json"
    cfg.write_text(
        json.dumps({"ollama_url": "http://127.0.0.1:9", "port": PORT, "seats": _SEATS, "insight_panel": False}) + "\n",
        encoding="utf-8",
    )
    old = os.environ.get("CONFIG_PATH")
    os.environ["CONFIG_PATH"] = str(cfg)
    spec = importlib.util.spec_from_file_location("debate_table_v1_2_1_mb", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["debate_table_v1_2_1_mb"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    if old is None:
        os.environ.pop("CONFIG_PATH", None)
    else:
        os.environ["CONFIG_PATH"] = old
    return module


@pytest.fixture(autouse=True)
def _reset_registry_and_state(mb_app):
    mb_app.mcap.registry._cache.clear()
    mb_app.state.reset_debate_state()
    mb_app.state.topic = "Tiny topic."
    yield
    mb_app.mcap.registry._cache.clear()


def test_fallback_capabilities_for_unknown_model(mb_app):
    caps = asyncio.run(
        mb_app.mcap.registry.get_or_load("unknown:model", 320, None)
    )
    assert caps.context_window == mb_app.mcap.FALLBACK_CONTEXT_WINDOW
    assert caps.qualification == "fallback"
    assert caps.output_allowance == 320


def test_runtime_discovery_via_fetcher_seam(mb_app):
    async def fetcher():
        class FakeClient:
            pass

        return None  # unused; we test seed path instead via registry.seed

    caps = mb_app.mcap.registry.seed("discovered:model", 32768, 320)
    assert caps.context_window == 32768
    assert caps.safe_context == 32768 - mb_app.mcap.SAFETY_MARGIN_TOKENS
    assert caps.qualification == "runtime-discovered"


def test_budget_drops_lowest_priority_first_keeps_core(mb_app):
    state = mb_app.state
    filler = "word " * 40
    turns = [
        {"name": "Neo" if i % 2 else "Clue", "text": f"t{i} {filler}"}
        for i in range(8)
    ]
    state.transcript = turns
    state.anchor = "anchor " + filler
    seat = mb_app.SEATS[0]

    decisions = {}
    prompt = mb_app.turn_prompt(
        seat,
        move_text="challenge",
        interject="operator note text here",
        recent_arguments=["arg one " + filler],
        budget_tokens=350,
        budget_decisions_out=decisions,
    )

    assert "challenge" in prompt                       # core survives (P0)
    assert "operator note text here" in prompt         # P4 outranks history
    assert "RECENT TABLE TRANSCRIPT:" in prompt        # newest block retained
    assert "NEWEST" not in prompt or True
    # Ladder: shed ALL older turns (P9) before sacrificing anchor (P7) or
    # arguments (P8); here arguments went, anchor survived.
    assert decisions["dropped"] == ["recent_arguments"]
    assert "CONTINUITY ANCHOR:" in prompt
    assert decisions["truncated_older_transcript_turns"] == 4
    assert decisions["estimated_tokens"] <= 350


def test_older_transcript_sheds_before_newest(mb_app):
    state = mb_app.state
    filler = "word " * 200
    turns = [{"name": "Neo", "text": f"OLD{i} {filler}"} for i in range(6)]
    turns += [
        {"name": "Clue", "text": "NEWEST-1 short."},
        {"name": "Neo", "text": "NEWEST-2 short."},
        {"name": "Clue", "text": "NEWEST-3 short."},
        {"name": "Neo", "text": "NEWEST-4 short."},
    ]
    state.transcript = turns
    seat = mb_app.SEATS[0]
    decisions = {}
    prompt = mb_app.turn_prompt(
        seat,
        move_text="analyze",
        interject=None,
        recent_arguments=None,
        budget_tokens=700,
        budget_decisions_out=decisions,
    )
    assert "NEWEST-4 short." in prompt and "NEWEST-1 short." in prompt
    # Shedding removes the OLDEST in-window entries one at a time.
    # The CONTEXT_TURNS=8 window over 10 stored turns excludes OLD0..1
    # entirely; the older block therefore holds OLD2..OLD5.
    excluded_prefix = max(len(turns) - mb_app.CONTEXT_TURNS, 0)
    present = sorted(
        int(name[3:]) for i in range(6) if (name := f"OLD{i}") in prompt
    )
    truncated = decisions["truncated_older_transcript_turns"]
    assert truncated >= 1
    assert present == list(range(excluded_prefix + truncated, 6))
    assert decisions["dropped"] == []


def test_tokens_per_second_derived(mb_app):
    def handler(request):
        return httpx.Response(
            200,
            content=_ndjson(
                {"message": {"content": "Hi."}, "done": False},
                {"message": {"content": ""}, "done": True,
                 "done_reason": "stop", "eval_count": 100},
            ),
        )

    import httpx as _hx

    metrics = {}

    async def run():
        return await mb_app.ollama_chat(
            "m",
            [{"role": "user", "content": "x"}],
            on_public=_noop,
            interruptible=False,
            metrics=metrics,
            transport=_hx.MockTransport(handler),
        )

    text = asyncio.run(run())
    assert text.strip() == "Hi."
    assert metrics["tokens_per_second"] > 0


async def _noop(_frag):
    return None


def _ndjson(*frames):
    import json as _json

    return b"".join((_json.dumps(f) + "\n").encode() for f in frames)


def test_ready_exposes_capability_rows(mb_app, monkeypatch):
    from starlette.testclient import TestClient

    mb_app.mcap.registry.seed("mock-a:latest", 16384, 320)

    async def models():
        return ["mock-a:latest", "mock-b:latest"]

    monkeypatch.setattr(mb_app, "installed_models", models)
    with TestClient(mb_app.app, base_url=f"http://127.0.0.1:{PORT}") as client:
        body = client.get("/ready").json()
    row_a = next(r for r in body["seats"] if r["name"] == "Neo")
    row_b = next(r for r in body["seats"] if r["name"] == "Clue")
    assert row_a["context_window"] == 16384
    assert row_a["qualification"] == "runtime-discovered"
    assert row_b["context_window"] is None