"""CR-023 — a debate WebSocket sender failure must close the socket (not leave the receiver open)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

DEBATE = Path(__file__).resolve().parents[4] / "modules" / "debate"
if str(DEBATE) not in sys.path:
    sys.path.insert(0, str(DEBATE))

import app as debate_app  # noqa: E402


class _FakeWS:
    def __init__(self, fail_send=False):
        self.fail_send = fail_send
        self.close_calls = 0
        self.sent: list[str] = []

    async def send_text(self, msg):
        if self.fail_send:
            raise RuntimeError("send failed")
        self.sent.append(msg)

    async def close(self, code=None):
        self.close_calls += 1


def _run_sender_with(ws, messages):
    async def scenario():
        hub = debate_app.Hub()
        conn = debate_app.ClientConnection(ws)
        hub.clients.add(conn)
        for m in messages:
            await conn.queue.put(m)
        await hub._sender(conn)
        return conn, hub
    return asyncio.run(scenario())


def test_cr023_sender_failure_closes_socket():
    ws = _FakeWS(fail_send=True)
    conn, hub = _run_sender_with(ws, ["hello"])  # send raises -> terminal failure
    assert ws.close_calls >= 1, "socket not closed on terminal sender failure (receiver would hang)"
    assert conn.closed is True
    assert conn not in hub.clients


def test_cr023_normal_sentinel_shutdown_also_closes_socket():
    ws = _FakeWS(fail_send=False)
    conn, hub = _run_sender_with(ws, [None])  # sentinel => clean shutdown
    assert ws.close_calls >= 1
    assert conn.closed is True
