"""v1.2.1 hardening hostile mock-Ollama E2E (AC-04 floor).

Full application path: API semantics -> FastAPI -> orchestrator -> HTTP
client -> mocked Ollama -> stream parser -> reasoning guard -> output
guard -> sentence buffer -> turn state -> WebSocket output.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import httpx
import pytest
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_CONFIG = ROOT / "config.json"
APP_PORT = 18701
BASE_URL = f"http://127.0.0.1:{APP_PORT}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_for_port(port: int, process: subprocess.Popen, timeout: float = 15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            out, err = process.communicate(timeout=1)
            raise AssertionError(f"exit {process.returncode}\n{out}\n{err}")
        with socket.socket() as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    raise AssertionError(f"port {port} did not open")


def available_port(preferred: int) -> int:
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", preferred)) != 0:
            return preferred
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def stop_process(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def receive_until(ws, predicate, timeout=15.0):
    deadline = time.monotonic() + timeout
    seen = []
    while time.monotonic() < deadline:
        event = json.loads(ws.recv(timeout=max(0.1, deadline - time.monotonic())))
        seen.append(event)
        if predicate(event, seen):
            return event, seen
    raise AssertionError(f"event not received; saw types={[e.get('type') for e in seen]}")


@pytest.fixture()
def stack():
    original_hash = sha256(PRODUCTION_CONFIG)
    temp_dir = Path(tempfile.mkdtemp(prefix=".hostile-", dir=ROOT / "tests"))
    isolated = temp_dir / "config.json"
    config = json.loads(PRODUCTION_CONFIG.read_text(encoding="utf-8"))
    config.update(
        {
            "port": APP_PORT,
            "turn_delay_ms": 200,
            "topic_rotate_turns": 0,
            "anchor_every_turns": 0,
            "empty_spoken_retry_count": 0,
        }
    )
    for index, seat in enumerate(config["seats"]):
        seat["model"] = ("mock-alpha:latest", "mock-beta:latest")[index % 2]
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    mock_port = available_port(11436)
    config["ollama_url"] = f"http://127.0.0.1:{mock_port}"
    isolated.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    mock_env = os.environ.copy()
    mock_env["MOCK_OLLAMA_PORT"] = str(mock_port)
    mock = subprocess.Popen(
        [sys.executable, str(ROOT / "tests" / "mock_ollama.py")],
        cwd=ROOT,
        env=mock_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creationflags,
    )
    app_env = os.environ.copy()
    app_env.update(
        {
            "OLLAMA_URL": f"http://127.0.0.1:{mock_port}",
            "CONFIG_PATH": str(isolated),
            "PYTHONUTF8": "1",
        }
    )
    app = None
    try:
        wait_for_port(mock_port, mock)
        app = subprocess.Popen(
            [sys.executable, str(ROOT / "app.py")],
            cwd=ROOT,
            env=app_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=creationflags,
        )
        wait_for_port(APP_PORT, app)
        yield isolated
    finally:
        if app is not None:
            stop_process(app)
            out, err = app.communicate()
            combined = (out + err).lower()
            assert "traceback" not in combined, combined[-800:]
        stop_process(mock)
        mout, merr = mock.communicate()
        assert "traceback" not in (mout + merr).lower(), (mout + merr)[-500:]
        assert sha256(PRODUCTION_CONFIG) == original_hash
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_http_500_then_recovery(stack):
    mock_url = json.loads(stack.read_text(encoding="utf-8"))["ollama_url"]
    ws = connect(f"ws://127.0.0.1:{APP_PORT}/ws", open_timeout=10)
    try:
        json.loads(ws.recv())  # snapshot
        httpx.post(f"{mock_url}/control/stream_mode/http_500")
        _, events = receive_until(
            ws,
            lambda e, _: e.get("type") == "turn_skipped"
            and e.get("reason") == "generation_error",
        )
        # Recovery after the temporary failure: normal mode completes a turn.
        httpx.post(f"{mock_url}/control/stream_mode/normal")
        _end, recovery = receive_until(
            ws,
            lambda e, _: e.get("type") == "turn_end" and e.get("text"),
            timeout=20,
        )
        assert any(e["type"] == "token" for e in recovery)
    finally:
        ws.close()


def test_malformed_ndjson_maps_to_protocol_error(stack):
    mock_url = json.loads(stack.read_text(encoding="utf-8"))["ollama_url"]
    ws = connect(f"ws://127.0.0.1:{APP_PORT}/ws", open_timeout=10)
    try:
        json.loads(ws.recv())
        httpx.post(f"{mock_url}/control/stream_mode/malformed_ndjson")
        skip, _ = receive_until(
            ws,
            lambda e, _: e.get("type") == "turn_skipped"
            and e.get("reason") == "protocol_error",
        )
        assert skip["reason"] == "protocol_error"
    finally:
        ws.close()


def test_partial_frame_maps_to_protocol_error(stack):
    mock_url = json.loads(stack.read_text(encoding="utf-8"))["ollama_url"]
    ws = connect(f"ws://127.0.0.1:{APP_PORT}/ws", open_timeout=10)
    try:
        json.loads(ws.recv())
        httpx.post(f"{mock_url}/control/stream_mode/partial_frame")
        skip, _ = receive_until(
            ws,
            lambda e, _: e.get("type") == "turn_skipped"
            and e.get("reason") == "protocol_error",
        )
        assert skip["turn"] >= 1
    finally:
        ws.close()


def test_missing_done_maps_to_protocol_incomplete(stack):
    mock_url = json.loads(stack.read_text(encoding="utf-8"))["ollama_url"]
    ws = connect(f"ws://127.0.0.1:{APP_PORT}/ws", open_timeout=10)
    try:
        json.loads(ws.recv())
        httpx.post(f"{mock_url}/control/stream_mode/no_done")
        skip, _ = receive_until(
            ws,
            lambda e, _: e.get("type") == "turn_skipped"
            and e.get("reason") == "protocol_incomplete",
        )
        # A stream without terminal done must NOT become a completed turn.
        assert skip["reason"] == "protocol_incomplete"
    finally:
        ws.close()


def test_stall_pause_cancels_within_e2e_budget(stack):
    mock_url = json.loads(stack.read_text(encoding="utf-8"))["ollama_url"]
    ws = connect(f"ws://127.0.0.1:{APP_PORT}/ws", open_timeout=10)
    try:
        json.loads(ws.recv())
        httpx.post(f"{BASE_URL}/api/pause")
        httpx.post(f"{mock_url}/control/stream_mode/stall_pause")
        httpx.post(f"{BASE_URL}/api/resume")
        start, _ = receive_until(
            ws, lambda e, _: e.get("type") == "turn_start", timeout=10
        )
        t0 = time.monotonic()
        assert httpx.post(f"{BASE_URL}/api/pause").status_code == 200
        skip, _ = receive_until(
            ws,
            lambda e, _: e.get("type") == "turn_skipped"
            and e.get("reason") == "operator_interruption",
            timeout=10,
        )
        elapsed = time.monotonic() - t0
        print(f"E2E_PAUSE_CANCEL_SECONDS={elapsed:.3f}")
        assert elapsed < 5.0, elapsed
    finally:
        ws.close()


def test_control_echo_blocked_public_clean_turn_completes(stack):
    mock_url = json.loads(stack.read_text(encoding="utf-8"))["ollama_url"]
    payload = "CONFIDENTIAL interjection payload must never surface"
    ws = connect(f"ws://127.0.0.1:{APP_PORT}/ws", open_timeout=10)
    try:
        json.loads(ws.recv())
        httpx.post(f"{BASE_URL}/api/pause")
        httpx.post(f"{BASE_URL}/api/interject", json={"text": payload})
        httpx.post(f"{mock_url}/control/stream_mode/echo_control")
        httpx.post(f"{BASE_URL}/api/resume")
        _end, events = receive_until(
            ws,
            lambda e, _: e.get("type") == "turn_end" and e.get("text"),
            timeout=20,
        )
        public = "".join(
            e.get("text", "") for e in events if e["type"] in {"token", "turn_end"}
        )
        assert payload not in public
        assert "YOUR MOVE:" not in public
        assert "clean-token-" in public  # legitimate speech survived
        blocked = [
            e
            for e in events
            if e.get("type") == "diagnostic"
            and e.get("kind") == "CONTROL_TEXT_LEAK_BLOCKED"
        ]
        assert blocked, "expected leak-block diagnostics"
    finally:
        ws.close()


def test_short_interjection_does_not_suppress_speech(stack):
    mock_url = json.loads(stack.read_text(encoding="utf-8"))["ollama_url"]
    ws = connect(f"ws://127.0.0.1:{APP_PORT}/ws", open_timeout=10)
    try:
        json.loads(ws.recv())
        httpx.post(f"{mock_url}/control/stream_mode/short_echo")
        _end, events = receive_until(
            ws,
            lambda e, _: e.get("type") == "turn_end" and e.get("text"),
            timeout=20,
        )
        public = "".join(
            e.get("text", "") for e in events if e["type"] in {"token", "turn_end"}
        )
        assert "I think the premise is incorrect." in public
    finally:
        ws.close()


def test_chat_failure_window_recovers(stack):
    mock_url = json.loads(stack.read_text(encoding="utf-8"))["ollama_url"]
    ws = connect(f"ws://127.0.0.1:{APP_PORT}/ws", open_timeout=10)
    try:
        json.loads(ws.recv())
        httpx.post(f"{mock_url}/control/chat_failure/1")
        skip, _ = receive_until(
            ws,
            lambda e, _: e.get("type") == "turn_skipped"
            and e.get("reason") == "generation_error",
        )
        _end, recovery = receive_until(
            ws,
            lambda e, _: e.get("type") == "turn_end" and e.get("text"),
            timeout=20,
        )
        assert any(e["type"] == "token" for e in recovery)
    finally:
        ws.close()


def test_unavailable_model_mode_skips_turn(stack):
    mock_url = json.loads(stack.read_text(encoding="utf-8"))["ollama_url"]
    ws = connect(f"ws://127.0.0.1:{APP_PORT}/ws", open_timeout=10)
    try:
        json.loads(ws.recv())
        httpx.post(f"{mock_url}/control/stream_mode/model_404")
        skip, _ = receive_until(
            ws,
            lambda e, _: e.get("type") == "turn_skipped"
            and e.get("reason") == "generation_error",
        )
        assert skip["seat"]
    finally:
        ws.close()