"""v1.2.1 hardening regression tests: WS isolation + insight recovery (Phase 6b)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_PATH = ROOT / "app.py"
PORT = 19011

_SEATS = [
    {"name": "Neo", "model": "m", "color": "#4fd1ff", "persona": "B", "thesis": "T"},
    {"name": "Clue", "model": "m", "color": "#7dffa0", "persona": "C", "thesis": "T"},
]


@pytest.fixture(scope="module")
def ws_app():
    temp_dir = Path(tempfile.mkdtemp(prefix=".r9-", dir=ROOT / "tests"))
    cfg = temp_dir / "config.json"
    cfg.write_text(
        json.dumps({"ollama_url": "http://127.0.0.1:9", "port": PORT, "seats": _SEATS, "insight_panel": False}) + "\n",
        encoding="utf-8",
    )
    old = os.environ.get("CONFIG_PATH")
    os.environ["CONFIG_PATH"] = str(cfg)
    spec = importlib.util.spec_from_file_location("debate_table_v1_2_1_ws", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["debate_table_v1_2_1_ws"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    if old is None:
        os.environ.pop("CONFIG_PATH", None)
    else:
        os.environ["CONFIG_PATH"] = old
    return module


class StubSocket:
    def __init__(self, name, delay=0.0, hang=False):
        self.name = name
        self.delay = delay
        self.hang = hang
        self.sent = []
        self.closed_with = None

    async def send_text(self, message):
        if self.hang:
            await asyncio.sleep(30)
        if self.delay:
            await asyncio.sleep(self.delay)
        self.sent.append(message)

    async def close(self, code=1000):
        self.closed_with = code


def test_slow_client_cannot_delay_fast_client(ws_app):
    """MEASURED: 300 broadcasts complete fast even with a non-reading peer."""
    hub = ws_app.Hub()
    fast = ws_app.ClientConnection(StubSocket("fast"))
    slow = ws_app.ClientConnection(StubSocket("slow"))
    # Replace sockets' queues with unbounded drains for the fast client by
    # running its sender; slow client never reads (no sender started).
    hub.clients.add(fast)
    hub.clients.add(slow)

    async def scenario():
        fast.sender_task = asyncio.create_task(hub._sender(fast))
        t0 = time.monotonic()
        for index in range(300):
            await hub.send({"type": "token", "i": index})
        elapsed = time.monotonic() - t0
        await asyncio.sleep(0.05)  # let overflow disconnects settle
        return elapsed, len(fast.ws.sent), slow.ws.closed_with

    async def _cancel():
        fast.sender_task.cancel()

    elapsed, fast_count, slow_close = asyncio.run(scenario())
    asyncio.run(_cancel())
    print(f"BROADCAST_300_ELAPSED={elapsed:.4f}")
    assert elapsed < 1.0, elapsed
    assert fast_count == 300
    assert slow_close is not None  # disconnected for falling behind


def test_overflow_disconnect_counts_drops(ws_app):
    hub = ws_app.Hub()
    stub = StubSocket("slow2")
    conn = ws_app.ClientConnection(stub)
    hub.clients.add(conn)

    async def scenario():
        for i in range(ws_app.CLIENT_QUEUE_MAX + 5):
            await hub.send({"type": "x"})
        await asyncio.sleep(0.05)

    asyncio.run(scenario())
    assert hub.broadcast_dropped_total >= 1
    assert stub.closed_with == 1013
    assert conn not in hub.clients


def test_wedged_socket_sender_times_out(ws_app, monkeypatch):
    monkeypatch.setattr(ws_app, "CLIENT_SEND_TIMEOUT_S", 0.05)
    hub = ws_app.Hub()
    conn = ws_app.ClientConnection(StubSocket("wedged", hang=True))
    hub.clients.add(conn)

    async def scenario():
        conn.sender_task = asyncio.create_task(hub._sender(conn))
        await hub.send({"type": "x"})
        await asyncio.wait_for(conn.sender_task, timeout=3)

    asyncio.run(scenario())
    assert conn.closed is True
    assert conn not in hub.clients


def test_insight_negative_availability_recovers_after_ttl(ws_app, monkeypatch):
    calls = {"n": 0}

    async def models():
        calls["n"] += 1
        return [] if calls["n"] == 1 else ["extractor"]

    manager = ws_app.InsightManager(2, 1, "extractor")
    monkeypatch.setattr(ws_app, "INSIGHT_INSTALLED_TTL_S", 0.01)
    monkeypatch.setattr(ws_app, "installed_models", models)
    sent = []

    async def send(event):
        sent.append(event)

    monkeypatch.setattr(ws_app.hub, "send", send)

    job = {"text": "public statement here", "seat": "Neo", "turn": 1,
           "topic_epoch": manager and ws_app.state.topic_epoch}

    async def chat(model, messages, **kw):
        return '{"stance":"mixed","addressed_seat":"","claims":["A"],"question":""}'

    monkeypatch.setattr(ws_app, "ollama_chat", chat)

    async def scenario():
        await manager._extract(job)
        first_status = sent[-1]["status"]
        await asyncio.sleep(0.02)  # exceed TTL
        await manager._extract(job)
        second_status = sent[-1]["status"]
        return first_status, second_status

    first, second = asyncio.run(scenario())
    assert first == "unavailable"
    assert second == "complete"
    assert calls["n"] == 2


def test_insight_counters_instrumentation(ws_app):
    manager = ws_app.InsightManager(4, 1, "x")
    manager.enqueue({"text": "one", "seat": "N", "turn": 1, "topic_epoch": 1})
    manager.enqueue({"text": "", "turn": 2})
    assert manager.counters["queued"] == 1
    manager.enqueue({"text": "two", "seat": "N", "turn": 2, "topic_epoch": 1})
    manager.enqueue({"text": "three", "seat": "N", "turn": 3, "topic_epoch": 1})
    manager.enqueue({"text": "four", "seat": "N", "turn": 4, "topic_epoch": 1})
    manager.enqueue({"text": "five", "seat": "N", "turn": 5, "topic_epoch": 1})
    assert manager.counters["dropped"] == 1
    stats = manager.stats()
    assert set(stats) >= {"queued", "completed", "cancelled", "dropped", "unavailable"}


def test_reset_drains_and_counts(ws_app):
    manager = ws_app.InsightManager(8, 1, "x")
    for i in range(3):
        manager.enqueue({"text": f"m{i}", "seat": "N", "turn": i, "topic_epoch": 1})

    async def run():
        await manager.reset()

    asyncio.run(run())
    assert manager.queue.qsize() == 0
    assert manager.counters["dropped"] == 3