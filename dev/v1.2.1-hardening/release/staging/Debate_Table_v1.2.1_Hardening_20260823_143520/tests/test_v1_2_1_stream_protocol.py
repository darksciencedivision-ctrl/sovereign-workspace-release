"""v1.2.1 hardening regression tests: stream protocol + cancellation (P0-13/14)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_PATH = ROOT / "app.py"
PORT = 18955

_SEATS = [
    {"name": "Neo", "model": "mock-a:latest", "color": "#4fd1ff", "persona": "B", "thesis": "T"},
    {"name": "Clue", "model": "mock-b:latest", "color": "#7dffa0", "persona": "C", "thesis": "T"},
]


def _load_app(module_name="debate_table_v1_2_1_stream"):
    temp_dir = Path(tempfile.mkdtemp(prefix=".r5-", dir=ROOT / "tests"))
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
    spec = importlib.util.spec_from_file_location(module_name, APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def stream_app():
    module = _load_app()
    yield module


@pytest.fixture(autouse=True)
def _fresh_interrupt_event(stream_app):
    """Each test drives its own event loop; give the shared state a matching
    Event so cross-loop binding cannot pollute behavior between tests."""
    stream_app.state.interrupt_generation = asyncio.Event()
    yield
    stream_app.state.interrupt_generation.clear()


def _ndjson(*frames):
    return b"".join(
        (json.dumps(frame) + "\n").encode("utf-8") for frame in frames
    )


def _chat_transport(handler):
    return httpx.MockTransport(handler)


def test_stream_with_done_is_success(stream_app):
    def handler(request):
        return httpx.Response(
            200,
            content=_ndjson(
                {"message": {"content": "Hello "}, "done": False},
                {"message": {"content": "world."}, "done": True,
                 "done_reason": "stop", "eval_count": 10},
            ),
        )

    metrics = {}
    text = asyncio.run(
        stream_app.ollama_chat(
            "m",
            [{"role": "user", "content": "x"}],
            on_public=_async_noop,
            interruptible=True,
            metrics=metrics,
            transport=_chat_transport(handler),
        )
    )
    assert "Hello" in text and "world." in text
    assert metrics["done_seen"] is True
    assert metrics["stream_protocol"] == "ok"


async def _async_noop(_fragment):
    return None


def test_eof_without_done_raises_incomplete(stream_app):
    def handler(request):
        return httpx.Response(
            200,
            content=_ndjson({"message": {"content": "Partial"}, "done": False}),
        )

    with pytest.raises(stream_app.StreamIncomplete):
        asyncio.run(
            stream_app.ollama_chat(
                "m",
                [{"role": "user", "content": "x"}],
                on_public=_async_noop,
                interruptible=True,
                metrics={},
                transport=_chat_transport(handler),
            )
        )


def test_malformed_ndjson_raises_protocol_error(stream_app):
    def handler(request):
        return httpx.Response(
            200,
            content=b'{"message": {"content": "ok"}, "done": false}\nNOT_JSON\n',
        )

    with pytest.raises(stream_app.StreamProtocolError) as excinfo:
        asyncio.run(
            stream_app.ollama_chat(
                "m",
                [{"role": "user", "content": "x"}],
                on_public=_async_noop,
                interruptible=True,
                metrics={},
                transport=_chat_transport(handler),
            )
        )
    assert "NOT_JSON" in str(excinfo.value)


def test_done_frame_missing_but_empty_output_still_requires_done(stream_app):
    def handler(request):
        return httpx.Response(200, content=b"\n\n")

    with pytest.raises(stream_app.StreamIncomplete):
        asyncio.run(
            stream_app.ollama_chat(
                "m",
                [{"role": "user", "content": "x"}],
                on_public=_async_noop,
                interruptible=True,
                metrics={},
                transport=_chat_transport(handler),
            )
        )


def test_empty_output_with_done_returns_empty_string(stream_app):
    def handler(request):
        return httpx.Response(200, content=_ndjson({"done": True}))

    text = asyncio.run(
        stream_app.ollama_chat(
            "m",
            [{"role": "user", "content": "x"}],
            on_public=_async_noop,
            interruptible=True,
            metrics={},
            transport=_chat_transport(handler),
        )
    )
    assert text == ""


def test_pause_during_stalled_stream_cancels_within_sla(stream_app):
    started = {"first": False}

    async def slow_chunks():
        yield b'{"message": {"content": "First."}, "done": false}\n'
        await asyncio.sleep(30)

    def handler(request):
        return httpx.Response(200, content=slow_chunks())

    async def scenario():
        stream_app.state.interrupt_generation.clear()
        metrics = {}
        task = asyncio.create_task(
            stream_app.ollama_chat(
                "m",
                [{"role": "user", "content": "x"}],
                on_public=_async_noop,
                interruptible=True,
                metrics=metrics,
                transport=_chat_transport(handler),
            )
        )
        await asyncio.sleep(0.05)
        t0 = time.monotonic()
        stream_app.state.interrupt_generation.set()
        with pytest.raises(stream_app.TurnInterrupted):
            await task
        latency = time.monotonic() - t0
        stream_app.state.interrupt_generation.clear()
        return latency, metrics

    latency, metrics = asyncio.run(scenario())
    print(f"CANCEL_LATENCY_SECONDS={latency:.4f}")
    assert latency <= 0.5, latency
    assert metrics.get("interrupt_reason") == "operator_interruption"


def test_inactivity_timer_interrupts_silent_stream(stream_app, monkeypatch):
    monkeypatch.setattr(stream_app, "STREAM_INACTIVITY_SECONDS", 0.05)

    async def silent():
        yield b""
        await asyncio.sleep(5)

    def handler(request):
        return httpx.Response(200, content=silent())

    async def scenario():
        metrics = {}
        t0 = time.monotonic()
        with pytest.raises(stream_app.TurnInterrupted):
            await stream_app.ollama_chat(
                "m",
                [{"role": "user", "content": "x"}],
                on_public=_async_noop,
                interruptible=False,
                metrics=metrics,
                transport=_chat_transport(handler),
            )
        return time.monotonic() - t0, metrics

    latency, metrics = asyncio.run(scenario())
    print(f"INACTIVITY_LATENCY_SECONDS={latency:.4f}")
    assert latency < 2.0, latency
    assert metrics.get("interrupt_reason") == "stream_inactivity"


def test_nonstreaming_generation_cancellable_within_sla(stream_app):
    """The non-streaming POST path (used by topic/anchor) must race the
    interrupt event rather than wait out the full HTTP timeout."""

    async def hanging(request):
        await asyncio.sleep(30)
        return httpx.Response(200, json={"message": {"content": "topic?"}})

    async def scenario():
        stream_app.state.interrupt_generation.clear()
        metrics = {}
        task = asyncio.create_task(
            stream_app.ollama_chat(
                "m",
                [{"role": "user", "content": "x"}],
                on_public=None,
                interruptible=True,
                metrics=metrics,
                transport=httpx.MockTransport(hanging),
            )
        )
        await asyncio.sleep(0.05)
        t0 = time.monotonic()
        stream_app.state.interrupt_generation.set()
        with pytest.raises(stream_app.TurnInterrupted):
            await task
        latency = time.monotonic() - t0
        stream_app.state.interrupt_generation.clear()
        return latency

    latency = asyncio.run(scenario())
    print(f"NONSTREAM_CANCEL_LATENCY_SECONDS={latency:.4f}")
    assert latency <= 0.5, latency


def test_http_500_maps_to_generic_generation_error(stream_app):
    def handler(request):
        return httpx.Response(500, text="boom")

    async def scenario():
        with pytest.raises(httpx.HTTPStatusError):
            await stream_app.ollama_chat(
                "m",
                [{"role": "user", "content": "x"}],
                on_public=None,
                interruptible=True,
                metrics={},
                transport=_chat_transport(handler),
            )

    asyncio.run(scenario())