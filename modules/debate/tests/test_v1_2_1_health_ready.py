"""v1.2.1 hardening regression tests: /health, /ready, shared httpx client (Phase 6a P1s)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
APP_PATH = ROOT / "app.py"
PORT = 18999

_SEATS = [
    {"name": "Neo", "model": "mock-a:latest", "color": "#4fd1ff", "persona": "B", "thesis": "T"},
    {"name": "Clue", "model": "mock-b:latest", "color": "#7dffa0", "persona": "C", "thesis": "T"},
]


def _make(module_name):
    temp_dir = Path(tempfile.mkdtemp(prefix=".r8-", dir=ROOT / "tests"))
    cfg = temp_dir / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "ollama_url": f"http://127.0.0.1:{9}",
                "port": PORT,
                "seats": _SEATS,
                "insight_panel": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    old = os.environ.get("CONFIG_PATH")
    os.environ["CONFIG_PATH"] = str(cfg)
    spec = importlib.util.spec_from_file_location(module_name, APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    if old is None:
        os.environ.pop("CONFIG_PATH", None)
    else:
        os.environ["CONFIG_PATH"] = old
    return module


@pytest.fixture(scope="module")
def hr_app():
    return _make("debate_table_v1_2_1_hr")


@pytest.fixture()
def client(hr_app):
    # TestClient context manager runs lifespan: shared client is created and
    # closed around the test body.
    with TestClient(hr_app.app, base_url=f"http://127.0.0.1:{PORT}") as c:
        yield c


def test_health_schema_and_liveness(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["config_loaded"] is True
    assert isinstance(body["generation_active"], bool)
    assert body["uptime_seconds"] >= 0
    assert body["version"]


# EPC-01 P1-3. These three tests patched `installed_models`, and `/ready` has not called that
# function since it was refactored to use `installed_model_records()` (app.py:2087) — the rows
# carry the parameter counts the 8B ceiling needs, which a list of names cannot supply. The
# patch therefore stopped intercepting silently: every one of these tests reached the REAL
# ollama on the host and failed with ConnectError/"unavailable" instead of the asserted values,
# in a way that reads like an environment problem rather than lost coverage.
#
# The endpoint was never broken — live, it answers 200 "ready" with both seats installed. What
# was broken is that ready / degraded / unavailable had no test holding them apart. They patch
# the seam the handler actually calls now, and `_records()` builds rows in the shape
# `/api/tags` returns so the ceiling logic runs for real rather than being bypassed.


def _records(*names, parameter_size="8B"):
    """`/api/tags`-shaped rows, the shape `installed_model_records()` returns."""
    return {
        name: {"name": name, "details": {"parameter_size": parameter_size}}
        for name in names
    }


def test_ready_when_all_models_present(hr_app, monkeypatch, client):
    async def records():
        return _records("mock-a:latest", "mock-b:latest")

    monkeypatch.setattr(hr_app, "installed_model_records", records)
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["ollama"]["reachable"] is True
    assert body["ollama"]["endpoint_class"] == "loopback"
    assert body["missing_models"] == []
    assert all(row["installed"] for row in body["seats"])
    assert body["http_client_active"] is True


def test_ready_unreachable_returns_503(hr_app, monkeypatch, client):
    async def broken():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(hr_app, "installed_model_records", broken)
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["ollama"]["reachable"] is False
    assert body["ollama"]["error_type"] == "RuntimeError"


def test_ready_missing_model_degraded_503(hr_app, monkeypatch, client):
    async def partial():
        return _records("mock-a:latest")

    monkeypatch.setattr(hr_app, "installed_model_records", partial)
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["missing_models"] == ["mock-b:latest"]
    assert body["seats"][1]["installed"] is False


def test_ready_over_ceiling_seat_degrades_just_like_a_missing_one(hr_app, monkeypatch, client):
    """The third way this endpoint can be not-ready, and it had no test at all.

    A seat that IS installed but sits above the operator's 8B ceiling cannot take its turn, so
    reporting "ready" would be the silent-absence defect wearing a green badge (app.py:2130).
    This distinguishes degraded-by-ceiling from degraded-by-absence: `missing_models` stays
    empty while the status still drops."""
    async def oversized():
        return _records("mock-a:latest", "mock-b:latest", parameter_size="70B")

    monkeypatch.setattr(hr_app, "installed_model_records", oversized)
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["missing_models"] == [], "the seats are installed; only the ceiling refuses them"
    assert all(row["installed"] for row in body["seats"])
    assert all(row["within_ceiling"] is False for row in body["seats"])
    assert all(row["ceiling_reason"] for row in body["seats"]), \
        "an over-ceiling seat must say WHY it cannot run, not merely that it cannot"


def test_ready_leaks_no_prompt_or_interjection_content(hr_app, monkeypatch, client):
    async def models():
        return ["mock-a:latest", "mock-b:latest"]

    monkeypatch.setattr(hr_app, "installed_models", models)
    hr_app.state.interject = "PRIVATE operator note that must never leak"
    try:
        body = client.get("/ready").json()
    finally:
        hr_app.state.interject = None
    text = json.dumps(body)
    assert "PRIVATE" not in text
    assert "interject" not in {key.lower() for key in body}


def test_lifespan_creates_and_closes_shared_client():
    module = _make("debate_table_v1_2_1_hr_lifespan")
    assert module._http_client is None  # before lifespan
    with TestClient(module.app, base_url=f"http://127.0.0.1:{PORT}"):
        assert module._http_client is not None
    assert module._http_client is None  # closed after lifespan shutdown


def test_new_endpoints_survive_host_guard(client):
    # permitted host passes (TestClient base_url host is 127.0.0.1:PORT)
    assert client.get("/health").status_code == 200
    # disallowed host is still rejected for these routes too (P0-11 interplay)
    response = client.get("/health", headers={"host": "evil.example"})
    assert response.status_code == 421