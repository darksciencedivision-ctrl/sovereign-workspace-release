"""v1.2.1 hardening regression tests: control-plane isolation (P0-10/11/12)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

ROOT = Path(__file__).resolve().parent.parent
APP_PATH = ROOT / "app.py"
PORT = 18944

_SEATS = [
    {"name": "Neo", "model": "mock-a:latest", "color": "#4fd1ff", "persona": "B", "thesis": "T"},
    {"name": "Clue", "model": "mock-b:latest", "color": "#7dffa0", "persona": "C", "thesis": "T"},
]


@pytest.fixture(scope="module")
def guard_app():
    temp_dir = Path(tempfile.mkdtemp(prefix=".r4-guard-", dir=ROOT / "tests"))
    cfg = temp_dir / "config.json"
    doc = {
        "ollama_url": "http://127.0.0.1:9",
        "port": PORT,
        "seats": _SEATS,
        "insight_panel": False,
    }
    cfg.write_text(json.dumps(doc) + "\n", encoding="utf-8")
    old = {k: os.environ.get(k) for k in ("CONFIG_PATH", "OLLAMA_URL")}
    os.environ["CONFIG_PATH"] = str(cfg)
    os.environ.pop("OLLAMA_URL", None)
    spec = importlib.util.spec_from_file_location("debate_table_v1_2_1_guard", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["debate_table_v1_2_1_guard"] = module
    try:
        assert spec.loader is not None
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop("debate_table_v1_2_1_guard", None)
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _transport(module):
    return httpx.ASGITransport(
        app=module.app, root_path="", client=(("127.0.0.1", PORT))
    )


def _request(module, method, path, headers=None):
    body = json.dumps({"text": "x"}) if method == "POST" and path == "/api/topic" else None
    return httpx.Request(method, f"http://127.0.0.1:{PORT}{path}", headers=headers or {}, content=body)


def run_request(module, method, path, headers=None):
    import asyncio

    request = _request(module, method, path, headers)

    async def _send():
        transport = httpx.ASGITransport(app=module.app)
        response = await transport.handle_async_request(request)
        await response.aread()
        return response

    return asyncio.run(_send())


def test_invalid_host_rejected_on_http(guard_app):
    for host in ("evil.example:8700", f"evil.example:{PORT}", "192.168.0.10"):
        response = run_request(guard_app, "GET", "/", {"host": host})
        assert response.status_code == 421, (host, response.status_code)


def test_wrong_port_host_rejected(guard_app):
    response = run_request(guard_app, "GET", "/", {"host": f"127.0.0.1:{PORT - 1}"})
    assert response.status_code == 421


def test_valid_loopback_hosts_accepted(guard_app):
    for host in (f"127.0.0.1:{PORT}", f"localhost:{PORT}", f"[::1]:{PORT}"):
        response = run_request(guard_app, "GET", "/", {"host": host})
        assert response.status_code == 200, (host, response.status_code)


def test_foreign_origin_mutation_rejected(guard_app):
    response = run_request(
        guard_app,
        "POST",
        "/api/pause",
        {"host": f"127.0.0.1:{PORT}", "origin": "https://evil.example"},
    )
    assert response.status_code == 403
    assert b"foreign-origin" in response.content


def test_cross_site_sec_fetch_mutation_rejected(guard_app):
    response = run_request(
        guard_app,
        "POST",
        "/api/pause",
        {"host": f"127.0.0.1:{PORT}", "sec-fetch-site": "cross-site"},
    )
    assert response.status_code == 403


def test_same_origin_mutation_accepted_and_originless_nonbrowser_allowed(guard_app):
    ok = run_request(
        guard_app,
        "POST",
        "/api/pause",
        {"host": f"127.0.0.1:{PORT}", "origin": f"http://127.0.0.1:{PORT}"},
    )
    assert ok.status_code == 200
    non_browser = run_request(
        guard_app, "POST", "/api/resume", {"host": f"127.0.0.1:{PORT}"}
    )
    assert non_browser.status_code == 200
    # restore live state for later tests in other files using this module only
    guard_app.state.paused = False


def test_foreign_websocket_origin_rejected_before_snapshot(guard_app):
    client = TestClient(guard_app.app, root_path="")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/ws",
            headers={"host": f"127.0.0.1:{PORT}", "origin": "https://evil.example"},
        ) as ws:
            ws.receive_json()


def test_allowed_origin_websocket_receives_snapshot(guard_app):
    client = TestClient(guard_app.app, root_path="")
    with client.websocket_connect(
        "/ws",
        headers={
            "host": f"127.0.0.1:{PORT}",
            "origin": f"http://localhost:{PORT}",
        },
    ) as ws:
        message = ws.receive_json()
        assert message["type"] == "snapshot"


def test_originless_websocket_client_policy_allows_tooling(guard_app):
    client = TestClient(guard_app.app, root_path="")
    with client.websocket_connect(
        "/ws", headers={"host": f"127.0.0.1:{PORT}"}
    ) as ws:
        message = ws.receive_json()
        assert message["type"] == "snapshot"