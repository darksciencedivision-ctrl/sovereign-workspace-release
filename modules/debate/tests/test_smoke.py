import hashlib
import json
import os
from pathlib import Path
import re
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
APP_PORT = 18700
BASE_URL = f"http://127.0.0.1:{APP_PORT}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_for_port(port: int, process: subprocess.Popen, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            raise AssertionError(f"process exited {process.returncode}\nstdout={stdout}\nstderr={stderr}")
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


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def receive_until(ws, predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    seen = []
    while time.monotonic() < deadline:
        event = json.loads(ws.recv(timeout=max(0.1, deadline - time.monotonic())))
        seen.append(event)
        if predicate(event, seen):
            return event, seen
    raise AssertionError(f"event not received; saw {seen}")


@pytest.fixture()
def running_stack():
    original_hash = sha256(PRODUCTION_CONFIG)
    temp_dir = Path(tempfile.mkdtemp(prefix=".smoke-", dir=ROOT / "tests"))
    isolated_config = temp_dir / "config.json"
    shutil.copy2(PRODUCTION_CONFIG, isolated_config)
    config = json.loads(isolated_config.read_text(encoding="utf-8"))
    config["port"] = APP_PORT
    config["turn_delay_ms"] = 250
    config["topic_rotate_turns"] = 0
    config["anchor_every_turns"] = 0
    for index, seat in enumerate(config["seats"]):
        seat["model"] = ("mock-alpha:latest", "mock-beta:latest")[index % 2]
    isolated_config.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    mock_port = available_port(11435)
    config["ollama_url"] = f"http://127.0.0.1:{mock_port}"
    isolated_config.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    mock_env = os.environ.copy()
    mock_env["MOCK_OLLAMA_PORT"] = str(mock_port)
    mock = subprocess.Popen(
        [sys.executable, str(ROOT / "tests" / "mock_ollama.py")],
        cwd=ROOT, env=mock_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        creationflags=creationflags,
    )
    app_env = os.environ.copy()
    app_env.update({"OLLAMA_URL": f"http://127.0.0.1:{mock_port}", "CONFIG_PATH": str(isolated_config), "PYTHONUTF8": "1"})
    app = None
    try:
        wait_for_port(mock_port, mock)
        app = subprocess.Popen(
            [sys.executable, str(ROOT / "app.py")], cwd=ROOT, env=app_env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=creationflags,
        )
        wait_for_port(APP_PORT, app)
        yield isolated_config
    finally:
        if app is not None:
            stop_process(app)
            app_stdout, app_stderr = app.communicate()
            combined = (app_stdout + app_stderr).lower()
            assert "traceback" not in combined
            assert "deprecat" not in combined
        stop_process(mock)
        mock_stdout, mock_stderr = mock.communicate()
        mock_combined = (mock_stdout + mock_stderr).lower()
        assert "traceback" not in mock_combined
        assert "deprecat" not in mock_combined
        assert sha256(PRODUCTION_CONFIG) == original_hash
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_smoke_and_operator_controls(running_stack):
    ws = connect(f"ws://127.0.0.1:{APP_PORT}/ws", open_timeout=10)
    try:
        snapshot = json.loads(ws.recv())
        assert snapshot["type"] == "snapshot"
        assert snapshot["models"] == ["mock-alpha:latest", "mock-beta:latest"]
        seat_names = {seat["name"] for seat in snapshot["seats"]}

        _, initial = receive_until(ws, lambda event, _: event["type"] == "topic")
        assert any(event["type"] == "topic" for event in initial)

        completed = set()
        phases = {name: set() for name in seat_names}

        def all_seats_done(event, _seen):
            if event.get("seat") in phases and event["type"] in {"turn_start", "token", "turn_end"}:
                phases[event["seat"]].add(event["type"])
                if event["type"] == "turn_start":
                    assert event["move_reason"]
                if event["type"] == "turn_end":
                    completed.add(event["seat"])
            return completed == seat_names

        receive_until(ws, all_seats_done, timeout=15)
        assert all(values == {"turn_start", "token", "turn_end"} for values in phases.values())

        # Swap after an active turn has begun: the current turn retains its
        # snapshotted model and the same seat's following turn uses the new one.
        active_start, _ = receive_until(ws, lambda event, _: event["type"] == "turn_start")
        active_seat = active_start["seat"]
        old_model = active_start["model"]
        new_model = "mock-beta:latest" if old_model == "mock-alpha:latest" else "mock-alpha:latest"
        response = httpx.post(f"{BASE_URL}/api/seat_model", json={"seat": active_seat, "model": new_model})
        assert response.status_code == 200
        seats_event, _ = receive_until(ws, lambda event, _: event["type"] == "seats")
        assert next(item for item in seats_event["seats"] if item["name"] == active_seat)["model"] == new_model
        assert active_start["model"] == old_model
        next_start, _ = receive_until(
            ws,
            lambda event, _: event["type"] == "turn_start" and event["seat"] == active_seat,
            timeout=10,
        )
        assert next_start["model"] == new_model
        persisted = json.loads(running_stack.read_text(encoding="utf-8"))
        assert next(item for item in persisted["seats"] if item["name"] == active_seat)["model"] == new_model

        response = httpx.post(f"{BASE_URL}/api/topic", json={"text": "A fresh operator topic?"})
        assert response.status_code == 200
        topic, _ = receive_until(ws, lambda event, _: event["type"] == "topic" and event["text"] == "A fresh operator topic?")
        assert topic["text"] == "A fresh operator topic?"

        response = httpx.post(f"{BASE_URL}/api/pause")
        assert response.status_code == 200
        receive_until(ws, lambda event, _: event["type"] == "status" and event["text"] == "paused")
        produced_turn = False
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            try:
                event = json.loads(ws.recv(timeout=max(0.1, deadline - time.monotonic())))
            except TimeoutError:
                break
            produced_turn |= event["type"] == "turn_start"
        assert not produced_turn

        before_invalid = running_stack.read_bytes()
        assert httpx.post(f"{BASE_URL}/api/seat_model", json={"seat": "missing", "model": "mock-alpha:latest"}).status_code == 400
        assert httpx.post(f"{BASE_URL}/api/seat_model", json={"seat": next(iter(seat_names)), "model": "not-installed"}).status_code == 400
        assert running_stack.read_bytes() == before_invalid

        mock_url = json.loads(running_stack.read_text(encoding="utf-8"))["ollama_url"]
        assert httpx.post(f"{mock_url}/control/tags_failure/1").status_code == 200
        unavailable = httpx.get(f"{BASE_URL}/api/models")
        assert unavailable.status_code == 502
        assert "error" in unavailable.json()
        second_ws = connect(f"ws://127.0.0.1:{APP_PORT}/ws", open_timeout=10)
        try:
            unavailable_snapshot = json.loads(second_ws.recv())
            assert unavailable_snapshot["type"] == "snapshot"
            assert unavailable_snapshot["models"] == []
        finally:
            second_ws.close()
            httpx.post(f"{mock_url}/control/tags_failure/0")

        persisted_before_failure = json.loads(running_stack.read_text(encoding="utf-8"))
        current_model = next(item for item in persisted_before_failure["seats"] if item["name"] == active_seat)["model"]
        attempted_model = "mock-beta:latest" if current_model == "mock-alpha:latest" else "mock-alpha:latest"
        backup_path = running_stack.with_suffix(".backup.json")
        running_stack.rename(backup_path)
        running_stack.mkdir()
        try:
            failed_write = httpx.post(
                f"{BASE_URL}/api/seat_model",
                json={"seat": active_seat, "model": attempted_model},
            )
            assert failed_write.status_code == 500
            rollback_ws = connect(f"ws://127.0.0.1:{APP_PORT}/ws", open_timeout=10)
            try:
                rollback_snapshot = json.loads(rollback_ws.recv())
                assert next(item for item in rollback_snapshot["seats"] if item["name"] == active_seat)["model"] == current_model
            finally:
                rollback_ws.close()
        finally:
            running_stack.rmdir()
            backup_path.rename(running_stack)

    finally:
        ws.close()


def test_reasoning_filter_and_empty_response_retry(running_stack):
    mock_url = json.loads(running_stack.read_text(encoding="utf-8"))["ollama_url"]
    assert httpx.post(f"{BASE_URL}/api/pause").status_code == 200
    assert httpx.post(f"{mock_url}/control/stream_mode/empty_once").status_code == 200
    ws = connect(f"ws://127.0.0.1:{APP_PORT}/ws", open_timeout=10)
    try:
        json.loads(ws.recv())
        assert httpx.post(f"{BASE_URL}/api/resume").status_code == 200
        _end, events = receive_until(
            ws,
            lambda event, seen: event["type"] == "turn_end"
            and any(item["type"] == "token" for item in seen),
            timeout=15,
        )
        assert any(
            event["type"] == "status" and "retrying empty public response" in event["text"]
            for event in events
        )
        metrics = httpx.get(f"{mock_url}/control/metrics").json()
        assert metrics["stream_calls"] >= 2
        public = "".join(event.get("text", "") for event in events if event["type"] == "token")
        assert "private" not in public
        assert "<think>" not in public

        assert httpx.post(f"{BASE_URL}/api/pause").status_code == 200
        assert httpx.post(f"{mock_url}/control/stream_mode/reasoning").status_code == 200
        assert httpx.post(f"{BASE_URL}/api/resume").status_code == 200
        _end, reasoning_events = receive_until(
            ws,
            lambda event, _seen: event["type"] == "turn_end",
            timeout=15,
        )
        visible = "".join(
            event.get("text", "")
            for event in reasoning_events
            if event["type"] in {"token", "turn_end"}
        )
        assert "Public answer after hidden reasoning." in visible
        assert "private" not in visible
        assert "separate private reasoning" not in visible
        assert not re.search(r"</?(?:think|analysis|reasoning)>", visible, re.I)
    finally:
        ws.close()
